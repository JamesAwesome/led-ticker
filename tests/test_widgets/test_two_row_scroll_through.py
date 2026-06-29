"""Tests for bottom_text_scroll on TwoRowMessage widget.

The bottom_text_scroll field is an enum that picks the bottom row's
scroll style when its content overflows (or — for "scroll_through" —
even when it doesn't):

  "marquee"        Default. Current behavior: held at bottom_align
                   when text fits; cursor-driven single-pass scroll
                   when it overflows; or seamless tile when paired
                   with bottom_text_wrap=True.

  "scroll_through" New. Always scroll, regardless of overflow. Text
                   starts fully off the right edge (bottom_x =
                   canvas.width) and ends fully off the left edge
                   (bottom_x + bottom_width < 0). One pass per visit.
                   bottom_align is ignored. Mutually exclusive with
                   bottom_text_wrap=True.
"""

from __future__ import annotations

import attrs
import pytest

from led_ticker.ticker import Ticker
from led_ticker.widgets.two_row import TwoRowMessage


def _two_row(**kwargs):
    defaults = dict(top_text="TOP", bottom_text="bottom scrolling")
    defaults.update(kwargs)
    return TwoRowMessage(**defaults)


class TestBottomTextScrollDefaults:
    def test_field_defaults_to_marquee(self):
        w = _two_row()
        assert w.bottom_text_scroll == "marquee"

    def test_marquee_explicit_accepted(self):
        w = _two_row(bottom_text_scroll="marquee")
        assert w.bottom_text_scroll == "marquee"

    def test_scroll_through_accepted(self):
        w = _two_row(bottom_text_scroll="scroll_through")
        assert w.bottom_text_scroll == "scroll_through"


class TestBottomTextScrollValidation:
    def test_unknown_value_raises_with_valid_options_listed(self):
        with pytest.raises(ValueError, match="bottom_text_scroll") as exc_info:
            _two_row(bottom_text_scroll="bogus")
        # Error message should list both valid options so the user
        # doesn't have to read the source to find them.
        msg = str(exc_info.value)
        assert "marquee" in msg
        assert "scroll_through" in msg
        assert "bogus" in msg

    def test_scroll_through_with_wrap_true_refused(self):
        """Mutex rule: bottom_text_wrap=True is the seamless tiled
        marquee; bottom_text_scroll='scroll_through' is the
        offscreen-to-offscreen single pass. Pick one."""
        with pytest.raises(
            ValueError,
            match=r"bottom_text_scroll=.scroll_through.*bottom_text_wrap=True",
        ):
            _two_row(
                bottom_text_scroll="scroll_through",
                bottom_text_wrap=True,
            )

    def test_scroll_through_with_empty_bottom_text_refused(self):
        """Nothing to scroll through — same defensive guard as
        bottom_text_wrap=True with empty bottom_text."""
        with pytest.raises(
            ValueError,
            match=r"bottom_text_scroll=.scroll_through.*non-empty bottom_text",
        ):
            TwoRowMessage(
                top_text="TOP",
                bottom_text="",
                bottom_text_scroll="scroll_through",
            )

    def test_marquee_with_wrap_true_still_accepted(self):
        """The default value of bottom_text_scroll must not break
        existing configs that set bottom_text_wrap=True."""
        w = _two_row(
            bottom_text_scroll="marquee",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
        )
        assert w.bottom_text_scroll == "marquee"
        assert w.bottom_text_wrap is True

    def test_loops_with_scroll_through_now_composes(self):
        """bottom_text_loops composes with scroll_through to repeat the
        offscreen pass N times. Previously this combo was rejected;
        composition is the desired UX (real-world configs want
        "scroll the bottom 3 times then transition" semantics)."""
        w = _two_row(
            bottom_text_loops=3,
            bottom_text_scroll="scroll_through",
        )
        assert w.bottom_text_loops == 3
        assert w.bottom_text_scroll == "scroll_through"
        # Forces the engine to drive a multi-pass scroll.
        assert w.forces_offscreen_scroll is True

    def test_loops_with_marquee_default_still_rejected(self):
        """The original validation contract still holds: bottom_text_loops
        without EITHER wrap or scroll_through has no cycle to count."""
        with pytest.raises(
            ValueError,
            match=r"bottom_text_loops.*requires.*(bottom_text_wrap|scroll_through)",
        ):
            _two_row(bottom_text_loops=3)  # default scroll=marquee, wrap=False


