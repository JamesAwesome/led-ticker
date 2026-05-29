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

    def test_preview_top_has_away_at_home(self):
        """Top segments contain AWAY, '@', HOME with team colors."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message, _team_color

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI", state="preview",
            start_time=None,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        texts = [t for t, _ in msg.top_segments]
        colors = [c for _, c in msg.top_segments]
        assert "NYM" in texts
        assert "@" in " ".join(texts)
        assert "PHI" in texts
        nym_idx = texts.index("NYM")
        phi_idx = texts.index("PHI")
        assert colors[nym_idx] == _team_color("NYM")
        assert colors[phi_idx] == _team_color("PHI")

    def test_preview_sets_matchup_abbrs(self):
        """Preview cards carry (away_abbr, home_abbr) so draw() can expand."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(away_abbr="MIA", home_abbr="NYM", state="preview")
        msg = _build_two_row_message(game, "NYM", ZoneInfo("America/New_York"))
        assert msg.matchup == ("MIA", "NYM")

    def test_final_has_no_matchup_expansion(self):
        """Score screens (final / live) don't carry a matchup to expand."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="MIA", home_abbr="NYM",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(game, "NYM", ZoneInfo("America/New_York"))
        assert msg.matchup is None

    def test_matchup_expands_to_full_names_when_room(self):
        """On a wide canvas the abbr matchup expands to full team names."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker.colors import RGB_WHITE
        from led_ticker.fonts import FONT_SMALL
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.widgets.mlb import _expand_matchup_if_fits, _team_color

        opts = RGBMatrixOptions()
        opts.rows = 64
        opts.cols = 256
        opts.chain_length = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        canvas = ScaledCanvas(real, scale=2)  # 128 logical wide — ample room

        top = [
            ("MIA", _team_color("MIA")),
            (" @ ", RGB_WHITE),
            ("NYM", _team_color("NYM")),
        ]
        out = _expand_matchup_if_fits(top, ("MIA", "NYM"), FONT_SMALL, canvas)
        texts = [t for t, _ in out]
        assert "Marlins" in texts
        assert "Mets" in texts
        # Colors preserved through the swap.
        assert out[0][1] == _team_color("MIA")
        assert out[2][1] == _team_color("NYM")

    def test_matchup_keeps_abbrs_when_no_room(self):
        """On a narrow canvas the matchup stays abbreviated (fallback)."""
        from unittest import mock

        from led_ticker.colors import RGB_WHITE
        from led_ticker.fonts import FONT_SMALL
        from led_ticker.widgets.mlb import _expand_matchup_if_fits, _team_color

        narrow = mock.Mock()
        narrow.width = 12  # too narrow for "Marlins @ Mets"
        narrow.height = 16
        top = [
            ("MIA", _team_color("MIA")),
            (" @ ", RGB_WHITE),
            ("NYM", _team_color("NYM")),
        ]
        out = _expand_matchup_if_fits(top, ("MIA", "NYM"), FONT_SMALL, narrow)
        texts = [t for t, _ in out]
        assert texts == ["MIA", " @ ", "NYM"]

    def test_preview_bottom_has_game_time(self):
        """Bottom segments contain a formatted start time."""
        import datetime
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        tz = ZoneInfo("America/New_York")
        # today at 7:10 PM ET
        now = datetime.datetime.now(tz).replace(
            hour=19, minute=10, second=0, microsecond=0
        )
        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI", state="preview", start_time=now
        )
        msg = _build_two_row_message(game, "PHI", tz)
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        assert "7:10" in bottom_text or "PM" in bottom_text

    def test_preview_top_includes_series_record_when_decided(self):
        """Series record appears in top segments when total_decided > 0."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI", state="preview", start_time=None
        )
        msg = _build_two_row_message(
            game, "PHI", ZoneInfo("America/New_York"),
            series_wins=2, series_losses=1,
        )
        top_text = "".join(t for t, _ in msg.top_segments)
        assert "2-1" in top_text

    def test_preview_top_omits_record_when_no_games_decided(self):
        """No record segment when series_wins + series_losses == 0."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI", state="preview", start_time=None
        )
        msg = _build_two_row_message(
            game, "PHI", ZoneInfo("America/New_York"),
            series_wins=0, series_losses=0,
        )
        # exactly: away_abbr, " @ ", home_abbr — no record segment
        assert len(msg.top_segments) == 3

    def test_final_top_away_wins_scores_use_win_loss_colors(self):
        """Away win: away score = WIN_COLOR, home score = LOSS_COLOR."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import LOSS_COLOR, WIN_COLOR, _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        texts = [t for t, _ in msg.top_segments]
        colors = [c for _, c in msg.top_segments]
        # NYM (away) won 5-3: find " 5" score segment
        score_idx_away = next(i for i, t in enumerate(texts) if "5" in t)
        score_idx_home = next(i for i, t in enumerate(texts) if "3" in t)
        assert colors[score_idx_away] is WIN_COLOR
        assert colors[score_idx_home] is LOSS_COLOR

    def test_final_top_home_wins_colors_flipped(self):
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import LOSS_COLOR, WIN_COLOR, _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=3, home_score=8, state="final",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        texts = [t for t, _ in msg.top_segments]
        colors = [c for _, c in msg.top_segments]
        score_idx_away = next(i for i, t in enumerate(texts) if "3" in t)
        score_idx_home = next(i for i, t in enumerate(texts) if "8" in t)
        assert colors[score_idx_away] is LOSS_COLOR
        assert colors[score_idx_home] is WIN_COLOR

    def test_final_bottom_has_final_text(self):
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        assert "FINAL" in bottom_text

    def test_final_bottom_has_series_record_when_multi_game(self):
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(
            game, "PHI", ZoneInfo("America/New_York"),
            series_wins=2, series_losses=1,
            series_total_games=3,
        )
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        assert "leads" in bottom_text or "Tied" in bottom_text

    def test_final_bottom_omits_record_on_single_game(self):
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(
            game, "PHI", ZoneInfo("America/New_York"),
            series_wins=1, series_losses=0,
            series_total_games=1,
        )
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        assert "leads" not in bottom_text
        assert "FINAL" in bottom_text

    def test_live_top_has_team_abbrs_and_scores(self):
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=3, home_score=5, state="live",
            inning="▼7", balls=2, strikes=1, outs=1,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        full = "".join(t for t, _ in msg.top_segments)
        assert "NYM" in full
        assert "PHI" in full
        assert "3" in full
        assert "5" in full

    def test_live_bottom_has_inning(self):
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=3, home_score=5, state="live",
            inning="▼7", balls=2, strikes=1, outs=1,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        assert "▼7" in bottom_text or "7" in bottom_text

    def test_live_bottom_has_base_diamonds(self):
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=3, home_score=5, state="live",
            inning="▼7", balls=2, strikes=1, outs=1,
            on_first=True, on_second=False, on_third=True,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        assert "◆" in bottom_text  # occupied
        assert "◇" in bottom_text  # empty

    def test_live_bottom_bso_colors(self):
        """BSO values: balls=green, strikes=yellow, outs=red.
        Use 3/2/1 so all three values are distinct — avoids dict key collision
        when strikes and outs share a value like '1'.
        """
        from zoneinfo import ZoneInfo

        from led_ticker.colors import make_color
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=3, home_score=5, state="live",
            inning="▼7", balls=3, strikes=2, outs=1,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        ball_c = make_color(80, 255, 80)
        strike_c = make_color(255, 255, 80)
        out_c = make_color(255, 80, 80)
        seg_map = {t: c for t, c in msg.bottom_segments}
        assert seg_map.get("3") == ball_c    # balls
        assert seg_map.get("2") == strike_c  # strikes
        assert seg_map.get("1") == out_c     # outs

    def test_postponed_top_has_matchup(self):
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message, _team_color

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI", state="postponed",
            postpone_tag="PPD", postpone_reason="Rain",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        texts = [t for t, _ in msg.top_segments]
        colors = [c for _, c in msg.top_segments]
        assert "NYM" in texts
        assert "PHI" in texts
        assert colors[texts.index("NYM")] == _team_color("NYM")
        assert colors[texts.index("PHI")] == _team_color("PHI")

    def test_postponed_bottom_has_tag_and_reason(self):
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI", state="postponed",
            postpone_tag="PPD", postpone_reason="Rain",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        assert "PPD" in bottom_text
        assert "Rain" in bottom_text

    def test_postponed_bottom_tag_only_when_no_reason(self):
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI", state="postponed",
            postpone_tag="CANC", postpone_reason="",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        bottom_text = "".join(t for t, _ in msg.bottom_segments)
        assert "CANC" in bottom_text

    def test_pips_hidden_when_challenges_none(self):
        """No pip segments when away/home challenges are None."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
            away_challenges=None, home_challenges=None,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        top_texts = [seg[0] for seg in msg.top_segments]
        assert "-" not in top_texts

    def test_pips_trailing_away_score_one_remaining(self):
        """Away has 1 challenge remaining: 1 orange + 1 grey. Home has 2: 2 orange."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import (
            CHALLENGE_COLOR,
            CHALLENGE_USED,
            _build_two_row_message,
        )

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
            away_challenges=1, home_challenges=2,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        pip_segs = [seg for seg in msg.top_segments if seg[0] == "-"]
        # 2 away pips + 2 home pips = 4 total
        assert len(pip_segs) == 4
        orange_pips = [seg for seg in pip_segs if seg[1] is CHALLENGE_COLOR]
        grey_pips = [seg for seg in pip_segs if seg[1] is CHALLENGE_USED]
        # away=1 remaining → 1 orange; home=2 remaining → 2 orange; total=3
        assert len(orange_pips) == 3
        assert len(grey_pips) == 1

    def test_pips_all_grey_when_zero_remaining(self):
        """Both teams used all challenges: 4 grey dashes."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import CHALLENGE_USED, _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
            away_challenges=0, home_challenges=0,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        pip_segs = [seg for seg in msg.top_segments if seg[0] == "-"]
        assert len(pip_segs) == 4
        assert all(seg[1] is CHALLENGE_USED for seg in pip_segs)

    def test_pips_use_small_font_in_segments(self):
        """Pip segments carry small_font as a per-segment font override."""
        from zoneinfo import ZoneInfo

        from led_ticker.fonts import FONT_SMALL
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
            away_challenges=1, home_challenges=1,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        # 3-tuple segments carry a font override
        pip_segs = [seg for seg in msg.top_segments if seg[0] == "-"]
        assert len(pip_segs) == 4
        for seg in pip_segs:
            assert len(seg) == 3, "pip segments must carry font override"
            assert seg[2] is FONT_SMALL

    def test_pips_use_custom_small_font_when_passed(self):
        """When small_font is passed to _build_two_row_message, pips use it."""
        from zoneinfo import ZoneInfo

        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
            away_challenges=2, home_challenges=0,
        )
        msg = _build_two_row_message(
            game, "PHI", ZoneInfo("America/New_York"), small_font=FONT_DEFAULT
        )
        pip_segs = [seg for seg in msg.top_segments if seg[0] == "-"]
        assert len(pip_segs) == 4
        for seg in pip_segs:
            assert len(seg) == 3
            assert seg[2] is FONT_DEFAULT

    def test_draw_returns_canvas_and_does_not_crash(self, canvas):
        """draw() completes without error and returns (canvas, cursor_pos)."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        result_canvas, cursor = msg.draw(canvas)
        assert result_canvas is canvas
        assert cursor <= canvas.width

    def test_draw_live_does_not_crash(self, canvas):
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=3, home_score=5, state="live",
            inning="▼7", balls=2, strikes=1, outs=1,
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        result_canvas, cursor = msg.draw(canvas)
        assert result_canvas is canvas

    def test_draw_raises_when_hires_font_exceeds_band(self, canvas):
        """Band-overflow guard: a HIRES font taller than its band raises,
        naming the offending row.

        The guard is universal (BDF and hires alike) — mirrors
        TwoRowMessage.draw. On the 160x16 scale=1 canvas each band is 8
        logical rows; Inter@40 far exceeds that, so it doesn't fit.
        """
        from zoneinfo import ZoneInfo

        import pytest

        from led_ticker.fonts import resolve_font
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        big_font = resolve_font("Inter-Regular", 40)
        msg = _build_two_row_message(
            game, "PHI", ZoneInfo("America/New_York"), font=big_font
        )
        with pytest.raises(ValueError, match="line-height"):
            msg.draw(canvas)

    def test_draw_raises_when_bdf_font_exceeds_band(self, canvas):
        """Universal guard: a too-tall BDF font also raises (not just hires).

        FONT_DEFAULT is 6x12 (line-height 12 logical); each band on the
        160x16 scale=1 canvas is 8 logical rows, so 12 > 8 overflows. This
        is the behavior the universal guard adds over a hires-only scope.
        The widget's actual default (FONT_SMALL, line-height 8) fits, so
        this only fires when a config explicitly picks a taller BDF font.
        """
        from zoneinfo import ZoneInfo

        import pytest

        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(
            game, "PHI", ZoneInfo("America/New_York"), font=FONT_DEFAULT
        )
        with pytest.raises(ValueError, match="line-height"):
            msg.draw(canvas)

    def test_draw_default_font_fits_default_band(self, canvas):
        """The no-font default (FONT_SMALL) fits the default 8-row band."""
        from zoneinfo import ZoneInfo

        from led_ticker.fonts import FONT_SMALL
        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(game, "PHI", ZoneInfo("America/New_York"))
        assert msg.font is FONT_SMALL
        # Must not raise — FONT_SMALL line-height 8 == band 8.
        msg.draw(canvas)

    def test_top_font_threads_through_from_monitor(self):
        """top_font set on MLBScoreMonitor reaches MLBTwoRowMessage instances."""
        from unittest import mock

        from led_ticker.fonts import FONT_DEFAULT
        m = MLBScoreMonitor(
            session=mock.Mock(), team="PHI",
            layout="two_row", top_font=FONT_DEFAULT,
        )
        assert m.top_font is FONT_DEFAULT

    def test_top_row_height_threads_through_to_message(self):
        """top_row_height on MLBScoreMonitor threads to MLBTwoRowMessage."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_message

        game = GameInfo(
            away_abbr="NYM", home_abbr="PHI",
            away_score=5, home_score=3, state="final",
        )
        msg = _build_two_row_message(
            game, "PHI", ZoneInfo("America/New_York"), top_row_height=4
        )
        assert msg.top_row_height == 4

    def test_dispatch_two_row_branch_exists_in_update(self):
        """Tripwire: update() source contains the two_row dispatch branch.

        Confirms the elif dispatch hasn't been removed or renamed, which would
        cause layout='two_row' to silently fall through to the ticker layout.
        """
        import inspect

        from led_ticker.widgets.mlb import MLBScoreMonitor

        source = inspect.getsource(MLBScoreMonitor.update)
        assert 'layout == "two_row"' in source, (
            "The 'layout == \"two_row\"' dispatch branch is missing from "
            "MLBScoreMonitor.update — layout='two_row' would silently fall "
            "through to ticker layout."
        )

    def test_dispatch_two_row_produces_mlb_two_row_message_instances(self):
        """Tripwire: _build_two_row_message is routed for all game states.

        Verifies that the factory itself returns MLBTwoRowMessage for every
        game state that the dispatch branch would encounter in update().
        """
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import MLBTwoRowMessage, _build_two_row_message

        tz = ZoneInfo("America/New_York")

        states_and_games = [
            GameInfo(away_abbr="NYM", home_abbr="PHI", state="preview"),
            GameInfo(
                away_abbr="NYM", home_abbr="PHI",
                away_score=3, home_score=5, state="final",
            ),
            GameInfo(
                away_abbr="NYM", home_abbr="PHI",
                away_score=1, home_score=2, state="live",
                inning="▼5", balls=1, strikes=2, outs=1,
            ),
            GameInfo(
                away_abbr="NYM", home_abbr="PHI",
                state="postponed", postpone_tag="PPD",
            ),
        ]
        for game in states_and_games:
            msg = _build_two_row_message(game, "PHI", tz)
            assert isinstance(msg, MLBTwoRowMessage), (
                f"Expected MLBTwoRowMessage for state={game.state!r}, "
                f"got {type(msg).__name__}"
            )

    def test_series_title_is_two_row_message(self):
        """The two_row series title is an MLBTwoRowMessage, not a SegmentMessage."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import (
            MLBTwoRowMessage,
            _build_two_row_series_title,
        )

        series = SeriesInfo(
            opponent_abbr="NYM",
            games=[GameInfo(away_abbr="NYM", home_abbr="PHI", state="preview")],
        )
        title = _build_two_row_series_title(
            "PHI", series, ZoneInfo("America/New_York")
        )
        assert isinstance(title, MLBTwoRowMessage)

    def test_series_title_top_band_has_matchup_with_team_colors(self):
        """Top band carries Away @ Home in team colors."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_series_title, _team_color

        series = SeriesInfo(
            opponent_abbr="NYM",
            games=[GameInfo(away_abbr="NYM", home_abbr="PHI", state="preview")],
        )
        title = _build_two_row_series_title(
            "PHI", series, ZoneInfo("America/New_York")
        )
        top_text = "".join(t for t, _ in title.top_segments)
        assert "@" in top_text
        assert "Mets" in top_text  # away (NYM) full name
        assert "Phillies" in top_text  # home (PHI) full name
        colors = [c for _, c in title.top_segments]
        assert _team_color("NYM") in colors
        assert _team_color("PHI") in colors

    def test_series_title_bottom_band_has_record_when_multi_game_decided(self):
        """Bottom band shows the leader-relative record on a decided series."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_series_title

        series = SeriesInfo(
            opponent_abbr="NYM",
            games=[
                GameInfo(away_abbr="NYM", home_abbr="PHI", state="final"),
                GameInfo(away_abbr="NYM", home_abbr="PHI", state="final"),
                GameInfo(away_abbr="NYM", home_abbr="PHI", state="preview"),
            ],
            team_wins=2,
            team_losses=1,
        )
        title = _build_two_row_series_title(
            "PHI", series, ZoneInfo("America/New_York")
        )
        bottom_text = "".join(t for t, _ in title.bottom_segments)
        assert "leads" in bottom_text
        assert "2-1" in bottom_text
        assert "PHI" in bottom_text  # monitored team leads

    def test_series_title_bottom_band_empty_on_single_game(self):
        """No record on the bottom band for a one-game series."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_series_title

        series = SeriesInfo(
            opponent_abbr="NYM",
            games=[GameInfo(away_abbr="NYM", home_abbr="PHI", state="preview")],
            team_wins=0,
            team_losses=0,
        )
        title = _build_two_row_series_title(
            "PHI", series, ZoneInfo("America/New_York")
        )
        assert title.bottom_segments == []

    def test_series_title_bottom_band_shows_spring_badge(self):
        """Spring-training series surfaces the (ST) badge on the bottom band."""
        from zoneinfo import ZoneInfo

        from led_ticker.widgets.mlb import _build_two_row_series_title

        series = SeriesInfo(
            opponent_abbr="NYM",
            games=[
                GameInfo(
                    away_abbr="NYM", home_abbr="PHI",
                    state="preview", game_type="S",
                )
            ],
        )
        title = _build_two_row_series_title(
            "PHI", series, ZoneInfo("America/New_York")
        )
        bottom_text = "".join(t for t, _ in title.bottom_segments)
        assert "(ST)" in bottom_text

    def test_series_title_threads_per_row_fields(self):
        """top_font and top_row_height reach the title MLBTwoRowMessage."""
        from zoneinfo import ZoneInfo

        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.widgets.mlb import _build_two_row_series_title

        series = SeriesInfo(
            opponent_abbr="NYM",
            games=[GameInfo(away_abbr="NYM", home_abbr="PHI", state="preview")],
        )
        title = _build_two_row_series_title(
            "PHI", series, ZoneInfo("America/New_York"),
            top_font=FONT_DEFAULT, top_row_height=6,
        )
        assert title.top_font is FONT_DEFAULT
        assert title.top_row_height == 6
