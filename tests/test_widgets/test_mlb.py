"""Tests for MLB score monitor widget."""

import unittest.mock as mock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from led_ticker.widgets.mlb import (
    MLB_TEAM_COLORS,
    MLB_TEAM_NAMES,
    GameInfo,
    MLBGameMessage,
    MLBScoreMonitor,
    SeriesInfo,
    _build_game_message,
    _build_series_title,
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
        assert _format_inning(1, "top") == "Top 1st"

    def test_bot_seventh(self):
        assert _format_inning(7, "bottom") == "Bot 7th"

    def test_top_ninth(self):
        assert _format_inning(9, "top") == "Top 9th"

    def test_extras(self):
        assert _format_inning(12, "bottom") == "Bot 12th"


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
        assert result.startswith("Tomorrow")

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
            home_abbr="PHI", away_abbr="NYM",
            home_score=5, away_score=3, state="final",
        )
        assert g.state == "final"
        assert g.home_score == 5


# --- SeriesInfo ---


class TestSeriesInfo:
    def test_empty_series(self):
        s = SeriesInfo(opponent_abbr="NYM")
        assert s.team_wins == 0
        assert s.team_losses == 0


# --- Message Building ---


class TestBuildSeriesTitle:
    def test_builds_title_with_record(self):
        series = SeriesInfo(
            opponent_abbr="NYM",
            games=[],
            team_wins=2,
            team_losses=1,
        )
        msg = _build_series_title("PHI", series, ET)
        assert isinstance(msg, MLBGameMessage)
        text = "".join(t for t, _ in msg.segments)
        assert "Phillies" in text
        assert "Mets" in text
        assert "leads" in text

    def test_tied_series(self):
        series = SeriesInfo(
            opponent_abbr="NYM",
            games=[],
            team_wins=1,
            team_losses=1,
        )
        msg = _build_series_title("PHI", series, ET)
        text = "".join(t for t, _ in msg.segments)
        assert "Tied" in text


class TestBuildGameMessage:
    def test_final_win(self):
        game = GameInfo(
            home_abbr="PHI", away_abbr="NYM",
            home_score=5, away_score=3, state="final",
        )
        msg = _build_game_message(game, "PHI", ET)
        text = "".join(t for t, _ in msg.segments)
        assert "PHI" in text
        assert "5" in text
        assert "Final" in text

    def test_live_game(self):
        game = GameInfo(
            home_abbr="PHI", away_abbr="NYM",
            home_score=3, away_score=2, state="live",
            inning="Bot 7th",
        )
        msg = _build_game_message(game, "PHI", ET)
        text = "".join(t for t, _ in msg.segments)
        assert "LIVE" in text
        assert "Bot 7th" in text

    def test_upcoming_game(self):
        game = GameInfo(
            home_abbr="NYM", away_abbr="PHI",
            state="preview",
            start_time=datetime.now(ET) + timedelta(hours=3),
        )
        msg = _build_game_message(game, "PHI", ET)
        text = "".join(t for t, _ in msg.segments)
        assert "@" in text
        assert "PM" in text or "AM" in text


# --- MLBGameMessage draw ---


class TestMLBGameMessageDraw:
    def test_returns_canvas_and_cursor(self, canvas):
        msg = MLBGameMessage(
            [("PHI", mock.Mock()), ("5", mock.Mock())],
        )
        result_canvas, cursor_pos = msg.draw(canvas)
        assert result_canvas is canvas
        assert cursor_pos > 0

    def test_has_padding_attribute(self):
        msg = MLBGameMessage([("test", mock.Mock())])
        assert hasattr(msg, "padding")
        assert msg.padding == 6


# --- MLBScoreMonitor ---


class TestMLBScoreMonitor:
    def test_has_padding(self):
        widget = MLBScoreMonitor(
            session=mock.Mock(), team="PHI",
        )
        assert widget.padding == 6

    def test_has_feed_stories(self):
        widget = MLBScoreMonitor(
            session=mock.Mock(), team="PHI",
        )
        assert isinstance(widget.feed_stories, list)

    def test_registered(self):
        from led_ticker.widgets import get_widget_class

        cls = get_widget_class("mlb")
        assert cls is MLBScoreMonitor


class TestMLBParsing:
    def test_group_into_series(self):
        widget = MLBScoreMonitor(
            session=mock.Mock(), team="PHI",
        )
        games = [
            GameInfo(
                home_abbr="PHI", away_abbr="NYM", state="final",
                home_score=5, away_score=3,
                start_time=datetime(2026, 6, 1, 19, tzinfo=ET),
            ),
            GameInfo(
                home_abbr="PHI", away_abbr="NYM", state="final",
                home_score=2, away_score=4,
                start_time=datetime(2026, 6, 2, 19, tzinfo=ET),
            ),
            GameInfo(
                home_abbr="PHI", away_abbr="NYM", state="preview",
                start_time=datetime(2026, 6, 3, 19, tzinfo=ET),
            ),
            GameInfo(
                home_abbr="ATL", away_abbr="PHI", state="preview",
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
            session=mock.Mock(), team="PHI",
        )
        widget._tz = ET
        now = datetime.now(ET)
        series = [
            SeriesInfo(
                opponent_abbr="NYM",
                games=[
                    GameInfo(
                        home_abbr="PHI", away_abbr="NYM",
                        state="live", home_score=3, away_score=2,
                        start_time=now - timedelta(hours=1),
                    ),
                ],
            ),
        ]
        result = widget._find_current_series(series, now)
        assert result is not None
        assert result.opponent_abbr == "NYM"
