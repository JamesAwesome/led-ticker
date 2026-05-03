"""Tests for the hi-res transition registry, loader, and renderer."""

from __future__ import annotations


class TestHiresRegistry:
    def test_registry_has_exactly_four_entries(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        assert set(HIRES_REGISTRY.keys()) == {
            "nyancat",
            "nyancat_reverse",
            "pokeball",
            "pokeball_reverse",
        }

    def test_nyancat_uses_webp_no_flip(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        spec = HIRES_REGISTRY["nyancat"]
        assert spec.sprite_path.name == "nyancat.webp"
        assert spec.flip_horizontal is False

    def test_nyancat_reverse_uses_same_file_with_flip(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        base = HIRES_REGISTRY["nyancat"]
        rev = HIRES_REGISTRY["nyancat_reverse"]
        assert rev.sprite_path == base.sprite_path
        assert rev.flip_horizontal is True

    def test_pokeball_uses_gif_no_flip(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        spec = HIRES_REGISTRY["pokeball"]
        assert spec.sprite_path.name == "pokeball.gif"
        assert spec.flip_horizontal is False

    def test_pokeball_reverse_uses_same_file_with_flip(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        base = HIRES_REGISTRY["pokeball"]
        rev = HIRES_REGISTRY["pokeball_reverse"]
        assert rev.sprite_path == base.sprite_path
        assert rev.flip_horizontal is True

    def test_sprite_paths_are_absolute_and_exist(self):
        from led_ticker.transitions._hires_registry import HIRES_REGISTRY

        for name, spec in HIRES_REGISTRY.items():
            assert spec.sprite_path.is_absolute(), f"{name} path not absolute"
            assert spec.sprite_path.exists(), f"{name} sprite file missing"
