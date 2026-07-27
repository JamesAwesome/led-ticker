"""Reload atomicity for config-declared image emoji (Task 3).

Mirrors the `_apply_reload` harness idiom in tests/test_reload.py: build old/new
configs via `load_config`, seed the global DataRegistry, invoke `rl._apply_reload`
directly with a `fake_respawn`, then assert on `pixel_emoji`'s registries + the
threaded widget_cache.

The image-emoji commit must ride the SAME atomicity as `set_data_registry`:
a failed source rebuild must leave BOTH the old registry AND the old committed
emoji slugs untouched (never a torn half-set); a successful rebuild must commit
the new slugs atomically with the registry swap. Separately, an image-source-set
change must flush the ENTIRE widget cache even when no individual widget's own
config changed (widgets cache `_has_emoji` at construction).
"""

from pathlib import Path

import pytest
from PIL import Image

from led_ticker import pixel_emoji
from led_ticker import reload as rl
from led_ticker.app.factories import _cache_key
from led_ticker.app.run import build_source_registry
from led_ticker.config import load_config
from led_ticker.pixel_emoji import abort_image_emoji
from led_ticker.render_breaker import RenderBreaker
from led_ticker.sources import DataRegistry, get_data_registry, set_data_registry

_DISPLAY = "[display]\nrows=16\ncols=32\n\n"
_SECTION = '[[playlist.section]]\nmode = "slideshow"\n'


def _write(path: Path, body: str) -> Path:
    path.write_text(body)
    return path


def _png(tmp_path: Path, name: str, color: tuple[int, int, int, int]) -> Path:
    img = Image.new("RGBA", (8, 8), color)
    p = tmp_path / name
    img.save(p)
    return p


async def _fake_respawn(old_task, cfg):
    return None


def _first_pixel_rgb(slug: str) -> tuple[int, int, int]:
    """(r, g, b) of the first lit lowres pixel for `slug` — used to tell a
    same-id-different-content image apart (both sprites share the slug "img.a"
    but are baked from differently-colored source PNGs)."""
    px = pixel_emoji._get_registry()[slug][0]
    return px[2], px[3], px[4]


def _reset_emoji_state():
    abort_image_emoji()
    for slug in list(pixel_emoji._CONFIG_IMAGE_SLUGS):
        pixel_emoji.EMOJI_REGISTRY.pop(slug, None)
        pixel_emoji.HIRES_REGISTRY.pop(slug, None)
    pixel_emoji._CONFIG_IMAGE_SLUGS.clear()


@pytest.fixture(autouse=True)
def _clean_emoji_state():
    """Mirrors test_image_source.py's `_clean` fixture: a committed/staged
    image slug from one test must never leak into the next."""
    _reset_emoji_state()
    yield
    _reset_emoji_state()


