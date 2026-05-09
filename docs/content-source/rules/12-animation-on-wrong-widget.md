# Rule 12: animation field only valid on message, gif, and image widgets

**SOURCE:** `app.py` `_build_widget` (raises at config-load); `validate.py` `_ERROR_PATTERNS` (rule 12); CLAUDE.md "Color providers and animations".

**DETECT:** A widget of any type other than `message`, `gif`, or `image` specifies an `animation` field.

**SYMPTOM:** Config load raises with an error containing:

```
animation is only valid on type="message", "gif", or "image"; got type=<widget_type>. For color effects on other widgets, use font_color = 'rainbow' (or similar).
```

**FIX:**

- Remove `animation` from the widget; OR
- Use `font_color = "rainbow"` (or `"color_cycle"`, or a gradient table) on widgets that support `font_color` — these work on data widgets like `weather`, `crypto`, etc.

The `animation` field drives effects such as `"typewriter"` that require a controlled text-reveal loop inside `TickerMessage` or `_BaseImageWidget`. Data widgets (`weather`, `rss_feed`, `mlb`, etc.) have their own draw paths and do not participate in that loop — wiring `animation` to them would silently do nothing at best, or produce an error at worst. Color-cycle effects via `font_color` are the supported alternative for dynamic color on those widget types.
