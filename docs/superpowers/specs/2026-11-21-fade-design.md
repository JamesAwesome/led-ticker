# Design: `fade` transition (crossfade, optional dip through a colour)

Roadmap item 4, approach B (gate `2026-11-20-fade-gate.md`, local-only;
James 2026-11-21: "both if it's easy, simple dip if it's complex to have
both"). Status: **APPROVED 2026-11-22** via the design antagonist loop James
delegated ("loop, then demo on moonbunny/bigsign"); five cycles, exit on
LOW / DOCS only, ledger
`docs/superpowers/reviews/2026-11-22-fade-design-antagonist.md`. Size: a project (a new transition
module, a readable-raster surface, runner kwargs with an API minor bump, a
meta-wrapper hook forward, docs, a demo GIF, a hardware check).

## Intent and why

A soft swap between two messages. Core has no fade; `dissolve` is the only
soft transition. Five first-party plugins hand-roll brightness fades, and
the flight plugin's exists because a hard cut "read as a glitch on the
physical panel" in hardware review (gate section 2). Daktronics names the
effect. A sign owner who wants the broadcast crossfade, or the classic dip
to black, should get it from one core transition name.

## Goals / non-goals / anti-goals

- Goals: `transition = "fade"` crossfades outgoing into incoming, honouring
  `duration`, `easing`, both sides' `bg_color`, cross-scale and
  cross-`content_height` entries and `outgoing_scroll_pos`;
  `transition_color = [r, g, b]` turns it into a dip through that colour;
  `fade` joins the `random` / `auto` default pool; every existing
  transition is byte-identical; the precursor PR changes no existing
  config's output.
- Non-goals: software gamma (the panel's inverse CIE 1931 L* table already
  makes an 8-bit blend lightness-linear, gate sections 2 and 5); new
  easings (gate section 12, ask 2); exporting `PixelBuffer` through
  `led_ticker.plugin`; unifying flair's `Raster` onto it (later, with a
  plugin consumer); a per-widget brightness fade (the gain proxy stays
  text-only); a hardware-brightness dip (gate section 6).
- Anti-goals: `GetPixel` on any real canvas; a frame that allocates a
  framebuffer (`create_canvas`); a pooled fade that replays the previous
  firing's snapshots; a snapshot target missing a canvas method, which
  would make the draw guard trip a healthy widget's breaker; any change to
  an existing render when `fade` is absent.

## Approaches considered

- **A. Mix only.** Rejected only because B costs one `Image.blend` call
  more.
- **B. Mix, plus a dip through a colour (chosen).** Same snapshots, a
  different blend factor per half.
- **C. Dip only.** James's fallback if the mix path grows during the build.
- **D. Defer.** Loses the one effect with a hardware-review finding behind
  it.
- **Through-colour carrier.** A new `through` key was rejected: core
  constructors receive only `color` / `colors` from `_build_trans_obj`
  (`app/factories.py:461-464`), and `_child_transition_cfg` refuses unknown keys
  on a core pool entry (`factories.py:580-591`, used by `_resolve_pool`), so a new key costs the
  builtin-key set, the factory, the pool refusal, a validate rule and the
  config-options drift test. `transition_color` (the `color_flash`
  precedent) costs nothing: chosen.
- **Snapshot timing.** Lazy, on the first `frame_at` of a firing, released
  by `end_firing` (chosen: the hook already exists and the runner calls it
  on every transition in its `finally`); vs a new pre-loop runner hook
  (rejected: a runner change for one consumer).
- **Seam for the blend.** Snapshot both widgets into readable rasters and
  blend in Pillow (chosen); vs generalising `GainCanvas` (rejected: a
  write-side proxy dims one widget, it cannot mix two); vs the hardware
  brightness knob (rejected: through-black only, dims the busy dot, races
  the brightness scheduler, invisible on the headless backend).

## Design

### Config surface

```toml
transition = "fade"                                            # mix
transition = { type = "fade", duration = 1.0 }
transition = { type = "fade", transition_color = [0, 0, 0] }   # dip through black
transition = { type = "fade", transition_color = [255, 255, 255], duration = 0.8 }
```

- The flat sibling form (`transition = "fade"` plus `transition_color` on
  the section) is the same thing, as for every core transition.
- `transition_colors` (the list) is not read by `fade`; rule 74 already
  warns about a list on a single-colour core transition.
- In a pool, members inherit the slot's `transition_color` (item 2 builder
  decision 2), so `{ type = "random", transition_color = [255, 0, 0] }`
  makes the pooled fade dip through red. An entry cannot unset an inherited
  colour; put the colour on the entries that want it instead
  (`pool = [{ type = "wipe_left", transition_color = [255, 0, 0] }, "fade"]`).
  Documented on the special page and pinned by a test.

### The class (`src/led_ticker/transitions/fade.py`, auto-discovered)

