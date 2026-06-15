"""Guard 4 — validate ⟹ no-crash property test (class E).

Invariant: if Calendar.validate_config() returns [] (accepted), then building
and drawing the widget must not raise.

Structure:
- For each config in the battery: run validate_config().
- If accepted (errors == []): assert validate_widget_cfg() does not raise AND,
  for file:// feeds, run update() then draw() on the resulting feed_stories.
- If rejected (errors != []): assert errors is non-empty and mentions the
  offending field.

No real network access. File:// feeds use either the shared fixture
(calendar_sample.ics) or an in-memory minimal .ics written to tmp_path.
"""

import asyncio
import textwrap
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from led_ticker.widgets.calendar import Calendar

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "calendar_sample.ics"

# A tiny in-memory ICS that validate_widget_cfg can use for its update() step.
_MINI_ICS = textwrap.dedent("""\
    BEGIN:VCALENDAR
    VERSION:2.0
    PRODID:-//test//EN
    BEGIN:VEVENT
    UID:mini-1
    DTSTART:20260615T150000Z
    DTEND:20260615T160000Z
    SUMMARY:Mini Event
    END:VEVENT
    END:VCALENDAR
""")


def _mini_ics_file(tmp_path: Path) -> str:
    """Write _MINI_ICS to tmp_path and return a file:// URL."""
    p = tmp_path / "mini.ics"
    p.write_text(_MINI_ICS)
    return f"file://{p}"


def _fixture_url() -> str:
    return f"file://{_FIXTURE}"


def _fixed_now(tz):
    if tz is None:
        return datetime(2026, 6, 15, 0, 0, tzinfo=datetime.now().astimezone().tzinfo)
    return datetime(2026, 6, 15, 0, 0, tzinfo=tz)


def _check_accepted(cfg: dict, tmp_path: Path) -> None:
    """Accepted config: build + draw must not raise."""
    # 1) validate_widget_cfg must not raise
    from led_ticker.app.factories import validate_widget_cfg

    # validate_widget_cfg pops 'type' and coerces in-place; work on a copy.
    asyncio.run(validate_widget_cfg(dict(cfg), session=None))

    # 2) Build a Calendar and run update() + draw() on feed_stories.
    # Inject the mini fixture if the config doesn't have a reachable file:// URL.
    build_cfg = {k: v for k, v in cfg.items() if k != "type"}
    if not build_cfg.get("ics_url", "").startswith("file://"):
        build_cfg["ics_url"] = _mini_ics_file(tmp_path)
    # session is None — Calendar._fetch_ics handles file://
    cal = Calendar(session=None, **build_cfg)
    _now_patch = "led_ticker.widgets.calendar._now_in"
    with patch(_now_patch, side_effect=_fixed_now):
        asyncio.run(cal.update())

    canvas = Mock()
    canvas.width = 160
    canvas.height = 16
    for story in cal.feed_stories:
        with patch(_now_patch, side_effect=_fixed_now):
            story.draw(canvas)


# ---------------------------------------------------------------------------
# Battery of configs
# ---------------------------------------------------------------------------
# Each entry: (test_id, cfg, rejected_field_or_None)
# rejected_field_or_None:
#   None => accepted; build+draw must not raise (http configs: validate only)
#   str  => rejected; errors must mention this field name

_VALID_ICS_URL = _fixture_url()
_V = _VALID_ICS_URL  # short alias for use in the parametrize table below


def _c(tid: str, cfg: dict, rej: str | None = None) -> tuple:
    """Shorthand to build a parametrize case tuple."""
    return (tid, cfg, rej)


def _cal(**kw) -> dict:
    """Build a calendar config dict; type is always injected."""
    return {"type": "calendar", **kw}


