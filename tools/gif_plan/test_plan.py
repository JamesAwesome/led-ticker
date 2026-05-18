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
        w = {"type": "gif", "path": str(g), "gif_loops": 3}
        assert widget_ms(w, {}, 160, tmp_path) == 600

    def test_gif_loops_zero_is_section_hold(self, tmp_path):
        w = {"type": "gif", "path": "x.gif", "gif_loops": 0}
        assert widget_ms(w, {"hold_time": 4.0}, 160, tmp_path) == 4000

    def test_gif_relative_path_resolves_against_config_dir(self, tmp_path):
        (tmp_path / "assets").mkdir()
        (tmp_path / "cfg").mkdir()
        _gif(tmp_path / "assets" / "x.gif", frames=5, dur_ms=80)
        w = {"type": "gif", "path": "../assets/x.gif", "gif_loops": 2}
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
