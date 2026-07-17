"""Producer backpressure (#394): the notif queue is bounded so gate
evaluation in _build_ticker_iter's per-pass expansion tracks DISPLAY time
instead of running unboundedly ahead at enqueue time."""

import asyncio
import itertools

import pytest

from led_ticker.render_breaker import RenderBreaker
from led_ticker.ticker import (
    TICKER_QUEUE_MAXSIZE,
    Ticker,
    _enqueue_ticker_objects,
)


def test_maxsize_constant():
    assert TICKER_QUEUE_MAXSIZE == 2


def test_run_loop_constructs_bounded_queue():
    """Source tripwire (house AST-tripwire style): the run loop's queue
    construction must pass maxsize=TICKER_QUEUE_MAXSIZE — the behavior
    tests below build their own queues, so this is the pin that the REAL
    wiring is bounded. A bare `asyncio.Queue()` reintroduces #394."""
    import inspect

    from led_ticker.app import run as run_mod

    src = inspect.getsource(run_mod)
    assert "maxsize=TICKER_QUEUE_MAXSIZE" in src
    assert "notif_queue: asyncio.Queue[Any] = asyncio.Queue()" not in src


async def _drain_n(queue, n, per_item_delay=0.01):
    got = []
    for _ in range(n):
        item = await queue.get()
        got.append(item)
        await asyncio.sleep(per_item_delay)
    return got


@pytest.mark.asyncio
async def test_queue_depth_never_exceeds_maxsize():
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(
        _enqueue_ticker_objects(itertools.count(), queue)  # infinite iterator
    )
    try:
        max_seen = 0
        for _ in range(20):
            await asyncio.sleep(0.005)
            max_seen = max(max_seen, queue.qsize())
            if not queue.empty():
                queue.get_nowait()
        assert max_seen <= TICKER_QUEUE_MAXSIZE
    finally:
        producer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await producer


@pytest.mark.asyncio
async def test_sentinel_arrives_last_on_finite_iterator():
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(
        _enqueue_ticker_objects(iter([1, 2, 3, 4, 5]), queue)
    )
    got = await _drain_n(queue, 6)
    await producer
    assert got == [1, 2, 3, 4, 5, None]


@pytest.mark.asyncio
async def test_cancel_while_parked_in_put_unwinds_cleanly():
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(_enqueue_ticker_objects(itertools.count(), queue))
    await asyncio.sleep(0.01)  # producer fills the queue and parks in put()
    assert queue.full()
    producer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(producer, timeout=1.0)  # no hang


@pytest.mark.asyncio
async def test_gating_tracks_display_time():
    """The #394 headline: a visibility flip mid-'section' reaches the
    consumer within maxsize+1 items, instead of being buried behind an
    unbounded backlog of pre-gated items."""

    class _FlippingWidget:
        def __init__(self):
            self.visible = True

        def should_display(self):
            return self.visible

    w = _FlippingWidget()

    def passes():
        # Mimics _build_ticker_iter's cycle_with_refresh: re-evaluate the
        # gate every pass, stop yielding when it goes false.
        from led_ticker.ticker import _expand_sources

        while True:
            widgets = _expand_sources([w])
            if not widgets:
                return
            yield from widgets

    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(_enqueue_ticker_objects(passes(), queue))
    # Consume 3 items, then flip the widget invisible.
    await _drain_n(queue, 3)
    w.visible = False
    # The sentinel must arrive within maxsize+2 further gets. asyncio.Queue's
    # put() only suspends once the queue is actually full — it never yields
    # when space exists — so the producer is always one item further ahead
    # than what's queued: up to `maxsize` items sitting in the queue plus
    # exactly one more already gated and blocked in an in-flight put(). That
    # whole backlog (maxsize + 1 stale items, all gated before the flip)
    # must drain before the *next* evaluation — the first one to see the
    # flip — can even run, let alone be retrieved.
    tail = await asyncio.wait_for(
        _drain_n(queue, TICKER_QUEUE_MAXSIZE + 2), timeout=2.0
    )
    await producer
    assert None in tail


