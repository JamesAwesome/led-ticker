"""Core-owned `schedule` field: popped at dispatch, bound to the built widget,
reserved against widget classes that try to declare it."""

import asyncio
from unittest import mock

import attrs
import pytest

from led_ticker.app.factories import _build_widget, _cache_key, validate_widget_cfg
from led_ticker.schedule import schedule_for
from led_ticker.widgets import _WIDGET_REGISTRY

SCHED = {"start": "09:00", "end": "17:00", "days": ["mon"]}


def test_built_widget_is_bound_and_constructor_never_sees_schedule():
    widget = asyncio.run(
        _build_widget(
            {"type": "message", "text": "hi", "schedule": dict(SCHED)},
            mock.Mock(),
        )
    )
    s = schedule_for(widget)
    assert s is not None
    assert s.window.start == 9 * 60
    assert s.window.days == frozenset({0})
    # attrs would have raised on an unknown kwarg; belt-and-suspenders:
    assert not hasattr(widget, "schedule")


def test_widget_without_schedule_is_unbound():
    widget = asyncio.run(_build_widget({"type": "message", "text": "hi"}, mock.Mock()))
    assert schedule_for(widget) is None


def test_malformed_schedule_raises_at_validate():
    with pytest.raises(ValueError, match="not a valid 24h HH:MM"):
        asyncio.run(
            validate_widget_cfg(
                {
                    "type": "message",
                    "text": "hi",
                    "schedule": {"start": "9am", "end": "17:00"},
                },
                session=None,
            )
        )


def test_validate_pops_schedule():
    cfg = {"type": "message", "text": "hi", "schedule": dict(SCHED)}
    asyncio.run(validate_widget_cfg(cfg, session=None))
    assert "schedule" not in cfg


def test_widget_class_declaring_schedule_is_rejected(monkeypatch):
    @attrs.define
    class _SchedWidget:
        schedule: str = ""

    monkeypatch.setitem(_WIDGET_REGISTRY, "_sched_test", _SchedWidget)
    with pytest.raises(ValueError, match="reserved by the core engine"):
        asyncio.run(validate_widget_cfg({"type": "_sched_test"}, session=None))


def test_cache_key_includes_schedule():
    base = {"type": "message", "text": "hi"}
    a = {**base, "schedule": {"start": "09:00", "end": "17:00"}}
    b = {**base, "schedule": {"start": "10:00", "end": "17:00"}}
    assert _cache_key(a) != _cache_key(b)
    assert _cache_key(base) != _cache_key(a)