class TestForcesOffscreenScrollProperty:
    """Engine cooperation signal — parallel to `wraps_forever`. True only
    when bottom_text_scroll='scroll_through' AND bottom_text is non-empty.
    `_swap_and_scroll` uses this to pick the dedicated scroll-through
    branch (no pre/post holds, decrement pos until fully offscreen left)."""

    def test_false_by_default(self):
        w = _two_row()
        assert w.forces_offscreen_scroll is False

    def test_true_when_scroll_through_set(self):
        w = _two_row(bottom_text_scroll="scroll_through")
        assert w.forces_offscreen_scroll is True

    def test_false_when_bottom_empty_post_construction(self):
        """Defensive: if bottom_text is mutated to '' after construction
        (validation would normally reject this), forces_offscreen_scroll
        should still report False so the engine doesn't spin forever."""
        w = _two_row(bottom_text_scroll="scroll_through")
        w.bottom_text = ""
        assert w.forces_offscreen_scroll is False


class TestScrollThroughDraw:
    """In scroll_through mode, the bottom row is positioned at
    bottom_x = canvas.width + cursor_pos:

        cursor_pos =  0   → bottom_x = canvas.width   (fully off right)
        cursor_pos = -50  → bottom_x = canvas.width - 50
        cursor_pos = -(canvas.width + bottom_width)  → fully off left

    bottom_align is ignored (no "held" path in this mode). Top row is
    still held at its computed top_align position.
    """

    def _capture_draws(self, monkeypatch):
        from led_ticker.widgets import two_row as tr

        captured: list[tuple[int, int]] = []  # (x, y) per draw_with_emoji call

        def fake_draw_with_emoji(canvas, font, x, y, color, text, **kw):
            captured.append((x, y))
            return 50

        monkeypatch.setattr(tr, "draw_with_emoji", fake_draw_with_emoji)
        return captured

    def test_at_cursor_zero_bottom_drawn_fully_offscreen_right(
        self, canvas, monkeypatch
    ):
        captured = self._capture_draws(monkeypatch)
        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="some scrolling content here",
            bottom_text_scroll="scroll_through",
        )
        w.draw(canvas, cursor_pos=0)
        # Two draw_with_emoji calls expected — top then bottom.
        assert len(captured) == 2, captured
        bottom_x = captured[1][0]
        assert bottom_x == canvas.width, (
            f"scroll_through must start bottom row at canvas.width "
            f"({canvas.width}); got {bottom_x}"
        )

    def test_negative_cursor_moves_bottom_left(self, canvas, monkeypatch):
        captured = self._capture_draws(monkeypatch)
        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="some scrolling content here",
            bottom_text_scroll="scroll_through",
        )
        w.draw(canvas, cursor_pos=-50)
        bottom_x = captured[1][0]
        # cursor_pos=-50 puts the bottom row 50px left of canvas.width.
        assert bottom_x == canvas.width - 50, (
            f"scroll_through expected bottom_x={canvas.width - 50} at "
            f"cursor_pos=-50; got {bottom_x}"
        )

    def test_bottom_align_ignored_in_scroll_through(self, canvas, monkeypatch):
        """Even with `bottom_align='center'` and short text that would
        normally fit, scroll_through forces the offscreen start — not
        the centered held position."""
        captured = self._capture_draws(monkeypatch)
        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="hi",  # short — would normally center
            bottom_align="center",
            bottom_text_scroll="scroll_through",
        )
        w.draw(canvas, cursor_pos=0)
        bottom_x = captured[1][0]
        assert bottom_x == canvas.width, (
            f"scroll_through must ignore bottom_align; expected "
            f"bottom_x={canvas.width}, got {bottom_x}"
        )

    def test_top_row_still_held_in_scroll_through(self, canvas, monkeypatch):
        """Top row continues to draw at the same x regardless of
        cursor_pos — only bottom scrolls."""
        captured = self._capture_draws(monkeypatch)
        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="some long bottom text here",
            bottom_text_scroll="scroll_through",
        )
        w.draw(canvas, cursor_pos=0)
        top_x_a = captured[0][0]
        captured.clear()
        w.draw(canvas, cursor_pos=-100)
        top_x_b = captured[0][0]
        assert top_x_a == top_x_b, (
            f"Top row x must be stable across scroll ticks; "
            f"got {top_x_a} then {top_x_b}"
        )

    def test_returned_cursor_anchors_engine_stop_to_one_full_cycle(self, canvas):
        """The widget's returned cursor_pos must let the engine compute
        a stop position equal to -cycle_width (= -(canvas.width + bottom_width)).

        Engine math: stop_pos = -(returned_cursor - canvas.width) + padding.
        We derive the assertion BEHAVIORALLY (compute engine stop_pos
        from returned cursor) rather than pinning the literal formula,
        so a future refactor that rebalances widget-vs-engine math
        without changing the visible behavior still passes."""
        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="content",
            bottom_text_scroll="scroll_through",
        )
        _, cursor = w.draw(canvas, cursor_pos=0)
        bottom_width = w._bottom_width
        cycle_width = canvas.width + bottom_width
        engine_stop_pos = -(cursor - canvas.width) + w.padding
        assert engine_stop_pos == -cycle_width, (
            f"With loops=0 (default), engine stop_pos must be one full "
            f"cycle_width ({cycle_width}); got {engine_stop_pos} from "
            f"returned cursor {cursor}."
        )

    def test_returned_cursor_anchors_n_cycles_when_loops_set(self, canvas):
        """With bottom_text_loops=N, the engine stop math must land at
        -N*cycle_width so the bottom row scrolls through N full passes."""
        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="content",
            bottom_text_scroll="scroll_through",
            bottom_text_loops=3,
        )
        _, cursor = w.draw(canvas, cursor_pos=0)
        bottom_width = w._bottom_width
        cycle_width = canvas.width + bottom_width
        engine_stop_pos = -(cursor - canvas.width) + w.padding
        assert engine_stop_pos == -3 * cycle_width, (
            f"With loops=3, engine stop_pos must be 3*cycle_width "
            f"({3 * cycle_width}); got {engine_stop_pos} from "
            f"returned cursor {cursor}."
        )

    def test_draw_wraps_modularly_across_loop_boundaries(self, canvas, monkeypatch):
        """When loops>=2, cursor_pos at the boundary between two cycles
        should put the bottom row back at canvas.width (start of new cycle)."""
        captured = self._capture_draws(monkeypatch)
        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="text",
            bottom_text_scroll="scroll_through",
            bottom_text_loops=2,
        )
        # First populate _bottom_width by drawing at pos=0.
        w.draw(canvas, cursor_pos=0)
        captured.clear()

        cycle_width = canvas.width + w._bottom_width
        # At pos = -cycle_width, the second cycle begins — bottom_x must
        # return to canvas.width (modular wrap).
        w.draw(canvas, cursor_pos=-cycle_width)
        bottom_x_at_cycle_boundary = captured[1][0]
        assert bottom_x_at_cycle_boundary == canvas.width, (
            f"At cursor_pos=-cycle_width ({-cycle_width}), bottom_x must "
            f"wrap to canvas.width ({canvas.width}); got "
            f"{bottom_x_at_cycle_boundary}. Modular formula broken."
        )

        captured.clear()
        # One tick into cycle 2: pos = -cycle_width - 1
        # → bottom_x = canvas.width - 1.
        w.draw(canvas, cursor_pos=-cycle_width - 1)
        assert captured[1][0] == canvas.width - 1, (
            f"One tick into cycle 2: bottom_x should be canvas.width - 1 "
            f"({canvas.width - 1}); got {captured[1][0]}"
        )


