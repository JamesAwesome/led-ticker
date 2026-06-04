"""Minimal example led-ticker plugin — the worked example for the authoring guide.

Drop `example/` into your `config/plugins/` (local use), or package it with an
`[project.entry-points."led_ticker.plugins"]  example = "example:register"`
entry (packaged use), then reference it in TOML as `type = "example.counter"`.

Imports only `led_ticker.plugin` (the public surface) plus `attrs` and stdlib —
never a private `led_ticker.*` module.
"""

import datetime as _dt

import attrs

from led_ticker.plugin import Color, draw_text, make_color, resolve_font


def register(api):
    @api.widget("counter")
    @attrs.define
    class Counter:
        """Shows whole days since a configured date, e.g. ``DAY 42``."""

        # Config fields. The loader builds the widget from your TOML, passing
        # declared keys as constructor kwargs; `@attrs.define` lets it inspect them.
        since: str = "2020-01-01"
        label: str = "DAY"
        # `color` is a known color key: the loader coerces an [r, g, b] list in
        # TOML into a Color before your widget sees it (None = default white).
        color: Color | None = None

        @classmethod
        def validate_config(cls, cfg):
            """Pre-coercion config check; return a list of human-readable errors."""
            errors = []
            since = cfg.get("since")
            if since is None:
                errors.append("since is required (a YYYY-MM-DD date)")
            else:
                try:
                    start = _dt.date.fromisoformat(str(since))
                except ValueError:
                    errors.append(f"since must be a YYYY-MM-DD date; got {since!r}")
                else:
                    if start > _dt.date.today():
                        errors.append(f"since must not be in the future; got {since!r}")
            return errors

        def _days(self):
            return (_dt.date.today() - _dt.date.fromisoformat(self.since)).days

        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
            """Render `<label> <N>` onto the canvas; return (canvas, end_x)."""
            font = resolve_font("6x12")
            color = self.color if self.color is not None else make_color(255, 255, 255)
            text = f"{self.label} {self._days()}"
            end_x = draw_text(canvas, font, text, cursor_pos, 10 + y_offset, color)
            return canvas, end_x
