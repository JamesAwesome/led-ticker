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
    "draw_with_emoji",
]


def test_draw_with_emoji_is_the_pixel_emoji_function():
    from led_ticker.pixel_emoji import draw_with_emoji

    assert P.draw_with_emoji is draw_with_emoji


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
