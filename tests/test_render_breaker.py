import logging
from types import SimpleNamespace

from led_ticker.render_breaker import RenderBreaker


def test_trip_disables_and_records_summary():
    b = RenderBreaker()
    w = SimpleNamespace()
    assert b.is_disabled(w) is False
    b.trip(w, ValueError("boom"))
    assert b.is_disabled(w) is True
    assert b.disabled[id(w)] == "ValueError: boom"


def test_trip_logs_error_once(caplog):
    b = RenderBreaker()
    w = SimpleNamespace()
    with caplog.at_level(logging.ERROR):
        b.trip(w, ValueError("boom"))
        b.trip(w, ValueError("again"))  # second trip is a no-op
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1  # logged once, not per-call
    assert b.disabled[id(w)] == "ValueError: boom"  # first summary kept


def test_distinct_widgets_tracked_independently():
    b = RenderBreaker()
    w1, w2 = SimpleNamespace(), SimpleNamespace()
    b.trip(w1, KeyError("x"))
    assert b.is_disabled(w1) is True
    assert b.is_disabled(w2) is False
