# Engine Architecture Review — Findings
Date: 2026-05-20

## Executive Summary

The led-ticker engine is structurally sound: the registry/protocol pattern is consistent, ~1438 tests guard the hardware contract, and the load-bearing invariants documented in CLAUDE.md are enforced by AST-scanning tripwires. The dominant theme across all four reviews is **weak typing at the boundary** — `Canvas = Any`, `**kwargs` in `Widget.draw`, `frame_invariant: bool` answered by convention, and unknown widget kwargs that bypass `led-ticker validate` and only surface as raw `TypeError` at startup. The single most important finding is **Critical #1**: the validate-clean → boots-clean contract is silently broken for every misspelled or misplaced widget field because `_build_widget` splats `**widget_cfg` into the dataclass without an allowlist check.

## Critical Findings

### C1. Unknown widget kwargs bypass `validate` and surface as raw `TypeError` at startup
`_build_widget` (`src/led_ticker/app.py:535-786`) pops known dispatch keys and then splats the remaining `widget_cfg` into `cls(**widget_cfg)`. There is no per-widget allowlist. `validate.py` rule 29 (`validate.py:409`) patches one specific case (`text_loops` on TwoRowMessage); every other typo (`text_color`, `font_threshhold`, `top_text` on a single-row gif) falls through to a startup `TypeError` pointing at attrs internals — no field suggestion, no section index. This silently breaks the documented "validate clean → it'll boot" contract.

Example:
```toml
[[playlist.section.widget]]
type = "message"
text = "hello"
text_color = [255, 0, 0]   # typo: should be font_color
```
`led-ticker validate` reports no error; startup raises `TypeError: TickerMessage.__init__() got an unexpected keyword argument 'text_color'`.

Fix direction: in `_build_widget(validate_only=True)`, compare remaining `widget_cfg` keys against `cls.__attrs_attrs__` and raise with `difflib.get_close_matches` suggestion. This also fixes Significant #4 below (ignored `top_color` on single-row image widgets).

### C2. `feedparser.parse` blocks the asyncio event loop during RSS updates
`RSSFeedMonitor.update()` (`src/led_ticker/widgets/rss_feed.py:66`) awaits `aiohttp.get` but then runs `feedparser.parse(feed_data)` synchronously on the main event loop thread. A feed with hundreds of items can take tens of milliseconds; at the engine's 50ms tick budget, a single 50-100ms parse spike will visibly stutter scrolling on the panel.

Fix direction: `await asyncio.to_thread(feedparser.parse, feed_data)`.

### C3. Engine tick sleeps for a fixed duration regardless of work time
Every per-tick loop runs `advance_frame → draw → swap → asyncio.sleep(tick_seconds)` where `tick_seconds = ENGINE_TICK_MS/1000 = 0.05` — not `0.05 - work_elapsed`. Call sites: `src/led_ticker/ticker.py:1117-1163`, `1138-1144`, `444-449`, `633-639`; `src/led_ticker/widgets/_image_base.py:1389`, `1658`. Every tick takes `work_time + 50ms`. If a bigsign tick does ~10ms of Python work, actual FPS is ~16.7 instead of 20 — over an hour, continuous-phase effects (Rainbow, ColorCycle, RainbowChaseBorder) advance ~17% slower than configured. The bigsign-tuned "~12s per revolution" RainbowChaseBorder defaults actually take 14s+ under load.

Fix direction: capture `t0 = loop.time()` before work, sleep `max(0, tick_seconds - (loop.time() - t0))`.

### C4. `Widget` Protocol is unenforced documentation; `_has_play` dispatch silently misroutes on broken subclasses
Two related boundary-typing failures with the same shape — "the protocol is a comment, not a check":

- **Widget Protocol is documentation only** (`src/led_ticker/widget.py:18-43`, `_types.py:21`): `DrawResult = tuple[Any, int]`, `Canvas = Any`, `**kwargs: Any`. Every callable named `draw` satisfies the Protocol — including bare `Mock()` objects. Zero `isinstance(..., Widget)` call sites in the engine. A widget that forgets to return the canvas (returns `None`), or returns `(int, canvas)` reversed, fails neither mypy nor any runtime check — it fails visibly only on the panel.