class TestReloadAtomicity:
    async def test_failed_reload_keeps_old_image_slugs(self, tmp_path):
        # old config: image source "img.a", red — committed at "boot".
        _png(tmp_path, "a.png", (255, 0, 0, 255))
        a = load_config(
            _write(
                tmp_path / "a.toml",
                _DISPLAY
                + '[[source]]\nid = "img.a"\ntype = "image"\npath = "a.png"\n\n'
                + _SECTION,
            )
        )
        old_reg = build_source_registry(a.sources, session=None, config_dir=tmp_path)
        set_data_registry(old_reg)
        assert "img.a" in pixel_emoji._get_registry()
        assert _first_pixel_rgb("img.a") == (255, 0, 0)

        # new config: img.a retargeted to blue (A') + a broken source (missing file).
        _png(tmp_path, "a_prime.png", (0, 0, 255, 255))
        b = load_config(
            _write(
                tmp_path / "b.toml",
                _DISPLAY
                + '[[source]]\nid = "img.a"\ntype = "image"\npath = "a_prime.png"\n\n'
                + '[[source]]\nid = "img.b"\ntype = "image"\npath = "missing.png"\n\n'
                + _SECTION,
            )
        )

        await rl._apply_reload(
            b,
            old_config=a,
            widget_cache={},
            widget_tasks={},
            render_breaker=RenderBreaker(),
            schedule_task=None,
            respawn_schedule=_fake_respawn,
            source_refresh_task=None,
            config_dir=tmp_path,
        )

        # registry identity unchanged (old sources kept)
        assert get_data_registry() is old_reg
        # slug img.a still renders the OLD (red) sprite, not A' (blue)
        assert "img.a" in pixel_emoji._get_registry()
        assert _first_pixel_rgb("img.a") == (255, 0, 0)
        # nothing from the broken source was applied
        assert "img.b" not in pixel_emoji._get_registry()

    async def test_failed_reload_does_not_leak_staged_slugs_into_next_reload(
        self, tmp_path
    ):
        """The abort's real job isn't visible in the single-reload test above
        (that failure path returns before commit either way regardless of
        whether abort actually clears anything). Its load-bearing effect only
        shows up across TWO reloads: reload #1 stages "img.a" then fails (a
        broken sibling source raises) -> abort must drop the staged "img.a".
        Reload #2 succeeds with a config that does NOT declare "img.a" at
        all. Without the abort, the leaked `_PENDING_IMAGE_EMOJI["img.a"]`
        entry would still be sitting there and reload #2's `commit_image_emoji`
        would resurrect it even though nothing in reload #2's config asked
        for it."""
        # config #0 ("a"): no image sources — registry starts empty.
        a = load_config(_write(tmp_path / "a.toml", _DISPLAY + _SECTION))
        old_reg = build_source_registry(a.sources, session=None, config_dir=tmp_path)
        set_data_registry(old_reg)
        assert "img.a" not in pixel_emoji._get_registry()

        # reload #1 ("b"): stages a brand-new "img.a" + a broken sibling
        # source (missing file) -> the registry rebuild raises, so the
        # reload fails and abort_image_emoji() must drop the staged "img.a".
        _png(tmp_path, "a.png", (255, 0, 0, 255))
        b = load_config(
            _write(
                tmp_path / "b.toml",
                _DISPLAY
                + '[[source]]\nid = "img.a"\ntype = "image"\npath = "a.png"\n\n'
                + '[[source]]\nid = "img.broken"\ntype = "image"\n'
                + 'path = "missing.png"\n\n'
                + _SECTION,
            )
        )

        await rl._apply_reload(
            b,
            old_config=a,
            widget_cache={},
            widget_tasks={},
            render_breaker=RenderBreaker(),
            schedule_task=None,
            respawn_schedule=_fake_respawn,
            source_refresh_task=None,
            config_dir=tmp_path,
        )

        # reload #1 failed: old registry kept, "img.a" never committed.
        assert get_data_registry() is old_reg
        assert "img.a" not in pixel_emoji._get_registry()

        # reload #2 ("c"): succeeds; its config does NOT mention "img.a" at
        # all. old_config is still "a" — the caller never swapped config on
        # reload #1's failure.
        _png(tmp_path, "c.png", (0, 255, 0, 255))
        c = load_config(
            _write(
                tmp_path / "c.toml",
                _DISPLAY
                + '[[source]]\nid = "img.c"\ntype = "image"\npath = "c.png"\n\n'
                + _SECTION,
            )
        )

        await rl._apply_reload(
            c,
            old_config=a,
            widget_cache={},
            widget_tasks={},
            render_breaker=RenderBreaker(),
            schedule_task=None,
            respawn_schedule=_fake_respawn,
            source_refresh_task=None,
            config_dir=tmp_path,
        )

        assert "img.c" in pixel_emoji._get_registry()
        # The slug staged only by the FAILED reload #1 must not have been
        # resurrected by reload #2's commit.
        assert "img.a" not in pixel_emoji._get_registry()
        assert "img.a" not in pixel_emoji.HIRES_REGISTRY
        assert "img.a" not in pixel_emoji._CONFIG_IMAGE_SLUGS

    async def test_successful_reload_swaps_slug_set(self, tmp_path):
        _png(tmp_path, "a.png", (255, 0, 0, 255))
        a = load_config(
            _write(
                tmp_path / "a.toml",
                _DISPLAY
                + '[[source]]\nid = "img.a"\ntype = "image"\npath = "a.png"\n\n'
                + _SECTION,
            )
        )
        old_reg = build_source_registry(a.sources, session=None, config_dir=tmp_path)
        set_data_registry(old_reg)
        assert "img.a" in pixel_emoji._get_registry()

        _png(tmp_path, "b.png", (0, 255, 0, 255))
        b = load_config(
            _write(
                tmp_path / "b.toml",
                _DISPLAY
                + '[[source]]\nid = "img.b"\ntype = "image"\npath = "b.png"\n\n'
                + _SECTION,
            )
        )

        await rl._apply_reload(
            b,
            old_config=a,
            widget_cache={},
            widget_tasks={},
            render_breaker=RenderBreaker(),
            schedule_task=None,
            respawn_schedule=_fake_respawn,
            source_refresh_task=None,
            config_dir=tmp_path,
        )

        assert get_data_registry() is not old_reg
        assert "img.b" in pixel_emoji._get_registry()
        assert "img.a" not in pixel_emoji._get_registry()


