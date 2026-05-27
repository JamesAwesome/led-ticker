"""Tests for MLBScoreboardMessage and related scoreboard layout support."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import attrs
import pytest

from led_ticker.widgets.mlb import (
    GameInfo,
    MLBScoreboardMessage,
    MLBScoreMonitor,
    SeriesInfo,
)


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


def _challenges_game_fixture(challenges: dict) -> dict:
    """Schedule fixture with the given challenges value."""
    return {
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
                        "challenges": challenges,
                    }
                ]
            }
        ]
    }


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


async def _run_update_with_schedule(layout: str, schedule: dict):
    """Helper: build a monitor, inject a schedule response, run update()."""
    import unittest.mock as mock
    from zoneinfo import ZoneInfo

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="PHI", layout=layout)
    monitor._team_id = 143  # PHI's real ID — skip team resolution
    monitor._tz = ZoneInfo("America/New_York")

    resp = mock.AsyncMock()
    resp.json = mock.AsyncMock(return_value=schedule)
    session.get.return_value.__aenter__ = mock.AsyncMock(return_value=resp)
    session.get.return_value.__aexit__ = mock.AsyncMock(return_value=False)

    await monitor.update()
    return monitor


def _phi_nym_schedule(state: str = "live") -> dict:
    return {
        "dates": [
            {
                "games": [
                    {
                        "gamePk": 1,
                        "gameDate": "2026-05-26T23:10:00Z",
                        "gameType": "R",
                        "status": {
                            "abstractGameState": "Live" if state == "live" else "Final",
                            "detailedState": "In Progress"
                            if state == "live"
                            else "Final",
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
                    }
                ]
            }
        ]
    }


def test_scoreboard_draw_off_day():
    canvas = _stub_canvas()
    game = GameInfo(home_abbr="PHI", away_abbr="", state="off_day")
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI")
    _, cursor = msg.draw(canvas)
    assert cursor == 128


@pytest.mark.asyncio
async def test_layout_scoreboard_builds_scoreboard_messages():
    monitor = await _run_update_with_schedule("scoreboard", _phi_nym_schedule())
    game_stories = [
        s for s in monitor.feed_stories if isinstance(s, MLBScoreboardMessage)
    ]
    assert len(game_stories) >= 1


@pytest.mark.asyncio
async def test_layout_ticker_builds_game_messages():
    from led_ticker.widgets.mlb import MLBGameMessage

    monitor = await _run_update_with_schedule("ticker", _phi_nym_schedule())
    game_stories = [s for s in monitor.feed_stories if isinstance(s, MLBGameMessage)]
    assert len(game_stories) >= 1


# ---------------------------------------------------------------------------
# _fit_team_name: full name vs abbreviation fallback
# ---------------------------------------------------------------------------


def test_fit_team_name_returns_name_when_it_fits():
    """Short names like 'Mets' should fit in a 128px column and be returned."""
    from led_ticker.fonts import FONT_DEFAULT
    from led_ticker.widgets.mlb import _fit_team_name

    canvas = _stub_canvas(w=128, h=16)
    # 'Mets' is 4 chars — should easily fit in a 38px zone
    result = _fit_team_name("NYM", 38, FONT_DEFAULT, canvas)
    assert result == "Mets"


def test_fit_team_name_falls_back_to_abbr_when_too_wide():
    """On a narrow canvas, even short names should fall back to the abbreviation."""
    from led_ticker.fonts import FONT_DEFAULT
    from led_ticker.widgets.mlb import _fit_team_name

    canvas = _stub_canvas(w=32, h=16)
    # zone_w=0 — nothing fits except empty string; any name should fall back
    result = _fit_team_name("NYM", 0, FONT_DEFAULT, canvas)
    assert result == "NYM"


def test_fit_team_name_unknown_abbr_returns_abbr():
    """An unknown abbreviation returns itself regardless of zone width."""
    from led_ticker.fonts import FONT_DEFAULT
    from led_ticker.widgets.mlb import _fit_team_name

    canvas = _stub_canvas(w=128, h=16)
    result = _fit_team_name("XYZ", 200, FONT_DEFAULT, canvas)
    assert result == "XYZ"


# ---------------------------------------------------------------------------
# small_font field
# ---------------------------------------------------------------------------


def test_scoreboard_small_font_defaults_to_font_small():
    """small_font attr exists and defaults to FONT_SMALL."""
    from led_ticker.fonts import FONT_SMALL

    msg = MLBScoreboardMessage(game=_live_game(), team_abbr="PHI")
    assert msg.small_font is FONT_SMALL


def test_scoreboard_small_font_accepted_as_kwarg():
    """small_font can be overridden at construction time."""
    from led_ticker.fonts import FONT_DEFAULT

    msg = MLBScoreboardMessage(
        game=_live_game(), team_abbr="PHI", small_font=FONT_DEFAULT
    )
    assert msg.small_font is FONT_DEFAULT


def test_build_scoreboard_message_threads_small_font():
    """_build_scoreboard_message passes small_font into the built object."""
    from zoneinfo import ZoneInfo

    from led_ticker.fonts import FONT_DEFAULT
    from led_ticker.widgets.mlb import _build_scoreboard_message

    game = _live_game()
    msg = _build_scoreboard_message(
        game,
        team_abbr="PHI",
        tz=ZoneInfo("America/New_York"),
        small_font=FONT_DEFAULT,
    )
    assert msg.small_font is FONT_DEFAULT


def test_scoreboard_draw_uses_self_small_font_not_hardcoded():
    """Center zone draws must route through self.small_font, not FONT_SMALL.

    Strategy: pass FONT_DEFAULT as small_font (a different object than FONT_SMALL),
    then spy on draw_with_emoji calls to verify FONT_SMALL is never passed when a
    custom small_font is set.
    """
    from led_ticker.fonts import FONT_DEFAULT, FONT_SMALL
    from led_ticker.pixel_emoji import draw_with_emoji as real_dwe

    canvas = _stub_canvas()
    game = GameInfo(
        home_abbr="PHI",
        away_abbr="NYM",
        state="live",
        home_score=5,
        away_score=3,
        inning="▲7",
        outs=2,
        balls=1,
        strikes=2,
        on_first=True,
        on_second=False,
        on_third=False,
    )
    # Use FONT_DEFAULT as the small_font — it's a different object than FONT_SMALL
    msg = MLBScoreboardMessage(game=game, team_abbr="PHI", small_font=FONT_DEFAULT)

    fonts_drawn = []

    def _spy_dwe(canvas, font, *args, **kwargs):
        fonts_drawn.append(font)
        return real_dwe(canvas, font, *args, **kwargs)

    import unittest.mock as mock

    with mock.patch("led_ticker.pixel_emoji.draw_with_emoji", side_effect=_spy_dwe):
        msg.draw(canvas)

    assert (
        FONT_DEFAULT in fonts_drawn
    ), "small_font (FONT_DEFAULT) was never used in draw()"
    assert (
        FONT_SMALL not in fonts_drawn
    ), "hardcoded FONT_SMALL is still being used in draw()"


# ---------------------------------------------------------------------------
# MLBScoreMonitor.small_font
# ---------------------------------------------------------------------------


def test_monitor_small_font_defaults_to_font_small():
    """MLBScoreMonitor.small_font defaults to FONT_SMALL."""
    import unittest.mock as mock

    from led_ticker.fonts import FONT_SMALL

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="PHI")
    assert monitor.small_font is FONT_SMALL


@pytest.mark.asyncio
async def test_monitor_threads_small_font_to_scoreboard_messages():
    """When layout=scoreboard, update() passes small_font to each built message."""
    import unittest.mock as mock
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    from led_ticker.fonts import FONT_DEFAULT

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(
        session=session,
        team="PHI",
        layout="scoreboard",
        small_font=FONT_DEFAULT,
    )
    monitor._tz = ZoneInfo("America/New_York")
    monitor._team_id = 143  # PHI team id — skip resolve step

    now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    schedule = {
        "dates": [
            {
                "games": [
                    {
                        "gamePk": 1,
                        "gameDate": now_str,
                        "gameType": "R",
                        "status": {
                            "abstractGameState": "Live",
                            "detailedState": "In Progress",
                        },
                        "teams": {
                            "home": {"team": {"abbreviation": "PHI"}, "score": 3},
                            "away": {"team": {"abbreviation": "NYM"}, "score": 1},
                        },
                        "linescore": {
                            "currentInning": 4,
                            "inningHalf": "top",
                            "balls": 0,
                            "strikes": 0,
                            "outs": 0,
                            "offense": {},
                        },
                    }
                ]
            }
        ]
    }

    async def _fake_get(*args, **kwargs):
        resp = mock.AsyncMock()
        resp.json.return_value = schedule
        return resp

    session.get.return_value.__aenter__ = _fake_get
    session.get.return_value.__aexit__ = mock.AsyncMock(return_value=False)

    await monitor.update()

    scoreboard_stories = [
        s for s in monitor.feed_stories if isinstance(s, MLBScoreboardMessage)
    ]
    assert scoreboard_stories, "no MLBScoreboardMessage in feed_stories"
    for story in scoreboard_stories:
        assert (
            story.small_font is FONT_DEFAULT
        ), f"story.small_font is {story.small_font!r}, expected FONT_DEFAULT"


# ---------------------------------------------------------------------------
# Stale-game-state / parse robustness tests
# ---------------------------------------------------------------------------


def _challenges_game_fixture(challenges) -> dict:
    """Schedule fixture with a configurable challenges value for fault-injection."""
    return {
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
                        "challenges": challenges,
                    }
                ]
            }
        ]
    }


def test_parse_games_challenges_as_list_does_not_raise():
    """challenges field that is a list (unexpected API shape) must not raise."""
    from zoneinfo import ZoneInfo

    monitor = _make_monitor_for_parse()
    schedule = _challenges_game_fixture([{"home": 2}, {"away": 1}])
    games = monitor._parse_games(schedule, ZoneInfo("America/New_York"))
    assert len(games) == 1
    assert games[0].home_challenges is None
    assert games[0].away_challenges is None


def test_parse_games_challenges_remaining_non_int_does_not_raise():
    """Non-numeric remaining value must be silently ignored."""
    from zoneinfo import ZoneInfo

    monitor = _make_monitor_for_parse()
    schedule = _challenges_game_fixture(
        {
            "home": {"remaining": "two"},
            "away": {"remaining": None},
        }
    )
    games = monitor._parse_games(schedule, ZoneInfo("America/New_York"))
    assert len(games) == 1
    assert games[0].home_challenges is None
    assert games[0].away_challenges is None


@pytest.mark.asyncio
async def test_update_parse_error_shows_no_data_not_stale():
    """A _parse_games exception must clear stale data and show 'No Data'."""
    import unittest.mock as mock
    from zoneinfo import ZoneInfo

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="PHI")
    monitor._team_id = 143
    monitor._tz = ZoneInfo("America/New_York")

    from rgbmatrix.graphics import Color

    from led_ticker.widgets.mlb import MLBGameMessage

    stale = MLBGameMessage([("PHI 5 NYM 3 (Final)", Color(255, 255, 255))])
    monitor.feed_stories = [stale]

    resp = mock.AsyncMock()
    resp.json = mock.AsyncMock(return_value="not a dict")  # str has no .get()
    resp.__aenter__ = mock.AsyncMock(return_value=resp)
    resp.__aexit__ = mock.AsyncMock(return_value=False)
    session.get.return_value = resp

    await monitor.update()

    from led_ticker.widgets.message import TickerMessage

    assert not any(isinstance(s, MLBGameMessage) for s in monitor.feed_stories)
    assert any(
        isinstance(s, TickerMessage) and "No Data" in s.text
        for s in monitor.feed_stories
    )


# ---------------------------------------------------------------------------
# _find_current_series hold-window boundary tests
# ---------------------------------------------------------------------------


def _make_monitor_for_series() -> MLBScoreMonitor:
    import unittest.mock as mock
    from zoneinfo import ZoneInfo

    monitor = MLBScoreMonitor(session=mock.MagicMock(), team="PHI")
    monitor._tz = ZoneInfo("America/New_York")
    return monitor


def test_find_current_series_past_hold_window_returns_none():
    """All-final series whose last game ended beyond final_hold_hours returns None."""
    from zoneinfo import ZoneInfo

    monitor = _make_monitor_for_series()
    tz = ZoneInfo("America/New_York")
    now = datetime(2026, 5, 27, 18, 0, tzinfo=tz)
    game_time = now - timedelta(hours=8)
    series = [
        SeriesInfo(
            opponent_abbr="NYM",
            games=[
                GameInfo(
                    home_abbr="PHI",
                    away_abbr="NYM",
                    state="final",
                    home_score=5,
                    away_score=3,
                    start_time=game_time,
                )
            ],
        )
    ]
    result = monitor._find_current_series(series, now)
    assert result is None


def test_find_current_series_within_hold_window_returns_series():
    """All-final series whose last game ended within final_hold_hours is returned."""
    from zoneinfo import ZoneInfo

    monitor = _make_monitor_for_series()
    tz = ZoneInfo("America/New_York")
    now = datetime(2026, 5, 27, 18, 0, tzinfo=tz)
    game_time = now - timedelta(hours=4)
    series = [
        SeriesInfo(
            opponent_abbr="NYM",
            games=[
                GameInfo(
                    home_abbr="PHI",
                    away_abbr="NYM",
                    state="final",
                    home_score=5,
                    away_score=3,
                    start_time=game_time,
                )
            ],
        )
    ]
    result = monitor._find_current_series(series, now)
    assert result is not None
    assert result.opponent_abbr == "NYM"


# ---------------------------------------------------------------------------
# _fetch_abs_challenges
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_abs_challenges_active_game():
    """Returns (home, away) remaining counts when ABS is active."""
    import unittest.mock as mock

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="PHI")

    resp = mock.AsyncMock()
    resp.json = mock.AsyncMock(
        return_value={
            "gameData": {
                "absChallenges": {
                    "hasChallenges": True,
                    "home": {"remaining": 2, "usedSuccessful": 0, "usedFailed": 0},
                    "away": {"remaining": 0, "usedSuccessful": 2, "usedFailed": 2},
                }
            }
        }
    )
    resp.__aenter__ = mock.AsyncMock(return_value=resp)
    resp.__aexit__ = mock.AsyncMock(return_value=False)
    session.get.return_value = resp

    home, away = await monitor._fetch_abs_challenges(823294)
    assert home == 2
    assert away == 0


@pytest.mark.asyncio
async def test_fetch_abs_challenges_no_challenge_made_yet():
    """Returns remaining counts when ABS is equipped but no challenge made yet.

    hasChallenges=false is the initial state before any challenge is thrown —
    the field flips to true only after the first challenge. The non-empty dict
    is the reliable indicator that ABS is active; hasChallenges alone is not.
    Confirmed 2026-05-27 against CIN@NYM (gamePk=823626) at Citi Field.
    """
    import unittest.mock as mock

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="NYM")

    resp = mock.AsyncMock()
    resp.json = mock.AsyncMock(
        return_value={
            "gameData": {
                "absChallenges": {
                    "hasChallenges": False,
                    "home": {"remaining": 2, "usedSuccessful": 0, "usedFailed": 0},
                    "away": {"remaining": 2, "usedSuccessful": 0, "usedFailed": 0},
                }
            }
        }
    )
    resp.__aenter__ = mock.AsyncMock(return_value=resp)
    resp.__aexit__ = mock.AsyncMock(return_value=False)
    session.get.return_value = resp

    home, away = await monitor._fetch_abs_challenges(823626)
    assert home == 2
    assert away == 2


@pytest.mark.asyncio
async def test_fetch_abs_challenges_inactive_returns_none():
    """Returns (None, None) when absChallenges is empty (ABS not active)."""
    import unittest.mock as mock

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="PHI")

    resp = mock.AsyncMock()
    resp.json = mock.AsyncMock(return_value={"gameData": {"absChallenges": {}}})
    resp.__aenter__ = mock.AsyncMock(return_value=resp)
    resp.__aexit__ = mock.AsyncMock(return_value=False)
    session.get.return_value = resp

    home, away = await monitor._fetch_abs_challenges(823294)
    assert home is None
    assert away is None


@pytest.mark.asyncio
async def test_fetch_abs_challenges_error_returns_none():
    """Network errors return (None, None) without raising."""
    import unittest.mock as mock

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="PHI")
    session.get.side_effect = Exception("network error")

    home, away = await monitor._fetch_abs_challenges(823294)
    assert home is None
    assert away is None


# ---------------------------------------------------------------------------
# update() ABS challenge hydration integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_hydrates_abs_challenges_for_live_game():
    """Live games get ABS challenge counts fetched from the live feed during update()."""  # noqa: E501
    import unittest.mock as mock
    from zoneinfo import ZoneInfo

    session = mock.MagicMock()
    monitor = MLBScoreMonitor(session=session, team="PHI", layout="scoreboard")
    monitor._team_id = 143
    monitor._tz = ZoneInfo("America/New_York")

    schedule_resp = mock.AsyncMock()
    schedule_resp.json = mock.AsyncMock(return_value=_phi_nym_schedule("live"))
    schedule_resp.__aenter__ = mock.AsyncMock(return_value=schedule_resp)
    schedule_resp.__aexit__ = mock.AsyncMock(return_value=False)

    live_resp = mock.AsyncMock()
    live_resp.json = mock.AsyncMock(
        return_value={
            "gameData": {
                "absChallenges": {
                    "hasChallenges": True,
                    "home": {"remaining": 2, "usedSuccessful": 0, "usedFailed": 0},
                    "away": {"remaining": 1, "usedSuccessful": 1, "usedFailed": 0},
                }
            }
        }
    )
    live_resp.__aenter__ = mock.AsyncMock(return_value=live_resp)
    live_resp.__aexit__ = mock.AsyncMock(return_value=False)

    def get_side_effect(url):
        if "v1.1" in url:
            return live_resp
        return schedule_resp

    session.get = mock.MagicMock(side_effect=get_side_effect)

    await monitor.update()

    scoreboard_msgs = [
        s for s in monitor.feed_stories if isinstance(s, MLBScoreboardMessage)
    ]
    assert len(scoreboard_msgs) >= 1
    assert scoreboard_msgs[0].game.home_challenges == 2
    assert scoreboard_msgs[0].game.away_challenges == 1
