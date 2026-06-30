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


class RecordingWidget:
    """A good widget that records the canvas id each draw() call receives.

    Used to assert constraint #1: the engine captures SwapOnVSync's return
    value and passes the NEW back-buffer to each subsequent draw call.
    """

    bg_color = None

    def __init__(self, text="hello"):
        self.text = text
        self.seen: list[int] = []

    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        self.seen.append(id(canvas))
        return canvas, 0


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
    # check: isinstance gate in _expand_sources fires
    assert isinstance(container, Container)

    result = _expand_sources([container], breaker=b)
    assert story_good in result
    assert story_bad not in result


# ---------------------------------------------------------------------------
# swap mode
# ---------------------------------------------------------------------------


async def test_swap_mode_survives_faulty_draw(swapping_frame, no_sleep):
    """A faulty widget must not raise — the run completes and the breaker trips.

    Also asserts constraint #1: the engine captures SwapOnVSync's return value
    and hands the fresh back-buffer to the good sibling widget on each draw call.
    The swapping_frame fixture rotates between two distinct canvas objects, so
    seeing >= 2 distinct canvas ids proves the engine kept capturing the swap.
    """
    good = RecordingWidget("hello")
    bad = FaultyDrawWidget()
    breaker = RenderBreaker()
    ticker = _make_ticker(monitors=[bad, good], frame=swapping_frame, breaker=breaker)
    # Must not raise:
    await ticker.run_slideshow(loop_count=1)
    assert breaker.is_disabled(bad) is True
    # Disabled widget is filtered from the rotation next pass:
    assert _expand_sources([bad, good], breaker=breaker) == [good]
    # Constraint #1: engine must have captured SwapOnVSync return value — good
    # widget must have seen >= 2 distinct canvas objects across its draw calls.
    assert len(set(good.seen)) >= 2, (
        "Engine dropped SwapOnVSync return value: good widget only saw "
        f"{len(set(good.seen))} distinct canvas id(s) across {len(good.seen)} draw(s)"
    )


# ---------------------------------------------------------------------------
# forever scroll mode
# ---------------------------------------------------------------------------


async def test_ticker_survives_faulty_draw(swapping_frame, no_sleep):
    """ticker (_scroll_side_by_side) must absorb a faulty draw."""
    good = _make_message_widget("hello")
    bad = FaultyDrawWidget()
    breaker = RenderBreaker()
    ticker = _make_ticker(monitors=[bad, good], frame=swapping_frame, breaker=breaker)
    await ticker.run_ticker(loop_count=1)
    assert breaker.is_disabled(bad) is True
    # Disabled widget is filtered from the rotation next pass:
    assert _expand_sources([bad, good], breaker=breaker) == [good]


