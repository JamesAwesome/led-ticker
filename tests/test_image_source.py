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
        lowres, hires, anim = load_image_sprites(_png(tmp_path))
        assert anim is None
        assert lowres and all(len(px) == 5 for px in lowres)
        assert max(p[0] for p in lowres) <= 7 and max(p[1] for p in lowres) <= 7
        assert hires.physical_size == 32
        assert hires.pixels  # opaque red square -> fully lit
        assert hires.physical_width and hires.physical_width <= 128

    def test_gif_uses_frame_zero(self, tmp_path):
        lowres, hires, _anim = load_image_sprites(_gif(tmp_path))
        # frame 0 is red; every lit pixel red-dominant
        assert all(px[2] > px[3] for px in hires.pixels)  # r > g

    def test_wide_image_caps_at_128(self, tmp_path):
        _, hires, _anim = load_image_sprites(_png(tmp_path, size=(1000, 40)))
        assert max(p[0] for p in hires.pixels) <= 127

    def test_transparent_pixels_dropped(self, tmp_path):
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        img.putpixel((0, 0), (255, 255, 255, 255))
        p = tmp_path / "dot.png"
        img.save(p)
        lowres, hires, _anim = load_image_sprites(p)
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


def _gif_frames(tmp_path, name, frames_spec):
    """frames_spec: list of (lit_width, duration_ms). 64x64 canvas,
    frame i lights columns [0, lit_width) rows [0, 8).

    Saves an animated PNG (APNG) with raw RGBA frames — NOT
    ``.convert("P")``. A palette round-trip drops the alpha channel (no
    transparency index survives), so every decoded frame comes back fully
    opaque and identical in extent regardless of how many columns were
    actually lit — that would make extent-sensitive assertions (e.g. the
    union-extent test below) pass vacuously even for a broken
    implementation. RGBA APNG frames preserve alpha through the
    save/reload round-trip, so per-frame extents differ for real. The
    decode path (``load_image_sprites``) is format-agnostic — it only
    uses Pillow's ``n_frames``/``seek``/``convert("RGBA")`` — so this
    works as a drop-in for every caller below, GIF-named or not.

    Deliberately omits ``disposal=`` — passing ``disposal=2`` on an APNG
    save was observed (empirically, not from docs) to cause Pillow to
    silently merge/drop frames with genuinely different content (a
    61-frame alternating-width source came back as 41 frames), which
    would silently defeat `test_over_cap_refused` below. Without it,
    APNG shows the same "pixel-identical ADJACENT frames merge, durations
    sum" behavior as GIF (verified empirically) — same posture as the
    existing per-test comments about keeping adjacent frames distinct.
    """
    from PIL import Image

    imgs = []
    for w, _d in frames_spec:
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        for x in range(w):
            for y in range(8):
                im.putpixel((x, y), (255, 0, 0, 255))
        imgs.append(im)
    p = tmp_path / name
    imgs[0].save(
        p,
        format="PNG",
        save_all=True,
        append_images=imgs[1:],
        duration=[d for _w, d in frames_spec],
    )
    return p


