# Decision Rules

These rules are the validation checklist. The skill consults this file at every validation checkpoint (per-section lint, Phase 3 final, refine-mode flag-and-ask).

Last synced: 2026-05-07

---

## Rule 1: content_height × scale ≤ panel_h_real

**SOURCE:** CLAUDE.md — "Per-section `content_height`" section (lines 105-106).

**DETECT:** `section.content_height * default_scale > panel_height`. For bigsign (default_scale=4, panel_height=64) this means `content_height > 16`.

**SYMPTOM:** Top + bottom rows of logical canvas overflow visible area; content placed near edges silently clips. BDF text may look fine; hi-res emoji and large hi-res fonts surface the clip immediately (e.g., TwoRow's hi-res `:instagram:` cuts off ~4 real px at the bottom).

**FIX:** Lower `content_height` to `panel_height // default_scale` (16 for bigsign at scale=4). For per-row breathing room use widget-level `text_y_offset` instead of raising `content_height`.

---

## Rule 2: Within-family font_threshold matching

**SOURCE:** CLAUDE.md — "Match thresholds within a font family" section (line 95).

**DETECT:** Two widgets in the same section using the same `font` family (e.g., `Inter-Regular` and `Inter-Bold`, or `Beloved Sans Regular` and `Beloved Sans Bold`) with different `font_threshold` values (or one set and one using the default 128).

**SYMPTOM:** Weight contrast inverts on the panel. Concretely: Regular at thr=80 has more lit pixels than Bold at thr=128, so Bold no longer looks bolder. Bold rendering at the 128 default while Regular uses 80 makes Regular appear fatter than Bold.

**FIX:** Pair Bold to the same `font_threshold` as Regular. If using Inter-Regular at `font_threshold = 80`, set Inter-Bold to `font_threshold = 80` as well. This is a hardware-validated finding — the weight contrast survives only when thresholds match within the family.

---

## Rule 3: text_align="scroll" + fit="stretch" is invalid

**SOURCE:** CLAUDE.md — "Footgun validation" subsection (line 120).

**DETECT:** Gif or image widget with both `text_align = "scroll"` or `text_align = "scroll_over"` AND `fit = "stretch"`.

**SYMPTOM:** No transparent regions to expose text behind. Stretch mode fills the entire canvas with image; scroll-text expects a transparent silhouette to walk "behind."

**FIX:** Change `fit` to `"pillarbox"`, `"letterbox"`, or `"crop"` (which all expose transparent regions), OR change `text_align` to `"left"`, `"right"`, `"auto"`, or `"center"` (non-scroll modes).

---

## Rule 4: Hires emoji size capped at _EMOJI_ROW_CAP

**SOURCE:** CLAUDE.md — "Two-row widget" section (line 103).

**DETECT:** A hi-res emoji (e.g., `:instagram:` 32×32) in a two-row widget when the emoji height would exceed the per-row band height.

**SYMPTOM:** Emoji auto-falls back to 8×8 low-res sprite. The hi-res variant is skipped silently.

**FIX:** No config change needed — the fallback is automatic via `_EMOJI_ROW_CAP = 8`. If you want the hi-res detail, increase `top_row_height` or `bottom_row_height` to accommodate a larger emoji, or use a smaller hi-res emoji slug.

---

## Rule 5: HiresFont configs MUST specify font_size

**SOURCE:** CLAUDE.md — "Single-row image text" section (line 115).

**DETECT:** A widget specifies `font = "<name>"` where `<name>` resolves to a HiresFont (TTF/OTF, not a BDF alias) but omits `font_size`.

**SYMPTOM:** Config load raises with a clear error message like "HiresFont `<name>` requires `font_size` to be set explicitly (e.g., `font_size = 24` on bigsign)."

**FIX:** Add `font_size = <pixels>` next to `font`. Pick a size ≤ `content_height * scale` (e.g., `font_size = 24` on bigsign at scale=4 with default `content_height = 16` gives 24 real pixels, well within the 64-pixel panel). BDF fonts (5x8, 6x12) have smart defaults and do NOT need `font_size`.

---

## Rule 6: TwoRow at scale > 2 limits handle width on bigsign

**SOURCE:** CLAUDE.md — "Two-row widget" section (line 103).

**DETECT:** TwoRowMessage in a section with `default_scale = 4` (bigsign full-height) and typical social-media handle text (e.g., "@MoonBunny").

**SYMPTOM:** Logical canvas is 128 pixels wide (256 real px / scale=4), which is OK for single handles but cramped for two-row layouts. Handles scroll instead of fitting cleanly.

**FIX:** Use `scale = 2` per-section (override via `[[sections.widgets]] scale = 2`) so the logical canvas is 256 pixels wide (256 real px / scale=2). This is idiomatic for handle layouts on bigsign.

---

## Rule 7: text_x_offset != 0 invalid with scroll modes

**SOURCE:** CLAUDE.md — "Footgun validation" subsection (line 120).

**DETECT:** Gif or image widget with `text_x_offset != 0` AND `text_align ∈ ("scroll", "scroll_over")`.

**SYMPTOM:** Undefined behavior. X-offset shifts the starting position of scrolling text; combined with scroll mode (which slides the full width), the offset creates visual confusion.

**FIX:** Use either `text_align = "left"` / `"right"` / `"auto"` / `"center"` (with `text_x_offset` for fine tuning) OR keep `text_align = "scroll"` / `"scroll_over"` (omit `text_x_offset`).

---

## Rule 8: hold_seconds < 0.05 invalid on image widgets

**SOURCE:** CLAUDE.md — "Footgun validation" subsection (line 120).

**DETECT:** Image or gif widget with `hold_seconds < 0.05` (less than 50 milliseconds).

**SYMPTOM:** Image flashes too briefly to perceive; likely a typo.

**FIX:** Raise `hold_seconds` to at least `0.05` (50ms), or use a value that makes sense for the content (e.g., `2.0` for a 2-second hold).

---

## Rule 9: BDF font_size < cell_h invalid on image widgets

**SOURCE:** CLAUDE.md — "Single-row image text" section (line 115) and "Footgun validation" subsection (line 120).

**DETECT:** Gif or image widget with a BDF font (e.g., `font = "6x12"`) and `font_size < cell_h` where `cell_h` is the BDF cell height (12 for 6×12, 8 for 5×8, etc.).

**SYMPTOM:** Config load or first-paint raises with a hint pointing to a smaller bundled BDF (5×8) or recommending a HiresFont.

**FIX:** Use a BDF with smaller `cell_h` (switch from `6x12` to `5x8`), or use a HiresFont with your desired `font_size`.

---

## Rule 10: Per-widget font_threshold must be int 0-255

**SOURCE:** CLAUDE.md — "Per-widget `font_threshold`" section (line 93).

**DETECT:** A widget specifies `font_threshold = <value>` where `<value>` is a float (e.g., `80.0`), string, or bool.

**SYMPTOM:** Config load raises with a type validation error. Only `int` 0-255 accepted (bool excluded explicitly since it's an int subclass in Python).

**FIX:** Convert to an integer: `font_threshold = 80` (not `80.0`, not `"80"`). Valid range is 0–255 (where 128 is the default, 50% intensity cutoff).

---

## Rule 11: Section transition overrides inter-widget AND inter-section transitions

**SOURCE:** CLAUDE.md — "Section transition precedence" section (line 388).

**DETECT:** A section with `transition = "<name>"` explicitly set in TOML.

**SYMPTOM:** That transition is used for BOTH (a) entry into this section from the previous one (inter-section), AND (b) between widgets within this section (inter-widget). Sections that omit `transition` fall back to `[transitions] between_sections` for entry only.

**FIX:** No fix needed — this is the intended behavior. If you set `transition = pokeball` on a single-widget section, you'll see pokeball when that section appears. If you want different transitions for entry vs. inter-widget, split the section or use `[transitions] between_sections` for global inter-widget default and let the section omit `transition`.

---

## Rule 12: animation = "typewriter" only on message widget

**SOURCE:** CLAUDE.md — "Color providers and animations" section (line 243-244).

**DETECT:** A widget of type other than `"message"` (or `"countdown"` which extends `message`) specifies `animation = "typewriter"`.

**SYMPTOM:** Config load raises with an error message: "_build_widget raises if `animation` appears on any other widget type."

**FIX:** Remove `animation = "typewriter"` from non-message widgets. Typewriter effect is only supported on TickerMessage and TickerCountdown. For other widgets (gif, image, two_row, etc.), use `font_color = "rainbow"` or other color effects instead.

---

## Rule 13: bottom_text != "" on image/gif switches to two-row mode

**SOURCE:** CLAUDE.md — "Two-row text overlay on image widgets" section (line 113).

**DETECT:** Gif or image widget with `bottom_text` set (non-empty string).

**SYMPTOM:** Widget switches to two-row text-overlay mode (image painted underneath, two text rows overlaid). Single-row params (`text_align`, `text_valign`, `text_x_offset`, `font_size`) are refused with a clear error at config load.

**FIX:** Use per-row TOML knobs instead: `top_text` (or `text` as alias), `top_align` / `bottom_align`, `top_color` / `bottom_color`, `top_font` / `bottom_font`, `top_text_y_offset` / `bottom_text_y_offset`, `top_emoji_y_offset` / `bottom_emoji_y_offset`, `top_row_height`. These parallel TwoRowMessage's contract.

---

## Rule 14: animation = "typewriter" + two-row raises at config load

**SOURCE:** CLAUDE.md — "Typewriter on image widgets" section (line 122).

**DETECT:** Gif or image widget with `animation = "typewriter"` AND any of: `bottom_text != ""`, `text_align ∈ ("scroll", "scroll_over")`, or `text == ""`.

**SYMPTOM:** Config load raises with a clear error message identifying which constraint was violated (single-row only, no scrolling, no empty text).

**FIX:** For two-row layouts, omit `animation` (typewriter is single-row only). For scrolling text, omit `animation`. For empty text, add non-empty `text = "..."` or omit `animation`.

---

## Rule 15: border field restricted to specific widget types

**SOURCE:** CLAUDE.md — "Rainbow border" section (line 313-315).

**DETECT:** A widget of type NOT in (`"message"`, `"countdown"`, `"two_row"`, `"gif"`, `"image"`) specifies a `border` field.

**SYMPTOM:** Config load raises with a loud failure message: "Border is restricted to message, countdown, two_row, gif, and image widget types."

**FIX:** Remove the `border` field from data widgets (weather, rss_feed, mlb, mlb_standings, crypto widgets). Border paints an animated ring around the panel perimeter — meaningful only for presentation widgets, not data displays. Assign `border` only to message, countdown, two_row, gif, or image widgets.

---

## Rule 16: Hi-res text fonts must fit per-row band height

**SOURCE:** CLAUDE.md — "Two-row widget" section (line 103).

**DETECT:** TwoRowMessage with a per-row HiresFont where `font_line_height > canvas.height // 2` (i.e., the font is taller than its half of the logical canvas).

**SYMPTOM:** Draw time raises with a clear message identifying which row (top or bottom) and the constraint.

**FIX:** Lower `font_size` for that row, or increase the canvas height (or per-row height via `top_row_height`). On bigsign with `default_scale = 4` and default `content_height = 16`, each row gets 8 logical pixels (32 real px). A 24px HiresFont needs 48 real pixels — it overflows. Use `font_size = 16` or smaller, or raise `top_row_height = 10` to give the top row more space.

---

## Rule 17: Hires emoji on small sign (scale=1) falls back to low-res

**SOURCE:** CLAUDE.md — "Hi-res emoji on the bigsign" section (line 87).

**DETECT:** A message or image widget with inline emoji (e.g., `:instagram:`) on a small sign (scale=1).

**SYMPTOM:** The hi-res variant (32×32) is NOT used. Renderer automatically falls back to 8×8 low-res sprite. This is by design — hi-res sprites are only rendered when `isinstance(canvas, ScaledCanvas)` (bigsign at scale > 1).

**FIX:** No fix needed — emoji render at full detail automatically on bigsign, and fallback gracefully on small sign. If you need more emoji detail on small sign, use HiresFont text instead or increase the canvas scale.

---

## Rule 18: BDF font `font_size` smart default only (no explicit needed)

**SOURCE:** CLAUDE.md — "Single-row image text" section (line 115).

**DETECT:** Gif or image widget with a BDF font (alias like `"6x12"`, `"5x8"`) and NO explicit `font_size` set in TOML.

**SYMPTOM:** No error. `font_size` defaults to `cell_h × _logical_scale` (12 on small sign, 48 on bigsign for FONT_DEFAULT). BDF fonts do NOT require explicit `font_size` — HiresFont does.

**FIX:** No fix needed. BDF fonts have smart defaults. If you want to scale a BDF explicitly, use `font_size = N × cell_h` (e.g., `font_size = 24` for 2× scale of a 12-cell BDF on small sign).

---

## Rule 19: Dissolve transition must use physical resolution on ScaledCanvas

**SOURCE:** CLAUDE.md — "Hardware Rendering Constraints" section, constraint #11 (line 162).

**DETECT:** Dissolve transition running on a bigsign with `default_scale = 4`. Internal code MUST unwrap the ScaledCanvas via `unwrap_to_real(canvas)` and scatter at physical pixels.

**SYMPTOM:** Without unwrapping, logical-grain scatter at scale=4 creates a fade-through-black at t=0.5 (every logical pixel and its 4×4 block blacks out simultaneously) instead of a dissolve. This is automatic in the codebase — not a user config issue, but listed for completeness.

**FIX:** No user action needed — the transition framework handles this internally. If you're implementing a custom transition, remember to unwrap before pixel-scatter operations on scaled canvases.

---

## Rule 20: Migration error from legacy text_scale to font_size

**SOURCE:** CLAUDE.md — "Single-row image text" section (line 115).

**DETECT:** Gif or image widget with `text_scale = <N>` in TOML (legacy field from older configs).

**SYMPTOM:** Config load raises with a migration error pointing to the new `font_size` formula: `font_size = N × cell_h_of_your_font`. For BDF 6×12: text_scale=2 → font_size=24, text_scale=4 → font_size=48.

**FIX:** Replace `text_scale = <N>` with `font_size = <N> × <cell_h>`. For example, if your BDF is 6×12 and you had `text_scale = 2`, use `font_size = 24`. For `text_scale = 4` with 6×12, use `font_size = 48`.
