import logging
from types import SimpleNamespace

from led_ticker.render_breaker import RenderBreaker, _key


def test_trip_disables_and_records_summary():
    b = RenderBreaker()
    w = SimpleNamespace()
    assert b.is_disabled(w) is False
    b.trip(w, ValueError("boom"))
    assert b.is_disabled(w) is True
    # content-less object keys by id; verify the entry is stored
    assert b.disabled[_key(w)] == "ValueError: boom"


def test_trip_logs_error_once(caplog):
    b = RenderBreaker()
    w = SimpleNamespace()
    with caplog.at_level(logging.ERROR):
        b.trip(w, ValueError("boom"))
        b.trip(w, ValueError("again"))  # second trip is a no-op
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1  # logged once, not per-call
    assert b.disabled[_key(w)] == "ValueError: boom"  # first summary kept


def test_distinct_content_less_widgets_tracked_independently():
    b = RenderBreaker()
    w1, w2 = SimpleNamespace(), SimpleNamespace()
    b.trip(w1, KeyError("x"))
    assert b.is_disabled(w1) is True
    assert b.is_disabled(w2) is False


# ---------------------------------------------------------------------------
# Content-signature keying (FIX 2): container story case
# ---------------------------------------------------------------------------


class _Story:
    """Minimal story object with a text field (container-story pattern)."""

    def __init__(self, text: str) -> None:
        self.text = text


def test_content_key_two_same_content_objects_share_disabled_state():
    """Tripping one object disables ANY distinct object with the same content
    signature — this is the container-story case where stories are rebuilt as
    NEW objects each refresh cycle."""
    b = RenderBreaker()
    a = _Story("Headline A")
    b_obj = _Story("Headline A")  # distinct object, same content
    assert a is not b_obj  # genuinely different objects
    b.trip(a, ValueError("bad"))
    # The OTHER object with identical (type, text) must be seen as disabled.
    assert b.is_disabled(b_obj) is True, (
        "Content-signature keying must treat two objects with the same "
        "(type, text) as the same breaker entry"
    )


def test_content_key_trip_second_is_noop_logs_once(caplog):
    """When the key is already disabled, tripping a distinct same-content object
    must be a no-op (log once total, not twice)."""
    b = RenderBreaker()
    a = _Story("Headline B")
    b_obj = _Story("Headline B")
    with caplog.at_level(logging.ERROR):
        b.trip(a, ValueError("first"))
        b.trip(b_obj, ValueError("second"))  # same key — no-op
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1


def test_content_key_different_texts_tracked_independently():
    """Different content → different keys → tracked independently."""
    b = RenderBreaker()
    a = _Story("Story One")
    c = _Story("Story Two")
    b.trip(a, ValueError("x"))
    assert b.is_disabled(a) is True
    assert b.is_disabled(c) is False


def test_content_less_objects_key_by_id():
    """Objects without text/top_text/path fall back to id() — two distinct
    content-less objects must be tracked independently."""
    b = RenderBreaker()

    class _NoContent:
        pass

    w1 = _NoContent()
    w2 = _NoContent()
    assert _key(w1) == id(w1)
    assert _key(w2) == id(w2)
    b.trip(w1, ValueError("x"))
    assert b.is_disabled(w1) is True
    assert b.is_disabled(w2) is False


def test_reset_clears_disabled():
    from types import SimpleNamespace

    b = RenderBreaker()
    w = SimpleNamespace(text="hi")
    b.trip(w, ValueError("boom"))
    assert b.is_disabled(w) is True
    b.reset()
    assert b.is_disabled(w) is False
    assert b.disabled == {}


# ---------------------------------------------------------------------------
# _TransitionDrawGuard + guard_for_transition tests
# ---------------------------------------------------------------------------


def test_guard_for_transition_passthrough_without_breaker():
    from types import SimpleNamespace

    from led_ticker.render_breaker import guard_for_transition

    w = SimpleNamespace(text="hi")
    assert guard_for_transition(w, None) is w  # no breaker -> raw widget


def test_guard_draws_through_on_success():
    from led_ticker.render_breaker import RenderBreaker, guard_for_transition

    class W:
        text = "ok"

        def draw(self, canvas, cursor_pos=0, **kw):
            return ("DREW", cursor_pos)

    g = guard_for_transition(W(), RenderBreaker())
    assert g.draw("CANVAS", cursor_pos=7) == ("DREW", 7)


def test_guard_traps_raise_trips_and_returns_canvas():
    from led_ticker.render_breaker import RenderBreaker, guard_for_transition

    class Boom:
        text = "boom"

        def draw(self, canvas, cursor_pos=0, **kw):
            raise ValueError("kaboom")

    b = RenderBreaker()
    w = Boom()
    g = guard_for_transition(w, b)
    out = g.draw("CANVAS", cursor_pos=3)  # must NOT raise
    assert out == ("CANVAS", 0)  # canvas unchanged, pos 0
    assert b.is_disabled(w) is True  # tripped


def test_guard_short_circuits_disabled_without_calling_draw():
    from led_ticker.render_breaker import RenderBreaker, guard_for_transition

    class Counting:
        text = "x"

        def __init__(self):
            self.calls = 0

        def draw(self, canvas, cursor_pos=0, **kw):
            self.calls += 1
            return ("DREW", cursor_pos)

    b = RenderBreaker()
    w = Counting()
    b.trip(w, ValueError("pre"))  # already disabled
    g = guard_for_transition(w, b)
    out = g.draw("CANVAS", cursor_pos=5)
    assert out == ("CANVAS", 0)
    assert w.calls == 0  # draw NOT called


def test_guard_delegates_other_attrs():
    from types import SimpleNamespace

    from led_ticker.render_breaker import RenderBreaker, guard_for_transition

    w = SimpleNamespace(text="hi", bg_color=(1, 2, 3))
    g = guard_for_transition(w, RenderBreaker())
    assert g.bg_color == (1, 2, 3)  # __getattr__ delegates
    assert g.text == "hi"
