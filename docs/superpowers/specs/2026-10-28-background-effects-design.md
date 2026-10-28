# Background effects (`background = ...`) — design

**Date:** 2026-10-28 · **Status:** approved in chat (James, option 1 of 3)

## Intent

Give widgets a first-class "paint this behind my content, every tick" hook so
full-panel background animations (fireworks today; stars / snow / rain later)
no longer have to masquerade as a `border`. The motivating case: the flair
pack's `flair.fireworks` border (led-ticker-plugins#128) spent the widget's only
`border` slot, so a rainbow ring and fireworks could not be combined on one
widget. The fix is a sibling field, `background`, with the same shape as
`border`, painted before it.

## Goals

- `background = "<plugin.name>"` or `{style = "<plugin.name>", ...kwargs}` on
  every widget that accepts `border` today (`message`, `countdown`, `countup`,
  `two_row`, `gif`, `image`, `clock`; plus any plugin widget that declares the
  field).
- Paint order per widget: **background → (image) → border → text**. On image
  widgets the background goes under the image so it shows through transparent
  / skipped-black regions and is hidden behind an opaque image.
- Plugin registration surface `api.background(name)`; core ships NO built-in
  styles (registry starts empty).
- Same effect-counter / transition-pause / fast-path contract as `border`:
  `frame_for("background")`, `frame_invariant`, `restart_on_visit`.
- `led-ticker validate` rejects `background` on unsupported widget types with
  a ruled error; `--list-fields` shows the field.
- Catalog + docs-site surface: `backgrounds` kind in `plugins_catalog.json`,
  API reference rows, a Backgrounds concept page, fact-pack rows.

## Non-goals

- Compositing multiple backgrounds or multiple borders (one slot each).
- Any built-in core background style.
- `bg_color` changes — a background effect paints over the `bg_color` fill.

## Design

- `src/led_ticker/backgrounds.py`: `BackgroundEffect` Protocol (`frame_invariant`,
  `paint(canvas, frame_count)`), `BackgroundEffectBase` (enforces the
  `frame_invariant` class attr via `__init_subclass__`, same as
  `BorderEffectBase`), `_BACKGROUND_REGISTRY: dict[str, type] = {}`.
- `plugin.py`: export both names; `api.background(name)`; `_buffers["backgrounds"]`.
  `_plugin_loader._REGISTRY_MAP["backgrounds"] = _BACKGROUND_REGISTRY`.
- `app/coercion._coerce_background(value)`: `None` → `None`; duck-typed
  pass-through; `str` → registry lookup → `_build_plugin_style(cls, {}, …)`;
  `dict` with `style` → registry lookup + kwargs; otherwise `ValueError` with
  the plugin-install hint (kind `"background"`).
- `app/factories`: `FIELD_HINTS["background"]`, `_DISPATCH_APPLICABLE_TYPES["background"]`
  (same set as `border`), and a coercion block mirroring `border`'s (type gate
  OR `_widget_declares_field(cls, "background")`).
- `validate._ERROR_PATTERNS`: `"background is only valid on"` → rule 72.
- `widgets/_frame_aware._EFFECT_ATTRS` gains `"background"`.
- `widgets/_effects.py`: `paint_background(widget, canvas)` — one helper so the
  paint sites can't drift (`getattr(widget, "background", None)`; paints with
  `widget.frame_for("background")`).
- Widget fields: `background: Any | None = attrs.field(default=None, kw_only=True)`
  on `TickerMessage`, `_CountWidget`, `Clock`, `TwoRowMessage`, `_BaseImageWidget`.
  Paint sites: text widgets call `paint_background` immediately before the
  border paint; image widgets call it immediately after each `reset_canvas(...)`
  that precedes an image paint (`_image_base` ×4, `gif._play_no_text`,
  `still._play_no_text`). The three image fast-path predicates AND in
  `background.frame_invariant` (default `True` when unset).
- Catalog: `_SURFACE_KINDS` / `_PRIMARY_ORDER` gain `"backgrounds"` (after
  `"borders"`); `PluginCatalog.astro` `KIND_ORDER` / `KIND_LABELS` likewise.

## Builder notes

- Left to the builder: exact FieldHint wording; docs page prose.
- Core release: minor (`v4.32.0`) — new public plugin surface.
- Follow-up in led-ticker-plugins: flair re-registers fireworks under
  `api.background("fireworks")` (module rename, README/CLAUDE), core floor
  `>= 4.32`, release `flair-v0.16.0`.
- Acceptance (James): a scrolling `message` on moonbunny with
  `border = "rainbow"` AND `background = "flair.fireworks"` running together.
