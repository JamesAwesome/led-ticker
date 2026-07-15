# Colored value tokens (source-declared) — design spec

**Date:** 2026-07-15
**Status:** approved (brainstorm) — pending user review before planning
**Repo:** `led-ticker` core, worktree `led-ticker--colored-tokens`, branch `feat/colored-value-tokens`
**Builds on:** inline value tokens (`[[source]]` / `:id:`), the `stocks.trend` color provider (a use case), and the measure-at-lock scroll fix (#389 — width/scroll geometry stays token-length-driven).

---

## 1. Summary

Let a `:id:` value token render in its **own color** while the surrounding literal text keeps the
widget's `font_color`. The color is declared **on the source**:

```toml
[[source]]
id = "stocks.aapl"
type = "stocks.quote"
symbol = "AAPL"
color = {style = "stocks.trend", symbol = "AAPL"}   # any color provider

# then, in ONE message line:
text = "AAPL :stocks.aapl:"
font_color = [80, 140, 255]     # "AAPL " blue, the token trend-colored
```

**Phase 1 = `TickerMessage` only.** two_row and image/gif text overlays are Phase 2 (deferred,
on the board — the shared segment infra is built to extend there).

## 2. Design decisions (brainstorm)

| Decision | Choice |
|---|---|
| Where the color is declared | **On the `[[source]]`** (`color = <provider>`) — define-once; global to the token |
| Scope (widgets) | **Phase 1 = message only**; two_row + image deferred to Phase 2 |
| Rendering | Per-character color override composed with the host `font_color` (literal chars keep host color, token chars use the token color) |
| Backward compat | A source without `color` behaves EXACTLY as today; existing configs byte-identical |

## 3. Core infra

### 3.1 `DataSource.color`
`DataSource` (sources.py) gains `color: ColorProvider | None = None` (settable; default None). It's
presentation metadata attached to the source, read by the token renderer. Sync sources
(clock/date/static) and polled/plugin sources all inherit it.

### 3.2 `build_source` (factories.py)
- Add `"color"` to the polled-source `_RESERVED` set so a `[[source]] color = …` is NOT passed
  to a plugin source's `__init__` (the plugin never sees a `color` kwarg).
- After constructing the source (ALL branches — clock/date/static/polled/fallback), if
  `cfg.raw` has `color`, coerce it via `_coerce_color_provider(cfg.raw["color"], "source color")`
  and set `source.color`. One place, all types.
- Coercion runs at build time (plugins already loaded), so a plugin provider like `stocks.trend`
  resolves. A bad provider table raises at config-load with the coercion's existing diagnostics.

### 3.3 `validate.py`
The static validator must accept `color` as a valid `[[source]]` field (it currently may flag
unknown source keys). Add it to the recognized source-field set; optionally dry-run the coercion
so a bad `color` provider is caught in `led-ticker validate` too.

### 3.4 `TokenizedField` segment resolution (sources.py)
The existing flat-string `resolve(registry) -> (str, bool)` is UNTOUCHED — it still drives width,
scroll geometry, and every current caller (byte-identical). Add a parallel:

```
resolve_segments(registry) -> list[Segment]
```

where `Segment` = `(text: str, color: ColorProvider | None)`. It walks the same raw template,
emits literal runs with `color=None` and token runs with `color = registry.get(id).color`
(None when the source has no `color`, or the token is an emoji slug / unknown id — those stay
literal). The concatenation of segment texts EQUALS `resolve()`'s flat string (invariant, tested).

## 4. Rendering (TickerMessage)

**Geometry unchanged.** Width/scroll still come from the flat `resolve()` string; colors never
affect layout (pairs with the measure-at-lock fix).

**Per-character color override.** On draw, when `resolve_segments` yields at least one colored
token span, the widget builds a per-visible-character override and threads it through the two
existing color paths:

- **Per-char path** (`draw_text_per_char`, used for per-char providers): wrap the host `color_fn`
  — `lambda idx, total: override[idx] if override[idx] is not None else host.color_for(frame, idx, total)`.
- **Whole-string path** (constant host color): a colored token forces this through the per-char
  path with the same wrapped `color_fn` (constant host color returned for literal chars).
- **Emoji path** (`draw_with_emoji`): add an optional `color_override: Callable[[int], Color | None] = None`
  parameter, consumed at `draw_with_emoji`'s existing per-text-char coloring site (it already
  tracks a running visible-text-char index). Literal emoji sprites are unaffected; token letters
  get their override color. Default None ⇒ byte-identical for every existing caller.

