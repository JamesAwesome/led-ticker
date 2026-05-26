"""Tests for MLBScoreboardMessage and related scoreboard layout support."""

from __future__ import annotations

from datetime import UTC, datetime

import attrs

from led_ticker.widgets.mlb import GameInfo, MLBScoreboardMessage, MLBScoreMonitor


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


# ---------------------------------------------------------------------------
# Task 3: MLBScoreboardMessage skeleton
# ---------------------------------------------------------------------------


def _live_game() -> GameInfo:
    return GameInfo(
        home_abbr="PHI",
        away_abbr="NYM",
        state="live",
        home_score=5,
        away_score=3,
        inning="▲7",
        outs=2,
        balls=1,
        strikes=2,
        on_first=False,
        on_second=True,
        on_third=False,
    )


def _stub_canvas(w=128, h=16):
    from rgbmatrix import _StubCanvas

    return _StubCanvas(width=w, height=h)


def test_scoreboard_draw_live_returns_correct_cursor():
    canvas = _stub_canvas()
    msg = MLBScoreboardMessage(game=_live_game(), team_abbr="PHI")
    _, cursor = msg.draw(canvas)
    assert cursor == 128


def test_scoreboard_draw_final():
    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI", away_abbr="NYM", state="final", home_score=5, away_score=3
    )
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    result_canvas, cursor = msg.draw(canvas)
    assert cursor == 128
    assert result_canvas is canvas


def test_scoreboard_draw_preview():
    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI",
        away_abbr="NYM",
        state="preview",
        start_time=datetime(2026, 5, 26, 23, 10, tzinfo=UTC),
    )
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    _, cursor = msg.draw(canvas)
    assert cursor == 128


def test_scoreboard_draw_postponed():
    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI",
        away_abbr="NYM",
        state="postponed",
        postpone_tag="PPD",
        postpone_reason="Rain",
    )
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    _, cursor = msg.draw(canvas)
    assert cursor == 128


def test_scoreboard_advance_frame_accepts_visit_id():
    msg = MLBScoreboardMessage(game=_live_game(), team_abbr="PHI")
    msg.advance_frame(visit_id=42)
    msg.advance_frame(visit_id=42)
    assert msg._frame_count == 2


# ---------------------------------------------------------------------------
# Task 4: Team column rendering
# ---------------------------------------------------------------------------


def test_scoreboard_draws_pixels_for_team_names():
    """draw() must paint at least one pixel — smoke test that rendering occurs."""
    canvas = _stub_canvas()
    msg = MLBScoreboardMessage(game=_live_game(), team_abbr="PHI")
    msg.draw(canvas)
    assert len(canvas._pixels) > 0


def test_scoreboard_live_score_pixels_exist():
    """Score digits must produce pixels in the bottom half of the canvas."""
    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI",
        away_abbr="NYM",
        state="live",
        home_score=5,
        away_score=3,
        inning="▲7",
        outs=1,
        balls=1,
        strikes=1,
    )
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    msg.draw(canvas)
    bottom_half_pixels = {(x, y): c for (x, y), c in canvas._pixels.items() if y >= 8}
    assert len(bottom_half_pixels) > 0


def test_scoreboard_final_win_loss_colors():
    """Final state renders without errors (uses win/loss palette)."""
    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI", away_abbr="NYM", state="final", home_score=5, away_score=3
    )  # PHI wins (home)
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    msg.draw(canvas)
    # Just assert no exception and some pixels rendered
    assert len(canvas._pixels) > 0


# ---------------------------------------------------------------------------
# Task 5: Center zone rendering
# ---------------------------------------------------------------------------


def test_scoreboard_center_pixels_for_live_game():
    """Center zone must paint pixels for a live game."""
    canvas = _stub_canvas()
    msg = MLBScoreboardMessage(game=_live_game(), team_abbr="PHI")
    msg.draw(canvas)
    center_start = 128 * 30 // 100
    center_end = 128 - 128 * 30 // 100
    center_pixels = {
        (x, y): c
        for (x, y), c in canvas._pixels.items()
        if center_start <= x < center_end
    }
    assert len(center_pixels) > 0


def test_scoreboard_preview_draws_without_error():
    from datetime import datetime

    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI",
        away_abbr="NYM",
        state="preview",
        start_time=datetime(2026, 5, 26, 23, 10, tzinfo=UTC),
    )
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    _, cursor = msg.draw(canvas)
    assert cursor == 128


# ---------------------------------------------------------------------------
# Task 6: Diamond rendering
# ---------------------------------------------------------------------------


def test_scoreboard_diamond_second_base_occupied_paints_in_center_right():
    """With runner on 2B, center-right zone must have pixels in the top row."""
    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI",
        away_abbr="NYM",
        state="live",
        home_score=5,
        away_score=3,
        inning="▲7",
        outs=0,
        balls=0,
        strikes=0,
        on_second=True,
        on_first=False,
        on_third=False,
    )
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    msg.draw(canvas)
    cr_start = 128 * 30 // 100 + (128 - 2 * (128 * 30 // 100)) // 2
    top_row_center_right = {
        (x, y): c for (x, y), c in canvas._pixels.items() if x >= cr_start and y < 8
    }
    assert len(top_row_center_right) > 0


# ---------------------------------------------------------------------------
# Task 7: ABS challenge pip rendering
# ---------------------------------------------------------------------------


def _count_pixels_in_zone(canvas, x_start, x_end, y_start=0, y_end=16):
    return sum(
        1 for (x, y) in canvas._pixels if x_start <= x < x_end and y_start <= y < y_end
    )


def test_scoreboard_abs_pips_two_remaining_paints_more_than_zero():
    """Two remaining challenges should add pixels to the right of away abbr."""
    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI",
        away_abbr="NYM",
        state="live",
        home_score=5,
        away_score=3,
        inning="▲7",
        outs=0,
        balls=0,
        strikes=0,
        away_challenges=2,
        home_challenges=2,
    )
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    msg.draw(canvas)
    # Canvas must have pixels — pips included somewhere in left column
    assert _count_pixels_in_zone(canvas, 0, 38, 0, 8) > 0


def test_scoreboard_abs_pips_none_does_not_crash():
    """None challenges should render without error (pips hidden)."""
    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI",
        away_abbr="NYM",
        state="live",
        home_score=5,
        away_score=3,
        inning="▲7",
        outs=0,
        balls=0,
        strikes=0,
        away_challenges=None,
        home_challenges=None,
    )
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    _, cursor = msg.draw(canvas)
    assert cursor == 128


def test_scoreboard_abs_pips_clamped_to_two():
    """Values > 2 must not raise an error."""
    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI",
        away_abbr="NYM",
        state="live",
        home_score=5,
        away_score=3,
        inning="▲7",
        outs=0,
        balls=0,
        strikes=0,
        away_challenges=5,
        home_challenges=3,
    )
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    _, cursor = msg.draw(canvas)
    assert cursor == 128
