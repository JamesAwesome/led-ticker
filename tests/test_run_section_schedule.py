"""Section-level schedule gate + all-dark idle in the run loop."""

import asyncio
import logging
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

from led_ticker.app.run import (
    _idle_when_all_scheduled_out,
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


class TestIdleWhenAllScheduledOut:
    def test_sections_ran_resets_dark(self, caplog):
        frame = _frame()
        with caplog.at_level(logging.INFO):
            dark = asyncio.run(_idle_when_all_scheduled_out(frame, True, True))
        assert dark is False
        assert "waking" in caplog.text
        frame.get_clean_canvas.assert_not_called()

    def test_sections_ran_stays_quiet_when_not_dark(self, caplog):
        with caplog.at_level(logging.INFO):
            dark = asyncio.run(_idle_when_all_scheduled_out(_frame(), True, False))
        assert dark is False
        assert caplog.text == ""

    def test_transition_to_dark_blanks_once_and_logs(self, caplog):
        frame = _frame()
        with caplog.at_level(logging.INFO):
            dark = asyncio.run(_idle_when_all_scheduled_out(frame, False, False))
        assert dark is True
        frame.get_clean_canvas.assert_called_once()
        frame.swap.assert_called_once_with(frame.get_clean_canvas.return_value)
        assert "panel dark" in caplog.text

    def test_already_dark_does_not_reblank(self, caplog):
        frame = _frame()
        with caplog.at_level(logging.INFO):
            dark = asyncio.run(_idle_when_all_scheduled_out(frame, False, True))
        assert dark is True
        frame.get_clean_canvas.assert_not_called()
        assert caplog.text == ""


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

    def test_all_widgets_scheduled_out_drives_blank_and_idle(self, caplog):
        widget = _Widget()
        bind_schedule(widget, cast(VisibilitySchedule, _InactiveSchedule()))

        # What the section loop does this pass: no title, one widget, all
        # scheduled out -> _any_section_ran stays False for this section.
        has_content, _expanded = _section_has_content(None, [widget], None)
        any_section_ran = has_content  # single-section playlist: no other section
        assert any_section_ran is False

        # The outer loop's post-pass idle check then blanks + idles exactly
        # as it does for the section-level all-out case.
        frame = _frame()
        with caplog.at_level(logging.INFO):
            dark = asyncio.run(
                _idle_when_all_scheduled_out(frame, any_section_ran, False)
            )
        assert dark is True
        frame.get_clean_canvas.assert_called_once()
        frame.swap.assert_called_once_with(frame.get_clean_canvas.return_value)
        assert "panel dark" in caplog.text

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
        with caplog.at_level(logging.INFO):
            dark = asyncio.run(_idle_when_all_scheduled_out(frame, has_content, True))
        assert dark is False
        assert "waking" in caplog.text
