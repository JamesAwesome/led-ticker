"""Tests for tools/gif_plan/flags.py — heuristic checks."""

from __future__ import annotations

from tools.gif_plan.flags import check_all


class TestMidPassCutoff:
    def test_no_header_emits_suggestion(self):
        # No `# render-duration: N` → info-level suggestion, not error.
        flags = check_all(
            config={"display": {"cols": 32, "chain": 5}, "playlist": {"section": []}},
            playlist_total_ms=10000,
            render_duration_header=None,
            sections_summary=[],
        )
        codes = [f["code"] for f in flags]
        assert "render_duration_suggestion" in codes
        assert all(
            f["severity"] != "error"
            for f in flags
            if f["code"] == "render_duration_suggestion"
        )

    def test_header_too_short_is_error(self):
        flags = check_all(
            config={"display": {"cols": 32, "chain": 5}, "playlist": {"section": []}},
            playlist_total_ms=10000,
            render_duration_header=5,  # User said 5s but math says 11s.
            sections_summary=[],
        )
        errs = [f for f in flags if f["code"] == "mid_pass_cutoff"]
        assert len(errs) == 1
        assert errs[0]["severity"] == "error"

    def test_header_long_enough_is_quiet(self):
        flags = check_all(
            config={"display": {"cols": 32, "chain": 5}, "playlist": {"section": []}},
            playlist_total_ms=10000,
            render_duration_header=12,
            sections_summary=[],
        )
        assert not any(f["code"] == "mid_pass_cutoff" for f in flags)


class TestScrollStepBounds:
    def test_too_fast_emits_warning(self):
        sections = [{"index": 0, "scroll_step_ms": 15}]
        flags = check_all(
            config={
                "display": {"cols": 32, "chain": 5},
                "playlist": {"section": [{"scroll_step_ms": 15}]},
            },
            playlist_total_ms=0,
            render_duration_header=None,
            sections_summary=sections,
        )
        warns = [f for f in flags if f["code"] == "scroll_step_too_fast"]
        assert len(warns) == 1
        assert warns[0]["severity"] == "warning"
        assert "15" in warns[0]["message"]

    def test_too_slow_emits_warning(self):
        sections = [{"index": 0, "scroll_step_ms": 100}]
        flags = check_all(
            config={
                "display": {"cols": 32, "chain": 5},
                "playlist": {"section": [{"scroll_step_ms": 100}]},
            },
            playlist_total_ms=0,
            render_duration_header=None,
            sections_summary=sections,
        )
        warns = [f for f in flags if f["code"] == "scroll_step_too_slow"]
        assert len(warns) == 1

    def test_in_band_is_quiet(self):
        sections = [{"index": 0, "scroll_step_ms": 25}]
        flags = check_all(
            config={
                "display": {"cols": 32, "chain": 5},
                "playlist": {"section": [{"scroll_step_ms": 25}]},
            },
            playlist_total_ms=0,
            render_duration_header=None,
            sections_summary=sections,
        )
        assert not any(f["code"].startswith("scroll_step_") for f in flags)


class TestZeroCycle:
    def test_wrap_with_empty_text(self):
        config = {
            "display": {"cols": 32, "chain": 5},
            "playlist": {
                "section": [
                    {
                        "mode": "swap",
                        "hold_time": 1.0,
                        "widget": [
                            {
                                "type": "two_row",
                                "top_text": "T",
                                "bottom_text": "",  # zero content
                                "bottom_text_wrap": True,
                            }
                        ],
                    },
                ]
            },
        }
        flags = check_all(
            config=config,
            playlist_total_ms=0,
            render_duration_header=None,
            sections_summary=[],
        )
        errs = [f for f in flags if f["code"] == "zero_cycle_width"]
        assert len(errs) == 1
        assert errs[0]["severity"] == "error"


class TestPixelMapperInfo:
    def test_pixel_mapper_present(self):
        config = {
            "display": {"cols": 64, "chain": 8, "pixel_mapper": "U-mapper"},
            "playlist": {"section": []},
        }
        flags = check_all(
            config=config,
            playlist_total_ms=0,
            render_duration_header=None,
            sections_summary=[],
        )
        info = [f for f in flags if f["code"] == "pixel_mapper_present"]
        assert len(info) == 1
        assert info[0]["severity"] == "info"


class TestLoopCountZero:
    """loop_count=0 on a swap section means 'loop forever' to the engine
    (itertools.cycle). The planner can't compute a finite total. Flag
    as info-severity so the user knows; this is a known dynamic case."""

    def test_loop_count_zero_emits_info(self):
        config = {
            "display": {"cols": 32, "chain": 5},
            "playlist": {
                "section": [
                    {
                        "mode": "swap",
                        "hold_time": 3.0,
                        "loop_count": 0,
                        "widget": [{"type": "message", "text": "HI", "font": "5x8"}],
                    },
                ]
            },
        }
        flags = check_all(
            config=config,
            playlist_total_ms=0,
            render_duration_header=None,
            sections_summary=[],
        )
        info = [f for f in flags if f["code"] == "loop_count_zero_runtime"]
        assert len(info) == 1
        assert info[0]["severity"] == "info"

    def test_normal_loop_count_quiet(self):
        config = {
            "display": {"cols": 32, "chain": 5},
            "playlist": {
                "section": [
                    {"mode": "swap", "loop_count": 1, "widget": []},
                ]
            },
        }
        flags = check_all(
            config=config,
            playlist_total_ms=0,
            render_duration_header=None,
            sections_summary=[],
        )
        assert not any(f["code"] == "loop_count_zero_runtime" for f in flags)


class TestGifPathUnresolved:
    def _check(self, widget: dict) -> list[dict]:
        return check_all(
            config={
                "display": {"cols": 32, "chain": 5},
                "playlist": {"section": [{"widget": [widget]}]},
            },
            playlist_total_ms=1000,
            render_duration_header=None,
            sections_summary=[],
        )

    def test_missing_gif_file_warns(self):
        flags = self._check({"type": "gif", "path": "/no/such/file.gif"})
        hit = [f for f in flags if f["code"] == "gif_path_unresolved"]
        assert len(hit) == 1
        assert hit[0]["severity"] == "warning"

    def test_existing_gif_file_does_not_warn(self, tmp_path):
        from PIL import Image

        g = tmp_path / "ok.gif"
        Image.new("RGB", (8, 8), (1, 2, 3)).save(g, save_all=True, duration=100)
        flags = self._check({"type": "gif", "path": str(g)})
        assert not any(f["code"] == "gif_path_unresolved" for f in flags)

    def test_missing_image_path_is_not_flagged(self):
        # image/still timing comes from hold_seconds, not the file —
        # only `gif` is scoped for this warning.
        flags = self._check({"type": "image", "path": "/no/such/pic.png"})
        assert not any(f["code"] == "gif_path_unresolved" for f in flags)

    def test_gif_without_path_is_not_flagged(self):
        flags = self._check({"type": "gif", "gif_loops": 2})
        assert not any(f["code"] == "gif_path_unresolved" for f in flags)
