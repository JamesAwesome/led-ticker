"""Tests for MLB standings widget."""

import unittest.mock as mock

import pytest

from led_ticker.colors import RGB_WHITE
from led_ticker.widgets.message import TickerMessage
from led_ticker.widgets.mlb import MLBGameMessage
from led_ticker.widgets.mlb_standings import (
    MLBStandingsMonitor,
    TeamStanding,
    _build_standing_message,
)

# --- TeamStanding ---


class TestTeamStanding:
    def test_leader(self):
        s = TeamStanding(name="Yankees", wins=45, losses=20, rank=1, games_back="-")
        assert s.rank == 1
        assert s.games_back == "-"

    def test_non_leader(self):
        s = TeamStanding(name="Mets", wins=35, losses=30, rank=12, games_back="10.0")
        assert s.rank == 12
        assert s.games_back == "10.0"


# --- _build_standing_message ---


class TestBuildStandingMessage:
    def test_basic_format(self):
        s = TeamStanding(name="Yankees", wins=45, losses=20, rank=1, games_back="-")
        msg = _build_standing_message(s)
        assert isinstance(msg, MLBGameMessage)
        texts = [t for t, _ in msg.segments]
        assert texts[0] == "1. "
        assert texts[1] == "Yankees"
        assert texts[2] == " 45-20"
        assert texts[3] == " -"

    def test_rank_numbers_white(self):
        s = TeamStanding(name="Dodgers", wins=42, losses=23, rank=2, games_back="3.0")
        msg = _build_standing_message(s)
        colors = [c for _, c in msg.segments]
        assert colors[0] is RGB_WHITE  # rank
        assert colors[2] is RGB_WHITE  # record
        assert colors[3] is RGB_WHITE  # GB

    def test_team_color_applied(self):
        s = TeamStanding(name="Phillies", wins=40, losses=25, rank=3, games_back="5.0")
        msg = _build_standing_message(s)
        colors = [c for _, c in msg.segments]
        # Team name should use team color, not white
        assert colors[1] is not RGB_WHITE

    def test_gb_leader(self):
        s = TeamStanding(name="Yankees", wins=50, losses=15, rank=1, games_back="-")
        msg = _build_standing_message(s)
        texts = [t for t, _ in msg.segments]
        assert texts[3] == " -"

    def test_gb_behind(self):
        s = TeamStanding(name="Orioles", wins=41, losses=24, rank=3, games_back="9.5")
        msg = _build_standing_message(s)
        texts = [t for t, _ in msg.segments]
        assert texts[3] == " 9.5"

    def test_message_is_centered(self):
        s = TeamStanding(name="Yankees", wins=45, losses=20, rank=1, games_back="-")
        msg = _build_standing_message(s)
        assert msg.center is True

    def test_draw_returns_canvas_and_cursor(self, canvas):
        s = TeamStanding(name="Yankees", wins=45, losses=20, rank=1, games_back="-")
        msg = _build_standing_message(s)
        result_canvas, cursor_pos = msg.draw(canvas)
        assert result_canvas is canvas
        assert cursor_pos > 0


# --- MLBStandingsMonitor ---


class TestMLBStandingsMonitor:
    def test_registered(self):
        from led_ticker.widgets import get_widget_class

        cls = get_widget_class("mlb_standings")
        assert cls is MLBStandingsMonitor

    def test_has_feed_stories(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM", "PHI"],
        )
        assert isinstance(widget.feed_stories, list)

    def test_default_top_n(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM"],
        )
        assert widget.top_n == 3

    def test_custom_top_n(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM"],
            top_n=5,
        )
        assert widget.top_n == 5

    def test_default_title(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM"],
        )
        assert widget.title == "MLB Standings"

    def test_custom_title(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM"],
            title="NL Standings",
        )
        assert widget.title == "NL Standings"

    def test_has_padding(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM"],
        )
        assert widget.padding == 6


# --- Parsing ---


