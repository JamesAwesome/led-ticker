"""Tests for led_ticker.widgets.message."""

from datetime import date

from led_ticker.colors import DEFAULT_COLOR, RGB_WHITE
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widget import Widget
from led_ticker.widgets.message import TickerCountdown, TickerMessage


class TestTickerMessage:
    def test_conforms_to_widget_protocol(self):
        msg = TickerMessage(text="hello")
        assert isinstance(msg, Widget)

    def test_draw_centered(self, canvas):
        msg = TickerMessage(
            text="This is a message",
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
        )
        _, cursor_pos = msg.draw(canvas)
        assert cursor_pos == 160  # centered fills canvas width

    def test_draw_uncentered(self, canvas):
        msg = TickerMessage(
            text="This is a message",
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
            center=False,
        )
        _, cursor_pos = msg.draw(canvas)
        # 17 chars * 6px = 102px text + 6px padding = 108
        assert cursor_pos == 108

    def test_draw_overflow_not_centered(self, canvas):
        long_text = "This is a message" * 10
        msg = TickerMessage(
            text=long_text,
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
        )
        _, cursor_pos = msg.draw(canvas)
        # 170 chars * 6px = 1020px + 6px padding = 1026
        assert cursor_pos == 1026

    def test_draw_with_font_color_kwarg(self, canvas):
        msg = TickerMessage(
            text="test",
            font=FONT_DEFAULT,
            font_color=DEFAULT_COLOR,
        )
        # Should use the kwarg color, not the instance color
        canvas2, _ = msg.draw(canvas, font_color=RGB_WHITE)
        assert canvas2 is canvas

    def test_draw_returns_canvas(self, canvas):
        msg = TickerMessage(text="hi")
        result_canvas, _ = msg.draw(canvas)
        assert result_canvas is canvas

    def test_emoji_detected_only_for_slug_pattern(self):
        # Real emoji slugs trigger the emoji renderer
        assert TickerMessage(text=":taco: lunch")._has_emoji is True
        assert TickerMessage(text="hi :baseball:")._has_emoji is True

    def test_url_does_not_trigger_emoji_path(self):
        # Two-colon strings that are NOT emoji slugs (URLs, timestamps,
        # "key: value: more") must not be routed through the emoji renderer.
        assert TickerMessage(text="https://x.com/path")._has_emoji is False
        assert TickerMessage(text="Now: 12:30 PM")._has_emoji is False
        assert TickerMessage(text="A: B: C")._has_emoji is False

    def test_emoji_pattern_rejects_uppercase_and_digits(self):
        # Pattern is :[a-z_]+: — uppercase or digits in the slug shouldn't match.
        assert TickerMessage(text=":Taco: lunch")._has_emoji is False
        assert TickerMessage(text=":taco1: lunch")._has_emoji is False


class TestTickerCountdown:
    def test_conforms_to_widget_protocol(self):
        cd = TickerCountdown(text="Test", countdown_date=date(2030, 1, 1))
        assert isinstance(cd, Widget)

    def test_draw_shows_days(self, canvas):
        future = date(2099, 12, 31)
        cd = TickerCountdown(
            text="Future",
            countdown_date=future,
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
        )
        _, cursor_pos = cd.draw(canvas)
        # Should render without error and return a position
        assert cursor_pos > 0

    def test_draw_past_date_negative_days(self, canvas):
        past = date(2020, 1, 1)
        cd = TickerCountdown(
            text="Past",
            countdown_date=past,
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
        )
        # Should not raise, just show negative days
        _, cursor_pos = cd.draw(canvas)
        assert cursor_pos > 0


