"""Tests for led_ticker.frame."""

from unittest.mock import MagicMock

from led_ticker.frame import LedFrame


def test_frame_get_clean_canvas():
    frame = LedFrame(led_cols=32, led_chain_length=5)
    canvas = frame.get_clean_canvas()
    assert canvas.width == 160  # 32 * 5


def test_frame_default_values():
    frame = LedFrame()
    assert frame.led_rows == 16
    assert frame.led_cols == 32
    assert frame.led_brightness == 100
    assert frame.led_hardware_mapping == "adafruit-hat"


def test_stub_canvas_size_honors_u_mapper_fold():
    """U-mapper folds 1×8 chain into 2×4: doubles height, halves width."""
    frame = LedFrame(
        led_rows=32,
        led_cols=64,
        led_chain_length=8,
        led_parallel=1,
        led_pixel_mapper_config="U-mapper",
    )
    canvas = frame.matrix.CreateFrameCanvas()
    assert canvas.height == 64
    assert canvas.width == 256


def test_stub_canvas_size_default_no_mapper():
    frame = LedFrame(led_rows=16, led_cols=32, led_chain_length=5)
    canvas = frame.matrix.CreateFrameCanvas()
    assert canvas.height == 16
    assert canvas.width == 160


def test_stub_canvas_size_parallel_chains():
    frame = LedFrame(led_rows=32, led_cols=64, led_chain_length=4, led_parallel=2)
    canvas = frame.matrix.CreateFrameCanvas()
    assert canvas.height == 64  # 32 × 2 parallel
    assert canvas.width == 256  # 64 × 4 chain


def test_ledframe_matrix_is_not_none_after_construction():
    frame = LedFrame(led_cols=32, led_chain_length=5)
    assert frame.matrix is not None


def test_framerate_fraction_default():
    """limit_refresh_rate_hz=0 → fraction stays at 1 (no change to behaviour)."""
    frame = LedFrame(led_limit_refresh_rate_hz=0)
    assert frame._framerate_fraction == 1


def test_framerate_fraction_computed():
    """100 Hz / 20 fps engine = fraction 5."""
    frame = LedFrame(led_limit_refresh_rate_hz=100)
    assert frame._framerate_fraction == 5


def test_framerate_fraction_rounds():
    """15 Hz / 20 fps rounds to 0.75 → floor-at-1 → 1."""
    frame = LedFrame(led_limit_refresh_rate_hz=15)
    assert frame._framerate_fraction == 1


def test_swap_passes_fraction_to_matrix():
    """frame.swap() must forward _framerate_fraction to SwapOnVSync."""
    frame = LedFrame(led_limit_refresh_rate_hz=100)
    mock_matrix = MagicMock()
    frame.matrix = mock_matrix
    canvas = object()
    frame.swap(canvas)
    mock_matrix.SwapOnVSync.assert_called_once_with(canvas, 5)


def test_swap_returns_new_canvas():
    """frame.swap() returns the back-buffer (new canvas, not the same object)."""
    frame = LedFrame()
    canvas = frame.matrix.CreateFrameCanvas()
    result = frame.swap(canvas)
    assert result is not canvas


def test_overlay_hooks_default_empty():
    frame = LedFrame()
    assert frame.overlay_hooks == []


def test_swap_runs_hooks_before_swap_with_canvas():
    """Each overlay hook is called once with the canvas, BEFORE SwapOnVSync."""
    frame = LedFrame()
    order: list[str] = []
    received: list[object] = []
    canvas = object()

    def hook(c):
        received.append(c)
        order.append("hook")

    mock_matrix = MagicMock()
    mock_matrix.SwapOnVSync.side_effect = lambda c, f: order.append("swap")
    frame.matrix = mock_matrix
    frame.overlay_hooks.append(hook)

    frame.swap(canvas)

    assert received == [canvas]
    assert order == ["hook", "swap"]


def test_swap_runs_multiple_hooks_in_registration_order():
    frame = LedFrame()
    calls: list[str] = []
    frame.matrix = MagicMock()
    frame.overlay_hooks.extend(
        [lambda c: calls.append("a"), lambda c: calls.append("b")]
    )
    frame.swap(object())
    assert calls == ["a", "b"]


