"""Tests for led_ticker.frame."""

from unittest.mock import Mock

from led_ticker.backends.headless import HeadlessBackend
from led_ticker.backends.rgbmatrix import RgbMatrixBackend
from led_ticker.frame import LedFrame


def _frame(backend=None):
    """Return a setup-ready LedFrame with a HeadlessBackend by default."""
    if backend is None:
        backend = HeadlessBackend(160, 16)
    f = LedFrame(backend=backend)
    f.setup()
    return f


def _rgb_frame(**kwargs):
    """Return a setup LedFrame backed by RgbMatrixBackend with given kwargs."""
    backend = RgbMatrixBackend(**kwargs)
    f = LedFrame(backend=backend)
    f.setup()
    return f


def test_frame_get_clean_canvas():
    frame = _rgb_frame(led_cols=32, led_chain_length=5)
    canvas = frame.get_clean_canvas()
    assert canvas.width == 160  # 32 * 5


def test_stub_canvas_size_honors_u_mapper_fold():
    """U-mapper folds 1×8 chain into 2×4: doubles height, halves width."""
    frame = _rgb_frame(
        led_rows=32,
        led_cols=64,
        led_chain_length=8,
        led_parallel=1,
        led_pixel_mapper_config="U-mapper",
    )
    canvas = frame.create_canvas()
    assert canvas.height == 64
    assert canvas.width == 256


def test_stub_canvas_size_default_no_mapper():
    frame = _rgb_frame(led_rows=16, led_cols=32, led_chain_length=5)
    canvas = frame.create_canvas()
    assert canvas.height == 16
    assert canvas.width == 160


def test_stub_canvas_size_parallel_chains():
    frame = _rgb_frame(led_rows=32, led_cols=64, led_chain_length=4, led_parallel=2)
    canvas = frame.create_canvas()
    assert canvas.height == 64  # 32 × 2 parallel
    assert canvas.width == 256  # 64 × 4 chain


def test_ledframe_backend_is_not_none_after_construction():
    frame = _frame()
    assert frame.backend is not None


def test_framerate_fraction_default():
    """limit_refresh_rate_hz=0 → fraction stays at 1 (no change to behaviour)."""
    frame = _rgb_frame(led_limit_refresh_rate_hz=0)
    assert frame.backend.framerate_fraction == 1


def test_framerate_fraction_computed():
    """100 Hz / 20 fps engine = fraction 5."""
    frame = _rgb_frame(led_limit_refresh_rate_hz=100)
    assert frame.backend.framerate_fraction == 5


def test_framerate_fraction_rounds():
    """15 Hz / 20 fps rounds to 0.75 → floor-at-1 → 1."""
    frame = _rgb_frame(led_limit_refresh_rate_hz=15)
    assert frame.backend.framerate_fraction == 1


def test_frame_swap_calls_backend_swap_without_fraction_arg():
    """framerate_fraction is no longer part of the Backend protocol; frame.swap
    calls backend.swap(canvas) with no fraction arg (the rgbmatrix backend
    applies its own fraction internally — see the rgbmatrix backend test)."""
    backend = HeadlessBackend(32, 16)
    frame = LedFrame(backend=backend)
    frame.setup()
    received = []
    original_swap = backend.swap

    def capturing_swap(canvas):
        received.append(canvas)
        return original_swap(canvas)

    backend.swap = capturing_swap
    canvas = frame.get_clean_canvas()
    frame.swap(canvas)
    assert len(received) == 1


def test_swap_returns_new_canvas():
    """frame.swap() returns the back-buffer (new canvas, not the same object)."""
    frame = _frame()
    canvas = frame.get_clean_canvas()
    result = frame.swap(canvas)
    assert result is not canvas


def test_overlay_hooks_default_empty():
    frame = _frame()
    assert frame.overlay_hooks == []


def test_swap_runs_hooks_before_swap_with_canvas():
    """Each overlay hook is called once with the canvas, BEFORE backend swap."""
    order: list[str] = []
    received: list[object] = []

    backend = HeadlessBackend(32, 16)
    original_swap = backend.swap

    def recording_swap(canvas):
        order.append("swap")
        return original_swap(canvas)

    backend.swap = recording_swap
    frame = LedFrame(backend=backend)
    frame.setup()

    def hook(c):
        received.append(c)
        order.append("hook")

    frame.overlay_hooks.append(hook)
    canvas = frame.get_clean_canvas()
    frame.swap(canvas)

    assert received == [canvas]
    assert order == ["hook", "swap"]


