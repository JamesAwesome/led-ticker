"""Tests for MLB score monitor widget."""

import unittest.mock as mock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from led_ticker.widgets.message import SegmentMessage
from led_ticker.widgets.mlb import (
    MLB_TEAM_COLORS,
    MLB_TEAM_NAMES,
    GameInfo,
    MLBScoreMonitor,
    SeriesInfo,
    _build_game_message,
    _build_series_title,
    _classify_postponement,
    _format_game_time,
    _format_inning,
    _ordinal,
)

ET = ZoneInfo("America/New_York")


# --- Helpers ---


class TestOrdinal:
    def test_first(self):
        assert _ordinal(1) == "1st"

    def test_second(self):
        assert _ordinal(2) == "2nd"

    def test_third(self):
        assert _ordinal(3) == "3rd"

    def test_fourth(self):
        assert _ordinal(4) == "4th"

    def test_eleventh(self):
        assert _ordinal(11) == "11th"

    def test_twenty_first(self):
        assert _ordinal(21) == "21st"


class TestFormatInning:
    def test_top_first(self):
        assert _format_inning(1, "top") == "\u25b21"

    def test_bot_seventh(self):
        assert _format_inning(7, "bottom") == "\u25bc7"

    def test_top_ninth(self):
        assert _format_inning(9, "top") == "\u25b29"

    def test_extras(self):
        assert _format_inning(12, "bottom") == "\u25bc12"


class TestFormatGameTime:
    def test_today(self):
        now = datetime.now(ET)
        game_time = now.replace(hour=19, minute=5)
        result = _format_game_time(game_time, ET)
        assert result.startswith("Today")
        assert "7:05 PM" in result

    def test_tomorrow(self):
        now = datetime.now(ET)
        game_time = (now + timedelta(days=1)).replace(hour=13, minute=10)
        result = _format_game_time(game_time, ET)
        assert result.startswith("Tmrw")

    def test_this_week(self):
        now = datetime.now(ET)
        game_time = now + timedelta(days=3)
        game_time = game_time.replace(hour=19, minute=0)
        result = _format_game_time(game_time, ET)
        # Should show day name like "Fri 7:00 PM"
        assert "PM" in result or "AM" in result


# --- Team Data ---


class TestTeamData:
    def test_all_30_teams_have_colors(self):
        assert len(MLB_TEAM_COLORS) == 30

    def test_all_30_teams_have_names(self):
        assert len(MLB_TEAM_NAMES) == 30

    def test_phillies_color(self):
        assert MLB_TEAM_COLORS["PHI"] == (228, 24, 40)

    def test_mets_color(self):
        assert MLB_TEAM_COLORS["NYM"] == (0, 45, 114)

    def test_phillies_name(self):
        assert MLB_TEAM_NAMES["PHI"] == "Phillies"

    def test_mets_name(self):
        assert MLB_TEAM_NAMES["NYM"] == "Mets"


# --- GameInfo ---


class TestGameInfo:
    def test_default_state_is_preview(self):
        g = GameInfo(home_abbr="PHI", away_abbr="NYM")
        assert g.state == "preview"

    def test_final_game(self):
        g = GameInfo(
            home_abbr="PHI",
            away_abbr="NYM",
            home_score=5,
            away_score=3,
            state="final",
        )
        assert g.state == "final"
        assert g.home_score == 5


# --- Postponement classification ---


class TestClassifyPostponement:
    def test_postponed(self):
        assert _classify_postponement("Postponed") == ("postponed", "PPD")

    def test_cancelled(self):
        assert _classify_postponement("Cancelled") == ("postponed", "CANC")

    def test_canceled_us_spelling(self):
        assert _classify_postponement("Canceled") == ("postponed", "CANC")

    def test_suspended(self):
        assert _classify_postponement("Suspended") == ("postponed", "SUSP")

    def test_suspended_with_reason(self):
        assert _classify_postponement("Suspended: Rain") == ("postponed", "SUSP")

    def test_completed_early(self):
        assert _classify_postponement("Completed Early") == ("postponed", "EARLY")

    def test_completed_early_with_reason(self):
        assert _classify_postponement("Completed Early: Rain") == (
            "postponed",
            "EARLY",
        )

    def test_normal_final_returns_none(self):
        """Non-postponement states return None so caller falls back to abstract."""
        state, _ = _classify_postponement("Final")
        assert state is None

    def test_in_progress_returns_none(self):
        state, _ = _classify_postponement("In Progress")
        assert state is None

    def test_empty_string_returns_none(self):
        state, _ = _classify_postponement("")
        assert state is None