@pytest.mark.asyncio
async def test_run_swap_drain_loop_terminates_with_parked_producer():
    """Pin the general event-loop fact behind the Task 2 fix directly: a
    producer parked in `put()` CANNOT refill a synchronous, no-await
    drain — its waiter only resolves at the next event-loop yield.

    This is exactly why `_run_swap`'s tail loop (~ticker.py:798) now
    inserts `await asyncio.sleep(0)` before every `.empty()` check
    (see `test_run_swap_play_widgets_do_not_strand_trailing_widgets`
    below): without a yield, two adjacent suspension-free widget-visits
    (a play()-dispatched widget short-circuited by the breaker, or one
    whose `play()` raises before its first `await`) can drain both
    queue slots exactly like this test's manual loop does, and strand
    whatever the producer had queued up behind them."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(_enqueue_ticker_objects(itertools.count(), queue))
    await asyncio.sleep(0.01)  # queue full, producer parked
    drained = []
    while not queue.empty():
        drained.append(queue.get_nowait())
    # Terminated with exactly the buffered items — the parked producer
    # could not sneak refills in synchronously.
    assert len(drained) == TICKER_QUEUE_MAXSIZE
    producer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await producer


@pytest.mark.asyncio
async def test_consumer_never_starves_when_producer_is_fast():
    """With a fast producer, every consumer get() should find an item
    already buffered (the producer keeps the 2-slot queue topped up) —
    the producer must not become the frame-rate limiter."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(_enqueue_ticker_objects(itertools.count(), queue))
    await asyncio.sleep(0.01)
    empty_at_get = 0
    for _ in range(50):
        if queue.empty():
            empty_at_get += 1
        await queue.get()
        await asyncio.sleep(0.001)  # consumer tick
    assert empty_at_get == 0
    producer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await producer


# --- Carry-forward from Task 1's review: does the "empty() means done"
# idiom in the three consumers survive the bounded queue, or can a
# transient empty() strand widgets that are still coming? ---
#
# Three call sites use (or used) the pattern:
#   _run_swap            (~ticker.py:798)  while not queue.empty(): get_nowait()
#   _scroll_one_by_one    (~ticker.py:952)  try: get_nowait() except QueueEmpty
#   _scroll_side_by_side  (~ticker.py:1053) if queue.empty(): queue_empty=True (sticky)
#
# Verdict per site, established empirically (drive the real producer +
# a real maxsize=2 queue through the real consumer, count draws) AND by
# tracing the event-loop scheduling that would have to hold for the
# empirical result to generalize beyond the specific widths/timings
# tested:
#
#   _run_swap:            Task 1 verdict ("SAFE, not fixed") covered only
#                         the `_swap_and_scroll` (non-play) path, where
#                         `_hold_ticks`'s `n_ticks = max(1, ...)` floor
#                         guarantees a real await per visit. Task 2's
#                         review (#394) found the verdict FALSE for the
#                         `play()` dispatch path: a breaker-disabled
#                         widget short-circuits `_play_widget` before any
#                         await, and a `play()` that raises before its
#                         first await never suspends either — two such
#                         widgets back-to-back can drain the queue with
#                         zero real suspensions. FIXED in Task 2 by
#                         yielding once per drain iteration — see
#                         test_run_swap_play_widgets_do_not_strand_
#                         trailing_widgets below.
#   _scroll_one_by_one:   SAFE, not fixed — see
#                         test_scroll_one_by_one_survives_degenerate_config
#                         below.
#   _scroll_side_by_side: WAS BROKEN, fixed in Task 1 — see
#                         test_scroll_side_by_side_does_not_drop_widgets_
#                         under_bounded_queue below.


