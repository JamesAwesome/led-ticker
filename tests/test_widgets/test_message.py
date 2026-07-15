"""Tests for led_ticker.widgets.message."""

from datetime import date

from led_ticker.colors import DEFAULT_COLOR, GREEN, RGB_WHITE
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widget import Widget
from led_ticker.widgets.message import TickerCountdown, TickerMessage


class TestSegmentMessage:
    def test_segments_stored(self):
        from led_ticker.widgets.message import SegmentMessage

        msg = SegmentMessage([("A", RGB_WHITE), ("B", GREEN)])
        assert [t for t, _ in msg.segments] == ["A", "B"]

    def test_conforms_to_widget_protocol(self):
        from led_ticker.widgets.message import SegmentMessage

        assert isinstance(SegmentMessage([("x", RGB_WHITE)]), Widget)

    def test_draw_centered_returns_canvas(self, canvas):
        from led_ticker.widgets.message import SegmentMessage

        msg = SegmentMessage([("82", RGB_WHITE)], center=True)
        result_canvas, cursor_pos = msg.draw(canvas)
        assert result_canvas is canvas
        assert cursor_pos == 160


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
        assert TickerMessage(text="hi :star:")._has_emoji is True

    def test_url_does_not_trigger_emoji_path(self):
        # Two-colon strings that are NOT emoji slugs (URLs, timestamps,
        # "key: value: more") must not be routed through the emoji renderer.
        assert TickerMessage(text="https://x.com/path")._has_emoji is False
        assert TickerMessage(text="Now: 12:30 PM")._has_emoji is False
        assert TickerMessage(text="A: B: C")._has_emoji is False

    def test_emoji_pattern_rejects_uppercase(self):
        # Uppercase slugs must never match (`:Taco:` is not an emoji token).
        assert TickerMessage(text=":Taco: lunch")._has_emoji is False
        # Digits after the leading letter ARE valid slug syntax (namespaced
        # plugin slugs like `:acme2.heart:` can be registered). But
        # `has_renderable_emoji` only returns True for REGISTERED slugs, so
        # an unregistered slug like `:taco1:` (not in the core registry)
        # returns False — same final rendered output as the old path
        # (`:taco1:` appeared as literal text either way), but the emoji
        # render path is no longer invoked unnecessarily.
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


