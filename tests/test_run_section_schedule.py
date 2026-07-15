"""Section-level schedule gate + all-dark idle in the run loop."""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import Mock

from led_ticker.app.run import _idle_when_all_scheduled_out, _section_schedule_active


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
