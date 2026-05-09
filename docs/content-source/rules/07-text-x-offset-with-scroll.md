# Rule 7: text_x_offset is invalid with scroll text_align

**SOURCE:** `validate.py` `_check_static` (rule 7); CLAUDE.md "Footgun validation" inside "GIF widget and Still-image widget".

**DETECT:** A widget has `text_x_offset != 0` AND `text_align ∈ ("scroll", "scroll_over")`.

**SYMPTOM:** Config load reports an error:

```
text_x_offset is invalid with scroll text_align
```

**FIX:**

- Remove `text_x_offset` (set it to `0` or omit the key); OR
- Change `text_align` to `"left"`, `"right"`, or `"auto"` and keep the offset.

In scroll mode the text cursor position is computed dynamically each tick — a static `text_x_offset` would shift the start point but would not follow the scrolling logic, so the resulting position would be undefined. Static alignment modes (`left`, `right`, `auto`) compute a fixed anchor where the offset applies predictably.
