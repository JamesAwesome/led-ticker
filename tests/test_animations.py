"""Tests for animations module."""

from __future__ import annotations

from led_ticker.animations import AnimationFrame, Typewriter


class TestTypewriter:
    """Slice grows one character per frames_per_char frames."""

    def test_frame_zero_returns_first_char(self):
        anim = Typewriter()
        f = anim.frame_for(0, "WATCH ME", canvas_width=256, text_width=48)
        assert f.visible_text == "W"
        assert f.cursor_override is None

    def test_frame_advances_slice(self):
        # Default frames_per_char=3: 3 frames per char.
        anim = Typewriter()
        # frame=6 → progress = 6//3+1 = 3 chars
        f = anim.frame_for(6, "WATCH ME", canvas_width=256, text_width=48)
        assert f.visible_text == "WAT"

    def test_frame_past_end_clamps_to_full_text(self):
        anim = Typewriter()
        f = anim.frame_for(100, "ABC", canvas_width=256, text_width=18)
        assert f.visible_text == "ABC"

    def test_chars_per_frame_advances_faster(self):
        # 2 chars per "step", default 3 frames per step
        anim = Typewriter(chars_per_frame=2, frames_per_char=1)
        f = anim.frame_for(0, "ABCDEF", canvas_width=256, text_width=36)
        assert f.visible_text == "AB"
        f = anim.frame_for(1, "ABCDEF", canvas_width=256, text_width=36)
        assert f.visible_text == "ABCD"

    def test_frames_per_char_slows_typing(self):
        anim = Typewriter(frames_per_char=5)
        # frame=4 → progress = 4//5+1 = 1 char
        f = anim.frame_for(4, "ABCDEF", canvas_width=256, text_width=36)
        assert f.visible_text == "A"
        # frame=10 → progress = 10//5+1 = 3 chars
        f = anim.frame_for(10, "ABCDEF", canvas_width=256, text_width=36)
        assert f.visible_text == "ABC"


class TestAnimationFrame:
    def test_dataclass_construction(self):
        f = AnimationFrame(visible_text="HI", cursor_override=10)
        assert f.visible_text == "HI"
        assert f.cursor_override == 10

    def test_cursor_override_can_be_none(self):
        f = AnimationFrame(visible_text="HI", cursor_override=None)
        assert f.cursor_override is None
