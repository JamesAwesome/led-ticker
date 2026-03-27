"""MLB score monitor widget using the free MLB Stats API."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Self
from zoneinfo import ZoneInfo

import aiohttp
import attrs

from led_ticker._compat import require_graphics
from led_ticker._types import Canvas, Color, ColorTuple, DrawResult, Font, PixelData
from led_ticker.colors import RGB_WHITE, _color
from led_ticker.drawing import compute_cursor, get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register
from led_ticker.widgets.message import TickerMessage

logger: logging.Logger = logging.getLogger(__name__)

MLB_API: str = "https://statsapi.mlb.com/api/v1"

# Update intervals (seconds)
_INTERVAL_LIVE: int = 45  # ~half-inning cadence
_INTERVAL_IDLE: int = 300  # 5 minutes
_INTERVAL_OFFSEASON: int = 86400  # daily

WIN_COLOR: Color = _color(46, 200, 46)
LOSS_COLOR: Color = _color(220, 30, 30)
LIVE_COLOR: Color = _color(255, 40, 40)

# All 30 MLB team primary colors
MLB_TEAM_COLORS: dict[str, ColorTuple] = {
    "ARI": (167, 25, 48),
    "ATL": (206, 17, 65),
    "BAL": (223, 70, 1),
    "BOS": (189, 48, 57),
    "CHC": (14, 51, 134),
    "CIN": (198, 1, 31),
    "CLE": (0, 56, 93),
    "COL": (51, 0, 111),
    "CWS": (39, 37, 31),
    "DET": (12, 35, 64),
    "HOU": (235, 110, 31),
    "KC": (0, 70, 135),
    "LAA": (186, 0, 33),
    "LAD": (0, 90, 156),
    "MIA": (0, 163, 224),
    "MIL": (18, 40, 75),
    "MIN": (0, 43, 92),
    "NYM": (0, 45, 114),
    "NYY": (0, 48, 135),
    "OAK": (0, 56, 49),
    "PHI": (228, 24, 40),
    "PIT": (253, 184, 39),
    "SD": (47, 36, 28),
    "SEA": (0, 92, 92),
    "SF": (253, 90, 30),
    "STL": (196, 30, 58),
    "TB": (9, 44, 92),
    "TEX": (0, 50, 120),
    "TOR": (19, 74, 142),
    "WSH": (171, 0, 3),
}

# Full team names for display
MLB_TEAM_NAMES: dict[str, str] = {
    "ARI": "D-backs",
    "ATL": "Braves",
    "BAL": "Orioles",
    "BOS": "Red Sox",
    "CHC": "Cubs",
    "CIN": "Reds",
    "CLE": "Guardians",
    "COL": "Rockies",
    "CWS": "White Sox",
    "DET": "Tigers",
    "HOU": "Astros",
    "KC": "Royals",
    "LAA": "Angels",
    "LAD": "Dodgers",
    "MIA": "Marlins",
    "MIL": "Brewers",
    "MIN": "Twins",
    "NYM": "Mets",
    "NYY": "Yankees",
    "OAK": "Athletics",
    "PHI": "Phillies",
    "PIT": "Pirates",
    "SD": "Padres",
    "SEA": "Mariners",
    "SF": "Giants",
    "STL": "Cardinals",
    "TB": "Rays",
    "TEX": "Rangers",
    "TOR": "Blue Jays",
    "WSH": "Nationals",
}


# API team name -> abbreviation (standings API returns short names)
MLB_NAME_TO_ABBR: dict[str, str] = {v: k for k, v in MLB_TEAM_NAMES.items()}


def _team_color(abbr: str) -> Color:
    """Get graphics.Color for a team abbreviation."""
    r, g, b = MLB_TEAM_COLORS.get(abbr, (255, 255, 255))
    return _color(r, g, b)


def _team_color_by_name(name: str) -> Color:
    """Get graphics.Color for an API team name (e.g. 'Mets')."""
    abbr = MLB_NAME_TO_ABBR.get(name, "")
    r, g, b = MLB_TEAM_COLORS.get(abbr, (255, 255, 255))
    return _color(r, g, b)


@dataclass
class GameInfo:
    home_abbr: str
    away_abbr: str
    home_score: int | None = None
    away_score: int | None = None
    state: str = "preview"  # "final", "live", "preview"
    game_type: str = "R"  # R=regular, S=spring, A=all-star, P+=postseason
    inning: str | None = None
    balls: int = 0
    strikes: int = 0
    outs: int = 0
    on_first: bool = False
    on_second: bool = False
    on_third: bool = False
    start_time: datetime | None = None
    game_pk: int = 0


@dataclass
class SeriesInfo:
    opponent_abbr: str
    games: list[GameInfo] = field(default_factory=list)
    team_wins: int = 0
    team_losses: int = 0


def _ordinal(n: int) -> str:
    """Convert integer to ordinal string: 1st, 2nd, 3rd, etc."""
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{['th', 'st', 'nd', 'rd'][min(n % 10, 4)] if n % 10 < 4 else 'th'}"


def _format_inning(inning_num: int, half: str) -> str:
    """Format inning display: '▲5', '▼7'."""
    arrow = "\u25b2" if half == "top" else "\u25bc"
    return f"{arrow}{inning_num}"


def _format_game_time(dt: datetime, tz: ZoneInfo) -> str:
    """Format game time relative to now."""
    now = datetime.now(tz)
    local = dt.astimezone(tz)

    if local.date() == now.date():
        return f"Today {local.strftime('%-I:%M %p')}"
    if local.date() == (now + timedelta(days=1)).date():
        return f"Tmrw {local.strftime('%-I:%M %p')}"
    days_out = (local.date() - now.date()).days
    if days_out <= 6:
        return local.strftime("%a %-I:%M %p")
    return local.strftime("%b %-d %-I:%M %p")


def _parse_team_abbr(team_data: dict[str, Any]) -> str:
    """Extract team abbreviation from MLB API team data."""
    return team_data.get("abbreviation", "???")


class MLBGameMessage:
    """A single game rendered with team colors and score colors."""

    def __init__(
        self,
        segments: list[tuple[str, Color]],
        padding: int = 6,
        icon: PixelData | None = None,
        center: bool = False,
    ) -> None:
        self.segments: list[tuple[str, Color]] = segments
        self.padding: int = padding
        self.icon: PixelData | None = icon
        self.center: bool = center
        self._content_width: int = -1

    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        graphics = require_graphics()
        y_offset: int = kwargs.get("y_offset", 0)

        if self._content_width < 0:
            font: Font = FONT_DEFAULT
            self._content_width = sum(
                get_text_width(font, text, padding=0) for text, _ in self.segments
            )
            if self.icon is not None:
                from led_ticker.widgets.mlb_icons import (
                    ICON_PADDING,
                    ICON_WIDTH,
                )

                self._content_width += ICON_WIDTH + ICON_PADDING

        content_width = self._content_width
        cursor_pos, end_padding = compute_cursor(
            canvas.width,
            content_width,
            cursor_pos,
            self.padding,
            self.center,
        )

        font = FONT_DEFAULT
        for text, color in self.segments:
            cursor_pos += graphics.DrawText(
                canvas,
                font,
                cursor_pos,
                12 + y_offset,
                color,
                text,
            )

        if self.icon is not None:
            from led_ticker.widgets.mlb_icons import draw_mlb_icon

            cursor_pos = draw_mlb_icon(
                canvas,
                self.icon,
                int(cursor_pos),
                y_offset=5 + y_offset,
            )

        cursor_pos += end_padding
        return canvas, cursor_pos


def _build_series_title(
    team_abbr: str, series: SeriesInfo, tz: ZoneInfo
) -> MLBGameMessage:
    """Build the title message for a series.

    Uses AWAY @ HOME when all games share the same home team,
    otherwise falls back to neutral 'vs' separator.
    """
    team_c = _team_color(team_abbr)
    opp_c = _team_color(series.opponent_abbr)

    # Determine if all games share the same home team
    home_teams = {g.home_abbr for g in series.games}
    all_same_home = len(home_teams) == 1

    if all_same_home:
        home = next(iter(home_teams))
        away = team_abbr if home != team_abbr else series.opponent_abbr
        away_c = _team_color(away)
        home_c = _team_color(home)
        segments: list[tuple[str, Color]] = [
            (away, away_c),
            (" @ ", RGB_WHITE),
            (home, home_c),
        ]
        # First listed team is away, second is home
        first_is_team = away == team_abbr
    else:
        segments = [
            (team_abbr, team_c),
            (" vs ", RGB_WHITE),
            (series.opponent_abbr, opp_c),
        ]
        # First listed team is always team_abbr
        first_is_team = True

    # Show (ST) / (ASG) with icon for special game types
    icon: PixelData | None = None
    is_spring = any(g.game_type == "S" for g in series.games)
    is_allstar = any(g.game_type == "A" for g in series.games)
    if is_spring:
        from led_ticker.widgets.mlb_icons import FLOWER

        segments.append((" (ST)", RGB_WHITE))
        icon = FLOWER
    elif is_allstar:
        from led_ticker.widgets.mlb_icons import STAR

        segments.append((" (ASG)", RGB_WHITE))
        icon = STAR

    # Show series record ordered to match team name positions
    total_games = len(series.games)
    total_decided = series.team_wins + series.team_losses
    if total_games > 1 and total_decided > 0:
        if first_is_team:
            record = f" {series.team_wins}-{series.team_losses}"
        else:
            record = f" {series.team_losses}-{series.team_wins}"
        segments.append((record, RGB_WHITE))

    # Center the title if it fits on screen
    return MLBGameMessage(segments, center=True, icon=icon)


def _build_game_message(game: GameInfo, team_abbr: str, tz: ZoneInfo) -> MLBGameMessage:
    """Build a message for a single game.

    Uses standard baseball convention: away team listed first.
    """
    away_c = _team_color(game.away_abbr)
    home_c = _team_color(game.home_abbr)

    if game.state == "final":
        away_won = (game.away_score or 0) > (game.home_score or 0)
        away_score_color = WIN_COLOR if away_won else LOSS_COLOR
        home_score_color = LOSS_COLOR if away_won else WIN_COLOR

        segments: list[tuple[str, Color]] = [
            (game.away_abbr, away_c),
            (f" {game.away_score}", away_score_color),
            (" ", RGB_WHITE),
            (game.home_abbr, home_c),
            (f" {game.home_score}", home_score_color),
            (" (Final)", RGB_WHITE),
        ]

    elif game.state == "live":
        inning_str = f" {game.inning}" if game.inning else ""

        # Base diamonds: ◇ = empty, ◆ = occupied (3rd-2nd-1st)
        b3 = "\u25c6" if game.on_third else "\u25c7"
        b2 = "\u25c6" if game.on_second else "\u25c7"
        b1 = "\u25c6" if game.on_first else "\u25c7"

        # BSO in color: B|S|O
        ball_c = _color(80, 255, 80)  # green
        strike_c = _color(255, 255, 80)  # yellow
        out_c = _color(255, 80, 80)  # red

        segments = [
            (game.away_abbr, away_c),
            (f" {game.away_score}", RGB_WHITE),
            (" ", RGB_WHITE),
            (game.home_abbr, home_c),
            (f" {game.home_score}", RGB_WHITE),
            (inning_str, RGB_WHITE),
            (f" {b3}{b2}{b1}", RGB_WHITE),
            (f" {game.balls}", ball_c),
            ("\u00b7", RGB_WHITE),
            (f"{game.strikes}", strike_c),
            ("\u00b7", RGB_WHITE),
            (f"{game.outs}", out_c),
        ]

    else:  # preview
        time_str = _format_game_time(game.start_time, tz) if game.start_time else "TBD"
        segments = [
            (game.away_abbr, away_c),
            (" @ ", RGB_WHITE),
            (game.home_abbr, home_c),
            (f" {time_str}", RGB_WHITE),
        ]

    return MLBGameMessage(segments, center=True)


@register("mlb")
@attrs.define
class MLBScoreMonitor:
    """MLB scores for a single team's current series."""

    session: aiohttp.ClientSession
    team: str
    timezone: str = "America/New_York"
    padding: int = 6
    final_hold_hours: int = 6
    _team_id: int = attrs.field(init=False, default=0)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    _has_live_game: bool = attrs.field(init=False, default=False)
    feed_title: TickerMessage | MLBGameMessage | None = attrs.field(
        init=False, default=None
    )
    feed_stories: list[TickerMessage | MLBGameMessage] = attrs.field(
        init=False, factory=list
    )

    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession,
        team: str,
        update_interval: int = 300,
        **kwargs: Any,
    ) -> Self:
        logger.debug("MLBScoreMonitor.start: team=%s", team)
        widget = cls(session=session, team=team.upper(), **kwargs)
        widget._tz = ZoneInfo(widget.timezone)
        await widget._resolve_team_id()
        await widget.update()
        logger.info(
            "MLB %s: %d stories",
            team,
            len(widget.feed_stories),
        )
        asyncio.create_task(run_monitor_loop(widget, update_interval))
        return widget

    async def _resolve_team_id(self) -> None:
        """Fetch team ID from MLB API."""
        url = f"{MLB_API}/teams?sportId=1"
        logger.debug("MLB: resolving team ID for %s", self.team)
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
                for t in data.get("teams", []):
                    if t.get("abbreviation") == self.team:
                        self._team_id = t["id"]
                        logger.debug("MLB: %s → id %d", self.team, self._team_id)
                        return
            logger.warning("Team %s not found in MLB API", self.team)
        except Exception:
            logger.exception("Failed to resolve team ID for %s", self.team)

    async def update(self) -> None:
        """Fetch schedule and build display messages."""
        team_name = MLB_TEAM_NAMES.get(self.team, self.team)
        tz = self._tz or ZoneInfo(self.timezone)

        if not self._team_id:
            title = TickerMessage(
                f"{team_name}",
                font_color=_team_color(self.team),
            )
            self.feed_title = title
            self.feed_stories = [
                title,
                TickerMessage("No Data", font_color=RGB_WHITE),
            ]
            return

        now = datetime.now(tz)
        start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        end = (now + timedelta(days=7)).strftime("%Y-%m-%d")

        url = (
            f"{MLB_API}/schedule?teamId={self._team_id}"
            f"&startDate={start}&endDate={end}&sportId=1"
            f"&hydrate=team,linescore"
        )

        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.exception("MLB API error for %s", self.team)
            title = TickerMessage(
                f"{team_name}",
                font_color=_team_color(self.team),
            )
            self.feed_title = title
            self.feed_stories = [
                title,
                TickerMessage("No Data", font_color=RGB_WHITE),
            ]
            return

        games = self._parse_games(data, tz)

        if not games:
            title = TickerMessage(
                f"{team_name}",
                font_color=_team_color(self.team),
            )
            self.feed_title = title
            self.feed_stories = [
                title,
                TickerMessage("Season Over", font_color=RGB_WHITE),
            ]
            self._has_live_game = False
            return

        series = self._group_into_series(games)
        current = self._find_current_series(series, now)

        if current is None:
            # No current series — find next
            next_game = self._find_next_game(games, now)
            title = TickerMessage(
                f"{team_name}",
                font_color=_team_color(self.team),
            )
            self.feed_title = title
            if next_game:
                opp = (
                    next_game.away_abbr
                    if next_game.home_abbr == self.team
                    else next_game.home_abbr
                )
                opp_name = MLB_TEAM_NAMES.get(opp, opp)
                if next_game.start_time:
                    time_str = _format_game_time(next_game.start_time, tz)
                else:
                    time_str = "TBD"
                self.feed_stories = [
                    title,
                    TickerMessage(
                        f"Next: vs {opp_name}, {time_str}",
                        font_color=RGB_WHITE,
                    ),
                ]
            else:
                self.feed_stories = [
                    title,
                    TickerMessage("Season Over", font_color=RGB_WHITE),
                ]
            self._has_live_game = False
            return

        # Build display from current series
        series_title = _build_series_title(self.team, current, tz)
        self.feed_title = series_title
        stories: list[TickerMessage | MLBGameMessage] = [series_title]
        stories.extend(_build_game_message(g, self.team, tz) for g in current.games)
        self.feed_stories = stories
        self._has_live_game = any(g.state == "live" for g in current.games)

    def _parse_games(
        self, schedule_data: dict[str, Any], tz: ZoneInfo
    ) -> list[GameInfo]:
        """Parse MLB API schedule response into GameInfo list."""
        games: list[GameInfo] = []
        for date_entry in schedule_data.get("dates", []):
            for g in date_entry.get("games", []):
                status = g.get("status", {})
                abstract = status.get("abstractGameState", "Preview")

                home_team = g.get("teams", {}).get("home", {})
                away_team = g.get("teams", {}).get("away", {})
                home_abbr = _parse_team_abbr(home_team.get("team", {}))
                away_abbr = _parse_team_abbr(away_team.get("team", {}))

                home_score = home_team.get("score")
                away_score = away_team.get("score")

                inning: str | None = None
                balls = strikes = outs = 0
                on_first = on_second = on_third = False
                if abstract == "Live":
                    linescore = g.get("linescore", {})
                    inning_num = linescore.get("currentInning", 0)
                    half = linescore.get("inningHalf", "top").lower()
                    if inning_num:
                        inning = _format_inning(inning_num, half)

                    # At-bat data
                    offense = linescore.get("offense", {})
                    balls = linescore.get("balls", 0) or 0
                    strikes = linescore.get("strikes", 0) or 0
                    outs = linescore.get("outs", 0) or 0
                    on_first = "first" in offense
                    on_second = "second" in offense
                    on_third = "third" in offense

                start_time: datetime | None = None
                game_date = g.get("gameDate")
                if game_date:
                    import contextlib

                    with contextlib.suppress(ValueError, TypeError):
                        start_time = datetime.fromisoformat(
                            game_date.replace("Z", "+00:00")
                        )

                state_map: dict[str, str] = {
                    "Final": "final",
                    "Live": "live",
                    "Preview": "preview",
                }

                games.append(
                    GameInfo(
                        home_abbr=home_abbr,
                        away_abbr=away_abbr,
                        home_score=home_score,
                        away_score=away_score,
                        state=state_map.get(abstract, "preview"),
                        inning=inning,
                        start_time=start_time,
                        game_type=g.get("gameType", "R"),
                        game_pk=g.get("gamePk", 0),
                        balls=balls,
                        strikes=strikes,
                        outs=outs,
                        on_first=on_first,
                        on_second=on_second,
                        on_third=on_third,
                    )
                )

        games.sort(
            key=lambda g: (
                g.start_time
                or datetime.min.replace(
                    tzinfo=tz,
                )
            )
        )
        return games

    def _group_into_series(self, games: list[GameInfo]) -> list[SeriesInfo]:
        """Group games into series by consecutive opponent."""
        if not games:
            return []

        series_list: list[SeriesInfo] = []
        current_opp: str | None = None
        current_games: list[GameInfo] = []

        for g in games:
            opp = g.away_abbr if g.home_abbr == self.team else g.home_abbr
            if opp != current_opp:
                if current_games:
                    assert current_opp is not None
                    series_list.append(self._make_series(current_opp, current_games))
                current_opp = opp
                current_games = [g]
            else:
                current_games.append(g)

        if current_games:
            assert current_opp is not None
            series_list.append(self._make_series(current_opp, current_games))

        return series_list

    def _make_series(self, opponent_abbr: str, games: list[GameInfo]) -> SeriesInfo:
        """Create a SeriesInfo with win/loss record."""
        wins = 0
        losses = 0
        for g in games:
            if g.state != "final":
                continue
            is_home = g.home_abbr == self.team
            team_score = g.home_score if is_home else g.away_score
            opp_score = g.away_score if is_home else g.home_score
            if team_score is not None and opp_score is not None:
                if team_score > opp_score:
                    wins += 1
                else:
                    losses += 1
        return SeriesInfo(
            opponent_abbr=opponent_abbr,
            games=games,
            team_wins=wins,
            team_losses=losses,
        )

    def _find_current_series(
        self, series_list: list[SeriesInfo], now: datetime
    ) -> SeriesInfo | None:
        """Find series that is live or most recently played."""
        for s in reversed(series_list):
            has_final = any(g.state == "final" for g in s.games)
            has_live = any(g.state == "live" for g in s.games)
            has_upcoming = any(g.state == "preview" for g in s.games)
            if has_live:
                return s
            if has_final and has_upcoming:
                return s  # series in progress
            if has_final:
                # Check if this series ended recently (within 24h)
                last_game_time = max(
                    (g.start_time for g in s.games if g.start_time),
                    default=None,
                )
                if last_game_time:
                    hours_ago = (
                        now - last_game_time.astimezone(self._tz)
                    ).total_seconds() / 3600
                    if hours_ago < self.final_hold_hours:
                        return s
        # No current series — check for upcoming
        for s in series_list:
            if any(g.state == "preview" for g in s.games):
                return s
        return None

    def _find_next_game(self, games: list[GameInfo], now: datetime) -> GameInfo | None:
        """Find the next upcoming game."""
        for g in games:
            if (
                g.state == "preview"
                and g.start_time
                and g.start_time.astimezone(self._tz) > now
            ):
                return g
        return None
