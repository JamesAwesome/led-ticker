"""_expand_sources drops widgets that opt out of a pass via should_display()."""

from datetime import date, timedelta
from typing import cast

from led_ticker.schedule import (
    VisibilitySchedule,
    bind_schedule,
    parse_visibility_schedule,
)
from led_ticker.ticker import _expand_sources
from led_ticker.widgets.count import TickerCountdown, TickerCountup


class _Plain:
    """A widget with no should_display() — always shown."""


class _Hidden:
    def should_display(self):
        return False


class _Shown:
    def should_display(self):
        return True


def test_widget_without_should_display_is_kept():
    w = _Plain()
    assert _expand_sources([w]) == [w]


def test_should_display_false_is_dropped():
    assert _expand_sources([_Hidden()]) == []


def test_should_display_true_is_kept():
    w = _Shown()
    assert _expand_sources([w]) == [w]


def test_out_of_range_countdown_is_dropped():
    # Behavior change: a countdown past its date now disappears (was: rendered -N).
    past = TickerCountdown("X", countdown_date=date.today() - timedelta(days=1))
    assert _expand_sources([past]) == []


def test_in_range_countup_is_kept():
    cu = TickerCountup("X", countup_date=date.today() - timedelta(days=1))
    assert _expand_sources([cu]) == [cu]


def test_should_display_raising_keeps_widget():
    class _Boom:
        def should_display(self):
            raise RuntimeError("boom")

    w = _Boom()
    # A visibility check must never crash the render loop or silently hide content.
    assert _expand_sources([w]) == [w]


def _always():
    # 00:00–23:59 every day: active at any test runtime except exactly 23:59.
    return parse_visibility_schedule({"start": "00:00", "end": "23:59"}, location="t")


class _FakeSchedInactive:
    def is_active(self):
        return False


class _FakeSchedBoom:
    def is_active(self):
        raise RuntimeError("boom")


class _Container:
    """Satisfies the Container protocol structurally (has feed_stories)."""

    def __init__(self, stories):
        self.feed_stories = stories

    async def update(self):  # pragma: no cover - protocol completeness
        pass


class TestScheduleGate:
    def test_widget_without_binding_is_kept(self):
        w = _Plain()
        assert _expand_sources([w]) == [w]

    def test_active_schedule_is_kept(self):
        w = _Plain()
        bind_schedule(w, _always())
        assert _expand_sources([w]) == [w]

    def test_inactive_schedule_is_dropped(self):
        w = _Plain()
        bind_schedule(w, cast(VisibilitySchedule, _FakeSchedInactive()))
        assert _expand_sources([w]) == []

    def test_raising_schedule_keeps_widget(self):
        # Same contract as should_display: a check that raises must never
        # crash the render loop or silently hide content.
        w = _Plain()
        bind_schedule(w, cast(VisibilitySchedule, _FakeSchedBoom()))
        assert _expand_sources([w]) == [w]

    def test_schedule_ands_with_should_display(self):
        # Inactive schedule hides even when should_display() says show...
        w1 = _Shown()
        bind_schedule(w1, cast(VisibilitySchedule, _FakeSchedInactive()))
        assert _expand_sources([w1]) == []
        # ...and should_display() False hides even inside the window.
        w2 = _Hidden()
        bind_schedule(w2, _always())
        assert _expand_sources([w2]) == []

    def test_container_is_gated_before_expansion(self):
        story = _Plain()
        c = _Container([story])
        bind_schedule(c, cast(VisibilitySchedule, _FakeSchedInactive()))
        assert _expand_sources([c]) == []

    def test_container_with_active_schedule_expands(self):
        story = _Plain()
        c = _Container([story])
        bind_schedule(c, _always())
        assert _expand_sources([c]) == [story]