- **`_has_play` dispatch is asymmetric** (`src/led_ticker/ticker.py:770-777`): looks up `play` on `type(widget)` and calls `inspect.iscoroutinefunction`. A subclass overriding `play` as a plain method (no `async`) silently falls through to the `draw()` path with no warning — fed to `_swap_and_scroll`, the widget mis-renders silently. There is no `else: raise` branch confirming the dispatch found a valid handler.

Fix direction: tighten `DrawResult` to `tuple["Canvas", int]` where `Canvas` is a real `Protocol` (`SetPixel`, `width`, `height`, `Clear`, `Fill`); add an explicit `Playable` Protocol with `runtime_checkable`; have `_has_play` raise on `play`-attribute-present-but-not-coroutine.

## Significant Findings

### S1. `app.py` mixes five unrelated responsibilities in 1256 lines
`src/led_ticker/app.py` simultaneously contains: CLI argparse + entry (`main`, lines 1192-1256), TOML→provider coercion (`_coerce_color_provider`, `_coerce_border`, `_coerce_animation`, `_coerce_widget_colors`, lines 97-498), widget factory (`_build_widget`, `_build_title`, 250+ lines), transition factory, frame factory, and the main `run` async loop. Editing any single concern requires touching the same file as the run loop; `_build_widget` is 250 lines doing six interleaved validation jobs. The `validate_only=True` boolean toggle is a code smell pointing at this — a proper factory module would let `validate.py` reuse construction without the toggle. **This is the single biggest maintainability tax in the file map**, and it directly compounds Critical #1 (no allowlist) because field validation lives nowhere coherent.

Fix direction: split into `app/cli.py`, `app/factories.py`, `app/coercion.py`, `app/run.py`.

### S2. `ticker.py` private scrolling functions should be `Ticker` methods
`ticker.py:402-650` defines `_scroll_and_delay`, `_scroll_one_by_one`, `_scroll_side_by_side`, `_scroll_between`, `_run_swap`, `_run_gif`, `_show_one`, `_swap_and_scroll` as module-level free functions that re-thread `canvas`, `frame`, `notif_queue`, `scroll_speed` through their signatures even though every caller is `Ticker.run_*` which already has these as fields. No polymorphism, no reuse from outside — pure boilerplate.

Fix direction: pull onto `Ticker` as methods.

### S3. `_swap_and_scroll` (160 lines) has three duplicated tick-loop branches
`ticker.py:1004-1165` selects between `forces_offscreen_scroll`, `wraps_forever`, and overflow-vs-held branches, each rewriting the `advance_frame + reset + draw + swap + sleep` pattern slightly differently. The `is True` strict-equality guards at lines 1041 and 1076 exist specifically to defend against Mock auto-attrs. The AST-scanner tripwire in `tests/test_engine_redraw_contract.py` exists *because of* this exact branching drift.

Fix direction: extract a `TickLoop` helper that the three branches build with different step/stop predicates.

### S4. `ScaledCanvas` leaks across 24+ `isinstance` sites — the abstraction does not encapsulate
The wrapper is pattern-matched at `text_render.py:26`, `pixel_emoji.py` (4 sites), `transitions/{pokeball,baseball,nyancat}.py` (5 sites), `widgets/_image_base.py` (4 sites), `ticker.py` (4 sites). The wrapper exposes `scale`, `_y_offset`, and `real`; `ticker.py:75` reads `canvas._y_offset` cross-module. Every new feature that wants hi-res paint must learn both the unwrap pattern AND the detect pattern; the abstraction promises "transparent scaling" but hi-res requires non-transparent branching.

Fix direction: add a `paint_hires(canvas, callback)` helper that handles both unwrap and scale forwarding; rename `_y_offset` → `y_offset_real` since cross-module reads already happen.

### S5. `Widget.draw` uses `**kwargs` as a typed-protocol escape hatch
`src/led_ticker/widget.py:22-43` lists three recognized kwargs (`y_offset`, `region`, `font_color`) — all optional, all silently dropped if not consumed. Eight widget call sites do `y_offset = kwargs.get("y_offset", 0)`. Typos fail silently (`y_ofset=5` does nothing); widgets that should accept a kwarg are indistinguishable from widgets that ignored it. `region` is documented but **consumed nowhere in the codebase** — dead documentation.