class TestScrollThroughEngineIntegration:
    """`_swap_and_scroll` integration: scroll_through widgets must
    skip pre/post holds entirely. The signal is the count of
    cursor_pos=0 draws — without holds, only the initial entry-draw
    happens at pos=0; the scroll loop decrements pos *before* its
    first draw, so all subsequent draws use negative cursor_pos. A
    pre-scroll hold loop would draw at pos=0 once per tick, blowing
    that count past 1.

    These tests use a tiny fake widget to keep them fast and focused
    on the engine branch, not widget internals."""

    def _fake_scroll_through_widget(self, bottom_width=200, canvas_width=160):
        """Minimal widget mimicking TwoRowMessage's scroll_through
        engine contract."""
        import unittest.mock as mock

        widget = mock.Mock(
            spec_set=[
                "draw",
                "forces_offscreen_scroll",
                "wraps_forever",
                "bg_color",
                "padding",
                "_bottom_width",
            ]
        )
        widget.forces_offscreen_scroll = True
        widget.wraps_forever = False
        widget.bg_color = None
        widget.padding = 6
        widget._bottom_width = bottom_width
        # Returned cursor: anchors stop math to -(canvas.width + bw).
        widget.draw.side_effect = lambda c, cursor_pos=0, **kw: (
            c,
            2 * canvas_width + bottom_width + 6,
        )
        return widget

    @pytest.mark.asyncio
    async def test_scroll_through_only_one_draw_at_cursor_zero(
        self, swapping_frame, monkeypatch
    ):
        """The engine branch must skip the pre-scroll hold loop. The
        only draw with cursor_pos=0 should be the initial entry draw
        — the scroll loop decrements pos before its first draw, so
        every subsequent draw has cursor_pos < 0.

        Without the engine branch, the standard scroll path runs a
        pre-hold loop that redraws with cursor_pos=pos=0 once per tick,
        making this count > 1 for any non-zero hold_time."""

        # No-op sleep so the test doesn't dwell during any hold loops.
        async def _no_sleep(_):
            return None

        monkeypatch.setattr("asyncio.sleep", _no_sleep)

        widget = self._fake_scroll_through_widget(bottom_width=200, canvas_width=160)
        canvas = swapping_frame.get_clean_canvas.return_value
        ticker = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0.0)
        await ticker._swap_and_scroll(
            canvas,
            widget,
            hold_time=1.0,  # Non-trivial: pre-hold loop would fire 20 ticks.
        )
        zero_pos_draws = [
            call
            for call in widget.draw.call_args_list
            if call.kwargs.get("cursor_pos", call.args[1] if len(call.args) > 1 else 0)
            == 0
        ]
        assert len(zero_pos_draws) == 1, (
            f"scroll_through must skip pre-scroll hold. Expected 1 draw "
            f"at cursor_pos=0 (the initial entry draw); got {len(zero_pos_draws)}. "
            f"Likely the pre-hold loop wasn't skipped."
        )

    @pytest.mark.asyncio
    async def test_scroll_through_final_pos_clears_left_edge(
        self, swapping_frame, monkeypatch
    ):
        """The scroll loop must travel at LEAST -(canvas.width +
        bottom_width) so the bottom row clears the left edge. With
        widget bottom_width=200 + canvas.width=160, final pos must be
        <= -360."""

        async def _no_sleep(_):
            return None

        monkeypatch.setattr("asyncio.sleep", _no_sleep)

        widget = self._fake_scroll_through_widget(bottom_width=200, canvas_width=160)
        canvas = swapping_frame.get_clean_canvas.return_value
        ticker = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0.0)
        _, _, final_pos = await ticker._swap_and_scroll(
            canvas,
            widget,
            hold_time=0.0,
        )
        assert final_pos <= -(canvas.width + 200), (
            f"scroll_through must scroll bottom row fully off the left edge; "
            f"final pos={final_pos}, expected <= {-(canvas.width + 200)}"
        )