_CASES: list[tuple[str, dict, str | None]] = [
    # --- ics_url ---
    _c("ics_url_http", _cal(ics_url="http://x.com/c.ics", timezone="UTC")),
    _c("ics_url_https", _cal(ics_url="https://x.com/c.ics", timezone="UTC")),
    _c("ics_url_webcal", _cal(ics_url="webcal://x.com/c.ics", timezone="UTC")),
    _c("ics_url_file", _cal(ics_url=_V, timezone="UTC")),
    _c("ics_url_bare_path", _cal(ics_url=str(_FIXTURE), timezone="UTC")),
    _c("ics_url_missing", _cal(), "ics_url"),
    _c("ics_url_empty", _cal(ics_url=""), "ics_url"),
    _c("ics_url_whitespace", _cal(ics_url="   "), "ics_url"),
    _c("ics_url_non_str", _cal(ics_url=42), "ics_url"),
    # --- layout ---
    _c("layout_agenda", _cal(ics_url=_V, layout="agenda")),
    _c("layout_next", _cal(ics_url=_V, layout="next")),
    _c("layout_bad", _cal(ics_url="x", layout="bad"), "layout"),
    _c("layout_non_str", _cal(ics_url="x", layout=99), "layout"),
    # --- max_events ---
    _c("max_events_zero", _cal(ics_url=_V, max_events=0)),
    _c("max_events_5", _cal(ics_url=_V, max_events=5)),
    _c("max_events_huge", _cal(ics_url=_V, max_events=10000)),
    _c("max_events_negative", _cal(ics_url="x", max_events=-1), "max_events"),
    _c("max_events_bool_t", _cal(ics_url="x", max_events=True), "max_events"),
    _c("max_events_bool_f", _cal(ics_url="x", max_events=False), "max_events"),
    _c("max_events_non_int", _cal(ics_url="x", max_events="five"), "max_events"),
    # --- lookahead_days ---
    _c("lookahead_1", _cal(ics_url=_V, lookahead_days=1)),
    _c("lookahead_max", _cal(ics_url=_V, lookahead_days=366)),
    _c("lookahead_zero", _cal(ics_url=_V, lookahead_days=0)),
    _c("lookahead_toolarge", _cal(ics_url="x", lookahead_days=10000), "lookahead_days"),
    _c("lookahead_neg", _cal(ics_url="x", lookahead_days=-1), "lookahead_days"),
    _c("lookahead_bool", _cal(ics_url="x", lookahead_days=True), "lookahead_days"),
    # --- time_format ---
    _c("time_format_12h", _cal(ics_url=_V, time_format="12h")),
    _c("time_format_24h", _cal(ics_url=_V, time_format="24h")),
    _c("time_format_strftime", _cal(ics_url=_V, time_format="%H:%M")),
    _c("time_format_bogus", _cal(ics_url="x", time_format="bogus"), "time_format"),
    _c("time_format_int", _cal(ics_url="x", time_format=24), "time_format"),
    # --- timezone ---
    _c("timezone_utc", _cal(ics_url=_V, timezone="UTC")),
    _c("timezone_ny", _cal(ics_url=_V, timezone="America/New_York")),
    _c("timezone_empty", _cal(ics_url=_V, timezone="")),
    _c("timezone_none", _cal(ics_url=_V)),
    _c("timezone_bad", _cal(ics_url="x", timezone="Mars/Phobos"), "timezone"),
    _c("timezone_non_str", _cal(ics_url="x", timezone=123), "timezone"),
    # --- filter ---
    _c("filter_empty", _cal(ics_url=_V, filter=[])),
    _c("filter_keywords", _cal(ics_url=_V, filter=["standup", "meet"])),
    _c("filter_string", _cal(ics_url="x", filter="standup"), "filter"),
    _c("filter_int_list", _cal(ics_url="x", filter=[1, 2]), "filter"),
    # --- highlight ---
    _c("highlight_empty", _cal(ics_url=_V, highlight=[])),
    _c("highlight_keywords", _cal(ics_url=_V, highlight=["payday"])),
    _c("highlight_string", _cal(ics_url="x", highlight="payday"), "highlight"),
    _c("highlight_int_list", _cal(ics_url="x", highlight=[42]), "highlight"),
    # --- highlight_color (coerced by factory; validate_config accepts any value) ---
    _c("highlight_color_rgb", _cal(ics_url=_V, highlight_color=[255, 200, 60])),
    _c("highlight_color_rainbow", _cal(ics_url=_V, highlight_color="rainbow")),
]