Fix direction: hoist named kwargs into the Protocol signature as `*, y_offset: int = 0, region: Region | None = None, font_color: Color | None = None` and drop `**kwargs`. Delete `region` (YAGNI) or implement it. Add to CLAUDE.md "Adding a New Widget" that ignoring `y_offset` breaks vertical transitions.

### S6. `frame_invariant: bool` flag has silent, asymmetric failure modes
`src/led_ticker/color_providers.py:51-52`. Lying False-when-True wastes CPU but renders correctly; lying True-when-False makes the widget freeze on image widgets' fast path with no warning. All existing examples set `True` explicitly — a new animated provider author copying a static provider as a template ships a frozen widget.

Fix direction: make `frame_invariant` a `@property` that raises `NotImplementedError` so authors must answer it, or add a runtime tripwire comparing `color_for(0, ...)` and `color_for(100, ...)` at registration.

### S7. Registry decorators silently overwrite duplicate names
Both `src/led_ticker/widgets/__init__.py:14-15` and `transitions/__init__.py:73-74` do `_REGISTRY[name] = cls` without collision checks. A contributor copy-pasting an existing widget file as a template and forgetting to rename gets the new behavior of the old name silently — no compile-time, runtime, or test signal.

Fix direction: `raise ValueError(f"duplicate registration {name!r}: already bound to ...")` when key already exists.

### S8. Transition registration requires editing two parallel lists in `transitions/__init__.py`
`src/led_ticker/transitions/__init__.py:265-324` has both an auto-import list AND a parallel re-export list. Adding a transition requires (a) the decorator, (b) auto-import entry, (c) re-export entry. Forgetting (b) means the decorator never runs and the name is silently unavailable. CLAUDE.md mentions (b) but not (c).

Fix direction: use `pkgutil.iter_modules` for auto-discovery, or add a test asserting every `.py` under `transitions/` appears in both lists.

### S9. No `Animation` Protocol; `AnimationFrame.cursor_override` is dead
`src/led_ticker/animations.py:1-56` declares `AnimationFrame` and `Typewriter` but never defines an `Animation` Protocol — compare to `color_providers.py:41-54` and `borders.py:72-77` which both formalize their Protocol. A contributor wanting "FadeIn" must reverse-engineer the signature from `widgets/message.py:80-86` and `widgets/_image_base.py:664`. `AnimationFrame.cursor_override` (`animations.py:24-27`) is dead: Typewriter always returns None, image widgets explicitly ignore it (`_image_base.py:657`), `message.py:65-67` has a comment that the override branch was removed.

Fix direction: drop `cursor_override` from `AnimationFrame`. Either add the Protocol now (matches the pattern of `ColorProvider` / `BorderEffect`) or accept Typewriter as concrete-only until a second animation appears.

### S10. Wrong-shape `[r, g, b]` lists produce cryptic C-level errors
`_coerce_color_provider` (`app.py:97-149`) handles `len == 3` by calling `graphics.Color(*value)`. `font_color = [255, "ff", 0]` or `font_color = [256, 0, 0]` raises a C-level `TypeError` from rgbmatrix with no field context. `_coerce_border` (`app.py:282-303`) already hardens against bool components and out-of-range ints via `_validate_rgb` — the color-provider path was never updated.

Fix direction: lift `_validate_rgb` into a shared helper, call from `_coerce_color_provider` and `_coerce_widget_colors` before `graphics.Color(*value)`.

### S11. `font_color` / `color` / `top_color` / `bottom_color` naming has three overlapping conventions
- `TickerMessage`, `weather`, `mlb`, `gif`, `image`, `coinbase` → `font_color`
- Section title block → `color` (translated to `font_color` in `_build_title` at `app.py:824-829`)
- `TwoRowMessage` → `top_color` + `bottom_color` (no `font_color`)
- `gif`/`image` with `bottom_text` set → `top_color` + `bottom_color`
- `color = "random"` on title cycles a fixed 8-entry palette; `font_color = "random"` on widgets uses `color_providers.Random` (RNG, different palette)

A user reading `config.example.toml` (titles use `color = "random"`), copying to a normal widget, silently fails — the title block sets up the mental model wrong on page one. `top_color` on a single-row gif (mode chosen by `bottom_text != ""`) is silently ignored.

