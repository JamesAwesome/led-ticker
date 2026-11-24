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


class TestApiVersion:
    def test_minor_bump_is_probeable(self):
        """Plugins gate on this: flair.blink may drop its fastest-cadence
        (20 ms) WCAG assumption once `API_VERSION >= (1, 6)`."""
        from led_ticker import plugin

        assert plugin.API_VERSION >= (1, 6)


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

    @staticmethod
    def _is_self_scroll_tick_ms(value: ast.expr) -> bool:
        """Exactly `self._scroll_tick_ms` — the ONE floored tick property.
        Any other expression (a literal, `tick_ms`, a raw
        `round(self.scroll_speed * 1000)`) bypasses the swap-interval floor
        and is an offender even though it names the kwarg."""
        return (
            isinstance(value, ast.Attribute)
            and value.attr == "_scroll_tick_ms"
            and isinstance(value.value, ast.Name)
            and value.value.id == "self"
        )

    def test_kwarg_must_be_self_scroll_tick_ms(self):
        """Guard the guard: a `tick_ms=` kwarg with any other value is
        rejected by the predicate."""
        ok = ast.parse("self._scroll_tick_ms", mode="eval").body
        assert self._is_self_scroll_tick_ms(ok)
        for src in (
            "tick_ms",
            "50",
            "round(self.scroll_speed * 1000)",
            "other._scroll_tick_ms",
            "self.scroll_tick_ms",
        ):
            bad = ast.parse(src, mode="eval").body
            assert not self._is_self_scroll_tick_ms(bad), src

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
                    and not any(
                        k.arg == "tick_ms" and self._is_self_scroll_tick_ms(k.value)
                        for k in call.keywords
                    )
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


class TestSwapIntervalFloor:
    """Finding 1 of the #525 review: on a refresh-capped sign
    `SwapOnVSync(canvas, fraction)` blocks until the next multiple of
    `fraction` refreshes, so a nominal 35 ms loop really ticks at 50 ms.
    Banking the nominal 35 would run effects at 0.7×; the engine floors
    the banked tick at `frame.swap_interval_ms`."""

    async def test_capped_frame_banks_the_swap_interval_not_the_nominal(
        self, swapping_frame, no_sleep
    ):
        """35 ms nominal on a 50 ms swap interval → the plain path: one
        frame per scroll tick, carry untouched (parity with main)."""
        w = _Anim()
        swapping_frame.swap.return_value = _canvas()
        swapping_frame.swap_interval_ms = 50
        t = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0.035)
        assert t._scroll_tick_ms == 50
        await t._swap_and_scroll(_canvas(), w, hold_time=0, continuous=True)
        assert w._frame_count == 40
        assert w._frame_carry_ms == 0

    async def test_interval_below_nominal_leaves_nominal(
        self, swapping_frame, no_sleep
    ):
        """100 ms nominal on a 50 ms interval: the loop really ticks at
        100 ms, so it still banks 100 (2 frames per tick) — `max`, not a
        replacement."""
        w = _Anim()
        swapping_frame.swap.return_value = _canvas()
        swapping_frame.swap_interval_ms = 50
        t = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0.1)
        assert t._scroll_tick_ms == 100
        await t._swap_and_scroll(_canvas(), w, hold_time=0, continuous=True)
        assert w._frame_count == 80

    def test_mock_frame_has_no_floor(self, swapping_frame):
        """The Mock fixture answers `swap_interval_ms` with a Mock — the
        nominal tick must come through untouched (no TypeError, no floor)."""
        t = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0.02)
        assert t._scroll_tick_ms == 20