# --- SeriesInfo ---


class TestSeriesInfo:
    def test_empty_series(self):
        s = SeriesInfo(opponent_abbr="NYM")
        assert s.team_wins == 0
        assert s.team_losses == 0


class TestPostponedGameMessage:
    """Render a postponed game without faking a Final score."""

    def test_renders_without_scores(self):
        g = GameInfo(
            home_abbr="PHI",
            away_abbr="SF",
            state="postponed",
            postpone_tag="PPD",
            postpone_reason="Rain",
        )
        msg = _build_game_message(g, "PHI", ET)
        text = "".join(seg[0] for seg in msg.segments)
        assert "SF" in text
        assert "PHI" in text
        assert "(PPD: Rain)" in text
        # No "Final" tag, no "None" scores
        assert "Final" not in text
        assert "None" not in text

    def test_no_reason_just_tag(self):
        g = GameInfo(
            home_abbr="PHI",
            away_abbr="SF",
            state="postponed",
            postpone_tag="PPD",
        )
        msg = _build_game_message(g, "PHI", ET)
        text = "".join(seg[0] for seg in msg.segments)
        assert "(PPD)" in text
        assert ":" not in text  # no "PPD: ..." when reason is empty

    def test_cancelled_uses_canc_tag(self):
        g = GameInfo(
            home_abbr="PHI",
            away_abbr="SF",
            state="postponed",
            postpone_tag="CANC",
        )
        msg = _build_game_message(g, "PHI", ET)
        text = "".join(seg[0] for seg in msg.segments)
        assert "(CANC)" in text

    def test_postponed_not_counted_as_win_or_loss(self):
        """A postponed game must not affect a series record."""
        session = mock.MagicMock()
        monitor = MLBScoreMonitor(session=session, team="PHI")
        games = [
            GameInfo(
                home_abbr="PHI",
                away_abbr="SF",
                state="postponed",
                postpone_tag="PPD",
                postpone_reason="Rain",
            )
        ]
        series = monitor._make_series("SF", games)
        assert series.team_wins == 0
        assert series.team_losses == 0


# --- Message Building ---