class TestScrollThroughHoldTimeUnification:
    """Engine integration: scroll_through must honor hold_time as a floor
    alongside bottom_text_loops, using max-of semantics:

        n_passes = max(bottom_text_loops or 1,
                       ceil(hold_time_ticks / cycle_width))

    where hold_time_ticks = int(hold_time / scroll_speed)
    and   cycle_width     = canvas.width + bottom_width.

    These are real-widget tests driven through _swap_and_scroll.
    """

    @pytest.mark.asyncio
    async def test_scroll_through_hold_time_alone_drives_passes(
        self, swapping_frame, monkeypatch
    ):
        """hold_time=20.0, bottom_text_loops=0 → at least 2 full passes.

        Strategy: bottom_text has width ~160 → cycle_width=320.
        scroll_speed=0.05 → hold_time_ticks = int(20.0/0.05)=400.
        ceil(400/320) = 2 → n_passes >= 2.
        Verify final_pos <= -(2 * cycle_width).
        """
        import math

        async def _no_sleep(_):
            return None

        monkeypatch.setattr("asyncio.sleep", _no_sleep)

        # Use a long bottom_text so bottom_width ≈ 160 and cycle_width ≈ 320.
        widget = TwoRowMessage(
            top_text="TOP",
            bottom_text="A B C D E F G H I J K L M N O P Q R",
            bottom_text_scroll="scroll_through",
            bottom_text_loops=0,
        )
        canvas = swapping_frame.get_clean_canvas.return_value
        scroll_speed = 0.05
        hold_time = 20.0

        ticker = Ticker(monitors=[], frame=swapping_frame, scroll_speed=scroll_speed)
        _, _, final_pos = await ticker._swap_and_scroll(
            canvas,
            widget,
            hold_time=hold_time,
        )

        bottom_width = widget._bottom_width
        cycle_width = canvas.width + bottom_width
        hold_time_ticks = int(hold_time / scroll_speed)
        n_passes = max(
            1, math.ceil(hold_time_ticks / cycle_width) if cycle_width > 0 else 1
        )
        expected_final = -(n_passes * cycle_width)
        assert final_pos <= expected_final, (
            f"hold_time alone must drive passes: expected final_pos <= "
            f"{expected_final} ({n_passes} passes × {cycle_width}px); "
            f"got {final_pos}. bottom_width={bottom_width}"
        )
        # Check: must be > 1 pass to verify hold_time actually had effect.
        assert n_passes >= 2, (
            f"Test setup: expected ≥2 passes from hold_time; only got "
            f"{n_passes} (cycle_width={cycle_width}, hold_ticks={hold_time_ticks}). "
            f"Adjust text length or scroll_speed."
        )

    @pytest.mark.asyncio
    async def test_scroll_through_loops_wins_over_short_hold_time(
        self, swapping_frame, monkeypatch
    ):
        """bottom_text_loops=3, hold_time=0.05 → exactly 3 passes.

        hold_time is so short that hold_time_ticks < cycle_width,
        so ceil(ticks/cycle_width) = 1 < loops_floor=3.
        max picks loops_floor=3.
        """

        async def _no_sleep(_):
            return None

        monkeypatch.setattr("asyncio.sleep", _no_sleep)

        widget = TwoRowMessage(
            top_text="TOP",
            bottom_text="some scrolling content",
            bottom_text_scroll="scroll_through",
            bottom_text_loops=3,
        )
        canvas = swapping_frame.get_clean_canvas.return_value
        scroll_speed = 0.05
        hold_time = 0.05  # tiny — only 1 tick worth

        ticker = Ticker(monitors=[], frame=swapping_frame, scroll_speed=scroll_speed)
        _, _, final_pos = await ticker._swap_and_scroll(
            canvas,
            widget,
            hold_time=hold_time,
        )

        bottom_width = widget._bottom_width
        cycle_width = canvas.width + bottom_width
        # Verify loops=3 was the controlling factor.
        # final_pos must be exactly in range [-(3*cycle_width), -(2*cycle_width))
        expected_exact = -(3 * cycle_width)
        assert final_pos == expected_exact, (
            f"loops=3 should control: expected final_pos={expected_exact}; "
            f"got {final_pos}. bottom_width={bottom_width}, cycle_width={cycle_width}"
        )

    @pytest.mark.asyncio
    async def test_scroll_through_hold_time_wins_over_one_loop(
        self, swapping_frame, monkeypatch
    ):
        """hold_time=20.0, bottom_text_loops=1 → multiple passes driven by hold_time.

        scroll_speed=0.05 → hold_time_ticks=400.
        cycle_width ≈ 320 (wide text). ceil(400/320)=2 > loops_floor=1.
        n_passes=2, final_pos <= -(2 * cycle_width).
        """
        import math

        async def _no_sleep(_):
            return None

        monkeypatch.setattr("asyncio.sleep", _no_sleep)

        widget = TwoRowMessage(
            top_text="TOP",
            bottom_text="A B C D E F G H I J K L M N O P Q R",
            bottom_text_scroll="scroll_through",
            bottom_text_loops=1,
        )
        canvas = swapping_frame.get_clean_canvas.return_value
        scroll_speed = 0.05
        hold_time = 20.0

        ticker = Ticker(monitors=[], frame=swapping_frame, scroll_speed=scroll_speed)
        _, _, final_pos = await ticker._swap_and_scroll(
            canvas,
            widget,
            hold_time=hold_time,
        )

        bottom_width = widget._bottom_width
        cycle_width = canvas.width + bottom_width
        hold_time_ticks = int(hold_time / scroll_speed)
        n_passes = max(
            1, math.ceil(hold_time_ticks / cycle_width) if cycle_width > 0 else 1
        )

        # Must be more than 1 pass (hold_time wins).
        assert n_passes > 1, (
            f"Test setup: expected >1 passes from hold_time; got {n_passes}. "
            f"Adjust text or scroll_speed."
        )
        expected_final = -(n_passes * cycle_width)
        assert final_pos <= expected_final, (
            f"hold_time should win over 1 loop: expected final_pos <= "
            f"{expected_final} ({n_passes} passes); got {final_pos}"
        )

    @pytest.mark.asyncio
    async def test_scroll_through_both_zero_one_pass(self, swapping_frame, monkeypatch):
        """Regression: hold_time=0.0, bottom_text_loops=0 → exactly 1 pass.

        Both unset → baseline 1 pass. Back-compat.
        """

        async def _no_sleep(_):
            return None

        monkeypatch.setattr("asyncio.sleep", _no_sleep)

        widget = TwoRowMessage(
            top_text="TOP",
            bottom_text="some content",
            bottom_text_scroll="scroll_through",
            bottom_text_loops=0,
        )
        canvas = swapping_frame.get_clean_canvas.return_value

        ticker = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0.05)
        _, _, final_pos = await ticker._swap_and_scroll(
            canvas,
            widget,
            hold_time=0.0,
        )

        bottom_width = widget._bottom_width
        cycle_width = canvas.width + bottom_width
        expected_final = -(1 * cycle_width)
        assert final_pos == expected_final, (
            f"hold_time=0 + loops=0 must yield exactly 1 pass: "
            f"expected {expected_final}, got {final_pos}. "
            f"bottom_width={bottom_width}"
        )

    @pytest.mark.asyncio
    async def test_scroll_through_loops_only_unchanged(
        self, swapping_frame, monkeypatch
    ):
        """Regression: bottom_text_loops=3, hold_time=0 → exactly 3 passes.

        Existing TwoRow behavior preserved — loops alone controls passes
        when hold_time is 0.
        """

        async def _no_sleep(_):
            return None

        monkeypatch.setattr("asyncio.sleep", _no_sleep)

        widget = TwoRowMessage(
            top_text="TOP",
            bottom_text="some scrolling content",
            bottom_text_scroll="scroll_through",
            bottom_text_loops=3,
        )
        canvas = swapping_frame.get_clean_canvas.return_value

        ticker = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0.05)
        _, _, final_pos = await ticker._swap_and_scroll(
            canvas,
            widget,
            hold_time=0.0,
        )

        bottom_width = widget._bottom_width
        cycle_width = canvas.width + bottom_width
        expected_final = -(3 * cycle_width)
        assert final_pos == expected_final, (
            f"loops=3 + hold_time=0 must yield exactly 3 passes: "
            f"expected {expected_final}, got {final_pos}. "
            f"bottom_width={bottom_width}"
        )


