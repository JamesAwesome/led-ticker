# Image Text Wrap (Forever-Scroll Style) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add seamless wrap-around marquee scrolling to single-row text on `gif` and `image` widgets, with a configurable separator between repeats. Mirrors the visual feel of `forever_scroll` mode (text + separator chases itself across the panel) but scoped to per-widget text overlay rather than between-widgets layout.

**Architecture:** Three new fields on `_BaseImageWidget`: `text_wrap: bool`, `text_separator: str | None`, `text_separator_color: ColorProvider | None`. When `text_wrap = true` AND `text_align ∈ ("scroll", "scroll_over")`, the per-tick scroll branch in `_play_with_text` switches from the existing off-right→off-left marquee to a modular scroll: `cycle_width = text_width + sep_width`, `scroll_pos = (init + tick * step) % cycle_width`, draw `ceil(canvas_w / cycle) + 1` copies of `text + separator` so the panel is never empty. `text_loops` reinterprets as minimum number of cycle traversals. The separator renders through the same `_draw_text` path as the main text (full emoji + per-char-provider support) using `text_separator_color` (or `font_color` when unset). Single-row only in v1 — two-row image mode + `TwoRowMessage` wrap deferred. Reuses the existing `text_separator_color` parsing via the `_PROVIDER_COLOR_KEYS` coercion and registers it in `_FrameAware._EFFECT_ATTRS` for its own per-effect counter.

**Tech Stack:** Python 3.13, attrs, pytest, BDF + HiresFont rasterizers.

**Spec captured inline:**

- **Fields (all kw_only, default values preserve existing behavior):**
  - `text_wrap: bool = False`
  - `text_separator: str | None = None` (default `" • "` resolves at first use when `text_wrap=True` and unset; explicit `""` → two-space minimum gap, matching forever_scroll separator semantics)
  - `text_separator_color: Color | None = None` (None = inherit `font_color`; set value gets a `ColorProvider` via `_PROVIDER_COLOR_KEYS`)
- **Validation (config-load errors):**
  - `text_wrap=True` requires `text_align ∈ ("scroll", "scroll_over")` (else silent no-op)
  - `text_wrap=True` + `bottom_text != ""` → refuse (two-row scope deferred)
  - `text_separator` / `text_separator_color` set without `text_wrap=True` → refuse (signals user intent mismatch)
- **`text_loops` semantics in wrap mode:** one traversal = `cycle_width` ticks; `min_loops = max(1, text_loops)`; `n_ticks >= min_loops * cycle_width`. Same shape as existing non-wrap floor.
- **Color inheritance:**
  - `text_separator_color=None` → use the same provider as `font_color`, but read its own per-effect frame counter (registered in `_EFFECT_ATTRS`) so continuous-phase rainbow stays in phase with the main text.
  - `text_separator_color` is a whole-string color call (`color_for(frame, 0, 1)`) — separator is one "blob" at a single hue per frame. Rainbow on the main text still per-chars normally.

---

## Pre-flight

Use `superpowers:using-git-worktrees` to create an isolated workspace. Suggested name: `image-text-wrap`. Run `make test` to confirm a green baseline before Task 1.

```bash
make test
# Expect: all tests pass (1500+ at HEAD)
```

---

### Task 1: Add three fields to `_BaseImageWidget` with skeleton validation

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py` (attrs fields around line 95–105; `_validate_common` around line 254–283)
- Test: `tests/test_widgets/test_image_text_wrap.py` (new file)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_widgets/test_image_text_wrap.py`:

```python
"""Tests for text_wrap on image widgets (gif + still).

Validates field defaults, validation errors, and (in later tasks)
the seamless wrap render math. Single-row image widgets only —
two-row mode + TwoRowMessage wrap is intentionally out of scope
for v1 and validated to refuse.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from led_ticker.widgets.still import StillImage

# Reuse the shared 16×16 RGBA fixture used by other image-widget
# tests. Path is conventional; if it doesn't exist locally, this
# import-line failure surfaces the issue at test collection time.
FIXTURE = Path(__file__).parent / "fixtures" / "test_16x16.png"


def _still(**kwargs):
    """Build a StillImage with the shared fixture and kw overrides."""
    defaults = dict(path=str(FIXTURE), text="hello")
    defaults.update(kwargs)
    return StillImage(**defaults)


class TestTextWrapFieldDefaults:
    def test_text_wrap_defaults_false(self):
        w = _still()
        assert w.text_wrap is False

    def test_text_separator_defaults_none(self):
        w = _still()
        assert w.text_separator is None

    def test_text_separator_color_defaults_none(self):
        w = _still()
        assert w.text_separator_color is None


class TestTextWrapValidation:
    def test_wrap_requires_scroll_align(self):
        with pytest.raises(ValueError, match="text_wrap.*requires.*text_align"):
            _still(text_wrap=True, text_align="left")

    def test_wrap_refuses_two_row(self):
        with pytest.raises(ValueError, match="text_wrap.*not supported.*two-row"):
            _still(
                text_wrap=True,
                top_text="top",
                bottom_text="bottom",
            )

    def test_separator_without_wrap_refused(self):
        with pytest.raises(ValueError, match="text_separator.*requires.*text_wrap"):
            _still(text_separator=" * ", text_align="scroll")

    def test_separator_color_without_wrap_refused(self):
        with pytest.raises(
            ValueError, match="text_separator_color.*requires.*text_wrap"
        ):
            _still(text_separator_color=(255, 0, 0), text_align="scroll")

    def test_wrap_with_scroll_align_accepted(self):
        # text_align="scroll" needs transparent regions, so use
        # text_align="scroll_over" which doesn't impose that.
        w = _still(text_wrap=True, text_align="scroll_over")
        assert w.text_wrap is True

    def test_wrap_with_explicit_scroll_and_pillarbox_accepted(self):
        # text_align="scroll" + non-stretch fit is fine.
        w = _still(text_wrap=True, text_align="scroll", fit="fit")
        assert w.text_wrap is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_text_wrap.py -v
```