@pytest.mark.asyncio
async def test_run_swap_survives_degenerate_config(mock_frame, make_widget, no_sleep):
    """CARRY-FORWARD regression (#394 Task 1 review): 5 widgets, hold_time=0
    (the engine's floor — see below), no transition configured (the plain
    `else` branch in `_run_swap`, i.e. an instant cut), driven through the
    REAL producer (`_build_then_enqueue`, spawned by `run_slideshow` itself)
    over a REAL bounded queue (`maxsize=TICKER_QUEUE_MAXSIZE`). All 5 must
    display, and the section must end only via the `None` sentinel.

    SCOPE: this suspension guarantee covers the `_swap_and_scroll`
    (non-play) path only — these 5 widgets are plain draw()-based mocks,
    which is exactly the shape `_show_one` routes there. It does NOT
    cover the `play()` dispatch path (`_play_widget`): a breaker-disabled
    widget short-circuits before calling `play()` at all, and a `play()`
    that raises before its first `await` never suspends either — both
    are genuine zero-suspension visits. Task 2's review (#394) found that
    edge and it's covered separately by
    `test_run_swap_play_widgets_do_not_strand_trailing_widgets` below,
    fixed by `_run_swap`'s tail loop now doing `await asyncio.sleep(0)`
    before every `.empty()` check (~ticker.py:798) — that explicit yield
    is the general-purpose version of the guarantee this test's `_swap_
    and_scroll` widgets get for free (see next paragraph).

    EARLY-EXIT VERDICT (this path): not exposed. Empirically confirmed
    (this test passes, and passes even harder under 30 widgets at
    `scroll_speed=0` — see the report for the exploratory numbers) and
    explained by the engine's own floor: `_show_one` -> `_swap_and_scroll`
    always runs `_hold_ticks` with `n_ticks = max(1, ...)`, so EVERY
    widget-visit contains at least one real `await asyncio.sleep(...)` —
    even at hold_time=0 the `max(1, ...)` floor still runs one tick. That
    single await is a genuine event-loop suspension point.

    Why one suspension is enough: `_run_swap`'s catch-up drain consumes
    exactly one item right before calling `_show_one`, freeing exactly one
    of the queue's 2 slots. `queue.get_nowait()` calls `_wakeup_next` on
    the producer's parked `put()` future via `loop.call_soon` — a callback
    enqueued on the loop's FIFO ready-queue *before* `_show_one`'s own
    sleep registers ITS resume callback. So when the consumer's task
    suspends on that sleep, the loop's next pass runs the producer's
    already-queued wakeup first (FIFO), the producer synchronously
    `put_nowait()`s the freed slot and re-parks (still inside that same
    step — no further await needed to top back up to 2), and only THEN
    does the consumer's own sleep resume. By the time `_run_swap` next
    checks `queue.empty()`, the refill has already happened. This holds
    regardless of hold_time/scroll_speed magnitude (even 0 — `sleep(0)`
    is still a real suspend/resume cycle) because it's an ordering
    guarantee, not a timing one. This is the SAME mechanism the Task 2
    fix's explicit `await asyncio.sleep(0)` buys deliberately for the
    play() path, which has no floor to get it for free.
    """
    widgets = [make_widget(10) for _ in range(5)]
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    ticker = Ticker(
        monitors=widgets,
        frame=mock_frame,
        notif_queue=queue,
        hold_time=0.0,
    )
    await ticker.run_slideshow(loop_count=1)

    for i, w in enumerate(widgets):
        assert w.draw.called, f"widget {i} was dropped"
    assert queue.empty(), "sentinel + all items must be fully drained"
    # Timeboxed (#394 Task 2 review, Finding 2): a bare await here would
    # hang the whole suite instead of failing if the producer ever got
    # parked forever — matching the pattern at ~line 91.
    assert ticker._enqueue_task is not None
    await asyncio.wait_for(ticker._enqueue_task, timeout=2.0)


