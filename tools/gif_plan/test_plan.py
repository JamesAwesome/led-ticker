"""Tests for the slimmed gif_plan estimator."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image
from tools.gif_plan.plan import (
    EXIT_CUTOFF,
    EXIT_OK,
    EXIT_TOOL_ERROR,
    _canvas_w,
    _content_w,
    main,
    plan,
    recommended_s,
    total_ms,
    widget_ms,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO_ROOT / "docs" / "site" / "demos-pinned"


def _gif(path: Path, *, frames: int, dur_ms: int) -> None:
    imgs = [Image.new("RGB", (8, 8), (i, i, i)) for i in range(frames)]
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=dur_ms, loop=0)


class TestContentWidth:
    def test_plain_text(self):
        assert _content_w("HELLO") == 5 * 6

    def test_emoji_counts_as_8(self):
        # ":star:" stripped -> "hi  yo" (6 chars) x6 + 1 emoji x8 = 44
        assert _content_w("hi :star: yo") == 6 * 6 + 8

    def test_empty(self):
        assert _content_w("") == 0


class TestCanvasWidth:
    def test_default_scale(self):
        assert _canvas_w({"cols": 32, "chain": 5}, {}) == 160

    def test_section_scale_override(self):
        assert _canvas_w({"cols": 32, "chain": 5}, {"scale": 2}) == 80


class TestWidgetMs:
    def test_message_fits_is_hold_only(self):
        w = {"type": "message", "text": "HI"}
        s = {"hold_time": 4.0, "scroll_step_ms": 25}
        assert widget_ms(w, s, 160, Path(".")) == 4000

    def test_message_overflow_adds_scroll(self):
        w = {"type": "message", "text": "x" * 40}
        s = {"hold_time": 4.0, "scroll_step_ms": 25}
        assert widget_ms(w, s, 160, Path(".")) == 6000

    def test_two_row_uses_bottom_text(self):
        w = {"type": "two_row", "top_text": "T", "bottom_text": "y" * 40}
        s = {"hold_time": 0.0, "scroll_step_ms": 25}
        assert widget_ms(w, s, 160, Path(".")) == (240 - 160) * 25

    def test_image_default_hold_seconds(self):
        assert widget_ms({"type": "image"}, {}, 160, Path(".")) == 5000

    def test_gif_loops_times_frame_sum(self, tmp_path):
        g = tmp_path / "g.gif"
        _gif(g, frames=2, dur_ms=100)
        w = {"type": "gif", "path": str(g), "loops": 3}
        assert widget_ms(w, {}, 160, tmp_path) == 600

    def test_gif_loops_zero_is_section_hold(self, tmp_path):
        w = {"type": "gif", "path": "x.gif", "loops": 0}
        assert widget_ms(w, {"hold_time": 4.0}, 160, tmp_path) == 4000

    def test_gif_relative_path_resolves_against_config_dir(self, tmp_path):
        (tmp_path / "assets").mkdir()
        (tmp_path / "cfg").mkdir()
        _gif(tmp_path / "assets" / "x.gif", frames=5, dur_ms=80)
        w = {"type": "gif", "path": "../assets/x.gif", "loops": 2}
        prev = os.getcwd()
        os.chdir(REPO_ROOT)
        try:
            assert widget_ms(w, {}, 160, tmp_path / "cfg") == 400 * 2
        finally:
            os.chdir(prev)

    def test_unknown_widget_contributes_zero(self):
        assert widget_ms({"type": "weather"}, {}, 160, Path(".")) == 0


class TestTotals:
    def test_skips_non_swap_and_loop_count_zero(self):
        cfg = {
            "display": {"cols": 32, "chain": 5},
            "playlist": {
                "section": [
                    {
                        "mode": "swap",
                        "hold_time": 4.0,
                        "widget": [{"type": "message", "text": "HI"}],
                    },
                    {
                        "mode": "forever_scroll",
                        "widget": [{"type": "message", "text": "HI"}],
                    },
                    {
                        "mode": "swap",
                        "loop_count": 0,
                        "widget": [{"type": "message", "text": "HI"}],
                    },
                ]
            },
        }
        assert total_ms(cfg, Path(".")) == 4000

    def test_loop_count_multiplies(self):
        cfg = {
            "display": {"cols": 32, "chain": 5},
            "playlist": {
                "section": [
                    {
                        "mode": "swap",
                        "loop_count": 3,
                        "hold_time": 2.0,
                        "widget": [{"type": "message", "text": "HI"}],
                    }
                ]
            },
        }
        assert total_ms(cfg, Path(".")) == 6000

    def test_recommended_s(self):
        assert recommended_s(7000) == 8
        assert recommended_s(7001) == 9
        assert recommended_s(0) == 1


class TestCli:
    def _write(self, tmp_path: Path, body: str, header: str = "") -> Path:
        p = tmp_path / "demo.toml"
        p.write_text((header + "\n" + body).strip() + "\n")
        return p

    _BODY = """
[display]
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 4.0

