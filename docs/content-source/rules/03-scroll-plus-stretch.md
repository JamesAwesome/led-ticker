# Rule 3: text_align scroll + fit stretch invalid on gif/image

**SOURCE:** `validate.py` `_check_static` (rule 3); CLAUDE.md "Footgun validation" inside "GIF widget and Still-image widget".

**DETECT:** A `gif` or `image` widget has both `text_align ∈ ("scroll", "scroll_over")` AND `fit = "stretch"`.

**SYMPTOM:** Config load reports an error:

```
text_align='scroll' with fit='stretch': no transparent regions for text to walk behind
```

**FIX:**

- Change `fit` to `"pillarbox"`, `"letterbox"`, or `"crop"`; OR
- Change `text_align` to `"left"`, `"right"`, or `"auto"`.

Scroll modes paint text first, then composite the image on top with skip-black — the image's transparent regions are what let text show through as it moves. `fit = "stretch"` fills the entire panel with image pixels, leaving no transparent regions, so the text would be completely hidden behind the image.
