"""Tests for transition effects."""

import asyncio

import pytest

from led_ticker.transition import (
    _TRANSITION_REGISTRY,
    ColorFlash,
    Cut,
    Dissolve,
    NyanCatAlternating,
    PushAlternating,
    PushDown,
    PushLeft,
    PushRight,
    PushUp,
    Scroll,
    SplitHorizontal,
    WipeAlternating,
    WipeDown,
    WipeLeft,
    WipeRight,
    WipeUp,
    ease_in_out,
    ease_out,
    get_transition_class,
    linear,
    run_transition,
)

# --- Easing ---


class TestEasing:
    def test_linear_endpoints(self):
        assert linear(0.0) == 0.0
        assert linear(1.0) == 1.0

    def test_linear_midpoint(self):
        assert linear(0.5) == 0.5

    def test_ease_out_endpoints(self):
        assert ease_out(0.0) == 0.0
        assert ease_out(1.0) == 1.0

    def test_ease_out_faster_start(self):
        # Ease-out should be past 0.5 at the midpoint
        assert ease_out(0.5) > 0.5

    def test_ease_in_out_endpoints(self):
        assert ease_in_out(0.0) == 0.0
        assert ease_in_out(1.0) == 1.0

    def test_ease_in_out_midpoint(self):
        assert ease_in_out(0.5) == 0.5


# --- Registry ---


class TestTransitionRegistry:
    def test_all_transitions_registered(self):
        expected = [
            "cut",
            "push_left",
            "push_right",
            "push_up",
            "push_down",
            "color_flash",
            "wipe_left",
            "wipe_right",
            "wipe_up",
            "wipe_down",
            "dissolve",
            "split",
            "nyancat",
            "nyancat_reverse",
            "scroll",
            "push_alternating",
            "nyancat_alternating",
            "wipe_alternating",
        ]
        for name in expected:
            assert name in _TRANSITION_REGISTRY
        assert len(_TRANSITION_REGISTRY) == 18

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown transition"):
            get_transition_class("sparkle_explosion")


# --- Cut ---


class TestCut:
    def test_shows_incoming(self, canvas, make_widget):
        incoming = make_widget(40)
        outgoing = make_widget(60)
        cut = Cut()
        cut.frame_at(0.5, canvas, outgoing, incoming)
        incoming.draw.assert_called_once()


# --- PushLeft ---


class TestPushLeft:
    def test_at_zero_shows_outgoing_only(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushLeft()
        push.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=0)
        outgoing.draw.assert_called_once_with(canvas, cursor_pos=0)
        # incoming_pos = 160 + 10 - 0 = 170 > canvas.width, so not drawn
        incoming.draw.assert_not_called()

    def test_at_one_shows_incoming_at_zero(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushLeft()
        push.frame_at(1.0, canvas, outgoing, incoming, outgoing_scroll_pos=0)
        incoming.draw.assert_called_once()
        assert incoming.draw.call_args.kwargs["cursor_pos"] == 0

    def test_midpoint_draws_both(self, canvas, make_widget):
        """At midpoint, both outgoing and incoming should be drawn."""
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushLeft()
        push.frame_at(0.5, canvas, outgoing, incoming, outgoing_scroll_pos=0)
        # Outgoing drawn at negative offset (sliding left)
        outgoing.draw.assert_called_once()
        # At t=0.5, incoming_pos = 160 + 10 - 85 = 85, which is < 160
        incoming.draw.assert_called_once()
        assert incoming.draw.call_args.kwargs["cursor_pos"] == 85

    def test_midpoint_uses_setpixel_for_blackout(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushLeft()
        push.frame_at(0.5, canvas, outgoing, incoming, outgoing_scroll_pos=0)
        # SetPixel used to black out the right zone before drawing incoming
        assert canvas.SetPixel.call_count > 0

    def test_outgoing_scroll_pos_used(self, canvas, make_widget):
        """Outgoing should continue from its final scroll position."""
        outgoing = make_widget(600)
        incoming = make_widget(40)
        push = PushLeft()
        final_pos = -440  # -(600 - 160) as if scrolled to end
        push.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=final_pos)
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -440

    def test_returns_canvas(self, canvas, make_widget):
        push = PushLeft()
        result = push.frame_at(0.5, canvas, make_widget(40), make_widget(40))
        assert result is canvas

    def test_short_text_no_scroll_pos(self, canvas, make_widget):
        """Short text (pos=0) should slide cleanly off to the left."""
        outgoing = make_widget(100)
        incoming = make_widget(100)
        push = PushLeft()
        # At t=0, outgoing at 0, incoming off-screen
        push.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=0)
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == 0
        incoming.draw.assert_not_called()

    def test_default_outgoing_scroll_pos_is_zero(self, canvas, make_widget):
        """If outgoing_scroll_pos not passed, defaults to 0."""
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushLeft()
        push.frame_at(0.0, canvas, outgoing, incoming)
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == 0


