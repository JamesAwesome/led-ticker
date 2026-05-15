"""Integration tests for tools/gif_plan/plan.py CLI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

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
