"""Section-level schedule gate + all-dark idle in the run loop."""

import asyncio
import logging
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

from led_ticker.app.run import (
    _cycle_dark_canvas,
    _idle_when_all_scheduled_out,
    _on_display_dark_transition,
    _section_has_content,
    _section_schedule_active,
)
from led_ticker.schedule import VisibilitySchedule, bind_schedule


class _Active:
    def is_active(self):
        return True


class _Inactive:
    def is_active(self):
        return False


class _Boom:
    def is_active(self):
        raise RuntimeError("boom")


class TestSectionScheduleActive:
    def test_no_schedule_is_active(self):
        assert _section_schedule_active(SimpleNamespace(schedule=None)) is True

    def test_active(self):
        assert _section_schedule_active(SimpleNamespace(schedule=_Active())) is True

    def test_inactive(self):
        assert _section_schedule_active(SimpleNamespace(schedule=_Inactive())) is False

    def test_raising_keeps_section(self):
        assert _section_schedule_active(SimpleNamespace(schedule=_Boom())) is True


def _frame():
    frame = Mock()
    frame.get_clean_canvas.return_value = Mock(name="canvas")
    frame.swap.return_value = Mock(name="back_buffer")
    return frame


class TestCycleDarkCanvas:
    """Fix 3 (deep-dive-2, 2026-07-15): the extracted Clear+swap step shared
    by `_idle_when_all_scheduled_out` and run()'s empty-playlist-while-dark
    branch."""

    def test_clears_then_swaps_and_returns_swap_result(self):
        frame = _frame()
        canvas = Mock(name="dark_canvas")
        order = []
        canvas.Clear.side_effect = lambda: order.append("clear")

        def _fake_swap(c):
            order.append("swap")
            return frame.swap.return_value

        frame.swap.side_effect = _fake_swap

        result = _cycle_dark_canvas(frame, canvas)

        assert order == ["clear", "swap"]
        frame.swap.assert_called_once_with(canvas)
        assert result is frame.swap.return_value


