"""Assertions on the COMMITTED pack artifacts (no network, no generation)."""

import re
from pathlib import Path

from led_ticker import emoji_pack

_MANIFEST = Path(__file__).parent.parent / "tools" / "assets" / "emoji_manifest.txt"
_SLUG_RE = re.compile(r"^[a-z_][a-z0-9_.]*$")


class TestManifest:
    def test_slugs_valid_and_unique(self):
        slugs = [ln.split("\t")[1] for ln in _MANIFEST.read_text().splitlines()]
        assert len(slugs) > 1000  # size tripwire (spec)
        assert len(set(slugs)) == len(slugs)
        for s in slugs:
            assert _SLUG_RE.match(s), s

    def test_no_curated_collisions(self):
        from led_ticker.pixel_emoji import HIRES_REGISTRY, _get_registry

        curated = set(_get_registry()) | set(HIRES_REGISTRY)
        packed = {ln.split("\t")[1] for ln in _MANIFEST.read_text().splitlines()}
        assert not (curated & packed), curated & packed


class TestCommittedPack:
    def test_loads_and_matches_manifest(self):
        emoji_pack._reset_for_tests()
        assert emoji_pack.load_index() is True
        packed = set(emoji_pack.pack_slugs())
        manifest = {ln.split("\t")[1] for ln in _MANIFEST.read_text().splitlines()}
        assert packed == manifest
        assert len(packed) > 1000

    def test_spot_sprite_decodes(self):
        emoji_pack._reset_for_tests()
        emoji_pack.load_index()
        slug = emoji_pack.slug_for_codepoint(0x1F680)  # 🚀 rocket
        assert slug is not None
        s = emoji_pack.get_sprite(slug)
        assert s is not None and len(s.pixels) > 50

    def test_bmp_module_matches_pack(self):
        from led_ticker._emoji_pack_bmp import PACK_BMP

        emoji_pack._reset_for_tests()
        emoji_pack.load_index()
        pack_bmp = set(PACK_BMP)
        for ch in pack_bmp:
            assert emoji_pack.slug_for_codepoint(ord(ch)) is not None