```python
@register_transition("fade")
class Fade:
    min_frames = 8                      # 0.4 s at the default 50 ms tick

    def __init__(self, color: ColorTuple | None = None, **kwargs: Any) -> None:
        if color:                                   # falsy ([] -> ()) is the mix
            msg = rgb_shape_error(color)            # led_ticker.colors (leaf), shared with rule 74
            if msg is not None:
                raise ValueError(f"fade: transition_color: {msg}")
            self.through = (color[0], color[1], color[2])
        else:
            self.through = None

    def frame_at(self, t, canvas, outgoing, incoming, **kwargs) -> Canvas: ...
    def end_firing(self) -> None: ...   # drop the snapshots
```

`color` is an explicit parameter so `_build_trans_obj` forwards
`transition_color` into it and rule 74's `_allowed_init_kwargs` reports
`takes_single` (the same shape as `ColorFlash`). `rgb_shape_error` is imported from `led_ticker.colors`, NOT from
`led_ticker.app.coercion`: the transitions package auto-imports every
module mid-init (`transitions/__init__.py` pkgutil loop, before the
`HARD_EXCLUDED` / `META_TYPES` / `default_pool_names` re-exports), and
`app.coercion` imports widgets, which import `app`, which imports those
post-loop names from `led_ticker.transitions`; a module-level
`app.coercion` import in `fade.py` therefore breaks `import
led_ticker.plugin` and `import led_ticker.transitions` whenever either is
the first led_ticker import (every plugin test suite; verified by the cycle
3 reviewer on a copied tree). The precursor PR moves `rgb_shape_error` to
`led_ticker/colors.py` (a leaf module; no behaviour change) and
`app.coercion` re-exports it so `validate.py` and the factories are
untouched, plus a subprocess tripwire test running `sys.executable -c "import
led_ticker.plugin"` and `-c "import led_ticker.transitions"` with NO prior
import and `PYTHONPATH=src:tests/stubs` (the `tests/test_app.py:2534-2537`
pattern) so it imports the tree under test; an in-process test cannot
catch this because any earlier `led_ticker.app` import masks the cycle. Unlike `ColorFlash`, the
constructor refuses a malformed colour: `transition_color = "red"` parses
to `('r', 'e', 'd')` (`config.py:581`), which `Image.new` would reject
inside the unguarded `frame_at` (raise point three, below). A constructor
`ValueError` is caught by `run._build_trans_obj_guarded` (`app/run.py:411`)
and the slot cuts, which is the existing contract for a bad transition.

**First `frame_at` of a firing (lazy snapshot).**

1. `real = unwrap_to_real(canvas)`; two `PixelBuffer(real.width,
   real.height)`.
2. Outgoing: `Fill(*outgoing_bg_color)` when the kwarg is not `None`, else
   `Clear()`; then `outgoing.draw(wrap(buf, live geometry),
   cursor_pos=kwargs.get("outgoing_scroll_pos", 0))` (the `.get` is the
   `ColorFlash` precedent, `effects.py:56`; a kwargs-less caller must not
   `KeyError`).
3. Incoming: `Fill(*incoming_bg_color)` / `Clear()`; then
   `incoming.draw(wrap(buf, incoming geometry), cursor_pos=0)`.
4. Live geometry is `(canvas.scale, canvas.content_height)` when
   `is_scaled(canvas)`, else none (draw straight into the buffer). Incoming
   geometry is `(incoming_scale, incoming_content_height)` when
   `incoming_scale` is not `None`, else the live geometry:
   `incoming_content_height` arrives as its default 16 within a section, so
   gate on the scale exactly as the runner's `needs_switch` does.
5. `wrap` is `ticker._maybe_wrap` (already imported by the transitions
   package: wraps when `scale > 1 or content_height < buf.height`).
6. One `_snapshot(widget, bg, geometry, cursor) -> Image` helper owns the
   draw, the conversion and the failure handling, for both sides:
   - draw into the buffer; then, if the widget is a tripped guard, reset
     the buffer to bg. `_TransitionDrawGuard.draw` returns `(canvas, 0)`
     after `breaker.trip` without touching the canvas
     (`render_breaker.py:84-88`); its "the per-frame reset wipes any partial
     frame" premise holds for redraw-per-frame transitions, not for a
     snapshot taken once, so a widget that painted some pixels and then
     raised would otherwise be blended for the whole firing. The check goes
     through a new public `render_breaker.transition_draw_tripped(obj) ->
     bool` (precursor PR; true when `obj` is a guard whose widget is
     disabled), not through the guard's private `__slots__`, so a reshaped
     guard cannot turn the reset into a silent no-op. One tripwire.
   - convert the buffer to a Pillow `RGB` image the size of the real panel
     (`None` slot -> black) with ONE `Image.frombytes("RGB", size,
     b"".join(...))` over the buffer's rows, not a per-pixel `putpixel`.
   - the conversion runs INSIDE the same try/except as the widget draw:
     `PixelBuffer.SetPixel` / `SubFill` store whatever tuple a widget
     passes (`(255.0, 0, 0)`, `(256, 0, 0)`), so a value the real
     `SetPixel` would have rejected inside the guard (tripping the widget)
     surfaces here as a `TypeError` / `ValueError` from `bytes`. On failure:
     trip the widget through the guard when it has a breaker (a
     `render_breaker.trip_transition_draw(obj, exc)` sibling of the
     predicate above), log, and return a bg-filled image; with no breaker
     (`breaker=None`, tests) re-raise. No in-tree widget emits such values
     (core coercion and every provider produce ints), so this is defence in
     depth, but `HeadlessCanvas` stores floats too and no other test would
     notice.