class TestIdleWhenAllScheduledOut:
    def test_sections_ran_resets_dark(self, caplog):
        """Waking preserves whatever canvas was retained — it must NOT be
        nulled out, or the next dark episode would re-fetch and defeat the
        process-lifetime retention (the leak-guard fix)."""
        frame = _frame()
        existing_canvas = Mock(name="existing_dark_canvas")
        with caplog.at_level(logging.INFO):
            dark, dark_canvas, dark_streak = asyncio.run(
                _idle_when_all_scheduled_out(frame, True, True, existing_canvas, 3)
            )
        assert dark is False
        assert dark_canvas is existing_canvas
        assert dark_streak == 0
        assert "panel waking" in caplog.text
        frame.get_clean_canvas.assert_not_called()
        frame.swap.assert_not_called()

    def test_sections_ran_stays_quiet_when_not_dark(self, caplog):
        with caplog.at_level(logging.INFO):
            dark, dark_canvas, dark_streak = asyncio.run(
                _idle_when_all_scheduled_out(_frame(), True, False, None, 0)
            )
        assert dark is False
        assert dark_canvas is None
        assert dark_streak == 0
        assert caplog.text == ""

    def test_second_consecutive_out_cycle_blanks_once_and_logs(
        self, caplog, monkeypatch
    ):
        """The dark path (fetch + blank + log) only runs once the debounce
        has already registered one prior all-out cycle (`dark_streak == 1`,
        i.e. this is the SECOND consecutive out cycle)."""
        slept = []

        async def _fake_sleep(s):
            slept.append(s)

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
        frame = _frame()
        with caplog.at_level(logging.INFO):
            dark, dark_canvas, dark_streak = asyncio.run(
                _idle_when_all_scheduled_out(frame, False, False, None, 1)
            )
        assert dark is True
        assert dark_streak == 2
        frame.get_clean_canvas.assert_called_once()
        frame.get_clean_canvas.return_value.Clear.assert_called_once()
        frame.swap.assert_called_once_with(frame.get_clean_canvas.return_value)
        assert dark_canvas is frame.swap.return_value
        assert "panel dark" in caplog.text
        assert slept == [1.0]

    def test_already_dark_reswaps_every_iteration(self, caplog, monkeypatch):
        """Fix B (2026-07-15): the dark path must keep swapping a canvas
        every iteration (not just once at the dark transition) so overlay
        hooks (busy_light) keep compositing and the status board's
        swap_count liveness counter keeps advancing all night. Logging
        stays transition-only — quiet here since already dark. Fix
        (2026-07-15, HIGH): the canvas being re-swapped must be the SAME
        one threaded in via `dark_canvas` — `get_clean_canvas` must NOT be
        called again, or the real backend leaks a native framebuffer every
        tick."""
        slept = []

        async def _fake_sleep(s):
            slept.append(s)

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
        frame = _frame()
        existing_canvas = Mock(name="existing_dark_canvas")
        with caplog.at_level(logging.INFO):
            dark, dark_canvas, dark_streak = asyncio.run(
                _idle_when_all_scheduled_out(frame, False, True, existing_canvas, 7)
            )
        assert dark is True
        assert dark_streak == 8
        frame.get_clean_canvas.assert_not_called()
        existing_canvas.Clear.assert_called_once()
        frame.swap.assert_called_once_with(existing_canvas)
        assert dark_canvas is frame.swap.return_value
        assert caplog.text == ""
        assert slept == [1.0]

    def test_clear_runs_before_swap_each_iteration(self, monkeypatch):
        """Requirement: the dark canvas is Cleared before it's handed to
        swap() — Clear erases whatever an overlay hook painted onto this
        same buffer two swaps ago so it doesn't accumulate."""

        async def _fake_sleep(s):
            pass

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
        frame = _frame()
        canvas = frame.get_clean_canvas.return_value
        order = []
        canvas.Clear.side_effect = lambda: order.append("clear")

        def _fake_swap(c):
            order.append("swap")
            return frame.swap.return_value

        frame.swap.side_effect = _fake_swap
        # dark_streak=1: already past the debounce, so this call runs the
        # actual dark path (fetch + clear + swap).
        asyncio.run(_idle_when_all_scheduled_out(frame, False, False, None, 1))
        assert order == ["clear", "swap"]

    def test_dark_canvas_cycles_through_swap_chain_no_leak(self, monkeypatch):
        """The point of this fix (HIGH, real-hardware memory leak):
        get_clean_canvas is the ONLY allocation for the life of the process
        (see TestDarkCanvasProcessLifetimeRetention below for the
        multi-episode proof). Across N consecutive dark iterations (after
        the initial debounce cycle), swap is called once per iteration and
        each swap's argument is the PREVIOUS swap's return value — the
        double buffer cycles through the swap chain (mirroring the
        `swapping_frame` double-buffer contract in tests/conftest.py)
        instead of a fresh framebuffer being allocated every second."""

        async def _fake_sleep(s):
            pass

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

        frame = Mock()
        initial_canvas = Mock(name="clean_canvas")
        frame.get_clean_canvas.return_value = initial_canvas
        frame.swap.side_effect = lambda c: Mock(name="swapped")

        n = 5  # 1 debounce cycle + 4 real dark iterations
        returned_canvases = []
        swap_call_args = []
        dark_canvas = None
        was_dark = False
        dark_streak = 0
        prev_swap_count = 0
        for _ in range(n):
            was_dark, dark_canvas, dark_streak = asyncio.run(
                _idle_when_all_scheduled_out(
                    frame, False, was_dark, dark_canvas, dark_streak
                )
            )
            if frame.swap.call_count > prev_swap_count:
                swap_call_args.append(frame.swap.call_args.args[0])
                prev_swap_count = frame.swap.call_count
            returned_canvases.append(dark_canvas)

        assert frame.get_clean_canvas.call_count == 1
        assert frame.swap.call_count == n - 1  # first cycle was the debounce
        # First return (the debounce cycle) is None; real dark iterations
        # start at index 1.
        assert returned_canvases[0] is None
        assert swap_call_args[0] is initial_canvas
        for i in range(1, len(swap_call_args)):
            assert swap_call_args[i] is returned_canvases[i]