def test_swap_runs_multiple_hooks_in_registration_order():
    frame = _frame()
    calls: list[str] = []
    frame.overlay_hooks.extend(
        [lambda c: calls.append("a"), lambda c: calls.append("b")]
    )
    frame.swap(frame.get_clean_canvas())
    assert calls == ["a", "b"]


def test_swap_no_hooks_unchanged():
    """Empty overlay_hooks: swap returns a different back-buffer canvas."""
    frame = _rgb_frame(led_limit_refresh_rate_hz=100)
    canvas = frame.get_clean_canvas()
    result = frame.swap(canvas)
    assert result is not canvas


def test_rp1_pio_forwarded_to_options():
    """led_rp1_pio=1 must reach RGBMatrixOptions.rp1_pio."""
    frame = _rgb_frame(led_rp1_pio=1)
    assert frame.backend._matrix._options.rp1_pio == 1


def test_swap_records_engine_liveness():
    """LedFrame.swap() bumps the status board's swap counter — the web UI's
    only way to tell a wedged render loop from a healthy one."""
    from led_ticker import status_board
    from led_ticker.status_board import StatusBoard

    frame = _rgb_frame(led_cols=32, led_chain_length=5)
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

    frame = _rgb_frame(led_cols=32, led_chain_length=1)
    tee = PreviewTee(
        hw=frame.create_canvas(),
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

    frame = _rgb_frame(led_cols=32, led_chain_length=1)
    tee = PreviewTee(
        hw=frame.create_canvas(),
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

    frame = _rgb_frame(led_cols=32, led_chain_length=1)
    tee = PreviewTee(
        hw=frame.create_canvas(),
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

    frame = _rgb_frame(led_cols=32, led_chain_length=1)
    tee = PreviewTee(
        hw=frame.create_canvas(),
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
    frame = _rgb_frame(led_cols=32, led_chain_length=1)
    canvas = frame.get_clean_canvas()
    swapped = frame.swap(canvas)
    assert swapped is not canvas  # plain path: stub returns a new canvas


class _CountingBackend:
    """Minimal Backend double that counts create_canvas calls and models
    double-buffering (swap returns the previous back buffer)."""

    def __init__(self):
        self.create_calls = 0
        self._back = None
        self.brightness = 100

    def setup(self):
        pass

    def create_canvas(self):
        self.create_calls += 1
        return Mock(name=f"canvas{self.create_calls}")

    def swap(self, canvas):
        old_back = self._back if self._back is not None else Mock(name="back0")
        self._back = canvas
        return old_back


def _counting_frame():
    """Return a setup-ready LedFrame backed by a _CountingBackend, plus the
    backend itself (so tests can assert on create_calls)."""
    backend = _CountingBackend()
    frame = LedFrame(backend=backend)
    frame.setup()
    return frame, backend


class TestGetCleanCanvasRecycling:
    def test_first_fetch_allocates(self):
        frame, backend = _counting_frame()
        c = frame.get_clean_canvas()
        assert backend.create_calls == 1
        c.Clear.assert_called_once()

    def test_fetch_after_swap_recycles_the_returned_buffer(self):
        frame, backend = _counting_frame()
        c1 = frame.get_clean_canvas()
        back = frame.swap(c1)  # constraint #1: capture
        c2 = frame.get_clean_canvas()
        assert c2 is back  # the just-swapped-out buffer, recycled
        assert backend.create_calls == 1  # no new allocation
        back.Clear.assert_called()  # recycled buffer is cleared

    def test_steady_state_allocation_is_constant(self):
        frame, backend = _counting_frame()
        c = frame.get_clean_canvas()
        for _ in range(50):
            c = frame.swap(c)
            c = frame.get_clean_canvas()
        assert backend.create_calls == 1

    def test_double_fetch_before_any_swap_allocates_twice(self):
        # Documented bound: with no swap yet there is nothing to recycle.
        frame, backend = _counting_frame()
        frame.get_clean_canvas()
        frame.get_clean_canvas()
        assert backend.create_calls == 2

    def test_tee_path_recycles_hw_buffer(self):
        frame, backend = _counting_frame()
        tee = Mock()
        tee.mirror = False
        frame.install_preview(tee)
        c1 = frame.get_clean_canvas()
        assert c1 is tee
        hw1 = tee._hw
        result = frame.swap(tee)
        assert result is tee
        c2 = frame.get_clean_canvas()
        assert c2 is tee
        assert tee._hw is not hw1  # rebound to the swap-returned buffer
        assert backend.create_calls == 1
