"""The autumn / Halloween 8x8 set (`fall_emoji.py`).

Two things are pinned here: the sprite rules every entry must satisfy, and
the "one slug, both signs" behavior for the pack-fallback slugs — lowres
paints at scale 1 (where the bare pack sprite would strip), the pack's Noto
glyph still resolves as the hires, and unicode reaches the same sprite.
"""

import pytest
from rgbmatrix import _StubCanvas

from led_ticker import emoji_pack, pixel_emoji
from led_ticker.fall_emoji import FALL_LOWRES, FALL_PACK_FALLBACK_SLUGS
from led_ticker.pixel_emoji import _get_registry, _hires_for, _map_uemoji_to_slug

CURATED_ONLY = {"pumpkin", "acorn", "candy_corn"}


def test_slug_partition():
    assert set(FALL_LOWRES) >= FALL_PACK_FALLBACK_SLUGS
    assert set(FALL_LOWRES) - FALL_PACK_FALLBACK_SLUGS == CURATED_ONLY
    for slug in CURATED_ONLY:
        assert not emoji_pack.has_slug(slug), f"{slug} is in the pack after all"


@pytest.mark.parametrize("slug", sorted(FALL_LOWRES))
def test_sprite_fits_8x8_with_valid_colors(slug):
    px = FALL_LOWRES[slug]
    assert isinstance(px, list) and px, f"{slug} must be a non-empty pixel list"
    seen = set()
    for x, y, r, g, b in px:
        assert 0 <= x < 8 and 0 <= y < 8, f"{slug}: ({x},{y}) outside 8x8"
        assert all(0 <= c <= 255 for c in (r, g, b)), f"{slug}: bad color"
        assert (x, y) not in seen, f"{slug}: duplicate pixel ({x},{y})"
        seen.add((x, y))


@pytest.mark.parametrize("slug", sorted(FALL_LOWRES))
def test_no_invisible_pixels(slug):
    # A pure-black pixel is indistinguishable from an unlit LED; "black"
    # features (eyes, mouths) must use a visible dark gray instead.
    for x, y, r, g, b in FALL_LOWRES[slug]:
        assert max(r, g, b) >= 30, f"{slug}: ({x},{y}) is invisible on the panel"


@pytest.mark.parametrize("slug", sorted(FALL_LOWRES))
def test_sprite_is_bottom_anchored(slug):
    # Inline lowres emoji bottom-anchor at `baseline - 8`; a sprite whose
    # lowest lit row is above row 6 floats visibly above the text.
    assert max(y for _, y, *_ in FALL_LOWRES[slug]) >= 6, f"{slug} floats"


def test_every_slug_is_in_the_registry():
    reg = _get_registry()
    for slug, px in FALL_LOWRES.items():
        assert reg[slug] == px


class TestPackFallbackSlugsRenderOnBothSigns:
    def test_lowres_paints_at_scale_1(self):
        # Contrast with test_pixel_emoji_pack_wiring::test_scale1_pack_slug_strips:
        # a bare pack slug paints nothing at scale 1; a fall slug paints its 8x8.
        canvas = _StubCanvas(width=160, height=16)
        advanced = pixel_emoji.draw_emoji_at(canvas, "jack_o_lantern", 0, 0)
        assert advanced > 0
        assert canvas.count_nonzero() == len(FALL_LOWRES["jack_o_lantern"])

    def test_scale_1_draw_never_opens_the_pack(self, monkeypatch):
        opened = []
        real_load = emoji_pack.load_index
        monkeypatch.setattr(
            emoji_pack,
            "load_index",
            lambda *a, **k: opened.append(1) or real_load(*a, **k),
        )
        canvas = _StubCanvas(width=160, height=16)
        pixel_emoji.draw_emoji_at(canvas, "ghost", 0, 0)
        assert opened == []

    @pytest.mark.parametrize("slug", sorted(FALL_PACK_FALLBACK_SLUGS))
    def test_hires_is_still_the_pack_glyph(self, slug):
        hires = _hires_for(slug)
        assert hires is not None and hires.physical_size == 32
        assert hires is emoji_pack.get_sprite(slug)

    def test_unicode_reaches_the_lowres_sprite(self):
        slug = _map_uemoji_to_slug("\U0001f383")  # 🎃
        assert slug == "jack_o_lantern"
        assert slug in _get_registry()

    def test_inline_text_renders_the_sprite_at_scale_1(self):
        from led_ticker.fonts import FONT_SMALL

        canvas = _StubCanvas(width=160, height=16)
        text_only = pixel_emoji.draw_with_emoji(
            canvas, FONT_SMALL, cursor_pos=0, y=12, color=(255, 255, 255), text="BOO"
        )
        with_emoji = pixel_emoji.draw_with_emoji(
            _StubCanvas(width=160, height=16),
            FONT_SMALL,
            cursor_pos=0,
            y=12,
            color=(255, 255, 255),
            text="BOO :ghost:",
        )
        assert with_emoji > text_only