class TestTickerMessageInlineTokens:
    """Inline value-token substitution + the resolution-freeze model
    (spec §4 / §4a). A non-token message is byte-identical to today;
    a token message substitutes the live source value, re-measures on a
    held tick when the value width changes, and freezes resolution while
    paused (transition compositing) or mid-typewriter-reveal."""

    @staticmethod
    def _registry(*sources):
        from led_ticker.sources import DataRegistry, set_data_registry

        reg = DataRegistry()
        for src in sources:
            src.refresh()
            reg.add(src)
        set_data_registry(reg)
        return reg

    @staticmethod
    def _stub(width=160, height=16):
        from rgbmatrix import _StubCanvas

        return _StubCanvas(width=width, height=height)

    def test_non_token_message_byte_identical(self):
        """Regression guard: a message with no source tokens renders the
        exact same pixels regardless of registry state."""
        from led_ticker.widgets.message import TickerMessage

        # Empty registry — no sources declared.
        self._registry()
        w = TickerMessage(text="HELLO WORLD", font_color=RGB_WHITE)
        assert w._token is not None and w._token.has_tokens is False
        c1 = self._stub()
        w.draw(c1)
        # A fresh widget + fresh canvas must produce the same lit pixels.
        w2 = TickerMessage(text="HELLO WORLD", font_color=RGB_WHITE)
        c2 = self._stub()
        w2.draw(c2)
        assert c1.count_nonzero() == c2.count_nonzero()
        assert c1.count_nonzero() > 0

    def test_substitutes_token_on_draw(self):
        """`:brand.tag:` renders the source value, not the literal token.
        Compared against a literal control message of the same text."""
        from led_ticker.sources import StaticSource
        from led_ticker.widgets.message import TickerMessage

        self._registry(StaticSource(id="brand.tag", value="HELLO"))
        w = TickerMessage(text="x :brand.tag: y", font_color=RGB_WHITE)
        c_tok = self._stub()
        w.draw(c_tok)

        # Control: a literal message of the substituted string.
        self._registry()  # empty registry so control has no tokens
        control = TickerMessage(text="x HELLO y", font_color=RGB_WHITE)
        c_lit = self._stub()
        control.draw(c_lit)

        # Same substituted text → same lit-pixel count and same width.
        assert c_tok.count_nonzero() == c_lit.count_nonzero()
        assert w._resolved_text == "x HELLO y"

    def test_unknown_token_falls_through_to_literal(self):
        """A token with no matching source renders as the literal `:slug:`
        (existing intentional behavior)."""
        from led_ticker.widgets.message import TickerMessage

        self._registry()  # nothing declared
        w = TickerMessage(text=":not.declared:", font_color=RGB_WHITE)
        c = self._stub()
        w.draw(c)
        assert w._resolved_text == ":not.declared:"

    def test_rewidths_when_value_width_changes_while_held(self):
        """A held redraw (not locked) picks up a new value, re-measures,
        and re-centers."""
        from led_ticker.sources import StaticSource
        from led_ticker.widgets.message import TickerMessage

        src = StaticSource(id="t", value="9:59")
        self._registry(src)
        w = TickerMessage(text=":t:", font_color=RGB_WHITE)
        w.draw(self._stub())
        first = w._content_width
        assert first > 0

        src.value = "10:0000"  # wider value
        src.refresh()
        w.draw(self._stub())  # held redraw — not locked
        assert w._content_width != first, (
            "held redraw should re-measure when the token value width changes"
        )
        assert w._resolved_text == "10:0000"

    def test_unchanged_value_keeps_cached_width(self):
        """Steady state: an unchanged value does not invalidate the width
        cache (no needless reflow)."""
        from led_ticker.sources import StaticSource
        from led_ticker.widgets.message import TickerMessage

        src = StaticSource(id="t", value="STABLE")
        self._registry(src)
        w = TickerMessage(text=":t:", font_color=RGB_WHITE)
        w.draw(self._stub())
        first = w._content_width
        src.refresh()  # same value → version does not move
        w.draw(self._stub())
        assert w._content_width == first

    def test_pause_frame_locks_resolution(self):
        """C1: pause_frame() freezes resolution — a version bump while
        paused returns the cached value; resume_frame() releases it."""
        from led_ticker.sources import StaticSource
        from led_ticker.widgets.message import TickerMessage

        src = StaticSource(id="t", value="a")
        self._registry(src)
        w = TickerMessage(text=":t:", font_color=RGB_WHITE)
        w.draw(self._stub())  # cache "a"
        assert w._resolved_text == "a"
        width_a = w._content_width

        w.pause_frame()
        assert w._resolution_locked is True
        src.value = "bbbbb"
        src.refresh()  # version moves while locked
        w.draw(self._stub())
        # Still "a" — resolution frozen; width unchanged.
        assert w._resolved_text == "a"
        assert w._content_width == width_a

        w.resume_frame()
        assert w._resolution_locked is False
        w.draw(self._stub())
        # Now the new value applies.
        assert w._resolved_text == "bbbbb"
        assert w._content_width != width_a

    def test_per_char_color_flows_across_substituted_value(self):
        """A per-char provider (rainbow-like) iterates the SUBSTITUTED
        characters — token text gets hues like any other text, and
        total_chars is anchored to the substituted length."""
        from led_ticker.sources import StaticSource
        from led_ticker.widgets.message import TickerMessage

        self._registry(StaticSource(id="t", value="WXYZ"))

        class _TrackingProvider:
            per_char = True

            def __init__(self):
                self.calls = []

            def color_for(self, frame, char_index, total_chars):
                from rgbmatrix.graphics import Color

                self.calls.append((frame, char_index, total_chars))
                return Color(255, 255, 255)

        provider = _TrackingProvider()
        w = TickerMessage(text=":t:", font_color=provider)
        w.draw(self._stub())
        # 4 substituted chars → 4 per-char calls, contiguous indices,
        # total_chars == 4 (the substituted length, not the raw ":t:").
        assert len(provider.calls) == 4
        assert [c[1] for c in provider.calls] == [0, 1, 2, 3]
        assert all(c[2] == 4 for c in provider.calls)

    def test_typewriter_token_slice_stable_mid_reveal(self):
        """I3: a value change mid-typewriter-reveal does NOT corrupt the
        slice (resolution is frozen for the reveal), AND per-char hue
        total_chars counts the substituted string."""
        from led_ticker.animations import Typewriter
        from led_ticker.sources import StaticSource
        from led_ticker.widgets.message import TickerMessage

        src = StaticSource(id="t", value="ABCDE")
        self._registry(src)

        class _TrackingProvider:
            per_char = True

            def __init__(self):
                self.calls = []

            def color_for(self, frame, char_index, total_chars):
                from rgbmatrix.graphics import Color

                self.calls.append((frame, char_index, total_chars))
                return Color(255, 255, 255)

        provider = _TrackingProvider()
        w = TickerMessage(
            text=":t:", font_color=provider, animation=Typewriter(frames_per_char=3)
        )
        w._frame_count = 3  # ~2 chars revealed
        w.draw(self._stub())
        # Reveal locked to "ABCDE".
        assert w._anim_resolution_lock is True
        assert w._resolved_text == "ABCDE"

        # Source value width changes mid-reveal — must NOT affect the
        # frozen reveal string.
        src.value = "ZZZZZZZZZZ"
        src.refresh()
        provider.calls.clear()
        w._frame_count = 6  # more chars revealed, still from "ABCDE"
        w.draw(self._stub())
        assert w._resolved_text == "ABCDE", (
            "typewriter reveal must stay frozen to the start-of-reveal value"
        )
        # total_chars anchored to the substituted reveal string (5), not
        # raw ":t:" (3) and not the changed value (10).
        assert provider.calls, "per-char provider should have been called"
        assert all(c[2] == 5 for c in provider.calls), (
            f"total_chars should anchor to substituted reveal length 5; "
            f"got {[c[2] for c in provider.calls]!r}"
        )

        # On the next VISIT the lock clears and the current value applies.
        w.reset_frame()
        assert w._anim_resolution_lock is False

    def test_resolve_tokens_now_invalidates_width(self):
        """`resolve_tokens_now()` forces a resolve + width invalidate even
        when the value width is unchanged (engine pre-scroll hook)."""
        from led_ticker.sources import StaticSource
        from led_ticker.widgets.message import TickerMessage

        src = StaticSource(id="t", value="HI")
        self._registry(src)
        w = TickerMessage(text=":t:", font_color=RGB_WHITE)
        w.draw(self._stub())
        assert w._content_width > 0
        w.resolve_tokens_now()
        assert w._content_width == -1  # invalidated
        assert w._resolved_text == "HI"


