"""AnimationFrame.rotation seam + ENGINE_TICK_MS plugin export
(propeller spec §1/§2).

Extended for the lens seam: AnimationFrame.lens defaults None and
coexists with rotation (fisheye spec §1).
"""

from led_ticker.animations import AnimationFrame, LensSpec, Typewriter


def test_rotation_defaults_to_zero() -> None:
    frame = AnimationFrame(visible_text="HI")
    assert frame.rotation == 0.0


def test_rotation_keyword_settable() -> None:
    frame = AnimationFrame(visible_text="HI", rotation=90.0)
    assert frame.rotation == 90.0


def test_typewriter_emits_zero_rotation() -> None:
    """Back-compat: Typewriter's frames carry the default rotation."""
    tw = Typewriter()
    assert tw.frame_for(5, "HELLO", 160, 40).rotation == 0.0


def test_engine_tick_ms_on_plugin_surface() -> None:
    """Acceptance criterion (spec §2): flair imports ENGINE_TICK_MS from
    led_ticker.plugin — its import-purity test forbids any other path."""
    from led_ticker import constants, plugin

    assert plugin.ENGINE_TICK_MS is constants.ENGINE_TICK_MS
    assert "ENGINE_TICK_MS" in plugin.__all__


def test_rotation_surface_on_plugin_surface() -> None:
    """flair.spinout imports the seam through the public surface only."""
    from led_ticker import plugin, rotate

    assert plugin.make_rotation_surface is rotate.make_rotation_surface
    assert plugin.RotationSurface is rotate.RotationSurface
    assert "make_rotation_surface" in plugin.__all__
    assert "RotationSurface" in plugin.__all__


def test_lens_spec_on_plugin_surface() -> None:
    """flair.fisheye imports LensSpec through the public surface only —
    identity + __all__ membership (drift-guarded by
    tests/test_docs_plugin_api_drift.py)."""
    from led_ticker import animations, plugin

    assert plugin.LensSpec is animations.LensSpec
    assert "LensSpec" in plugin.__all__


def test_lens_defaults_to_none() -> None:
    """AnimationFrame.lens field defaults to None — preserves all existing
    draw paths untouched (fisheye spec §1)."""
    frame = AnimationFrame(visible_text="HI")
    assert frame.lens is None


def test_lens_and_rotation_coexist_in_dataclass() -> None:
    """Both fields are settable independently — widget integration may raise
    if both are non-default, but the data type does not forbid it."""
    spec = LensSpec()
    frame = AnimationFrame(visible_text="X", rotation=45.0, lens=spec)
    assert frame.rotation == 45.0
    assert frame.lens is spec
