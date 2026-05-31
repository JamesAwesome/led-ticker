"""MLB standings widget using the free MLB Stats API."""

import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Self
from zoneinfo import ZoneInfo

import aiohttp
import attrs

from led_ticker._types import Color, Font
from led_ticker.color_providers import ColorProvider
from led_ticker.colors import RGB_WHITE
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widget import run_monitor_loop, spawn_tracked
from led_ticker.widgets import register
from led_ticker.widgets.message import SegmentMessage, TickerMessage
from led_ticker.widgets.mlb import (
    MLB_API,
    MLB_NAME_TO_ABBR,
    _team_color_by_name,
)

logger: logging.Logger = logging.getLogger(__name__)

_INTERVAL_DAILY: int = 86400


@dataclass
class TeamStanding:
    name: str  # API team name, e.g. "Mets", "Yankees"
    wins: int
    losses: int
    rank: int
    games_back: str  # "-" for leader, "3.0", "10.5", etc.


def _build_standing_message(
    standing: TeamStanding,
    bg_color: Color | None = None,
    font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
) -> SegmentMessage:
    """Build a display message for a single team's standing."""
    team_c = _team_color_by_name(standing.name)

    gb_str = standing.games_back if standing.games_back != "-" else "-"

    segments: list[tuple[str, Any]] = [
        (f"{standing.rank}. ", RGB_WHITE),
        (standing.name, team_c),
        (f" {standing.wins}-{standing.losses}", RGB_WHITE),
        (f" {gb_str}", RGB_WHITE),
    ]
    return SegmentMessage(
        segments, center=True, bg_color=bg_color, font=font, font_color=font_color
    )


