"""countup/countdown shared-base widgets: _days math, should_display, render."""

from datetime import date, datetime, timedelta

import pytest

from led_ticker.widgets.count import TickerCountdown, TickerCountup


def _future(days=10):
    return date.today() + timedelta(days=days)


def _past(days=10):
    return date.today() - timedelta(days=days)


def test_countdown_days_positive_for_future():
    assert TickerCountdown("Launch", countdown_date=_future(5))._days() == 5


def test_countdown_days_zero_today():
    assert TickerCountdown("Launch", countdown_date=date.today())._days() == 0


def test_countdown_days_negative_for_past():
    assert TickerCountdown("Launch", countdown_date=_past(3))._days() == -3


def test_countup_days_positive_for_past():
    assert TickerCountup("Since", countup_date=_past(7))._days() == 7


def test_countup_days_zero_today():
    assert TickerCountup("Since", countup_date=date.today())._days() == 0


def test_countup_days_negative_for_future():
    assert TickerCountup("Since", countup_date=_future(4))._days() == -4


def test_should_display_in_range_true():
    assert TickerCountdown("X", countdown_date=_future(1)).should_display() is True
    assert TickerCountup("X", countup_date=_past(1)).should_display() is True


def test_should_display_out_of_range_false():
    assert TickerCountdown("X", countdown_date=_past(1)).should_display() is False
    assert TickerCountup("X", countup_date=_future(1)).should_display() is False


def test_countup_renders_label_and_count(canvas):
    # The `canvas` fixture (tests/conftest.py:45) is the test stub canvas that
    # writes real pixels; draw() returns the same canvas + an advanced cursor.
    w = TickerCountup("Days", countup_date=_past(42))
    result_canvas, cursor = w.draw(canvas, 0)
    assert result_canvas is canvas
    assert cursor > 0


def test_registered_names():
    from led_ticker.widgets import get_widget_class

    assert get_widget_class("countdown") is TickerCountdown
    assert get_widget_class("countup") is TickerCountup


def test_back_compat_countdown_import():
    # The move must not break the historical import path.
    from led_ticker.widgets.message import TickerCountdown as FromMessage

    assert FromMessage is TickerCountdown


def test_countup_future_date_warns():
    cfg = {"countup_date": _future(5), "text": "X"}
    msgs = TickerCountup.validate_config_warnings(cfg, None)
    assert len(msgs) == 1 and "future" in msgs[0]


def test_countup_past_date_no_warning():
    cfg = {"countup_date": _past(5), "text": "X"}
    assert TickerCountup.validate_config_warnings(cfg, None) == []


def test_countdown_past_date_warns():
    cfg = {"countdown_date": _past(5), "text": "X"}
    msgs = TickerCountdown.validate_config_warnings(cfg, None)
    assert len(msgs) == 1 and "past" in msgs[0]


def test_countdown_future_date_no_warning():
    cfg = {"countdown_date": _future(5), "text": "X"}
    assert TickerCountdown.validate_config_warnings(cfg, None) == []


def test_wrong_side_warning_ignores_missing_or_nondate():
    assert TickerCountup.validate_config_warnings({"text": "X"}, None) == []
    assert (
        TickerCountdown.validate_config_warnings({"countdown_date": "nope"}, None) == []
    )


def test_timezone_default_matches_local_today():
    w = TickerCountup("X", countup_date=_past(5))
    assert w._today() == date.today()


def test_timezone_field_used_for_today():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    w = TickerCountup("X", countup_date=_past(5), timezone="UTC")
    assert w._today() == datetime.now(ZoneInfo("UTC")).date()


def test_validate_config_accepts_valid_timezone():
    # valid date included so these isolate the timezone check
    assert (
        TickerCountup.validate_config(
            {"timezone": "America/New_York", "countup_date": "2000-01-01"}
        )
        == []
    )
    assert (
        TickerCountdown.validate_config(
            {"timezone": "UTC", "countdown_date": "2099-01-01"}
        )
        == []
    )


def test_validate_config_no_timezone_ok():
    assert (
        TickerCountup.validate_config({"text": "X", "countup_date": "2000-01-01"}) == []
    )


def test_validate_config_rejects_bad_timezone():
    msgs = TickerCountup.validate_config(
        {"timezone": "Not/AZone", "countup_date": "2000-01-01"}
    )
    assert len(msgs) == 1 and "valid IANA" in msgs[0]


def test_validate_config_rejects_nonstring_timezone():
    # include a valid date so this isolates the timezone error (the date check
    # is exercised separately in test_count_validation.py)
    msgs = TickerCountdown.validate_config(
        {"timezone": 5, "countdown_date": "2099-01-01"}
    )
    assert len(msgs) == 1 and "string" in msgs[0]


# --- date coercion (str / datetime / native date) — the smoke-test crash ---


def test_countdown_accepts_iso_string_date():
    w = TickerCountdown("Launch", countdown_date="2099-01-01")
    assert w.countdown_date == date(2099, 1, 1)
    assert w._days() > 0  # the original crash path: str date through _days()


def test_countup_accepts_iso_string_date():
    w = TickerCountup("Since", countup_date="2000-01-01")
    assert w.countup_date == date(2000, 1, 1)
    assert w._days() > 0


def test_string_date_days_math_matches_native():
    target = _future(10)
    assert (
        TickerCountdown("L", countdown_date=target.isoformat())._days()
        == TickerCountdown("L", countdown_date=target)._days()
        == 10
    )


def test_countdown_datetime_coerced_to_date():
    w = TickerCountdown("Launch", countdown_date=datetime(2099, 1, 1, 13, 30))
    assert w.countdown_date == date(2099, 1, 1)


def test_countdown_bad_string_raises_at_construction():
    with pytest.raises(ValueError):
        TickerCountdown("Launch", countdown_date="not-a-date")


def test_countup_bad_type_raises_at_construction():
    with pytest.raises(TypeError):
        TickerCountup("Since", countup_date=20270101)
