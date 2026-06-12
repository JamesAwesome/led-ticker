"""Inventory enumeration: fonts, assets, emoji."""

from led_ticker.webui.inventory import ASSET_CAP, build_inventory


def test_user_fonts_listed(tmp_path):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / "custom.ttf").write_bytes(b"x")
    (fonts / "pixel.bdf").write_bytes(b"x")
    inv = build_inventory(tmp_path)
    assert inv["fonts"]["user"] == ["custom.ttf", "pixel.bdf"]


def test_user_fonts_missing_dir_is_empty(tmp_path):
    assert build_inventory(tmp_path)["fonts"]["user"] == []


def test_bundled_fonts_nonempty_and_sorted(tmp_path):
    bundled = build_inventory(tmp_path)["fonts"]["bundled"]
    assert any(b.endswith(".bdf") for b in bundled)  # 5x8.bdf etc.
    assert bundled == sorted(bundled)


def test_assets_recursive_with_sizes(tmp_path):
    (tmp_path / "gifs").mkdir()
    (tmp_path / "gifs" / "cat.gif").write_bytes(b"GIF89a")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG")
    (tmp_path / "config.toml").write_text("[display]\n")  # not an asset
    inv = build_inventory(tmp_path)
    paths = {a["path"] for a in inv["assets"]}
    assert paths == {"gifs/cat.gif", "logo.png"}
    assert all(a["bytes"] > 0 for a in inv["assets"])
    assert inv["assets_truncated"] is False


def test_assets_truncate_at_cap(tmp_path):
    for i in range(ASSET_CAP + 5):
        (tmp_path / f"a{i:04d}.png").write_bytes(b"x")
    inv = build_inventory(tmp_path)
    assert len(inv["assets"]) == ASSET_CAP
    assert inv["assets_truncated"] is True


def test_emoji_registries_materialized(tmp_path):
    inv = build_inventory(tmp_path)
    assert len(inv["emoji"]["core"]) > 0  # lazy registry must be materialized
    # hires_only is exactly the hires slugs that lack a low-res fallback
    assert not set(inv["emoji"]["hires_only"]) & set(inv["emoji"]["core"])