class _KeyedPlayWidget:
    """A play()-dispatched widget keyed by `.text` for the breaker —
    mirrors how a content-bearing widget (e.g. an RSS story) is keyed by
    `render_breaker._key`: `(type(widget).__name__, str(widget.text))`.
    Two DIFFERENT instances sharing the same `.text` therefore share the
    same breaker key, so tripping one disables the other too.

    `raises=True` makes `play()` raise before its first `await` —
    `_play_widget`'s `except Exception` (~ticker.py:477) trips the
    breaker and returns the canvas unchanged, with ZERO real awaits for
    that visit. `raises=False` is used for the SECOND instance of a
    matching pair: by the time `_play_widget` reaches it, the breaker is
    already disabled (tripped by the first instance moments earlier), so
    `_play_widget`'s own disabled-check (~ticker.py:459) short-circuits
    before `play()` is ever called — also ZERO real awaits. Pre-tripping
    a widget BEFORE the section even starts doesn't reach this code path
    at all: `_expand_sources` filters already-disabled widgets out at
    enqueue time (~ticker.py:1204), so a widget disabled before its pass
    begins never reaches the queue, let alone `_play_widget`. The two
    zero-await code paths only become adjacent in the queue when the
    SAME pass enqueues both instances (neither disabled yet) and the
    first one's failure disables the second one in between.
    """

    def __init__(self, text, raises):
        self.text = text
        self.raises = raises
        self.play_called = False

    async def play(self, real_canvas, frame, loop_count=1, **kwargs):
        if self.raises:
            raise RuntimeError("boom before any await")
        self.play_called = True
        return real_canvas


@pytest.mark.asyncio
async def test_run_swap_play_widgets_do_not_strand_trailing_widgets(
    mock_frame, make_widget, no_sleep
):
    """Task 2 review regression (#394 Finding 1): two ADJACENT
    suspension-free play()-dispatched widgets — one whose `play()` raises
    synchronously, one that's short-circuited by the breaker it just
    tripped (same content key) — followed by two normal draw()-based
    widgets in a finite section, driven through the REAL producer + a
    REAL bounded queue via `run_slideshow`.

    Pre-fix, this reliably dropped the trailing widgets: `_run_swap`'s
    tail loop drained both consumed slots (`get_nowait()` for the raising
    widget, then `get_nowait()` for the now-disabled duplicate) with no
    intervening `await` anywhere — neither play()-visit ever suspends the
    running task — so the producer's pending refill (already scheduled
    via `loop.call_soon` from the first dequeue) never got a turn to run
    before `while not queue.empty()` re-checked and (falsely) concluded
    the section was exhausted.

    Fixed by `_run_swap` yielding `await asyncio.sleep(0)` before every
    `.empty()` check, giving the producer's pending refill a turn each
    time a slot is freed — see the docstring on
    `test_run_swap_drain_loop_terminates_with_parked_producer` for the
    underlying event-loop mechanics.
    """
    breaker = RenderBreaker()
    w_raising = _KeyedPlayWidget("dup", raises=True)
    w_disabled = _KeyedPlayWidget("dup", raises=False)
    w3 = make_widget(10)
    w4 = make_widget(10)

    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    ticker = Ticker(
        monitors=[w_raising, w_disabled, w3, w4],
        frame=mock_frame,
        notif_queue=queue,
        hold_time=0.0,
        breaker=breaker,
    )
    await ticker.run_slideshow(loop_count=1)

    assert not w_disabled.play_called, "breaker short-circuit didn't fire as expected"
    assert w3.draw.called, "widget 3 was stranded by the suspension-free drain"
    assert w4.draw.called, "widget 4 was stranded by the suspension-free drain"
    assert queue.empty(), "sentinel + all items must be fully drained"
    assert ticker._enqueue_task is not None
    await asyncio.wait_for(ticker._enqueue_task, timeout=2.0)