def test_swap_no_hooks_unchanged():
    """Empty overlay_hooks: swap forwards (canvas, fraction) and returns the result."""
    frame = LedFrame(led_limit_refresh_rate_hz=100)
    mock_matrix = MagicMock()
    mock_matrix.SwapOnVSync.return_value = "backbuffer"
    frame.matrix = mock_matrix
    canvas = object()
    result = frame.swap(canvas)
    mock_matrix.SwapOnVSync.assert_called_once_with(canvas, 5)
    assert result == "backbuffer"


def test_rp1_pio_forwarded_to_options():
    """led_rp1_pio=1 must reach RGBMatrixOptions.rp1_pio."""
    frame = LedFrame(led_rp1_pio=1)
    assert frame.matrix._options.rp1_pio == 1


def test_swap_records_engine_liveness():
    """LedFrame.swap() bumps the status board's swap counter — the web UI's
    only way to tell a wedged render loop from a healthy one."""
    from led_ticker import status_board
    from led_ticker.status_board import StatusBoard

    frame = LedFrame(led_cols=32, led_chain_length=5)
    canvas = frame.get_clean_canvas()

    # Without a board: swap must work unchanged.
    canvas = frame.swap(canvas)

    board = StatusBoard(path="/unused/status.json", min_interval=3600.0)
    status_board.set_active_board(board)
    try:
        canvas = frame.swap(canvas)
        canvas = frame.swap(canvas)
        assert board.swap_count == 2
    finally:
        status_board.clear_active_board()


def test_install_preview_returns_tee_from_get_clean_canvas(tmp_path):
    from led_ticker.preview import PreviewTee

    frame = LedFrame(led_cols=32, led_chain_length=1)
    tee = PreviewTee(
        hw=frame.matrix.CreateFrameCanvas(),
        width=32,
        height=16,
        frame_path=tmp_path / "preview.bin",
    )
    frame.install_preview(tee)
    canvas = frame.get_clean_canvas()
    assert canvas is tee  # same object, every time
    assert frame.get_clean_canvas() is tee


def test_swap_unwraps_and_rebinds_tee(tmp_path):
    from led_ticker.preview import PreviewTee

    frame = LedFrame(led_cols=32, led_chain_length=1)
    tee = PreviewTee(
        hw=frame.matrix.CreateFrameCanvas(),
        width=32,
        height=16,
        frame_path=tmp_path / "preview.bin",
    )
    frame.install_preview(tee)
    canvas = frame.get_clean_canvas()
    hw_before = tee._hw
    returned = frame.swap(canvas)
    assert returned is tee  # callers keep the tee (constraint #1 unchanged)
    assert tee._hw is not hw_before  # stub returns a DIFFERENT canvas


def test_swap_captures_when_watched(tmp_path):
    from led_ticker.preview import PreviewTee

    frame = LedFrame(led_cols=32, led_chain_length=1)
    tee = PreviewTee(
        hw=frame.matrix.CreateFrameCanvas(),
        width=32,
        height=16,
        frame_path=tmp_path / "preview.bin",
    )
    frame.install_preview(tee)
    canvas = frame.get_clean_canvas()  # mirror off here
    tee.set_watched(True)
    canvas = frame.get_clean_canvas()  # fresh tick: Clear mirrored
    canvas.SetPixel(0, 0, 1, 2, 3)
    frame.swap(canvas)
    assert (tmp_path / "preview.bin").exists()


def test_overlay_hooks_paint_through_tee_into_shadow(tmp_path):
    """The busy-light dot must appear in the preview: hooks receive the tee."""
    from led_ticker.preview import PreviewTee

    frame = LedFrame(led_cols=32, led_chain_length=1)
    tee = PreviewTee(
        hw=frame.matrix.CreateFrameCanvas(),
        width=32,
        height=16,
        frame_path=tmp_path / "preview.bin",
    )
    frame.install_preview(tee)
    tee.set_watched(True)
    canvas = frame.get_clean_canvas()
    frame.overlay_hooks.append(lambda c: c.SetPixel(31, 0, 200, 0, 0))
    frame.swap(canvas)
    i = (0 * 32 + 31) * 3
    assert tuple(tee._shadow[i : i + 3]) == (200, 0, 0)


def test_swap_without_preview_unchanged():
    frame = LedFrame(led_cols=32, led_chain_length=1)
    canvas = frame.get_clean_canvas()
    swapped = frame.swap(canvas)
    assert swapped is not canvas  # plain path: stub returns a new canvas
