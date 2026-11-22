"""Font / validate / loader follow-ups from the plugin-font review (#560,
items A1, A2, B1, B2, D). Each test names the user-visible gap it closes."""

import shutil
import textwrap
from importlib import resources

import pytest

from led_ticker import _plugin_loader as L
from led_ticker.fonts import hires_loader
from led_ticker.validate import validate_config, validate_config_text

DISPLAY_256x64 = """\
[display]
rows = 32
cols = 64
chain_length = 8
default_scale = 4
pixel_mapper_config = "Remap:256,64|U-mapper"

[[playlist.section]]
mode = "slideshow"
hold_time = 3
"""

LOCAL_CLOCK_PLUGIN = textwrap.dedent(
    """\
    import attrs

    def register(api):
        @api.widget("clock")
        @attrs.define
        class Clock:
            text: str = ""
            def draw(self, canvas, cursor_pos=0, **kw):
                return canvas, cursor_pos
    """
)


def _bundled_otf():
    with resources.as_file(
        resources.files("led_ticker.fonts") / "hires" / "Inter-Regular.otf"
    ) as p:
        return p


@pytest.fixture
def cold_plugins():
    """A cold plugin registry before AND after — these tests exercise the
    load-once guard, so a prior test's load must not leak in."""
    L.reset_plugins()
    try:
        yield
    finally:
        L.reset_plugins()


class TestA1TextValidateLocalPlugins:
    """webui text-validate writes the TOML to a temp dir; the local plugin dir
    must still resolve against the REAL config dir, and the first validate in
    a process must not pin an empty local-plugin set for the ones after it."""

    def _write(self, tmp_path):
        pdir = tmp_path / "plugins"
        pdir.mkdir()
        (pdir / "acme.py").write_text(LOCAL_CLOCK_PLUGIN)
        toml = (
            DISPLAY_256x64.replace("default_scale = 4", "default_scale = 1").replace(
                'pixel_mapper_config = "Remap:256,64|U-mapper"\n', ""
            )
            + '\n[[playlist.section.widget]]\ntype = "acme.clock"\ntext = "hi"\n'
        )
        (tmp_path / "config.toml").write_text(toml)
        return toml

    async def test_text_validate_sees_config_dir_local_plugin(
        self, tmp_path, cold_plugins
    ):
        toml = self._write(tmp_path)
        result = await validate_config_text(toml, config_dir=tmp_path)
        assert result.valid, [(e.rule, e.message) for e in result.errors]

    async def test_text_validate_first_does_not_pin_empty_set_for_file_validate(
        self, tmp_path, cold_plugins
    ):
        """The sidecar's FIRST validate is often a text validate. A file
        validate later in the same process must still see the plugin."""
        toml = self._write(tmp_path)
        await validate_config_text(toml, config_dir=tmp_path)
        result = await validate_config(tmp_path / "config.toml")
        assert result.valid, [(e.rule, e.message) for e in result.errors]

    async def test_text_validate_without_config_dir_keeps_temp_anchoring(
        self, tmp_path, cold_plugins
    ):
        """Back-compat: no config_dir → the temp dir is the anchor and the
        local plugin is (correctly) not found."""
        toml = self._write(tmp_path)
        result = await validate_config_text(toml)
        assert not result.valid


class TestA2ImageBdfFontSizeBelowCell:
    """`type = "image"`, BDF font, `font_size` below the cell height used to
    pass validate and build, then raise at play() and trip the render
    breaker. Validate must refuse it up front (one home: the same
    `block_scale_for_font_size` check play() runs)."""

    def _conf(self, tmp_path, widget_lines: str):
        from PIL import Image

        Image.new("RGB", (4, 4), (255, 0, 0)).save(tmp_path / "x.png")
        p = tmp_path / "config.toml"
        p.write_text(
            DISPLAY_256x64
            + '\n[[playlist.section.widget]]\ntype = "image"\npath = "x.png"\n'
            + widget_lines
        )
        return p

    async def test_explicit_bdf_font_below_cell_is_an_error(self, tmp_path):
        p = self._conf(tmp_path, 'text = "hi"\nfont = "5x8"\nfont_size = 3\n')
        result = await validate_config(p)
        hits = [e for e in result.errors if "below cell height" in e.message]
        assert hits, [(e.rule, e.message) for e in result.errors]
        assert hits[0].rule == 75
        assert "font_size" in hits[0].fix

    async def test_default_font_below_cell_is_an_error(self, tmp_path):
        """No `font` key still means a BDF default; `font_size = 3` fails
        the same way at play, so validate must catch it too."""
        p = self._conf(tmp_path, 'text = "hi"\nfont_size = 3\n')
        result = await validate_config(p)
        assert any(e.rule == 75 for e in result.errors), [
            (e.rule, e.message) for e in result.errors
        ]

    async def test_gif_shares_the_check(self, tmp_path):
        from PIL import Image

        frames = [Image.new("RGB", (4, 4), (c, 0, 0)) for c in (10, 200)]
        frames[0].save(
            tmp_path / "x.gif", save_all=True, append_images=frames[1:], duration=100
        )
        p = tmp_path / "config.toml"
        p.write_text(
            DISPLAY_256x64
            + '\n[[playlist.section.widget]]\ntype = "gif"\npath = "x.gif"\n'
            'text = "hi"\nfont = "5x8"\nfont_size = 3\n'
        )
        result = await validate_config(p)
        assert any(e.rule == 75 for e in result.errors)

    async def test_multiple_of_cell_passes(self, tmp_path):
        p = self._conf(tmp_path, 'text = "hi"\nfont = "5x8"\nfont_size = 16\n')
        result = await validate_config(p)
        assert not any(e.rule == 75 for e in result.errors), [
            (e.rule, e.message) for e in result.errors
        ]

    async def test_image_without_text_is_not_refused(self, tmp_path):
        """play() only sizes the font when there is overlay text; an image
        with no text and a stray `font_size = 3` runs fine today and must
        keep validating clean."""
        p = self._conf(tmp_path, "font_size = 3\n")
        result = await validate_config(p)
        assert not any(e.rule == 75 for e in result.errors), [
            (e.rule, e.message) for e in result.errors
        ]

    async def test_two_row_font_size_still_reports_rule_71_first(self, tmp_path):
        p = self._conf(
            tmp_path,
            'top_text = "a"\nbottom_text = "b"\nfont = "5x8"\nfont_size = 3\n',
        )
        result = await validate_config(p)
        rules = [e.rule for e in result.errors]
        assert 71 in rules and 75 not in rules, rules


