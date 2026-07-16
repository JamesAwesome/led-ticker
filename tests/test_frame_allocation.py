"""Process-lifetime allocation tripwire (spec: engine-liveness Phase 1).

Steady-state render paths must never call backend.create_canvas — on the
real backend each call is a C++ CreateFrameCanvas() retained until process
exit. LedFrame recycles the swap-returned buffer; this test drives the real
LedFrame + HeadlessBackend through the three paths that historically
allocated (entry-transition seeds, dark idle, empty-playlist idle) and pins
the total."""

from led_ticker.backends.headless import HeadlessBackend
from led_ticker.frame import LedFrame


class _CountingHeadless(HeadlessBackend):
    def __init__(self, width: int, height: int, *, pixel_mapper_config: str = ""):
        super().__init__(width, height, pixel_mapper_config=pixel_mapper_config)
        self.create_calls = 0

    def create_canvas(self):
        self.create_calls += 1
        return super().create_canvas()


def _live_frame():
    backend = _CountingHeadless(width=64, height=16)
    frame = LedFrame(backend=backend)
    frame.setup()
    return frame, backend


def test_allocation_is_constant_across_steady_state_paths():
    from led_ticker.app.run import _blank_swap

    frame, backend = _live_frame()
    # Boot-ish first fetch + swap.
    c = frame.get_clean_canvas()
    c = frame.swap(c)
    baseline = backend.create_calls
    # N "entry transition seed + section run" fetch/swap cycles.
    for _ in range(10):
        c = frame.get_clean_canvas()
        c = frame.swap(c)
    # N dark/empty-idle keepalives.
    for _ in range(10):
        _blank_swap(frame)
    assert backend.create_calls == baseline
    assert baseline <= 2  # first-fetch bound (nothing recycled before swap #1)
