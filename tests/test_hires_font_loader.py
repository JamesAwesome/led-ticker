"""Tests for the hi-res font loader."""

from __future__ import annotations


class TestHiresGlyphDataclass:
    def test_constructs_with_required_fields(self):
        from led_ticker.fonts.hires_loader import HiresGlyph

        glyph = HiresGlyph(
            width=10,
            height=20,
            advance=12,
            bearing_x=0,
            bearing_y=18,
            lit=((0, 0), (1, 1)),
        )
        assert glyph.width == 10
        assert glyph.lit == ((0, 0), (1, 1))

    def test_is_frozen(self):
        from led_ticker.fonts.hires_loader import HiresGlyph

        glyph = HiresGlyph(
            width=10, height=20, advance=12, bearing_x=0, bearing_y=18, lit=()
        )
        try:
            glyph.width = 99
        except Exception as e:  # noqa: BLE001
            assert "FrozenInstanceError" in type(e).__name__
            return
        raise AssertionError("expected FrozenInstanceError on attribute set")


class TestHiresFontDataclass:
    def test_constructs(self):
        from led_ticker.fonts.hires_loader import HiresFont, HiresGlyph

        glyph = HiresGlyph(
            width=10, height=20, advance=12, bearing_x=0, bearing_y=18, lit=()
        )
        font = HiresFont(
            name="test",
            size=32,
            ascent=30,
            descent=8,
            line_height=38,
            glyphs={"A": glyph},
        )
        assert font.name == "test"
        assert font.size == 32
        assert font.glyphs["A"] is glyph

    def test_is_frozen(self):
        from led_ticker.fonts.hires_loader import HiresFont

        font = HiresFont(
            name="t", size=8, ascent=6, descent=2, line_height=8, glyphs={}
        )
        try:
            font.size = 99
        except Exception as e:  # noqa: BLE001
            assert "FrozenInstanceError" in type(e).__name__
            return
        raise AssertionError("expected FrozenInstanceError on attribute set")


class TestThresholdConstant:
    def test_threshold_is_at_50_percent(self):
        from led_ticker.fonts.hires_loader import THRESHOLD

        # 50% of 0-255 ≈ 128
        assert THRESHOLD == 128