7. When `self.through` is set, the through image is cached PER INSTANCE
   keyed on `(width, height)` (`Image.new("RGB", size, self.through)`; the
   constructor already guaranteed the shape; the panel size changes only in
   tests). It is not dropped by `end_firing`.
8. Log at DEBUG: `fade: snapshot WxH in N.N ms` so the hardware check reads
   Pi timings from the DEBUG log (memory
   `project_bigsign_hardware_check_procedure.md`).

Cache key: hold the `outgoing` and `incoming` objects the runner passed
(the draw guards in production) and compare with `is`; bare `id()` values
are recycled after GC. This is belt and braces; the primary release is
`end_firing`.

**Every frame.**

- `k = min(1.0, max(0.0, t))`. Plugin easings share `EASING` and may
  overshoot; `Image.blend` extrapolates outside [0, 1].
- Mix: `img = Image.blend(out_img, in_img, k)`.
- Dip: `k < 0.5` -> `Image.blend(out_img, through_img, 2 * k)`; else
  `Image.blend(through_img, in_img, 2 * k - 1)`.
- `unwrap_to_real(canvas).SetImage(img, 0, 0)`; return `canvas`.
- **The fade's own code must never raise.** `frame_at` is unguarded
  (`transitions/__init__.py:444`); only the widget draws sit behind the
  breaker, and nothing between the runner and `asyncio.run` catches a
  generic exception, so a raise here exits the display process. The
  raise points: the rgbmatrix fork's `SetImage` raises on
  `image.mode != "RGB"` (`bindings/python/rgbmatrix/core.pyx`);
  `Image.blend` raises on a size mismatch; `Image.new` raises on a
  malformed through colour (closed in the constructor); the
  `PixelBuffer` -> bytes conversion raises on a widget-sourced non-int or
  out-of-range channel (closed in `_snapshot`). Invariant: every image the fade
  holds is mode `RGB` and exactly `(real.width, real.height)`; the spy-canvas
  tripwire asserts both on every frame (`HeadlessCanvas.SetImage` and
  `PreviewTee.SetImage` accept RGBA, so no other test would notice).
- Every real pixel is written, so the runner's per-frame `Fill` / `Clear`
  and its bg cut-over at `scale_switch_at` are overwritten and harmless.
  The fade declares no `scale_switch_at`: the default 0.5 only decides
  which wrapper the runner returns, which must be the incoming one anyway.
- The blend is linear in the 8-bit domain. No gamma: the rgbmatrix fork
  maps every value through the inverse CIE 1931 L* table at `SetPixel`
  time with brightness folded in (gate section 2, `lib/framebuffer.cc`
  at `84ce821`), so an 8-bit ramp is already lightness-linear.

**`end_firing`.** Drop both snapshot images and the held references (the
through image stays cached, above). The runner calls it in its `finally` for every transition; the
meta wrapper forwards it after the precursor (below).

**Guarded widgets.** A tripped widget's guard draws nothing, so the fade
runs from or to the bg colour (or black), as every transition does.

**Frozen for the firing.** Inline animated image emoji hold for at most
`duration`; that is the only thing the fade newly freezes. Gifs are already
frozen in every transition: `GifPlayer.draw` paints `_current_frame_idx`
and never advances it (`widgets/gif.py:228-249`; the index moves only in
`play()`), and frame-aware widgets are paused by the runner. Recorded, not
solved (gate section 6).

**Image-widget text overlays are not in the snapshot (known limit, my
call).** `GifPlayer.draw` (`widgets/gif.py:228-249`) and `StillImage.draw`
(`widgets/still.py:214-230`) call `_paint_full(real)` only: no text
overlay, no `border`, no `background`; the overlay lives in `play()`
because the compositing path has no scroll state. Every transition shares
this today: a `gif` / `image` widget's `text` / `bottom_text`, border ring
and background hard-cut at the transition's endpoints while the image
moves. The fade inherits it unchanged. Teaching the image widgets'
`draw()` to paint even the static overlay touches `_image_base`'s overlay
surface and its field-parity tripwires, a different PR with a much larger
review surface, so it is NOT in this item: documented as a known limit on
the special page, filed as a follow-up, and hardware pair (c) uses a
text-free, border-free, background-free gif so the check is not reading a
pre-existing artefact as a fade defect.