class TestBuildSeriesTitle:
    def test_same_home_uses_at_separator(self):
        """All games at same venue: AWAY @ HOME."""
        games = [
            GameInfo(
                home_abbr="PHI",
                away_abbr="NYM",
                state="final",
                home_score=5,
                away_score=3,
            ),
            GameInfo(
                home_abbr="PHI",
                away_abbr="NYM",
                state="final",
                home_score=4,
                away_score=2,
            ),
            GameInfo(home_abbr="PHI", away_abbr="NYM", state="preview"),
        ]
        series = SeriesInfo(
            opponent_abbr="NYM",
            games=games,
            team_wins=2,
            team_losses=1,
        )
        msg = _build_series_title("PHI", series, ET)
        assert isinstance(msg, SegmentMessage)
        texts = [t for t, _ in msg.segments]
        assert texts[0] == "Mets"  # away first
        assert texts[1] == " @ "
        assert texts[2] == "Phillies"  # home second
        text = "".join(texts)
        # Record ordered by position: NYM @ PHI → NYM_wins-PHI_wins
        # PHI has 2 wins, NYM has 1: "1-2"
        assert " 1-2" in text
        assert "leads" not in text

    def test_mixed_home_uses_vs_separator(self):
        """Mixed venues: neutral 'vs' separator."""
        games = [
            GameInfo(
                home_abbr="PHI",
                away_abbr="NYM",
                state="final",
                home_score=5,
                away_score=3,
            ),
            GameInfo(home_abbr="NYM", away_abbr="PHI", state="preview"),
        ]
        series = SeriesInfo(
            opponent_abbr="NYM",
            games=games,
            team_wins=1,
            team_losses=0,
        )
        msg = _build_series_title("PHI", series, ET)
        texts = [t for t, _ in msg.segments]
        assert texts[0] == "Phillies"
        assert texts[1] == " vs "
        assert texts[2] == "Mets"
        # Record ordered by position: PHI vs NYM → PHI_wins-NYM_wins
        text = "".join(texts)
        assert " 1-0" in text

    def test_tied_series(self):
        games = [
            GameInfo(
                home_abbr="PHI",
                away_abbr="NYM",
                state="final",
                home_score=5,
                away_score=3,
            ),
            GameInfo(
                home_abbr="PHI",
                away_abbr="NYM",
                state="final",
                home_score=2,
                away_score=4,
            ),
        ]
        series = SeriesInfo(
            opponent_abbr="NYM",
            games=games,
            team_wins=1,
            team_losses=1,
        )
        msg = _build_series_title("PHI", series, ET)
        text = "".join(t for t, _ in msg.segments)
        assert " 1-1" in text
        assert "Tied" not in text

    def test_opponent_leading_at_format(self):
        """When opponent leads and is home, record reflects positions."""
        games = [
            GameInfo(
                home_abbr="NYM",
                away_abbr="PIT",
                state="final",
                home_score=5,
                away_score=3,
            ),
            GameInfo(home_abbr="NYM", away_abbr="PIT", state="preview"),
        ]
        series = SeriesInfo(
            opponent_abbr="NYM",
            games=games,
            team_wins=0,
            team_losses=1,
        )
        msg = _build_series_title("PIT", series, ET)
        texts = [t for t, _ in msg.segments]
        # PIT @ NYM → PIT is away (first), NYM is home (second)
        assert texts[0] == "Pirates"
        assert texts[1] == " @ "
        assert texts[2] == "Mets"
        text = "".join(texts)
        # PIT has 0 wins (first), NYM has 1 win (second)
        assert " 0-1" in text

    def test_spring_training_label(self):
        games = [
            GameInfo(home_abbr="PHI", away_abbr="BAL", state="live", game_type="S"),
        ]
        series = SeriesInfo(
            opponent_abbr="BAL",
            games=games,
        )
        msg = _build_series_title("PHI", series, ET)
        text = "".join(t for t, _ in msg.segments)
        assert "(ST)" in text
        # Slug-bearing segment is rendered as an inline pixel-art flower
        # via draw_with_emoji (replaces the old `msg.icon` parameter).
        assert ":flower:" in text
        # Single home team: should use @ separator
        texts = [t for t, _ in msg.segments]
        assert texts[0] == "Orioles"
        assert texts[1] == " @ "
        assert texts[2] == "Phillies"

    def test_single_game_no_record(self):
        """Single-game matchups shouldn't show series record."""
        games = [
            GameInfo(
                home_abbr="PHI",
                away_abbr="BAL",
                state="final",
                home_score=5,
                away_score=3,
            ),
        ]
        series = SeriesInfo(
            opponent_abbr="BAL",
            games=games,
            team_wins=1,
            team_losses=0,
        )
        msg = _build_series_title("PHI", series, ET)
        text = "".join(t for t, _ in msg.segments)
        assert "leads" not in text

    def test_title_is_centered(self):
        games = [GameInfo(home_abbr="PHI", away_abbr="NYM", state="preview")]
        series = SeriesInfo(opponent_abbr="NYM", games=games)
        msg = _build_series_title("PHI", series, ET)
        assert msg.center is True


