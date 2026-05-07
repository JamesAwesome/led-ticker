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


class TestEffectFrames:
    """Per-effect frame counter behavior. The mixin tracks one
    counter per effect attribute (`font_color`, `top_color`,
    `bottom_color`, `border`, `animation`). Each counter follows
    its effect's `restart_on_visit` policy: True (default) zeros on
    `reset_frame()`; False keeps climbing for continuous phase."""

    def _make_widget_with_effects(self, **effects):
        """Construct a `_Dummy` subclass with the requested effect
        attributes. Effect classes inline so each test is self-
        contained."""

        @attrs.define
        class _WithEffects(_FrameAware):
            font_color: object = attrs.field(default=None, kw_only=True)
            border: object = attrs.field(default=None, kw_only=True)
            animation: object = attrs.field(default=None, kw_only=True)

        return _WithEffects(**effects)

    def test_advance_increments_per_effect_counter(self):
        """Per-effect counter climbs in lockstep with `_frame_count`."""

        class _Border:
            restart_on_visit = False

        widget = self._make_widget_with_effects(border=_Border())
        for _ in range(5):
            widget.advance_frame()
        assert widget._frame_count == 5
        assert widget._effect_frames["border"] == 5

    def test_reset_zeros_only_opted_in_effects(self):
        """Continuous-phase effects (restart_on_visit=False) keep
        their counter; restart-on-visit effects zero theirs."""

        class _Typewriter:
            restart_on_visit = True

        class _RainbowBorder:
            restart_on_visit = False

        widget = self._make_widget_with_effects(
            animation=_Typewriter(),
            border=_RainbowBorder(),
        )
        for _ in range(7):
            widget.advance_frame()
        assert widget._effect_frames["animation"] == 7
        assert widget._effect_frames["border"] == 7

        widget.reset_frame()
        assert widget._frame_count == 0
        # Restart-on-visit effect: zeroed
        assert widget._effect_frames["animation"] == 0
        # Continuous-phase effect: unchanged
        assert widget._effect_frames["border"] == 7

    def test_pause_freezes_all_counters(self):
        """Paused widget = all counters frozen, both primary and
        per-effect."""

        class _Border:
            restart_on_visit = False

        widget = self._make_widget_with_effects(border=_Border())
        widget.advance_frame()  # counters at 1
        widget.pause_frame()
        for _ in range(10):
            widget.advance_frame()
        assert widget._frame_count == 1
        assert widget._effect_frames["border"] == 1

    def test_frame_for_falls_back_to_frame_count(self):
        """Lookup of an attr_name not in the dict returns
        `_frame_count`. Covers the case where a test sets
        `_frame_count` directly without going through `advance_frame`."""

        class _Border:
            restart_on_visit = False

        widget = self._make_widget_with_effects(border=_Border())
        widget._frame_count = 42  # direct write, no advance_frame
        # `_effect_frames` is empty (no advance has populated it yet)
        assert widget._effect_frames == {}
        # frame_for falls back to _frame_count
        assert widget.frame_for("border") == 42

    def test_unknown_effect_class_resets_by_default(self):
        """Effect class without a `restart_on_visit` attribute uses
        the `getattr` default of True — same as the engine-side
        gate did in PR #11. Back-compat for any third-party effect."""

        class _CustomEffect:
            pass  # no restart_on_visit attribute

        widget = self._make_widget_with_effects(font_color=_CustomEffect())
        for _ in range(3):
            widget.advance_frame()
        assert widget._effect_frames["font_color"] == 3

        widget.reset_frame()
        # No restart_on_visit attribute → defaults to True → zeroes
        assert widget._effect_frames["font_color"] == 0
