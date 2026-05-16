"""Integration tests for tools/gif_plan/plan.py CLI."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from PIL import Image
from tools.gif_plan.plan import _resolve_widget_paths, plan

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "uv",
            "run",
            "python",
            str(REPO_ROOT / "tools" / "gif_plan" / "plan.py"),
            *args,
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def _write_config(tmp_path: Path, content: str, *, header: str = "") -> Path:
    cfg = tmp_path / "demo.toml"
    cfg.write_text((header + "\n" + content).strip() + "\n")
    return cfg


class TestCliExitCodes:
    def test_clean_config_exits_zero(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1

[[playlist.section]]
mode = "swap"
hold_time = 4.0
scroll_step_ms = 25

[[playlist.section.widget]]
type = "message"
text = "HELLO"
font = "5x8"
""",
            header="# render-duration: 5",
        )
        r = _run_cli(str(cfg), "--json")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["total_ms"] == 4000
        assert data["recommended_render_duration_s"] == 5
        # Header matches recommended → no mid_pass_cutoff flag.
        codes = [f["code"] for f in data["flags"]]
        assert "mid_pass_cutoff" not in codes

    def test_warning_config_exits_one(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
[display]
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 2.0
scroll_step_ms = 10

[[playlist.section.widget]]
type = "message"
text = "HI"
font = "5x8"
""",
            header="# render-duration: 3",
        )
        r = _run_cli(str(cfg), "--json")
        assert r.returncode == 1, r.stderr
        data = json.loads(r.stdout)
        codes = [f["code"] for f in data["flags"]]
        assert "scroll_step_too_fast" in codes

    def test_error_config_exits_two(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
[display]
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 4.0
scroll_step_ms = 25

[[playlist.section.widget]]
type = "two_row"
top_text = "T"
bottom_text = ""
bottom_text_wrap = true
""",
            header="# render-duration: 5",
        )
        r = _run_cli(str(cfg), "--json")
        # bottom_text_wrap=true with empty bottom_text → engine would
        # reject this at config-load. Our planner also flags it.
        # Note: this config would also fail led_ticker validation, but
        # the planner shouldn't require a valid config to plan.
        assert r.returncode == 2, r.stderr


class TestRenderDurationHeader:
    def test_reads_header_from_toml_comment(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
[display]
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 4.0
scroll_step_ms = 25

[[playlist.section.widget]]
type = "message"
text = "HI"
font = "5x8"
""",
            header="# render-duration: 8",
        )
        r = _run_cli(str(cfg), "--json")
        data = json.loads(r.stdout)
        assert data["render_duration_header"] == 8


class TestHumanRender:
    """The default (non-JSON) terminal output — `make plan-gif` path."""

    def test_human_output_contains_summary_lines(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
[display]
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 4.0
scroll_step_ms = 25

[[playlist.section.widget]]
type = "message"
text = "HI"
font = "5x8"
""",
            header="# render-duration: 5",
        )
        r = _run_cli(str(cfg))  # no --json
        assert r.returncode == 0, r.stderr
        out = r.stdout
        assert "playlist_total:" in out
        assert "recommended_render_duration:" in out
        assert "header `# render-duration:` found: 5s" in out
        assert "section[0]" in out
        assert "widget[0] type=message" in out

    def test_human_output_renders_flags(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
[display]
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 2.0
scroll_step_ms = 10

[[playlist.section.widget]]
type = "message"
text = "HI"
font = "5x8"
""",
            header="# render-duration: 3",
        )
        r = _run_cli(str(cfg))
        assert r.returncode == 1, r.stderr
        assert "flags:" in r.stdout
        assert "scroll_step_too_fast" in r.stdout

    def test_human_output_marks_forever_section_runtime_dependent(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
[display]
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
loop_count = 0
hold_time = 3.0

[[playlist.section.widget]]
type = "message"
text = "HI"
font = "5x8"
""",
        )
        r = _run_cli(str(cfg))
        assert r.returncode == 0, r.stderr
        assert "runtime-dependent" in r.stdout
        assert "loop_count_zero_runtime" in r.stdout