async def test_ticker_second_widget_fails(swapping_frame, no_sleep):
    """In ticker, the SECOND widget faulting must not break the loop.

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
    await ticker.run_ticker(loop_count=1)
    assert breaker.is_disabled(bad) is True
    # Good siblings are not tripped:
    assert not breaker.is_disabled(good)
    assert not breaker.is_disabled(good2)
    # Filtered from next pass:
    assert _expand_sources([good, bad, good2], breaker=breaker) == [good, good2]


# ---------------------------------------------------------------------------
# infini scroll mode
# ---------------------------------------------------------------------------


async def test_one_at_a_time_survives_faulty_draw(swapping_frame, no_sleep):
    """one_at_a_time (_scroll_one_by_one) must absorb a faulty draw."""
    good = _make_message_widget("hello")
    bad = FaultyDrawWidget()
    breaker = RenderBreaker()
    ticker = _make_ticker(monitors=[bad, good], frame=swapping_frame, breaker=breaker)
    await ticker.run_one_at_a_time(loop_count=1)
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


# ---------------------------------------------------------------------------
# play()-style widget circuit breaker tests
# ---------------------------------------------------------------------------


class FaultyPlayWidget:
    """A play()-style widget whose play() always raises."""

    bg_color = None
    play_count = 1

    def __init__(self):
        self.calls = 0

    async def play(self, canvas, frame, loop_count=1, hold_time=3.0):
        self.calls += 1
        raise ValueError("boom-play")


async def test_play_widget_survives_faulty_play(mock_frame):
    bad = FaultyPlayWidget()
    breaker = RenderBreaker()
    ticker = _make_ticker(monitors=[bad], frame=mock_frame, breaker=breaker)
    canvas = mock_frame.matrix.CreateFrameCanvas()
    # _play_widget must not raise and must return a valid canvas
    out = await ticker._play_widget(canvas, bad, section_hold_time=0.05)
    assert out is not None
    assert breaker.is_disabled(bad) is True


async def test_disabled_play_widget_short_circuits(mock_frame):
    bad = FaultyPlayWidget()
    breaker = RenderBreaker()
    breaker.trip(bad, ValueError("pre"))  # already disabled
    ticker = _make_ticker(monitors=[bad], frame=mock_frame, breaker=breaker)
    canvas = mock_frame.matrix.CreateFrameCanvas()
    # play() must NOT be called for an already-disabled widget (no raise either)
    out = await ticker._play_widget(canvas, bad, section_hold_time=0.05)
    assert out is canvas  # returned unchanged, play() skipped
    assert bad.calls == 0, "_play_widget must not call play() on a pre-tripped widget"


# ---------------------------------------------------------------------------
# Shared breaker injection (Task 5)
# ---------------------------------------------------------------------------


def test_shared_breaker_disables_across_tickers(mock_frame):
    # The whole point of injecting ONE breaker: a widget tripped while one
    # Ticker (section) renders stays disabled for the next Ticker.
    breaker = RenderBreaker()
    bad = FaultyDrawWidget()
    _make_ticker(monitors=[bad], frame=mock_frame, breaker=breaker)  # t1
    t2 = _make_ticker(monitors=[bad], frame=mock_frame, breaker=breaker)
    breaker.trip(bad, ValueError("x"))  # tripped during t1's run
    assert t2.breaker.is_disabled(bad) is True  # t2 sees it (same breaker)


def test_run_injects_a_shared_breaker():
    """RenderBreaker() must be constructed ONCE in run(), not inside a loop.

    Source-grep confirms the call exists; AST-parse confirms it's not nested
    inside any For or While loop node — so moving the construction into the
    per-section loop would fail this tripwire.
    """
    import ast
    import inspect
    import textwrap

    from led_ticker.app.run import run

    src = inspect.getsource(run)
    assert "RenderBreaker(" in src  # created in run()
    assert '"breaker"' in src or "breaker=" in src  # threaded into ticker_kwargs

    # Dedent so the AST parse starts at column 0 (getsource includes indentation).
    tree = ast.parse(textwrap.dedent(src))

    # Walk every For/While loop in the function body and assert none of them
    # contain a RenderBreaker() call — that would mean it's re-created per section.
    loop_types = (ast.For, ast.AsyncFor, ast.While)
    for node in ast.walk(tree):
        if isinstance(node, loop_types):
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func = child.func
                    name = (
                        func.id
                        if isinstance(func, ast.Name)
                        else getattr(func, "attr", None)
                    )
                    assert name != "RenderBreaker", (
                        "RenderBreaker() must not be constructed inside a loop "
                        "in run() — it must be created once and shared across "
                        "all sections/tickers."
                    )


# ---------------------------------------------------------------------------
# FIX 1 regression: _expand_sources at transition selection sites
# ---------------------------------------------------------------------------


def test_expand_sources_filters_tripped_widget_at_start():
    """A tripped widget in first position must be excluded."""
    b = RenderBreaker()
    good = object()
    bad = object()
    b.trip(bad, ValueError("x"))
    assert _expand_sources([bad, good], breaker=b) == [good]


def test_expand_sources_filters_tripped_widget_at_end():
    """A tripped widget in last position must be excluded."""
    b = RenderBreaker()
    good = object()
    bad = object()
    b.trip(bad, ValueError("x"))
    assert _expand_sources([good, bad], breaker=b) == [good]


def test_expand_sources_all_tripped_returns_empty():
    """When the only widget is tripped, result must be empty (not raise)."""
    b = RenderBreaker()
    bad = object()
    b.trip(bad, ValueError("x"))
    assert _expand_sources([bad], breaker=b) == []