class TestDebounceGoingDark:
    """Fix 1 (deep-dive-2, 2026-07-15): a config whose only section flaps
    content on/off between polls must not retain one native framebuffer per
    flap. The panel only commits to the dark state (fetch + blank + log) on
    the SECOND consecutive all-out cycle."""

    def test_flap_sequence_never_calls_get_clean_canvas(self, monkeypatch):
        """ran -> out -> ran -> out -> ... (never two consecutive `out`s in
        a row) must never fetch a clean canvas — every `out` cycle is a
        fresh debounce (dark_streak resets to 0 on every `ran`)."""

        async def _fake_sleep(s):
            pass

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
        frame = _frame()
        was_dark = False
        dark_canvas = None
        dark_streak = 0
        for i in range(20):
            any_section_ran = i % 2 == 0  # ran, out, ran, out, ...
            was_dark, dark_canvas, dark_streak = asyncio.run(
                _idle_when_all_scheduled_out(
                    frame, any_section_ran, was_dark, dark_canvas, dark_streak
                )
            )
            assert was_dark is False
        frame.get_clean_canvas.assert_not_called()
        frame.swap.assert_not_called()

    def test_two_consecutive_out_cycles_fetch_and_blank_once(self, caplog):
        """Exactly one fetch + blank + dark log, on the SECOND consecutive
        all-out cycle — not the first."""
        frame = _frame()
        with caplog.at_level(logging.INFO):
            dark1, dark_canvas1, streak1 = asyncio.run(
                _idle_when_all_scheduled_out(frame, False, False, None, 0)
            )
            first_cycle_log = caplog.text

            # First cycle: debounce only — checked BEFORE the second call
            # runs, since both calls share the same frame mock.
            assert dark1 is False
            assert dark_canvas1 is None
            assert streak1 == 1
            assert first_cycle_log == ""
            frame.get_clean_canvas.assert_not_called()
            frame.swap.assert_not_called()

            caplog.clear()
            dark2, dark_canvas2, streak2 = asyncio.run(
                _idle_when_all_scheduled_out(frame, False, dark1, dark_canvas1, streak1)
            )
            second_cycle_log = caplog.text

        # Second cycle: the real dark transition.
        assert dark2 is True
        assert streak2 == 2
        frame.get_clean_canvas.assert_called_once()
        frame.swap.assert_called_once_with(frame.get_clean_canvas.return_value)
        assert "panel dark" in second_cycle_log

    def test_debounce_cycle_still_sleeps(self, monkeypatch):
        slept = []

        async def _fake_sleep(s):
            slept.append(s)

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
        dark, dark_canvas, dark_streak = asyncio.run(
            _idle_when_all_scheduled_out(_frame(), False, False, None, 0)
        )
        assert dark is False
        assert dark_canvas is None
        assert dark_streak == 1
        assert slept == [1.0]