class TestAnimatedDecode:
    def test_union_extent_applied_to_all_frames(self, tmp_path):
        from led_ticker.sources import load_image_sprites

        # Lit widths 16/64/32 on a 64x64 canvas -> raw per-frame
        # rightmost-lit-pixel (max_x, BEFORE the 32-tall bake downscale)
        # is 15/63/31: genuinely different extents pre-normalization (see
        # the non-vacuity proof script referenced in
        # .superpowers/sdd/anim-task-2-report.md's correction note) —
        # this is what an alpha-preserving fixture buys over the old
        # palette-converted one, where every frame decoded as a fully-lit
        # 32x32 square and these three assertions passed trivially.
        p = _gif_frames(tmp_path, "a.png", [(16, 100), (64, 100), (32, 100)])
        _low, hires0, anim = load_image_sprites(p)
        assert anim is not None and len(anim.hires_frames) == 3
        widths = {f.physical_width for f in anim.hires_frames}
        assert len(widths) == 1  # every frame identical layout width
        # union EXTENT: no frame's rightmost lit pixel exceeds the width
        w = widths.pop()
        for f in anim.hires_frames:
            assert max((px[0] for px in f.pixels), default=0) < w
        # ... and the union is exactly the WIDEST frame's own extent, not
        # merely an upper bound: baking that frame ALONE (as a
        # single-frame file, so load_image_sprites' union-of-1 is itself)
        # must yield the identical physical_width.
        solo = _gif_frames(tmp_path, "a-widest.png", [(64, 100)])
        _low_solo, hires_solo, anim_solo = load_image_sprites(solo)
        assert anim_solo is None  # single frame -> no animation record
        assert w == hires_solo.physical_width

    def test_frame0_is_registry_sprite(self, tmp_path):
        from led_ticker.sources import load_image_sprites

        p = _gif_frames(tmp_path, "b.png", [(16, 100), (64, 100)])
        _low, hires0, anim = load_image_sprites(p)
        assert hires0 is anim.hires_frames[0]

    def test_durations_cumulative_and_clamped(self, tmp_path):
        from led_ticker.sources import load_image_sprites

        # Widths must differ between frames (8 vs 9) — Pillow's PNG
        # encoder merges pixel-identical ADJACENT frames on save (summing
        # their durations into one, verified empirically for APNG same as
        # GIF), which would silently collapse this to a single frame and
        # defeat the test. 5ms clamps to 20.
        p = _gif_frames(tmp_path, "c.png", [(8, 5), (9, 250)])
        _low, _h, anim = load_image_sprites(p)
        assert anim.cumulative_ms == (20, 270) and anim.total_ms == 270

    def test_malformed_duration_metadata_clamps_not_drops(self, tmp_path, monkeypatch):
        """Adversarial-review finding: duration=None or a non-numeric string
        in a frame's info dict must clamp THAT frame to the default, not
        raise and drop the whole source. Patch the info dict post-open via a
        wrapped Image.open (a real file can carry these; simplest determinism
        is injection)."""
        from PIL import Image as PILImage

        from led_ticker import sources as S

        p = _gif_frames(tmp_path, "m.png", [(8, 100), (9, 100), (10, 100)])
        real_open = PILImage.open
        bad = {0: None, 1: "75.5"}  # frame 2 keeps its real duration

        def wrapped_open(path, *a, **k):
            img = real_open(path, *a, **k)
            real_seek = img.seek

            def seek(i):
                real_seek(i)
                if i in bad:
                    img.info["duration"] = bad[i]

            img.seek = seek
            return img

        monkeypatch.setattr(PILImage, "open", wrapped_open)
        _low, _h, anim = S.load_image_sprites(p)
        assert anim is not None
        # None -> default 100; "75.5" -> 75 -> clamps to 75; real 100 stays
        assert anim.cumulative_ms[0] == 100  # None coerced to default
        assert anim.cumulative_ms[1] - anim.cumulative_ms[0] == 75  # "75.5" -> 75

    def test_over_cap_refused(self, tmp_path):
        import pytest

        from led_ticker.sources import load_image_sprites

        # Alternate width so no two ADJACENT frames are pixel-identical —
        # see the note in test_durations_cumulative_and_clamped above; an
        # all-identical run would collapse to 1 frame under Pillow's save
        # path and this test would never observe the 61-frame cap.
        p = _gif_frames(tmp_path, "d.png", [(4 + (i % 2), 30) for i in range(61)])
        with pytest.raises(ValueError, match="60"):
            load_image_sprites(p)

    def test_static_png_returns_none_animation(self, tmp_path):
        from led_ticker.sources import load_image_sprites

        _low, _h, anim = load_image_sprites(_png(tmp_path))
        assert anim is None

    def test_prepare_stages_animation(self, tmp_path):
        from led_ticker import pixel_emoji
        from led_ticker.sources import ImageSource

        p = _gif_frames(tmp_path, "e.png", [(8, 100), (16, 100)])
        ImageSource(id="me.anim", path=str(p)).prepare()
        assert "me.anim" in pixel_emoji._PENDING_IMAGE_ANIMATIONS