@register("mlb_standings")
@attrs.define
class MLBStandingsMonitor:
    """MLB overall standings showing top N teams and tracked teams."""

    session: aiohttp.ClientSession
    teams: list[str]
    title: str = "MLB Standings"
    top_n: int = 3
    timezone: str = "America/New_York"
    padding: int = 6
    hold_time: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    feed_title: TickerMessage | None = attrs.field(init=False, default=None)
    feed_stories: list[TickerMessage | SegmentMessage] = attrs.field(
        init=False, factory=list
    )

    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession,
        teams: list[str],
        update_interval: int = _INTERVAL_DAILY,
        **kwargs: Any,
    ) -> Self:
        logger.debug("MLBStandingsMonitor.start: teams=%s", teams)
        widget = cls(
            session=session,
            teams=[t.upper() for t in teams],
            **kwargs,
        )
        widget._tz = ZoneInfo(widget.timezone)
        await widget.update()
        logger.info(
            "MLB Standings: %d stories",
            len(widget.feed_stories),
        )
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self) -> None:
        """Fetch standings and build display messages."""
        tz = self._tz or ZoneInfo(self.timezone)
        now = datetime.now(tz)
        season = now.year

        url = (
            f"{MLB_API}/standings"
            f"?leagueId=103,104&season={season}"
            f"&standingsType=regularSeason"
        )

        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.exception("MLB Standings API error")
            self._set_error_state()
            return

        standings = self._parse_standings(data)
        if not standings:
            self._set_error_state()
            return

        # Season hasn't started yet — show opening day message
        if all(s.wins == 0 and s.losses == 0 for s in standings):
            await self._set_offseason_state()
            return

        title_color = self.font_color if self.font_color is not None else RGB_WHITE
        self.feed_title = TickerMessage(
            self.title,
            font_color=title_color,
            center=True,
            bg_color=self.bg_color,
        )
        stories: list[TickerMessage | SegmentMessage] = []

        # Top N teams
        top_names: set[str] = set()
        for standing in standings[: self.top_n]:
            top_names.add(standing.name)
            stories.append(
                _build_standing_message(
                    standing,
                    bg_color=self.bg_color,
                    font=self.font,
                    font_color=self.font_color,
                )
            )

        # Tracked teams not already in top N
        # Config uses abbreviations, so map API names back to abbrs for lookup
        standings_by_abbr: dict[str, TeamStanding] = {}
        for s in standings:
            abbr = MLB_NAME_TO_ABBR.get(s.name, "")
            if abbr:
                standings_by_abbr[abbr] = s
        for team in self.teams:
            standing = standings_by_abbr.get(team)
            if standing and standing.name not in top_names:
                stories.append(
                    _build_standing_message(
                        standing,
                        bg_color=self.bg_color,
                        font=self.font,
                        font_color=self.font_color,
                    )
                )

        self.feed_stories = stories
        logger.info(
            "MLB standings updated: %d stories",
            len(self.feed_stories),
        )

    def _parse_standings(
        self,
        data: dict[str, Any],
    ) -> list[TeamStanding]:
        """Parse MLB API standings response into sorted TeamStanding list."""
        all_teams: list[TeamStanding] = []
        for record in data.get("records", []):
            for tr in record.get("teamRecords", []):
                team = tr.get("team", {})
                name = team.get("name", "Unknown")
                wins = tr.get("wins", 0)
                losses = tr.get("losses", 0)
                rank = int(tr.get("sportRank", 99))
                gb = tr.get("sportGamesBack", "-")
                all_teams.append(
                    TeamStanding(
                        name=name,
                        wins=wins,
                        losses=losses,
                        rank=rank,
                        games_back=str(gb),
                    )
                )
        all_teams.sort(key=lambda t: t.rank)
        return all_teams

    async def _fetch_opening_day(self) -> str | None:
        """Fetch the earliest regular season game date for tracked teams."""
        tz = self._tz or ZoneInfo(self.timezone)
        now = datetime.now(tz)
        start = now.strftime("%Y-%m-%d")
        end = (now + timedelta(days=30)).strftime("%Y-%m-%d")

        # Resolve abbreviation -> ID once instead of refetching the whole
        # /teams endpoint for every tracked team.
        try:
            async with self.session.get(f"{MLB_API}/teams?sportId=1") as resp:
                teams_data = await resp.json()
        except Exception:
            logger.debug("Failed to fetch MLB teams roster")
            return None

        abbr_to_id: dict[str, int] = {
            t["abbreviation"]: t["id"]
            for t in teams_data.get("teams", [])
            if t.get("abbreviation") and t.get("id") is not None
        }

        for team_abbr in self.teams:
            team_id = abbr_to_id.get(team_abbr)
            if not team_id:
                continue
            url = (
                f"{MLB_API}/schedule?teamId={team_id}"
                f"&startDate={start}&endDate={end}"
                f"&sportId=1&gameType=R"
            )
            try:
                async with self.session.get(url) as resp:
                    data = await resp.json()
            except Exception:
                logger.debug("Failed to fetch schedule for %s", team_abbr)
                continue

            for date_entry in data.get("dates", []):
                for g in date_entry.get("games", []):
                    game_date = g.get("gameDate")
                    if not game_date:
                        continue
                    with contextlib.suppress(ValueError, TypeError):
                        dt = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
                        local = dt.astimezone(tz)
                        return local.strftime("%b %-d")
        return None

    async def _set_offseason_state(self) -> None:
        """Set display to offseason/pre-season message."""
        opening_day = await self._fetch_opening_day()
        msg = f"Opens {opening_day}" if opening_day else "Opens soon"

        body_color = self.font_color if self.font_color is not None else RGB_WHITE
        self.feed_title = TickerMessage(
            self.title,
            font_color=body_color,
            center=True,
            bg_color=self.bg_color,
        )
        self.feed_stories = [
            TickerMessage(
                msg, font_color=body_color, center=True, bg_color=self.bg_color
            ),
        ]
        logger.info(
            "MLB standings updated: %d stories (offseason)",
            len(self.feed_stories),
        )

    def _set_error_state(self) -> None:
        """Set display to error state."""
        body_color = self.font_color if self.font_color is not None else RGB_WHITE
        self.feed_title = TickerMessage(
            self.title,
            font_color=body_color,
            center=True,
            bg_color=self.bg_color,
        )
        self.feed_stories = [
            TickerMessage("No Data", font_color=body_color, bg_color=self.bg_color),
        ]
        logger.info(
            "MLB standings updated: %d stories (no data)",
            len(self.feed_stories),
        )