@pytest.mark.asyncio
async def test_scroll_one_by_one_survives_degenerate_config(
    mock_frame, make_widget, no_sleep
):
    """Same carry-forward check as above, for `_scroll_one_by_one`
    (`run_one_at_a_time`), whose `except asyncio.QueueEmpty: break` at
    ~ticker.py:952-954 is the same "empty() means done" shape.

    EARLY-EXIT VERDICT: not exposed, even with 20 one-pixel-wide widgets
    at `scroll_speed=0` (empirically checked; kept smaller here for a fast
    test). Reasoning: that `get_nowait()` only runs once the CURRENT
    widget has fully scrolled off-canvas (`final_pos < 0`), which takes
    `canvas.width + widget_width` per-pixel ticks — each tick has a real
    `await asyncio.sleep(...)`. So dozens of suspend/resume cycles (each
    one sufficient to let the producer top up by the single slot freed at
    the *previous* widget's dequeue — same FIFO-ordering argument as
    `_run_swap`) elapse before this site ever asks the queue for the next
    item. Not fixed, per the same "test doesn't catch it" rule.
    """
    widgets = [make_widget(10) for _ in range(5)]
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    ticker = Ticker(
        monitors=widgets,
        frame=mock_frame,
        notif_queue=queue,
        hold_time=0.0,
        scroll_speed=0,
    )
    await ticker.run_one_at_a_time(loop_count=1)

    for i, w in enumerate(widgets):
        assert w.draw.called, f"widget {i} was dropped"


@pytest.mark.asyncio
async def test_scroll_side_by_side_does_not_drop_widgets_under_bounded_queue(
    mock_frame, make_widget, no_sleep
):
    """CARRY-FORWARD regression (#394 Task 1 review) — the site that WAS
    broken: `_scroll_side_by_side`'s inner buffering loop
    (`while cursor_pos < canvas.width: ...`) has NO await in it at all —
    it's a tight synchronous burst that pulls from the queue as many
    times as it takes to fill one row. Before the fix, hitting
    `queue.empty()` mid-burst (before the producer had ANY chance to run)
    set a STICKY `queue_empty = True` flag that permanently disabled all
    further buffering for the rest of the section — even though the
    `None` sentinel had never arrived and the producer had more widgets
    queued up behind it. Under the old unbounded queue this couldn't
    happen (the whole section was enqueued before the first read, so
    `empty()` really did mean exhausted); under `maxsize=2` it's a near-
    certainty whenever a row needs more than 2 buffered widgets to fill.

    Repro (pre-fix): 8 widgets of width 10 on a 160px canvas needs ~16
    buffered to fill one row; only 2 fit in the queue at a time, so the
    burst always drained both, saw `empty()`, and stranded widgets
    4-8 (observed draw counts: [253, 46, 72, 0, 0, 0, 0, 0]).

    Fix: `queue_empty` is now set ONLY by the `None` sentinel via
    `get_nowait()` + `except asyncio.QueueEmpty: break` (a plain,
    non-sticky break — retried next outer tick) instead of a
    `queue.empty()` pre-check. Exhaustion is decided by the sentinel
    only, matching the carry-forward's directive.
    """
    widgets = [make_widget(10) for _ in range(8)]
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    ticker = Ticker(
        monitors=widgets,
        frame=mock_frame,
        notif_queue=queue,
        hold_time=0.0,
    )
    await ticker.run_ticker(loop_count=1)

    counts = [w.draw.call_count for w in widgets]
    for i, w in enumerate(widgets):
        assert w.draw.called, f"widget {i} was dropped: {counts}"


