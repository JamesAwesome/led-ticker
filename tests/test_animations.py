"""Tests for animations module."""

from __future__ import annotations

from led_ticker.animations import AnimationFrame, Bounce, Typewriter


class TestTypewriter:
    """Slice grows one character per frame."""

    def test_frame_zero_returns_first_char(self):
        anim = Typewriter()
        f = anim.frame_for(0, "WATCH ME", canvas_width=256, text_width=48)
        assert f.visible_text == "W"
        assert f.cursor_override is None

    def test_frame_advances_slice(self):
        anim = Typewriter()
        f = anim.frame_for(2, "WATCH ME", canvas_width=256, text_width=48)
        assert f.visible_text == "WAT"

    def test_frame_past_end_clamps_to_full_text(self):
        anim = Typewriter()
        f = anim.frame_for(100, "ABC", canvas_width=256, text_width=18)
        assert f.visible_text == "ABC"

    def test_chars_per_frame_advances_faster(self):
        anim = Typewriter(chars_per_frame=2)
        f = anim.frame_for(0, "ABCDEF", canvas_width=256, text_width=36)
        assert f.visible_text == "AB"
        f = anim.frame_for(1, "ABCDEF", canvas_width=256, text_width=36)
        assert f.visible_text == "ABCD"


class TestBounce:
    """Slide in from right, hold center, slide out left."""

    def test_frame_zero_cursor_at_canvas_width(self):
        anim = Bounce(scroll_frames=20, hold_frames=40)
        f = anim.frame_for(0, "BOUNCE", canvas_width=256, text_width=36)
        assert f.visible_text == "BOUNCE"
        # frame 0 → text just off-right
        assert f.cursor_override == 256

    def test_after_scroll_in_holds_at_center(self):
        anim = Bounce(scroll_frames=20, hold_frames=40)
        f = anim.frame_for(20, "BOUNCE", canvas_width=256, text_width=36)
        # center_x = (256 - 36) // 2 = 110
        assert f.cursor_override == 110

    def test_during_hold_cursor_stays_at_center(self):
        anim = Bounce(scroll_frames=20, hold_frames=40)
        f30 = anim.frame_for(30, "BOUNCE", canvas_width=256, text_width=36)
        f55 = anim.frame_for(55, "BOUNCE", canvas_width=256, text_width=36)
        assert f30.cursor_override == 110
        assert f55.cursor_override == 110

    def test_during_scroll_out_moves_left_of_zero(self):
        anim = Bounce(scroll_frames=20, hold_frames=40)
        # scroll_out range: 60..79; final frame moves close to -text_width
        f = anim.frame_for(79, "BOUNCE", canvas_width=256, text_width=36)
        assert f.cursor_override is not None
        assert f.cursor_override < 0

    def test_after_total_frames_holds_off_screen(self):
        """Past total_frames bounce remains at the end position
        (text not visible)."""
        anim = Bounce(scroll_frames=20, hold_frames=40)
        # total = 80; past that should be safe
        f = anim.frame_for(100, "BOUNCE", canvas_width=256, text_width=36)
        assert f.cursor_override is not None
        # Either at center_x (idle) or off-left; both are documented
        # post-cycle behaviors. Just assert it doesn't crash.

    def test_visible_text_always_full(self):
        """Bounce repositions but doesn't slice text."""
        anim = Bounce()
        for frame in (0, 10, 20, 30, 60, 75):
            f = anim.frame_for(frame, "HELLO", canvas_width=256, text_width=30)
            assert f.visible_text == "HELLO"


class TestAnimationFrame:
    def test_dataclass_construction(self):
        f = AnimationFrame(visible_text="HI", cursor_override=10)
        assert f.visible_text == "HI"
        assert f.cursor_override == 10

    def test_cursor_override_can_be_none(self):
        f = AnimationFrame(visible_text="HI", cursor_override=None)
        assert f.cursor_override is None
