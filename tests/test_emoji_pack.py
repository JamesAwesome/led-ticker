"""Pack format + lazy loader. Uses a synthetic fixture pack — no network,
no dependency on the committed asset (that's test_emoji_pack_asset.py)."""

from pathlib import Path

import pytest

from led_ticker import emoji_pack


@pytest.fixture(autouse=True)
def _fresh_pack_state():
    emoji_pack._reset_for_tests()
    yield
    emoji_pack._reset_for_tests()


def _fixture_entries():
    # two tiny sprites: a 2x2 red square and a single green px
    sq = [(0, 0, 255, 0, 0), (1, 0, 255, 0, 0), (0, 1, 255, 0, 0), (1, 1, 255, 0, 0)]
    dot = [(5, 5, 0, 255, 0)]
    return [("red_square", 0x1F7E5, sq), ("green_dot", 0x1F7E9, dot)]


class TestRoundTrip:
    def test_write_then_read_pixel_identical(self, tmp_path: Path):
        p = tmp_path / "fixture.bin"
        emoji_pack.write_pack(_fixture_entries(), p)
        assert emoji_pack.load_index(p) is True
        assert emoji_pack.pack_slugs() == ("green_dot", "red_square")
        s = emoji_pack.get_sprite("red_square")
        assert s is not None
        assert s.physical_size == 32
        assert sorted(s.pixels) == sorted(tuple(px) for px in _fixture_entries()[0][2])

    def test_codepoint_lookup(self, tmp_path: Path):
        p = tmp_path / "fixture.bin"
        emoji_pack.write_pack(_fixture_entries(), p)
        emoji_pack.load_index(p)
        assert emoji_pack.slug_for_codepoint(0x1F7E9) == "green_dot"
        assert emoji_pack.slug_for_codepoint(0x1F525) is None

    def test_has_slug(self, tmp_path: Path):
        p = tmp_path / "fixture.bin"
        emoji_pack.write_pack(_fixture_entries(), p)
        emoji_pack.load_index(p)
        assert emoji_pack.has_slug("red_square")
        assert not emoji_pack.has_slug("rocket")


class TestDegradation:
    def test_missing_file_is_pack_absent(self, tmp_path: Path):
        assert emoji_pack.load_index(tmp_path / "nope.bin") is False
        assert emoji_pack.pack_slugs() == ()
        assert emoji_pack.get_sprite("anything") is None

    def test_bad_magic_is_pack_absent(self, tmp_path: Path):
        p = tmp_path / "bad.bin"
        p.write_bytes(b"NOPE" + b"\x00" * 32)
        assert emoji_pack.load_index(p) is False
        assert emoji_pack.pack_slugs() == ()

    def test_wrong_version_is_pack_absent(self, tmp_path: Path):
        p = tmp_path / "v9.bin"
        emoji_pack.write_pack(_fixture_entries(), p)
        raw = bytearray(p.read_bytes())
        raw[4:6] = (99).to_bytes(2, "little")
        p.write_bytes(bytes(raw))
        assert emoji_pack.load_index(p) is False

    def test_truncated_payload_returns_none_not_raise(self, tmp_path: Path):
        p = tmp_path / "trunc.bin"
        emoji_pack.write_pack(_fixture_entries(), p)
        p.write_bytes(p.read_bytes()[:-3])
        emoji_pack.load_index(p)
        assert emoji_pack.get_sprite("red_square") is None  # logged, not raised


class TestLaziness:
    def test_sprite_decode_is_lazy_and_cached(self, tmp_path: Path, monkeypatch):
        p = tmp_path / "fixture.bin"
        emoji_pack.write_pack(_fixture_entries(), p)
        emoji_pack.load_index(p)
        calls = []
        real = emoji_pack.zlib.decompress
        monkeypatch.setattr(
            emoji_pack.zlib, "decompress", lambda b: calls.append(1) or real(b)
        )
        assert calls == []  # index load decoded nothing
        emoji_pack.get_sprite("green_dot")
        assert len(calls) == 1
        emoji_pack.get_sprite("green_dot")
        assert len(calls) == 1  # cached