class TestStandingsParsing:
    def _make_api_response(self, team_records):
        """Build a mock MLB API standings response."""
        return {"records": [{"teamRecords": team_records}]}

    def _make_team_record(self, name, wins, losses, rank, gb="-"):
        return {
            "team": {"name": name},
            "wins": wins,
            "losses": losses,
            "sportRank": str(rank),
            "sportGamesBack": gb,
        }

    def test_parse_and_sort(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM"],
        )
        data = self._make_api_response(
            [
                self._make_team_record("Orioles", 41, 24, 3, "4.0"),
                self._make_team_record("Yankees", 45, 20, 1, "-"),
                self._make_team_record("Dodgers", 42, 23, 2, "3.0"),
            ]
        )
        standings = widget._parse_standings(data)
        assert len(standings) == 3
        assert standings[0].name == "Yankees"
        assert standings[1].name == "Dodgers"
        assert standings[2].name == "Orioles"

    def test_top_n_and_tracked(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM", "PHI"],
            top_n=2,
        )
        data = self._make_api_response(
            [
                self._make_team_record("Yankees", 45, 20, 1, "-"),
                self._make_team_record("Dodgers", 42, 23, 2, "3.0"),
                self._make_team_record("Orioles", 41, 24, 3, "4.0"),
                self._make_team_record("Mets", 35, 30, 12, "10.0"),
                self._make_team_record("Phillies", 33, 32, 15, "12.0"),
            ]
        )
        standings = widget._parse_standings(data)

        from led_ticker.widgets.mlb import MLB_NAME_TO_ABBR

        # Simulate update logic (title not in stories, only in feed_title)
        stories: list = []
        top_names = set()
        for s in standings[: widget.top_n]:
            top_names.add(s.name)
            stories.append(_build_standing_message(s))
        standings_by_abbr: dict = {}
        for s in standings:
            abbr = MLB_NAME_TO_ABBR.get(s.name, "")
            if abbr:
                standings_by_abbr[abbr] = s
        for team in widget.teams:
            s = standings_by_abbr.get(team)
            if s and s.name not in top_names:
                stories.append(_build_standing_message(s))

        # 2 top + 2 tracked = 4
        assert len(stories) == 4
        # Stories 0-1 are top 2
        texts_0 = [t for t, _ in stories[0].segments]
        assert texts_0[0] == "1. "
        texts_1 = [t for t, _ in stories[1].segments]
        assert texts_1[0] == "2. "
        # Stories 2-3 are tracked teams
        texts_2 = [t for t, _ in stories[2].segments]
        assert texts_2[1] == "Mets"
        texts_3 = [t for t, _ in stories[3].segments]
        assert texts_3[1] == "Phillies"

    def test_tracked_team_skipped_if_in_top_n(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYY"],
            top_n=3,
        )
        data = self._make_api_response(
            [
                self._make_team_record("Yankees", 45, 20, 1, "-"),
                self._make_team_record("Dodgers", 42, 23, 2, "3.0"),
                self._make_team_record("Orioles", 41, 24, 3, "4.0"),
                self._make_team_record("Mets", 35, 30, 12, "10.0"),
            ]
        )
        standings = widget._parse_standings(data)

        from led_ticker.widgets.mlb import MLB_NAME_TO_ABBR

        stories: list = []
        top_names = set()
        for s in standings[: widget.top_n]:
            top_names.add(s.name)
            stories.append(_build_standing_message(s))
        standings_by_abbr: dict = {}
        for s in standings:
            abbr = MLB_NAME_TO_ABBR.get(s.name, "")
            if abbr:
                standings_by_abbr[abbr] = s
        for team in widget.teams:
            s = standings_by_abbr.get(team)
            if s and s.name not in top_names:
                stories.append(_build_standing_message(s))

        # 3 top, NYY skipped in tracked section = 3
        assert len(stories) == 3

    def test_empty_response(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM"],
        )
        data = {"records": []}
        standings = widget._parse_standings(data)
        assert standings == []

    def test_multiple_divisions(self):
        """API returns multiple division records; all should be flattened."""
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM"],
        )
        data = {
            "records": [
                {
                    "teamRecords": [
                        self._make_team_record("Yankees", 45, 20, 1, "-"),
                    ]
                },
                {
                    "teamRecords": [
                        self._make_team_record("Dodgers", 42, 23, 2, "3.0"),
                    ]
                },
            ],
        }
        standings = widget._parse_standings(data)
        assert len(standings) == 2
        assert standings[0].name == "Yankees"
        assert standings[1].name == "Dodgers"


# --- Offseason ---