Expected: ALL tests fail. The first failures will be `AttributeError: ... has no attribute 'text_wrap'` (field not defined yet).

- [ ] **Step 3: Add the three fields**

Edit `src/led_ticker/widgets/_image_base.py`. Locate the existing field block ending with `text_loops` (around line 97). Add the three new fields immediately AFTER `text_loops`:

```python
    text_loops: int = attrs.field(default=0, kw_only=True)

    # Wrap-mode marquee: continuous text + separator chase across the
    # panel. Only valid with `text_align in ("scroll", "scroll_over")`.
    # When True, the per-tick scroll loop runs at modular cycle width
    # (text + separator) so the text never fully leaves the panel.
    # `text_loops` reinterprets as "minimum cycle traversals" instead
    # of the off-right-to-off-left definition used by the default
    # marquee. Two-row mode (`bottom_text` set) refuses `text_wrap` —
    # the bottom row already auto-scrolls on overflow with different
    # semantics; conflating the two would be confusing.
    text_wrap: bool = attrs.field(default=False, kw_only=True)

    # The text inserted between repeats in `text_wrap` mode. None = use
    # the default " • " when wrap is on (matching forever_scroll's
    # default separator). Explicit "" → "  " (two-space gap, matching
    # forever_scroll's empty-separator semantics). Any other value is
    # rendered as-is.
    text_separator: str | None = attrs.field(default=None, kw_only=True)

    # Color for the separator in wrap mode. None = inherit `font_color`.
    # The separator is rendered as a single "blob" — even when the
    # value is a per-char provider (rainbow/gradient), it's called
    # with `color_for(frame, 0, 1)` to pick one hue per frame. Its
    # frame counter is registered in `_FrameAware._EFFECT_ATTRS` so
    # continuous-phase providers stay in phase with the main text.
    text_separator_color: Any | None = attrs.field(default=None, kw_only=True)
```

- [ ] **Step 4: Add validation in `_validate_common`**

Inside `_BaseImageWidget._validate_common` (around line 254–283, just before the two-row validation block at line 308), append:

```python
        # text_wrap validation. Wrap is a marquee variation, so it
        # only makes sense with the scrolling alignments. It also
        # composes oddly with two-row mode (the bottom row already
        # auto-scrolls with different semantics) — refuse outright.
        if self.text_wrap:
            if self.text_align not in ("scroll", "scroll_over"):
                raise ValueError(
                    f"text_wrap=True requires text_align in "
                    f"('scroll', 'scroll_over'); got "
                    f"text_align={self.text_align!r}. "
                    f"Wrap is a marquee variation; on static alignments "
                    f"it has nothing to wrap."
                )
            if self.bottom_text:
                raise ValueError(
                    "text_wrap=True is not supported in two-row mode "
                    "(bottom_text set). The bottom row already "
                    "auto-scrolls on overflow with different semantics. "
                    "Use single-row image text for wrap, or omit "
                    "bottom_text."
                )

        # Separator fields require text_wrap=True. Without wrap, the
        # separator has nowhere to render — silent no-op would mask
        # a misconfiguration.
        if self.text_separator is not None and not self.text_wrap:
            raise ValueError(
                f"text_separator={self.text_separator!r} requires "
                f"text_wrap=True. The separator only renders in wrap "
                f"mode."
            )
        if self.text_separator_color is not None and not self.text_wrap:
            raise ValueError(
                "text_separator_color requires text_wrap=True. The "
                "separator only renders in wrap mode."
            )
```

Also wrap `text_separator_color` in `_ConstantColor` defensively (in case the user passed a raw Color that bypassed the app.py coercion path):

Locate the existing `_validate_common` color-coercion block (lines 226–234):

```python
        if self.font_color is not None and not hasattr(self.font_color, "color_for"):
            self.font_color = _ConstantColor(self.font_color)
        if self.top_color is not None and not hasattr(self.top_color, "color_for"):
            self.top_color = _ConstantColor(self.top_color)
        if self.bottom_color is not None and not hasattr(
            self.bottom_color, "color_for"
        ):
            self.bottom_color = _ConstantColor(self.bottom_color)
```

Append immediately after:

```python
        if self.text_separator_color is not None and not hasattr(
            self.text_separator_color, "color_for"
        ):
            self.text_separator_color = _ConstantColor(self.text_separator_color)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_text_wrap.py -v
```

Expected: ALL tests PASS (field defaults verified, all five validation errors raise correctly, both accepted configurations construct without error).

- [ ] **Step 6: Run the full suite — fields shouldn't have broken anything**

```bash
make test
```

Expected: full suite passes (no regression in existing image widget tests).

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_text_wrap.py
git commit -m "$(cat <<'EOF'
image-text-wrap: add text_wrap / text_separator / text_separator_color fields

Field surface only. text_wrap=True triggers seamless marquee wrap;
text_separator (default " • " when wrap on) is the glyph between
repeats; text_separator_color (None inherits font_color) is its color.

Validation: text_wrap requires scroll_align; refused in two-row
mode; separator fields require text_wrap=True. Wrap math arrives
in the next commit — this is just the API surface + guardrails.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Register `text_separator_color` for color coercion and frame counters

**Files:**
- Modify: `src/led_ticker/app.py` (around line 81-86: `_PROVIDER_COLOR_KEYS`)
- Modify: `src/led_ticker/widgets/_frame_aware.py` (around line 40-49: `_EFFECT_ATTRS`)
- Test: `tests/test_widgets/test_image_text_wrap.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_widgets/test_image_text_wrap.py`:

```python
class TestSeparatorColorCoercion:
    def test_separator_color_in_provider_keys(self):
        """text_separator_color must be in _PROVIDER_COLOR_KEYS so
        the app.py coercion path wraps raw [r,g,b] into a
        ColorProvider before the widget sees it."""
        from led_ticker.app import _PROVIDER_COLOR_KEYS

        assert "text_separator_color" in _PROVIDER_COLOR_KEYS

    def test_separator_color_in_effect_attrs(self):
        """text_separator_color must be in _FrameAware._EFFECT_ATTRS
        so it gets its own per-effect frame counter (matters for
        continuous-phase providers like Rainbow)."""
        from led_ticker.widgets._frame_aware import _FrameAware

        assert "text_separator_color" in _FrameAware._EFFECT_ATTRS

    def test_separator_color_string_coerced(self):
        """When the app loader sees text_separator_color = 'rainbow',
        _coerce_widget_colors must convert it to a Rainbow provider."""
        from led_ticker.app import _coerce_widget_colors

        cfg = {"text_separator_color": "rainbow"}
        _coerce_widget_colors(cfg)
        provider = cfg["text_separator_color"]
        assert hasattr(provider, "color_for")
        # Rainbow is per-char by default.
        assert provider.per_char is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_text_wrap.py::TestSeparatorColorCoercion -v
```