@pytest.mark.parametrize("test_id,cfg,rejected_field", _CASES)
def test_validate_contract(test_id, cfg, rejected_field, tmp_path):
    """If validate_config accepts, build + draw must not raise.
    If it rejects, errors must be non-empty and mention the field.
    """
    errors = Calendar.validate_config(cfg)

    if rejected_field is None:
        assert errors == [], f"[{test_id}] unexpected errors: {errors}"
        # Skip live-network configs at build/draw time.
        ics = cfg.get("ics_url", "")
        if ics.startswith(("http://", "https://", "webcal://")):
            return  # validated-only is enough for http configs
        _check_accepted(cfg, tmp_path)
    else:
        assert errors, f"[{test_id}] should have rejected '{rejected_field}', got []"
        assert any(rejected_field in msg for msg in errors), (
            f"[{test_id}] errors must mention '{rejected_field}': {errors}"
        )


# ---------------------------------------------------------------------------
# Edge: ensure that every accepted layout draws without crash with real events
# ---------------------------------------------------------------------------


def test_accepted_agenda_draws_without_crash(tmp_path):
    """layout='agenda' with real fixture events: all stories draw cleanly."""
    cfg = {
        "type": "calendar",
        "ics_url": _fixture_url(),
        "layout": "agenda",
        "timezone": "UTC",
        "max_events": 5,
    }
    errors = Calendar.validate_config(cfg)
    assert errors == []
    _check_accepted(cfg, tmp_path)


def test_accepted_next_draws_without_crash(tmp_path):
    """layout='next' with real fixture events: the _NextEventWidget draws."""
    cfg = {
        "type": "calendar",
        "ics_url": _fixture_url(),
        "layout": "next",
        "timezone": "UTC",
    }
    errors = Calendar.validate_config(cfg)
    assert errors == []
    _check_accepted(cfg, tmp_path)


def test_accepted_empty_window_draws_without_crash(tmp_path):
    """Accepted config with no in-window events: empty_text story draws."""
    cfg = {
        "type": "calendar",
        "ics_url": _fixture_url(),
        "layout": "agenda",
        "timezone": "UTC",
        "lookahead_days": 1,
    }
    errors = Calendar.validate_config(cfg)
    assert errors == []

    build_cfg = {k: v for k, v in cfg.items() if k != "type"}
    cal = Calendar(session=None, **build_cfg)

    def _far_future(tz):
        from zoneinfo import ZoneInfo

        return datetime(
            2030, 1, 1, 0, 0, tzinfo=tz if tz is not None else ZoneInfo("UTC")
        )

    _now_patch = "led_ticker.widgets.calendar._now_in"
    with patch(_now_patch, side_effect=_far_future):
        asyncio.run(cal.update())

    canvas = Mock()
    canvas.width = 160
    canvas.height = 16
    for story in cal.feed_stories:
        with patch(_now_patch, side_effect=_far_future):
            story.draw(canvas)


def test_accepted_highlight_color_rgb_does_not_crash(tmp_path):
    """A valid [r,g,b] highlight_color accepted config draws without crash."""
    cfg = {
        "type": "calendar",
        "ics_url": _fixture_url(),
        "layout": "next",
        "timezone": "UTC",
        "highlight": ["Standup"],
        "highlight_color": [0, 255, 0],
    }
    errors = Calendar.validate_config(cfg)
    assert errors == []
    _check_accepted(cfg, tmp_path)
