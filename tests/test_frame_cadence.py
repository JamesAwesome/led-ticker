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
from led_ticker.constants import MAX_SETTLE_MS
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


class TestHoldLoopPassesFlooredTick:
    """AST tripwire (cycle-2 finding 4): `_hold_ticks` is the ONE
    ENGINE_TICK_MS-paced advance site in the engine (the post-scroll hold
    and the settle seam route through it). Its advance must pass
    ``tick_ms=<local>`` where ``<local>`` is assigned IN `_hold_ticks` from
    exactly ``floor_tick_ms(self.frame, ENGINE_TICK_MS)`` — hoisted once,
    not re-evaluated per tick. (The scroll loops are pinned the other way
    round, to the per-tick property ``self._scroll_tick_ms``; both are
    equivalent because the swap interval is fixed after ``setup()`` — the
    two conventions are deliberate, don't "fix" one to match the other.)
    A bare `_advance_frame_if_supported(widget)` banks a flat 50 and reopens
    the 0.75× hold on a 30 Hz cap. Completeness: NO
    `_advance_frame_if_supported` call anywhere in ticker.py may omit
    `tick_ms=` — every loop is either scroll-paced (`self._scroll_tick_ms`)
    or hold-paced (the floored local)."""

    @staticmethod
    def _is_floor_of_engine_tick(value: ast.expr) -> bool:
        """Exactly `floor_tick_ms(self.frame, ENGINE_TICK_MS)`."""
        return (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "floor_tick_ms"
            and len(value.args) == 2
            and not value.keywords
            and isinstance(value.args[0], ast.Attribute)
            and value.args[0].attr == "frame"
            and isinstance(value.args[0].value, ast.Name)
            and value.args[0].value.id == "self"
            and isinstance(value.args[1], ast.Name)
            and value.args[1].id == "ENGINE_TICK_MS"
        )

    @classmethod
    def _floored_locals(cls, fn: ast.AST) -> set[str]:
        """Names bound at the function's top level (outside any loop) from
        the floor call."""
        names: set[str] = set()
        for stmt in getattr(fn, "body", []):
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and cls._is_floor_of_engine_tick(stmt.value)
            ):
                names.add(stmt.targets[0].id)
        return names

    @staticmethod
    def _function(tree: ast.AST, name: str) -> ast.AST:
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and node.name == name
            ):
                return node
        raise AssertionError(f"{name} not found in ticker.py")

    def test_predicate_accepts_only_the_exact_floor_call(self):
        """Guard the guard."""
        ok = ast.parse("floor_tick_ms(self.frame, ENGINE_TICK_MS)", mode="eval").body
        assert self._is_floor_of_engine_tick(ok)
        for src in (
            "floor_tick_ms(self.frame, 50)",
            "floor_tick_ms(frame, ENGINE_TICK_MS)",
            "floor_tick_ms(self.frame, self._scroll_tick_ms)",
            "self.frame.swap_interval_ms",
            "ENGINE_TICK_MS",
            "max(ENGINE_TICK_MS, self.frame.swap_interval_ms)",
        ):
            assert not self._is_floor_of_engine_tick(
                ast.parse(src, mode="eval").body
            ), src

    def test_hoisted_local_is_found_only_outside_loops(self):
        """Guard the guard: a per-tick assignment inside the loop body is
        NOT accepted (the floor is hoisted once)."""
        hoisted = ast.parse(
            "def f(self):\n"
            "    tick = floor_tick_ms(self.frame, ENGINE_TICK_MS)\n"
            "    for _ in x:\n"
            "        pass\n"
        ).body[0]
        assert self._floored_locals(hoisted) == {"tick"}
        per_tick = ast.parse(
            "def f(self):\n"
            "    for _ in x:\n"
            "        tick = floor_tick_ms(self.frame, ENGINE_TICK_MS)\n"
        ).body[0]
        assert self._floored_locals(per_tick) == set()

    def test_hold_ticks_advances_by_the_hoisted_floored_tick(self):
        tree = ast.parse(inspect.getsource(ticker_mod))
        fn = self._function(tree, "_hold_ticks")
        floored = self._floored_locals(fn)
        assert floored, (
            "_hold_ticks must hoist floor_tick_ms(self.frame, ENGINE_TICK_MS)"
        )
        calls = [
            call
            for call in ast.walk(fn)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "_advance_frame_if_supported"
        ]
        assert calls, "_hold_ticks lost its advance call"
        for call in calls:
            kw = [k for k in call.keywords if k.arg == "tick_ms"]
            assert kw, f"ticker.py:{call.lineno}: _hold_ticks advance omits tick_ms="
            value = kw[0].value
            assert isinstance(value, ast.Name) and value.id in floored, (
                f"ticker.py:{call.lineno}: tick_ms must be the hoisted "
                f"floor_tick_ms(self.frame, ENGINE_TICK_MS) local, got "
                f"{ast.unparse(value)}"
            )

    def test_no_advance_site_in_the_engine_omits_tick_ms(self):
        tree = ast.parse(inspect.getsource(ticker_mod))
        offenders = [
            f"ticker.py:{call.lineno}"
            for call in ast.walk(tree)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "_advance_frame_if_supported"
            and not any(k.arg == "tick_ms" for k in call.keywords)
        ]
        assert not offenders, (
            "every engine advance must bank the wall clock its loop really "
            f"ticks at — pass tick_ms= at {offenders}"
        )


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