class TestBgColor:
    def test_bg_color_default_is_none(self):
        msg = TickerMessage(text="hi")
        assert msg.bg_color is None

    def test_bg_color_accepts_color(self):
        from rgbmatrix.graphics import Color

        bg = Color(20, 40, 60)
        msg = TickerMessage(text="hi", bg_color=bg)
        assert msg.bg_color is bg

    def test_countdown_bg_color_default_is_none(self):
        cd = TickerCountdown(text="X", countdown_date=date(2099, 1, 1))
        assert cd.bg_color is None

    def test_countdown_accepts_bg_color(self):
        from rgbmatrix.graphics import Color

        cd = TickerCountdown(
            text="X", countdown_date=date(2099, 1, 1), bg_color=Color(1, 2, 3)
        )
        assert cd.bg_color.red == 1


class TestTickerMessageColorProvider:
    """TickerMessage materializes a Color from font_color (a
    ColorProvider) per draw call. Per-char providers iterate chars."""

    def test_constructor_wraps_raw_color_in_constant_provider(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor
        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage(text="HELLO", font_color=Color(255, 0, 0))
        assert isinstance(widget.font_color, _ConstantColor)

    def test_constructor_passes_through_existing_provider(self):
        from led_ticker.color_providers import Rainbow
        from led_ticker.widgets.message import TickerMessage

        rainbow = Rainbow()
        widget = TickerMessage(text="HELLO", font_color=rainbow)
        assert widget.font_color is rainbow

    def test_advance_frame_increments_count(self):
        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage(text="HI")
        assert widget._frame_count == 0
        widget.advance_frame()
        assert widget._frame_count == 1


class TestTickerMessageAnimation:
    """`animation` field consumed by TickerMessage's draw — typewriter
    slices, bounce repositions."""

    def test_typewriter_set_via_constructor(self):
        from led_ticker.animations import Typewriter
        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage(text="HELLO", animation=Typewriter())
        assert isinstance(widget.animation, Typewriter)

    def test_no_animation_by_default(self):
        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage(text="HELLO")
        assert widget.animation is None


class TestTypewriterPlusPerCharProvider:
    """Tripwire: animation + per-char ColorProvider compose. Typewriter
    slices `visible_text`; per-char rainbow renders each visible char
    in its own hue. Smoke config §13 demos this; this test pins the
    composition at the unit level so a future refactor can't silently
    break either half (e.g. running the provider against `full_text`
    instead of `visible_text`, or skipping the per-char branch when
    animation is set)."""

    def test_typewriter_slices_text_and_per_char_rainbow_runs(self):
        from rgbmatrix import _StubCanvas

        from led_ticker.animations import Typewriter
        from led_ticker.widgets.message import TickerMessage

        # Tracking provider: per_char=True (mirrors Rainbow), records
        # every (frame, char_index, total_chars) it's asked for.
        class _TrackingProvider:
            per_char = True

            def __init__(self) -> None:
                self.calls: list[tuple[int, int, int]] = []

            def color_for(self, frame, char_index, total_chars):
                from rgbmatrix.graphics import Color

                self.calls.append((frame, char_index, total_chars))
                # Different color per char — value doesn't matter for
                # the assertion, just needs to be a Color.
                return Color((char_index * 60) % 256, 100, 200)

        provider = _TrackingProvider()
        widget = TickerMessage(
            text="ABCDE", font_color=provider, animation=Typewriter(frames_per_char=3)
        )
        # frame=3 with frames_per_char=3 → typewriter reveals 2 chars
        # (progress = (3//3)+1 = 2). The +1 in the formula means frame=0
        # already shows 1 char.
        widget._frame_count = 3
        canvas = _StubCanvas(width=160, height=16)

        widget.draw(canvas)

        # Per-char branch ran (provider got called per character).
        assert len(provider.calls) == 2, (
            f"Expected 2 per-char color_for calls (typewriter sliced "
            f"'ABCDE' to 2 chars at frame=3); got {len(provider.calls)}: "
            f"{provider.calls!r}"
        )
        # Char indices are 0..1 — proves typewriter sliced visible_text
        # rather than running over the full string.
        char_indices = [c[1] for c in provider.calls]
        assert char_indices == [0, 1], char_indices
        # Frame value passed through from _frame_count (drives rainbow
        # sweep over time).
        assert all(c[0] == 3 for c in provider.calls)
        # `total_chars` is anchored to FULL message length (5), not
        # the visible slice (2). This makes a per-char provider's hue
        # stable as typewriter reveals more chars — char 0's hue at
        # frame=3 is the same hue char 0 will have at frame=15 when
        # the full word is shown. Mirrors the image-widget contract.
        assert all(c[2] == 5 for c in provider.calls), (
            f"Expected total_chars=5 (full 'ABCDE' length, anchored); "
            f"got {[c[2] for c in provider.calls]!r}. If this fails "
            f"because TickerMessage reverted to passing the visible "
            f"slice length, see the comment in TickerMessage.draw "
            f"about hue anchoring."
        )

    def test_typewriter_overflow_returns_full_content_width(self):
        """Bug-fix tripwire: when typewriter is set on a message that
        overflows the canvas, draw() must return cursor_pos based on
        FULL content width — not the visible slice — so the engine's
        scroll detection (`cursor_pos > canvas.width` in
        `_swap_and_scroll`) fires correctly. Without this, frame=0
        (slice="R") reports a tiny cursor_pos, engine picks held-text,
        typewriter reveals chars past the right edge, and the message
        never scrolls. Hardware-observed bug on smoke §4."""
        from rgbmatrix import _StubCanvas

        from led_ticker.animations import Typewriter
        from led_ticker.widgets.message import TickerMessage

        long_text = "RAINBOW TYPES OUT"  # 17 chars × 6 logical ≈ 102 px
        widget = TickerMessage(text=long_text, animation=Typewriter(frames_per_char=3))
        widget._frame_count = 0  # only "R" visible
        canvas = _StubCanvas(width=64, height=16)

        _, cursor_pos = widget.draw(canvas)

        assert cursor_pos > canvas.width, (
            f"Expected cursor_pos > canvas.width ({canvas.width}) so "
            f"engine detects overflow; got {cursor_pos}. Without this, "
            f"typewriter at frame=0 reports a tiny cursor_pos and the "
            f"engine picks the held-text path — message overflows the "
            f"canvas with no scroll to recover."
        )

    def test_typewriter_no_overflow_does_not_falsely_trigger_scroll(self):
        """Counter-test: short text + typewriter must NOT report
        overflow. The fix should reflect FULL content width, not
        canvas.width — and a 5-char message at 6 logical px each
        (~30 px) on a 64-wide canvas fits comfortably."""
        from rgbmatrix import _StubCanvas

        from led_ticker.animations import Typewriter
        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage(text="HI", animation=Typewriter())
        widget._frame_count = 6
        canvas = _StubCanvas(width=64, height=16)

        _, cursor_pos = widget.draw(canvas)

        # "HI" fits — cursor_pos should NOT exceed canvas.width;
        # engine should pick the held-text path.
        assert cursor_pos <= canvas.width

    def test_typewriter_complete_renders_full_text_per_char(self):
        """After enough frames for typewriter to reveal everything,
        the full message is rendered per-char."""
        from rgbmatrix import _StubCanvas

        from led_ticker.animations import Typewriter
        from led_ticker.widgets.message import TickerMessage

        class _TrackingProvider:
            per_char = True

            def __init__(self) -> None:
                self.calls: list[tuple[int, int, int]] = []

            def color_for(self, frame, char_index, total_chars):
                from rgbmatrix.graphics import Color

                self.calls.append((frame, char_index, total_chars))
                return Color(255, 255, 255)

        provider = _TrackingProvider()
        widget = TickerMessage(
            text="ABCDE", font_color=provider, animation=Typewriter(frames_per_char=3)
        )
        # frame=15 → 15 // 3 = 5 chars revealed (full string).
        widget._frame_count = 15
        canvas = _StubCanvas(width=160, height=16)

        widget.draw(canvas)

        assert len(provider.calls) == 5
        assert [c[1] for c in provider.calls] == [0, 1, 2, 3, 4]

    def test_typewriter_anchors_total_chars_to_full_message_with_emoji(self):
        """Tripwire for the emoji branch: when message contains emoji
        slugs and typewriter is mid-cycle, `total_chars` passed to the
        per-char provider must be the FULL message's text-char count
        (excluding emoji slugs), not the visible slice's text-char
        count. Otherwise per-char hues drift as more chars reveal.
        Mirrors `TestImageTypewriter` in test_image_base.py — both
        widgets must use the same anchoring contract."""
        from rgbmatrix import _StubCanvas

        from led_ticker.animations import Typewriter
        from led_ticker.widgets.message import TickerMessage

        class _TrackingProvider:
            per_char = True

            def __init__(self) -> None:
                self.calls: list[tuple[int, int, int]] = []

            def color_for(self, frame, char_index, total_chars):
                from rgbmatrix.graphics import Color

                self.calls.append((frame, char_index, total_chars))
                return Color(255, 255, 255)

        provider = _TrackingProvider()
        # Full message: "AB:star:CD" → 4 text chars + 1 emoji.
        # `count_text_chars` returns 4 (excludes emoji).
        widget = TickerMessage(
            text="AB:star:CD",
            font_color=provider,
            animation=Typewriter(frames_per_char=3),
        )
        # frame=3 → typewriter shows ~2 visible chars ("AB"). The
        # emoji slug counts as one render unit too, but the per-char
        # provider is invoked for TEXT chars only (sprites get sprite
        # colors).
        widget._frame_count = 3
        canvas = _StubCanvas(width=160, height=16)

        widget.draw(canvas)

        assert provider.calls, (
            "Per-char provider was never called — emoji branch may have "
            "skipped the per-char path or rendered nothing."
        )
        # Each call's `total_chars` is the FULL message's text-char
        # count (4: A, B, C, D — emoji excluded), NOT the visible slice's.
        assert all(c[2] == 4 for c in provider.calls), (
            f"Expected total_chars=4 (full text-char count of "
            f"'AB:star:CD' excluding emoji); got "
            f"{[c[2] for c in provider.calls]!r}. If this fails, "
            f"TickerMessage's emoji branch likely stopped passing "
            f"`total_chars=count_text_chars(self.text)` to "
            f"draw_with_emoji and the hue-anchoring contract has "
            f"diverged from the image-widget side."
        )


class TestTickerCountdownColorProvider:
    def test_constructor_wraps_raw_color_in_constant_provider(self):
        from datetime import date

        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor
        from led_ticker.widgets.message import TickerCountdown

        widget = TickerCountdown(
            text="Days", countdown_date=date(2027, 1, 1), font_color=Color(255, 0, 0)
        )
        assert isinstance(widget.font_color, _ConstantColor)

    def test_advance_frame_increments_count(self):
        from datetime import date

        from led_ticker.widgets.message import TickerCountdown

        widget = TickerCountdown(text="Days", countdown_date=date(2027, 1, 1))
        assert widget._frame_count == 0
        widget.advance_frame()
        assert widget._frame_count == 1

    def test_per_char_provider_iterates_chars(self):
        """Tripwire: TickerCountdown with a per-char provider must
        iterate chars (rainbow / gradient render with per-character
        hue offsets), not materialize once at idx=0."""
        from datetime import date

        from rgbmatrix import _StubCanvas

        from led_ticker.widgets.message import TickerCountdown

        class _TrackingProvider:
            per_char = True

            def __init__(self) -> None:
                self.calls: list[tuple[int, int, int]] = []

            def color_for(self, frame, char_index, total_chars):
                from rgbmatrix.graphics import Color

                self.calls.append((frame, char_index, total_chars))
                return Color(255, 255, 255)

        provider = _TrackingProvider()
        widget = TickerCountdown(
            text="Days", countdown_date=date(2027, 1, 1), font_color=provider
        )
        canvas = _StubCanvas(width=160, height=16)

        widget.draw(canvas)

        # "Days: <N>" → at least 7 chars: D,a,y,s,:,space,digit(s).
        assert len(provider.calls) >= 7, (
            f"Expected per-char iteration; got {len(provider.calls)} "
            f"call(s). TickerCountdown is materializing the provider "
            f"once at char_index=0 instead of dispatching to "
            f"draw_text_per_char."
        )
        char_indices = [c[1] for c in provider.calls]
        # Indices are 0..N-1 contiguous.
        assert char_indices == list(range(len(provider.calls))), char_indices
        # total_chars matches the rendered length on every call.
        total = len(provider.calls)
        assert all(c[2] == total for c in provider.calls)


class TestHiresPerCharCursorMatchesHolistic:
    """Regression: HiresFont per-char rendering must return the same
    `cursor_pos` as `get_text_width(font, message, canvas)` on the
    SAME canvas, otherwise scroll detection in `_swap_and_scroll`
    disagrees with the visible per-char render and text gets drawn
    off-canvas without triggering scroll.

    Tripwire for the on-hardware bug where "INTER BOLD RAINBOW" with
    Inter-Bold @ 24 measured at 64 logical (canvas.width) but the
    per-char loop accumulated 72 logical worth of ceil-rounded
    advances — last char "W" rendered at logical x=68 → real x=272,
    off-screen, no scroll triggered."""

    def test_per_char_cursor_pos_matches_holistic_measure(self):
        from rgbmatrix import _StubCanvas

        from led_ticker.color_providers import Rainbow
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.widgets.message import TickerMessage

        font = resolve_font("Inter-Bold", 24)
        widget = TickerMessage(
            text="INTER BOLD RAINBOW",
            font=font,
            font_color=Rainbow(),
            padding=0,  # remove end-padding to compare cursor_pos directly
        )
        real = _StubCanvas(width=256, height=64)
        canvas = ScaledCanvas(real, scale=4)

        # Holistic measure (one ceil-div on real-px total)
        holistic = get_text_width(font, "INTER BOLD RAINBOW", padding=0, canvas=canvas)

        # Per-char render path: ask the widget to draw and return cursor_pos.
        _, cursor_pos = widget.draw(canvas, cursor_pos=0)

        assert cursor_pos == holistic, (
            f"Per-char cursor drift: holistic={holistic}, returned={cursor_pos}. "
            f"Sum-of-ceils accumulation can overshoot ceil-of-sum and break "
            f"scroll detection."
        )


class TestBaselineCache:
    """compute_baseline is frame-invariant — result depends only on the
    font metrics and canvas dimensions, both fixed within a section.
    Cache it after the first draw to avoid recomputing per tick."""

    def test_ticker_message_baseline_computed_once(self, canvas, monkeypatch):
        import led_ticker.widgets.message as message_mod
        from led_ticker.widgets.message import TickerMessage

        calls: list = []
        original = message_mod.compute_baseline

        def _track(*args, **kwargs):
            calls.append(args)
            return original(*args, **kwargs)

        monkeypatch.setattr(message_mod, "compute_baseline", _track)

        widget = TickerMessage(text="Hello")
        widget.draw(canvas)
        widget.draw(canvas)
        widget.draw(canvas)

        assert len(calls) == 1, (
            f"compute_baseline called {len(calls)} times"
            " — should be cached after first draw"
        )

    def test_ticker_countdown_baseline_computed_once(self, canvas, monkeypatch):
        from datetime import date

        import led_ticker.widgets.message as message_mod
        from led_ticker.widgets.message import TickerCountdown

        calls: list = []
        original = message_mod.compute_baseline

        def _track(*args, **kwargs):
            calls.append(args)
            return original(*args, **kwargs)

        monkeypatch.setattr(message_mod, "compute_baseline", _track)

        widget = TickerCountdown(text="Days", countdown_date=date(2027, 1, 1))
        widget.draw(canvas)
        widget.draw(canvas)
        widget.draw(canvas)

        assert len(calls) == 1, (
            f"compute_baseline called {len(calls)} times"
            " — should be cached after first draw"
        )
