"""MLB score monitor widget using the free MLB Stats API."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Self
from zoneinfo import ZoneInfo

import aiohttp
import attrs

from led_ticker._types import Canvas, Color, ColorTuple, DrawResult, Font
from led_ticker.color_providers import ColorProvider
from led_ticker.colors import RGB_WHITE, lazy_palette, make_color
from led_ticker.drawing import compute_baseline, compute_cursor
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import _FrameAware
from led_ticker.widgets.message import TickerMessage

logger: logging.Logger = logging.getLogger(__name__)

MLB_API: str = "https://statsapi.mlb.com/api/v1"

# Update intervals (seconds)
_INTERVAL_LIVE: int = 45  # ~half-inning cadence
_INTERVAL_IDLE: int = 300  # 5 minutes
_INTERVAL_OFFSEASON: int = 86400  # daily

_team_palette = lazy_palette(
    {
        "WIN_COLOR": (46, 200, 46),
        "LOSS_COLOR": (220, 30, 30),
        "LIVE_COLOR": (255, 40, 40),
        "CHALLENGE_COLOR": (255, 180, 0),  # amber — remaining ABS challenge pip
        "CHALLENGE_USED": (60, 40, 0),  # dim amber — used ABS challenge pip
    }
)


# PEP 562: external imports (`from led_ticker.widgets.mlb import WIN_COLOR`)
# resolve through __getattr__ on first access. Bare-name use inside this
# module must call `_team_palette(...)` directly because PEP 562 doesn't
# fire for in-module name lookups.
def __getattr__(name: str) -> Color:
    return _team_palette(name)


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
    return make_color(r, g, b)


def _team_color_by_name(name: str) -> Color:
    """Get graphics.Color for an API team name (e.g. 'Mets')."""
    abbr = MLB_NAME_TO_ABBR.get(name, "")
    r, g, b = MLB_TEAM_COLORS.get(abbr, (255, 255, 255))
    return make_color(r, g, b)


@dataclass
class GameInfo:
    home_abbr: str
    away_abbr: str
    home_score: int | None = None
    away_score: int | None = None
    state: str = "preview"  # "final", "live", "preview", "postponed"
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
    # For state="postponed": short reason like "Rain" or "" if unknown
    postpone_reason: str = ""
    # For state="postponed": short tag like "PPD", "SUSP", "CANC"
    postpone_tag: str = "PPD"
    # ABS challenge counts (None = system not in effect / data unavailable)
    home_challenges: int | None = None
    away_challenges: int | None = None


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


def _classify_postponement(detailed_state: str) -> tuple[str | None, str]:
    """Map a `status.detailedState` string to (game_state, short_tag).

    Returns (None, "PPD") for non-postponement states; the caller should
    fall back to abstractGameState in that case.

    Examples of detailedState values from the MLB API:
      "Postponed"                  → ("postponed", "PPD")
      "Cancelled"                  → ("postponed", "CANC")
      "Suspended"                  → ("postponed", "SUSP")
      "Suspended: Rain"            → ("postponed", "SUSP")
      "Completed Early"            → ("postponed", "EARLY")
      "Completed Early: Rain"      → ("postponed", "EARLY")
    """
    s = detailed_state.lower()
    if "postponed" in s:
        return "postponed", "PPD"
    if "cancelled" in s or "canceled" in s:
        return "postponed", "CANC"
    if "suspended" in s:
        return "postponed", "SUSP"
    if "completed early" in s:
        return "postponed", "EARLY"
    return None, "PPD"


def _parse_team_abbr(team_data: dict[str, Any]) -> str:
    """Extract team abbreviation from MLB API team data."""
    return team_data.get("abbreviation", "???")


class MLBGameMessage:
    """A single game rendered with team colors and score colors.

    Segments are drawn through `draw_with_emoji` so any segment text
    can contain `:flower:` / `:star:` / etc. slugs that render as
    inline pixel-art icons. (Previously the widget had its own
    `icon: PixelData | None` parameter and rendered via the now-deleted
    `mlb_icons.draw_mlb_icon` helper — that's been folded into the
    standard emoji-rendering path.)

    `font_color` is an optional `ColorProvider` override. When set it
    replaces the per-segment colors, allowing a `color_cycle` effect to
    animate the whole message. `advance_frame()` increments the frame
    counter so `_advance_frame_if_supported` in the engine picks it up.
    """

    def __init__(
        self,
        segments: list[tuple[str, Color]],
        padding: int = 6,
        center: bool = False,
        bg_color: Color | None = None,
        font: Font | None = None,
        font_color: Color | ColorProvider | None = None,
    ) -> None:
        self.segments: list[tuple[str, Color]] = segments
        self.padding: int = padding
        self.center: bool = center
        self.bg_color: Color | None = bg_color
        self.font: Font = font if font is not None else FONT_DEFAULT
        self.font_color: Color | ColorProvider | None = font_color
        self._content_width: int = -1
        self._frame_count: int = 0

    def advance_frame(self, *, visit_id: int | None = None) -> None:
        self._frame_count += 1

    def pause_frame(self) -> None:
        pass

    def resume_frame(self) -> None:
        pass

    def reset_frame(self) -> None:
        self._frame_count = 0

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        from led_ticker.pixel_emoji import draw_with_emoji, measure_width

        if self._content_width < 0:
            self._content_width = sum(
                measure_width(self.font, text, canvas) for text, _ in self.segments
            )

        content_width = self._content_width
        cursor_pos, end_padding = compute_cursor(
            canvas.width,
            content_width,
            cursor_pos,
            self.padding,
            self.center,
        )

        # If a color provider override is set, use it for all segments.
        # This enables color_cycle / rainbow effects on game messages.
        override_color: Color | None = None
        if self.font_color is not None and hasattr(self.font_color, "color_for"):
            override_color = self.font_color.color_for(self._frame_count, 0, 1)

        baseline_y = compute_baseline(self.font, canvas, valign="center")
        for text, seg_color in self.segments:
            color = override_color if override_color is not None else seg_color
            cursor_pos += draw_with_emoji(
                canvas,
                self.font,
                int(cursor_pos),
                y=baseline_y,
                color=color,
                text=text,
                y_offset=y_offset,
            )

        cursor_pos += end_padding
        return canvas, cursor_pos


def _build_series_title(
    team_abbr: str,
    series: SeriesInfo,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
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

    # Show (ST) / (ASG) with inline emoji slug for special game types.
    # The slug renders as an 8×8 pixel-art icon via the standard emoji
    # path (or 32×32 hi-res on the bigsign — free upgrade vs the
    # previous 5×5 mlb_icons sprites).
    is_spring = any(g.game_type == "S" for g in series.games)
    is_allstar = any(g.game_type == "A" for g in series.games)
    if is_spring:
        segments.append((" (ST) :flower:", RGB_WHITE))
    elif is_allstar:
        segments.append((" (ASG) :star:", RGB_WHITE))

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
    return MLBGameMessage(
        segments, center=True, bg_color=bg_color, font=font, font_color=font_color
    )


def _build_game_message(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
) -> MLBGameMessage:
    """Build a message for a single game.

    Uses standard baseball convention: away team listed first.
    """
    away_c = _team_color(game.away_abbr)
    home_c = _team_color(game.home_abbr)

    if game.state == "final":
        away_won = (game.away_score or 0) > (game.home_score or 0)
        win_color = _team_palette("WIN_COLOR")
        loss_color = _team_palette("LOSS_COLOR")
        away_score_color = win_color if away_won else loss_color
        home_score_color = loss_color if away_won else win_color

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
        ball_c = make_color(80, 255, 80)  # green
        strike_c = make_color(255, 255, 80)  # yellow
        out_c = make_color(255, 80, 80)  # red

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

    elif game.state == "postponed":
        # Rain delay / cancelled / suspended / completed early. Show team
        # vs team with a short tag and reason if available, instead of
        # "(Final)" + None scores.
        tag_color = make_color(255, 200, 60)  # amber — distinct from win/loss/white
        if game.postpone_reason:
            tag = f" ({game.postpone_tag}: {game.postpone_reason})"
        else:
            tag = f" ({game.postpone_tag})"
        segments = [
            (game.away_abbr, away_c),
            (" @ ", RGB_WHITE),
            (game.home_abbr, home_c),
            (tag, tag_color),
        ]

    else:  # preview
        time_str = _format_game_time(game.start_time, tz) if game.start_time else "TBD"
        segments = [
            (game.away_abbr, away_c),
            (" @ ", RGB_WHITE),
            (game.home_abbr, home_c),
            (f" {time_str}", RGB_WHITE),
        ]

    return MLBGameMessage(
        segments, center=True, bg_color=bg_color, font=font, font_color=font_color
    )


def _build_scoreboard_message(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
) -> MLBScoreboardMessage:
    """Build a scoreboard-layout message for a single game."""
    from led_ticker.fonts import FONT_DEFAULT as _FONT_DEFAULT

    return MLBScoreboardMessage(
        game=game,
        team_abbr=team_abbr,
        tz=tz,
        bg_color=bg_color,
        font=font if font is not None else _FONT_DEFAULT,
        font_color=font_color,
    )


@attrs.define
class MLBScoreboardMessage(_FrameAware):
    """Scoreboard-style two-column game display.

    Renders: [away team + score] [center: inning/BSO/diamond] [home team + score]
    with ABS challenge pips beside each team name.
    """

    game: GameInfo
    team_abbr: str
    tz: ZoneInfo | None = None
    bg_color: Color | None = None
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        from led_ticker.drawing import compute_baseline_for_band, safe_scale
        from led_ticker.fonts import FONT_SMALL
        from led_ticker.pixel_emoji import draw_with_emoji, measure_width

        scale = safe_scale(canvas)
        half_h = canvas.height // 2  # logical rows per band (8 on 128×16 canvas)

        # Zone widths (logical pixels)
        left_w = canvas.width * 30 // 100
        right_w = canvas.width * 30 // 100
        right_start = canvas.width - right_w

        # Baselines: top half (team names), bottom half (scores)
        top_baseline = compute_baseline_for_band(
            self.font, half_h, scale, valign="center"
        )
        bottom_baseline = half_h + compute_baseline_for_band(
            self.font, half_h, scale, valign="center"
        )

        game = self.game

        # Determine colors
        away_c = _team_color(game.away_abbr)
        home_c = _team_color(game.home_abbr)

        if game.state == "final":
            away_won = (game.away_score or 0) > (game.home_score or 0)
            win_c = _team_palette("WIN_COLOR")
            loss_c = _team_palette("LOSS_COLOR")
            away_score_c = win_c if away_won else loss_c
            home_score_c = loss_c if away_won else win_c
        else:
            away_score_c = RGB_WHITE
            home_score_c = RGB_WHITE

        def _draw_centered(
            text: str, zone_start: int, zone_w: int, y: int, color: Color
        ) -> None:
            w = measure_width(self.font, text, canvas)
            x = zone_start + max(0, (zone_w - w) // 2)
            draw_with_emoji(canvas, self.font, x, y + y_offset, color, text)

        away_abbr = game.away_abbr
        home_abbr = game.home_abbr

        # Away team (left column)
        _draw_centered(away_abbr, 0, left_w, top_baseline, away_c)
        away_score_str = str(game.away_score) if game.away_score is not None else "–"
        _draw_centered(away_score_str, 0, left_w, bottom_baseline, away_score_c)

        # Home team (right column)
        _draw_centered(home_abbr, right_start, right_w, top_baseline, home_c)
        home_score_str = str(game.home_score) if game.home_score is not None else "–"
        _draw_centered(
            home_score_str, right_start, right_w, bottom_baseline, home_score_c
        )

        # ABS challenge pips — superscript beside each team abbreviation
        def _draw_pips(
            count: int | None, abbr: str, zone_start: int, zone_w: int, y: int
        ) -> None:
            if count is None:
                return
            n = min(count, 2)
            abbr_w = measure_width(self.font, abbr, canvas)
            abbr_center = zone_start + max(0, (zone_w - abbr_w) // 2)
            pip_x = abbr_center + abbr_w + 1
            pip_w = measure_width(FONT_SMALL, "●", canvas)
            for i in range(2):
                color = (
                    _team_palette("CHALLENGE_COLOR")
                    if i < n
                    else _team_palette("CHALLENGE_USED")
                )
                draw_with_emoji(
                    canvas,
                    FONT_SMALL,
                    pip_x + i * (pip_w + 1),
                    y=y + y_offset,
                    color=color,
                    text="●",
                )

        _draw_pips(game.away_challenges, away_abbr, 0, left_w, top_baseline)
        _draw_pips(game.home_challenges, home_abbr, right_start, right_w, top_baseline)

        # --- Center zone ---
        center_total = canvas.width - left_w - right_w
        center_half = center_total // 2
        cl_start = left_w  # center-left x start
        cr_start = left_w + center_half  # center-right x start

        small_top = compute_baseline_for_band(
            FONT_SMALL, half_h, scale, valign="center"
        )
        small_bottom = half_h + compute_baseline_for_band(
            FONT_SMALL, half_h, scale, valign="center"
        )

        def _draw_small(text: str, x: int, y: int, color: Color) -> None:
            draw_with_emoji(
                canvas, FONT_SMALL, x, y=y + y_offset, color=color, text=text
            )

        # Helper: draw primary-font text horizontally centered in the full
        # center zone (cl_start → right_start).
        def _draw_center(text: str, y: int, color: Color) -> None:
            w = measure_width(self.font, text, canvas)
            x = cl_start + max(0, (center_total - w) // 2)
            draw_with_emoji(
                canvas, self.font, x, y=y + y_offset, color=color, text=text
            )

        if game.state == "live":
            # Row 0: inning + outs dots
            inning_str = game.inning or "–"
            out_c = make_color(255, 80, 80)
            outs = game.outs or 0
            outs_str = "●" * outs + "○" * (3 - outs)
            _draw_small(inning_str, cl_start, small_top, RGB_WHITE)
            inning_w = measure_width(FONT_SMALL, inning_str, canvas)
            _draw_small(outs_str, cl_start + inning_w + 2, small_top, out_c)

            # Row 1: B/S count
            ball_c = make_color(80, 255, 80)
            strike_c = make_color(255, 255, 80)
            _draw_small(str(game.balls), cl_start, small_bottom, ball_c)
            b_w = measure_width(FONT_SMALL, str(game.balls), canvas)
            _draw_small("B ", cl_start + b_w, small_bottom, RGB_WHITE)
            bs_w = b_w + measure_width(FONT_SMALL, "B ", canvas)
            _draw_small(str(game.strikes), cl_start + bs_w, small_bottom, strike_c)
            s_w = measure_width(FONT_SMALL, str(game.strikes), canvas)
            _draw_small("S", cl_start + bs_w + s_w, small_bottom, RGB_WHITE)

            # Diamond: center-right zone
            occupied_c = make_color(255, 220, 50)  # yellow
            empty_c = make_color(50, 50, 50)  # dim
            b2 = "◆" if game.on_second else "◇"
            b3 = "◆" if game.on_third else "◇"
            b1 = "◆" if game.on_first else "◇"

            b2_c = occupied_c if game.on_second else empty_c
            b3_c = occupied_c if game.on_third else empty_c
            b1_c = occupied_c if game.on_first else empty_c

            char_w = measure_width(FONT_SMALL, b2, canvas)
            b1_w = measure_width(FONT_SMALL, b1, canvas)
            cr_center = cr_start + center_half // 2

            # Row 0: 2B centered
            _draw_small(b2, cr_center - char_w // 2, small_top, b2_c)

            # Row 1: 3B left, 1B right
            _draw_small(b3, cr_start, small_bottom, b3_c)
            _draw_small(b1, cr_start + center_half - b1_w, small_bottom, b1_c)

        elif game.state == "final":
            _draw_center("FINAL", top_baseline, make_color(180, 180, 180))

        elif game.state == "preview":
            _tz = self.tz or ZoneInfo("UTC")
            if game.start_time:
                local = game.start_time.astimezone(_tz)
                now = datetime.now(_tz)
                if local.date() == now.date():
                    date_str = "Today"
                elif local.date() == (now + timedelta(days=1)).date():
                    date_str = "Tmrw"
                else:
                    date_str = local.strftime("%a")
                time_str = local.strftime("%-I:%M %p")
            else:
                date_str = ""
                time_str = "TBD"
            _draw_center(date_str, top_baseline, make_color(160, 160, 160))
            _draw_center(time_str, bottom_baseline, RGB_WHITE)

        elif game.state == "postponed":
            tag_c = make_color(255, 200, 60)
            _draw_center(game.postpone_tag, top_baseline, tag_c)
            if game.postpone_reason:
                _draw_center(game.postpone_reason[:6], bottom_baseline, tag_c)

        elif game.state == "off_day":
            _draw_center("–", top_baseline, make_color(120, 120, 120))

        return canvas, cursor_pos + canvas.width


@register("mlb")
@attrs.define
class MLBScoreMonitor:
    """MLB scores for a single team's current series."""

    session: aiohttp.ClientSession
    team: str
    timezone: str = "America/New_York"
    padding: int = 6
    final_hold_hours: int = 6
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    layout: str = attrs.field(default="ticker", kw_only=True)
    _team_id: int = attrs.field(init=False, default=0)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    _has_live_game: bool = attrs.field(init=False, default=False)
    feed_title: TickerMessage | MLBGameMessage | MLBScoreboardMessage | None = (
        attrs.field(init=False, default=None)
    )
    feed_stories: list[TickerMessage | MLBGameMessage | MLBScoreboardMessage] = (
        attrs.field(init=False, factory=list)
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

        # Resolve effective colors: honour explicit font_color override,
        # else fall back to the per-widget defaults.
        title_color = (
            self.font_color if self.font_color is not None else _team_color(self.team)
        )
        body_color = self.font_color if self.font_color is not None else RGB_WHITE

        if not self._team_id:
            title = TickerMessage(
                f"{team_name}",
                font_color=title_color,
                bg_color=self.bg_color,
            )
            self.feed_title = title
            self.feed_stories = [
                title,
                TickerMessage("No Data", font_color=body_color, bg_color=self.bg_color),
            ]
            return

        now = datetime.now(tz)
        start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        end = (now + timedelta(days=7)).strftime("%Y-%m-%d")

        url = (
            f"{MLB_API}/schedule?teamId={self._team_id}"
            f"&startDate={start}&endDate={end}&sportId=1"
            f"&hydrate=team,linescore,challenges"
        )

        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.exception("MLB API error for %s", self.team)
            title = TickerMessage(
                f"{team_name}",
                font_color=title_color,
                bg_color=self.bg_color,
            )
            self.feed_title = title
            self.feed_stories = [
                title,
                TickerMessage("No Data", font_color=body_color, bg_color=self.bg_color),
            ]
            return

        games = self._parse_games(data, tz)

        if not games:
            title = TickerMessage(
                f"{team_name}",
                font_color=title_color,
                bg_color=self.bg_color,
            )
            self.feed_title = title
            self.feed_stories = [
                title,
                TickerMessage(
                    "Season Over", font_color=body_color, bg_color=self.bg_color
                ),
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
                font_color=title_color,
                bg_color=self.bg_color,
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
                        font_color=body_color,
                        bg_color=self.bg_color,
                    ),
                ]
            else:
                self.feed_stories = [
                    title,
                    TickerMessage(
                        "Season Over", font_color=body_color, bg_color=self.bg_color
                    ),
                ]
            self._has_live_game = False
            return

        # Build display from current series
        series_title = _build_series_title(
            self.team,
            current,
            tz,
            bg_color=self.bg_color,
            font=self.font,
            font_color=self.font_color,
        )
        self.feed_title = series_title
        _build_msg = (
            _build_scoreboard_message
            if self.layout == "scoreboard"
            else _build_game_message
        )
        stories: list[TickerMessage | MLBGameMessage | MLBScoreboardMessage] = [
            series_title
        ]
        stories.extend(
            _build_msg(
                g,
                self.team,
                tz,
                bg_color=self.bg_color,
                font=self.font,
                font_color=self.font_color,
            )
            for g in current.games
        )
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
                detailed = status.get("detailedState", "")
                reason = status.get("reason", "") or ""

                # Postponed / cancelled / suspended games come through with
                # abstractGameState="Final" but detailedState like
                # "Postponed", "Cancelled", "Suspended: Rain", etc. Detect
                # those before treating the game as completed (which would
                # render None scores as if the game ended 0-0).
                postponed_state, postpone_tag = _classify_postponement(detailed)

                home_team = g.get("teams", {}).get("home", {})
                away_team = g.get("teams", {}).get("away", {})
                home_abbr = _parse_team_abbr(home_team.get("team", {}))
                away_abbr = _parse_team_abbr(away_team.get("team", {}))

                home_score = home_team.get("score")
                away_score = away_team.get("score")

                inning: str | None = None
                balls = strikes = outs = 0
                on_first = on_second = on_third = False
                if abstract == "Live" and not postponed_state:
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

                # ABS challenges — present only for games where the system is active.
                home_challenges: int | None = None
                away_challenges: int | None = None
                challenges = g.get("challenges", {})
                if challenges:
                    hc = challenges.get("home", {})
                    ac = challenges.get("away", {})
                    if hc is not None and "remainingChallenges" in hc:
                        home_challenges = int(hc["remainingChallenges"])
                    if ac is not None and "remainingChallenges" in ac:
                        away_challenges = int(ac["remainingChallenges"])

                start_time: datetime | None = None
                game_date = g.get("gameDate")
                if game_date:
                    with contextlib.suppress(ValueError, TypeError):
                        start_time = datetime.fromisoformat(
                            game_date.replace("Z", "+00:00")
                        )

                state_map: dict[str, str] = {
                    "Final": "final",
                    "Live": "live",
                    "Preview": "preview",
                }

                resolved_state = (
                    postponed_state
                    if postponed_state is not None
                    else state_map.get(abstract, "preview")
                )

                games.append(
                    GameInfo(
                        home_abbr=home_abbr,
                        away_abbr=away_abbr,
                        home_score=home_score,
                        away_score=away_score,
                        state=resolved_state,
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
                        postpone_reason=reason if postponed_state else "",
                        postpone_tag=postpone_tag if postponed_state else "PPD",
                        home_challenges=home_challenges,
                        away_challenges=away_challenges,
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
            # "Final" + "postponed" both count as "this game is done for now"
            # for the purpose of locating the current series.
            has_final = any(g.state in ("final", "postponed") for g in s.games)
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