[[playlist.section.widget]]
type = "message"
text = "HI"
"""

    def test_clean_exits_zero(self, tmp_path, capsys):
        cfg = self._write(tmp_path, self._BODY, "# render-duration: 5")
        assert main([str(cfg)]) == EXIT_OK
        assert capsys.readouterr().out.strip() == "duration: 5"

    def test_cutoff_exits_two(self, tmp_path, capsys):
        cfg = self._write(tmp_path, self._BODY, "# render-duration: 2")
        assert main([str(cfg)]) == EXIT_CUTOFF
        out = capsys.readouterr().out
        assert "duration: 5" in out and "cutoff: header 2s" in out

    def test_no_header_clean(self, tmp_path, capsys):
        cfg = self._write(tmp_path, self._BODY)
        assert main([str(cfg)]) == EXIT_OK
        assert "cutoff" not in capsys.readouterr().out

    def test_missing_file_exits_three(self, tmp_path, capsys):
        assert main([str(tmp_path / "nope.toml")]) == EXIT_TOOL_ERROR
        assert "cannot read config" in capsys.readouterr().err

    def test_malformed_toml_exits_three(self, tmp_path, capsys):
        bad = tmp_path / "bad.toml"
        bad.write_text("[display\ncols = 32\n")
        assert main([str(bad)]) == EXIT_TOOL_ERROR
        assert "malformed TOML" in capsys.readouterr().err

    def test_bad_args_exits_three(self, capsys):
        assert main([]) == EXIT_TOOL_ERROR
        assert "usage:" in capsys.readouterr().err


class TestConstantsMatchEngine:
    """Bind plan.py's mirrored constants to their led_ticker source.

    A future engine default change will fail these assertions loudly
    instead of silently mis-estimating gif durations.
    """

    def test_font_cell_w_matches_font_default_bbx_width(self):
        """_FONT_CELL_W mirrors the FONT_DEFAULT (6x12.bdf) cell advance width.

        Source: get_bdf_for(FONT_DEFAULT).bbx_width — the FONTBOUNDINGBOX
        width parsed from 6x12.bdf, which is the canonical advance width
        for that bitmap font.
        """
        from tools.gif_plan.plan import _FONT_CELL_W

        from led_ticker.fonts import FONT_DEFAULT, get_bdf_for

        engine_value = get_bdf_for(FONT_DEFAULT).bbx_width
        assert engine_value == _FONT_CELL_W, (
            f"plan._FONT_CELL_W={_FONT_CELL_W} drifted from "
            f"get_bdf_for(FONT_DEFAULT).bbx_width={engine_value}"
        )

    def test_default_hold_s_matches_section_config(self):
        """_DEFAULT_HOLD_S mirrors SectionConfig.hold_time default.

        Source: SectionConfig.__dataclass_fields__['hold_time'].default —
        SectionConfig is a plain dataclass; field defaults are directly
        accessible via __dataclass_fields__.
        """
        from tools.gif_plan.plan import _DEFAULT_HOLD_S

        from led_ticker.config import SectionConfig

        engine_value = SectionConfig.__dataclass_fields__["hold_time"].default
        assert engine_value == _DEFAULT_HOLD_S, (
            f"plan._DEFAULT_HOLD_S={_DEFAULT_HOLD_S} drifted from "
            f"SectionConfig.hold_time default={engine_value}"
        )

    def test_default_hold_seconds_matches_still_image(self):
        """_DEFAULT_HOLD_SECONDS mirrors StillImage.hold_time default.

        Source: attrs.fields(StillImage) — StillImage is an attrs class
        (@attrs.define); field defaults are accessible via attrs.fields().
        """
        import attrs
        from tools.gif_plan.plan import _DEFAULT_HOLD_SECONDS

        from led_ticker.widgets.still import StillImage

        engine_value = next(
            f.default for f in attrs.fields(StillImage) if f.name == "hold_time"
        )
        assert engine_value == _DEFAULT_HOLD_SECONDS, (
            f"plan._DEFAULT_HOLD_SECONDS={_DEFAULT_HOLD_SECONDS} drifted from "
            f"StillImage.hold_time default={engine_value}"
        )

    def test_default_step_ms_matches_engine_tick(self):
        """_DEFAULT_STEP_MS mirrors ENGINE_TICK_MS in ticker.py.

        The plan uses _DEFAULT_STEP_MS as the per-pixel scroll cadence when
        a section omits scroll_step_ms. The engine's default scroll cadence
        is Ticker.scroll_speed = 0.05 s = 50 ms = ENGINE_TICK_MS. Both
        constants should agree.

        Source: led_ticker.ticker.ENGINE_TICK_MS — a module-level int
        constant. Cross-checked against attrs.fields(Ticker).scroll_speed
        default (0.05 s → 50 ms) to catch either drifting independently.
        """
        import attrs
        from tools.gif_plan.plan import _DEFAULT_STEP_MS

        from led_ticker.ticker import ENGINE_TICK_MS, Ticker

        assert ENGINE_TICK_MS == _DEFAULT_STEP_MS, (
            f"plan._DEFAULT_STEP_MS={_DEFAULT_STEP_MS} drifted from "
            f"ticker.ENGINE_TICK_MS={ENGINE_TICK_MS}"
        )
        scroll_speed_default = next(
            f.default for f in attrs.fields(Ticker) if f.name == "scroll_speed"
        )
        assert int(scroll_speed_default * 1000) == _DEFAULT_STEP_MS, (
            f"plan._DEFAULT_STEP_MS={_DEFAULT_STEP_MS} drifted from "
            f"Ticker.scroll_speed default {scroll_speed_default}s "
            f"(= {int(scroll_speed_default * 1000)} ms)"
        )


class TestPinnedDemoSanity:
    """Every shipped demo must produce a usable number without crashing.
    NO accuracy assertion — the precise +/-20% pin is intentionally
    deleted, not relaxed."""

    def test_all_pinned_demos(self, capsys):
        tomls = sorted(DEMO_DIR.glob("*.toml"))
        assert tomls, "no pinned demos found"
        for cfg in tomls:
            code = main([str(cfg)])
            capsys.readouterr()
            assert code in (EXIT_OK, EXIT_CUTOFF), f"{cfg.name} -> exit {code}"
            rec, _, _ = plan(cfg)
            assert isinstance(rec, int) and rec > 0, cfg.name
