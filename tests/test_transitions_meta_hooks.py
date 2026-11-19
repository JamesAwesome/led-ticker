"""`run_transition`'s two additive meta-transition hooks.

`duration_override` (read before `frame_count`, `is not None` semantics) and
`end_firing()` (called once per firing in the runner's `finally`, after both
widgets are resumed, never propagating). Plus `DEFAULT_SCALE_SWITCH_AT`, the
hoisted runner default the `random` / `auto` wrapper forwards.
"""

import asyncio
import logging
from unittest import mock

import pytest

import led_ticker.transitions as transitions_mod
from led_ticker.backends.headless import HeadlessCanvas
from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.transitions import (
    DEFAULT_SCALE_SWITCH_AT,
    EASING,
    run_transition,
)


class _Stub:
    """Transition stub recording `frame_at` calls and `end_firing` calls."""

    def __init__(self, duration_override=None, raise_in_frame_at=None):
        self.calls: list[tuple[float, int | None]] = []
        self.ends = 0
        self.events: list[str] = []
        if duration_override is not None:
            self.duration_override = duration_override
        self._raise = raise_in_frame_at

    def frame_at(self, t, canvas, outgoing, incoming, **kw):
        self.calls.append((t, kw.get("duration_ms")))
        if self._raise is not None:
            raise self._raise
        return canvas

    def end_firing(self):
        self.ends += 1
        self.events.append("end_firing")


class _Bare:
    """A transition with neither hook — must be byte-identical."""

    def __init__(self):
        self.calls = 0

    def frame_at(self, t, canvas, outgoing, incoming, **kw):
        self.calls += 1
        return canvas


async def _run(canvas, frame, mw, stub, **kw):
    kw.setdefault("duration", 0.5)
    kw.setdefault("scroll_speed", 0.05)
    return await run_transition(canvas, frame, mw(40), mw(40), transition=stub, **kw)


async def test_duration_override_sets_frame_count_and_duration_ms(
    canvas, mock_frame, make_widget, no_sleep
):
    s = _Stub(duration_override=3.0)
    await _run(canvas, mock_frame, make_widget, s)
    assert len(s.calls) == 61  # frame_count 60 → range(61)
    assert s.calls[0][1] == 3000


async def test_duration_override_none_uses_section_duration(
    canvas, mock_frame, make_widget, no_sleep
):
    s = _Stub()
    s.duration_override = None
    await _run(canvas, mock_frame, make_widget, s)
    assert len(s.calls) == 11 and s.calls[0][1] == 500


async def test_duration_override_zero_is_honoured_not_or(
    canvas, mock_frame, make_widget, no_sleep
):
    """`is not None`, not `or`: a 0.0 override floors to ONE frame (2 calls),
    it does not fall back to the section's 10."""
    s = _Stub(duration_override=0.0)
    await _run(canvas, mock_frame, make_widget, s)
    assert len(s.calls) == 2


async def test_duration_override_shortens_below_section(
    canvas, mock_frame, make_widget, no_sleep
):
    s = _Stub(duration_override=0.05)
    await _run(canvas, mock_frame, make_widget, s)
    assert len(s.calls) == 2 and s.calls[0][1] == 50


async def test_transition_without_hooks_is_unchanged(
    canvas, mock_frame, make_widget, no_sleep
):
    b = _Bare()
    await _run(canvas, mock_frame, make_widget, b)
    assert b.calls == 11


async def test_end_firing_called_once_after_both_resumes(
    canvas, mock_frame, make_widget, no_sleep
):
    s = _Stub()
    outgoing, incoming = make_widget(40), make_widget(40)
    for w in (outgoing, incoming):
        w.pause_frame = mock.Mock()
        w.resume_frame = mock.Mock(side_effect=lambda: s.events.append("resume"))
    await run_transition(
        canvas,
        mock_frame,
        outgoing,
        incoming,
        transition=s,
        duration=0.5,
        scroll_speed=0.05,
    )
    assert s.ends == 1
    assert s.events == ["resume", "resume", "end_firing"]


async def test_end_firing_called_on_cancellation(
    canvas, mock_frame, make_widget, no_sleep
):
    s = _Stub()

    async def driver():
        await _run(canvas, mock_frame, make_widget, s)

    task = asyncio.create_task(driver())
    await asyncio.sleep(0)  # let it start
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert s.ends == 1


async def test_end_firing_runs_after_frame_at_exception(
    canvas, mock_frame, make_widget, no_sleep
):
    s = _Stub(raise_in_frame_at=RuntimeError("boom"))
    outgoing, incoming = make_widget(40), make_widget(40)
    for w in (outgoing, incoming):
        w.pause_frame = mock.Mock()
        w.resume_frame = mock.Mock()
    with pytest.raises(RuntimeError, match="boom"):
        await run_transition(
            canvas,
            mock_frame,
            outgoing,
            incoming,
            transition=s,
            duration=0.5,
            scroll_speed=0.05,
        )
    assert s.ends == 1
    assert outgoing.resume_frame.called and incoming.resume_frame.called


async def test_end_firing_exception_is_logged_not_raised(
    canvas, mock_frame, make_widget, no_sleep, caplog
):
    s = _Stub()
    s.end_firing = mock.Mock(side_effect=ValueError("hook broke"))
    with caplog.at_level(logging.ERROR, logger="led_ticker.transitions"):
        await _run(canvas, mock_frame, make_widget, s)
    assert any("end_firing" in r.message for r in caplog.records)


async def test_end_firing_called_once_with_custom_easing(
    canvas, mock_frame, make_widget, no_sleep, monkeypatch
):
    """A plugin easing whose endpoint never reaches 1.0 must still end the
    firing exactly once — the pick is not keyed on `t`."""
    monkeypatch.setitem(EASING, "flat", lambda p: 0.5)
    s = _Stub()
    await _run(canvas, mock_frame, make_widget, s, easing="flat")
    assert s.ends == 1


def test_default_scale_switch_at_is_half():
    assert DEFAULT_SCALE_SWITCH_AT == 0.5


async def test_runner_uses_default_scale_switch_at_constant(
    make_widget, no_sleep, monkeypatch
):
    """A transition WITHOUT `scale_switch_at` re-wraps at the module constant:
    move the constant to 1.0 and the switch moves to the final frame."""
    real = HeadlessCanvas(256, 64)
    frame = mock.Mock()
    frame.get_clean_canvas.return_value = real
    frame.swap.side_effect = lambda c: HeadlessCanvas(256, 64)
    seen: list[float] = []

    class _Rec:
        def frame_at(self, t, canvas, outgoing, incoming, **kw):
            seen.append((t, getattr(canvas, "scale", 1)))
            return canvas

    monkeypatch.setattr(transitions_mod, "DEFAULT_SCALE_SWITCH_AT", 1.0)
    await run_transition(
        ScaledCanvas(real, scale=2),
        frame,
        make_widget(40),
        make_widget(40),
        transition=_Rec(),
        duration=0.5,
        scroll_speed=0.05,
        incoming_scale=4,
    )
    scales = [sc for _t, sc in seen]
    assert scales[:-1] == [2] * 10 and scales[-1] == 4