**Token color value.** The token's provider is whole-string (`stocks.trend` is `per_char=False`),
so its span color for a draw is `span.color.color_for(frame, 0, 1)`, applied to every char of the
span. `frame` is the widget's `font_color` frame counter (so a frame-variant token color animates).

**INDEX ALIGNMENT (the sharp edge — call out for the plan).** `draw_with_emoji` and
`draw_text_per_char` index by VISIBLE text character (emoji slugs excluded, per-char provider
space). The override array MUST be built in that SAME space — i.e. walk the resolved text the way
the renderer counts chars (skip `:emoji:` slug substrings), mapping each token span's characters to
their visible-char indices. Tripwire: a message mixing a colored token AND an inline emoji must
color the token correctly and leave the emoji sprite untouched.

**Fast path.** A plain message is redrawn every engine tick by `_swap_and_scroll`'s held/scroll
branches (constraint #12), so a frame-variant token color animates with no gate change. (The
`frame_invariant` fast-path gate only matters for the Phase-2 image/gif `play()` widgets.)

## 5. Backward compatibility

- No source has `color` ⇒ `resolve_segments` yields a single literal span ⇒ the widget takes its
  existing path unchanged. Byte-identical rendering; zero overhead on the common path.
- `draw_with_emoji`'s new param defaults None ⇒ all current callers (two_row, image, message
  without colored tokens) unchanged.
- Width/scroll geometry is untouched.

## 6. Testing

- **Segment resolution:** `resolve_segments` splits literal/token spans; token span carries the
  source's `color`; a source without `color` ⇒ `None`; the segment-text concatenation equals
  `resolve()`; an emoji slug in the template stays literal (not a token span).
- **build_source / validate:** `color` coerced + set on the source; excluded from plugin kwargs;
  `validate` accepts `color` and rejects a bad provider table.
- **Rendering (headless, pixel-level via the stub):** a message with a colored token paints the
  token's characters in the token color and the literal characters in the host color; the
  emoji-path override colors the token but not the emoji sprite; no colored token ⇒ byte-identical
  to a captured baseline; width/scroll unchanged (assert the returned `cursor_pos` matches the
  no-color case).
- **Visual GIF gate (required):** `text = "AAPL :stocks.aapl:"`, `font_color = [80,140,255]`,
  source `color = {style="stocks.trend", symbol="AAPL"}` — render (demo) and confirm ONE scrolling
  line with "AAPL " in blue and the price segment green/red by trend.

## 7. Out of scope (Phase 2, deferred — on the board)

- Colored tokens in **two_row** (per-row) and **image/gif text overlay** (`_image_base`). The
  segment infra + the `draw_with_emoji` override param are built shared so Phase 2 wires them
  through those widgets' draw paths.
- Per-token color at the widget use-site (this spec is source-declared only).
- General colored text spans / markup (only `:id:` value tokens get a color).

## 8. Phasing (for the plan)

1. **Core infra** — `DataSource.color` + `build_source` coercion/exclusion + `validate` field +
   `TokenizedField.resolve_segments` + the `draw_with_emoji` `color_override` param. Unit-tested;
   no widget behavior change yet (segments + override plumbing, byte-identical default).
2. **TickerMessage rendering** — build the per-visible-char override from segments, thread it
   through the per-char + whole-string + emoji paths; index-alignment tripwire; no-color
   byte-identical regression; width/scroll-unchanged assertion.
3. **Docs + example** — value-tokens docs page gains a "Token color" section; an example config;
   note two_row/image as Phase 2.