### Breaker helpers (`src/led_ticker/render_breaker.py`, precursor PR)

`transition_draw_tripped(obj) -> bool` and `trip_transition_draw(obj, exc)
-> bool` (returns whether a breaker was there to trip): module functions
that recognise a `_TransitionDrawGuard` and act on its breaker, so a
snapshotting transition never reads the guard's `__slots__`. Both gate on
`isinstance(obj, _TransitionDrawGuard)` FIRST and return `False` for
anything else (no try/except unwrap: `object.__getattribute__` raises
`AttributeError` on a raw widget, which would replace the widget's own
error in `_snapshot`'s except; no core or plugin widget has a `_widget`
attribute), then unwrap (`widget = object.__getattribute__(obj,
"_widget")`) and call
`breaker.trip(widget, exc)` / `breaker.is_disabled(widget)` on the INNER
widget, exactly as `_TransitionDrawGuard.draw` does: `_key`
(`render_breaker.py:19-31`) falls back to `id()` for content-less widgets
(`clock`: no `text` / `top_text` / `path`), and guards are fresh per
`run_transition`, so tripping the guard object would disable a key no one
ever checks again (`Ticker._safe_draw` never sees it, the ERROR log and a
`_TransitionDrawGuard` row in `disabled_widgets` repeat every firing, and
`transition_draw_tripped` reads `False` so the bg reset never fires). A raw
widget or a guard with no disabled widget reads `False`. Tests use an
ID-KEYED fixture (no `text` / `top_text` / `path`; a text-bearing fixture
passes either way because `_key` delegates `.text` through the guard):
after `trip_...`, `breaker.is_disabled(widget)` is true for the inner
widget, `transition_draw_tripped(guard)` is true, and the status-board
entry's type is the widget class; a raw widget reads `False`.

### `PixelBuffer` surface (`src/led_ticker/rotate.py`, precursor PR)

Add `Clear()`, `Fill(r, g, b)` and `SetImage(image, offset_x=0,
offset_y=0)`, matching flair's `_raster.Raster` and `HeadlessCanvas`:
`SetImage` has two paths: a full-size `RGB` image at offset (0, 0)
replaces the pixel list from `image.tobytes()` sliced into 3-byte tuples
(NOT `getdata()`: deprecated in the locked Pillow 13.0.0, removed in 14;
`PreviewTee.SetImage` at `preview.py:149-156` uses `tobytes()` too) and
sets the extent to the full buffer (the shape `PreviewTee.SetImage`
fast-paths; this is the
`gif` / `image` snapshot case at 256x64, otherwise 16,384 Python `SetPixel`
calls land inside frame 1); anything else walks the image and calls
`SetPixel` per pixel (alpha 0 -> black; bounds and the lit extent stay
consistent). `Fill` sets every slot and the extent to the full buffer; `Clear()` is the existing `clear()`
(keep `clear()` for `rotate_blit` and the lens; `Clear` aliases it). The
class stays INTERNAL (not in `led_ticker.plugin.__all__`). Why the full
surface and not just what the fade calls: the item 3 handoff listed
`SetImage`, `Clear`, `Fill`; a target missing any method a widget paints
through makes the draw guard trip a healthy widget. Tripwire: a test that
draws every core widget type (`clock`, `countdown`, `countup`, `gif`,
`image`, `message`, `two_row`) into a `PixelBuffer` through
`guard_for_transition(widget, breaker)` at scale 1 and 4, covering the
paths that reach `unwrap_to_real(...).SetPixel`, `SetImage` and `SubFill`
(hires font, hires emoji, `border`, a plugin-free `bg_color`; the only core
`SetImage` callers are `gif.py:198` and `still.py:199`, both full-size RGB
at the origin, so the slow path has NO core caller and gets its own direct
unit test: offset, partial clip, RGBA alpha-0 -> black, extent, each
against `HeadlessCanvas.get_pixel`), and asserts (a) the breaker never trips and (b) the `PixelBuffer`'s
pixels equal a `HeadlessCanvas` of the same size wrapped the same way and
drawn by the same widget, read via `get_pixel` (`None` slot -> black), per
widget type and scale. Time is frozen in the fixture (`clock` reads
`datetime.now(tz)` at draw time, `widgets/clock.py:140`; `countdown` /
`countup` likewise) so the two draws cannot straddle a boundary. "Never
trips" alone would let a stride or mode bug
in the `SetImage` fast path (hit ONLY by the gif / image path, `gif.py:198`,
`still.py:199`) ship green and garble every image section's fade on the
sign. The cycle 4 reviewer probed this shape: zero pixel diffs across
256x64 scale 4 (hires font, `:star:`, border, cursor 0 and -30), 128x64
scale 2, 256x64 scale 1 / content_height 16, 160x16, `two_row`,
`GifPlayer` and `StillImage` with a `tobytes()`-based fast path. First-party plugin
widgets paint through the same primitives into flair's `Raster` today, so
"not a blocker" holds, with the evidence: scoped to `plugins/*/src`, plugin
`draw()` paths touch only `real.{width,height,SetPixel,SubFill,Fill,Clear}`
and wrapper attrs `{width,height,SetPixel,SubFill,Fill,scale,
content_height,y_offset_real}` (with `getattr` defaults where a raw canvas
is possible); zero uses of `canvas.real`, `rebind_innermost`,
`draw_bdf_text` or `graphics.Draw*` (cycle 1 tally, 2026-11-22). Flair's
`_raster.Raster` + `snapshot_into` (`flair/_raster.py:15-94`) has exactly
the surface the precursor gives `PixelBuffer` and already receives every
widget's `draw()` on moonbunny through the halal-cart `random` pool of
laser / accordion / sand. Residual risk: `fade` is default-pool while
`Raster` is opt-in, and a miss is a trip (widget disabled until reload),
not a freeze. The plugins-repo mirror test is filed as a tracked issue
BEFORE the feature PR merges, not "later".