# --- PushUp ---


class TestPushUp:
    def test_at_zero_shows_outgoing_only(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushUp()
        push.frame_at(0.0, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        assert outgoing.draw.call_args.kwargs.get("y_offset", 0) == 0
        incoming.draw.assert_not_called()

    def test_at_one_shows_incoming(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushUp()
        push.frame_at(1.0, canvas, outgoing, incoming)
        incoming.draw.assert_called_once()

    def test_midpoint_draws_both_with_y_offset(self, canvas, make_widget):
        """Both widgets drawn with y_offset at midpoint."""
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushUp()
        push.frame_at(0.5, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        # Outgoing should have negative y_offset (sliding up)
        assert outgoing.draw.call_args.kwargs["y_offset"] < 0
        incoming.draw.assert_called_once()
        # Incoming should have positive y_offset (entering from below)
        assert incoming.draw.call_args.kwargs["y_offset"] > 0

    def test_midpoint_uses_setpixel_for_blackout(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushUp()
        push.frame_at(0.5, canvas, outgoing, incoming)
        assert canvas.SetPixel.call_count > 0

    def test_outgoing_scroll_pos_used(self, canvas, make_widget):
        """Outgoing should stay at its scrolled position, not reset to 0."""
        outgoing = make_widget(600)
        incoming = make_widget(40)
        push = PushUp()
        push.frame_at(
            0.0, canvas, outgoing, incoming, outgoing_scroll_pos=-440
        )
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -440

    def test_returns_canvas(self, canvas, make_widget):
        push = PushUp()
        result = push.frame_at(0.5, canvas, make_widget(40), make_widget(40))
        assert result is canvas


# --- PushDown ---


class TestPushDown:
    def test_at_zero_shows_outgoing_only(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushDown()
        push.frame_at(0.0, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()

    def test_at_one_shows_incoming(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushDown()
        push.frame_at(1.0, canvas, outgoing, incoming)
        incoming.draw.assert_called_once()

    def test_midpoint_draws_both_with_y_offset(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushDown()
        push.frame_at(0.5, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        # Outgoing should have positive y_offset (sliding down)
        assert outgoing.draw.call_args.kwargs["y_offset"] > 0
        incoming.draw.assert_called_once()
        # Incoming should have negative y_offset (entering from top)
        assert incoming.draw.call_args.kwargs["y_offset"] < 0

    def test_midpoint_uses_setpixel_for_blackout(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushDown()
        push.frame_at(0.5, canvas, outgoing, incoming)
        assert canvas.SetPixel.call_count > 0

    def test_outgoing_scroll_pos_used(self, canvas, make_widget):
        outgoing = make_widget(600)
        incoming = make_widget(40)
        push = PushDown()
        push.frame_at(
            0.5, canvas, outgoing, incoming, outgoing_scroll_pos=-440
        )
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -440

    def test_returns_canvas(self, canvas, make_widget):
        push = PushDown()
        result = push.frame_at(
            0.5, canvas, make_widget(40), make_widget(40)
        )
        assert result is canvas


# --- PushRight ---


class TestPushRight:
    def test_at_zero_shows_outgoing_only(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushRight()
        push.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=0)
        outgoing.draw.assert_called_once_with(canvas, cursor_pos=0)
        incoming.draw.assert_not_called()

    def test_at_one_shows_incoming_at_zero(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushRight()
        push.frame_at(1.0, canvas, outgoing, incoming, outgoing_scroll_pos=0)
        incoming.draw.assert_called_once()
        assert incoming.draw.call_args.kwargs["cursor_pos"] == 0

    def test_midpoint_draws_both_no_overlap(self, canvas, make_widget):
        """Both drawn: incoming slides from left, outgoing at boundary."""
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushRight()
        push.frame_at(0.5, canvas, outgoing, incoming, outgoing_scroll_pos=0)
        boundary = int(0.5 * canvas.width)  # 80
        # Incoming slides in from left: -w + boundary = -80
        incoming.draw.assert_called_once()
        assert incoming.draw.call_args.kwargs["cursor_pos"] == -80
        # Outgoing drawn at cursor_pos=boundary (right zone)
        outgoing.draw.assert_called_once()
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == boundary

    def test_incoming_slides_from_left(self, canvas, make_widget):
        """Incoming should enter from off-screen left, not sit at pos=0."""
        push = PushRight()
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push.frame_at(0.25, canvas, outgoing, incoming)
        # At t=0.25: boundary=40, incoming_pos = -160 + 40 = -120
        assert incoming.draw.call_args.kwargs["cursor_pos"] == -120

    def test_midpoint_uses_setpixel_for_blackout(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushRight()
        push.frame_at(0.5, canvas, outgoing, incoming, outgoing_scroll_pos=0)
        # SetPixel used to black out right zone between incoming and outgoing
        assert canvas.SetPixel.call_count > 0

    def test_outgoing_at_scroll_pos_for_first_frame(self, canvas, make_widget):
        """At t=0, outgoing is at its natural hold position."""
        outgoing = make_widget(600)
        incoming = make_widget(40)
        push = PushRight()
        push.frame_at(
            0.0, canvas, outgoing, incoming, outgoing_scroll_pos=-440
        )
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -440

    def test_outgoing_confined_to_right_zone(self, canvas, make_widget):
        """Outgoing at cursor_pos=boundary can't bleed left."""
        outgoing = make_widget(600)
        incoming = make_widget(600)
        push = PushRight()
        push.frame_at(0.5, canvas, outgoing, incoming, outgoing_scroll_pos=-440)
        boundary = int(0.5 * canvas.width)
        # Outgoing drawn at boundary, not at scroll_pos
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == boundary
        # Incoming slides from left: -w + boundary
        assert incoming.draw.call_args.kwargs["cursor_pos"] == -80

    def test_short_text_slides_right(self, canvas, make_widget):
        """Short outgoing text at increasing cursor_pos = sliding right."""
        outgoing = make_widget(100)
        incoming = make_widget(100)
        push = PushRight()
        push.frame_at(0.25, canvas, outgoing, incoming, outgoing_scroll_pos=0)
        boundary_25 = int(0.25 * canvas.width)  # 40
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == boundary_25
        outgoing2 = make_widget(100)
        incoming2 = make_widget(100)
        push.frame_at(0.75, canvas, outgoing2, incoming2, outgoing_scroll_pos=0)
        boundary_75 = int(0.75 * canvas.width)  # 120
        assert outgoing2.draw.call_args.kwargs["cursor_pos"] == boundary_75
        # Outgoing slides right: 40 → 120
        assert boundary_75 > boundary_25

    def test_returns_canvas(self, canvas, make_widget):
        push = PushRight()
        result = push.frame_at(
            0.5, canvas, make_widget(40), make_widget(40)
        )
        assert result is canvas

    def test_default_outgoing_scroll_pos_is_zero(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushRight()
        push.frame_at(0.0, canvas, outgoing, incoming)
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == 0


# --- WipeUp ---


class TestWipeUp:
    def test_at_zero_shows_outgoing(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeUp()
        wipe.frame_at(0.0, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()

    def test_at_one_shows_incoming(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeUp()
        wipe.frame_at(1.0, canvas, outgoing, incoming)
        incoming.draw.assert_called_once()

    def test_mid_draws_outgoing_with_setpixel(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeUp()
        wipe.frame_at(0.5, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()
        assert canvas.SetPixel.call_count > 0

    def test_outgoing_scroll_pos_used(self, canvas, make_widget):
        outgoing = make_widget(600)
        incoming = make_widget(40)
        wipe = WipeUp()
        wipe.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=-440)
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -440

    def test_sweep_at_bottom_edge_on_first_frame(self, canvas, make_widget):
        """Sweep line should appear at bottom edge on first frame."""
        wipe = WipeUp()
        wipe.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        calls = canvas.SetPixel.call_args_list
        ys = [c.args[1] for c in calls]
        assert canvas.height - 1 in ys

    def test_returns_canvas(self, canvas, make_widget):
        wipe = WipeUp()
        result = wipe.frame_at(
            0.5, canvas, make_widget(40), make_widget(40)
        )
        assert result is canvas


# --- ColorFlash ---


class TestColorFlash:
    def test_early_shows_outgoing(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        flash = ColorFlash()
        flash.frame_at(0.1, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()

    def test_middle_fills_canvas(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        flash = ColorFlash()
        flash.frame_at(0.5, canvas, outgoing, incoming)
        canvas.Fill.assert_called_once_with(255, 255, 255)

    def test_late_shows_incoming(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        flash = ColorFlash()
        flash.frame_at(0.9, canvas, outgoing, incoming)
        incoming.draw.assert_called_once()
        outgoing.draw.assert_not_called()

    def test_outgoing_scroll_pos_used(self, canvas, make_widget):
        outgoing = make_widget(600)
        incoming = make_widget(40)
        flash = ColorFlash()
        flash.frame_at(0.1, canvas, outgoing, incoming, outgoing_scroll_pos=-440)
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -440

    def test_custom_color(self, canvas, make_widget):
        flash = ColorFlash(color=[255, 0, 0])
        flash.frame_at(0.5, canvas, make_widget(40), make_widget(40))
        canvas.Fill.assert_called_once_with(255, 0, 0)

    def test_default_color_is_white(self, canvas, make_widget):
        flash = ColorFlash()
        flash.frame_at(0.5, canvas, make_widget(40), make_widget(40))
        canvas.Fill.assert_called_once_with(255, 255, 255)


# --- WipeLeft ---


class TestWipeLeft:
    def test_at_zero_shows_outgoing(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeLeft()
        wipe.frame_at(0.0, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == 0

    def test_at_one_shows_incoming(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeLeft()
        wipe.frame_at(1.0, canvas, outgoing, incoming)
        incoming.draw.assert_called_once()
        assert incoming.draw.call_args.kwargs["cursor_pos"] == 0

    def test_mid_draws_outgoing_with_setpixel(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeLeft()
        wipe.frame_at(0.5, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()
        # SetPixel called for black-out region and sweep line
        assert canvas.SetPixel.call_count > 0

    def test_outgoing_scroll_pos_used(self, canvas, make_widget):
        outgoing = make_widget(600)
        incoming = make_widget(40)
        wipe = WipeLeft()
        wipe.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=-440)
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -440

    def test_sweep_at_left_edge_on_first_frame(self, canvas, make_widget):
        """Sweep line should appear at x=0 on the very first frame."""
        wipe = WipeLeft()
        wipe.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        calls = canvas.SetPixel.call_args_list
        xs = [c.args[0] for c in calls]
        assert 0 in xs

    def test_returns_canvas(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeLeft()
        result = wipe.frame_at(0.5, canvas, outgoing, incoming)
        assert result is canvas


# --- WipeRight ---


class TestWipeRight:
    def test_at_zero_shows_outgoing(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeRight()
        wipe.frame_at(0.0, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == 0

    def test_at_one_shows_incoming(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeRight()
        wipe.frame_at(1.0, canvas, outgoing, incoming)
        incoming.draw.assert_called_once()
        assert incoming.draw.call_args.kwargs["cursor_pos"] == 0

    def test_mid_draws_outgoing_with_setpixel(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeRight()
        wipe.frame_at(0.5, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()
        # SetPixel called for black-out region and sweep line
        assert canvas.SetPixel.call_count > 0

    def test_outgoing_scroll_pos_used(self, canvas, make_widget):
        outgoing = make_widget(600)
        incoming = make_widget(40)
        wipe = WipeRight()
        wipe.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=-440)
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -440

    def test_sweep_at_right_edge_on_first_frame(self, canvas, make_widget):
        """Sweep line should appear at right edge on first frame."""
        wipe = WipeRight()
        wipe.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        calls = canvas.SetPixel.call_args_list
        xs = [c.args[0] for c in calls]
        assert canvas.width - 1 in xs

    def test_returns_canvas(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeRight()
        result = wipe.frame_at(0.5, canvas, outgoing, incoming)
        assert result is canvas


# --- Dissolve ---


class TestDissolve:
    def test_early_shows_outgoing(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        dissolve = Dissolve()
        dissolve.frame_at(0.1, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()
        # SetPixel called for scatter
        assert canvas.SetPixel.call_count > 0

    def test_late_shows_incoming(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        dissolve = Dissolve()
        dissolve.frame_at(0.9, canvas, outgoing, incoming)
        incoming.draw.assert_called_once()
        outgoing.draw.assert_not_called()
        # SetPixel called for scatter
        assert canvas.SetPixel.call_count > 0

    def test_at_zero_shows_outgoing_only(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        dissolve = Dissolve()
        dissolve.frame_at(0.0, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()

    def test_at_one_shows_incoming_only(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        dissolve = Dissolve()
        dissolve.frame_at(1.0, canvas, outgoing, incoming)
        incoming.draw.assert_called_once()
        outgoing.draw.assert_not_called()

    def test_outgoing_scroll_pos_used(self, canvas, make_widget):
        outgoing = make_widget(600)
        incoming = make_widget(40)
        dissolve = Dissolve()
        dissolve.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=-440)
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -440

    def test_returns_canvas(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        dissolve = Dissolve()
        result = dissolve.frame_at(0.5, canvas, outgoing, incoming)
        assert result is canvas


# --- SplitHorizontal ---


class TestSplitHorizontal:
    def test_early_shows_outgoing(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        split = SplitHorizontal()
        split.frame_at(0.1, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()

    def test_late_draws_outgoing_with_setpixel(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        split = SplitHorizontal()
        split.frame_at(0.9, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()
        # SetPixel called for black band and magenta edge lines
        assert canvas.SetPixel.call_count > 0

    def test_at_one_shows_incoming(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        split = SplitHorizontal()
        split.frame_at(1.0, canvas, outgoing, incoming)
        incoming.draw.assert_called_once()
        outgoing.draw.assert_not_called()

    def test_outgoing_scroll_pos_used(self, canvas, make_widget):
        outgoing = make_widget(600)
        incoming = make_widget(40)
        split = SplitHorizontal()
        split.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=-440)
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -440

    def test_returns_canvas(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        split = SplitHorizontal()
        result = split.frame_at(0.5, canvas, outgoing, incoming)
        assert result is canvas


# --- WipeDown ---


class TestWipeDown:
    def test_early_shows_outgoing(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeDown()
        wipe.frame_at(0.1, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()

    def test_late_draws_outgoing_with_setpixel(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeDown()
        wipe.frame_at(0.9, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()
        # SetPixel called for row blackout and sweep line
        assert canvas.SetPixel.call_count > 0

    def test_at_one_shows_incoming(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeDown()
        wipe.frame_at(1.0, canvas, outgoing, incoming)
        incoming.draw.assert_called_once()
        outgoing.draw.assert_not_called()

    def test_outgoing_scroll_pos_used(self, canvas, make_widget):
        outgoing = make_widget(600)
        incoming = make_widget(40)
        wipe = WipeDown()
        wipe.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=-440)
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -440

    def test_sweep_at_top_edge_on_first_frame(self, canvas, make_widget):
        """Sweep line should appear at top edge on first frame."""
        wipe = WipeDown()
        wipe.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        calls = canvas.SetPixel.call_args_list
        ys = [c.args[1] for c in calls]
        assert 0 in ys

    def test_returns_canvas(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeDown()
        result = wipe.frame_at(0.5, canvas, outgoing, incoming)
        assert result is canvas


# --- Scroll ---


class TestScroll:
    def test_at_zero_shows_outgoing(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        scroll = Scroll()
        scroll.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=0)
        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()

    def test_at_one_shows_incoming_at_zero(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        scroll = Scroll()
        scroll.frame_at(1.0, canvas, outgoing, incoming)
        incoming.draw.assert_called_once()
        assert incoming.draw.call_args.kwargs["cursor_pos"] == 0

    def test_outgoing_scroll_pos_used(self, canvas, make_widget):
        outgoing = make_widget(600)
        incoming = make_widget(40)
        scroll = Scroll()
        scroll.frame_at(
            0.0, canvas, outgoing, incoming, outgoing_scroll_pos=-440
        )
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -440

    def test_bullet_exists(self):
        """Scroll transition should have a bullet separator."""
        scroll = Scroll()
        assert scroll._bullet is not None
        assert scroll._bullet_width > 0

    def test_positions_are_consecutive(self, canvas, make_widget):
        """At t=0, outgoing at scroll_pos, bullet/incoming off-screen."""
        scroll = Scroll()
        outgoing = make_widget(40)
        incoming = make_widget(40)
        scroll.frame_at(
            0.0, canvas, outgoing, incoming, outgoing_scroll_pos=0
        )
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == 0
        # Bullet at canvas.width (160), incoming at 160+bullet_width
        # Both off-screen right, so incoming not drawn
        incoming.draw.assert_not_called()

    def test_returns_canvas(self, canvas, make_widget):
        scroll = Scroll()
        result = scroll.frame_at(
            0.5, canvas, make_widget(40), make_widget(40)
        )
        assert result is canvas


# --- PushAlternating ---


class TestPushAlternating:
    def test_first_swap_uses_push_left(self, canvas, make_widget):
        alt = PushAlternating()
        alt.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert alt._index == 0
        assert isinstance(alt._transitions[0], PushLeft)

    def test_cycles_through_directions(self, canvas, make_widget):
        alt = PushAlternating()
        for i in range(4):
            alt.frame_at(0.0, canvas, make_widget(40), make_widget(40))
            alt.frame_at(1.0, canvas, make_widget(40), make_widget(40))
            assert alt._index == i

    def test_wraps_around(self, canvas, make_widget):
        alt = PushAlternating()
        for _i in range(5):
            alt.frame_at(0.0, canvas, make_widget(40), make_widget(40))
            alt.frame_at(1.0, canvas, make_widget(40), make_widget(40))
        assert alt._index == 0

    def test_returns_canvas(self, canvas, make_widget):
        alt = PushAlternating()
        result = alt.frame_at(
            0.5, canvas, make_widget(40), make_widget(40)
        )
        assert result is canvas

    def test_forwards_outgoing_scroll_pos(self, canvas, make_widget):
        alt = PushAlternating()
        alt.frame_at(
            0.0, canvas, make_widget(600), make_widget(40),
            outgoing_scroll_pos=-440,
        )


# --- NyanCatAlternating ---


class TestNyanCatAlternating:
    def test_first_swap_uses_nyancat(self, canvas, make_widget):
        alt = NyanCatAlternating()
        alt.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert alt._index == 0

    def test_second_swap_uses_reverse(self, canvas, make_widget):
        alt = NyanCatAlternating()
        alt.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        alt.frame_at(1.0, canvas, make_widget(40), make_widget(40))
        alt.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert alt._index == 1

    def test_wraps_around(self, canvas, make_widget):
        alt = NyanCatAlternating()
        for _i in range(3):
            alt.frame_at(0.0, canvas, make_widget(40), make_widget(40))
            alt.frame_at(1.0, canvas, make_widget(40), make_widget(40))
        assert alt._index == 0

    def test_returns_canvas(self, canvas, make_widget):
        alt = NyanCatAlternating()
        result = alt.frame_at(
            0.5, canvas, make_widget(40), make_widget(40)
        )
        assert result is canvas


# --- WipeAlternating ---


class TestWipeAlternating:
    def test_first_swap_uses_wipe_left(self, canvas, make_widget):
        alt = WipeAlternating()
        alt.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert alt._index == 0
        assert isinstance(alt._transitions[0], WipeLeft)

    def test_cycles_through_directions(self, canvas, make_widget):
        alt = WipeAlternating()
        for i in range(4):
            alt.frame_at(0.0, canvas, make_widget(40), make_widget(40))
            alt.frame_at(1.0, canvas, make_widget(40), make_widget(40))
            assert alt._index == i

    def test_wraps_around(self, canvas, make_widget):
        alt = WipeAlternating()
        for _i in range(5):
            alt.frame_at(0.0, canvas, make_widget(40), make_widget(40))
            alt.frame_at(1.0, canvas, make_widget(40), make_widget(40))
        assert alt._index == 0

    def test_color_forwarded_to_sub_transitions(self):
        alt = WipeAlternating(color=[255, 0, 0])
        for trans in alt._transitions:
            assert trans.color == (255, 0, 0)

    def test_returns_canvas(self, canvas, make_widget):
        alt = WipeAlternating()
        result = alt.frame_at(
            0.5, canvas, make_widget(40), make_widget(40)
        )
        assert result is canvas


# --- run_transition ---


@pytest.fixture
def no_sleep(monkeypatch):
    _real_sleep = asyncio.sleep

    async def _fast(seconds):
        await _real_sleep(0)

    monkeypatch.setattr("led_ticker.transition.asyncio.sleep", _fast)


class TestRunTransition:
    async def test_runs_correct_frame_count(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushLeft()

        await run_transition(
            canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=push,
            duration=0.5,
            scroll_speed=0.05,
        )
        # duration=0.5 / scroll_speed=0.05 = 10 frames + 1 final
        assert mock_frame.matrix.SwapOnVSync.call_count == 11

    async def test_final_frame_shows_incoming(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        cut = Cut()

        await run_transition(
            canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=cut,
            duration=0.1,
        )
        # Last call should be incoming drawn at cursor_pos=0
        incoming.draw.assert_called()

    async def test_returns_canvas(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        cut = Cut()

        result = await run_transition(
            canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=cut,
            duration=0.1,
        )
        assert result is not None
