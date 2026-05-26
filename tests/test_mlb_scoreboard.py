"""Tests for MLBScoreboardMessage and related scoreboard layout support."""

from __future__ import annotations

import attrs

from led_ticker.widgets.mlb import GameInfo, MLBScoreMonitor


def test_gameinfo_challenge_fields_default_to_none():
    g = GameInfo(home_abbr="PHI", away_abbr="NYM")
    assert g.home_challenges is None
    assert g.away_challenges is None


def test_gameinfo_challenge_fields_can_be_set():
    g = GameInfo(home_abbr="PHI", away_abbr="NYM", home_challenges=2, away_challenges=1)
    assert g.home_challenges == 2
    assert g.away_challenges == 1


def test_mlb_score_monitor_layout_defaults_to_ticker():
    field = next(f for f in attrs.fields(MLBScoreMonitor) if f.name == "layout")
    assert field.default == "ticker"


def _make_monitor_for_parse():
    """Return an MLBScoreMonitor wired to parse test data (no real session needed)."""
    import unittest.mock as mock
    from zoneinfo import ZoneInfo

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="PHI")
    monitor._tz = ZoneInfo("America/New_York")
    return monitor


def test_parse_games_extracts_abs_challenges_when_present():
    monitor = _make_monitor_for_parse()
    from zoneinfo import ZoneInfo

    schedule = {
        "dates": [
            {
                "games": [
                    {
                        "gamePk": 1,
                        "gameDate": "2026-05-26T23:10:00Z",
                        "gameType": "R",
                        "status": {
                            "abstractGameState": "Live",
                            "detailedState": "In Progress",
                        },
                        "teams": {
                            "home": {"team": {"abbreviation": "PHI"}, "score": 5},
                            "away": {"team": {"abbreviation": "NYM"}, "score": 3},
                        },
                        "linescore": {
                            "currentInning": 7,
                            "inningHalf": "top",
                            "balls": 1,
                            "strikes": 2,
                            "outs": 1,
                            "offense": {},
                        },
                        "challenges": {
                            "home": {"remainingChallenges": 2},
                            "away": {"remainingChallenges": 1},
                        },
                    }
                ]
            }
        ]
    }
    games = monitor._parse_games(schedule, ZoneInfo("America/New_York"))
    assert len(games) == 1
    assert games[0].home_challenges == 2
    assert games[0].away_challenges == 1


def test_parse_games_challenges_none_when_absent():
    monitor = _make_monitor_for_parse()
    from zoneinfo import ZoneInfo

    schedule = {
        "dates": [
            {
                "games": [
                    {
                        "gamePk": 2,
                        "gameDate": "2026-05-26T23:10:00Z",
                        "gameType": "R",
                        "status": {
                            "abstractGameState": "Live",
                            "detailedState": "In Progress",
                        },
                        "teams": {
                            "home": {"team": {"abbreviation": "PHI"}, "score": 5},
                            "away": {"team": {"abbreviation": "NYM"}, "score": 3},
                        },
                        "linescore": {
                            "currentInning": 7,
                            "inningHalf": "top",
                            "balls": 1,
                            "strikes": 2,
                            "outs": 1,
                            "offense": {},
                        },
                        # no "challenges" key
                    }
                ]
            }
        ]
    }
    games = monitor._parse_games(schedule, ZoneInfo("America/New_York"))
    assert len(games) == 1
    assert games[0].home_challenges is None
    assert games[0].away_challenges is None