class TestCliErrorHandling:
    """Missing / malformed config must exit with a code distinct from
    the flag-severity codes (0/1/2) so callers can tell a tool failure
    apart from a config that merely has warnings."""

    def test_missing_config_exits_three_with_stderr(self, tmp_path):
        r = _run_cli(str(tmp_path / "does-not-exist.toml"))
        assert r.returncode == 3
        assert "config not found" in r.stderr
        assert r.stdout == ""

    def test_malformed_toml_exits_three_with_stderr(self, tmp_path):
        cfg = tmp_path / "bad.toml"
        cfg.write_text("# render-duration: 5\n[display\ncols = 32\n")
        r = _run_cli(str(cfg))
        assert r.returncode == 3
        assert "malformed TOML" in r.stderr


class TestSchema:
    def test_json_output_has_required_keys(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
[display]
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 3.0

[[playlist.section.widget]]
type = "message"
text = "HI"
font = "5x8"
""",
        )
        r = _run_cli(str(cfg), "--json")
        data = json.loads(r.stdout)
        for key in (
            "config_path",
            "sections",
            "total_ms",
            "recommended_render_duration_s",
            "flags",
            "render_duration_header",
        ):
            assert key in data, f"Missing top-level key: {key}"
        section = data["sections"][0]
        for key in ("index", "mode", "section_total_ms", "widgets"):
            assert key in section, f"Missing section key: {key}"


class TestGifPathResolution:
    """Regression: relative gif paths must resolve against the CONFIG
    file's directory, not the caller's cwd. Mirrors app.py:652-659.
    Before the fix, a pinned demo's `../../../config/assets/x.gif`
    failed to resolve from the repo root and silently hit the
    1000ms/loop fallback, mispredicting every gif demo's duration."""

    def _make_gif(self, path: Path, *, frames: int, dur_ms: int) -> None:
        imgs = [Image.new("RGB", (8, 8), (i, i, i)) for i in range(frames)]
        imgs[0].save(
            path,
            save_all=True,
            append_images=imgs[1:],
            duration=dur_ms,
            loop=0,
        )

    def test_relative_gif_path_resolves_against_config_dir(self, tmp_path):
        # Layout: <tmp>/assets/x.gif and <tmp>/cfg/demo.toml referencing
        # it as a config-relative "../assets/x.gif".
        (tmp_path / "assets").mkdir()
        (tmp_path / "cfg").mkdir()
        self._make_gif(tmp_path / "assets" / "x.gif", frames=5, dur_ms=80)
        cfg = tmp_path / "cfg" / "demo.toml"
        cfg.write_text(
            "[display]\ncols = 32\nchain = 5\n\n"
            '[[playlist.section]]\nmode = "swap"\n\n'
            "[[playlist.section.widget]]\n"
            'type = "gif"\n'
            'path = "../assets/x.gif"\n'
            "gif_loops = 3\n"
        )
        # Run with cwd = repo root (as `make plan-gif` / dogfood does).
        prev = os.getcwd()
        os.chdir(REPO_ROOT)
        try:
            data = plan(cfg)
        finally:
            os.chdir(prev)
        # 5 frames × 80ms × 3 loops = 1200ms — NOT the 1000×3=3000
        # fallback that a cwd-relative (unresolved) path would produce.
        assert data["sections"][0]["widgets"][0]["visit_ms"] == 1200
        assert data["total_ms"] == 1200

    def test_absolute_gif_path_is_left_untouched(self, tmp_path):
        gif = tmp_path / "abs.gif"
        self._make_gif(gif, frames=2, dur_ms=100)
        cfg = tmp_path / "demo.toml"
        cfg.write_text(
            "[display]\ncols = 32\nchain = 5\n\n"
            '[[playlist.section]]\nmode = "swap"\n\n'
            "[[playlist.section.widget]]\n"
            'type = "gif"\n'
            f'path = "{gif}"\n'
            "gif_loops = 4\n"
        )
        data = plan(cfg)
        # 2 × 100 × 4 = 800ms (absolute path resolves directly).
        assert data["total_ms"] == 800


class TestResolveWidgetPathsUnit:
    """Direct unit coverage of `_resolve_widget_paths` branches."""

    def test_relative_gif_path_rewritten_to_config_dir(self, tmp_path):
        cfg = {
            "playlist": {
                "section": [{"widget": [{"type": "gif", "path": "../a/x.gif"}]}]
            }
        }
        _resolve_widget_paths(cfg, tmp_path / "cfg")
        resolved = cfg["playlist"]["section"][0]["widget"][0]["path"]
        assert Path(resolved).is_absolute()
        assert resolved == str((tmp_path / "a" / "x.gif").resolve())

    def test_image_and_still_relative_paths_rewritten(self, tmp_path):
        cfg = {
            "playlist": {
                "section": [
                    {
                        "widget": [
                            {"type": "image", "path": "pics/a.png"},
                            {"type": "still", "path": "pics/b.png"},
                        ]
                    }
                ]
            }
        }
        _resolve_widget_paths(cfg, tmp_path)
        ws = cfg["playlist"]["section"][0]["widget"]
        assert ws[0]["path"] == str((tmp_path / "pics" / "a.png").resolve())
        assert ws[1]["path"] == str((tmp_path / "pics" / "b.png").resolve())

    def test_absolute_path_left_untouched(self, tmp_path):
        abs_p = str((tmp_path / "abs.gif").resolve())
        cfg = {"playlist": {"section": [{"widget": [{"type": "gif", "path": abs_p}]}]}}
        _resolve_widget_paths(cfg, tmp_path / "elsewhere")
        assert cfg["playlist"]["section"][0]["widget"][0]["path"] == abs_p

    def test_non_file_widget_and_missing_path_are_skipped(self, tmp_path):
        cfg = {
            "playlist": {
                "section": [
                    {
                        "widget": [
                            {"type": "message", "text": "hi"},  # no path key
                            {"type": "gif"},  # gif but no path
                            {"type": "gif", "path": ""},  # empty path
                        ]
                    }
                ]
            }
        }
        _resolve_widget_paths(cfg, tmp_path)  # must not raise
        ws = cfg["playlist"]["section"][0]["widget"]
        assert "path" not in ws[0]
        assert "path" not in ws[1]
        assert ws[2]["path"] == ""

    def test_missing_playlist_and_sections_are_safe(self, tmp_path):
        for cfg in ({}, {"playlist": {}}, {"playlist": {"section": []}}):
            _resolve_widget_paths(cfg, tmp_path)  # must not raise

    def test_resolved_but_missing_file_still_rewritten_and_flagged(self, tmp_path):
        # The file doesn't exist; the path is still made absolute, and
        # gif_visit_ms must fall back gracefully (1000ms/loop) AND the
        # planner must surface a gif_path_unresolved warning rather than
        # let the confidently-wrong number pass silently.
        cfg = tmp_path / "demo.toml"
        cfg.write_text(
            "[display]\ncols = 32\nchain = 5\n\n"
            '[[playlist.section]]\nmode = "swap"\n\n'
            "[[playlist.section.widget]]\n"
            'type = "gif"\n'
            'path = "missing/nope.gif"\n'
            "gif_loops = 2\n"
        )
        data = plan(cfg)
        # Fallback: 1000ms/loop × 2 = 2000ms (no crash).
        assert data["total_ms"] == 2000
        codes = [f["code"] for f in data["flags"]]
        assert "gif_path_unresolved" in codes
        flag = next(f for f in data["flags"] if f["code"] == "gif_path_unresolved")
        assert flag["severity"] == "warning"