class TestEveryAdvanceFrameClassBanksElapsed:
    """Finding 2 of the #525 review: the engine dispatches
    `advance_frame_elapsed` by CLASS attribute, so a core class that defines
    its own `advance_frame` without `advance_frame_elapsed` silently falls
    back to one frame per scroll tick — a hole in the (1, 6) guarantee
    (`SegmentMessage`, a plugin export, had exactly that). Every class in
    `src/led_ticker/**` that defines `advance_frame` must also define
    `advance_frame_elapsed` or inherit `FrameAwareBase` (by base name)."""

    @staticmethod
    def _classes_defining(name: str):
        import pathlib

        import led_ticker

        root = pathlib.Path(led_ticker.__file__).parent
        found = []
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                methods = {
                    n.name
                    for n in node.body
                    if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
                }
                if name in methods:
                    bases = {
                        b.id if isinstance(b, ast.Name) else getattr(b, "attr", "")
                        for b in node.bases
                    }
                    found.append(
                        (path.relative_to(root).as_posix(), node, methods, bases)
                    )
        return found

    def test_advance_frame_definers_also_bank_elapsed(self):
        offenders = []
        for rel, node, methods, bases in self._classes_defining("advance_frame"):
            if "advance_frame_elapsed" in methods or "FrameAwareBase" in bases:
                continue
            offenders.append(f"{rel}:{node.lineno} {node.name}")
        assert not offenders, (
            "classes with their own advance_frame must also define "
            "advance_frame_elapsed (use _frame_aware.bank_frames) or inherit "
            f"FrameAwareBase, else scroll loops advance 1 frame/tick: {offenders}"
        )

    def test_scan_found_the_known_definers(self):
        names = {node.name for _, node, _, _ in self._classes_defining("advance_frame")}
        assert {"FrameAwareBase", "SegmentMessage"} <= names, names


class TestSegmentMessageCadence:
    def test_sub_frame_ticks_bank_to_wall_clock(self):
        """5 × 20 ms = 100 ms = 2 frames, not 5."""
        from led_ticker.colors import RGB_WHITE
        from led_ticker.widgets.message import SegmentMessage

        w = SegmentMessage([("A", RGB_WHITE)])
        for _ in range(5):
            w.advance_frame_elapsed(20)
        assert w._frame_count == 2
        assert w._frame_carry_ms == 0

    def test_slow_ticks_and_carry(self):
        from led_ticker.colors import RGB_WHITE
        from led_ticker.widgets.message import SegmentMessage

        w = SegmentMessage([("A", RGB_WHITE)])
        w.advance_frame_elapsed(60)
        w.advance_frame_elapsed(60)
        assert w._frame_count == 2
        assert w._frame_carry_ms == 20
        w.advance_frame_elapsed(100)
        assert w._frame_count == 4

    def test_non_positive_tick_is_one_frame(self):
        from led_ticker.colors import RGB_WHITE
        from led_ticker.widgets.message import SegmentMessage

        w = SegmentMessage([("A", RGB_WHITE)])
        w.advance_frame_elapsed(0)
        assert w._frame_count == 1

    def test_reset_clears_carry(self):
        from led_ticker.colors import RGB_WHITE
        from led_ticker.widgets.message import SegmentMessage

        w = SegmentMessage([("A", RGB_WHITE)])
        w.advance_frame_elapsed(40)
        w.reset_frame()
        w.advance_frame_elapsed(20)
        assert w._frame_count == 0
        assert w._frame_carry_ms == 20

    async def test_engine_dispatches_the_bank(self, swapping_frame, no_sleep):
        """End to end: a 20 ms marquee over 40 scroll ticks = 800 ms = 16
        frames on SegmentMessage, same as TickerMessage beside it."""
        from led_ticker.colors import RGB_WHITE
        from led_ticker.widgets.message import SegmentMessage

        w = SegmentMessage([("A" * 60, RGB_WHITE)])
        swapping_frame.swap.return_value = _canvas()
        t = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0.02)
        canvas = _canvas()
        _, cursor = w.draw(canvas)
        # constraint #7: stop_pos adds padding back, so the scroll runs
        # (cursor - width - padding) ticks.
        scroll_ticks = cursor - canvas.width - w.padding
        assert scroll_ticks > 0
        await t._swap_and_scroll(canvas, w, hold_time=0, continuous=True)
        assert w._frame_count == scroll_ticks * 20 // 50
        assert w._frame_count != scroll_ticks, "fell back to 1 frame/tick"


class TestBankFrames:
    def test_pure_helper(self):
        from led_ticker.widgets._frame_aware import bank_frames

        assert bank_frames(0, 50) == (1, 0)
        assert bank_frames(0, 20) == (0, 20)
        assert bank_frames(40, 20) == (1, 10)
        assert bank_frames(0, 100) == (2, 0)
        assert bank_frames(30, 120) == (3, 0)
