"""Tests for tools/gif_plan/totals.py — section + playlist aggregation."""

from __future__ import annotations

from tools.gif_plan.totals import (
    playlist_total_ms,
    recommended_render_duration_s,
    section_total_ms,
)


class TestSectionTotal:
    def test_single_widget_swap(self):
        section = {
            "mode": "swap",
            "hold_time": 4.0,
            "scroll_step_ms": 25,
            "loop_count": 1,
            "widget": [{"type": "message", "text": "HI", "font": "5x8"}],
        }
        display = {"cols": 32, "chain": 5, "default_scale": 1}
        # Static text → 4000 ms × loop_count 1 = 4000.
        assert section_total_ms(section, display) == 4000

    def test_multi_widget_swap(self):
        section = {
            "mode": "swap",
            "hold_time": 4.0,
            "scroll_step_ms": 25,
            "loop_count": 2,
            "widget": [
                {"type": "message", "text": "HI", "font": "5x8"},
                {"type": "message", "text": "BYE", "font": "5x8"},
            ],
        }
        display = {"cols": 32, "chain": 5, "default_scale": 1}
        # Two static texts → (4000 + 4000) × 2 = 16000.
        assert section_total_ms(section, display) == 16000

    def test_forever_scroll_returns_none(self):
        section = {
            "mode": "forever_scroll",
            "widget": [{"type": "message", "text": "x"}],
        }
        display = {"cols": 32, "chain": 5, "default_scale": 1}
        # forever_scroll / infini_scroll are runtime-dependent. v1 emits
        # None for the caller to flag.
        assert section_total_ms(section, display) is None

    def test_loop_count_zero_returns_none(self):
        # loop_count=0 → engine runs itertools.cycle (loop forever), so
        # the section duration is runtime-dependent. It must NOT be
        # coerced to a finite single-pass total (regression: 0→1).
        section = {
            "mode": "swap",
            "loop_count": 0,
            "widget": [{"type": "message", "text": "x", "font": "5x8"}],
        }
        display = {"cols": 32, "chain": 5, "default_scale": 1}
        assert section_total_ms(section, display) is None

    def test_loop_count_zero_excluded_from_playlist_total(self):
        from tools.gif_plan.totals import playlist_total_ms

        config = {
            "display": {"cols": 32, "chain": 5, "default_scale": 1},
            "playlist": {
                "section": [
                    {
                        "mode": "swap",
                        "loop_count": 1,
                        "hold_time": 4.0,
                        "widget": [{"type": "message", "text": "x", "font": "5x8"}],
                    },
                    {
                        "mode": "swap",
                        "loop_count": 0,  # forever — contributes nothing
                        "hold_time": 9.0,
                        "widget": [{"type": "message", "text": "y", "font": "5x8"}],
                    },
                ]
            },
        }
        # Only the finite section (4000 ms) counts.
        assert playlist_total_ms(config) == 4000


class TestPlaylistTotal:
    def test_single_section(self):
        config = {
            "display": {"cols": 32, "chain": 5, "default_scale": 1},
            "playlist": {
                "section": [
                    {
                        "mode": "swap",
                        "hold_time": 3.0,
                        "loop_count": 1,
                        "widget": [{"type": "message", "text": "HI", "font": "5x8"}],
                    }
                ]
            },
        }
        assert playlist_total_ms(config) == 3000

    def test_two_sections(self):
        config = {
            "display": {"cols": 32, "chain": 5, "default_scale": 1},
            "playlist": {
                "section": [
                    {
                        "mode": "swap",
                        "hold_time": 3.0,
                        "loop_count": 1,
                        "widget": [{"type": "message", "text": "HI", "font": "5x8"}],
                    },
                    {
                        "mode": "swap",
                        "hold_time": 5.0,
                        "loop_count": 1,
                        "widget": [{"type": "message", "text": "BYE", "font": "5x8"}],
                    },
                ]
            },
        }
        # 3000 + 5000 = 8000.
        assert playlist_total_ms(config) == 8000

    def test_forever_scroll_excluded_from_total(self):
        config = {
            "display": {"cols": 32, "chain": 5, "default_scale": 1},
            "playlist": {
                "section": [
                    {
                        "mode": "forever_scroll",
                        "widget": [{"type": "message", "text": "HI"}],
                    },
                    {
                        "mode": "swap",
                        "hold_time": 3.0,
                        "loop_count": 1,
                        "widget": [{"type": "message", "text": "HI", "font": "5x8"}],
                    },
                ]
            },
        }
        # forever_scroll contributes nothing to the deterministic total.
        assert playlist_total_ms(config) == 3000


class TestRecommendedRenderDuration:
    def test_seven_seconds_total_plus_buffer(self):
        # 7000 ms → ceil(7) + 1 = 8.
        assert recommended_render_duration_s(7000) == 8

    def test_seven_point_one_seconds_rounds_up(self):
        # 7100 ms → ceil(7.1) + 1 = 9.
        assert recommended_render_duration_s(7100) == 9

    def test_zero_ms_still_returns_buffer(self):
        # Empty playlist → just the 1 sec buffer (sensible floor).
        assert recommended_render_duration_s(0) == 1