class TestBuildGameMessage:
    def test_final_home_win_away_first(self):
        """Home team wins — away listed first, scores colored independently."""
        game = GameInfo(
            home_abbr="PHI",
            away_abbr="NYM",
            home_score=5,
            away_score=3,
            state="final",
        )
        msg = _build_game_message(game, "PHI", ET)
        texts = [t for t, _ in msg.segments]
        full = "".join(texts)
        # Away team (NYM) listed first
        assert texts[0] == "NYM"
        assert texts[3] == "PHI"
        assert "Final" in full
        # Away lost (3 < 5): away score red, home score green
        from led_ticker.widgets.mlb import LOSS_COLOR, WIN_COLOR

        colors = [c for _, c in msg.segments]
        assert colors[1] is LOSS_COLOR  # NYM score (3) = red
        assert colors[4] is WIN_COLOR  # PHI score (5) = green

    def test_final_away_win(self):
        """Away team wins — scores colored: away green, home red."""
        game = GameInfo(
            home_abbr="PHI",
            away_abbr="NYM",
            home_score=2,
            away_score=4,
            state="final",
        )
        msg = _build_game_message(game, "PHI", ET)
        from led_ticker.widgets.mlb import LOSS_COLOR, WIN_COLOR

        texts = [t for t, _ in msg.segments]
        colors = [c for _, c in msg.segments]
        assert texts[0] == "NYM"
        assert colors[1] is WIN_COLOR  # NYM score (4) = green
        assert colors[4] is LOSS_COLOR  # PHI score (2) = red

    def test_live_game_away_first(self):
        """Live game: away team listed first, scores in white."""
        game = GameInfo(
            home_abbr="PHI",
            away_abbr="NYM",
            home_score=3,
            away_score=2,
            state="live",
            inning="\u25bc7",
            balls=2,
            strikes=1,
            outs=1,
            on_first=True,
            on_second=False,
            on_third=True,
        )
        msg = _build_game_message(game, "PHI", ET)
        texts = [t for t, _ in msg.segments]
        text = "".join(texts)
        # Away (NYM) listed first
        assert texts[0] == "NYM"
        assert texts[3] == "PHI"
        assert "\u25bc7" in text
        assert "\u00b7" in text
        assert "\u25c6\u25c7\u25c6" in text

    def test_live_game_bases_empty(self):
        game = GameInfo(
            home_abbr="PHI",
            away_abbr="NYM",
            home_score=0,
            away_score=0,
            state="live",
            inning="\u25b21",
        )
        msg = _build_game_message(game, "PHI", ET)
        text = "".join(t for t, _ in msg.segments)
        assert "\u25c7\u25c7\u25c7" in text
        assert "\u00b7" in text

    def test_preview_away_at_home(self):
        """Preview always shows AWAY @ HOME regardless of which team is yours."""
        game = GameInfo(
            home_abbr="NYM",
            away_abbr="PHI",
            state="preview",
            start_time=datetime.now(ET) + timedelta(hours=3),
        )
        msg = _build_game_message(game, "PHI", ET)
        texts = [t for t, _ in msg.segments]
        assert texts[0] == "PHI"  # away
        assert texts[1] == " @ "
        assert texts[2] == "NYM"  # home

    def test_preview_home_team_also_away_first(self):
        """When your team is home, away opponent still listed first."""
        game = GameInfo(
            home_abbr="PHI",
            away_abbr="NYM",
            state="preview",
            start_time=datetime.now(ET) + timedelta(hours=3),
        )
        msg = _build_game_message(game, "PHI", ET)
        texts = [t for t, _ in msg.segments]
        assert texts[0] == "NYM"  # away
        assert texts[1] == " @ "
        assert texts[2] == "PHI"  # home


# --- SegmentMessage draw ---


class TestSegmentMessageDraw:
    def test_returns_canvas_and_cursor(self, canvas):
        msg = SegmentMessage(
            [("PHI", mock.Mock()), ("5", mock.Mock())],
        )
        result_canvas, cursor_pos = msg.draw(canvas)
        assert result_canvas is canvas
        assert cursor_pos > 0

    def test_has_padding_attribute(self):
        msg = SegmentMessage([("test", mock.Mock())])
        assert hasattr(msg, "padding")
        assert msg.padding == 6

    def test_default_font_is_FONT_DEFAULT(self):
        from led_ticker.fonts import FONT_DEFAULT

        msg = SegmentMessage([("test", mock.Mock())])
        assert msg.font is FONT_DEFAULT

    def test_advance_frame_accepts_visit_id_kwarg(self):
        """Regression: _advance_frame_if_supported passes visit_id=N; must not crash."""
        msg = SegmentMessage([("PHI", mock.Mock())])
        msg.advance_frame(visit_id=42)  # must not raise TypeError
        assert msg._frame_count == 1

    def test_accepts_hires_font_kwarg(self):
        """Regression: SegmentMessage now accepts a `font` so the user
        can set `font="Inter-Bold"` on `mlb` / `mlb_standings` widgets
        and have it propagate into the colored segments."""
        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        font = resolve_font("Inter-Regular", 24)
        msg = SegmentMessage([("test", mock.Mock())], font=font)
        assert isinstance(msg.font, HiresFont)
        assert msg.font is font


# --- MLBScoreMonitor ---


class TestMLBScoreMonitor:
    def test_registered(self):
        from led_ticker.widgets import get_widget_class

        cls = get_widget_class("mlb")
        assert cls is MLBScoreMonitor