class TestDarkCanvasProcessLifetimeRetention:
    """Cycle-3 review Fix 1: the leak guard is process-lifetime canvas
    retention, not per-episode. `get_clean_canvas` must be fetched AT MOST
    ONCE for the life of the process, no matter how many dark<->wake
    episodes happen — the debounce alone only covers a 1-cycle flap; a
    config that stays all-out for many consecutive cycles per episode (e.g.
    a slow-polling Container) would otherwise still leak one retained
    framebuffer per episode."""

    def test_dark_wake_dark_across_two_episodes_fetches_once(self, monkeypatch):
        async def _fake_sleep(s):
            pass

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

        frame = Mock()
        initial_canvas = Mock(name="clean_canvas")
        frame.get_clean_canvas.return_value = initial_canvas
        swapped = []

        def _fake_swap(c):
            new = Mock(name=f"swapped_{len(swapped)}")
            swapped.append(new)
            return new

        frame.swap.side_effect = _fake_swap

        was_dark = False
        dark_canvas = None
        dark_streak = 0

        # Episode 1: debounce no-op, then commit (fetch #1).
        was_dark, dark_canvas, dark_streak = asyncio.run(
            _idle_when_all_scheduled_out(
                frame, False, was_dark, dark_canvas, dark_streak
            )
        )
        was_dark, dark_canvas, dark_streak = asyncio.run(
            _idle_when_all_scheduled_out(
                frame, False, was_dark, dark_canvas, dark_streak
            )
        )
        assert was_dark is True
        assert frame.get_clean_canvas.call_count == 1
        episode_1_canvas = dark_canvas

        # Wake: canvas must be preserved, not dropped.
        was_dark, dark_canvas, dark_streak = asyncio.run(
            _idle_when_all_scheduled_out(
                frame, True, was_dark, dark_canvas, dark_streak
            )
        )
        assert was_dark is False
        assert dark_canvas is episode_1_canvas
        assert dark_streak == 0

        # Episode 2: debounce no-op, then commit again — must REUSE the
        # retained canvas, not re-fetch.
        was_dark, dark_canvas, dark_streak = asyncio.run(
            _idle_when_all_scheduled_out(
                frame, False, was_dark, dark_canvas, dark_streak
            )
        )
        was_dark, dark_canvas, dark_streak = asyncio.run(
            _idle_when_all_scheduled_out(
                frame, False, was_dark, dark_canvas, dark_streak
            )
        )
        assert was_dark is True
        assert frame.get_clean_canvas.call_count == 1, (
            "get_clean_canvas must be fetched exactly once for the life of "
            "the process, regardless of how many dark/wake episodes occur"
        )
        # The second episode still cycles the swap chain from wherever the
        # first episode's retained canvas left off.
        assert dark_canvas is swapped[-1]

    def test_multi_cycle_flap_fetches_once(self, monkeypatch):
        """A flap pattern with runs LONGER than the 1-cycle debounce (out,
        out, ran, out, out, ran, ...) must still fetch exactly once, total,
        across the whole run — the debounce alone can't cover this (each
        run is 2 all-out cycles wide, so every episode commits to dark),
        only the process-lifetime retention does."""

        async def _fake_sleep(s):
            pass

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

        frame = Mock()
        frame.get_clean_canvas.return_value = Mock(name="clean_canvas")
        frame.swap.side_effect = lambda c: Mock(name="swapped")

        was_dark = False
        dark_canvas = None
        dark_streak = 0
        pattern = [False, False, True] * 5  # out, out, ran, repeated
        for any_section_ran in pattern:
            was_dark, dark_canvas, dark_streak = asyncio.run(
                _idle_when_all_scheduled_out(
                    frame, any_section_ran, was_dark, dark_canvas, dark_streak
                )
            )
        assert frame.get_clean_canvas.call_count == 1


class TestOnDisplayDarkTransition:
    """Fix A (2026-07-15): the False->True (panel just went dark) transition
    must reset outgoing-transition tracking state, so the morning wake's
    entry transition doesn't draw yesterday evening's last_widget at full
    brightness as the outgoing frame."""

    def test_wake_to_dark_returns_reset_triple(self):
        assert _on_display_dark_transition(False, True) == (None, 0, None)

    def test_still_dark_returns_none(self):
        # was_dark=True, now_dark=True: no transition, no reset.
        assert _on_display_dark_transition(True, True) is None

    def test_dark_to_wake_returns_none(self):
        # was_dark=True, now_dark=False: waking, not going dark — no reset
        # (the widget currently active IS the correct outgoing content).
        assert _on_display_dark_transition(True, False) is None

    def test_never_dark_returns_none(self):
        assert _on_display_dark_transition(False, False) is None


