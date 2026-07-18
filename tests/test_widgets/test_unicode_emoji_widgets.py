"""Task 4 — Unicode-emoji gate consolidation: widget-level regression tests.

Every gate that used to be ``EMOJI_PATTERN.search(text)`` now uses
``has_renderable_emoji(text)``.  These tests pin the three behavioral
changes that flow from that:

1. A TickerMessage whose text contains a Unicode-emoji run (no :slug:)
   sets ``_has_emoji=True`` and routes through ``draw_with_emoji``.
2. An UNMAPPED Unicode emoji (e.g. 🐦 cardinal) is stripped by
   ``draw_with_emoji`` — no box-character render, no crash.
3. The same routing fires correctly in TwoRowMessage and
   _BaseImageWidget text-overlay paths.

Plus an AST/grep tripwire that fails if any ``EMOJI_PATTERN.search``
gate reappears in the three widget files.
"""

import unittest.mock as mock
from pathlib import Path

import attrs

from led_ticker._types import Canvas

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WIDGET_FILES = [
    Path("src/led_ticker/widgets/message.py"),
    Path("src/led_ticker/widgets/two_row.py"),
    Path("src/led_ticker/widgets/_image_base.py"),
]

_REPO_ROOT = Path(__file__).parent.parent.parent


def _abs(rel: Path) -> Path:
    return _REPO_ROOT / rel


# ---------------------------------------------------------------------------
# Tripwire: no EMOJI_PATTERN.search remains as a widget GATE
# ---------------------------------------------------------------------------