class TestReloadValidatesCommittedSlug:
    """A running config with an image source must be able to hot-reload the
    SAME file: validate (`load_and_validate` -> `validate_config`) runs in the
    live process where the source's slug is already committed. Rule 56's
    `is_emoji_slug(src.id)` collision check must not treat the source's own
    live commit as a pre-existing emoji and reject the reload — validate
    suspends the committed image slugs so static checks see pristine state."""

    async def _boot_then_validate(self, tmp_path, slug: str):
        _png(tmp_path, "logo.png", (255, 0, 0, 255))
        toml = (
            _DISPLAY
            + f'[[source]]\nid = "{slug}"\ntype = "image"\npath = "logo.png"\n\n'
            + _SECTION
            + f'[[playlist.section.widget]]\ntype="message"\ntext=":{slug}:"\n'
        )
        cfg_path = _write(tmp_path / "c.toml", toml)
        # "Boot": build + commit the image slug into the live registries.
        old_reg = build_source_registry(
            load_config(cfg_path).sources, session=None, config_dir=tmp_path
        )
        set_data_registry(old_reg)
        assert slug in pixel_emoji._get_registry()
        # Hot-reload preflight on the same file, in the same live process.
        config, errors, transient = await rl.load_and_validate(cfg_path)
        return config, errors, transient

    async def test_reload_of_own_image_source_is_valid(self, tmp_path):
        config, errors, transient = await self._boot_then_validate(tmp_path, "logo")
        assert not any("collides with an existing emoji slug" in e for e in errors)
        assert not errors
        assert config is not None
        assert transient is False

    async def test_reload_of_dotted_image_source_is_valid(self, tmp_path):
        config, errors, transient = await self._boot_then_validate(
            tmp_path, "cart.logo"
        )
        assert not any("collides with an existing emoji slug" in e for e in errors)
        assert not errors
        assert config is not None


class TestWidgetCacheFlush:
    async def test_image_source_change_flushes_widget_cache(self, tmp_path):
        set_data_registry(DataRegistry())
        widget_toml = '[[playlist.section.widget]]\ntype="message"\ntext=":b:"\n'

        a = load_config(_write(tmp_path / "a.toml", _DISPLAY + _SECTION + widget_toml))
        _png(tmp_path, "b.png", (0, 255, 0, 255))
        b = load_config(
            _write(
                tmp_path / "b.toml",
                _DISPLAY
                + '[[source]]\nid = "b"\ntype = "image"\npath = "b.png"\n\n'
                + _SECTION
                + widget_toml,
            )
        )

        # widget config is byte-identical between a and b -> same cache key
        key_a = _cache_key(dict(a.sections[0].widgets[0]))
        key_b = _cache_key(dict(b.sections[0].widgets[0]))
        assert key_a == key_b, "fixture must keep the widget config unchanged"

        widget_cache = {key_a: object()}
        widget_tasks: dict = {}

        await rl._apply_reload(
            b,
            old_config=a,
            widget_cache=widget_cache,
            widget_tasks=widget_tasks,
            render_breaker=RenderBreaker(),
            schedule_task=None,
            respawn_schedule=_fake_respawn,
            source_refresh_task=None,
            config_dir=tmp_path,
        )

        # Even though the widget's OWN config never changed (so the pre-existing
        # changed/removed-widget eviction would have kept it), the image-source
        # set changed (none -> "b") -> the whole cache must be flushed so the
        # reconstructed widget picks up the new :b: slug (_has_emoji recomputed).
        assert widget_cache == {}
