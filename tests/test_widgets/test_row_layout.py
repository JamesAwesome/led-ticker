"""Unit tests for `row_layout` centering math.

These tests exercise the function directly, bypassing the widget
wrappers. Widget-level integration tests live in test_two_row.py
and test_image_base.py.
"""

from types import SimpleNamespace

from led_ticker.fonts import FONT_SMALL
from led_ticker.widgets._row_layout import row_layout


class TestRowLayoutSpriteHeight:
    """`sprite_logical_height` parameter centers the actual sprite,
    not the EMOJI_ROW_CAP-tall low-res default."""

    def test_default_sprite_height_preserves_legacy_centering(self):
        """Callers that don't pass `sprite_logical_height` get the
        old EMOJI_ROW_CAP-based centering — back-compat for any
        external caller of row_layout."""
        canvas = SimpleNamespace(height=16, scale=2, width=128)
        # 16-row band, default sprite_logical_height = 8:
        # emoji_y = (16 - 8) // 2 + 0 = 4 (old buggy default)
        _, emoji_y = row_layout(canvas, FONT_SMALL, band_height=16, band_offset=0)
        assert emoji_y == 4

    def test_full_band_sprite_anchors_at_band_top(self):
        """Sprite exactly fills the band — emoji_y should be 0
        (or band_offset for non-zero offsets).

        This is the original `:instagram:` + top_row_height=16 case
        that produced the bleed into the bottom band."""
        canvas = SimpleNamespace(height=16, scale=2, width=128)
        _, emoji_y = row_layout(
            canvas,
            FONT_SMALL,
            band_height=16,
            band_offset=0,
            sprite_logical_height=16,
        )
        # (16 - 16) // 2 + 0 = 0
        assert emoji_y == 0

    def test_sprite_smaller_than_band_centers(self):
        """8-row sprite in a 16-row band — centered at row 4."""
        canvas = SimpleNamespace(height=16, scale=2, width=128)
        _, emoji_y = row_layout(
            canvas,
            FONT_SMALL,
            band_height=16,
            band_offset=0,
            sprite_logical_height=8,
        )
        # (16 - 8) // 2 + 0 = 4
        assert emoji_y == 4

    def test_sprite_taller_than_band_clamps_to_band_top(self):
        """Sprite logically taller than its band — formula would
        return negative emoji_y; clamp to band_offset so the top
        edge of the sprite anchors at the top of the band (the
        bottom bleeds into the next band, which is the existing
        documented behavior for tiny bands)."""
        canvas = SimpleNamespace(height=16, scale=2, width=128)
        _, emoji_y = row_layout(
            canvas,
            FONT_SMALL,
            band_height=8,
            band_offset=0,
            sprite_logical_height=16,
        )
        # (8 - 16) // 2 + 0 = -4 → clamped to 0
        assert emoji_y == 0

    def test_non_zero_band_offset_threads_through(self):
        """Bottom-row band starts at band_offset > 0. The centering
        result is relative to band_offset, not to canvas y=0."""
        canvas = SimpleNamespace(height=24, scale=2, width=128)
        _, emoji_y = row_layout(
            canvas,
            FONT_SMALL,
            band_height=8,
            band_offset=16,
            sprite_logical_height=8,
        )
        # (8 - 8) // 2 + 16 = 16
        assert emoji_y == 16