class _Widget:
    """Weakref-able stand-in for a built widget (bind_schedule keys off id())."""


class _FakeContainer:
    """Minimal Container Protocol implementer (feed_stories attribute)."""

    def __init__(self, stories):
        self.feed_stories = list(stories)


class _InactiveSchedule:
    def is_active(self, now=None):
        return False


class TestSectionHasContent:
    """Fix 1 (2026-07-15): a section with NO section-level schedule can still
    have nothing to show if every widget is individually scheduled out (or a
    Container is currently empty). The caller must NOT mark the section as
    "ran" in that case — the panel must blank + idle via
    `_idle_when_all_scheduled_out`, not keep its last drawn frame while the
    outer loop busy-spins."""

    def test_title_always_counts_as_content(self):
        # A title counts as content even with zero widgets, or with widgets
        # that would otherwise expand to nothing.
        has_content, expanded = _section_has_content("News", [], None)
        assert has_content is True
        assert expanded == []

    def test_title_wins_even_with_inactive_widgets(self):
        widget = _Widget()
        bind_schedule(widget, cast(VisibilitySchedule, _InactiveSchedule()))
        has_content, _ = _section_has_content("News", [widget], None)
        assert has_content is True

    def test_no_title_no_widgets_is_empty(self):
        has_content, expanded = _section_has_content(None, [], None)
        assert has_content is False
        assert expanded == []

    def test_no_title_active_widgets_is_content(self):
        widget = _Widget()
        has_content, expanded = _section_has_content(None, [widget], None)
        assert has_content is True
        assert expanded == [widget]

    def test_no_title_all_widgets_schedule_inactive_is_empty(self):
        """The widget-level all-scheduled-out case this fix closes: no
        section-level schedule, but every widget's OWN `schedule = {...}`
        is currently inactive."""
        widget = _Widget()
        bind_schedule(widget, cast(VisibilitySchedule, _InactiveSchedule()))
        has_content, expanded = _section_has_content(None, [widget], None)
        assert has_content is False
        assert expanded == []

    def test_no_title_empty_container_is_empty(self):
        """Boot-time empty container: a Container with zero feed_stories
        (e.g. an RSS feed before its first successful poll) and no section
        title yields no content — must recover, not busy-spin or freeze."""
        container = _FakeContainer([])
        has_content, expanded = _section_has_content(None, [container], None)
        assert has_content is False
        assert expanded == []

    def test_recovers_once_container_gets_stories(self):
        """Same container object, re-evaluated after its background update()
        task populates feed_stories — content decision flips True without
        rebuilding the widget."""
        container = _FakeContainer([])
        before, _ = _section_has_content(None, [container], None)
        assert before is False

        container.feed_stories = ["headline"]
        after, expanded = _section_has_content(None, [container], None)
        assert after is True
        assert expanded == ["headline"]

    def test_reuses_expanded_result_no_double_expand(self, monkeypatch):
        """The caller (`app.run`'s section loop) reuses the returned
        `expanded` list for `first_widget` instead of calling
        `_expand_sources` a second time — guard the call count here.

        Fetched via `importlib` (not `import led_ticker.app.run as x`):
        `led_ticker.app.__init__` does `from led_ticker.app.run import run`,
        which rebinds the `run` ATTRIBUTE on the `led_ticker.app` package to
        the function — a plain `import ... as` walks that shadowed
        attribute and would hand back the function, not the submodule.
        """
        import importlib

        run_mod = importlib.import_module("led_ticker.app.run")

        calls = []
        real_expand = run_mod._expand_sources

        def counting_expand(sources, breaker=None):
            calls.append(sources)
            return real_expand(sources, breaker)

        monkeypatch.setattr(run_mod, "_expand_sources", counting_expand)
        widget = _Widget()
        _section_has_content(None, [widget], None)
        assert len(calls) == 1