### Runner (`transitions/__init__.py::run_transition`, precursor PR)

Pass `incoming_scale=incoming_scale`,
`incoming_content_height=incoming_content_height` and
`outgoing_bg_color=outgoing_bg_color` to `frame_at` beside the existing
`outgoing_scroll_pos`, `duration_ms`, `incoming_bg_color`. Document the
three on the `Transition` protocol docstring. Safe for every receiver: 53 of
53 `frame_at` definitions across core and the plugins repo take `**kwargs`,
`render_hires_frame` takes `**kwargs`, the meta wrapper forwards
`**kwargs` (gate section 6). `API_VERSION` -> the next unclaimed minor, `(1, 5)` while PR #561 (`fix/image-play-settle-seam`, claims `(1, 5)` for `frames_to_rest` on gif/image hosts) is open; re-check `git branch -r` and open PRs at precursor-merge time, since a reused minor would satisfy a plugin's `>=` probe for a guarantee the core does not have ("`frame_at`
receives the incoming geometry and the outgoing bg colour"); tests pin
`>=`. `tests/test_docs_plugin_api_drift.py:143-158` checks the "currently
`(1, 3)`" literal on TWO pages, `plugins/api-reference.mdx` and
`plugins/authoring/01-scaffold.mdx`; both move to `(1, 5)` and the
api-reference page gains the row. One new test: the three kwargs
reach `frame_at` with the values the runner was given, including
`incoming_scale=None` from a within-section call. Existing runner tests
pass unchanged.

### Meta wrapper (`transitions/meta.py`, precursor PR)

`_PickAhead.end_firing` fires the hook on the child that RAN, then picks:

```python
def end_firing(self) -> None:
    child = self._children[self._current]      # the child that just ran
    try:
        hook = getattr(child, "end_firing", None)
        if callable(hook):
            hook()
    finally:
        self._current = self._advance()
        self._log_pick()
```

`_current` names the child that ran only BEFORE `_advance()`
(`meta.py:132-136`); the `finally` means a raising child can never skip
the pick (the runner already logs and swallows the exception). Pinned:
"hook fires on the child that ran, not the newly picked one". Tests run WITHOUT a breaker, where the guards ARE
the widgets and an A-B-A firing sequence would otherwise reuse a cache key:
a pooled child with a counting `end_firing` runs exactly once per firing;
`auto` still cycles in order; a raising child still advances the pick. No
core or plugin child defines the hook today (grepped both repos), so no
existing pool changes behaviour.

### Factory and validate