class TestScrollThroughRealWidgetEngineIntegration:
    """End-to-end: a real TwoRowMessage driven through _swap_and_scroll.

    The other engine-integration tests use a Mock widget which fixes
    attribute names + types up-front. That can mask drift between
    the real widget's surface and what the engine reads (e.g., a
    renamed `_bottom_width` or a `forces_offscreen_scroll` that
    silently returns a Mock truthy proxy instead of strict bool).

    This test pipes a REAL widget through the engine and asserts the
    same behavioral contract — if either widget or engine drifts,
    this catches the gap that the mocked tests would miss.
    """

    @pytest.mark.asyncio
    async def test_real_two_row_scroll_through_clears_left_edge(
        self, swapping_frame, monkeypatch
    ):
        async def _no_sleep(_):
            return None

        monkeypatch.setattr("asyncio.sleep", _no_sleep)

        widget = TwoRowMessage(
            top_text="TOP",
            bottom_text="some real scrolling content",
            bottom_text_scroll="scroll_through",
        )
        canvas = swapping_frame.get_clean_canvas.return_value

        # Real widget needs to measure its bottom_width on first draw.
        ticker = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0.0)
        _, _, final_pos = await ticker._swap_and_scroll(
            canvas,
            widget,
            hold_time=1.0,  # Non-trivial: a pre-hold would inflate ticks.
        )

        # After the loop, the bottom row must have travelled at least
        # -(canvas.width + bottom_width) so the last char clears the left
        # edge. _bottom_width is populated on the widget's first draw.
        assert widget._bottom_width > 0, (
            "Widget should have measured _bottom_width on first draw"
        )
        expected = -(canvas.width + widget._bottom_width)
        assert final_pos <= expected, (
            f"Real TwoRowMessage scroll_through must travel to "
            f"pos <= {expected}; got {final_pos}. Widget _bottom_width="
            f"{widget._bottom_width}, canvas.width={canvas.width}."
        )

    @pytest.mark.asyncio
    async def test_real_two_row_scroll_through_skips_holds(
        self, swapping_frame, monkeypatch
    ):
        """Same cursor_pos=0 count check as the mocked test, but with a
        real widget — guards against drift where the real widget's
        `forces_offscreen_scroll` property starts returning a truthy
        Mock-like object instead of strict True.

        Subclasses TwoRowMessage to capture draw() calls — attrs.define
        produces slots-only instances so post-construction monkeypatch
        and mocker.spy both fail.
        """
        captured: list[int] = []

        @attrs.define
        class _RecordingTwoRow(TwoRowMessage):
            def draw(self, canvas, cursor_pos=0, **kwargs):
                captured.append(cursor_pos)
                return super().draw(canvas, cursor_pos, **kwargs)

        async def _no_sleep(_):
            return None

        monkeypatch.setattr("asyncio.sleep", _no_sleep)

        widget = _RecordingTwoRow(
            top_text="TOP",
            bottom_text="content here",
            bottom_text_scroll="scroll_through",
        )
        canvas = swapping_frame.get_clean_canvas.return_value
        ticker = Ticker(monitors=[], frame=swapping_frame, scroll_speed=0.0)
        await ticker._swap_and_scroll(canvas, widget, hold_time=1.0)

        zero_pos_draws = [pos for pos in captured if pos == 0]
        assert len(zero_pos_draws) == 1, (
            f"Real widget engine path must skip pre-scroll hold; "
            f"expected 1 cursor_pos=0 draw, got {len(zero_pos_draws)}. "
            f"If this is > 1, the `forces_offscreen_scroll` property "
            f"is not being read as strict True by the engine."
        )
