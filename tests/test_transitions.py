"""Tests for transition effects."""

import unittest.mock as mock

import pytest

from led_ticker.transitions import (
    _TRANSITION_REGISTRY,
    ColorFlash,
    Cut,
    Dissolve,
    NyanCatAlternating,
    PushAlternating,
    PushDown,
    PushLeft,
    PushRandom,
    PushRight,
    PushUp,
    Scroll,
    SplitHorizontal,
    WipeAlternating,
    WipeDown,
    WipeLeft,
    WipeRandom,
    WipeRight,
    WipeUp,
    ease_in_out,
    ease_out,
    get_transition_class,
    linear,
    run_transition,
)
from led_ticker.transitions.wipe import _BaseWipe

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
            "pokeball",
            "pokeball_reverse",
            "pokeball_alternating",
            "baseball",
            "baseball_reverse",
            "baseball_alternating",
            "pacman",
            "pacman_reverse",
            "pacman_alternating",
            "scroll",
            "push_alternating",
            "push_random",
            "nyancat_alternating",
            "wipe_alternating",
            "wipe_random",
            "sailor_moon",
            "sailor_moon_reverse",
            "sailor_moon_alternating",
        ]
        for name in expected:
            assert name in _TRANSITION_REGISTRY
        assert len(_TRANSITION_REGISTRY) == 32

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown transition"):
            get_transition_class("sparkle_explosion")

    def test_register_duplicate_transition_raises(self):
        from led_ticker.transitions import register_transition

        with pytest.raises(
            ValueError, match="Transition name.*cut.*already registered"
        ):

            @register_transition("cut")
            class ShouldFail:
                pass


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

    def test_midpoint_uses_subfill_for_blackout(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushLeft()
        # t=0.5: scroll_offset=85, clear_start=max(0,160+10-85)=85, w-clear_start=75
        push.frame_at(0.5, canvas, outgoing, incoming, outgoing_scroll_pos=0)
        canvas.SubFill.assert_called_once_with(85, 0, 75, 16, 0, 0, 0)

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

    def test_midpoint_uses_subfill_for_blackout(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushUp()
        # t=0.5: scroll_offset=int(0.5*20)=10, incoming_y=16+4-10=10
        # boundary_row=max(0,min(16,10))=10, SubFill from row 10, height 6
        push.frame_at(0.5, canvas, outgoing, incoming)
        canvas.SubFill.assert_called_once_with(0, 10, 160, 6, 0, 0, 0)

    def test_outgoing_scroll_pos_used(self, canvas, make_widget):
        """Outgoing should stay at its scrolled position, not reset to 0."""
        outgoing = make_widget(600)
        incoming = make_widget(40)
        push = PushUp()
        push.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=-440)
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

    def test_midpoint_uses_subfill_for_blackout(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushDown()
        # t=0.5: scroll_offset=10, incoming_y=-(16+4)+10=-10
        # boundary_row=max(0,min(16,-10+16))=6, SubFill from row 6, height 10
        push.frame_at(0.5, canvas, outgoing, incoming)
        canvas.SubFill.assert_called_once_with(0, 6, 160, 10, 0, 0, 0)

    def test_outgoing_scroll_pos_used(self, canvas, make_widget):
        outgoing = make_widget(600)
        incoming = make_widget(40)
        push = PushDown()
        push.frame_at(0.5, canvas, outgoing, incoming, outgoing_scroll_pos=-440)
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -440

    def test_returns_canvas(self, canvas, make_widget):
        push = PushDown()
        result = push.frame_at(0.5, canvas, make_widget(40), make_widget(40))
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

    def test_midpoint_uses_subfill_for_blackout(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushRight()
        # t=0.5: boundary=int(0.5*160)=80, SubFill from x=80, width=80
        push.frame_at(0.5, canvas, outgoing, incoming, outgoing_scroll_pos=0)
        canvas.SubFill.assert_called_once_with(80, 0, 80, 16, 0, 0, 0)

    def test_outgoing_at_scroll_pos_for_first_frame(self, canvas, make_widget):
        """At t=0, outgoing is at its natural hold position."""
        outgoing = make_widget(600)
        incoming = make_widget(40)
        push = PushRight()
        push.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=-440)
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
        result = push.frame_at(0.5, canvas, make_widget(40), make_widget(40))
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
        result = wipe.frame_at(0.5, canvas, make_widget(40), make_widget(40))
        assert result is canvas

    def test_mid_blackout_uses_subfill(self, canvas, make_widget):
        wipe = WipeUp()
        # t=0.5: sweep_row=max(0,15-min(8,15))=7; blackout rows [8..15]
        wipe.frame_at(0.5, canvas, make_widget(40), make_widget(40))
        canvas.SubFill.assert_called_once_with(0, 8, 160, 8, 0, 0, 0)


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

    def test_sweep_at_right_edge_on_first_frame(self, canvas, make_widget):
        """Sweep starts at right edge (moves toward left)."""
        wipe = WipeLeft()
        wipe.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        calls = canvas.SetPixel.call_args_list
        xs = [c.args[0] for c in calls]
        assert canvas.width - 1 in xs

    def test_returns_canvas(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeLeft()
        result = wipe.frame_at(0.5, canvas, outgoing, incoming)
        assert result is canvas

    def test_mid_blackout_uses_subfill(self, canvas, make_widget):
        wipe = WipeLeft()
        # t=0.5: boundary=min(int(0.5*161),160)=80; line_x=160-80=80
        # blackout SubFill(80, 0, 80, 16, 0,0,0)
        wipe.frame_at(0.5, canvas, make_widget(40), make_widget(40))
        canvas.SubFill.assert_called_once_with(80, 0, 80, 16, 0, 0, 0)


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

    def test_sweep_at_left_edge_on_first_frame(self, canvas, make_widget):
        """Sweep starts at left edge (moves toward right)."""
        wipe = WipeRight()
        wipe.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        calls = canvas.SetPixel.call_args_list
        xs = [c.args[0] for c in calls]
        assert 0 in xs

    def test_returns_canvas(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeRight()
        result = wipe.frame_at(0.5, canvas, outgoing, incoming)
        assert result is canvas

    def test_mid_blackout_uses_subfill(self, canvas, make_widget):
        wipe = WipeRight()
        # t=0.5: boundary=80; blackout SubFill(0, 0, 80, 16, 0,0,0)
        wipe.frame_at(0.5, canvas, make_widget(40), make_widget(40))
        canvas.SubFill.assert_called_once_with(0, 0, 80, 16, 0, 0, 0)


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

    def test_scatter_uses_physical_resolution_through_scaled_canvas(self, make_widget):
        """Regression: dissolve must scatter at the underlying real
        canvas's resolution, not the wrapper's logical canvas. Otherwise
        on the bigsign (scale=4) at t=0.5 the scatter `count` exactly
        equals `total` (every logical block blacks out) → the dissolve
        becomes a fade-through-black, and gif content (which paints
        native pixels) appears to wipe rather than melt."""
        from led_ticker.scaled_canvas import ScaledCanvas

        real = mock.Mock()
        real.width = 256
        real.height = 64
        wrapper = ScaledCanvas(real, scale=4)
        wrapper.real = real  # ScaledCanvas constructor already wires this

        outgoing = make_widget(40)
        incoming = make_widget(40)
        dissolve = Dissolve()
        dissolve.frame_at(0.5, wrapper, outgoing, incoming)

        # At t=0.5 with physical-grain scatter, count = 256*64 = 16384
        # SetPixel calls go to `real`, not the wrapper.
        assert real.SetPixel.call_count == 256 * 64
        # Sequence cached at physical dims, not logical (64*16=1024)
        seq = dissolve._get_sequence(256, 64)
        assert seq is not None
        assert len(seq) == 256 * 64

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

    def test_late_blackout_uses_subfill(self, canvas, make_widget):
        split = SplitHorizontal()
        # t=0.9: half=80, reveal=int(0.9*80)=72; left=80-72=8, right=80+72=152
        # band_x=max(0,8)=8, band_w=min(152,160)-8=144
        split.frame_at(0.9, canvas, make_widget(40), make_widget(40))
        canvas.SubFill.assert_called_once_with(8, 0, 144, 16, 0, 0, 0)


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

    def test_mid_blackout_uses_subfill(self, canvas, make_widget):
        wipe = WipeDown()
        # t=0.5: sweep_row=min(int(0.5*17),16)=8; blackout rows [0..7]
        wipe.frame_at(0.5, canvas, make_widget(40), make_widget(40))
        canvas.SubFill.assert_called_once_with(0, 0, 160, 8, 0, 0, 0)


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
        scroll.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=-440)
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -440

    def test_separator_width(self):
        """Separator should be gap + bullet + gap."""
        from led_ticker.ticker import (
            BULLET_WIDTH,
            SCROLL_GAP,
            scroll_separator_width,
        )

        scroll = Scroll()
        expected = SCROLL_GAP + BULLET_WIDTH + SCROLL_GAP
        assert scroll._sep_w == expected
        assert scroll._sep_w == scroll_separator_width()

    def test_positions_are_consecutive(self, canvas, make_widget):
        """At t=0, outgoing at scroll_pos, bullet/incoming off-screen."""
        scroll = Scroll()
        outgoing = make_widget(40)
        incoming = make_widget(40)
        scroll.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=0)
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == 0
        # Bullet at canvas.width (160), incoming at 160+bullet_width
        # Both off-screen right, so incoming not drawn
        incoming.draw.assert_not_called()

    def test_returns_canvas(self, canvas, make_widget):
        scroll = Scroll()
        result = scroll.frame_at(0.5, canvas, make_widget(40), make_widget(40))
        assert result is canvas


class TestScrollInlinedDrawing:
    def test_frame_at_does_not_import_draw_scroll_frame(self):
        """Scroll.frame_at must not import the private _draw_scroll_frame
        from ticker. Extension authors must not depend on engine privates.
        Inline the logic into frame_at instead."""
        import inspect

        source = inspect.getsource(Scroll.frame_at)
        assert "_draw_scroll_frame" not in source, (
            "Scroll.frame_at still imports _draw_scroll_frame from ticker — "
            "inline the draw logic into frame_at directly"
        )

    def test_blackout_region_cleared_at_mid_scroll(self, canvas, make_widget):
        """At mid-scroll the region between outgoing tail and the right
        edge of the canvas is blacked out via SubFill."""
        scroll = Scroll()
        outgoing = make_widget(40)
        incoming = make_widget(40)
        # t=0.5, sep_w=14: scroll_offset=int(0.5*174)=87
        # clear_start=max(0,160-87)=73, w-clear_start=87
        scroll.frame_at(0.5, canvas, outgoing, incoming)
        canvas.SubFill.assert_called_once_with(73, 0, 87, 16, 0, 0, 0)

    def test_bullet_painted_at_mid_scroll(self, canvas, make_widget):
        """Bullet (2×2 white dot) is painted during scroll."""
        scroll = Scroll()
        outgoing = make_widget(40)
        incoming = make_widget(40)
        scroll.frame_at(0.5, canvas, outgoing, incoming)
        white_calls = [
            c for c in canvas.SetPixel.call_args_list if c.args[2:] == (255, 255, 255)
        ]
        assert len(white_calls) >= 1, "No bullet pixels were painted"


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
        result = alt.frame_at(0.5, canvas, make_widget(40), make_widget(40))
        assert result is canvas

    def test_forwards_outgoing_scroll_pos(self, canvas, make_widget):
        alt = PushAlternating()
        alt.frame_at(
            0.0,
            canvas,
            make_widget(600),
            make_widget(40),
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
        result = alt.frame_at(0.5, canvas, make_widget(40), make_widget(40))
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

    def test_default_colors_from_base_classes(self):
        alt = WipeAlternating()
        assert alt._transitions[0].color == WipeLeft.DEFAULT_COLOR
        assert alt._transitions[1].color == WipeRight.DEFAULT_COLOR
        assert alt._transitions[2].color == WipeUp.DEFAULT_COLOR
        assert alt._transitions[3].color == WipeDown.DEFAULT_COLOR
        # All unique
        colors = [t.color for t in alt._transitions]
        assert len(set(colors)) == 4

    def test_single_color_override(self):
        alt = WipeAlternating(color=[255, 0, 0])
        for t in alt._transitions:
            assert t.color == (255, 0, 0)

    def test_per_direction_colors(self):
        custom = [[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 0]]
        alt = WipeAlternating(colors=custom)
        assert alt._transitions[0].color == (255, 0, 0)
        assert alt._transitions[1].color == (0, 255, 0)
        assert alt._transitions[2].color == (0, 0, 255)
        assert alt._transitions[3].color == (255, 255, 0)

    def test_returns_canvas(self, canvas, make_widget):
        alt = WipeAlternating()
        result = alt.frame_at(0.5, canvas, make_widget(40), make_widget(40))
        assert result is canvas


# --- WipeRandom ---


class TestWipeRandomNeverRepeatsDirection:
    def _do_swaps(self, rnd, canvas, make_widget, n=20):
        classes = []
        for _ in range(n):
            rnd.frame_at(0.0, canvas, make_widget(40), make_widget(40))
            classes.append(type(rnd._current))
            rnd.frame_at(1.0, canvas, make_widget(40), make_widget(40))
        return classes

    def test_no_consecutive_repeats(self, canvas, make_widget):
        rnd = WipeRandom()
        classes = self._do_swaps(rnd, canvas, make_widget)
        for a, b in zip(classes, classes[1:], strict=False):
            assert a is not b, f"Consecutive repeat: {a.__name__}"

    def test_all_four_directions_used_over_many_swaps(self, canvas, make_widget):
        rnd = WipeRandom()
        classes = self._do_swaps(rnd, canvas, make_widget, n=40)
        assert set(classes) == {WipeLeft, WipeRight, WipeUp, WipeDown}

    def test_first_swap_all_directions_are_candidates(self, canvas, make_widget):
        seen = set()
        for _ in range(60):
            rnd = WipeRandom()
            rnd.frame_at(0.0, canvas, make_widget(40), make_widget(40))
            seen.add(type(rnd._current))
        assert seen == {WipeLeft, WipeRight, WipeUp, WipeDown}


class TestWipeRandomColorPool:
    def test_default_pool_is_four_direction_colors(self):
        rnd = WipeRandom()
        expected = [cls.DEFAULT_COLOR for cls in WipeRandom._WIPE_CLASSES]
        assert rnd._color_pool == expected

    def test_single_color_becomes_one_element_pool(self):
        rnd = WipeRandom(color=(255, 0, 0))
        assert rnd._color_pool == [(255, 0, 0)]

    def test_colors_list_used_verbatim(self):
        pool = [(1, 2, 3), (4, 5, 6)]
        rnd = WipeRandom(colors=pool)
        assert rnd._color_pool == pool

    def test_colors_kwarg_takes_priority_over_color(self):
        rnd = WipeRandom(colors=[(10, 20, 30)], color=(255, 0, 0))
        assert rnd._color_pool == [(10, 20, 30)]

    def test_current_color_comes_from_pool(self, canvas, make_widget):
        pool = [(111, 222, 33), (44, 55, 66)]
        rnd = WipeRandom(colors=pool)
        rnd.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert rnd._current is not None
        assert isinstance(rnd._current, _BaseWipe)
        assert rnd._current.color in pool


class TestWipeRandomMiscellaneous:
    def test_returns_canvas(self, canvas, make_widget):
        rnd = WipeRandom()
        result = rnd.frame_at(0.5, canvas, make_widget(40), make_widget(40))
        assert result is canvas

    def test_min_frames_before_first_swap_is_40(self):
        rnd = WipeRandom()
        assert rnd.min_frames == 40

    def test_min_frames_delegates_to_current_after_first_swap(
        self, canvas, make_widget
    ):
        rnd = WipeRandom()
        rnd.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert rnd.min_frames == rnd._current.min_frames

    def test_registered_as_wipe_random(self):
        assert get_transition_class("wipe_random") is WipeRandom


# --- PushRandom ---


class TestPushRandomNeverRepeatsDirection:
    def _do_swaps(self, rnd, canvas, make_widget, n=20):
        classes = []
        for _ in range(n):
            rnd.frame_at(0.0, canvas, make_widget(40), make_widget(40))
            classes.append(type(rnd._current))
            rnd.frame_at(1.0, canvas, make_widget(40), make_widget(40))
        return classes

    def test_no_consecutive_repeats(self, canvas, make_widget):
        rnd = PushRandom()
        classes = self._do_swaps(rnd, canvas, make_widget)
        for a, b in zip(classes, classes[1:], strict=False):
            assert a is not b, f"Consecutive repeat: {a.__name__}"

    def test_all_four_directions_used_over_many_swaps(self, canvas, make_widget):
        rnd = PushRandom()
        classes = self._do_swaps(rnd, canvas, make_widget, n=40)
        assert set(classes) == {PushLeft, PushRight, PushUp, PushDown}

    def test_first_swap_all_directions_are_candidates(self, canvas, make_widget):
        seen = set()
        for _ in range(60):
            rnd = PushRandom()
            rnd.frame_at(0.0, canvas, make_widget(40), make_widget(40))
            seen.add(type(rnd._current))
        assert seen == {PushLeft, PushRight, PushUp, PushDown}


class TestPushRandomDelegatesFrameAt:
    def test_returns_canvas(self, canvas, make_widget):
        rnd = PushRandom()
        result = rnd.frame_at(0.5, canvas, make_widget(40), make_widget(40))
        assert result is canvas

    def test_forwards_outgoing_scroll_pos(self, canvas, make_widget):
        rnd = PushRandom()
        rnd.frame_at(
            0.0,
            canvas,
            make_widget(600),
            make_widget(40),
            outgoing_scroll_pos=-440,
        )

    def test_min_frames_before_first_swap_is_10(self):
        rnd = PushRandom()
        assert rnd.min_frames == 10

    def test_min_frames_delegates_to_current_after_first_swap(
        self, canvas, make_widget
    ):
        rnd = PushRandom()
        rnd.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert rnd.min_frames == getattr(rnd._current, "min_frames", 10)

    def test_registered_as_push_random(self):
        assert get_transition_class("push_random") is PushRandom


class TestPushRandomMinFrames:
    def test_current_is_set_at_construction(self):
        from led_ticker.transitions.push import PushRandom

        pr = PushRandom()
        assert pr._current is not None

    def test_min_frames_reflects_sub_transition(self):
        from led_ticker.transitions.push import PushRandom

        pr = PushRandom()
        # Must equal the sub-transition's min_frames, not a hardcoded fallback
        expected = getattr(pr._current, "min_frames", 10)
        assert pr.min_frames == expected


class TestDissolveSequenceCache:
    def test_two_instances_same_seed_share_sequence_object(self):
        from led_ticker.transitions.effects import Dissolve

        d1 = Dissolve(seed=7)
        d2 = Dissolve(seed=7)
        seq1 = d1._get_sequence(160, 16)
        seq2 = d2._get_sequence(160, 16)
        assert seq1 is seq2

    def test_different_seed_gives_different_sequence(self):
        from led_ticker.transitions.effects import Dissolve

        d1 = Dissolve(seed=1)
        d2 = Dissolve(seed=2)
        assert d1._get_sequence(160, 16) != d2._get_sequence(160, 16)


# --- run_transition ---


@pytest.fixture
def no_sleep(monkeypatch):
    async def _fast(seconds):
        pass

    monkeypatch.setattr("led_ticker.transitions.asyncio.sleep", _fast)


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

    async def test_pauses_presenters_during_transition(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        # Regression: _FrameAware widgets on outgoing/incoming should be paused
        # for the duration so their frame_count doesn't drift while they're
        # only being re-rendered for compositing.
        outgoing = make_widget(40)
        incoming = make_widget(40)
        outgoing.pause_frame = mock.Mock()
        outgoing.resume_frame = mock.Mock()
        incoming.pause_frame = mock.Mock()
        incoming.resume_frame = mock.Mock()

        await run_transition(
            canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=Cut(),
            duration=0.1,
        )
        outgoing.pause_frame.assert_called_once()
        outgoing.resume_frame.assert_called_once()
        incoming.pause_frame.assert_called_once()
        incoming.resume_frame.assert_called_once()

    async def test_resets_incoming_frame_counter_before_compositor_draws(
        self,
        canvas,
        mock_frame,
        no_sleep,
    ):
        """Tripwire: incoming widget's _frame_count must be reset to 0
        before the transition's first compositor frame fires. Without
        this, a frame-aware widget (typewriter, color_cycle, rainbow)
        renders its previous-visit-end state during the transition,
        then snaps to its visit-initial state when the section begins.

        Hardware-observed bug: §4 of the showroom config (typewriter +
        rainbow) showed the FULL text "READY. SET. GLOW." during the
        wipe-in on loop iteration 2+, then cut to empty and typed out.
        Root cause: run_transition paused incoming frame_count but
        didn't reset it, so the compositor rendered the
        previous-visit-end state."""

        # Custom transition that always calls incoming.draw so we can
        # verify _frame_count seen at draw time. Avoids dependency on
        # any specific built-in transition's frame_at semantics.
        class _AlwaysDrawIncoming:
            def frame_at(self, t, canvas, outgoing, incoming, **kw):
                incoming.draw(canvas, cursor_pos=0)

        incoming = mock.Mock()
        incoming._frame_count = 99  # simulate previous-visit-end state
        seen_frame_counts: list[int] = []

        def _draw(c, cursor_pos=0, **kw):
            seen_frame_counts.append(incoming._frame_count)
            return (c, cursor_pos + 30)

        incoming.draw.side_effect = _draw

        def _reset():
            incoming._frame_count = 0

        incoming.reset_frame.side_effect = _reset

        outgoing = mock.Mock()
        outgoing.draw.side_effect = lambda c, cursor_pos=0, **kw: (
            c,
            cursor_pos + 30,
        )

        await run_transition(
            canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=_AlwaysDrawIncoming(),
            duration=0.1,
        )

        assert seen_frame_counts, "incoming.draw was never called"
        assert all(f == 0 for f in seen_frame_counts), (
            f"Expected _frame_count == 0 throughout the transition; "
            f"got {seen_frame_counts}. Without reset, the compositor "
            f"renders the widget's previous-visit-end state — visible "
            f"as full typewriter text flashing during a wipe-in, then "
            f"snapping back to frame=0 when the section starts."
        )
        # And reset_frame should fire BEFORE pause_frame… actually
        # order doesn't matter (reset doesn't touch the pause flag),
        # but pause must still happen exactly once.
        incoming.pause_frame.assert_called_once()
        incoming.resume_frame.assert_called_once()
        incoming.reset_frame.assert_called_once()

    async def test_resumes_presenters_on_exception(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        outgoing.pause_frame = mock.Mock()
        outgoing.resume_frame = mock.Mock()
        incoming.pause_frame = mock.Mock()
        incoming.resume_frame = mock.Mock()

        broken = mock.Mock(spec=["frame_at"])
        broken.frame_at.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await run_transition(
                canvas,
                mock_frame,
                outgoing,
                incoming,
                transition=broken,
                duration=0.1,
            )
        # The finally block must still resume both presenters.
        outgoing.resume_frame.assert_called_once()
        incoming.resume_frame.assert_called_once()

    async def test_wipe_min_frames_respected(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        """Wipe transitions should use min_frames even with short duration."""
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeLeft()

        await run_transition(
            canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=wipe,
            duration=0.1,  # would be 2 frames normally
            scroll_speed=0.05,
        )
        # min_frames=40, so at least 41 swaps (40 + 1 final)
        assert mock_frame.matrix.SwapOnVSync.call_count == 41

    async def test_non_wipe_unaffected_by_min_frames(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        """Non-wipe transitions should not be affected by min_frames."""
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushLeft()

        await run_transition(
            canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=push,
            duration=0.1,
            scroll_speed=0.05,
        )
        # duration=0.1 / 0.05 = 2 frames + 1 final = 3
        assert mock_frame.matrix.SwapOnVSync.call_count == 3

    async def test_longer_duration_respected_over_min_frames(
        self,
        canvas,
        mock_frame,
        make_widget,
        no_sleep,
    ):
        """User's longer duration should win over min_frames."""
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeLeft()

        await run_transition(
            canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=wipe,
            duration=5.0,  # 100 frames > min_frames=40
            scroll_speed=0.05,
        )
        assert mock_frame.matrix.SwapOnVSync.call_count == 101


# --- ScaledCanvas integration ---


class TestRunTransitionOnScaledCanvas:
    """End-to-end transitions against a ScaledCanvas wrapper.

    The wrapper hides scaling from transition code; these tests verify
    transitions don't blow up when given a wrapper instead of a real canvas.
    """

    @pytest.fixture
    def real_bigsign_canvas(self):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 8
        opts.parallel = 1
        opts.pixel_mapper_config = "U-mapper"
        return RGBMatrix(options=opts).CreateFrameCanvas()

    @pytest.fixture
    def bigsign_frame(self, real_bigsign_canvas):
        import unittest.mock as mock

        frame = mock.Mock()
        frame.get_clean_canvas.return_value = real_bigsign_canvas
        # Real swap returns a different stub canvas each time; mock that
        frame.matrix.SwapOnVSync.side_effect = lambda c: type(real_bigsign_canvas)(
            width=c.width, height=c.height
        )
        return frame

    @pytest.fixture
    def scaled_canvas(self, real_bigsign_canvas):
        from led_ticker.scaled_canvas import ScaledCanvas

        return ScaledCanvas(real_bigsign_canvas, scale=4)

    async def test_cut_runs_against_scaled_canvas(
        self,
        scaled_canvas,
        bigsign_frame,
        make_widget,
        no_sleep,
    ):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        cut = Cut()

        result = await run_transition(
            scaled_canvas,
            bigsign_frame,
            outgoing,
            incoming,
            transition=cut,
            duration=0.1,
        )
        # Returns the wrapper, not the underlying real canvas
        assert result is scaled_canvas

    async def test_color_flash_runs_against_scaled_canvas(
        self,
        scaled_canvas,
        bigsign_frame,
        make_widget,
        no_sleep,
    ):
        """Regression: ColorFlash.frame_at calls canvas.Fill, which the
        wrapper must support."""
        outgoing = make_widget(40)
        incoming = make_widget(40)
        flash = ColorFlash()

        # Should not raise AttributeError on canvas.Fill
        await run_transition(
            scaled_canvas,
            bigsign_frame,
            outgoing,
            incoming,
            transition=flash,
            duration=0.5,
            scroll_speed=0.05,
        )

    async def test_wipe_left_runs_against_scaled_canvas(
        self,
        scaled_canvas,
        bigsign_frame,
        make_widget,
        no_sleep,
    ):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        wipe = WipeLeft()

        await run_transition(
            scaled_canvas,
            bigsign_frame,
            outgoing,
            incoming,
            transition=wipe,
            duration=0.5,
            scroll_speed=0.05,
        )


class TestRunTransitionCrossScale:
    """Regression: when incoming_scale != current scale, run_transition
    must allocate a new wrapper at incoming_scale at t >= 0.5 and dissolve
    the incoming widget in at its native size. Without this, the new
    section's first render snaps to the correct scale AFTER the dissolve,
    causing a visible "flash" at scale-change boundaries (commit e539a47).

    Uses real bigsign canvases + ScaledCanvas to exercise the integration
    end-to-end rather than mocking the wrapper.
    """

    @pytest.fixture
    def real_bigsign_canvas(self):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 8
        opts.parallel = 1
        opts.pixel_mapper_config = "U-mapper"
        return RGBMatrix(options=opts).CreateFrameCanvas()

    @pytest.fixture
    def bigsign_frame(self, real_bigsign_canvas):
        frame = mock.Mock()
        frame.get_clean_canvas.return_value = real_bigsign_canvas
        frame.matrix.SwapOnVSync.side_effect = lambda c: type(real_bigsign_canvas)(
            width=c.width, height=c.height
        )
        # CreateFrameCanvas must return a fresh real canvas (not a ScaledCanvas)
        # — run_transition wraps it itself.
        frame.matrix.CreateFrameCanvas.side_effect = lambda: type(real_bigsign_canvas)(
            width=real_bigsign_canvas.width, height=real_bigsign_canvas.height
        )
        return frame

    async def test_incoming_scale_triggers_wrapper_switch(
        self, real_bigsign_canvas, bigsign_frame, make_widget, no_sleep
    ):
        from led_ticker.scaled_canvas import ScaledCanvas

        outgoing = make_widget(40)
        incoming = make_widget(40)
        outgoing_wrapper = ScaledCanvas(real_bigsign_canvas, scale=2)

        result = await run_transition(
            outgoing_wrapper,
            bigsign_frame,
            outgoing,
            incoming,
            transition=Dissolve(),
            duration=0.5,
            scroll_speed=0.05,
            incoming_scale=4,
        )
        # Once at t=0.5 the wrapper is swapped to scale=4
        assert isinstance(result, ScaledCanvas)
        assert result.scale == 4
        # And exactly one fresh canvas was allocated for the new wrapper
        assert bigsign_frame.matrix.CreateFrameCanvas.call_count == 1

    async def test_same_scale_skips_wrapper_switch(
        self, real_bigsign_canvas, bigsign_frame, make_widget, no_sleep
    ):
        from led_ticker.scaled_canvas import ScaledCanvas

        outgoing = make_widget(40)
        incoming = make_widget(40)
        wrapper = ScaledCanvas(real_bigsign_canvas, scale=4)

        result = await run_transition(
            wrapper,
            bigsign_frame,
            outgoing,
            incoming,
            transition=Dissolve(),
            duration=0.5,
            scroll_speed=0.05,
            incoming_scale=4,  # same as current
        )
        # No re-wrap needed
        assert bigsign_frame.matrix.CreateFrameCanvas.call_count == 0
        # Result is the SAME wrapper (real canvas may have been swapped in-place)
        assert result is wrapper

    async def test_no_incoming_scale_no_switch(
        self, real_bigsign_canvas, bigsign_frame, make_widget, no_sleep
    ):
        from led_ticker.scaled_canvas import ScaledCanvas

        outgoing = make_widget(40)
        incoming = make_widget(40)
        wrapper = ScaledCanvas(real_bigsign_canvas, scale=2)

        await run_transition(
            wrapper,
            bigsign_frame,
            outgoing,
            incoming,
            transition=Dissolve(),
            duration=0.5,
            scroll_speed=0.05,
            # incoming_scale=None → no switch
        )
        assert bigsign_frame.matrix.CreateFrameCanvas.call_count == 0

    async def test_incoming_content_height_threaded_into_wrapper(
        self, real_bigsign_canvas, bigsign_frame, make_widget, no_sleep
    ):
        """Regression: the incoming wrapper must use the new section's
        `content_height` so widgets like TwoRowMessage compute the same
        row positions during the dissolve as `run_swap` will after.
        Without this, a section with `content_height=20` saw its rows
        rendered at y-positions for `content_height=16` during the
        dissolve, then jump to the correct positions when the section
        actually started.
        """
        from led_ticker.scaled_canvas import ScaledCanvas

        outgoing = make_widget(40)
        incoming = make_widget(40)
        outgoing_wrapper = ScaledCanvas(real_bigsign_canvas, scale=4)

        result = await run_transition(
            outgoing_wrapper,
            bigsign_frame,
            outgoing,
            incoming,
            transition=Dissolve(),
            duration=0.5,
            scroll_speed=0.05,
            incoming_scale=2,
            incoming_content_height=20,
        )
        assert isinstance(result, ScaledCanvas)
        assert result.scale == 2
        assert result.height == 20

    async def test_cross_scale_dissolve_handoff_into_play_widget(
        self, real_bigsign_canvas, bigsign_frame, make_widget, no_sleep, tmp_path
    ):
        """End-to-end: dissolve from a normal widget at scale=2 into a
        gif widget (which has play() and paints at native res), then
        immediately call play() on the new wrapper. Verifies the
        run_transition return value can be handed straight to
        `_play_widget` without losing its real-canvas back-buffer.

        Without this test, a regression that returned the OLD wrapper
        from run_transition (instead of the new scale=4 one) would
        slip through — and the gif's first frame would be painted to
        the wrong canvas."""
        import io

        from PIL import Image

        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.ticker import Ticker
        from led_ticker.widgets.gif import GifPlayer

        # Tiny 1-frame gif for the incoming side
        img = Image.new("RGB", (8, 8), color=(200, 80, 40))
        buf = io.BytesIO()
        img.save(buf, format="GIF", save_all=True, append_images=[], duration=50)
        gif_path = tmp_path / "tiny.gif"
        gif_path.write_bytes(buf.getvalue())

        outgoing = make_widget(40)  # plain widget at scale=2
        incoming = GifPlayer(path=str(gif_path), fit="stretch")
        outgoing_wrapper = ScaledCanvas(real_bigsign_canvas, scale=2)

        # Step 1: cross-scale dissolve
        new_wrapper = await run_transition(
            outgoing_wrapper,
            bigsign_frame,
            outgoing,
            incoming,
            transition=Dissolve(),
            duration=0.2,
            scroll_speed=0.05,
            incoming_scale=4,
        )
        assert isinstance(new_wrapper, ScaledCanvas)
        assert new_wrapper.scale == 4

        # Step 2: hand the new wrapper to _play_widget (the real handoff
        # path used by _show_one in run_swap).
        with mock.patch("asyncio.sleep", new=mock.AsyncMock()):
            ticker = Ticker(monitors=[], frame=bigsign_frame)
            result = await ticker._play_widget(new_wrapper, incoming)

        # Result is still the wrapper (rebound to the new back-buffer)
        assert result is new_wrapper
        assert isinstance(new_wrapper.real, type(real_bigsign_canvas))


class TestRunTransitionDurationMs:
    @pytest.mark.asyncio
    async def test_duration_ms_kwarg_passed_to_frame_at(self, mock_frame):
        """run_transition passes duration*1000 as duration_ms kwarg."""
        from led_ticker.transitions import run_transition

        captured: list[dict] = []

        class _CaptureTransition:
            min_frames = 1

            def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
                captured.append(dict(kwargs))
                return canvas

        canvas = mock_frame.get_clean_canvas.return_value
        outgoing = mock.Mock()
        incoming = mock.Mock()
        await run_transition(
            canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=_CaptureTransition(),
            duration=0.5,
        )
        assert captured  # at least one frame ran
        assert all(c.get("duration_ms") == 500 for c in captured)

    @pytest.mark.asyncio
    async def test_duration_ms_reflects_actual_duration(self, mock_frame):
        from led_ticker.transitions import run_transition

        captured: list[int] = []

        class _CaptureTransition:
            min_frames = 1

            def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
                captured.append(kwargs.get("duration_ms"))
                return canvas

        canvas = mock_frame.get_clean_canvas.return_value
        outgoing = mock.Mock()
        incoming = mock.Mock()
        await run_transition(
            canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=_CaptureTransition(),
            duration=1.25,
        )
        assert all(d == 1250 for d in captured)


class TestRunTransitionIncomingBgColor:
    """`incoming_bg_color` lets the panel ramp to the incoming
    section's bg over the second half of the transition (t >= 0.5,
    same threshold as `incoming_scale`). Without this parameter, the
    per-frame reset is `Clear()` (black), and the panel snaps from
    black to the section's bg at t=1.0 — visible as a hard flash on
    bright-bg sections (showroom §8 black→yellow being the worst
    case). Tests pin both the t<0.5 and t>=0.5 behavior plus the
    interaction with `incoming_scale`.
    """

    @pytest.fixture
    def capturing_canvas(self):
        """Stub canvas that records every Clear() and Fill() call.

        Lets the test assert which reset path fired per frame
        without depending on actual pixel state."""
        canvas = mock.MagicMock()
        canvas.width = 64
        canvas.height = 32
        canvas.scale = 1
        # Track the call order so tests can correlate with frame
        # indices via the transition's frame_at side-effect.
        canvas.reset_calls: list[tuple[str, tuple]] = []  # type: ignore[attr-defined]
        canvas.Clear.side_effect = lambda: canvas.reset_calls.append(("Clear", ()))
        canvas.Fill.side_effect = lambda r, g, b: canvas.reset_calls.append(
            ("Fill", (r, g, b))
        )
        return canvas

    async def test_clear_used_when_incoming_bg_color_is_none(
        self, capturing_canvas, mock_frame, no_sleep
    ):
        """Default (None) → every frame uses Clear, matching legacy
        behavior. No regression for sections without bg_color."""
        outgoing = mock.Mock()
        incoming = mock.Mock()
        mock_frame.matrix.SwapOnVSync.return_value = capturing_canvas

        await run_transition(
            capturing_canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=Cut(),
            duration=0.5,
        )

        kinds = [k for k, _ in capturing_canvas.reset_calls]
        assert kinds, "no resets fired — transition didn't loop"
        assert all(k == "Clear" for k in kinds), (
            f"Expected every reset to be Clear when incoming_bg_color=None; "
            f"got {capturing_canvas.reset_calls}"
        )

    async def test_fill_used_after_midpoint_when_incoming_bg_color_set(
        self, capturing_canvas, mock_frame, no_sleep
    ):
        """`incoming_bg_color = (255, 230, 80)` → t<0.5 uses Clear,
        t>=0.5 uses Fill(255, 230, 80). The boundary frame is exactly
        when the section's bg becomes visible — by t=1.0 the panel
        is already on the new bg, eliminating the post-transition
        flash."""
        outgoing = mock.Mock()
        incoming = mock.Mock()
        mock_frame.matrix.SwapOnVSync.return_value = capturing_canvas

        await run_transition(
            capturing_canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=Cut(),
            duration=0.5,
            incoming_bg_color=(255, 230, 80),
        )

        # First frame must be Clear (t=0).
        assert capturing_canvas.reset_calls[0] == ("Clear", ())
        # Last frame must be Fill (t=1.0).
        assert capturing_canvas.reset_calls[-1] == ("Fill", (255, 230, 80)), (
            f"Expected last reset to Fill the incoming bg; got "
            f"{capturing_canvas.reset_calls[-1]}"
        )
        # Some Clear calls AND some Fill calls — the midpoint switch
        # is where the transition crosses t=0.5.
        kinds = [k for k, _ in capturing_canvas.reset_calls]
        assert "Clear" in kinds, "no Clear at all — t<0.5 frames missing"
        assert "Fill" in kinds, "no Fill at all — t>=0.5 frames missing"

    async def test_fill_value_matches_incoming_bg_color(
        self, capturing_canvas, mock_frame, no_sleep
    ):
        """Fill() is called with the exact (r, g, b) from
        `incoming_bg_color` — no normalization or clamping."""
        outgoing = mock.Mock()
        incoming = mock.Mock()
        mock_frame.matrix.SwapOnVSync.return_value = capturing_canvas

        await run_transition(
            capturing_canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=Cut(),
            duration=0.5,
            incoming_bg_color=(42, 0, 16),
        )

        fill_args = [
            args for kind, args in capturing_canvas.reset_calls if kind == "Fill"
        ]
        assert fill_args, "no Fill calls"
        assert all(a == (42, 0, 16) for a in fill_args)

    async def test_accepts_graphics_color_object(
        self, capturing_canvas, mock_frame, no_sleep
    ):
        """Widgets store `bg_color` as `graphics.Color` (after
        `_build_widget`'s coercion). `run_transition` normalizes it
        to a tuple at entry so the inter-widget call site in
        `_run_swap` (which passes `widget.bg_color`) works the same
        as the inter-section call site (which passes a tuple)."""
        from rgbmatrix.graphics import Color

        outgoing = mock.Mock()
        incoming = mock.Mock()
        mock_frame.matrix.SwapOnVSync.return_value = capturing_canvas

        await run_transition(
            capturing_canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=Cut(),
            duration=0.5,
            incoming_bg_color=Color(100, 50, 200),
        )

        fill_args = [
            args for kind, args in capturing_canvas.reset_calls if kind == "Fill"
        ]
        assert fill_args, "graphics.Color not normalized — Fill never fired"
        assert all(a == (100, 50, 200) for a in fill_args)


class TestRunTransitionOutgoingBgColor:
    """`outgoing_bg_color` keeps the OUTGOING section's bg painted at
    t<0.5 of the transition. Without this parameter, the per-frame
    reset is `Clear()` (black) for the entire first half — visible as
    the outgoing's bg disappearing the instant the transition starts
    (e.g. on §5 of the showroom, the dark wine bg vanished before the
    pokeball appeared). With it set, t<0.5 paints `Fill(outgoing_bg)`,
    t>=0.5 honors `incoming_bg_color` (or falls back to Clear if not
    set) — symmetric with the incoming side.
    """

    @pytest.fixture
    def capturing_canvas(self):
        canvas = mock.MagicMock()
        canvas.width = 64
        canvas.height = 32
        canvas.scale = 1
        canvas.reset_calls: list[tuple[str, tuple]] = []  # type: ignore[attr-defined]
        canvas.Clear.side_effect = lambda: canvas.reset_calls.append(("Clear", ()))
        canvas.Fill.side_effect = lambda r, g, b: canvas.reset_calls.append(
            ("Fill", (r, g, b))
        )
        return canvas

    async def test_fill_used_before_midpoint_when_outgoing_bg_color_set(
        self, capturing_canvas, mock_frame, no_sleep
    ):
        """outgoing only → t<0.5 paints Fill(outgoing), t>=0.5 falls
        back to Clear since incoming is None."""
        outgoing = mock.Mock()
        incoming = mock.Mock()
        mock_frame.matrix.SwapOnVSync.return_value = capturing_canvas

        await run_transition(
            capturing_canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=Cut(),
            duration=0.5,
            outgoing_bg_color=(42, 0, 16),
        )

        # First frame (t=0) must be Fill(outgoing).
        assert capturing_canvas.reset_calls[0] == ("Fill", (42, 0, 16))
        # Last frame (t=1.0) must be Clear since incoming is None.
        assert capturing_canvas.reset_calls[-1] == ("Clear", ())
        kinds = [k for k, _ in capturing_canvas.reset_calls]
        assert "Fill" in kinds, "no Fill — t<0.5 frames missing"
        assert "Clear" in kinds, "no Clear — t>=0.5 fallback missing"

    async def test_both_set_paints_outgoing_then_incoming(
        self, capturing_canvas, mock_frame, no_sleep
    ):
        """Both → t<0.5 Fill(outgoing), t>=0.5 Fill(incoming). The
        boundary at t=0.5 is the same point `incoming_scale` switches
        — bg color and scale flip together."""
        outgoing = mock.Mock()
        incoming = mock.Mock()
        mock_frame.matrix.SwapOnVSync.return_value = capturing_canvas

        await run_transition(
            capturing_canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=Cut(),
            duration=0.5,
            outgoing_bg_color=(42, 0, 16),  # wine
            incoming_bg_color=(255, 230, 80),  # yellow
        )

        # First frame is wine, last frame is yellow. No Clear at all.
        assert capturing_canvas.reset_calls[0] == ("Fill", (42, 0, 16))
        assert capturing_canvas.reset_calls[-1] == ("Fill", (255, 230, 80))
        kinds = [k for k, _ in capturing_canvas.reset_calls]
        assert "Clear" not in kinds, (
            "Clear fired even though both bgs are set — "
            "transition flashed black mid-transition"
        )

    async def test_outgoing_accepts_graphics_color_object(
        self, capturing_canvas, mock_frame, no_sleep
    ):
        """Inter-widget call site in `_run_swap` passes
        `prev_object.bg_color` which is a `graphics.Color` after
        `_build_widget` coercion — must normalize the same way as
        `incoming_bg_color`."""
        from rgbmatrix.graphics import Color

        outgoing = mock.Mock()
        incoming = mock.Mock()
        mock_frame.matrix.SwapOnVSync.return_value = capturing_canvas

        await run_transition(
            capturing_canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=Cut(),
            duration=0.5,
            outgoing_bg_color=Color(42, 0, 16),
        )

        fill_args = [
            args for kind, args in capturing_canvas.reset_calls if kind == "Fill"
        ]
        assert fill_args, "graphics.Color not normalized for outgoing"
        assert all(a == (42, 0, 16) for a in fill_args)

    async def test_incoming_bg_color_threaded_to_frame_at(
        self, capturing_canvas, mock_frame, no_sleep
    ):
        """`run_transition` must forward `incoming_bg_color` to
        `frame_at` via kwargs so the hires snap (in `_hires_loader.
        render_hires_frame`) can paint Fill(incoming_bg) instead of
        Clear() at t>=0.95. Without this kwarg the snap clobbers the
        outer Fill — visible as a one-tick "border on black" flash on
        bordered widgets."""
        outgoing = mock.Mock()
        incoming = mock.Mock()
        mock_frame.matrix.SwapOnVSync.return_value = capturing_canvas

        captured_kwargs: list[dict] = []

        class _CaptureTransition:
            min_frames = 1

            def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
                captured_kwargs.append(kwargs)
                return canvas

        await run_transition(
            capturing_canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=_CaptureTransition(),
            duration=0.5,
            incoming_bg_color=(255, 230, 80),
        )

        assert captured_kwargs, "frame_at never called"
        # Exact-set assertion: a refactor that drops `incoming_bg_color`
        # from the forwarding kwargs would slip past a contains-check
        # but break the hires snap (its bg-respect reads kwargs).
        # Likewise, an accidental KEY ADDITION (e.g. typo'd duplicate)
        # surfaces here. Update this set when you legitimately add a
        # kwarg to `run_transition`'s frame_at call.
        expected_keys = {"outgoing_scroll_pos", "duration_ms", "incoming_bg_color"}
        for kw in captured_kwargs:
            assert set(kw.keys()) == expected_keys, (
                f"frame_at kwargs drifted: got {sorted(kw.keys())}, "
                f"expected {sorted(expected_keys)}"
            )
            assert kw["incoming_bg_color"] == (255, 230, 80)

    async def test_boundary_frame_at_t_exactly_half_uses_incoming_bg(
        self, capturing_canvas, mock_frame, no_sleep
    ):
        """At t=0.5 exactly, the reset must use incoming_bg_color
        (the cut-over is `<` vs `>=`). Frame budget is chosen so one
        iteration lands exactly at t=0.5 — Cut.min_frames=1 is
        bypassed by `frame_count = max(min_frames, duration/scroll_speed)`,
        so duration=0.5 + scroll_speed=0.05 yields frame_count=10 and
        i=5 → t=0.5 (linear easing). Pins the inversion of `<` to
        `<=` (or `<` to `>` etc.) at this exact frame."""
        outgoing = mock.Mock()
        incoming = mock.Mock()
        mock_frame.matrix.SwapOnVSync.return_value = capturing_canvas

        await run_transition(
            capturing_canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=Cut(),
            duration=0.5,
            scroll_speed=0.05,
            easing="linear",
            outgoing_bg_color=(42, 0, 16),
            incoming_bg_color=(255, 230, 80),
        )

        # Frames 0..10 → t = 0.0, 0.1, ..., 1.0. Frame index 5 is t=0.5.
        # That frame's reset MUST be Fill(incoming) — the cut-over.
        assert capturing_canvas.reset_calls[5] == ("Fill", (255, 230, 80)), (
            f"frame at t=0.5 should be Fill(incoming); got "
            f"{capturing_canvas.reset_calls[5]}"
        )
        # And frame 4 (t=0.4) must still be the outgoing color.
        assert capturing_canvas.reset_calls[4] == ("Fill", (42, 0, 16)), (
            f"frame at t=0.4 should still be Fill(outgoing); got "
            f"{capturing_canvas.reset_calls[4]}"
        )


class TestHiresSnapRespectsIncomingBg:
    """The hires snap inside `render_hires_frame` and
    `render_hires_baseball_frame` (`_hires_loader.py:_snap_reset`) does
    its own bg-aware reset before drawing incoming at t>=SNAP_THRESHOLD.
    Without it, the snap calls `canvas.Clear()` and the last transition
    frame paints incoming on black — clobbering the Fill(incoming_bg)
    that `run_transition` did one line earlier. The visible artifact
    is a one-tick "incoming text on black" flash before the new
    section's `reset_canvas` finally fills the panel.
    """

    def test_snap_clear_when_incoming_bg_is_none(self):
        """Default → snap calls Clear(). Legacy behavior preserved
        for transitions between two no-bg sections."""
        from led_ticker.transitions._hires_loader import _snap_reset

        canvas = mock.MagicMock()
        _snap_reset(canvas, None)
        canvas.Clear.assert_called_once_with()
        canvas.Fill.assert_not_called()

    def test_snap_fill_when_incoming_bg_set(self):
        """Tuple `(r, g, b)` → snap calls Fill(r, g, b) instead of
        Clear, so the snap-drawn incoming sits on the right bg."""
        from led_ticker.transitions._hires_loader import _snap_reset

        canvas = mock.MagicMock()
        _snap_reset(canvas, (255, 230, 80))
        canvas.Fill.assert_called_once_with(255, 230, 80)
        canvas.Clear.assert_not_called()

    def test_snap_normalizes_graphics_color(self):
        """`_snap_reset` accepts an un-normalized `graphics.Color` —
        future direct callers (outside `run_transition`) that pass a
        widget's `bg_color` (which is a Color post-coercion) work
        without re-normalizing at every site."""
        from rgbmatrix.graphics import Color

        from led_ticker.transitions._hires_loader import _snap_reset

        canvas = mock.MagicMock()
        _snap_reset(canvas, Color(42, 0, 16))
        canvas.Fill.assert_called_once_with(42, 0, 16)
        canvas.Clear.assert_not_called()

    def test_baseball_hires_snap_uses_fill_when_incoming_bg_set(self):
        """End-to-end integration tripwire on the snap path. Drives
        `Baseball.frame_at(t=0.95)` through the hires dispatch (real
        ScaledCanvas → real `render_hires_baseball_frame` →
        `_snap_reset`) with `incoming_bg_color` set, asserts the
        underlying real canvas saw `Fill(...)` and NOT `Clear()`.

        Catches a refactor that drops `kwargs.get('incoming_bg_color')`
        in `_hires_loader.render_hires_baseball_frame` (or
        `render_hires_frame`) and reverts the snap to `canvas.Clear()`
        — that change passes the unit test on `_snap_reset` alone.

        Baseball is fully procedural (no Pillow decode), so this test
        runs without mocking `load_hires` or pre-warming any cache.
        """
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.transitions.baseball import Baseball

        # Mock real canvas. ScaledCanvas.Fill / .Clear delegate to
        # `self.real.Fill` / `self.real.Clear`, so spying on the mock
        # captures both wrapper-level and direct calls.
        real = mock.MagicMock()
        real.width = 256
        real.height = 64
        wrapper = ScaledCanvas(real, scale=4)

        outgoing = mock.Mock()
        incoming = mock.Mock()
        bb = Baseball()

        # t=0.95 is the SNAP_THRESHOLD; t=1.0 short-circuits to the
        # `t >= 1.0` early return BEFORE the hires dispatch, which
        # is a different (also correct) path. 0.95 forces the snap
        # branch inside render_hires_baseball_frame.
        bb.frame_at(
            0.95,
            wrapper,
            outgoing,
            incoming,
            incoming_bg_color=(255, 230, 80),
        )

        # The snap must Fill, not Clear. Outgoing.draw and the trail
        # paint via SetPixel — those don't touch Fill/Clear. So any
        # Fill call here came from _snap_reset.
        assert real.Fill.called, (
            "Baseball hires snap did not call Fill — "
            "`_snap_reset` regressed to `canvas.Clear()`"
        )
        real.Fill.assert_any_call(255, 230, 80)
        real.Clear.assert_not_called()


def test_easing_lookup_unknown_raises():
    """Programmatic use with an unknown easing should fail loudly,
    not silently fall back to linear. Config-load coerces case + checks
    membership upstream, so this is the second-line guard."""
    from led_ticker.transitions import EASING

    with pytest.raises(KeyError):
        _ = EASING["easeout"]


# --- Transition.min_frames Protocol ---


class TestMinFramesProtocol:
    def test_protocol_class_has_zero_default(self):
        """Transition.min_frames class attribute must be 0 so callers that
        access it via the Protocol class get the documented default."""
        from led_ticker.transitions import Transition

        assert Transition.min_frames == 0

    def test_transition_without_min_frames_still_accessible_via_protocol(self):
        """A transition that omits min_frames can still access the default
        via Transition.min_frames = 0 without needing to explicitly define it."""
        from led_ticker.transitions import Transition

        # Verify the default is accessible on the Protocol class
        assert hasattr(Transition, "min_frames")
        assert Transition.min_frames == 0


class TestNyanCatFrameDrawing:
    def test_draw_nyan_frame_uses_subfill_for_rainbow(self, canvas):
        from led_ticker.transitions.nyancat import RAINBOW, draw_nyan_frame

        # At progress=0.5 the trail covers a visible portion of the canvas
        draw_nyan_frame(canvas, progress=0.5, width=160, height=16)
        # 6 rainbow stripes → 6 SubFill calls (one per stripe color)
        assert canvas.SubFill.call_count == len(RAINBOW)

    def test_draw_nyan_frame_rtl_uses_subfill_for_rainbow(self, canvas):
        from led_ticker.transitions.nyancat import RAINBOW, draw_nyan_frame_rtl

        draw_nyan_frame_rtl(canvas, progress=0.5, width=160, height=16)
        assert canvas.SubFill.call_count == len(RAINBOW)
