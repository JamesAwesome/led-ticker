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
from led_ticker.fonts import FONT_DEFAULT, FONT_SMALL
from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import _FrameAware
from led_ticker.widgets.message import SegmentMessage, TickerMessage

logger: logging.Logger = logging.getLogger(__name__)

MLB_API: str = "https://statsapi.mlb.com/api/v1"
_MLB_LIVE_API: str = "https://statsapi.mlb.com/api/v1.1"

# Update intervals (seconds)
_INTERVAL_LIVE: int = 45  # ~half-inning cadence
_INTERVAL_IDLE: int = 300  # 5 minutes
_INTERVAL_OFFSEASON: int = 86400  # daily

_team_palette = lazy_palette(
    {
        "WIN_COLOR": (46, 200, 46),
        "LOSS_COLOR": (220, 30, 30),
        "LIVE_COLOR": (255, 40, 40),
        "CHALLENGE_COLOR": (255, 140, 0),  # orange — remaining ABS challenge dash
        "CHALLENGE_USED": (140, 140, 140),  # grey — used ABS challenge dash
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


def _fit_team_name(abbr: str, zone_w: int, font: Font, canvas: Canvas) -> str:
    """Return the short team name if it fits in zone_w logical pixels, else abbr."""
    from led_ticker.pixel_emoji import measure_width

    name = MLB_TEAM_NAMES.get(abbr, abbr)
    return name if measure_width(font, name, canvas) <= zone_w else abbr


def _lift_color(r: int, g: int, b: int, min_max: int = 120) -> tuple[int, int, int]:
    """Scale dark colors proportionally so the brightest channel >= min_max.

    Preserves hue and saturation; teams already above the threshold are unchanged.
    At display brightness=60, min_max=120 ensures the peak channel renders at ~72
    on the physical panel — clearly legible against a black background.
    """
    peak = max(r, g, b)
    if peak == 0 or peak >= min_max:
        return r, g, b
    scale = min_max / peak
    return (
        min(255, round(r * scale)),
        min(255, round(g * scale)),
        min(255, round(b * scale)),
    )


def _team_color(abbr: str) -> Color:
    """Get graphics.Color for a team abbreviation."""
    r, g, b = MLB_TEAM_COLORS.get(abbr, (255, 255, 255))
    r, g, b = _lift_color(r, g, b)
    return make_color(r, g, b)


def _team_color_by_name(name: str) -> Color:
    """Get graphics.Color for an API team name (e.g. 'Mets')."""
    abbr = MLB_NAME_TO_ABBR.get(name, "")
    r, g, b = MLB_TEAM_COLORS.get(abbr, (255, 255, 255))
    r, g, b = _lift_color(r, g, b)
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


def _build_series_title(
    team_abbr: str,
    series: SeriesInfo,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
) -> SegmentMessage:
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
        away_name = MLB_TEAM_NAMES.get(away, away)
        home_name = MLB_TEAM_NAMES.get(home, home)
        segments: list[tuple[str, Color]] = [
            (away_name, away_c),
            (" @ ", RGB_WHITE),
            (home_name, home_c),
        ]
        # First listed team is away, second is home
        first_is_team = away == team_abbr
    else:
        team_name = MLB_TEAM_NAMES.get(team_abbr, team_abbr)
        opp_name = MLB_TEAM_NAMES.get(series.opponent_abbr, series.opponent_abbr)
        segments = [
            (team_name, team_c),
            (" vs ", RGB_WHITE),
            (opp_name, opp_c),
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
    return SegmentMessage(
        segments, center=True, bg_color=bg_color, font=font, font_color=font_color
    )


def _build_game_message(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
) -> SegmentMessage:
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

    return SegmentMessage(
        segments, center=True, bg_color=bg_color, font=font, font_color=font_color
    )


def _build_scoreboard_message(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    small_font: Font | None = None,
    font_color: Color | ColorProvider | None = None,
) -> MLBScoreboardMessage:
    """Build a scoreboard-layout message for a single game."""
    return MLBScoreboardMessage(
        game=game,
        team_abbr=team_abbr,
        tz=tz,
        bg_color=bg_color,
        font=font if font is not None else FONT_DEFAULT,
        small_font=small_font if small_font is not None else FONT_SMALL,
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
    small_font: Font = attrs.field(default=FONT_SMALL, kw_only=True)

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        from led_ticker.drawing import compute_baseline_for_band, safe_scale
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

        # Use the full team name when it fits in the column; fall back to abbreviation.
        away_label = _fit_team_name(away_abbr, left_w, self.font, canvas)
        home_label = _fit_team_name(home_abbr, right_w, self.font, canvas)

        # Away team (left column)
        _draw_centered(away_label, 0, left_w, top_baseline, away_c)
        away_score_str = str(game.away_score) if game.away_score is not None else "–"
        _draw_centered(away_score_str, 0, left_w, bottom_baseline, away_score_c)

        # Home team (right column)
        _draw_centered(home_label, right_start, right_w, top_baseline, home_c)
        home_score_str = str(game.home_score) if game.home_score is not None else "–"
        _draw_centered(
            home_score_str, right_start, right_w, bottom_baseline, home_score_c
        )

        # ABS challenge dashes — two "-" stacked vertically, centered in the
        # gap between the score number and the outer edge of each zone.
        # Orange = remaining (unused), grey = used.
        # 5/8 and 7/8 through the bottom band → ~6px physical gap between
        # dashes at scale=4, matching the colon character's dot spacing.
        def _draw_dash_pips(count: int | None, align_right: bool) -> None:
            if count is None:
                return
            n = min(count, 2)
            dash_w = measure_width(self.small_font, "-", canvas)
            if align_right:
                score_w = measure_width(self.font, home_score_str, canvas)
                score_inner = right_start + max(0, (right_w - score_w) // 2) + score_w
                x = score_inner + max(0, (canvas.width - score_inner - dash_w) // 2)
            else:
                score_w = measure_width(self.font, away_score_str, canvas)
                score_inner = max(0, (left_w - score_w) // 2)
                x = max(0, (score_inner - dash_w) // 2)
            y1 = half_h + (5 * half_h) // 8
            y2 = half_h + (7 * half_h) // 8
            for i, y in enumerate((y1, y2)):
                color = (
                    _team_palette("CHALLENGE_COLOR")
                    if i < n
                    else _team_palette("CHALLENGE_USED")
                )
                draw_with_emoji(
                    canvas, self.small_font, x, y=y + y_offset, color=color, text="-"
                )

        _draw_dash_pips(game.away_challenges, align_right=False)
        _draw_dash_pips(game.home_challenges, align_right=True)

        # --- Center zone ---
        center_total = canvas.width - left_w - right_w
        center_half = center_total // 2
        cl_start = left_w  # center-left x start
        cr_start = left_w + center_half  # center-right x start

        small_top = compute_baseline_for_band(
            self.small_font, half_h, scale, valign="center"
        )
        small_bottom = half_h + compute_baseline_for_band(
            self.small_font, half_h, scale, valign="center"
        )

        def _draw_small(text: str, x: int, y: int, color: Color) -> None:
            draw_with_emoji(
                canvas, self.small_font, x, y=y + y_offset, color=color, text=text
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
            inning_w = measure_width(self.small_font, inning_str, canvas)
            _draw_small(outs_str, cl_start + inning_w + 2, small_top, out_c)

            # Row 1: B/S count
            ball_c = make_color(80, 255, 80)
            strike_c = make_color(255, 255, 80)
            _draw_small(str(game.balls), cl_start, small_bottom, ball_c)
            b_w = measure_width(self.small_font, str(game.balls), canvas)
            _draw_small("B ", cl_start + b_w, small_bottom, RGB_WHITE)
            bs_w = b_w + measure_width(self.small_font, "B ", canvas)
            _draw_small(str(game.strikes), cl_start + bs_w, small_bottom, strike_c)
            s_w = measure_width(self.small_font, str(game.strikes), canvas)
            _draw_small("S", cl_start + bs_w + s_w, small_bottom, RGB_WHITE)

            # Diamond: center-right zone — use main font for larger glyphs.
            # Pack 3B/1B with a 2px gap, cluster centered in the zone.
            # 2B centered horizontally above the midpoint.
            occupied_c = make_color(255, 220, 50)  # yellow
            empty_c = make_color(50, 50, 50)  # dim
            b2 = "◆" if game.on_second else "◇"
            b3 = "◆" if game.on_third else "◇"
            b1 = "◆" if game.on_first else "◇"

            b2_c = occupied_c if game.on_second else empty_c
            b3_c = occupied_c if game.on_third else empty_c
            b1_c = occupied_c if game.on_first else empty_c

            dw = measure_width(self.font, b2, canvas)
            diamond_gap = 2
            cluster_w = 2 * dw + diamond_gap
            cluster_x = cr_start + max(0, (center_half - cluster_w) // 2)
            b3_x = cluster_x
            b1_x = cluster_x + dw + diamond_gap
            b2_x = cluster_x + dw + diamond_gap // 2 - dw // 2

            # 2B uses top-band center baseline; 3B/1B use bottom-band
            # bottom-aligned so the glyphs sit inside the band without clip.
            diamond_top_y = compute_baseline_for_band(
                self.font, half_h, scale, valign="center"
            )
            diamond_bot_y = half_h + compute_baseline_for_band(
                self.font, half_h, scale, valign="bottom"
            )
            draw_with_emoji(
                canvas, self.font, b2_x, y=diamond_top_y + y_offset, color=b2_c, text=b2
            )
            draw_with_emoji(
                canvas, self.font, b3_x, y=diamond_bot_y + y_offset, color=b3_c, text=b3
            )
            draw_with_emoji(
                canvas, self.font, b1_x, y=diamond_bot_y + y_offset, color=b1_c, text=b1
            )

        elif game.state == "final":
            full_baseline = compute_baseline_for_band(
                self.font, canvas.height, scale, valign="center"
            )
            _draw_center("FINAL", full_baseline, make_color(180, 180, 180))

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


def _compute_preview_two_row(
    game: GameInfo,
    team_abbr: str,  # uniform signature — used by final/live/postponed helpers
    tz: ZoneInfo,
    series_wins: int,
    series_losses: int,
) -> tuple[list[tuple[str, Color]], list[tuple[str, Color]]]:
    """Compute top/bottom segment lists for a preview-state game."""
    away_c = _team_color(game.away_abbr)
    home_c = _team_color(game.home_abbr)
    top: list[tuple[str, Color]] = [
        (game.away_abbr, away_c),
        (" @ ", RGB_WHITE),
        (game.home_abbr, home_c),
    ]
    if series_wins + series_losses > 0:
        top.append((f" ({series_wins}-{series_losses})", make_color(150, 150, 150)))  # grey — series record
    time_str = _format_game_time(game.start_time, tz) if game.start_time else "TBD"
    bot: list[tuple[str, Color]] = [(time_str, RGB_WHITE)]
    return top, bot


def _pip_segments(count: int | None) -> list[tuple[str, Color]]:
    """ABS challenge pip dashes for one team's score.

    Returns empty list when count is None (ABS not in effect).
    Orange dashes for remaining challenges, grey for used (max 2 shown).
    """
    if count is None:
        return []
    chal_c = _team_palette("CHALLENGE_COLOR")
    used_c = _team_palette("CHALLENGE_USED")
    n = min(count, 2)
    return [("-", chal_c if i < n else used_c) for i in range(2)]


def _compute_final_two_row(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,  # uniform signature — unused here
    series_wins: int,
    series_losses: int,
    series_total_games: int = 1,
) -> tuple[list[tuple[str, Color]], list[tuple[str, Color]]]:
    """Compute top/bottom segment lists for a final-state game."""
    win_c = _team_palette("WIN_COLOR")
    loss_c = _team_palette("LOSS_COLOR")
    away_c = _team_color(game.away_abbr)
    home_c = _team_color(game.home_abbr)
    away_won = (game.away_score or 0) > (game.home_score or 0)
    away_score_c = win_c if away_won else loss_c
    home_score_c = loss_c if away_won else win_c

    away_score_str = str(game.away_score) if game.away_score is not None else "–"
    home_score_str = str(game.home_score) if game.home_score is not None else "–"

    top: list[tuple[str, Color]] = []
    top.append((game.away_abbr, away_c))
    top.append((f" {away_score_str}", away_score_c))
    top.extend(_pip_segments(game.away_challenges))
    top.append(("  ", RGB_WHITE))
    top.append((game.home_abbr, home_c))
    top.append((f" {home_score_str}", home_score_c))
    top.extend(_pip_segments(game.home_challenges))

    grey = make_color(180, 180, 180)  # grey — FINAL label
    bot: list[tuple[str, Color]] = [("FINAL", grey)]

    if series_total_games > 1 and (series_wins + series_losses) > 0:
        bot.append((" · ", grey))
        if series_wins > series_losses:
            leader_abbr = team_abbr
        elif series_losses > series_wins:
            opp = game.home_abbr if game.away_abbr == team_abbr else game.away_abbr
            leader_abbr = opp
        else:
            leader_abbr = None

        if leader_abbr is None:
            bot.append((f"Tied {series_wins}-{series_losses}", RGB_WHITE))
        else:
            bot.append((leader_abbr, _team_color(leader_abbr)))
            bot.append((f" leads {series_wins}-{series_losses}", RGB_WHITE))

    return top, bot


def _compute_live_two_row(
    game: GameInfo,
    team_abbr: str,  # uniform signature — unused here
    tz: ZoneInfo,    # uniform signature — unused here
    series_wins: int,   # uniform signature — unused here
    series_losses: int, # uniform signature — unused here
) -> tuple[list[tuple[str, Color]], list[tuple[str, Color]]]:
    """Compute top/bottom segment lists for a live-state game."""
    away_c = _team_color(game.away_abbr)
    home_c = _team_color(game.home_abbr)
    away_score_str = str(game.away_score) if game.away_score is not None else "–"
    home_score_str = str(game.home_score) if game.home_score is not None else "–"

    top: list[tuple[str, Color]] = []
    top.append((game.away_abbr, away_c))
    top.append((f" {away_score_str}", RGB_WHITE))
    top.extend(_pip_segments(game.away_challenges))
    top.append(("  ", RGB_WHITE))
    top.append((game.home_abbr, home_c))
    top.append((f" {home_score_str}", RGB_WHITE))
    top.extend(_pip_segments(game.home_challenges))

    live_c = _team_palette("LIVE_COLOR")
    ball_c = make_color(80, 255, 80)    # green — balls
    strike_c = make_color(255, 255, 80)  # yellow — strikes
    out_c = make_color(255, 80, 80)     # red — outs
    occupied_c = make_color(255, 220, 50)  # yellow — occupied base
    empty_c = make_color(50, 50, 50)       # dim — empty base

    inning_str = game.inning or "–"
    b3 = "◆" if game.on_third else "◇"
    b2 = "◆" if game.on_second else "◇"
    b1 = "◆" if game.on_first else "◇"
    b3_c = occupied_c if game.on_third else empty_c
    b2_c = occupied_c if game.on_second else empty_c
    b1_c = occupied_c if game.on_first else empty_c

    bot: list[tuple[str, Color]] = [
        (inning_str, live_c),
        ("  ", RGB_WHITE),
        (b3, b3_c),
        (b2, b2_c),
        (b1, b1_c),
        ("  ", RGB_WHITE),
        (str(game.balls), ball_c),
        ("·", RGB_WHITE),
        (str(game.strikes), strike_c),
        ("·", RGB_WHITE),
        (str(game.outs), out_c),
    ]
    return top, bot


def _compute_postponed_two_row(
    game: GameInfo,
    team_abbr: str,    # uniform signature — unused here
    tz: ZoneInfo,      # uniform signature — unused here
    series_wins: int,  # uniform signature — unused here
    series_losses: int, # uniform signature — unused here
) -> tuple[list[tuple[str, Color]], list[tuple[str, Color]]]:
    """Compute top/bottom segment lists for a postponed-state game."""
    away_c = _team_color(game.away_abbr)
    home_c = _team_color(game.home_abbr)
    top: list[tuple[str, Color]] = [
        (game.away_abbr, away_c),
        (" @ ", RGB_WHITE),
        (game.home_abbr, home_c),
    ]
    tag_color = make_color(255, 200, 60)  # amber — postponed/cancelled tag
    if game.postpone_reason:
        tag = f"{game.postpone_tag}: {game.postpone_reason}"
    else:
        tag = game.postpone_tag
    bot: list[tuple[str, Color]] = [(tag, tag_color)]
    return top, bot


def _build_two_row_message(
    game: GameInfo,
    team_abbr: str,
    tz: ZoneInfo,
    bg_color: Color | None = None,
    font: Font | None = None,
    small_font: Font | None = None,
    top_font: Font | None = None,
    top_row_height: int | None = None,
    font_color: Color | ColorProvider | None = None,
    series_wins: int = 0,
    series_losses: int = 0,
    series_total_games: int = 1,
) -> "MLBTwoRowMessage":
    """Build a two-row layout message for a single game."""
    if game.state == "preview":
        top_segs, bot_segs = _compute_preview_two_row(
            game, team_abbr, tz, series_wins, series_losses
        )
    elif game.state == "final":
        top_segs, bot_segs = _compute_final_two_row(
            game, team_abbr, tz, series_wins, series_losses, series_total_games
        )
    elif game.state == "live":
        top_segs, bot_segs = _compute_live_two_row(
            game, team_abbr, tz, series_wins, series_losses
        )
    elif game.state == "postponed":
        top_segs, bot_segs = _compute_postponed_two_row(
            game, team_abbr, tz, series_wins, series_losses
        )
    else:
        top_segs, bot_segs = [], []
    return MLBTwoRowMessage(
        game=game,
        team_abbr=team_abbr,
        tz=tz,
        bg_color=bg_color,
        font=font if font is not None else FONT_DEFAULT,
        small_font=small_font if small_font is not None else FONT_SMALL,
        top_font=top_font,
        top_row_height=top_row_height,
        font_color=font_color,
        top_segments=top_segs,
        bottom_segments=bot_segs,
    )


@attrs.define
class MLBTwoRowMessage(_FrameAware):
    """Two-band game display: score/matchup on top, status on bottom."""

    game: GameInfo
    team_abbr: str
    tz: ZoneInfo | None = None
    bg_color: Color | None = None
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    small_font: Font = attrs.field(default=FONT_SMALL, kw_only=True)
    top_font: Font | None = attrs.field(default=None, kw_only=True)
    top_row_height: int | None = attrs.field(default=None, kw_only=True)
    top_segments: list[tuple[str, Color]] = attrs.field(factory=list)
    bottom_segments: list[tuple[str, Color]] = attrs.field(factory=list)

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        return canvas, canvas.width  # stub — implemented in later tasks


@register("mlb")
@attrs.define
class MLBScoreMonitor:
    """MLB scores for a single team's current series."""

    session: aiohttp.ClientSession
    team: str
    timezone: str = "America/New_York"
    padding: int = 6
    final_hold_hours: int = 6
    hold_time: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    small_font: Font = attrs.field(default=FONT_SMALL, kw_only=True)
    layout: str = attrs.field(default="ticker", kw_only=True)
    top_font: Font | None = attrs.field(default=None, kw_only=True)
    top_row_height: int | None = attrs.field(default=None, kw_only=True)
    _team_id: int = attrs.field(init=False, default=0)
    _tz: ZoneInfo | None = attrs.field(init=False, default=None)
    _has_live_game: bool = attrs.field(init=False, default=False)
    feed_title: TickerMessage | SegmentMessage | MLBScoreboardMessage | MLBTwoRowMessage | None = (
        attrs.field(init=False, default=None)
    )
    feed_stories: list[TickerMessage | SegmentMessage | MLBScoreboardMessage | MLBTwoRowMessage] = (
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
            logger.info(
                "MLB %s updated: %d stories (no data)",
                self.team,
                len(self.feed_stories),
            )
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
                font_color=title_color,
                bg_color=self.bg_color,
            )
            self.feed_title = title
            self.feed_stories = [
                title,
                TickerMessage("No Data", font_color=body_color, bg_color=self.bg_color),
            ]
            logger.info(
                "MLB %s updated: %d stories (no data)",
                self.team,
                len(self.feed_stories),
            )
            return

        try:
            games = self._parse_games(data, tz)
        except Exception:
            logger.exception("MLB parse error for %s", self.team)
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
            logger.info(
                "MLB %s updated: %d stories (no data)",
                self.team,
                len(self.feed_stories),
            )
            return

        # Concurrently hydrate ABS challenge counts for live games.
        live_games = [g for g in games if g.state == "live" and g.game_pk]
        if live_games:
            results = await asyncio.gather(
                *(self._fetch_abs_challenges(g.game_pk) for g in live_games)
            )
            for g, (home_ch, away_ch) in zip(live_games, results, strict=False):
                g.home_challenges = home_ch
                g.away_challenges = away_ch

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
            logger.info(
                "MLB %s updated: %d stories (season over)",
                self.team,
                len(self.feed_stories),
            )
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
            next_label = "season over"
            if next_game:
                opp = (
                    next_game.away_abbr
                    if next_game.home_abbr == self.team
                    else next_game.home_abbr
                )
                opp_name = MLB_TEAM_NAMES.get(opp, opp)
                next_label = opp_name
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
            logger.info(
                "MLB %s updated: %d stories (next: %s)",
                self.team,
                len(self.feed_stories),
                next_label,
            )
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
        stories: list[TickerMessage | SegmentMessage | MLBScoreboardMessage | MLBTwoRowMessage] = [
            series_title
        ]
        if self.layout == "scoreboard":
            stories.extend(
                _build_scoreboard_message(
                    g,
                    self.team,
                    tz,
                    bg_color=self.bg_color,
                    font=self.font,
                    small_font=self.small_font,
                    font_color=self.font_color,
                )
                for g in current.games
            )
        elif self.layout == "two_row":
            stories.extend(
                _build_two_row_message(
                    g,
                    self.team,
                    tz,
                    bg_color=self.bg_color,
                    font=self.font,
                    small_font=self.small_font,
                    top_font=self.top_font,
                    top_row_height=self.top_row_height,
                    font_color=self.font_color,
                    series_wins=current.team_wins,
                    series_losses=current.team_losses,
                    series_total_games=len(current.games),
                )
                for g in current.games
            )
        else:
            stories.extend(
                _build_game_message(
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
        n_live = sum(1 for g in current.games if g.state == "live")
        logger.info(
            "MLB %s updated: %d stories (live: %d)",
            self.team,
            len(self.feed_stories),
            n_live,
        )

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

                # ABS challenges — hydrated separately for live games
                # via _fetch_abs_challenges.
                home_challenges: int | None = None
                away_challenges: int | None = None

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

    async def _fetch_abs_challenges(
        self, game_pk: int
    ) -> tuple[int | None, int | None]:
        """Fetch ABS challenge remaining counts from the live game feed.

        Returns (home_remaining, away_remaining), or (None, None) when ABS is
        not active for this game or the request fails.
        """
        url = f"{_MLB_LIVE_API}/game/{game_pk}/feed/live"
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except Exception:
            logger.exception("ABS challenge fetch failed for gamePk=%s", game_pk)
            return None, None

        abs_ch = data.get("gameData", {}).get("absChallenges", {})
        # Empty dict means ABS is not active at this park. Non-empty means ABS
        # is equipped; hasChallenges is false until the first challenge is made,
        # so we gate on the dict being non-empty rather than on hasChallenges.
        if not abs_ch or "home" not in abs_ch:
            return None, None

        home = abs_ch.get("home") or {}
        away = abs_ch.get("away") or {}
        with contextlib.suppress(TypeError, ValueError):
            return int(home.get("remaining", 0)), int(away.get("remaining", 0))
        return None, None
