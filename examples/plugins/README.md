# Example led-ticker plugin

`acme/` is a complete reference plugin exercising every plugin surface
(widget, transition, color provider, animation, border, easing, emoji,
hi-res emoji, font) and every lifecycle hook (overlay, on_startup,
on_shutdown). Each contribution is namespaced `acme.*`.

**Local use:** copy `acme/` into your `config/plugins/`.
**Packaged use:** ship it as a package declaring
`[project.entry-points."led_ticker.plugins"]  acme = "acme:register"`.

Full walkthrough: see the Plugins page in the docs site.

`acme/fonts/Brand.ttf` here is a copy of Inter Bold for illustration — a real plugin can bundle any `.ttf`/`.otf`.