@pytest.mark.asyncio
async def test_run_slideshow_completes_over_bounded_queue(
    mock_frame, make_widget, no_sleep
):
    """Integration pin: `Ticker.run_slideshow` end-to-end over a REAL
    bounded queue with the REAL producer (`_build_then_enqueue`, spawned
    internally by `run_slideshow`) — not a hand-fed unbounded queue like
    the consumer-side tests in `tests/test_ticker_display.py`. Mirrors
    `TestTickerRunSwap.test_run_swap_terminates`'s fixture setup (mock
    frame + `make_widget` + `no_sleep`) but supplies a bounded queue.
    """
    w1 = make_widget(30)
    w2 = make_widget(30)
    w3 = make_widget(30)
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    ticker = Ticker(monitors=[w1, w2, w3], frame=mock_frame, notif_queue=queue)
    await ticker.run_slideshow(loop_count=1)

    assert w1.draw.called
    assert w2.draw.called
    assert w3.draw.called
    assert queue.empty()
    # Timeboxed (#394 Task 2 review, Finding 2): see the matching comment
    # in test_run_swap_survives_degenerate_config.
    assert ticker._enqueue_task is not None
    await asyncio.wait_for(ticker._enqueue_task, timeout=2.0)


# ---------------------------------------------------------------------------
# Issue #400: producer death BEFORE the first put() strands the consumer
# ---------------------------------------------------------------------------
# _enqueue_ticker_objects only sentinels on StopIteration; any OTHER
# exception out of the first next() (e.g. a plugin container whose
# feed_stories property raises during _expand_sources) killed the producer
# with only a log line — no sentinel — so the consumer's first blocking
# `await notif_queue.get()` waited forever: a panel freeze (constraint #1
# class). Mid-stream death already degraded safely (later reads are
# empty()-guarded get_nowait); only the death-before-first-put window froze.


class _ExplodingContainer:
    """A Container-shaped widget whose expansion raises on FIRST access —
    the exact failure _build_ticker_iter hits lazily inside next()."""

    @property
    def feed_stories(self):
        raise RuntimeError("boom on first expansion")


@pytest.mark.asyncio
async def test_producer_death_before_first_put_delivers_sentinel():
    """Unit: the producer must wake the consumer even when it dies before
    its first put — exactly one None sentinel, and the exception still
    propagates (so the done-callback's logging is preserved)."""
    from led_ticker.ticker import _build_then_enqueue

    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    task = asyncio.create_task(_build_then_enqueue([_ExplodingContainer()], queue))
    with pytest.raises(RuntimeError, match="boom on first expansion"):
        await asyncio.wait_for(task, timeout=2.0)
    assert queue.get_nowait() is None, "dead producer must enqueue the sentinel"
    assert queue.empty(), "exactly ONE sentinel"


@pytest.mark.asyncio
async def test_producer_death_mid_stream_still_delivers_sentinel(make_widget):
    """Defense in depth: a mid-stream death also sentinels (consumers
    already degrade via empty()-guarded reads, but the sentinel ends the
    section promptly instead of on the next poll)."""
    from led_ticker.ticker import _build_then_enqueue

    class _ExplodesOnSecondExpansion:
        def __init__(self):
            self.calls = 0
            self._story = make_widget(10)

        @property
        def feed_stories(self):
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError("boom mid-stream")
            return [self._story]

    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    task = asyncio.create_task(
        _build_then_enqueue([_ExplodesOnSecondExpansion()], queue)
    )
    with pytest.raises(RuntimeError, match="boom mid-stream"):
        await asyncio.wait_for(task, timeout=2.0)
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    assert items and items[-1] is None, "sentinel must arrive last"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "run_method", ["run_slideshow", "run_ticker", "run_one_at_a_time"]
)
async def test_consumers_return_when_producer_dies_before_first_put(
    mock_frame, no_sleep, run_method
):
    """Integration (the freeze itself): each of the three consumers must
    RETURN — not hang — when the section's producer dies before its first
    put. Timeboxed: pre-fix this times out on the first blocking get()."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    ticker = Ticker(
        monitors=[_ExplodingContainer()],
        frame=mock_frame,
        notif_queue=queue,
        hold_time=0.0,
    )
    await asyncio.wait_for(getattr(ticker, run_method)(loop_count=1), timeout=2.0)