No factory change: `_build_trans_obj` forwards `transition_color` as
`color=` to every core class whenever no `transition_colors` list is set
(`factories.py:461-464`: `colors` wins and `color` is then dropped), so
`Fade` only has to name the parameter. Consequence: a plain `fade` slot
carrying BOTH keys renders a MIX (rule 74 already warns "forwarded instead
and then ignored"); in a pool the inherited list is dropped for a core
child and the parent's `color` reaches it (`factories.py:626-631`), so the
pool-dip claim holds. The pool-colour test adds the both-keys slot case. No new validate
rule: rule 74 already grades the colour shape per slot. One wording
caveat: rule 74's empty-colour message says the core type "falls back to
its default colour" (`validate.py:1649,1663`); for `fade` an empty
`transition_color = []` (parsed to `()`, forwarded as a falsy `color`)
selects the MIX, a different effect, so the `fade` docs must not borrow
the `color_flash` phrasing, and the builder may special-case the message
for `fade` if it reads wrong (builder's call). Rule 73's default
pool grows to 16 through `default_pool_names()`. Pins that move with it:
`FIFTEEN` in `tests/test_transitions_meta.py` and
`tests/test_factories_meta_transition.py` (the latter also hardcodes
`[None] * 15` at `:81` and `range(15)` at `:89`),
`tests/test_transitions.py:106`'s registry count (23 -> 24), and
CLAUDE.md's "(15 today)". Release note: existing `random` / `auto` configs
gain a member and `auto`'s cycle order shifts (`fade` sorts after
`dissolve`); a slot that already carries `transition_color` (written for
its wipes) makes the new member a DIP through that colour, not a mix
(inheritance via `_child_transition_cfg`); documented `exclude` examples
such as `special.mdx:50`'s `exclude = ["color_flash", "dissolve"]` now
yield a pool with `fade` in it. No
committed demo GIF uses a pool (checked 2026-11-21).

### Docs

- `transitions/special.mdx`: frontmatter description and intro add `fade`;
  a section with `transitions-fade.gif`, both forms, the pool-colour
  inheritance line, and a tuning note from the hardware check (bigsign
  `pwm_bits` 9 or 10 if the tail shows; refresh cost as measured). The
  `TomlExample` beside the `DemoGif` is copied character-for-character from
  `docs/site/demos/transitions-fade.toml` (`docs/DOCS-STYLE.md:107`, hard
  rule) and bound by a drift tripwire on the flair pattern
  (`tests/test_docs_flair_transitions_demo_drift.py`), scoped to
  `transitions-fade`.
- `docs/content-source/transitions/special.md` (the fact pack behind
  `special.mdx`'s `<OptionsTable source="transitions/special" />`): a
  `fade` row in the Variants table, `fade` in the Tuning bullets for
  `transition_color`, and `fade`'s `min_frames` floor on the
  `transition_duration` bullet ("0.4 s floor at 20 fps; below it, raise
  `transition_fps`", the `wipe.md` pattern: a pool entry `{ type = "fade",
  duration = 0.2 }` runs 0.4 s). New tripwire: every registered core name minus `META_TYPES` appears
  as the FIRST-COLUMN cell of exactly one pipe-table row (`^\| \`name\` `)
  across the four `content-source/transitions/*.md` files; prose mentions
  do not count (`cut` appears 4x and `scroll` 6x as prose on main; the
  first-column count is exactly 1 for all 21 names today). `split` stays
  in `special.md`.
- `transitions/index.mdx`: the Special catalogue row ("Cut, fade,
  dissolve, …"); the `transition_color` bullet adds "the colour `fade`
  dips through"; the "Which to use" table (`index.mdx:23-27`) gains `fade`
  in the same rows as its skill mirror below, so site and skill agree.
- `reference/config-options.mdx`: no new field; the `transition_color`
  description mentions `fade`.
- `tutorial/05-polish.mdx:139` ("**Special** — `cut`, `color_flash`,
  `dissolve`, `split`, `scroll`") and the creating-a-config skill's
  `.claude/skills/creating-a-config/references/transition-selection.md:18`
  gain `fade` (neither has a drift test; `fade` goes under the skill's
  branded-pro / info-dense rows as the crossfade).
- Plugin API reference (`plugins/api-reference.mdx:42`, a prose sentence,
  plus the `frame_at` kwargs); `docs/plugin-system.md:233-237`'s
  one-bullet-per-minor list; the `src/led_ticker/plugin.py:192-199` comment
  block. All precursor PR.
- CLAUDE.md: file map `fade.py`; the Special list; "(15 today)" -> 16; the
  three kwargs and the meta forward under the Meta bullet; `(1, 5)` in the
  Plugin invariants `API_VERSION` sentence; hardware constraint #2 ("Never
  call `widget.draw()` on anything other than a real canvas or the test
  stub canvas") and "Adding a New Transition" step 6 gain the carve-out for
  an OWNED readable raster (`PixelBuffer`, flair's `Raster`) pointing at the
  snapshot-every-widget tripwire, so a reviewer following them does not
  refuse the snapshot; precursor PR for the constraint, feature PR for the
  step.
- Demo: `docs/site/demos/transitions-fade.toml` with its
  `# render-duration:` = `make plan-gif`'s number + the sum of the entry
  transition `duration`s + 1 s (`tools/gif_plan/plan.py::total_ms` sums
  hold and scroll only, no transition term; every committed transitions
  demo hand-pads the same way, e.g. color_flash 14 vs plan 10); making-a-gif
  skill, sample by playback time, never frame index: a mix pair, a
  dip-through-black pair, a `bg_color` pair. The rendered GIF is committed under
  `docs/site/public/demos/`.

### Tests (feature PR, `tests/test_transitions_fade.py`)

- Endpoints on a `HeadlessCanvas` read via `get_pixel`: t = 0 equals the
  outgoing drawn INDEPENDENTLY at a non-zero `outgoing_scroll_pos` (so
  `cursor_pos=0` fails it); t = 1 equals the incoming; a mid frame equals
  `Image.blend` of the two. Parametrised over a `message` pair AND a
  `gif` -> `message` pair (the gif side exercises the `SetImage` fast
  path end to end).
- Dip through BLACK (`color=(0, 0, 0)`, the headline case; written so a
  falsy-colour shortcut would fail it): t = 0.5 is black everywhere while
  both snapshots are lit; a second case with a non-black colour.
  `color=None` never paints a solid frame.
- Clamp: t = 1.2 and t = -0.1 (programmatic) equal the endpoints.
- bg: two DISTINCT colours; an unlit pixel at t = 0 equals
  `outgoing_bg_color`, at t = 1 equals `incoming_bg_color` (an
  implementation that fills both buffers with the incoming bg passes a
  same-colour test); `None` -> black.
- Ramp shape: mix t = 0.25 equals `blend(out, in, 0.25)`; dip t = 0.25
  equals `blend(out, through, 0.5)` and t = 0.75 equals
  `blend(through, in, 0.5)` (a first half using `k` instead of `2k` passes
  every endpoint and midpoint test yet snaps to the through colour at the
  midpoint, exactly the pop the hardware check is looking for).
- Geometry: a 4 -> 2 cross-scale entry and a same-scale
  cross-`content_height` entry snapshot incoming at the incoming geometry
  (pixel positions equal `_maybe_wrap(..., incoming_scale,
  incoming_content_height)` + `draw`) AND outgoing at the LIVE geometry (t =
  0 pixels equal a scale-4 draw, so wrapping both buffers at the incoming
  geometry fails); `incoming_scale=None` uses the live wrapper.
- Lazy snapshot and release: `draw` runs once per widget per firing
  whatever the frame count; after `end_firing` the next firing re-snapshots
  (changed text shows); A-B-A through a TWO-member `random` pool (`fade` + one
  other, `rng=random.Random(seed)` so the pick sequence is known and `fade`
  runs on firings 1 and 3) with `breaker=None`, widget A's text changed
  between firings, re-snapshots (exercises the meta forward end to end; an
  unpinned rng or a larger pool makes this test vacuous).
- Breaker: an incoming whose draw PAINTS pixels and then raises trips, and
  the fade completes to bg / black with none of the partial paint (a fixture
  that raises before painting cannot catch a missing reset); a widget that
  writes `(255.0, 0, 0)` trips at conversion and the fade completes; with
  `breaker=None` the same widget raises out of `frame_at`.
- Constructor: `color=('r','e','d')` raises `ValueError`; `color=()` and
  `color=None` build a mix; a malformed `transition_color = "red"` on a
  `fade` section cuts through `run._build_trans_obj_guarded`.
- Validate / runtime parity: one parametrised test over a shape table
  (`"red"`, `[255, 0]`, `[255.0, 0, 0]`, `[256, 0, 0]`, `[True, 0, 0]`,
  `[]`, `[0, 0, 0]`) asserting `Fade(color=shape)` raises iff rule 74
  reports that shape as an ERROR on a `fade` slot. Validate never
  constructs a core non-meta slot (rule 53 skips bare names), so this test
  is the only thing that keeps the two in step if the constructor is ever
  loosened.
- Pool: `default_pool_names()` includes `fade`; the sixteen pins; `auto`
  order.
- Per-frame path tripwire on a SPY canvas (not `HeadlessCanvas`, whose
  `SetImage` is per-pixel `SetPixel`): exactly one `SetImage` on the real
  canvas and no direct `SetPixel` per frame (keeps the Pi cost at one C
  call per frame), and the image passed is mode `RGB` with size
  `(real.width, real.height)` on every frame.
- Pool colour inheritance: `{ type = "random", transition_color = ... }`
  builds a dipping fade; a bare pool entry inherits it; an entry with its
  own colour keeps it.
- Mutation check before each commit (item 2 process).

## Hardware check (go given 2026-11-21; runs on the feature branch)

Procedure: memory `project_bigsign_hardware_check_procedure.md` (branch
deploy, `compose.override.yaml` DEBUG, in-container preview capture,
restore). The window is re-asked if the check lands on a work day. Each
test config names its variant IN the message text ("mix 0.5 linear",
"dip 1.0 ease_in_out") so capture frames and eyes agree.

What the preview capture can prove (it records the 8-bit values written,
BEFORE the L* table and the `pwm_bits` truncation, throttled to one frame
per `CAPTURE_INTERVAL = 0.2` s, `preview.py:33`, so a 0.5 s fade yields 2
or 3 frames): intermediate blend levels exist on the panel path; the
cross-scale pair lands at the incoming geometry (no vertical snap when the
section starts); no stale snapshot across pooled firings; the busy dot
still composited; snapshot and per-firing timing from two DEBUG lines
(`fade: snapshot WxH in N.N ms` and `fade: firing done, N frames, M.M ms`).
Frame count per firing and "no one-tick bg flash" are proven by the
spy-canvas unit tripwire, not by the capture.

What needs James watching the panel: the tail (does the incoming pop in or
ramp in, does the outgoing drop or ramp out) at `pwm_bits = 8`, then 9 and
10 with `show_refresh_rate = true` for the refresh cost; the midpoint (soft
blend vs mush) for the mix; whether the dip reads better than the mix on
the 73-level ramp.

Pairs (gate section 10): (a) `message` -> `message`, plain colours; (b) a
bordered `message` on a `bg_color` section -> a different `bg_color`; (c)
`gif` (phoenix; no text overlay, no border, no background) -> `message`; (d) a scale-4 section -> a scale-2 section.
Each as mix and dip-black, `duration` 0.5 and 1.0, `easing` linear and
`ease_in_out`. Smallsign (scale 1, `pwm_bits` 11): (a) and (b). Findings go
in the "Hardware findings" section below and the docs tuning note; the
check tunes `min_frames` and the docs recommendation, it does not gate the
design.

## Hardware findings

(pending)

## Process

Worktree `fade-transition`. Two branches, two PRs, both opened as drafts;
`gh pr create` and every merge need James's fresh go. The precursor branch
is off `origin/main`; the FEATURE branch is STACKED on the precursor
branch (it cannot import without `PixelBuffer.SetImage`, the runner kwargs
and the breaker helpers) and is rebased onto `origin/main` after the
precursor merges. The hardware check deploys the FEATURE branch (pushed,
stacked), per the procedure's `git checkout -B <branch> origin/<branch>`.

1. **Precursor PR** (behaviour-free for every existing config): the
   `PixelBuffer` surface and its snapshot-every-widget tripwire; the two
   breaker helpers; `rgb_shape_error` relocated to `led_ticker.colors`
   with the `app.coercion` re-export and the two subprocess import
   tripwires; the three runner kwargs, the protocol docstring,
   `API_VERSION (1, 5)`, BOTH docs-page literals (`plugins/api-reference.mdx`,
   `plugins/authoring/01-scaffold.mdx`) and the api-reference row; the
   CLAUDE.md edits that describe precursor behaviour (constraint #2
   carve-out, the `(1, 5)` `API_VERSION` sentence, the Meta bullet's three
   kwargs and `end_firing` forward); the two stale `rgb_shape_error`
   docstrings (`validate.py:1553` and the function's own) renamed to the
   new home; the meta `end_firing` forward and its tests.
2. **Feature PR**: `fade.py`, the sixteen pins, docs, the demo GIF, the
   remaining CLAUDE.md edits (file map, Special list, "(15 today)" -> 16,
   step 6 carve-out).

TDD; mutation check before each commit; the 5-cap antagonist loop per PR
(fresh reviewer and fresh ledger under `docs/superpowers/reviews/`, exit on
LOW / DOCS only, cycle 5 with MEDIUM+ stops and asks); the hardware check
between the feature PR's loop and ready-and-ask. No core release is needed
before the feature PR (nothing depends on `(1, 5)` yet; `(1, 3)` is
`api.font(threshold=)`, shipped in core v4.35.0 and consumed by flair
0.25.0; `(1, 4)` is PR #561's); the next core release carries both. This design doc is committed on the feature branch,
like item 2's.

## Builder-check decisions (2026-11-21)

A fresh reviewer read the draft as the builder. One question changed the
document, settled as my call and flagged for James: image-widget text
overlays are absent from `draw()` snapshots (see "Image-widget text
overlays" above), accept-and-document rather than widen the item. The
reviewer also found pins the draft had not listed (the registry count in
`tests/test_transitions.py:106`, `range(15)` in
`tests/test_factories_meta_transition.py:89`, the second API-version literal
on `plugins/authoring/01-scaffold.mdx`) and a rule 74 wording caveat for
an empty colour on `fade`; all folded in above. Verified against the code:
the runner takes but does not forward the three kwargs; `end_firing` is
swallowed in `finally`; the meta wrapper does not forward it; every core
`frame_at` and every test double take `**kwargs`; the test stub canvas is
`HeadlessCanvas` and `PreviewTee.SetImage` mirrors into the capture shadow,
so the demo GIF and the in-container capture both see fade frames.

## Left to the builder

- Where the `PixelBuffer` -> Pillow conversion lives (a private helper in
  `fade.py` vs a `PixelBuffer.to_image()`); keep `rotate.py` free of a
  Pillow import unless it already has one.
- DEBUG log wording; test names; the demo TOML composition within the
  making-a-gif skill's constraints.
