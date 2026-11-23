"""#525: the frame counter means ENGINE_TICK_MS (50 ms) of wall clock on
EVERY engine loop, including the scroll loops that tick at
``scroll_step_ms``. Before this the scroll branches advanced one frame per
scroll pixel, so a typewriter / blink / rainbow ran 2.5× fast on a 20 ms
marquee and half speed on a 100 ms one, while `typing_duration_seconds`,
validate rule 61 and the docs all assumed 50 ms per frame.
"""

import ast
import inspect
from unittest import mock

import attrs
import pytest

from led_ticker import ticker as ticker_mod
from led_ticker.ticker import Ticker
from led_ticker.widgets._frame_aware import FrameAwareBase


@attrs.define
class _Anim(FrameAwareBase):
    """Frame-aware widget whose draw reports a fixed cursor."""

    cursor: int = 200
    draws: int = attrs.field(init=False, default=0)

    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        self.draws += 1
        return canvas, self.cursor

    @property
    def bg_color(self):
        return None

    @property
    def padding(self):
        return 0


class _LegacyAdvance:
    """Duck-typed widget with ONLY `advance_frame` (no mixin) — must keep
    getting one call per tick, never freeze."""

    def __init__(self):
        self.advances = 0
        self.draws = 0

    def draw(self, canvas, cursor_pos=0, **kwargs):
        self.draws += 1
        return canvas, 200

    def advance_frame(self, *, visit_id=None):
        self.advances += 1

    bg_color = None
    padding = 0


def _canvas():
    from rgbmatrix import _StubCanvas

    return _StubCanvas(width=160, height=16)


class TestSwapAndScrollCadence:
    """cursor 200 on a 160-wide canvas → stop_pos −40 → 40 scroll ticks.
    `continuous=True` skips the holds so only the scroll loop advances."""

    @pytest.mark.parametrize(
        ("scroll_speed", "frames"),
        [(0.02, 16), (0.05, 40), (0.1, 80)],
        ids=["20ms→16", "50ms→40(parity)", "100ms→80"],
    )
    async def test_scroll_frames_track_wall_clock(
        self, swapping_frame, no_sleep, scroll_speed, frames
    ):
        w = _Anim()
        swapping_frame.swap.return_value = _canvas()
        t = Ticker(monitors=[], frame=swapping_frame, scroll_speed=scroll_speed)
        await t._swap_and_scroll(_canvas(), w, hold_time=0, continuous=True)
        assert w.draws == 41  # entry draw + 40 scroll ticks
        assert w._frame_count == frames

    async def test_duck_typed_widget_keeps_one_frame_per_tick(
        self, swapping_frame, no_sleep
    ):
        w = _LegacyAdvance()
        swapping_frame.swap.return_value = _canvas()
        t = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0.02)
        await t._swap_and_scroll(_canvas(), w, hold_time=0, continuous=True)
        assert w.advances == 40

    async def test_mock_widget_is_not_mistaken_for_the_mixin(
        self, swapping_frame, no_sleep
    ):
        """`hasattr(Mock(), "advance_frame_elapsed")` is always True; the
        dispatch must look at the CLASS (like `_has_play`) or every
        spy-based engine test silently stops seeing advances."""
        w = mock.MagicMock()
        w.draw.return_value = (_canvas(), 200)
        w.bg_color = None
        w.padding = 0
        swapping_frame.swap.return_value = _canvas()
        t = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0.02)
        await t._swap_and_scroll(_canvas(), w, hold_time=0, continuous=True)
        assert w.advance_frame.call_count == 40
        assert w.advance_frame_elapsed.call_count == 0

    async def test_zero_scroll_speed_does_not_freeze_effects(
        self, swapping_frame, no_sleep
    ):
        """`scroll_speed=0` is test-only (validate rule 31 refuses it) but
        must degrade to one frame per tick, not a stuck counter."""
        w = _Anim()
        swapping_frame.swap.return_value = _canvas()
        t = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0)
        await t._swap_and_scroll(_canvas(), w, hold_time=0, continuous=True)
        assert w._frame_count == 40


class TestScrollAndDelayCadence:
    async def test_scroll_in_frames_track_wall_clock(self, swapping_frame, no_sleep):
        """100-px scroll-in at 20 ms = 2 s = 40 frames, then the 50 ms
        post-scroll hold (`delay=0.05` → 1 engine tick) adds one."""
        w = _Anim(cursor=5)
        swapping_frame.swap.return_value = _canvas()
        t = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0.02)
        await t._scroll_and_delay(_canvas(), w, delay=0.05, cursor_pos=100)
        assert w._frame_count == 41


class TestHoldTicksUnchanged:
    async def test_hold_is_one_frame_per_engine_tick(self, swapping_frame, no_sleep):
        w = _Anim(cursor=5)
        swapping_frame.swap.return_value = _canvas()
        t = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0.02)
        await t._hold_ticks(_canvas(), w, 10, 0, None)
        assert w._frame_count == 10


class TestScrollLoopsPassTickMs:
    """AST tripwire: every `_advance_frame_if_supported(...)` inside a loop
    that paces itself on `self.scroll_speed` must pass `tick_ms=`. A new
    scroll loop that forgets it silently reintroduces #525."""

    @staticmethod
    def _sleeps_on_scroll_speed(loop_node: ast.AST) -> bool:
        for n in ast.walk(loop_node):
            if isinstance(n, ast.Attribute) and n.attr == "scroll_speed":
                return True
        return False

    def test_every_scroll_paced_loop_passes_tick_ms(self):
        tree = ast.parse(inspect.getsource(ticker_mod))
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.While | ast.For | ast.AsyncFor):
                continue
            if not self._sleeps_on_scroll_speed(node):
                continue
            for call in ast.walk(node):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "_advance_frame_if_supported"
                    and not any(k.arg == "tick_ms" for k in call.keywords)
                ):
                    offenders.append(f"ticker.py:{call.lineno}")
        assert not offenders, (
            "scroll-paced loops must advance by wall clock: pass "
            f"tick_ms=self._scroll_tick_ms to _advance_frame_if_supported "
            f"at {offenders}"
        )

    def test_at_least_the_known_scroll_loops_were_scanned(self):
        """Guard the guard: the scan must have found the scroll loops."""
        tree = ast.parse(inspect.getsource(ticker_mod))
        n = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.While | ast.For | ast.AsyncFor)
            and self._sleeps_on_scroll_speed(node)
        )
        assert n >= 6, n
