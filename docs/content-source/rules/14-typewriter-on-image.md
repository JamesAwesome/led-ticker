# Rule 14: animation = "typewriter" on gif/image is single-row only

**SOURCE:** CLAUDE.md — "Typewriter on image widgets" section.

**DETECT:** A widget of type `gif` or `image` specifies `animation = "typewriter"` AND any of: `bottom_text != ""`, `text_align ∈ ("scroll", "scroll_over")`, or `text == ""`.

**SYMPTOM:** Config load raises with one of:
- `"animation='typewriter' on gif/image is single-row only; bottom_text is set"`
- `"animation='typewriter' on gif/image cannot combine with scrolling text_align"`
- `"animation='typewriter' on gif/image requires non-empty text"`

**FIX:**
- For two-row layouts: omit `animation` (typewriter is single-row only).
- For scrolling text: omit `animation`.
- For empty text: add a non-empty `text = "..."` or omit `animation`.

Typewriter on gif/image composes cleanly with `font_color = "rainbow"` and `border = {style="rainbow"}` — independent counters, all animate together. The single-row constraint exists because typewriter draws fixed-position glyphs and a scrolling/two-row layout has no fixed positions to anchor characters to.