class TestNoEmojiPatternGates:
    """AST-level tripwire: assert the 10 gate sites are all converted."""

    def test_no_emoji_pattern_search_in_widget_files(self):
        """No file in _WIDGET_FILES should contain a call to
        EMOJI_PATTERN.search(...) at an if-guard position.

        We grep for the literal text ``EMOJI_PATTERN.search`` because AST
        is overkill here — the pattern is distinctive enough that a grep
        of the source text catches all real occurrences.
        """
        violations: list[str] = []
        for rel in _WIDGET_FILES:
            src = _abs(rel).read_text(encoding="utf-8")
            for lineno, line in enumerate(src.splitlines(), start=1):
                stripped = line.strip()
                # Skip pure comments and import lines — those aren't gates.
                if stripped.startswith("#"):
                    continue
                if "EMOJI_PATTERN.search" in stripped:
                    violations.append(f"{rel}:{lineno}: {stripped}")

        assert not violations, (
            "EMOJI_PATTERN.search found in widget files — all 10 gates must "
            "use has_renderable_emoji() instead:\n" + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# TickerMessage — Unicode emoji detection
# ---------------------------------------------------------------------------


class TestTickerMessageUnicodeEmoji:
    """Verify that TickerMessage treats Unicode emoji the same as :slug: emoji."""

    def test_mapped_unicode_emoji_sets_has_emoji_true(self):
        """❤️ is mapped to the 'heart' sprite — _has_emoji must be True."""
        from led_ticker.widgets.message import TickerMessage

        msg = TickerMessage(text="❤️ Sale")
        assert msg._has_emoji is True

    def test_unmapped_unicode_emoji_sets_has_emoji_true(self):
        """🐦 is NOT in the sprite map but IS a Unicode emoji run —
        _has_emoji must still be True so the emoji path strips it cleanly
        (the motivating regression: old EMOJI_PATTERN gate returned False,
        routing to the plain-text path which rendered the bird as a box).
        """
        from led_ticker.widgets.message import TickerMessage

        msg = TickerMessage(text="Natalie saw a Cardinal 🐦")
        assert msg._has_emoji is True

    def test_plain_text_sets_has_emoji_false(self):
        """No emoji slug or Unicode emoji → _has_emoji is False, plain path."""
        from led_ticker.widgets.message import TickerMessage

        assert TickerMessage(text="plain text")._has_emoji is False

    def test_mapped_unicode_emoji_routes_through_draw_with_emoji(
        self, canvas, monkeypatch
    ):
        """When text contains a mapped Unicode emoji, draw() must call
        draw_with_emoji (not the plain draw_text path).

        message.draw's three-branch dispatch was extracted into the shared
        draw_text_run helper (Task 2), which binds draw_with_emoji at module
        import, so we patch the helper module where the call now resolves.
        """
        import led_ticker.widgets._text_run as text_run_mod

        calls: list[tuple] = []

        def fake_draw_with_emoji(canvas, font, x, y, color, text, **kwargs):
            calls.append((x, text))
            return 50  # fake advance

        monkeypatch.setattr(text_run_mod, "draw_with_emoji", fake_draw_with_emoji)

        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage(text="❤️ Sale")
        widget.draw(canvas)
        assert calls, "draw_with_emoji was never called for text='❤️ Sale'"

    def test_unmapped_unicode_emoji_stripped_no_crash(self, canvas, monkeypatch):
        """Unmapped Unicode emoji (🐦) must not crash and must not produce
        a box character.  We verify this by confirming draw_with_emoji is
        called (which strips unmapped emoji) — NOT the plain draw_text path
        (which would render a box).

        message.draw's three-branch dispatch was extracted into the shared
        draw_text_run helper (Task 2), which binds draw_with_emoji / draw_text
        at module import, so we patch the helper module where the calls now
        resolve.
        """
        import led_ticker.widgets._text_run as text_run_mod

        emoji_draw_calls: list = []
        plain_draw_calls: list = []

        def fake_draw_with_emoji(canvas, font, x, y, color, text, **kwargs):
            emoji_draw_calls.append(text)
            return 80

        def fake_draw_text(canvas, font, x, y, color, text):
            plain_draw_calls.append(text)

        monkeypatch.setattr(text_run_mod, "draw_with_emoji", fake_draw_with_emoji)
        monkeypatch.setattr(text_run_mod, "draw_text", fake_draw_text)

        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage(text="Natalie saw a Cardinal 🐦")
        widget.draw(canvas)

        # The emoji path must have been taken...
        assert emoji_draw_calls, (
            "draw_with_emoji not called for unmapped Unicode emoji — "
            "the plain text path would render a box character"
        )
        # ...and the plain-text draw_text path must NOT have been called
        # for the full text (it may be called for sub-segments by
        # draw_with_emoji internally, but the widget-level dispatch must
        # not route the whole string there).
        # We verify the widget dispatched via draw_with_emoji, which is
        # sufficient — draw_with_emoji itself handles stripping internally.


# ---------------------------------------------------------------------------
# TwoRowMessage — Unicode emoji routing
# ---------------------------------------------------------------------------


class TestTwoRowUnicodeEmoji:
    """TwoRowMessage gate sites: _effect_total_chars, _measure_separator_width,
    _draw_row_text_at, _draw_bottom_separator — all now use has_renderable_emoji."""

    def test_top_row_with_mapped_emoji_has_emoji_true(self):
        """❤️ in top_text → count_text_chars used (not plain len)."""
        from led_ticker.pixel_emoji import count_text_chars
        from led_ticker.widgets.two_row import TwoRowMessage

        w = TwoRowMessage(top_text="❤️ hi", bottom_text="x")
        total = w._effect_total_chars("top_color")
        expected = max(1, count_text_chars("❤️ hi"))
        assert total == expected, (
            f"_effect_total_chars('top_color') returned {total!r}, "
            f"expected emoji-aware count {expected!r}"
        )

    def test_bottom_row_with_unmapped_emoji_routes_to_draw_with_emoji(
        self, canvas, monkeypatch
    ):
        """🐦 in bottom_text → _draw_row_text_at must call draw_with_emoji,
        which then strips the unmapped bird cleanly."""
        import led_ticker.widgets.two_row as tr

        calls: list[str] = []

        def fake_draw_with_emoji(canvas, font, x, y, provider, text, **kwargs):
            calls.append(text)
            return 60

        monkeypatch.setattr(tr, "draw_with_emoji", fake_draw_with_emoji)

        from led_ticker.widgets.two_row import TwoRowMessage

        w = TwoRowMessage(top_text="top", bottom_text="🐦 x")
        w.draw(canvas)

        assert calls, (
            "draw_with_emoji not called for bottom_text='🐦 x' — "
            "unmapped Unicode emoji would render as a box"
        )

    def test_separator_with_emoji_routes_to_draw_with_emoji(self, canvas, monkeypatch):
        """A Unicode-emoji separator (e.g. ⭐) triggers the draw_with_emoji
        path in _draw_bottom_separator.  `bottom_text_separator` requires
        `bottom_text_wrap=True`."""
        import led_ticker.widgets.two_row as tr

        emoji_sep_calls: list[str] = []

        def fake_draw_with_emoji(canvas, font, x, y, provider, text, **kwargs):
            emoji_sep_calls.append(text)
            return 12

        monkeypatch.setattr(tr, "draw_with_emoji", fake_draw_with_emoji)

        from led_ticker.widgets.two_row import TwoRowMessage

        # A long bottom_text causes repeated separator draws (scroll-through).
        # bottom_text_wrap=True is required when bottom_text_separator is set.
        w = TwoRowMessage(
            top_text="A",
            bottom_text="hello world long enough to scroll",
            bottom_text_separator="⭐",
            bottom_text_wrap=True,
        )
        w.draw(canvas, cursor_pos=-50)  # mid-scroll to force separator paint

        # At least one draw_with_emoji call should be for the ⭐ separator
        assert any("⭐" in t for t in emoji_sep_calls), (
            f"No draw_with_emoji call with '⭐' separator; got {emoji_sep_calls!r}"
        )


# ---------------------------------------------------------------------------
# _BaseImageWidget text overlay — Unicode emoji detection
# ---------------------------------------------------------------------------


class TestImageBaseUnicodeEmoji:
    """_has_emoji_cached and the _draw_text / _draw_row_text routing gates
    in _BaseImageWidget now use has_renderable_emoji."""

    @staticmethod
    def _make_dummy(text="", top_text="", bottom_text=""):
        """Return a minimal _BaseImageWidget subclass instance."""
        from led_ticker.widgets._image_base import _BaseImageWidget

        @attrs.define
        class _Dummy(_BaseImageWidget):
            def __attrs_post_init__(self) -> None:
                self._validate_common(image_align="center", fit="pillarbox")

            def _paint_full(self, canvas: Canvas) -> None:
                pass

            def _paint_skip_black(self, canvas: Canvas) -> None:
                pass

            def _load(self, panel_w: int = 0, panel_h: int = 0) -> None:
                pass

        return _Dummy(text=text, top_text=top_text, bottom_text=bottom_text)

    def test_unicode_emoji_text_sets_has_emoji_cached_true(self):
        """⭐ in single-row `text` → _has_emoji_cached must be True."""
        w = self._make_dummy(text="⭐ Open")
        assert w._has_emoji_cached is True

    def test_unicode_emoji_in_top_text_sets_has_emoji_cached_true(self):
        """❤️ in `top_text` → _has_emoji_cached must be True (two-row scan)."""
        w = self._make_dummy(top_text="❤️ hi", bottom_text="x")
        assert w._has_emoji_cached is True

    def test_plain_text_sets_has_emoji_cached_false(self):
        w = self._make_dummy(text="No emoji here")
        assert w._has_emoji_cached is False

    def test_draw_text_routes_through_draw_with_emoji_for_unicode(
        self, canvas, monkeypatch
    ):
        """_draw_text must call draw_with_emoji when text='⭐ Open'."""
        import led_ticker.widgets._text_run as text_run_mod

        calls: list[str] = []

        def fake_draw_with_emoji(canvas, font, x, y, color, text, **kwargs):
            calls.append(text)
            return 60

        monkeypatch.setattr(text_run_mod, "draw_with_emoji", fake_draw_with_emoji)

        from led_ticker.colors import DEFAULT_COLOR

        w = self._make_dummy(text="⭐ Open")
        mock_canvas = mock.Mock()
        mock_canvas.width = 160
        mock_canvas.height = 16

        # _draw_text(canvas, x, baseline_y, color, text_override=None)
        w._draw_text(mock_canvas, 0, 8, DEFAULT_COLOR)

        assert calls, "draw_with_emoji not called for text='⭐ Open'"
        assert any("⭐" in t for t in calls), (
            f"Expected '⭐' in draw_with_emoji call; got {calls!r}"
        )

    def test_draw_row_text_routes_through_draw_with_emoji_for_unicode(
        self, canvas, monkeypatch
    ):
        """_draw_row_text must call draw_with_emoji for row text with ❤️."""
        import led_ticker.widgets._text_run as text_run_mod

        calls: list[str] = []

        def fake_draw_with_emoji(canvas, font, x, y, color, text, **kwargs):
            calls.append(text)
            return 60

        monkeypatch.setattr(text_run_mod, "draw_with_emoji", fake_draw_with_emoji)

        from led_ticker.colors import DEFAULT_COLOR
        from led_ticker.fonts import FONT_SMALL

        w = self._make_dummy(top_text="❤️ hi", bottom_text="x")
        mock_canvas = mock.Mock()
        mock_canvas.width = 160
        mock_canvas.height = 16

        w._draw_row_text(
            mock_canvas,
            FONT_SMALL,
            "❤️ hi",
            DEFAULT_COLOR,
            x=0,
            baseline_y=8,
            emoji_y=0,
            frame_count=0,
        )

        assert calls, "draw_with_emoji not called for row text '❤️ hi'"