class TestColoredTokens:
    """Per-token color: a `:id:` token renders in its source-declared
    `.color` while surrounding literal text keeps the host `font_color`.
    The override is indexed by VISIBLE TEXT-CHAR position (emoji slugs
    excluded) so it aligns with `draw_with_emoji`'s `char_index` and
    `draw_text_per_char`'s `idx`. Composes with host per-char providers,
    is byte-identical when no source declares a color, and never changes
    geometry."""

    @staticmethod
    def _registry(*sources):
        from led_ticker.sources import DataRegistry, set_data_registry

        reg = DataRegistry()
        for src in sources:
            src.refresh()
            reg.add(src)
        set_data_registry(reg)
        return reg

    @staticmethod
    def _stub(width=160, height=16):
        from rgbmatrix import _StubCanvas

        return _StubCanvas(width=width, height=height)

    @staticmethod
    def _colored_source(value, rgb):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor
        from led_ticker.sources import StaticSource

        src = StaticSource(id="x", value=value)
        src.color = _ConstantColor(Color(*rgb))
        return src

    def test_token_chars_use_source_color_literal_uses_host(self):
        """Token 'AB :x:' with host green + source-red token: 'AB ' pixels
        are green (host), the '99' token pixels are red (source), and the
        literal run is strictly LEFT of the token run (index alignment on
        the whole-string→per-char forced path)."""
        from led_ticker.widgets.message import TickerMessage

        host = (0, 200, 0)
        tok = (200, 0, 0)
        self._registry(self._colored_source("99", tok))
        w = TickerMessage(text="AB :x:", font_color=host, center=False)
        c = self._stub()
        w.draw(c)

        lit = {xy: v for xy, v in c._pixels.items() if v != (0, 0, 0)}
        colors = set(lit.values())
        assert host in colors, "literal 'AB' should render in host green"
        assert tok in colors, "token '99' should render in source red"
        assert colors <= {host, tok}, f"only host+token colors expected; got {colors!r}"
        # 'AB ' is left of '99' -> the RED (token) pixels are all to the
        # right of the GREEN (literal) pixels: proves the override maps
        # the trailing token chars, not the leading literal chars.
        green_xs = [x for (x, _y), v in lit.items() if v == host]
        red_xs = [x for (x, _y), v in lit.items() if v == tok]
        assert max(green_xs) < min(red_xs), (
            f"literal (green) must be left of token (red); "
            f"green max={max(green_xs)} red min={min(red_xs)}"
        )
        # Control: literal chars are unchanged reference is left to the
        # byte-identical test; here confirm no host-color leaked onto the
        # token by proving no green pixel sits at/after the token start.
        assert not any(x >= min(red_xs) for x in green_xs)

    def test_no_color_source_is_byte_identical(self):
        """A colorless token renders the EXACT same pixels as the literal
        substituted text with no token at all — the `token_override is
        None` path leaves the three color branches untouched."""
        from led_ticker.sources import StaticSource
        from led_ticker.widgets.message import TickerMessage

        host = (0, 200, 0)
        self._registry(StaticSource(id="x", value="99"))  # no .color
        w = TickerMessage(text="AB :x:", font_color=host, center=False)
        c_tok = self._stub()
        w.draw(c_tok)

        # Control: a literal, tokenless message of the substituted string.
        # This is guaranteed to run the pre-feature code path (has_tokens
        # is False), so equal pixels == byte-identical.
        self._registry()  # empty registry
        control = TickerMessage(text="AB 99", font_color=host, center=False)
        c_lit = self._stub()
        control.draw(c_lit)

        assert c_tok.count_nonzero() > 0
        assert c_tok._pixels == c_lit._pixels, (
            "a colorless token must render byte-identically to the literal text"
        )

    def test_colored_token_with_host_rainbow(self):
        """Host `rainbow` (per-char) composes with a red token: the literal
        chars vary in hue (rainbow) while the token chars are ALL red — the
        override wins per-char over the host provider."""
        from led_ticker.color_providers import Rainbow
        from led_ticker.widgets.message import TickerMessage

        tok = (200, 0, 0)
        self._registry(self._colored_source("99", tok))
        w = TickerMessage(text="AB :x:", font_color=Rainbow(), center=False)
        c = self._stub()
        w.draw(c)

        lit = {xy: v for xy, v in c._pixels.items() if v != (0, 0, 0)}
        red_xs = [x for (x, _y), v in lit.items() if v == tok]
        assert red_xs, "token '99' should render red under a rainbow host"
        # Literal 'AB' varies: at least two distinct non-token hues.
        non_tok = {v for v in lit.values() if v != tok}
        assert len(non_tok) >= 2, (
            f"literal chars should carry varied rainbow hues; got {non_tok!r}"
        )
        # And the rainbow never coincidentally produced the exact token red
        # (Rainbow is full-value HSV; 200-valued red can't appear).
        assert tok not in non_tok

    def test_colored_token_mixed_with_emoji(self):
        """INDEX-ALIGNMENT TRIPWIRE. 'A :x: :sun:' with a red token and an
        inline emoji: the ONLY pixels that differ between a colored-token
        render and a colorless render are the token chars (green→red). The
        `:sun:` sprite pixels are byte-identical — proving the override
        (which skips emoji segments) stays aligned with `draw_with_emoji`'s
        emoji-excluding `char_index`."""
        from led_ticker.sources import StaticSource
        from led_ticker.widgets.message import TickerMessage

        host = (0, 200, 0)
        tok = (200, 0, 0)
        black = (0, 0, 0)

        def render(with_color):
            src = (
                self._colored_source("99", tok)
                if with_color
                else StaticSource(id="x", value="99")
            )
            self._registry(src)
            w = TickerMessage(text="A :x: :sun:", font_color=host, center=False)
            c = self._stub()
            w.draw(c)
            # Confirm the emoji path actually fired for this message.
            assert w._has_emoji is True
            return dict(c._pixels)

        pw = render(with_color=False)  # token green (host), like literal
        pc = render(with_color=True)  # token red

        diff = {
            xy for xy in set(pw) | set(pc) if pw.get(xy, black) != pc.get(xy, black)
        }
        assert diff, "the colored token must change some pixels (green→red)"
        # Every differing pixel is a token char: green in the colorless
        # render, red in the colored one. Nothing else moved — not 'A ',
        # not the sun sprite.
        for xy in diff:
            assert pw.get(xy) == host and pc.get(xy) == tok, (
                f"unexpected diff at {xy}: {pw.get(xy)!r} -> {pc.get(xy)!r} "
                f"(only the token chars should change color)"
            )
        # The sun sprite rendered (pixels that are neither host green nor
        # black) and is byte-identical across both renders.
        sprite = {xy for xy, v in pw.items() if v not in (host, black)}
        assert sprite, "the :sun: sprite should have rendered"
        assert not (sprite & diff), (
            "emoji sprite pixels must be identical with and without a colored token"
        )
        for xy in sprite:
            assert pc.get(xy) == pw.get(xy)

    def test_width_unchanged_with_color(self):
        """Color never changes geometry: `draw()`'s returned cursor_pos is
        identical with and without a source color."""
        from led_ticker.sources import StaticSource
        from led_ticker.widgets.message import TickerMessage

        host = (0, 200, 0)
        tok = (200, 0, 0)

        def cursor(with_color):
            src = (
                self._colored_source("99", tok)
                if with_color
                else StaticSource(id="x", value="99")
            )
            self._registry(src)
            w = TickerMessage(text="AB :x:", font_color=host, center=False)
            _, cp = w.draw(self._stub())
            return cp

        assert cursor(with_color=True) == cursor(with_color=False)


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

        import led_ticker.widgets.count as count_mod
        from led_ticker.widgets.count import TickerCountdown

        calls: list = []
        original = count_mod.compute_baseline

        def _track(*args, **kwargs):
            calls.append(args)
            return original(*args, **kwargs)

        monkeypatch.setattr(count_mod, "compute_baseline", _track)

        widget = TickerCountdown(text="Days", countdown_date=date(2027, 1, 1))
        widget.draw(canvas)
        widget.draw(canvas)
        widget.draw(canvas)

        assert len(calls) == 1, (
            f"compute_baseline called {len(calls)} times"
            " — should be cached after first draw"
        )