class TestMLBParsing:
    def test_group_into_series(self):
        widget = MLBScoreMonitor(
            session=mock.Mock(),
            team="PHI",
        )
        games = [
            GameInfo(
                home_abbr="PHI",
                away_abbr="NYM",
                state="final",
                home_score=5,
                away_score=3,
                start_time=datetime(2026, 6, 1, 19, tzinfo=ET),
            ),
            GameInfo(
                home_abbr="PHI",
                away_abbr="NYM",
                state="final",
                home_score=2,
                away_score=4,
                start_time=datetime(2026, 6, 2, 19, tzinfo=ET),
            ),
            GameInfo(
                home_abbr="PHI",
                away_abbr="NYM",
                state="preview",
                start_time=datetime(2026, 6, 3, 19, tzinfo=ET),
            ),
            GameInfo(
                home_abbr="ATL",
                away_abbr="PHI",
                state="preview",
                start_time=datetime(2026, 6, 5, 19, tzinfo=ET),
            ),
        ]
        series = widget._group_into_series(games)
        assert len(series) == 2
        assert series[0].opponent_abbr == "NYM"
        assert len(series[0].games) == 3
        assert series[0].team_wins == 1
        assert series[0].team_losses == 1
        assert series[1].opponent_abbr == "ATL"

    def test_find_current_series_live(self):
        widget = MLBScoreMonitor(
            session=mock.Mock(),
            team="PHI",
        )
        widget._tz = ET
        now = datetime.now(ET)
        series = [
            SeriesInfo(
                opponent_abbr="NYM",
                games=[
                    GameInfo(
                        home_abbr="PHI",
                        away_abbr="NYM",
                        state="live",
                        home_score=3,
                        away_score=2,
                        start_time=now - timedelta(hours=1),
                    ),
                ],
            ),
        ]
        result = widget._find_current_series(series, now)
        assert result is not None
        assert result.opponent_abbr == "NYM"


class TestMlbBgColor:
    def test_field_exists_on_monitor(self):
        names = {a.name for a in MLBScoreMonitor.__attrs_attrs__}
        assert "bg_color" in names

    def test_accepts_bg_color(self):
        from rgbmatrix.graphics import Color

        w = MLBScoreMonitor(session=mock.Mock(), team="NYY", bg_color=Color(70, 80, 90))
        assert w.bg_color.red == 70

    def test_game_message_has_bg_color_field(self):
        """SegmentMessage needs bg_color so the orchestrator can read it."""
        msg = SegmentMessage(
            [
                (
                    "NYY 4 BOS 2 (Final)",
                    __import__("rgbmatrix.graphics", fromlist=["Color"]).Color(
                        255, 255, 255
                    ),
                )
            ]
        )
        assert hasattr(msg, "bg_color")
        assert msg.bg_color is None  # default

    def test_game_message_accepts_bg_color(self):
        from rgbmatrix.graphics import Color

        bg = Color(10, 20, 30)
        msg = SegmentMessage(
            [("NYY", Color(255, 255, 255))],
            bg_color=bg,
        )
        assert msg.bg_color is bg


class TestMLBTwoRowLayout:
    """MLBTwoRowMessage class + MLBScoreMonitor dispatch for layout='two_row'."""

    def test_monitor_top_font_default_is_none(self):
        from unittest import mock
        m = MLBScoreMonitor(session=mock.Mock(), team="PHI")
        assert m.top_font is None

    def test_monitor_top_row_height_default_is_none(self):
        from unittest import mock
        m = MLBScoreMonitor(session=mock.Mock(), team="PHI")
        assert m.top_row_height is None

    def test_monitor_layout_default_is_ticker(self):
        from unittest import mock
        m = MLBScoreMonitor(session=mock.Mock(), team="PHI")
        assert m.layout == "ticker"

    def test_two_row_message_type_imported(self):
        from led_ticker.widgets.mlb import MLBTwoRowMessage  # noqa: F401

    def test_build_two_row_message_factory_returns_mlb_two_row_message(self):
        """Factory smoke test: _build_two_row_message returns MLBTwoRowMessage."""
        from zoneinfo import ZoneInfo
        from led_ticker.widgets.mlb import MLBTwoRowMessage, _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        assert isinstance(msg, MLBTwoRowMessage)
