import led_ticker.plugin as P

NEW_SYMBOLS = [
    "TickerMessage",
    "FrameAwareBase",
    "safe_scale",
    "compute_baseline_for_band",
    "measure_width",
    "resolve_band_heights",
    "font_line_height_logical",
    "FONT_DEFAULT",
    "FONT_SMALL",
    "ScaledCanvas",
    "unwrap_to_real",
    "paint_hires",
]


def test_draw_with_emoji_is_public():
    # Promoted from internal alias (_draw_with_emoji) to public surface in P3.
    assert "draw_with_emoji" in P.__all__
    assert hasattr(P, "draw_with_emoji")


def test_baseball_surface_symbols_exported():
    for name in NEW_SYMBOLS:
        assert name in P.__all__, f"{name} missing from led_ticker.plugin.__all__"
        assert hasattr(P, name), f"{name} not importable from led_ticker.plugin"


def test_frame_aware_base_is_a_real_public_class():
    from led_ticker.widgets._frame_aware import FrameAwareBase as RealBase

    assert P.FrameAwareBase is RealBase
    import led_ticker.widgets._frame_aware as fa

    assert not hasattr(fa, "_FrameAware"), (
        "_FrameAware should be renamed to FrameAwareBase"
    )


def test_snap_and_normalize_exported():
    assert "snap_reset" in P.__all__ and hasattr(P, "snap_reset")
    # normalize_bg is internal — snap_reset calls it; it is NOT on the surface.
    assert "normalize_bg" not in P.__all__ and not hasattr(P, "normalize_bg")
    from led_ticker.transitions import _normalize_bg

    assert _normalize_bg(None) is None
    assert _normalize_bg((1, 2, 3)) == (1, 2, 3)


def test_is_scaled_predicate_exported():
    assert "is_scaled" in P.__all__ and hasattr(P, "is_scaled")

    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    from led_ticker.scaled_canvas import ScaledCanvas

    options = RGBMatrixOptions()
    options.cols = 256
    options.rows = 64
    options.chain_length = 1
    matrix = RGBMatrix(options=options)
    real = matrix.CreateFrameCanvas()

    assert P.is_scaled(real) is False
    assert P.is_scaled(ScaledCanvas(real, scale=4)) is True


def test_compute_cursor_is_public():
    import led_ticker.plugin as P
    from led_ticker.drawing import compute_cursor as core_compute_cursor

    assert "compute_cursor" in P.__all__
    assert P.compute_cursor is core_compute_cursor
