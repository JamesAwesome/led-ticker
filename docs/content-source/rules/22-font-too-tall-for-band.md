# Rule 22: font line-height exceeds per-row band on a multi-row widget

**SOURCE:** `validate.py` `_check_band_layout` (rule 22, error); also raised at draw time by `TwoRowMessage.draw` and `_BaseImageWidget._play_with_two_row_text`.

**DETECT:** A section contains a `type = "two_row"` widget OR a `type = "gif"` / `type = "image"` widget with `bottom_text != ""`, AND a row's font has a logical line-height larger than the row's band height (in logical rows).

**SYMPTOM:** `led-ticker validate` reports:

```
top font line-height (12 logical rows) exceeds the per-row band (8 rows on a 16-tall canvas).
```

**FIX:**

- Pick a smaller `font_size` for the offending row.
- Or raise the section's `content_height` so each row's band is taller (50/50 split: band = `content_height / 2`).
- Or set `top_row_height` to give the offending row more rows (the other row gets the remainder).
- Or use a BDF alias (`5x8`, `6x12`) — they have fixed cell heights and tend to fit small bands more reliably than a hi-res font sized for visual weight.

The check fires both at config-load (so a misconfigured TOML fails up-front in `led-ticker validate`) and at first draw (so a runtime-resolved font that grew too tall still gets caught). For two_row at scale=2, the canonical pairing is BDF 5x8 on `content_height = 16`; bumping to hi-res Inter at sizes 14+ usually requires `content_height = 24` or larger.