Expected: all three tests FAIL (key not in set / not in effect attrs / coercion didn't fire).

- [ ] **Step 3: Add the key to `_PROVIDER_COLOR_KEYS`**

Edit `src/led_ticker/app.py` (around line 81). Locate:

```python
_PROVIDER_COLOR_KEYS: set[str] = {
    "font_color",
    "top_color",
    "bottom_color",
    "font_color_temp",
}
```

Add the new key:

```python
_PROVIDER_COLOR_KEYS: set[str] = {
    "font_color",
    "top_color",
    "bottom_color",
    "font_color_temp",
    "text_separator_color",
}
```

- [ ] **Step 4: Add the key to `_EFFECT_ATTRS`**

Edit `src/led_ticker/widgets/_frame_aware.py` (around line 40). Locate:

```python
    _EFFECT_ATTRS: ClassVar[frozenset[str]] = frozenset(
        {
            "font_color",
            "font_color_temp",
            "top_color",
            "bottom_color",
            "border",
            "animation",
        }
    )
```

Add `"text_separator_color"`:

```python
    _EFFECT_ATTRS: ClassVar[frozenset[str]] = frozenset(
        {
            "font_color",
            "font_color_temp",
            "top_color",
            "bottom_color",
            "border",
            "animation",
            "text_separator_color",
        }
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_text_wrap.py::TestSeparatorColorCoercion -v
```

Expected: all three tests PASS.

- [ ] **Step 6: Run full suite for regression check**

```bash
make test
```

Expected: green. The `_EFFECT_ATTRS` addition is safe — widgets that don't declare `text_separator_color` return None from `getattr` and `_iter_effects` filters them out.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/app.py src/led_ticker/widgets/_frame_aware.py tests/test_widgets/test_image_text_wrap.py
git commit -m "$(cat <<'EOF'
image-text-wrap: register text_separator_color in coercion + frame counters

Add to _PROVIDER_COLOR_KEYS so TOML strings/lists become ColorProvider
instances at config-load. Add to _FrameAware._EFFECT_ATTRS so the
provider gets its own per-effect frame counter — keeps continuous-
phase Rainbow / ColorCycle in phase with the main text rather than
restarting per visit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Implement seamless wrap math in `_play_with_text`

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py` (`_play_with_text` around lines 773–952; new helper `_resolve_separator_text` + `_render_wrap_tick`)
- Test: `tests/test_widgets/test_image_text_wrap.py` (extend)

This is the core change. We add a parallel render-tick path for wrap mode and a wrap-aware scroll loop, leaving the non-wrap branch untouched.

- [ ] **Step 1: Write the failing test — wrap renders TWO copies of text simultaneously**

The defining property of wrap mode: at the moment the trailing edge of copy N leaves the right side of the panel, copy N+1's leading edge has already entered from the left. So a wide-enough panel with short-enough text MUST show ≥2 copies at some tick.

Append to `tests/test_widgets/test_image_text_wrap.py`:

```python
import asyncio

from unittest.mock import MagicMock


class FakeFrame:
    """Minimal Frame stub. Returns the same canvas object so
    text_canvas reanchoring works without our test caring."""

    def __init__(self, canvas):
        self.matrix = MagicMock()
        self.matrix.SwapOnVSync = MagicMock(side_effect=lambda c: c)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_test_canvas(width=64, height=16):
    """Build a stub canvas — uses the test stub from tests/stubs/."""
    from rgbmatrix import RGBMatrixOptions  # tests/stubs version

    options = RGBMatrixOptions()
    options.cols = width
    options.rows = height
    options.chain_length = 1
    options.parallel = 1
    from rgbmatrix import RGBMatrix

    matrix = RGBMatrix(options=options)
    return matrix.CreateFrameCanvas()


class TestWrapRendersMultipleCopies:
    """The defining test: in wrap mode, at the right tick, two copies
    of the text must be on the panel simultaneously.

    We don't read pixels back (CLAUDE.md #3: no GetPixel). Instead we
    monkeypatch `_draw_text` to record each call's (x, text) and
    assert that at some tick we see two text draws with distinct x's
    that are both on-panel."""

    def test_wrap_left_yields_two_text_copies_on_panel(self, monkeypatch):
        # Short "Hi" + " * " separator. With BDF 6x12, "Hi" is ~10px
        # and " * " is ~14px → cycle_width ≈ 24px. A 64-px panel
        # comfortably shows 2 copies once the second copy enters.
        w = _still(
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
        )
        w._panel_w = 64
        w._panel_h = 16

        # Record (x, text) for every _draw_text call.
        draws: list[tuple[int, str]] = []
        orig = w._draw_text

        def _record(canvas, x, baseline_y, color, text_override=None, **kw):
            text = text_override if text_override is not None else w.text
            draws.append((x, text))
            return orig(canvas, x, baseline_y, color, text_override=text_override, **kw)

        monkeypatch.setattr(w, "_draw_text", _record)

        canvas = _make_test_canvas(64, 16)
        frame = FakeFrame(canvas)

        # 30 ticks at default 50ms = 1.5s; cycle ~24 ticks at 1px/tick
        # → guaranteed to have completed at least one full cycle and
        # have both copies on-panel at the wraparound tick.
        _run(w._play_with_text(canvas, frame, n_ticks=30))

        # Group draws by tick: assume two draws per tick (one per copy)
        # is the wrap signature. At minimum one tick should have ≥2
        # text draws with main-text content (not just separator).
        per_tick_groups: list[list[tuple[int, str]]] = []
        # Heuristic: a "tick" is delimited by main-text reappearance —
        # but cleaner: just count main-text occurrences. If wrap is
        # working, total main-text draws > n_ticks (because some ticks
        # render 2 copies).
        main_text_draws = [d for d in draws if d[1] == "Hi"]
        assert len(main_text_draws) > 30, (
            f"Wrap should render >1 copy at some ticks. "
            f"Got {len(main_text_draws)} main-text draws across "
            f"30 ticks — that's ≤1 per tick (no wrap happening)."
        )
```

This is a behavioral test, not a pixel-level test — it asserts that wrap mode draws more copies of the main text than there are ticks, which can only happen if multiple copies render per tick.

- [ ] **Step 2: Run the test to verify it fails**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_text_wrap.py::TestWrapRendersMultipleCopies -v
```

Expected: FAIL. `len(main_text_draws) <= 30` because wrap math doesn't exist yet — current code draws one copy per tick.

- [ ] **Step 3: Add helper for resolving separator text + measuring**

Append to `_BaseImageWidget` in `src/led_ticker/widgets/_image_base.py` (right after `_measure_text` around line 489, before `_draw_text`):

```python
    def _resolved_separator_text(self) -> str:
        """Resolve the separator string per wrap-mode semantics:
          - None (default): " • "
          - "" (explicit empty): "  " (two spaces — minimum gap so
            adjacent copies don't visually butt up)
          - any other value: as-is.

        Mirrors `forever_scroll`'s separator literal-text rules so a
        user moving from per-section to per-widget wraps gets the
        same defaults."""
        if self.text_separator is None:
            return " • "
        if self.text_separator == "":
            return "  "
        return self.text_separator

    def _measure_separator(self, canvas: Canvas) -> int:
        """Width of the resolved separator in logical px on `canvas`.
        Uses the same font as the main text (per v1 scope — separator
        font/font_size override is deferred)."""
        sep = self._resolved_separator_text()
        if not sep:
            return 0
        # Reuse measure_width if the separator contains emoji,
        # otherwise plain get_text_width. The separator typically
        # doesn't have emoji but emoji-in-separator is supported
        # for free.
        if EMOJI_PATTERN.search(sep):
            from led_ticker.pixel_emoji import measure_width

            return measure_width(self.font, sep, canvas=canvas)
        return get_text_width(self.font, sep, padding=0, canvas=canvas)

    def _draw_separator(
        self,
        canvas: Canvas,
        x: int,
        baseline_y: int,
    ) -> None:
        """Draw the resolved separator at (x, baseline_y) with the
        right color. Whole-string color call so even a Rainbow on
        text_separator_color paints the separator as one hue per
        frame (rather than per-char sweeping across the bullet).

        Reads its own per-effect counter via
        `frame_for("text_separator_color")` so continuous-phase
        providers stay in phase with the main text instead of
        resetting per visit."""
        sep = self._resolved_separator_text()
        if not sep:
            return
        # Color resolution: explicit text_separator_color wins;
        # otherwise inherit font_color. The fallback path matters
        # for the common case where a user just sets text_wrap=true
        # without picking a separator color — the separator should
        # match the text color out of the box.
        provider = (
            self.text_separator_color
            if self.text_separator_color is not None
            else self.font_color
        )
        # Whole-string: one color_for call per draw. Per-char
        # rainbow on text_separator_color collapses to char-0's hue.
        frame_count = self.frame_for(
            "text_separator_color"
            if self.text_separator_color is not None
            else "font_color"
        )
        if hasattr(provider, "color_for"):
            color = provider.color_for(frame_count, 0, 1)
        else:
            color = provider
        # Reuse _draw_text with text_override so emoji + color paths
        # are shared. Force text=sep via text_override.
        # We need to pass color (not provider) since per-char
        # providers would sweep — already collapsed above.
        if EMOJI_PATTERN.search(sep):
            from led_ticker.pixel_emoji import draw_with_emoji

            draw_with_emoji(
                canvas,
                self.font,
                x,
                baseline_y,
                color,
                sep,
                emoji_y=baseline_y - 8,
                frame=frame_count,
                total_chars=1,
            )
        else:
            draw_text(canvas, self.font, x, baseline_y, color, sep)
```

- [ ] **Step 4: Add `_render_wrap_tick` helper**

Append to `_BaseImageWidget` (right after `_render_tick` around line 721, before `_render_two_row_tick`):

```python
    def _render_wrap_tick(
        self,
        canvas: Canvas,
        text_canvas: Canvas,
        scroll_pos: int,
        baseline_y: int,
        text_width: int,
        sep_width: int,
        cycle_width: int,
    ) -> None:
        """Compose one wrap-mode frame: reset → image / border / text
        in the right order for the current text_align, drawing
        as many text+separator copies as needed to cover the panel.

        `scroll_pos` is the normalized leading-copy x-position in
        [0, cycle_width). To cover the panel, we draw copies at
        `scroll_pos - cycle_width`, `scroll_pos`, `scroll_pos + cycle_width`,
        ... until past the right edge. Two copies are usually enough
        on a 64-px panel with cycle≥30, but for narrower cycles
        (short text + " " separator) we need more — compute the
        count from `ceil(canvas_w / cycle) + 1`.

        Mirrors `_render_tick`'s paint-order logic for the two
        scrolling alignments. Skip-black `text_align="scroll"` paints
        text first, then the image silhouette on top; `scroll_over`
        paints image first, then text on top."""
        reset_canvas(canvas, self.bg_color)
        provider = self.font_color
        canvas_w = text_canvas.width

        # Number of copies needed to cover the panel plus one off-
        # screen on the leading side. `+1` ensures the copy that is
        # leaving has a successor visible.
        n_copies = (canvas_w + cycle_width - 1) // cycle_width + 1

        # Leading copy's x: `scroll_pos` normalized to [0, cycle_width)
        # but offset to start one cycle off-screen so the first copy
        # we draw is already partly visible on the left.
        start_x = scroll_pos - cycle_width

        def _draw_text_chain() -> None:
            for i in range(n_copies):
                x = start_x + i * cycle_width
                self._draw_text(text_canvas, x, baseline_y, provider)
                if sep_width > 0:
                    self._draw_separator(text_canvas, x + text_width, baseline_y)

        if self.text_align == "scroll":
            _draw_text_chain()
            self._paint_skip_black(canvas)
            if self.border is not None:
                self.border.paint(canvas, self.frame_for("border"))
        else:  # scroll_over
            self._paint_image(canvas)
            if self.border is not None:
                self.border.paint(canvas, self.frame_for("border"))
            _draw_text_chain()
```

- [ ] **Step 5: Integrate wrap mode into `_play_with_text`**

Edit `_play_with_text` in `src/led_ticker/widgets/_image_base.py`. Locate the existing scroll-mode setup block (around lines 844–853):

```python
        scrolling = self.text_align in ("scroll", "scroll_over")
        if not scrolling:
            scroll_pos = 0
            scroll_step = 0
        elif self.scroll_direction == "right":
            scroll_pos = -text_width
            scroll_step = 1
        else:  # "left"
            scroll_pos = text_w
            scroll_step = -1
```

Replace with:

```python
        scrolling = self.text_align in ("scroll", "scroll_over")
        wrap_mode = scrolling and self.text_wrap

        # Wrap-mode constants: cycle_width is one full (text+sep)
        # repeat; sep_width is needed by `_render_wrap_tick` to
        # place the separator after each text copy.
        sep_width = self._measure_separator(text_canvas) if wrap_mode else 0
        cycle_width = (text_width + sep_width) if wrap_mode else 0

        if not scrolling:
            scroll_pos = 0
            scroll_step = 0
        elif wrap_mode:
            # Initial scroll_pos in [0, cycle_width): the leading copy
            # starts flush-left. Direction is the step sign.
            scroll_pos = 0
            scroll_step = 1 if self.scroll_direction == "right" else -1
        elif self.scroll_direction == "right":
            scroll_pos = -text_width
            scroll_step = 1
        else:  # "left"
            scroll_pos = text_w
            scroll_step = -1
```

Then locate the marquee-floor block (around lines 868–871):

```python
        if scrolling:
            ticks_per_text_loop = text_w + text_width
            min_loops = max(1, self.text_loops)
            n_ticks = max(n_ticks, min_loops * ticks_per_text_loop)
```

Replace with:

```python
        if scrolling:
            if wrap_mode:
                # In wrap mode, one "loop" = one cycle (text + sep)
                # rather than one full off-right→off-left traversal.
                ticks_per_text_loop = cycle_width
            else:
                ticks_per_text_loop = text_w + text_width
            min_loops = max(1, self.text_loops)
            n_ticks = max(n_ticks, min_loops * ticks_per_text_loop)
```

Then locate the static-fast-path predicate (around lines 893–917):

```python
        if (
            not scrolling
            and self.text_loops == 0
            and self._is_static()
            and color_is_static
            and border_is_static
            and self.animation is None
        ):
```

No change needed — wrap mode implies `scrolling=True`, which already disables the fast path.

Locate the per-tick render call (around lines 919–943):

```python
        for tick in range(n_ticks):
            self._pick_frame_for_elapsed(tick * tick_ms)
            self.advance_frame()
            self._render_tick(
                canvas,
                text_canvas,
                scroll_pos,
                baseline_y,
                text_x_left,
                text_x_right,
            )
            canvas = frame.matrix.SwapOnVSync(canvas)
            if text_is_wrapped:
                text_canvas.real = canvas
            else:
                text_canvas = canvas
            await asyncio.sleep(tick_seconds)
```

Replace with a wrap-aware version:

```python
        for tick in range(n_ticks):
            self._pick_frame_for_elapsed(tick * tick_ms)
            self.advance_frame()
            if wrap_mode:
                self._render_wrap_tick(
                    canvas,
                    text_canvas,
                    scroll_pos,
                    baseline_y,
                    text_width,
                    sep_width,
                    cycle_width,
                )
            else:
                self._render_tick(
                    canvas,
                    text_canvas,
                    scroll_pos,
                    baseline_y,
                    text_x_left,
                    text_x_right,
                )
            canvas = frame.matrix.SwapOnVSync(canvas)
            if text_is_wrapped:
                text_canvas.real = canvas
            else:
                text_canvas = canvas
            await asyncio.sleep(tick_seconds)
```

Finally, locate the scroll-pos increment block (around lines 945–950):

```python
            if scrolling:
                scroll_pos += scroll_step
                if scroll_step < 0 and scroll_pos + text_width <= 0:
                    scroll_pos = text_w
                elif scroll_step > 0 and scroll_pos >= text_w:
                    scroll_pos = -text_width
```

Replace with:

```python
            if scrolling:
                scroll_pos += scroll_step
                if wrap_mode:
                    # Normalize to [0, cycle_width). Python's `%` on
                    # negative numbers already returns a non-negative
                    # result for positive divisors, so this works for
                    # both directions.
                    scroll_pos %= cycle_width
                elif scroll_step < 0 and scroll_pos + text_width <= 0:
                    scroll_pos = text_w
                elif scroll_step > 0 and scroll_pos >= text_w:
                    scroll_pos = -text_width
```

- [ ] **Step 6: Run the wrap test to verify it passes**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_text_wrap.py::TestWrapRendersMultipleCopies -v
```

Expected: PASS. `len(main_text_draws) > 30` (multiple copies per tick).

- [ ] **Step 7: Run full image-widget test suites for regression check**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py tests/test_widgets/test_gif.py tests/test_widgets/test_still.py tests/test_widgets/test_image_text_wrap.py -v
```

Expected: all green. The non-wrap path is unchanged — existing tests stay green.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_text_wrap.py
git commit -m "$(cat <<'EOF'
image-text-wrap: seamless marquee with text + separator

When text_wrap=true, the per-tick scroll loop runs at modular
cycle width (text + separator) instead of the off-right-to-off-
left default. `_render_wrap_tick` draws ceil(canvas_w / cycle) + 1
copies of (text + separator) per frame so the panel is never empty.

text_loops in wrap mode reinterprets as "minimum cycle traversals"
(one traversal = cycle_width ticks). The non-wrap path is
untouched.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Direction = "right" wraps correctly

Negative-direction wrap is the modular-arithmetic gotcha — Python's `%` handles it but assert behavior explicitly.

**Files:**
- Test: `tests/test_widgets/test_image_text_wrap.py` (extend)

- [ ] **Step 1: Write the test**

Append to `TestWrapRendersMultipleCopies` in `tests/test_widgets/test_image_text_wrap.py`:

```python
    def test_wrap_right_direction_renders(self, monkeypatch):
        """scroll_direction='right' must still wrap correctly. The
        cycle math is direction-independent; this catches a future
        change that special-cases one direction."""
        w = _still(
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
            scroll_direction="right",
        )
        w._panel_w = 64
        w._panel_h = 16

        draws: list[tuple[int, str]] = []
        orig = w._draw_text

        def _record(canvas, x, baseline_y, color, text_override=None, **kw):
            text = text_override if text_override is not None else w.text
            draws.append((x, text))
            return orig(canvas, x, baseline_y, color, text_override=text_override, **kw)

        monkeypatch.setattr(w, "_draw_text", _record)

        canvas = _make_test_canvas(64, 16)
        frame = FakeFrame(canvas)
        _run(w._play_with_text(canvas, frame, n_ticks=30))

        main_text_draws = [d for d in draws if d[1] == "Hi"]
        assert len(main_text_draws) > 30, (
            f"Right-direction wrap should also render >1 copy at "
            f"some ticks. Got {len(main_text_draws)} for 30 ticks."
        )
```

- [ ] **Step 2: Run the test**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_text_wrap.py::TestWrapRendersMultipleCopies::test_wrap_right_direction_renders -v
```

Expected: PASS (Python's `%` handles negative-mod correctly; the implementation from Task 3 should already cover it). If it FAILS, the modular-pos normalization in `_play_with_text` is the culprit — check that `scroll_pos %= cycle_width` covers both signs.

- [ ] **Step 3: Commit**

```bash
git add tests/test_widgets/test_image_text_wrap.py
git commit -m "test(image-text-wrap): scroll_direction='right' wraps correctly

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `text_loops` traversal floor in wrap mode

Validate the n_ticks floor reinterpretation explicitly so a future change can't silently regress the contract.

**Files:**
- Test: `tests/test_widgets/test_image_text_wrap.py` (extend)

- [ ] **Step 1: Write the test**

Append to `tests/test_widgets/test_image_text_wrap.py`:

```python
class TestTextLoopsTraversalFloor:
    """In wrap mode, text_loops=N means at least N cycle_width
    traversals (one traversal = text + separator). The underlying
    source duration extends to match when shorter; longer sources
    are unaffected."""

    def test_wrap_short_duration_extends_to_min_one_traversal(
        self, monkeypatch
    ):
        """A still with hold_seconds=0.05 (10ms < tick_ms=50) would
        normally run 1 tick. With text_wrap=true, the floor pushes
        n_ticks up to one cycle_width."""
        w = _still(
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
            hold_seconds=0.05,
        )
        w._panel_w = 64
        w._panel_h = 16

        # Patch out the actual drawing — count ticks via swap calls.
        canvas = _make_test_canvas(64, 16)
        frame = FakeFrame(canvas)

        _run(w._play_with_text(canvas, frame, n_ticks=1))

        # cycle_width for "Hi" + " * " in BDF 6×12 is approximately
        # 24 logical px on a smallsign-scale wrap. The exact value
        # depends on font advance widths; assert ≥ 2 instead of an
        # exact number so the test isn't font-fragile.
        swaps = frame.matrix.SwapOnVSync.call_count
        assert swaps >= 2, (
            f"text_wrap with text_loops=0 should still floor to "
            f"≥1 full cycle traversal. Got only {swaps} ticks for "
            f"a cycle that should be >1 tick wide."
        )

    def test_wrap_text_loops_2_runs_at_least_two_cycles(
        self, monkeypatch
    ):
        """text_loops=2 must run at least 2× cycle_width ticks."""
        w = _still(
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
            text_loops=2,
            hold_seconds=0.05,
        )
        w._panel_w = 64
        w._panel_h = 16

        canvas = _make_test_canvas(64, 16)
        frame = FakeFrame(canvas)

        # n_ticks=1 from the source; floor should push to >=
        # 2 * cycle_width.
        _run(w._play_with_text(canvas, frame, n_ticks=1))

        swaps_2 = frame.matrix.SwapOnVSync.call_count

        # Same setup with text_loops=1.
        w2 = _still(
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
            text_loops=1,
            hold_seconds=0.05,
        )
        w2._panel_w = 64
        w2._panel_h = 16
        canvas2 = _make_test_canvas(64, 16)
        frame2 = FakeFrame(canvas2)
        _run(w2._play_with_text(canvas2, frame2, n_ticks=1))
        swaps_1 = frame2.matrix.SwapOnVSync.call_count

        assert swaps_2 >= swaps_1 * 2 - 2, (
            f"text_loops=2 should yield ~2x the ticks of text_loops=1 "
            f"in wrap mode. Got {swaps_2} vs {swaps_1}."
        )
```

- [ ] **Step 2: Run the tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_text_wrap.py::TestTextLoopsTraversalFloor -v
```

Expected: BOTH PASS. The Task 3 implementation already sets `ticks_per_text_loop = cycle_width` for wrap mode and floors `n_ticks` to `min_loops * ticks_per_text_loop`. If either FAILS, double-check the wrap-mode branch in the floor block from Task 3 Step 5.

- [ ] **Step 3: Commit**

```bash
git add tests/test_widgets/test_image_text_wrap.py
git commit -m "test(image-text-wrap): text_loops floors to N cycle traversals in wrap mode

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Separator color inheritance + per-effect counter behavior

Verify the two color paths:
- `text_separator_color = None` → separator inherits `font_color` (whole-string call)
- `text_separator_color = "rainbow"` → separator uses its own provider with its own frame counter

**Files:**
- Test: `tests/test_widgets/test_image_text_wrap.py` (extend)

- [ ] **Step 1: Write the tests**

Append to `tests/test_widgets/test_image_text_wrap.py`:

```python
class TestSeparatorColorInheritance:
    def test_separator_inherits_font_color_when_unset(self, monkeypatch):
        """text_separator_color=None should make the separator paint
        with font_color resolved at its current frame."""
        from led_ticker.color_providers import _ConstantColor
        from led_ticker._compat import require_graphics

        graphics = require_graphics()
        red = _ConstantColor(graphics.Color(255, 0, 0))

        w = _still(
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
            font_color=red,
        )
        w._panel_w = 64
        w._panel_h = 16

        captured_separator_colors: list = []
        # Patch draw_text to capture the color used.
        import led_ticker.widgets._image_base as base_mod

        orig = base_mod.draw_text

        def _spy(canvas, font, x, baseline_y, color, text):
            if text in (" • ", " * ", "  "):
                captured_separator_colors.append(color)
            return orig(canvas, font, x, baseline_y, color, text)

        monkeypatch.setattr(base_mod, "draw_text", _spy)

        canvas = _make_test_canvas(64, 16)
        frame = FakeFrame(canvas)
        _run(w._play_with_text(canvas, frame, n_ticks=5))

        assert captured_separator_colors, "No separator draws captured"
        # All separator colors should be red (RGB 255,0,0).
        for c in captured_separator_colors:
            assert (c.red, c.green, c.blue) == (255, 0, 0), (
                f"Separator should inherit font_color=red; got "
                f"({c.red},{c.green},{c.blue})"
            )

    def test_separator_uses_own_color_when_set(self, monkeypatch):
        """Explicit text_separator_color overrides inheritance."""
        from led_ticker.color_providers import _ConstantColor
        from led_ticker._compat import require_graphics

        graphics = require_graphics()
        red = _ConstantColor(graphics.Color(255, 0, 0))
        blue = _ConstantColor(graphics.Color(0, 0, 255))

        w = _still(
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
            font_color=red,
            text_separator_color=blue,
        )
        w._panel_w = 64
        w._panel_h = 16

        captured: list = []
        import led_ticker.widgets._image_base as base_mod

        orig = base_mod.draw_text

        def _spy(canvas, font, x, baseline_y, color, text):
            if text in (" • ", " * ", "  "):
                captured.append(color)
            return orig(canvas, font, x, baseline_y, color, text)

        monkeypatch.setattr(base_mod, "draw_text", _spy)

        canvas = _make_test_canvas(64, 16)
        frame = FakeFrame(canvas)
        _run(w._play_with_text(canvas, frame, n_ticks=5))

        assert captured, "No separator draws captured"
        for c in captured:
            assert (c.red, c.green, c.blue) == (0, 0, 255), (
                f"Separator should use text_separator_color=blue; "
                f"got ({c.red},{c.green},{c.blue})"
            )
```

- [ ] **Step 2: Run the tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_text_wrap.py::TestSeparatorColorInheritance -v
```

Expected: BOTH PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_widgets/test_image_text_wrap.py
git commit -m "test(image-text-wrap): separator color inheritance from font_color + override

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Special-case `text_separator = ""` → two-space gap

Verify the explicit-empty semantics so users moving from forever_scroll's separator API get the same default-vs-explicit behavior.

**Files:**
- Test: `tests/test_widgets/test_image_text_wrap.py` (extend)

- [ ] **Step 1: Write the test**

Append:

```python
class TestSeparatorEmptyString:
    def test_empty_string_separator_renders_two_spaces(self):
        """text_separator='' → '  ' (two-space minimum gap) so
        adjacent text copies don't visually butt up. Matches the
        forever_scroll separator's empty-string semantics."""
        w = _still(
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator="",
        )
        assert w._resolved_separator_text() == "  "

    def test_none_separator_renders_default_bullet(self):
        w = _still(
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            # text_separator omitted → None
        )
        assert w._resolved_separator_text() == " • "

    def test_custom_string_separator_renders_as_is(self):
        w = _still(
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
        )
        assert w._resolved_separator_text() == " * "
```

- [ ] **Step 2: Run the tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_text_wrap.py::TestSeparatorEmptyString -v
```

Expected: ALL PASS (the `_resolved_separator_text` helper from Task 3 already encodes this).

- [ ] **Step 3: Commit**

```bash
git add tests/test_widgets/test_image_text_wrap.py
git commit -m "test(image-text-wrap): empty-string separator → two-space gap

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Update widget docs pages

**Files:**
- Modify: `docs/site/src/content/docs/widgets/gif.mdx`
- Modify: `docs/site/src/content/docs/widgets/image.mdx`

The docs site already covers existing image-text-overlay knobs. Add a new subsection under each page describing `text_wrap`, `text_separator`, `text_separator_color`.

- [ ] **Step 1: Read the existing structure to find the insertion point**

```bash
grep -n "text_align\|text_loops\|scroll_speed_ms" /Users/james/projects/github/jamesawesome/led-ticker/docs/site/src/content/docs/widgets/gif.mdx | head -20
```

Identify the section that documents `text_loops` — the new fields belong adjacent to it.

- [ ] **Step 2: Add a "Wrap mode" subsection to `gif.mdx`**

Insert below the `text_loops` / scroll-mode discussion. Suggested content (adapt to match the page's existing voice):

```mdx
### Wrap mode (`text_wrap`)

When `text_wrap = true` and `text_align` is `"scroll"` or `"scroll_over"`,
the marquee becomes seamless: instead of running off the right edge before
re-entering on the left, the text repeats with a configurable separator
between copies. At any tick at least one full copy is on the panel.

```toml
[[playlist.section.widget]]
type = "gif"
path = "panda.gif"
text = "BREAKING NEWS"
text_wrap = true
text_align = "scroll_over"
text_separator = " * "        # default " • "
text_separator_color = "rainbow"  # default: inherit font_color
```

**Field reference:**

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `text_wrap` | `bool` | `false` | Toggle seamless wrap. Requires `text_align ∈ ("scroll", "scroll_over")`. |
| `text_separator` | `string` | `" • "` (when `text_wrap=true`) | Glyph(s) between repeats. `""` → two-space gap. |
| `text_separator_color` | color spec | inherit `font_color` | Color for the separator; whole-string (one hue per frame). |

**Notes:**

- `text_loops` in wrap mode means *minimum number of full cycle traversals* (one cycle = text + separator), not the off-right→off-left definition used by the default marquee.
- Two-row mode (setting `bottom_text`) refuses `text_wrap` in v1.
- The separator's font is the widget's `font` (separator font/size override isn't in v1).
```

Adapt phrasing to the page's voice — keep the field table.

- [ ] **Step 3: Mirror the subsection in `image.mdx`**

Repeat the same insertion in the `image.mdx` page, switching the example to `type = "image"` and a `.png` path.

- [ ] **Step 4: Lint the docs site if a docs-only build is available**

```bash
cd docs/site && pnpm astro check 2>&1 | head -20
```

If `astro check` is part of CI in this repo, ensure no errors are introduced. (If `pnpm` isn't available locally, skip — CI will catch it.)

- [ ] **Step 5: Commit**

```bash
git add docs/site/src/content/docs/widgets/gif.mdx docs/site/src/content/docs/widgets/image.mdx
git commit -m "$(cat <<'EOF'
docs(image-text-wrap): document text_wrap + separator on gif/image

Mirrors the new fields on both widget pages with field table and
example. Notes the v1 scope (single-row only) and the text_loops
reinterpretation in wrap mode.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Full suite + final integration check

- [ ] **Step 1: Run the full test suite from a clean state**

```bash
make test
```

Expected: GREEN. New tests are in `tests/test_widgets/test_image_text_wrap.py`; no existing tests should regress.

- [ ] **Step 2: Run ruff**

```bash
make lint
```

Expected: no errors.

- [ ] **Step 3: Validate the example configs**

```bash
make validate CONFIG=config/config.example.toml
make validate CONFIG=config/config.bigsign.example.toml
```

Expected: no validation errors (these configs don't use text_wrap; just confirming the new validation didn't break anything).

- [ ] **Step 4: Smoke test with a hand-crafted wrap config**

Create a temporary test config to confirm end-to-end (no hardware needed — the validator + cli `--dry-run` path exercises the build):

```bash
cat > /tmp/wrap-test.toml <<'EOF'
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_seconds = 5

[[playlist.section.widget]]
type = "still"
path = "demos/assets/test_16x16.png"
text = "BREAKING"
text_wrap = true
text_align = "scroll_over"
text_separator = " * "
text_separator_color = "rainbow"
EOF

uv run led-ticker validate --config /tmp/wrap-test.toml
```

Expected: validation passes.

- [ ] **Step 5: No commit — final verification only**

If all steps green, the plan is complete. Final commit happens in Task 8.

---

## Self-Review

**Spec coverage:**
- [x] 3 fields added (`text_wrap`, `text_separator`, `text_separator_color`) — Task 1
- [x] Validation: wrap requires scroll, refuses two-row, separator fields require wrap — Task 1
- [x] `_PROVIDER_COLOR_KEYS` + `_EFFECT_ATTRS` registration — Task 2
- [x] Wrap render math + integration — Task 3
- [x] Direction = "right" works — Task 4
- [x] `text_loops` = cycle traversals — Task 5
- [x] Separator color inheritance + override — Task 6
- [x] Empty-string separator → two-space gap — Task 7
- [x] Docs updates — Task 8
- [x] Final integration check — Task 9

**Deferred (documented in plan goal):**
- Two-row image widget wrap
- TwoRowMessage bottom-row wrap
- `text_separator_font` / `text_separator_font_size` overrides

**Placeholder scan:** None — every step has its code/command.

**Type consistency:**
- `text_separator: str | None`, default `None` — consistent across plan
- `text_separator_color: Any | None` (kept loose so attrs accepts either raw `Color` or a coerced provider, matching the existing `font_color` pattern)
- `_resolved_separator_text() -> str` — defined in Task 3 Step 3, called from Task 3 Step 4's `_render_wrap_tick`
- `_measure_separator(canvas) -> int` — defined in Task 3 Step 3, called from `_play_with_text` integration in Task 3 Step 5

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-13-image-text-wrap.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using `executing-plans`, batch execution with checkpoints.