class TestB1Rule2RowFonts:
    """Rule 2 compared only `font` / `font_threshold`; a two_row's
    `top_font_threshold` could invert weight against a message with no
    warning."""

    async def test_row_font_threshold_mismatch_warns(self, tmp_path):
        p = tmp_path / "config.toml"
        p.write_text(
            DISPLAY_256x64
            + textwrap.dedent("""\

            [[playlist.section.widget]]
            type = "message"
            text = "bold"
            font = "Inter-Bold"
            font_size = 24
            font_threshold = 60

            [[playlist.section.widget]]
            type = "two_row"
            top_text = "a"
            bottom_text = "b"
            top_font = "Inter-Regular"
            top_font_size = 22
            top_font_threshold = 200
            """)
        )
        result = await validate_config(p)
        assert any(w.rule == 2 for w in result.warnings), [
            (w.rule, w.message) for w in result.warnings
        ]

    async def test_row_fonts_on_their_defaults_stay_quiet(self, tmp_path):
        p = tmp_path / "config.toml"
        p.write_text(
            DISPLAY_256x64
            + textwrap.dedent("""\

            [[playlist.section.widget]]
            type = "message"
            text = "bold"
            font = "Inter-Bold"
            font_size = 24

            [[playlist.section.widget]]
            type = "two_row"
            top_text = "a"
            bottom_text = "b"
            top_font = "Inter-Regular"
            top_font_size = 22
            bottom_font = "Inter-Bold"
            bottom_font_size = 22
            """)
        )
        result = await validate_config(p)
        assert not any(w.rule == 2 for w in result.warnings), [
            w.message for w in result.warnings if w.rule == 2
        ]


class TestB2RowFontSizeClassification:
    """A hi-res `top_font` without `top_font_size` raised with rule `None`
    and the generic fix; it is the rule-5 shape and the fix must name the
    prefixed key (the bare "add font_size" advice walks a two-row user
    straight into rule 71)."""

    @pytest.mark.parametrize("prefix", ["top", "bottom"])
    async def test_missing_row_size_is_rule_5_naming_the_prefixed_key(
        self, tmp_path, prefix
    ):
        other = "bottom" if prefix == "top" else "top"
        p = tmp_path / "config.toml"
        p.write_text(
            DISPLAY_256x64
            + textwrap.dedent(f"""\

            [[playlist.section.widget]]
            type = "two_row"
            top_text = "a"
            bottom_text = "b"
            {prefix}_font = "Inter-Regular"
            {other}_font = "Inter-Bold"
            {other}_font_size = 22
            """)
        )
        result = await validate_config(p)
        hits = [e for e in result.errors if f"requires {prefix}_font_size" in e.message]
        assert hits, [(e.rule, e.message) for e in result.errors]
        assert hits[0].rule == 5
        assert f"{prefix}_font_size" in hits[0].fix
        assert "Add font_size" not in hits[0].fix


class TestDLoadPluginsClearsFontCache:
    """A pre-registration lookup caches `None` for a plugin font name; after
    the plugin commits, `resolve_font` must see the registered file instead
    of raising a misleading "registered but its file is missing"."""

    def test_poisoned_cache_is_cleared_by_load_plugins(self, tmp_path, cold_plugins):
        from led_ticker.fonts import resolve_font

        pdir = tmp_path / "plugins"
        pdir.mkdir()
        shutil.copy(_bundled_otf(), pdir / "Brand.otf")
        (pdir / "acme.py").write_text(
            textwrap.dedent(
                """\
                def register(api):
                    api.font("Brand", "Brand.otf", threshold=45)
                """
            )
        )
        # Poison: a lookup before the plugin commits caches a miss.
        assert hires_loader.load_hires_font("acme.Brand", 24, 45) is None
        # No reset_plugins() between the poison and the load — that helper
        # clears the cache itself and would hide the bug.
        L.load_plugins(pdir, entry_points_enabled=False)
        font = resolve_font("acme.Brand", 24)
        assert font is not None
