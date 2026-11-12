"""The cute / anime 8x8 set (`kawaii_emoji.py`).

Same contract as `test_fall_emoji.py`: the sprite rules every entry must
satisfy, and the "one slug, both signs" behavior — every slug here is a
pack slug whose lowres paints at scale 1 (where the bare pack sprite would
strip), whose hires is still the pack's Noto glyph, and which unicode
reaches too.
"""

import pytest
from rgbmatrix import _StubCanvas

from led_ticker import emoji_pack, pixel_emoji
from led_ticker.kawaii_emoji import (
    _ART,
    KAWAII_LOWRES,
    KAWAII_PACK_FALLBACK_SLUGS,
)
from led_ticker.pixel_emoji import (
    PACK_FALLBACK_SLUGS,
    _get_registry,
    _hires_for,
    _map_uemoji_to_slug,
)


def test_every_slug_is_a_pack_fallback():
    # No curated-only slugs in this set: each one rides the pack's Noto hires.
    assert set(KAWAII_LOWRES) == KAWAII_PACK_FALLBACK_SLUGS
    assert {"cherry_blossom", "steaming_bowl"} == KAWAII_PACK_FALLBACK_SLUGS
    for slug in KAWAII_PACK_FALLBACK_SLUGS:
        assert emoji_pack.has_slug(slug), f"{slug} is not a pack slug"


def test_aggregate_pack_fallback_set_includes_this_set():
    assert PACK_FALLBACK_SLUGS >= KAWAII_PACK_FALLBACK_SLUGS


@pytest.mark.parametrize("slug", sorted(KAWAII_LOWRES))
def test_sprite_fits_8x8_with_valid_colors(slug):
    px = KAWAII_LOWRES[slug]
    assert isinstance(px, list) and px, f"{slug} must be a non-empty pixel list"
    seen = set()
    for x, y, r, g, b in px:
        assert 0 <= x < 8 and 0 <= y < 8, f"{slug}: ({x},{y}) outside 8x8"
        assert all(0 <= c <= 255 for c in (r, g, b)), f"{slug}: bad color"
        assert (x, y) not in seen, f"{slug}: duplicate pixel ({x},{y})"
        seen.add((x, y))


@pytest.mark.parametrize("slug", sorted(KAWAII_LOWRES))
def test_no_invisible_pixels(slug):
    for x, y, r, g, b in KAWAII_LOWRES[slug]:
        assert max(r, g, b) >= 30, f"{slug}: ({x},{y}) is invisible on the panel"


@pytest.mark.parametrize("slug", sorted(KAWAII_LOWRES))
def test_sprite_is_bottom_anchored(slug):
    assert max(y for _, y, *_ in KAWAII_LOWRES[slug]) >= 6, f"{slug} floats"


@pytest.mark.parametrize("slug", sorted(_ART))
def test_art_grid_is_exactly_8x8(slug):
    art = _ART[slug]
    assert len(art) == 8, f"{slug}: {len(art)} rows"
    widths = [len(row) for row in art]
    assert widths == [8] * 8, f"{slug}: ragged rows {widths}"


def test_every_slug_is_in_the_registry():
    reg = _get_registry()
    for slug, px in KAWAII_LOWRES.items():
        assert reg[slug] == px


class TestRenderOnBothSigns:
    @pytest.mark.parametrize("slug", sorted(KAWAII_PACK_FALLBACK_SLUGS))
    def test_lowres_paints_at_scale_1(self, slug):
        canvas = _StubCanvas(width=160, height=16)
        advanced = pixel_emoji.draw_emoji_at(canvas, slug, 0, 0)
        assert advanced > 0
        assert canvas.count_nonzero() == len(KAWAII_LOWRES[slug])

    @pytest.mark.parametrize("slug", sorted(KAWAII_PACK_FALLBACK_SLUGS))
    def test_hires_is_still_the_pack_glyph(self, slug):
        hires = _hires_for(slug)
        assert hires is not None and hires.physical_size == 32
        assert hires is emoji_pack.get_sprite(slug)

    @pytest.mark.parametrize(
        ("char", "slug"),
        [("\U0001f338", "cherry_blossom"), ("\U0001f35c", "steaming_bowl")],
    )
    def test_unicode_reaches_the_lowres_sprite(self, char, slug):
        assert _map_uemoji_to_slug(char) == slug
        assert slug in _get_registry()

    def test_inline_header_renders_both_sprites_at_scale_1(self):
        # The motivating config: the smallsign "Anime News Network" title.
        from led_ticker.fonts import FONT_SMALL

        text_only = pixel_emoji.draw_with_emoji(
            _StubCanvas(width=160, height=16),
            FONT_SMALL,
            cursor_pos=0,
            y=12,
            color=(255, 255, 255),
            text="Anime News Network",
        )
        with_emoji = pixel_emoji.draw_with_emoji(
            _StubCanvas(width=160, height=16),
            FONT_SMALL,
            cursor_pos=0,
            y=12,
            color=(255, 255, 255),
            text=":cherry_blossom: Anime News Network :steaming_bowl:",
        )
        assert with_emoji > text_only
