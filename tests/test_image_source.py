"""ImageSource: decode -> stage -> commit; boot never darks."""

from pathlib import Path

import pytest
from PIL import Image

from led_ticker import pixel_emoji
from led_ticker.pixel_emoji import abort_image_emoji
from led_ticker.sources import ImageSource, load_image_sprites


@pytest.fixture(autouse=True)
def _clean():
    abort_image_emoji()
    for slug in list(pixel_emoji._CONFIG_IMAGE_SLUGS):
        pixel_emoji.EMOJI_REGISTRY.pop(slug, None)
        pixel_emoji.HIRES_REGISTRY.pop(slug, None)
    pixel_emoji._CONFIG_IMAGE_SLUGS.clear()
    yield
    abort_image_emoji()
    for slug in list(pixel_emoji._CONFIG_IMAGE_SLUGS):
        pixel_emoji.EMOJI_REGISTRY.pop(slug, None)
        pixel_emoji.HIRES_REGISTRY.pop(slug, None)
    pixel_emoji._CONFIG_IMAGE_SLUGS.clear()


def _png(tmp_path: Path, name="logo.png", size=(64, 64)) -> Path:
    img = Image.new("RGBA", size, (255, 0, 0, 255))
    p = tmp_path / name
    img.save(p)
    return p


def _gif(tmp_path: Path, name="anim.gif") -> Path:
    frames = [Image.new("RGB", (40, 40), c) for c in ((255, 0, 0), (0, 255, 0))]
    p = tmp_path / name
    frames[0].save(p, save_all=True, append_images=frames[1:], duration=100)
    return p


class TestLoadImageSprites:
    def test_png_builds_both_forms(self, tmp_path):
        lowres, hires = load_image_sprites(_png(tmp_path))
        assert lowres and all(len(px) == 5 for px in lowres)
        assert max(p[0] for p in lowres) <= 7 and max(p[1] for p in lowres) <= 7
        assert hires.physical_size == 32
        assert hires.pixels  # opaque red square -> fully lit
        assert hires.physical_width and hires.physical_width <= 128

    def test_gif_uses_frame_zero(self, tmp_path):
        lowres, hires = load_image_sprites(_gif(tmp_path))
        # frame 0 is red; every lit pixel red-dominant
        assert all(px[2] > px[3] for px in hires.pixels)  # r > g

    def test_wide_image_caps_at_128(self, tmp_path):
        _, hires = load_image_sprites(_png(tmp_path, size=(1000, 40)))
        assert max(p[0] for p in hires.pixels) <= 127

    def test_transparent_pixels_dropped(self, tmp_path):
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        img.putpixel((0, 0), (255, 255, 255, 255))
        p = tmp_path / "dot.png"
        img.save(p)
        lowres, hires = load_image_sprites(p)
        assert len(hires.pixels) < 32 * 32  # alpha<110 dropped

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(Exception, match="no-such"):
            load_image_sprites(tmp_path / "no-such.png")


class TestImageSourceStaging:
    def test_build_stages_but_does_not_commit(self, tmp_path):
        src = ImageSource(id="cart.logo", path=str(_png(tmp_path)))
        src.prepare()  # decode + stage
        assert "cart.logo" in pixel_emoji._PENDING_IMAGE_EMOJI
        assert "cart.logo" not in pixel_emoji._get_registry()

    def test_compute_returns_literal_token(self, tmp_path):
        # Defensive value if token resolution ever sees it (it should not:
        # is_emoji_slug excludes registered slugs from _candidate_ids).
        src = ImageSource(id="cart.logo", path=str(_png(tmp_path)))
        assert src.compute() == ":cart.logo:"


class TestBootWiring:
    def test_bad_image_source_skips_not_raises(self, tmp_path):
        # build_source_registry's per-source try/except must swallow a
        # decode failure: the registry builds, the panel boots.
        from led_ticker.app.run import build_source_registry
        from led_ticker.config import SourceConfig

        good = SourceConfig(type="static", id="ok", raw={"value": "x"})
        bad = SourceConfig(
            type="image", id="broken", raw={"path": str(tmp_path / "nope.png")}
        )
        reg = build_source_registry([good, bad], session=None)
        assert reg.get("ok") is not None
        assert reg.get("broken") is None  # skipped, not fatal

    def test_good_image_source_commits_at_boot(self, tmp_path):
        from led_ticker.app.run import build_source_registry
        from led_ticker.config import SourceConfig

        good = SourceConfig(
            type="image", id="cart.logo", raw={"path": str(_png(tmp_path))}
        )
        reg = build_source_registry([good], session=None, config_dir=tmp_path)
        assert reg.get("cart.logo") is not None
        assert "cart.logo" in pixel_emoji._get_registry()
        assert "cart.logo" in pixel_emoji.HIRES_REGISTRY

    def test_relative_path_resolves_against_config_dir(self, tmp_path):
        from led_ticker.app.factories import build_source
        from led_ticker.config import SourceConfig

        _png(tmp_path, name="rel.png")
        cfg = SourceConfig(type="image", id="cart.rel", raw={"path": "rel.png"})
        source = build_source(cfg, session=None, config_dir=tmp_path)
        assert Path(source.path).is_absolute()
        assert Path(source.path) == (tmp_path / "rel.png").resolve()
