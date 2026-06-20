"""Engine-level tests for the widget render circuit breaker.

Covers all three display modes (swap / forever / infini). In each mode,
a FaultyDrawWidget whose draw() always raises must NOT propagate the
exception — the run completes normally, the breaker is tripped, and the
widget is filtered from subsequent rotation passes.
"""

import asyncio

from led_ticker.render_breaker import RenderBreaker
from led_ticker.ticker import Ticker, _expand_sources
from led_ticker.widgets.message import TickerMessage


class FaultyDrawWidget:
    """A widget whose draw() always raises (no play())."""

    bg_color = None

    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        raise ValueError("boom-draw")


def _make_message_widget(text: str) -> TickerMessage:
    """Create a minimal TickerMessage that draws successfully."""
    return TickerMessage(text=text, hold_time=0.0)


def _make_ticker(monitors, frame, breaker: RenderBreaker, **kwargs) -> Ticker:
    """Create a Ticker with a fresh queue and the given breaker."""
    q: asyncio.Queue = asyncio.Queue()
    return Ticker(
        monitors=monitors,
        frame=frame,
        notif_queue=q,
        scroll_speed=0,
        hold_time=0.0,
        breaker=breaker,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Unit test: _expand_sources filters disabled widgets
# ---------------------------------------------------------------------------


def test_expand_sources_filters_disabled():
    b = RenderBreaker()
    good, bad = object(), object()
    b.trip(bad, ValueError("x"))
    assert _expand_sources([good, bad], breaker=b) == [good]


def test_expand_sources_passes_through_without_breaker():
    good, bad = object(), object()
    result = _expand_sources([good, bad])
    assert result == [good, bad]


def test_expand_sources_filters_disabled_stories_in_container():
    """Container stories that are disabled must also be filtered."""
    from unittest.mock import Mock

    from led_ticker.widget import Container

    class _FakeContainer(Container):
        def __init__(self, stories):
            self.feed_stories = stories

    b = RenderBreaker()
    story_good = Mock()
    story_bad = Mock()
    b.trip(story_bad, ValueError("x"))

    container = _FakeContainer([story_good, story_bad])
    # sanity: isinstance gate in _expand_sources fires
    assert isinstance(container, Container)

    result = _expand_sources([container], breaker=b)
    assert story_good in result
    assert story_bad not in result


# ---------------------------------------------------------------------------
# swap mode
# ---------------------------------------------------------------------------


async def test_swap_mode_survives_faulty_draw(swapping_frame, no_sleep):
    """A faulty widget must not raise — the run completes and the breaker trips."""
    good = _make_message_widget("hello")
    bad = FaultyDrawWidget()
    breaker = RenderBreaker()
    ticker = _make_ticker(monitors=[bad, good], frame=swapping_frame, breaker=breaker)
    # Must not raise:
    await ticker.run_swap(loop_count=1)
    assert breaker.is_disabled(bad) is True
    # Disabled widget is filtered from the rotation next pass:
    assert _expand_sources([bad, good], breaker=breaker) == [good]


# ---------------------------------------------------------------------------
# forever scroll mode
# ---------------------------------------------------------------------------


async def test_forever_scroll_survives_faulty_draw(swapping_frame, no_sleep):
    """forever_scroll (_scroll_side_by_side) must absorb a faulty draw."""
    good = _make_message_widget("hello")
    bad = FaultyDrawWidget()
    breaker = RenderBreaker()
    ticker = _make_ticker(monitors=[bad, good], frame=swapping_frame, breaker=breaker)
    await ticker.run_forever_scroll(loop_count=1)
    assert breaker.is_disabled(bad) is True
    # Disabled widget is filtered from the rotation next pass:
    assert _expand_sources([bad, good], breaker=breaker) == [good]


async def test_forever_scroll_second_widget_fails(swapping_frame, no_sleep):
    """In forever_scroll, the SECOND widget faulting must not break the loop.

    The run completes, the breaker trips the bad widget, and a good sibling
    still rendered (run did not raise).
    """
    good = _make_message_widget("hello")
    bad = FaultyDrawWidget()
    good2 = _make_message_widget("world")
    breaker = RenderBreaker()
    ticker = _make_ticker(
        monitors=[good, bad, good2], frame=swapping_frame, breaker=breaker
    )
    # Must not raise:
    await ticker.run_forever_scroll(loop_count=1)
    assert breaker.is_disabled(bad) is True
    # Good siblings are not tripped:
    assert not breaker.is_disabled(good)
    assert not breaker.is_disabled(good2)
    # Filtered from next pass:
    assert _expand_sources([good, bad, good2], breaker=breaker) == [good, good2]


# ---------------------------------------------------------------------------
# infini scroll mode
# ---------------------------------------------------------------------------


async def test_infini_scroll_survives_faulty_draw(swapping_frame, no_sleep):
    """infini_scroll (_scroll_one_by_one) must absorb a faulty draw."""
    good = _make_message_widget("hello")
    bad = FaultyDrawWidget()
    breaker = RenderBreaker()
    ticker = _make_ticker(monitors=[bad, good], frame=swapping_frame, breaker=breaker)
    await ticker.run_infini_scroll(loop_count=1)
    assert breaker.is_disabled(bad) is True
    # Disabled widget is filtered from the rotation next pass:
    assert _expand_sources([bad, good], breaker=breaker) == [good]


# ---------------------------------------------------------------------------
# _safe_draw unit tests
# ---------------------------------------------------------------------------


async def test_safe_draw_returns_canvas_unchanged_on_error(swapping_frame):
    """On draw error: canvas is returned as-is (no Clear), cursor_pos unchanged."""
    canvas = swapping_frame.get_clean_canvas()
    bad = FaultyDrawWidget()
    breaker = RenderBreaker()
    ticker = _make_ticker(monitors=[], frame=swapping_frame, breaker=breaker)

    result_canvas, result_pos = ticker._safe_draw(bad, canvas, cursor_pos=42)
    assert result_canvas is canvas
    assert result_pos == 42
    assert breaker.is_disabled(bad) is True


async def test_safe_draw_short_circuits_when_already_disabled(swapping_frame):
    """Already-disabled widget must NOT have draw() called at all."""
    canvas = swapping_frame.get_clean_canvas()
    bad = FaultyDrawWidget()
    breaker = RenderBreaker()
    # Pre-trip the widget
    breaker.trip(bad, ValueError("already broken"))

    call_count = 0
    original_draw = bad.draw

    def _counting_draw(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original_draw(*args, **kwargs)

    bad.draw = _counting_draw  # type: ignore[method-assign]

    ticker = _make_ticker(monitors=[], frame=swapping_frame, breaker=breaker)
    result_canvas, result_pos = ticker._safe_draw(bad, canvas, cursor_pos=7)
    assert call_count == 0, "_safe_draw must not call draw() on a pre-tripped widget"
    assert result_canvas is canvas
    assert result_pos == 7


async def test_safe_draw_passthrough_on_success(swapping_frame):
    """A working widget's draw() result is passed through unchanged."""
    canvas = swapping_frame.get_clean_canvas()
    good = _make_message_widget("hi")
    breaker = RenderBreaker()
    ticker = _make_ticker(monitors=[], frame=swapping_frame, breaker=breaker)

    result_canvas, result_pos = ticker._safe_draw(good, canvas, cursor_pos=0)
    # draw() returns (canvas, cursor_pos + text_width) — just verify not tripped
    assert not breaker.is_disabled(good)
    assert result_canvas is not None
