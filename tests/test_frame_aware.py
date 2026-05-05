"""Tests for the _FrameAware mixin."""

from __future__ import annotations

import attrs

from led_ticker.widgets._frame_aware import _FrameAware


@attrs.define
class _Dummy(_FrameAware):
    """Minimal subclass to exercise the mixin."""


class TestFrameAware:
    def test_initial_frame_count_is_zero(self):
        d = _Dummy()
        assert d._frame_count == 0

    def test_advance_increments(self):
        d = _Dummy()
        d.advance_frame()
        assert d._frame_count == 1
        d.advance_frame()
        d.advance_frame()
        assert d._frame_count == 3

    def test_pause_freezes_advance(self):
        d = _Dummy()
        d.advance_frame()
        d.pause_frame()
        d.advance_frame()
        d.advance_frame()
        assert d._frame_count == 1

    def test_resume_re_enables_advance(self):
        d = _Dummy()
        d.pause_frame()
        d.advance_frame()
        d.resume_frame()
        d.advance_frame()
        assert d._frame_count == 1

    def test_reset_zeroes_count(self):
        d = _Dummy()
        d.advance_frame()
        d.advance_frame()
        d.advance_frame()
        d.reset_frame()
        assert d._frame_count == 0

    def test_reset_does_not_clear_pause(self):
        """reset_frame is for visit boundaries; pause state belongs to
        transition boundaries and should not be cleared by a reset."""
        d = _Dummy()
        d.pause_frame()
        d.reset_frame()
        d.advance_frame()
        # Still paused after reset → advance should NOT increment
        assert d._frame_count == 0
