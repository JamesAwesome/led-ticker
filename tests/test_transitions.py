"""Tests for transition effects."""

import asyncio

import pytest

from led_ticker.transition import (
    _TRANSITION_REGISTRY,
    ColorFlash,
    Cut,
    PushLeft,
    PushRight,
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
    def test_all_phase1_transitions_registered(self):
        for name in ["cut", "push_left", "push_right",
                      "color_flash", "wipe_left", "wipe_right"]:
            assert name in _TRANSITION_REGISTRY

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
    def test_at_zero_shows_outgoing(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushLeft()
        push.frame_at(0.0, canvas, outgoing, incoming)
        # At t=0, offset=0: outgoing at 0, incoming at canvas.width
        outgoing.draw.assert_called_once()
        incoming.draw.assert_called_once()
        # outgoing drawn at cursor_pos=0
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == 0
        # incoming drawn at cursor_pos=160
        assert incoming.draw.call_args.kwargs["cursor_pos"] == 160

    def test_at_one_shows_incoming(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushLeft()
        push.frame_at(1.0, canvas, outgoing, incoming)
        # At t=1, offset=160: outgoing at -160, incoming at 0
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -160
        assert incoming.draw.call_args.kwargs["cursor_pos"] == 0

    def test_at_midpoint_both_visible(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushLeft()
        push.frame_at(0.5, canvas, outgoing, incoming)
        assert outgoing.draw.call_args.kwargs["cursor_pos"] == -80
        assert incoming.draw.call_args.kwargs["cursor_pos"] == 80


# --- PushRight ---


class TestPushRight:
    def test_at_one_incoming_at_origin(self, canvas, make_widget):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushRight()
        push.frame_at(1.0, canvas, outgoing, incoming)
        assert incoming.draw.call_args.kwargs["cursor_pos"] == 0


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


# --- run_transition ---


@pytest.fixture
def no_sleep(monkeypatch):
    _real_sleep = asyncio.sleep

    async def _fast(seconds):
        await _real_sleep(0)

    monkeypatch.setattr("led_ticker.transition.asyncio.sleep", _fast)


class TestRunTransition:
    async def test_runs_correct_frame_count(
        self, canvas, mock_frame, make_widget, no_sleep,
    ):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        push = PushLeft()

        await run_transition(
            canvas, mock_frame, outgoing, incoming,
            transition=push, duration=0.5, scroll_speed=0.05,
        )
        # duration=0.5 / scroll_speed=0.05 = 10 frames + 1 final
        assert mock_frame.matrix.SwapOnVSync.call_count == 11

    async def test_final_frame_shows_incoming(
        self, canvas, mock_frame, make_widget, no_sleep,
    ):
        outgoing = make_widget(40)
        incoming = make_widget(40)
        cut = Cut()

        await run_transition(
            canvas, mock_frame, outgoing, incoming,
            transition=cut, duration=0.1,
        )
        # Last call should be incoming drawn at cursor_pos=0
        incoming.draw.assert_called()