def test_run_py_section_loop_does_not_double_expand():
    """Source-level guard: the section loop must call
    `_expand_sources(widgets, ...)` exactly twice in `run.py` — once inside
    `_section_has_content` (reused for both the content decision AND
    `first_widget`) and once later when tracking `last_widget` after the
    ticker run (a deliberately separate point in time, since the widget
    rotation may have changed while the ticker ran). A regression that
    reintroduces a second `_expand_sources` call just for `first_widget`
    would push this count to 3."""
    import importlib
    import inspect

    run_mod = importlib.import_module("led_ticker.app.run")

    src = inspect.getsource(run_mod)
    assert src.count("_expand_sources(widgets,") == 2


class TestWidgetLevelAllOutIdleWiring:
    """Integration-ish test of the composed contract the outer `run()` loop
    relies on: a section pass with no section-level schedule but every
    widget scheduled out must flow `_section_has_content` -> False all the
    way through to `_idle_when_all_scheduled_out` blanking + idling — the
    same as the pre-existing section-level gate — instead of leaving
    `_any_section_ran = True` and the panel on its last drawn frame."""

    def test_all_widgets_scheduled_out_drives_blank_and_idle(self, caplog, monkeypatch):
        slept = []

        async def _fake_sleep(s):
            slept.append(s)

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

        widget = _Widget()
        bind_schedule(widget, cast(VisibilitySchedule, _InactiveSchedule()))

        # What the section loop does this pass: no title, one widget, all
        # scheduled out -> _any_section_ran stays False for this section.
        has_content, _expanded = _section_has_content(None, [widget], None)
        any_section_ran = has_content  # single-section playlist: no other section
        assert any_section_ran is False

        # The outer loop's post-pass idle check then blanks + idles exactly
        # as it does for the section-level all-out case. dark_streak=1
        # simulates this being the second consecutive all-out cycle (past
        # the debounce), so the dark path actually commits.
        frame = _frame()
        with caplog.at_level(logging.INFO):
            dark, dark_canvas, dark_streak = asyncio.run(
                _idle_when_all_scheduled_out(frame, any_section_ran, False, None, 1)
            )
        assert dark is True
        assert dark_streak == 2
        frame.get_clean_canvas.assert_called_once()
        frame.swap.assert_called_once_with(frame.get_clean_canvas.return_value)
        assert dark_canvas is frame.swap.return_value
        assert "panel dark" in caplog.text
        assert slept == [1.0]

    def test_widget_becoming_active_again_wakes_the_panel(self, caplog):
        widget = _Widget()
        bind_schedule(widget, cast(VisibilitySchedule, _InactiveSchedule()))
        has_content, _ = _section_has_content(None, [widget], None)
        assert has_content is False

        # Time passes; the widget's window opens (re-bind to simulate the
        # schedule clock moving — same widget id, new active schedule).
        class _NowActive:
            def is_active(self, now=None):
                return True

        bind_schedule(widget, cast(VisibilitySchedule, _NowActive()))
        has_content, expanded = _section_has_content(None, [widget], None)
        assert has_content is True
        assert expanded == [widget]

        frame = _frame()
        existing_canvas = Mock(name="existing_dark_canvas")
        with caplog.at_level(logging.INFO):
            dark, dark_canvas, dark_streak = asyncio.run(
                _idle_when_all_scheduled_out(
                    frame, has_content, True, existing_canvas, 4
                )
            )
        assert dark is False
        # Waking preserves the retained canvas rather than dropping it
        # (process-lifetime retention, cycle-3 review Fix 1).
        assert dark_canvas is existing_canvas
        assert dark_streak == 0
        assert "panel waking" in caplog.text