Fix direction: accept `font_color` on title blocks as canonical synonym; rename internal title palette to `"title_palette"`; explicitly reject `top_*`/`bottom_*` on image widgets when `bottom_text == ""`.

### S12. Per-widget field surface has crossed the memorize-or-grep threshold
`_BaseImageWidget` ~39 fields; `TwoRowMessage` ~18; `_build_widget` ~12 dispatch-level fields. Per-widget surface is 40-60 knobs with no schema export.

Fix direction: `led-ticker validate --list-fields type=two_row` that prints `_build_widget`-dispatch fields plus the widget's `__attrs_attrs__` with defaults and types. Also serves as the foundation for fixing Critical #1.

### S13. `Canvas = Any` defeats type checking across the engine
`src/led_ticker/_types.py:12-14` defines `Canvas = Any`, `Font = Any`, `Color = Any`. Every `draw(self, canvas: Canvas, ...)`, every transition `frame_at(t, canvas, outgoing, incoming)`, every `SwapOnVSync(canvas) -> Canvas` is unchecked. `ScaledCanvas` already satisfies a `SetPixel`/`width`/`height`/`Clear`/`Fill` shape structurally.

Fix direction: introduce `CanvasLike` Protocol and use everywhere. (Companion to Critical #4 and Significant #4.)

### S14. Engine widget cache + frame-counter mutable state has an aliasing risk
`src/led_ticker/app.py:1014-1033` caches widgets by config key and reuses across section visits. `_FrameAware._effect_frames` (`widgets/_frame_aware.py:55`) is per-instance mutable state. `_scroll_side_by_side` (`ticker.py:560-568`) explicitly dedups by `id()` because the same widget can appear in multiple buffer slots simultaneously. Other modes (`_run_swap`, `_scroll_one_by_one`) assume one-widget-at-a-time but the cache-and-cycle pattern doesn't guarantee that for all consumers.

Fix direction: either document the no-aliasing invariant with an assertion (`_frame_count_owner` claim on first `advance_frame`), or make frame state external to the widget — keyed `dict[(widget_id, visit_id), int]` owned by the engine.

### S15. `get_text_width` cache is `dict.clear()`-at-256, not LRU
`src/led_ticker/drawing.py:122-124`. Crossing the threshold causes a thundering-herd recompute on the next tick for all cached strings. RSS feeds that build a fresh `TickerMessage` per story can churn the cache fast.

Fix direction: use `functools.lru_cache` directly, or pop oldest entry instead of `dict.clear()`.

### S16. Rainbow / ColorCycle / RainbowChaseBorder allocate `colorsys.hsv_to_rgb` + `graphics.Color()` per character per tick
On a held bigsign widget with `font_color = "rainbow"`, every tick calls `Rainbow.color_for` once per character — ~340 Python function calls per second through `colorsys.hsv_to_rgb` plus `graphics.Color()` C-extension allocation. References: `src/led_ticker/color_providers.py:106-110`. `RainbowChaseBorder.paint` (`borders.py:202-215`) compounds this: rebuilds the perimeter list every frame AND runs `colorsys.hsv_to_rgb` per pixel — 640 HSV conversions per frame for a 1-px ring on bigsign.

Fix direction: precompute a 360-entry hue → `graphics.Color` table at startup, shared by Rainbow, ColorCycle, RainbowChaseBorder, ColorCycleBorder. `@functools.cache` `_perimeter_pixels` keyed on `(width, height, thickness)`.

### S17. `ScaledCanvas.SetPixel` at scale=4 does 16 Python→C calls per logical pixel
`src/led_ticker/scaled_canvas.py:85-98`. Nested `for dy in range(s): for dx in range(s)` calls `real.SetPixel(...)` s² times. BDF text on bigsign: ~1,088 `SetPixel` calls per draw, ~21,760/second at 20fps. Each is a Python→C call (~1µs est).

Fix direction: requires native batch-SetPixel binding — out of scope without modifying the rgbmatrix fork. Listed for awareness; needs profiling before any rewrite.

## Minor Findings

### M1. `Transition` Protocol declares `min_frames: int` required but runner uses `hasattr`
`transitions/__init__.py:39` vs `:159`. Many transitions in `effects.py` don't declare it. Fix: change to `min_frames: int = 0` on the Protocol.

### M2. `frame_at(**kwargs)` recognized kwargs are undocumented
`outgoing_scroll_pos`, `duration_ms`, `incoming_bg_color` — transition authors can't discover available context without reading existing transitions. Fix: document in Protocol docstring like `Widget.draw` does.

### M3. `RainbowChaseBorder.frame_invariant` is `@property`; Protocol declares plain attribute
`src/led_ticker/borders.py:75` vs `:198-200`. Fix: document on Protocol that it may be a property.

### M4. `Scroll` transition imports private engine symbol `_draw_scroll_frame` from `ticker`
`src/led_ticker/transitions/effects.py:167-171`. Extension authors shouldn't import engine privates. Fix: promote `_draw_scroll_frame` to public or copy into `Scroll.frame_at`.

### M5. `Widget` Protocol doesn't declare frame-aware methods
Engine calls `pause_frame` / `resume_frame` / `reset_frame` / `advance_frame` via duck-typing — widgets wanting animated effects MUST inherit `_FrameAware` but the Protocol doesn't say so. Fix: add `FrameAwareWidget` Protocol; note in CLAUDE.md "Adding a New Widget".

### M6. `PushRandom.min_frames` fallback fires every first-frame
`transitions/push.py:241-245`. `_current` is None on first query. Fix: pre-construct one sub-transition in `__init__`, or document.

### M7. `transition_specified: bool` exposes a dual-role design users can't see
Writing `transition = "wipe_left"` on a single-widget section silently becomes the inter-widget transition the moment a second widget is added. Fix: split into `entry_transition` and `widget_transition`; keep `transition` as "set both" shorthand.

### M8. `_ERROR_PATTERNS` only covers two migration patterns; no tripwire keeps it in sync
`validate.py:36`. Future deprecations without table entries degrade to `"See error message for details."` Fix: typed `MigrationError(message, suggested_fix)` so `_classify_error` reads from the exception.

### M9. Gradient/color_cycle errors leak `from_color`/`to_color` instead of TOML `from`/`to`
`app.py:207-211`. Fix: substitute in the allowed-keys error message.

### M10. `from __future__ import annotations` missing from 3 modules
`src/led_ticker/__init__.py`, `widgets/__init__.py`, `widgets/crypto/__init__.py`. Fix: add for consistency.

### M11. `_types.py` mixes C-extension stubs with real type aliases
`_types.py:12-21`. Fix: split into `_compat_types.py` and `_types.py`, or add section comments.

### M12. `ColorTuple` + `graphics.Color` + `_ConstantColor` — three representations
`_types.py:19`. `_draw_hires_circle` at `ticker.py:77` does `isinstance(color, tuple)` to handle both. Fix: pick one internal representation post-coercion (`graphics.Color`) and convert at boundaries.

### M13. `_FrameAware` `attrs.define` + `init=False` silently breaks if subclasses forget `@attrs.define`
`src/led_ticker/widgets/_frame_aware.py:36-55`. Fix: `__init_subclass__` check, or make it a plain non-attrs class.

### M14. `LedFrame.matrix` typed as `RGBMatrixType = Any` with `default=None`
`src/led_ticker/frame.py:36, 71`. Fix: `attrs.field(init=False, default=attrs.NOTHING)` or sentinel + property.

### M15. `TransitionConfig.transition_obj: Any = None` mutated at runtime
`src/led_ticker/config.py:42` + `app.py:1135`. Fix: lift into a `ResolvedTransition`; keep `TransitionConfig` declarative.

### M16. `AsyncWidget(Widget, Protocol)` defined but never referenced
`src/led_ticker/widget.py:55-61`. Fix: delete or actually use.

### M17. Dissolve `_sequence` is per-instance, not cached across instances
`transitions/effects.py:67-75`. First dissolve per section pays the shuffle cost (~16K elements on bigsign). Fix: `@functools.cache` on `(w, h, seed)`.

### M18. `compute_baseline` called per-draw in `TickerMessage.draw`; result is invariant
`src/led_ticker/widgets/message.py:113`. `_BaseImageWidget` already hoists this (`:1249`). Fix: cache `baseline_y` on the widget after first draw.

### M19. `pixel_emoji._parse_segments` runs `re.split` per `measure_width`/`draw_with_emoji` call
`src/led_ticker/pixel_emoji.py:2740`, `:2778`, `:2831`. For a held widget, same string parsed every tick. Fix: cache parsed segments on the widget alongside `_has_emoji_cached`. Diminishing return.

## Cross-Cutting Observations

### CC1. The boundary between "engine" and "widget/transition contributor" is typed as `Any`
Surfaces in: Critical #4 (Widget Protocol unenforced, `_has_play` silent misroute), Significant #5 (`**kwargs` escape hatch), Significant #13 (`Canvas = Any`), Significant #4 (`ScaledCanvas` leaked everywhere), Significant #9 (no `Animation` Protocol), Minor #1/#2/#3/#5 (Protocol fields missing, `frame_at` kwargs undocumented). Every protocol in the codebase is either "documentation that lies" or "duck-typed with no Protocol at all." A single concerted typing pass — `CanvasLike`, `Playable`, `Animation`, `FrameAwareWidget`, tightened `Widget.draw` signature — would close the entire class.

### CC2. Silent failure is the default failure mode
Critical #1 (unknown kwargs), Critical #4 (wrong `play` signature), Significant #6 (wrong `frame_invariant`), Significant #7 (duplicate registry names), Significant #8 (forgotten auto-import), Significant #10 (bad RGB tuples), Significant #11 (`top_color` on single-row image), Minor #6 (`PushRandom.min_frames` fallback). The codebase has invested heavily in tripwires for the *render path* (constraint #12 AST scanner, double-buffered test stubs, `test_docs_config_options_drift`) but extension/config surface failures take the panel down with no diagnostic. A `--strict` validation mode + per-area registration guards would mirror the render-path investment.

### CC3. `app.py` is the gravity well that absorbs concerns from every layer
Significant #1 (5 responsibilities, 1256 lines) is the cause; Critical #1 (no allowlist), Significant #10 (untyped color shape), Significant #11 (naming inconsistency), Significant #12 (no schema export) are symptoms. As long as `_build_widget` is a 250-line function with a `validate_only` bool, the validator and the runtime factory will keep drifting, and field-level validation has no natural home.

### CC4. Continuous-phase color effects are the performance hot spot
Critical #3 (fixed-duration sleep accumulates ~17% drift) and Significant #16 (Rainbow/ColorCycle/Border per-character allocation) compound: the loop runs slower than configured AND each iteration does more work than it needs to. The fixes are independent (`max(0, tick - elapsed)` sleep; cached hue → Color table) but ship together they fully restore the documented bigsign defaults (12s revolution actually 12s; per-char rainbow not eating measurable budget).

### CC5. The `ScaledCanvas` wrapper does not actually isolate scale-aware code
Significant #4 (24+ `isinstance` sites), constraint #10 (callers must rebind `.real` after every swap), constraint #11 (Dissolve must manually `unwrap_to_real`), Significant #17 (per-pixel block expansion). The wrapper provides one good service (`draw_bdf_text`) and then leaks the abstraction at every other consumer. Either commit to encapsulation (helpers like `paint_hires`, `unwrap_for_scatter`) or rename the type to make the leakage honest.

## Prioritized Action List

### Quick Wins (< 1 PR each)

1. **Wrap `feedparser.parse` in `asyncio.to_thread`** — Critical #2. `rss_feed.py:66`. One line; eliminates event-loop stalls.
2. **Fix engine tick drift to `max(0, tick - elapsed)`** — Critical #3. ~6 call sites in `ticker.py` + `_image_base.py`. Restores documented timing for all continuous-phase effects.
3. **Validate RGB tuples in `_coerce_color_provider`** — Significant #10. Lift `_validate_rgb` from `borders.py` into a shared module; call from color provider and widget-color coercion.
4. **Raise on duplicate registry names** — Significant #7. Two-line change in `widgets/__init__.py:15` and `transitions/__init__.py:74`.
5. **Drop dead `cursor_override` field from `AnimationFrame`** — Significant #9 (partial). `animations.py:24-27`. Plus delete `region` from `Widget.draw` docstring (Significant #5, partial).
6. **Delete unused `AsyncWidget` Protocol** — Minor #16. `widget.py:55-61`.
7. **Fix `Transition.min_frames` Protocol default + document `frame_at` kwargs** — Minor #1, #2. `transitions/__init__.py:39`.
8. **Cache `_perimeter_pixels` and `compute_baseline` on TickerMessage** — Significant #16 (partial), Minor #18. `@functools.cache` decoration.
9. **Promote `_draw_scroll_frame` (or inline into `Scroll`)** — Minor #4. `effects.py:167-171`.
10. **Tighten error messages: `from_color`→`from`, `to_color`→`to`** — Minor #9. `app.py:207-211`.
11. **Convert `get_text_width` cache to `functools.lru_cache`** — Significant #15. `drawing.py:122-124`.
12. **Add `from __future__ import annotations` to 3 missing modules** — Minor #10.

### Medium (1–2 PRs each)

1. **Unknown-kwarg allowlist + `did-you-mean` for `_build_widget`** — Critical #1. Per-widget allowlist from `cls.__attrs_attrs__` + `difflib.get_close_matches`. Also serves as foundation for Significant #12 (`--list-fields`).
2. **Precomputed 360-entry hue → `graphics.Color` LUT** — Significant #16. New module `color_lut.py`; rewire Rainbow, ColorCycle, RainbowChaseBorder, ColorCycleBorder.
3. **Typed `Canvas`, `Color`, `Font` Protocols replacing `Any`** — Significant #13, Critical #4 (partial), Significant #4 (partial). New `CanvasLike` Protocol; threaded through `Widget.draw`, transitions, `SwapOnVSync` return type.
4. **Tighten `Widget` Protocol: drop `**kwargs`, hoist `y_offset`/`font_color`** — Significant #5. Update the 8 widgets that consume `y_offset`; mention `_FrameAware` requirement in CLAUDE.md.
5. **Make `frame_invariant` a `@property` raising `NotImplementedError`** — Significant #6. `color_providers.py:51-52` + `borders.py`. Forces authors to answer.
6. **Auto-discover transitions via `pkgutil.iter_modules`** — Significant #8. Removes the two-list-edit footgun.
7. **`led-ticker validate --list-fields type=X`** — Significant #12. Reuses the allowlist from Medium #1; eliminates the memorize-or-grep tax.
8. **Tighten `_has_play` dispatch with explicit `Playable` Protocol + assertive failure** — Critical #4 (partial). `ticker.py:770-777`.
9. **`Animation` Protocol + document the contract** — Significant #9 (rest). Pairs with deleting `cursor_override`.
10. **Split `entry_transition` vs `widget_transition` on `SectionConfig`** — Minor #7. Keep `transition` as shorthand; migration error for clarity.

### Large (multi-PR)

1. **Split `app.py` into `app/cli.py`, `app/factories.py`, `app/coercion.py`, `app/run.py`** — Significant #1. Foundational refactor; removes the gravity well that makes Critical #1, Significant #10/#11/#12 hard to fix coherently. The validator and the runtime factory stop drifting once they share one factory module without a `validate_only` toggle.
2. **Pull `_scroll_*` / `_run_*` / `_swap_and_scroll` onto `Ticker` as methods + extract `TickLoop` helper** — Significant #2, Significant #3. Collapses the boilerplate, dedupes the three tick-loop branches, and the AST-scanner tripwire becomes redundant (the loop body lives in one place).
3. **`ScaledCanvas` encapsulation pass: `paint_hires` helper + rename `_y_offset`** — Significant #4. Removes the 24+ `isinstance` sites; closes constraint #10/#11 ergonomics; either honestly hides scale or renames to declare the leakage.
4. **Engine-owned frame-counter state, keyed `(widget_id, visit_id)`** — Significant #14. Removes the cache-aliasing risk; lets widgets become stateless from the engine's perspective. Companion to subagent-driven `_FrameAware` cleanup (Minor #13).
5. **`led-ticker validate --strict` mode + typed `MigrationError`** — Cross-cutting CC2. Inverts the silent-failure default. Builds on Medium #1 (allowlist) and Minor #8 (typed migration errors).
