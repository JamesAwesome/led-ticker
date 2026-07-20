"""Pack wiring through pixel_emoji: slug + unicode + folds + laziness.
Uses the COMMITTED pack (rocket U+1F680 as the canonical pack emoji)."""

import pytest
from rgbmatrix import _StubCanvas

from led_ticker import emoji_pack, pixel_emoji
from led_ticker.pixel_emoji import (
    _map_uemoji_to_slug,
    emoji_slugs,
    has_renderable_emoji,
    is_emoji_slug,
)
from led_ticker.scaled_canvas import ScaledCanvas


@pytest.fixture(autouse=True)
def _fresh():
    emoji_pack._reset_for_tests()
    yield
    emoji_pack._reset_for_tests()


def emoji_pack_slug_for_rocket() -> str:
    emoji_pack.load_index()
    slug = emoji_pack.slug_for_codepoint(0x1F680)
    assert slug
    return slug


class TestSlugSurface:
    def test_pack_slug_is_emoji_slug(self):
        rocket = emoji_pack_slug_for_rocket()
        assert is_emoji_slug(rocket)

    def test_emoji_slugs_includes_pack(self):
        slugs = emoji_slugs()
        assert len(slugs) > 1000  # spec tripwire
        assert "taco" in slugs  # curated intact

    def test_unknown_still_unknown(self):
        assert not is_emoji_slug("dragon_that_does_not_exist_xyz")


class TestUnicodeFold:
    def test_rocket_unicode_maps(self):
        assert _map_uemoji_to_slug("🚀") == emoji_pack_slug_for_rocket()

    def test_curated_unicode_still_wins(self):
        assert _map_uemoji_to_slug("🔥") == "fire"

    def test_skin_tone_folds_to_base(self):
        base = _map_uemoji_to_slug("👍")
        assert base is not None
        assert _map_uemoji_to_slug("👍🏽") == base

    def test_zwj_folds_to_first_base(self):
        first = _map_uemoji_to_slug("👨")
        assert first is not None
        assert _map_uemoji_to_slug("👨‍👩‍👧") == first

    def test_letter_flags_strip(self):
        assert _map_uemoji_to_slug("🇺🇸") is None

    def test_run_scanner_detects_pack_astral(self):
        assert has_renderable_emoji("we are live 🚀 now")

    def test_run_scanner_detects_pack_bmp(self):
        # ☂ U+2602 is BMP; in the pack via the generated allowlist. If the
        # committed manifest lacks it, substitute any PACK_BMP char.
        from led_ticker._emoji_pack_bmp import PACK_BMP

        ch = "☂" if "☂" in PACK_BMP else PACK_BMP[0]
        assert has_renderable_emoji(f"rain {ch} ahead")


class TestDrawPaths:
    def _scaled(self):
        real = _StubCanvas(width=256, height=64)
        return real, ScaledCanvas(real, scale=4, content_height=16)

    def test_pack_slug_draws_hires(self):
        real, canvas = self._scaled()
        rocket = emoji_pack_slug_for_rocket()
        pixel_emoji.draw_emoji_at(canvas, rocket, 0, 0)
        assert real.count_nonzero() > 50  # painted at physical resolution

    def test_pack_unicode_draws_in_text(self):
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import resolve_font

        real, canvas = self._scaled()
        font = resolve_font("Inter-Bold", size=30)
        pixel_emoji.draw_with_emoji(canvas, font, 0, 12, Color(255, 255, 255), "GO 🚀")
        assert real.count_nonzero() > 100

    def test_scale1_pack_slug_strips(self):
        real = _StubCanvas(width=160, height=16)
        rocket = emoji_pack_slug_for_rocket()
        before = real.count_nonzero()
        pixel_emoji.draw_emoji_at(real, rocket, 0, 0)
        assert real.count_nonzero() == before  # hires-only: nothing at scale 1


class TestLaziness:
    def test_curated_draw_never_opens_pack(self, monkeypatch):
        opened = []
        real_load = emoji_pack.load_index
        monkeypatch.setattr(
            emoji_pack,
            "load_index",
            lambda *a, **k: opened.append(1) or real_load(*a, **k),
        )
        canvas = _StubCanvas(width=160, height=16)
        pixel_emoji.draw_emoji_at(canvas, "taco", 0, 0)
        assert opened == []  # curated hit → pack untouched