class TestScrollTickMsIsTheConfiguredMs:
    """Cycle-2 finding 3: `scroll_speed` is `scroll_step_ms / 1000` and the
    product `scroll_speed * 1000` is not always exact in binary — `int()`
    truncates 1.001 * 1000 = 1000.9999… to 1000 (and 2.002 → 2001, 4.007 →
    4006), so the tick must be `round()`ed back to the configured ms."""

    @pytest.mark.parametrize("ms", [29, 1001, 2002, 4007, 4999])
    def test_scroll_tick_ms_is_the_configured_ms(self, swapping_frame, ms):
        t = Ticker(monitors=[], frame=swapping_frame, scroll_speed=ms / 1000)
        assert t._scroll_tick_ms == ms


@attrs.define
class _Settling(_Anim):
    """Frame-aware widget that always asks the settle seam for *owed*
    more frames (constant, so the tick arithmetic is the only variable)."""

    owed: int = 10

    def frames_to_transition_ready(self) -> int:
        return self.owed


class TestHoldLoopFloorsAtSwapInterval:
    """Cycle-2 finding 4: the ENGINE_TICK_MS-paced loops (`_hold_ticks`, and
    through it `_scroll_and_delay`'s post-scroll hold and the settle seam)
    ALSO really tick at the swap interval on a refresh-capped sign — 67 ms
    at 30 Hz, 55 at 110 — so banking a flat 50 per tick ran held effects at
    0.75–0.95×. The hold loop banks `floor_tick_ms(frame, ENGINE_TICK_MS)`
    so the (1, 6) "every core loop" guarantee is true as written."""

    async def test_capped_frame_banks_the_swap_interval(self, swapping_frame, no_sleep):
        """10 ticks × 67 ms = 670 ms = 13 frames + 20 ms carry, not 10."""
        w = _Anim(cursor=5)
        swapping_frame.swap.return_value = _canvas()
        swapping_frame.swap_interval_ms = 67
        t = Ticker(monitors=[], frame=swapping_frame)
        await t._hold_ticks(_canvas(), w, 10, 0, None)
        assert w.draws == 10, "the tick count / sleep cadence must not change"
        assert w._frame_count == 13
        assert w._frame_carry_ms == 20

    async def test_interval_below_the_engine_tick_is_one_frame_per_tick(
        self, swapping_frame, no_sleep
    ):
        """A 25 Hz cap swaps every 40 ms — shorter than the 50 ms hold tick,
        so the loop still really ticks at 50: `max`, not a replacement (a
        mutant that passes the raw interval instead of the floored nominal
        banks 40 and delivers 8 frames)."""
        w = _Anim(cursor=5)
        swapping_frame.swap.return_value = _canvas()
        swapping_frame.swap_interval_ms = 40
        t = Ticker(monitors=[], frame=swapping_frame)
        await t._hold_ticks(_canvas(), w, 10, 0, None)
        assert w._frame_count == 10
        assert w._frame_carry_ms == 0

    async def test_duck_typed_widget_keeps_one_frame_per_tick(
        self, swapping_frame, no_sleep
    ):
        w = _LegacyAdvance()
        swapping_frame.swap.return_value = _canvas()
        swapping_frame.swap_interval_ms = 67
        t = Ticker(monitors=[], frame=swapping_frame)
        await t._hold_ticks(_canvas(), w, 10, 0, None)
        assert w.advances == 10

    async def test_post_scroll_hold_inherits_the_floor(self, swapping_frame, no_sleep):
        """`_scroll_and_delay` at pos 0 is pure hold: 0.5 s = 10 ticks."""
        w = _Anim(cursor=5)
        swapping_frame.swap.return_value = _canvas()
        swapping_frame.swap_interval_ms = 67
        t = Ticker(monitors=[], frame=swapping_frame)
        await t._scroll_and_delay(_canvas(), w, delay=0.5, cursor_pos=0)
        assert w._frame_count == 13


