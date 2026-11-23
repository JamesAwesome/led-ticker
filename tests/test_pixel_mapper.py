"""One home for "what canvas does this pixel_mapper_config produce" (#560 C2).

HeadlessBackend, the rgbmatrix test stub (which render-demo drives) and
`led-ticker validate` each parsed the mapper on their own: validate read
`Remap:W,H`, the other two honoured only `U-mapper`, so a real bigsign
`[display]` block built a 512x32 headless canvas and failed the
content_height ceiling while validate reported clean."""

import textwrap

from led_ticker.pixel_mapper import mapped_canvas_size, remap_canvas_size

BIGSIGN_REMAP = "Remap:256,64|192,32n|192,0n|128,32n|128,0n|64,32n|64,0n|0,32n|0,0n"


class TestRemapCanvasSize:
    def test_reads_the_header(self):
        assert remap_canvas_size(BIGSIGN_REMAP) == (256, 64)

    def test_header_with_chained_mapper(self):
        assert remap_canvas_size("Remap:256,64|U-mapper") == (256, 64)

    def test_non_remap_is_none(self):
        assert remap_canvas_size("") is None
        assert remap_canvas_size("U-mapper") is None

    def test_malformed_remap_is_none(self):
        """`Remap:custom` appears in backend tests; a bad header must fall
        back to the naive geometry, never raise."""
        assert remap_canvas_size("Remap:custom") is None
        assert remap_canvas_size("Remap:256") is None
        assert remap_canvas_size("Remap:a,b") is None


class TestMappedCanvasSize:
    def test_empty_is_naive(self):
        assert mapped_canvas_size(512, 32, "") == (512, 32)

    def test_u_mapper_folds(self):
        assert mapped_canvas_size(512, 32, "U-mapper") == (256, 64)

    def test_remap_wins(self):
        assert mapped_canvas_size(512, 32, BIGSIGN_REMAP) == (256, 64)

    def test_malformed_remap_is_naive(self):
        assert mapped_canvas_size(512, 32, "Remap:custom") == (512, 32)


class TestConsumers:
    def test_headless_backend_honours_remap(self):
        from led_ticker.backends.headless import HeadlessBackend

        b = HeadlessBackend(64 * 8, 32, pixel_mapper_config=BIGSIGN_REMAP)
        b.setup()
        c = b.create_canvas()
        assert (c.width, c.height) == (256, 64)

    def test_stub_rgbmatrix_honours_remap(self):
        """render-demo patches this stub, so a bigsign demo TOML can now
        carry its real Remap block."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.rows, opts.cols, opts.chain_length, opts.parallel = 32, 64, 8, 1
        opts.pixel_mapper_config = BIGSIGN_REMAP
        c = RGBMatrix(options=opts).CreateFrameCanvas()
        assert (c.width, c.height) == (256, 64)

    def test_validate_panel_dims_use_the_helper(self):
        from led_ticker.config import DisplayConfig
        from led_ticker.validate import _panel_h_real, _panel_w_real

        d = DisplayConfig(
            rows=32, cols=64, chain_length=8, pixel_mapper_config=BIGSIGN_REMAP
        )
        assert (_panel_w_real(d), _panel_h_real(d)) == (256, 64)

    def test_validate_malformed_remap_falls_back_instead_of_raising(self):
        from led_ticker.config import DisplayConfig
        from led_ticker.validate import _panel_h_real, _panel_w_real

        d = DisplayConfig(
            rows=32, cols=64, chain_length=8, pixel_mapper_config="Remap:custom"
        )
        assert (_panel_w_real(d), _panel_h_real(d)) == (512, 32)

    def test_validate_does_not_fold_u_mapper(self):
        """Pinned on purpose: validate's panel size ignored a bare U-mapper
        before the helper existed and still does — folding it here would
        silently change rule 1 for U-mapper configs. Revisit deliberately."""
        from led_ticker.config import DisplayConfig
        from led_ticker.validate import _panel_h_real, _panel_w_real

        d = DisplayConfig(
            rows=32, cols=64, chain_length=8, pixel_mapper_config="U-mapper"
        )
        assert (_panel_w_real(d), _panel_h_real(d)) == (512, 32)

    async def test_bigsign_display_block_builds_256x64_headless_and_validates(
        self, tmp_path
    ):
        """Acceptance: the real bigsign geometry, headless, agrees with validate."""
        from led_ticker.app.factories import build_frame_from_config
        from led_ticker.config import load_config
        from led_ticker.validate import validate_config

        p = tmp_path / "config.toml"
        p.write_text(
            textwrap.dedent(f"""\
            [display]
            rows = 32
            cols = 64
            chain_length = 8
            parallel = 1
            default_scale = 4
            pixel_mapper_config = "{BIGSIGN_REMAP}"
            backend = "headless"

            [[playlist.section]]
            mode = "slideshow"
            hold_time = 3

            [[playlist.section.widget]]
            type = "message"
            text = "hi"
            """)
        )
        cfg = load_config(p)
        frame = build_frame_from_config(cfg.display)
        frame.setup()
        c = frame.get_clean_canvas()
        assert (c.width, c.height) == (256, 64)
        result = await validate_config(p)
        assert result.valid, [(e.rule, e.message) for e in result.errors]