class TestOffseason:
    def test_all_zeros_detected(self):
        """When all teams have 0-0 records, season hasn't started."""
        standings = [
            TeamStanding(name="Yankees", wins=0, losses=0, rank=1, games_back="-"),
            TeamStanding(name="Dodgers", wins=0, losses=0, rank=2, games_back="-"),
            TeamStanding(name="Mets", wins=0, losses=0, rank=3, games_back="-"),
        ]
        assert all(s.wins == 0 and s.losses == 0 for s in standings)

    def test_not_all_zeros_when_games_played(self):
        standings = [
            TeamStanding(name="Yankees", wins=1, losses=0, rank=1, games_back="-"),
            TeamStanding(name="Dodgers", wins=0, losses=1, rank=2, games_back="1.0"),
        ]
        assert not all(s.wins == 0 and s.losses == 0 for s in standings)

    def _make_session(self, *, all_zero: bool = True, schedule_dates=None):
        """Mock aiohttp session that routes by URL.

        - /standings -> records with all-zero records (offseason) or sample data
        - /teams -> abbr->id map for tracked teams
        - /schedule -> game dates (or empty for fallback path)
        """
        session = mock.MagicMock()

        def make_ctx(url, *args, **kwargs):
            resp = mock.AsyncMock()
            if "/standings" in url:
                if all_zero:
                    resp.json.return_value = {
                        "records": [
                            {
                                "teamRecords": [
                                    {
                                        "team": {"name": "New York Mets"},
                                        "wins": 0,
                                        "losses": 0,
                                        "sportRank": "1",
                                        "sportGamesBack": "-",
                                    },
                                    {
                                        "team": {"name": "New York Yankees"},
                                        "wins": 0,
                                        "losses": 0,
                                        "sportRank": "2",
                                        "sportGamesBack": "-",
                                    },
                                ]
                            }
                        ]
                    }
                else:
                    resp.json.return_value = {
                        "records": [
                            {
                                "teamRecords": [
                                    {
                                        "team": {"name": "New York Mets"},
                                        "wins": 5,
                                        "losses": 2,
                                        "sportRank": "1",
                                        "sportGamesBack": "-",
                                    }
                                ]
                            }
                        ]
                    }
            elif "/teams" in url:
                resp.json.return_value = {
                    "teams": [
                        {"id": 121, "abbreviation": "NYM"},
                        {"id": 147, "abbreviation": "NYY"},
                    ]
                }
            elif "/schedule" in url:
                if schedule_dates:
                    resp.json.return_value = {
                        "dates": [{"games": [{"gameDate": d} for d in schedule_dates]}]
                    }
                else:
                    resp.json.return_value = {"dates": []}
            else:
                resp.json.return_value = {}

            ctx = mock.AsyncMock()
            ctx.__aenter__.return_value = resp
            return ctx

        session.get.side_effect = make_ctx
        return session

    @pytest.mark.asyncio
    async def test_update_routes_to_offseason_when_all_zero(self):
        # Drive update() — assert behavior, not pre-set state.
        session = self._make_session(
            all_zero=True,
            schedule_dates=["2026-03-27T17:00:00Z"],
        )
        widget = MLBStandingsMonitor(session=session, teams=["NYM"])
        widget._tz = __import__("zoneinfo").ZoneInfo("America/New_York")

        await widget.update()

        assert len(widget.feed_stories) == 1
        # Offseason path produced an "Opens <date>" message
        assert widget.feed_stories[0].message.startswith("Opens ")
        # Title is set
        assert widget.feed_title is not None

    @pytest.mark.asyncio
    async def test_update_offseason_fallback_when_no_schedule(self):
        # All-zero standings + empty schedule → "Opens soon"
        session = self._make_session(all_zero=True, schedule_dates=None)
        widget = MLBStandingsMonitor(session=session, teams=["NYM"])
        widget._tz = __import__("zoneinfo").ZoneInfo("America/New_York")

        await widget.update()

        assert len(widget.feed_stories) == 1
        assert widget.feed_stories[0].message == "Opens soon"

    @pytest.mark.asyncio
    async def test_update_skips_offseason_when_games_played(self):
        # Some non-zero records → normal path, NOT offseason.
        session = self._make_session(all_zero=False)
        widget = MLBStandingsMonitor(session=session, teams=["NYM"], top_n=1)
        widget._tz = __import__("zoneinfo").ZoneInfo("America/New_York")

        await widget.update()

        # Should have a real standings story, not "Opens ..."
        assert len(widget.feed_stories) >= 1
        first_msg = widget.feed_stories[0]
        # MLBGameMessage doesn't have a single .message; just verify it's not
        # the offseason TickerMessage.
        if isinstance(first_msg, TickerMessage):
            assert not first_msg.message.startswith("Opens")

    @pytest.mark.asyncio
    async def test_update_handles_api_error_gracefully(self):
        # Network failure → _set_error_state() puts a "No Data" story.
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        widget = MLBStandingsMonitor(session=session, teams=["NYM"])
        widget._tz = __import__("zoneinfo").ZoneInfo("America/New_York")

        # Should not propagate the exception
        await widget.update()

        assert len(widget.feed_stories) == 1
        assert widget.feed_stories[0].message == "No Data"
