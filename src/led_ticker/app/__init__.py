"""led_ticker.app — application package.

This package replaces the former app.py module. All names remain
importable from this namespace for backwards compatibility.
"""

from __future__ import annotations

# CLI
from led_ticker.app.cli import _setup_logging, main

# Coercion layer
from led_ticker.app.coercion import (
    _COLOR_KEYS,
    _PROVIDER_COLOR_KEYS,
    _RAW_COLOR_KEYS,
    _WIDGET_ENUM_FIELDS,
    _WIDGET_FLOAT_FIELDS,
    _WIDGET_INT_FIELDS,
    _coerce_animation,
    _coerce_border,
    _coerce_color,
    _coerce_color_provider,
    _coerce_widget_cfg,
    _coerce_widget_colors,
    _is_hires_font_name,
    _provider_from_style,
    _validate_rgb,
)

# Factory functions
from led_ticker.app.factories import (
    RANDOM_COLOR,
    RUN_MODES,
    _build_title,
    _build_trans_obj,
    _build_widget,
    _cache_key,
    _configure_user_font_dir,
    _list_widget_fields,
    _resolve_buffer_msg,
    _resolve_title_delay,
    build_frame_from_config,
)

# Run loop
from led_ticker.app.run import run  # noqa: F401

# Re-exported for backwards compatibility
from led_ticker.config import load_config  # noqa: F401

__all__ = [
    "RANDOM_COLOR",
    "RUN_MODES",
    "_build_title",
    "_build_trans_obj",
    "_build_widget",
    "_cache_key",
    "_coerce_animation",
    "_coerce_border",
    "_coerce_color",
    "_coerce_color_provider",
    "_coerce_widget_cfg",
    "_coerce_widget_colors",
    "_COLOR_KEYS",
    "_configure_user_font_dir",
    "_is_hires_font_name",
    "_list_widget_fields",
    "_PROVIDER_COLOR_KEYS",
    "_provider_from_style",
    "_RAW_COLOR_KEYS",
    "_resolve_buffer_msg",
    "_resolve_title_delay",
    "_setup_logging",
    "_validate_rgb",
    "_WIDGET_ENUM_FIELDS",
    "_WIDGET_FLOAT_FIELDS",
    "_WIDGET_INT_FIELDS",
    "build_frame_from_config",
    "load_config",
    "main",
    "run",
]