class TestSettleConvertsFramesToFlooredTicks:
    """The settle seam asks the widget for FRAMES and used to hand them to
    `_hold_ticks` as TICKS — exact while a hold tick was one frame. On a
    capped frame the hold banks 67 per tick, so 10 ticks would overshoot
    the rest point (13 frames). Mirror the image loops' `_settle_ticks`:
    `ceil((frames × 50 − banked carry) / hold_tick_ms)` ticks, refused when
    a tick is longer than MAX_SETTLE_MS or would START at or past it (#570: the
    last tick may cross the line; refusing the delivered total dropped every
    top-of-budget settle on an interval that does not divide 1000)."""

    async def test_uncapped_frame_holds_one_tick_per_frame(
        self, swapping_frame, no_sleep
    ):
        """Parity: cursor 5 fits, hold 0.05 s = 1 tick, then 10 settle
        ticks → entry draw + 1 + 10 draws, 11 frames."""
        w = _Settling(cursor=5, owed=10)
        swapping_frame.swap.return_value = _canvas()
        t = Ticker(monitors=[], frame=swapping_frame)
        await t._swap_and_scroll(_canvas(), w, hold_time=0.05)
        assert w.draws == 12
        assert w._frame_count == 11

    async def test_capped_frame_converts_owed_frames_into_ticks(
        self, swapping_frame, no_sleep
    ):
        """After the 1-tick hold (67 banked → 1 frame, carry 17) the widget
        owes 10 frames = 500 ms − 17 carry = 483 ms → ceil(483 / 67) = 8
        ticks (not 10), which bank 536 → 11 frames: the rest point (11)
        plus the sub-tick ceil remainder, never the 13-frame overshoot."""
        w = _Settling(cursor=5, owed=10)
        swapping_frame.swap.return_value = _canvas()
        swapping_frame.swap_interval_ms = 67
        t = Ticker(monitors=[], frame=swapping_frame)
        await t._swap_and_scroll(_canvas(), w, hold_time=0.05)
        assert w.draws == 1 + 1 + 8
        assert w._frame_count == 12

    async def test_nothing_owed_on_a_capped_frame_is_no_extension(
        self, swapping_frame, no_sleep
    ):
        """A widget already at rest (0 owed frames) must get no settle tick
        on a capped frame either: the `max(1, …)` floor on the owed ms must
        never turn a zero debt into a 67 ms hold (cycle-3 mutant: guard
        `0 < frames` → `0 <= frames` survived)."""
        w = _Settling(cursor=5, owed=0)
        swapping_frame.swap.return_value = _canvas()
        swapping_frame.swap_interval_ms = 67
        t = Ticker(monitors=[], frame=swapping_frame)
        await t._swap_and_scroll(_canvas(), w, hold_time=0.05)
        assert w.draws == 2  # entry draw + the 1-tick hold, no settle

    async def test_tick_longer_than_the_budget_is_refused(
        self, swapping_frame, no_sleep
    ):
        """20 frames (the MAX_SETTLE_TICKS edge) = 1000 ms owed; on a
        2000 ms swap interval even one tick would hold the panel 2 s, so
        the extension is refused outright (all-or-nothing)."""
        w = _Settling(cursor=5, owed=20)
        swapping_frame.swap.return_value = _canvas()
        swapping_frame.swap_interval_ms = 2000
        t = Ticker(monitors=[], frame=swapping_frame)
        await t._swap_and_scroll(_canvas(), w, hold_time=0.05)
        assert w.draws == 2  # entry draw + the 1-tick hold, no settle

    async def test_duck_typed_widget_keeps_one_tick_per_frame(
        self, swapping_frame, no_sleep
    ):
        """A widget without `advance_frame_elapsed` advances one frame per
        hold tick whatever the interval, so its settle must NOT be
        converted (it would undershoot the rest point)."""

        class _LegacySettling(_LegacyAdvance):
            def draw(self, canvas, cursor_pos=0, **kwargs):
                self.draws += 1
                return canvas, 5

            def frames_to_transition_ready(self) -> int:
                return 10

        w = _LegacySettling()
        swapping_frame.swap.return_value = _canvas()
        swapping_frame.swap_interval_ms = 67
        t = Ticker(monitors=[], frame=swapping_frame)
        await t._swap_and_scroll(_canvas(), w, hold_time=0.05)
        assert w.advances == 1 + 10

    async def test_banked_carry_is_subtracted_from_the_owed_time(
        self, swapping_frame, no_sleep
    ):
        """The 1-tick hold leaves 17 ms banked; 3 owed frames = 150 ms −
        17 = 133 → ceil(133 / 67) = 2 ticks (3 without the carry term),
        which bank 134 + 17 = 151 → exactly the 3 frames owed."""
        w = _Settling(cursor=5, owed=3)
        swapping_frame.swap.return_value = _canvas()
        swapping_frame.swap_interval_ms = 67
        t = Ticker(monitors=[], frame=swapping_frame)
        await t._swap_and_scroll(_canvas(), w, hold_time=0.05)
        assert w.draws == 1 + 1 + 2
        assert w._frame_count == 1 + 3

    async def test_last_tick_may_end_exactly_at_the_budget(
        self, swapping_frame, no_sleep
    ):
        """20 frames = 1000 ms owed on a 100 ms interval → 10 ticks ×
        100 = exactly MAX_SETTLE_MS: granted (the last tick starts at 900)."""
        w = _Settling(cursor=5, owed=20)
        swapping_frame.swap.return_value = _canvas()
        swapping_frame.swap_interval_ms = 100
        t = Ticker(monitors=[], frame=swapping_frame)
        await t._swap_and_scroll(_canvas(), w, hold_time=0.05)
        assert w.draws == 1 + 1 + 10
        assert w._frame_count == 2 + 20

    async def test_top_of_budget_at_the_30_hz_swap_interval_is_granted(
        self, swapping_frame, no_sleep
    ):
        """#570: 20 owed frames at a 67 ms interval. The 1-tick hold banks
        67 (1 frame, carry 17) → 983 ms owed → 15 ticks = 1005 ms. The
        strict delivered check refused this for EVERY carry (14 × 67 = 938
        is the most that fits under 1000), so a 30 Hz-capped sign could
        never settle a 20-frame `frames_to_rest`; the last tick starts at
        938 < 1000, so it is granted."""
        w = _Settling(cursor=5, owed=20)
        swapping_frame.swap.return_value = _canvas()
        swapping_frame.swap_interval_ms = 67
        t = Ticker(monitors=[], frame=swapping_frame)
        await t._swap_and_scroll(_canvas(), w, hold_time=0.05)
        assert w.draws == 1 + 1 + 15
        assert w._frame_count == 67 * (1 + 15) // 50  # 21: rest (21) reached

    async def test_top_of_budget_at_a_110_hz_swap_interval_is_granted(
        self, swapping_frame, no_sleep
    ):
        """Second non-dividing interval (55 ms at 110 Hz): hold banks 55
        (carry 5) → 995 owed → 19 ticks = 1045 ms; the last starts at 990."""
        w = _Settling(cursor=5, owed=20)
        swapping_frame.swap.return_value = _canvas()
        swapping_frame.swap_interval_ms = 55
        t = Ticker(monitors=[], frame=swapping_frame)
        await t._swap_and_scroll(_canvas(), w, hold_time=0.05)
        assert w.draws == 1 + 1 + 19
        assert w._frame_count == 55 * (1 + 19) // 50  # 22

    def test_tick_boundary_is_strictly_longer_than_the_budget(self, swapping_frame):
        """A 1000 ms tick owing one frame is one tick starting at 0 →
        granted; 1001 ms can't start any tick inside the budget → 0."""
        w = _Settling(cursor=5, owed=1)
        t = Ticker(monitors=[], frame=swapping_frame)
        swapping_frame.swap_interval_ms = MAX_SETTLE_MS
        assert t._settle_hold_ticks(w, 1) == 1
        swapping_frame.swap_interval_ms = MAX_SETTLE_MS + 1
        assert t._settle_hold_ticks(w, 1) == 0

    def test_negative_third_party_carry_cannot_start_a_tick_at_or_past_the_line(
        self, swapping_frame
    ):
        """The engine reads `_frame_carry_ms` off the widget by getattr. In
        tree `bank_frames` keeps it in [0, 49], so this state is
        unreachable for FrameAwareBase / SegmentMessage; a third-party
        class defining `advance_frame_elapsed` with its own carry could
        hand over a negative one, inflating the owed time past
        MAX_SETTLE_MS. The start clause is the backstop, and refusing (not
        clamping) is the pinned choice — no extension is the safe outcome
        for a bogus carry. 20 frames − (−100) = 1100 → 17 ticks at 67 ms,
        tick 17 would start at 1072 → 0. Boundary: at 100 ms with carry
        −50 the 11th tick would start exactly AT 1000 → also 0 (`>=`)."""
        w = _Settling(cursor=5, owed=20)
        w._frame_carry_ms = -100
        swapping_frame.swap_interval_ms = 67
        t = Ticker(monitors=[], frame=swapping_frame)
        assert t._settle_hold_ticks(w, 20) == 0
        w._frame_carry_ms = -50
        swapping_frame.swap_interval_ms = 100
        assert t._settle_hold_ticks(w, 20) == 0

    def test_wide_interval_overshoot_is_a_recorded_choice(self, swapping_frame):
        """Engine twin of the image pin: a 600 ms interval owing 20 frames
        → 2 ticks = 1200 ms (the second starts at 600 < 1000). Reachable
        only with `limit_refresh_rate_hz <= 4`; pinned so a tighter rule
        is deliberate."""
        w = _Settling(cursor=5, owed=20)
        swapping_frame.swap_interval_ms = 600
        t = Ticker(monitors=[], frame=swapping_frame)
        assert t._settle_hold_ticks(w, 20) == 2


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
    def test_routes_through_advance_frame(self):
        """Every banked frame goes through `advance_frame`, so a subclass
        override (the `FrameAwareBase` contract, promised by the docstring)
        sees each one — a `_frame_count += frames` shortcut would skip it
        (cycle-4 mutant survived without it)."""
        from led_ticker.colors import RGB_WHITE
        from led_ticker.widgets.message import SegmentMessage

        seen: list[int | None] = []

        class _Spy(SegmentMessage):
            def advance_frame(self, *, visit_id: int | None = None) -> None:
                seen.append(visit_id)
                super().advance_frame(visit_id=visit_id)

        w = _Spy([("A", RGB_WHITE)])
        w.advance_frame_elapsed(100, visit_id=7)
        w.advance_frame_elapsed(20, visit_id=7)
        w.advance_frame_elapsed(30, visit_id=7)
        assert seen == [7, 7, 7]
        assert w._frame_count == 3

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
