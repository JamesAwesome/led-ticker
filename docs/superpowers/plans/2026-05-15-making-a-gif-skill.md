# Making-a-gif Skill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `tools/gif_plan/` (deterministic CLI for led-ticker demo-gif planning) and `.claude/skills/making-a-gif/` (Claude-facing skill that wraps it) so users can plan demo gifs with exact math + judgment overlay before invoking `make render-demo`.

**Architecture:** Two pieces, each independently testable. CLI does math + simple flags in pure Python (stdlib + Pillow). Skill orchestrates: detect mode (docs vs dev), invoke CLI, add color/contrast judgment, suggest commands. No engine import; CLI works on raw TOML dicts.

**Tech Stack:** Python 3.11+ (`tomllib` stdlib), Pillow (already in repo env), pytest. Skill is plain markdown.

**Spec:** `docs/superpowers/specs/2026-05-15-making-a-gif-skill-design.md`.

**Setup:**
- Create branch `making-a-gif-skill` off `main`.
- Repo path: `/Users/james/projects/github/jamesawesome/led-ticker/`.
- Pre-commit needs `node` on PATH for docs-lint. If `which node` fails, prepend `/Users/<user>/.nvm/versions/node/<v>/bin/` to PATH before any git commit.

**Caveat — canvas-width math:** The CLI's canvas-width formula `(cols × chain) / scale` is accurate for smallsign-style configs (the 35 existing pinned demos all use this shape). Bigsign configs with a `pixel_mapper_config` (e.g., "U-mapper") have a transformed layout the naive formula gets wrong. v1 emits an info-severity flag when `pixel_mapper_config` is set and continues with the naive math; the user can sanity-check. v2 may inspect the mapper string.

---

### Task 1: Skeleton + canvas-width helper

**Files:**
- Create: `tools/gif_plan/__init__.py`
- Create: `tools/gif_plan/widgets.py`
- Create: `tools/gif_plan/test_widgets.py`

- [ ] **Step 1: Create the package skeleton**

```bash
mkdir -p tools/gif_plan
touch tools/gif_plan/__init__.py
```

- [ ] **Step 2: Write failing test for canvas width**

Create `tools/gif_plan/test_widgets.py`:

```python
"""Tests for tools/gif_plan/widgets.py — per-widget math helpers."""

from __future__ import annotations

from tools.gif_plan.widgets import canvas_width_logical


class TestCanvasWidth:
    def test_smallsign_default_scale(self):
        # 5 panels × 32 cols / scale=1 = 160 logical px.
        display = {"cols": 32, "chain": 5, "default_scale": 1}
        section = {}
        assert canvas_width_logical(display, section) == 160

    def test_section_scale_override(self):
        # Section scale=2 halves the logical width.
        display = {"cols": 32, "chain": 5, "default_scale": 1}
        section = {"scale": 2}
        assert canvas_width_logical(display, section) == 80

    def test_default_scale_fallback(self):
        # No section.scale → fall back to display.default_scale.
        display = {"cols": 64, "chain": 8, "default_scale": 4}
        section = {}
        # Naive: (64 × 8) / 4 = 128. This is the v1 caveat — bigsign
        # actual is 64, but pixel_mapper_config handling is future work.
        assert canvas_width_logical(display, section) == 128

    def test_missing_default_scale_treated_as_one(self):
        # If display omits default_scale, use 1.
        display = {"cols": 32, "chain": 5}
        section = {}
        assert canvas_width_logical(display, section) == 160
```

- [ ] **Step 3: Run test to verify it fails**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_widgets.py::TestCanvasWidth -v`
Expected: ImportError (module doesn't exist yet) or FAIL.

- [ ] **Step 4: Implement canvas_width_logical**

Create `tools/gif_plan/widgets.py`:

```python
"""Per-widget math helpers for the gif planner.

Each function takes raw config dicts (parsed from TOML) and returns
integer ms or pixel values. No led_ticker engine import — the tool
works on raw config data.
"""

from __future__ import annotations


def canvas_width_logical(display: dict, section: dict) -> int:
    """Compute the section's logical canvas width in pixels.

    Formula: (display.cols × display.chain) / scale, where scale =
    section.scale OR display.default_scale OR 1.

    Caveat: pixel_mapper_config-based configs (e.g., bigsign U-mapper) have
    a transformed layout this naive formula gets wrong. Callers
    should flag pixel_mapper_config presence at the section level.
    """
    cols = int(display.get("cols", 0))
    chain = int(display.get("chain", 1))
    scale = int(section.get("scale") or display.get("default_scale") or 1)
    if scale <= 0:
        scale = 1
    return (cols * chain) // scale
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_widgets.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add tools/gif_plan/__init__.py tools/gif_plan/widgets.py tools/gif_plan/test_widgets.py
git commit -m "gif_plan: skeleton + canvas_width_logical helper"
```

---

### Task 2: Content width approximation

**Files:**
- Modify: `tools/gif_plan/widgets.py`
- Modify: `tools/gif_plan/test_widgets.py`

- [ ] **Step 1: Write failing tests**

Append to `tools/gif_plan/test_widgets.py`:

```python
from tools.gif_plan.widgets import estimate_content_width_logical


class TestContentWidth:
    def test_bdf_5x8_simple_text(self):
        # 5x8 BDF: 5 px/char × "HELLO" (5 chars) = 25.
        assert estimate_content_width_logical("HELLO", font="5x8") == 25

    def test_bdf_6x12_simple_text(self):
        # 6x12: 6 px/char × "HELLO" = 30.
        assert estimate_content_width_logical("HELLO", font="6x12") == 30

    def test_inline_emoji_counts_as_8(self):
        # ":heart: HI" → emoji is 8 px + " HI" is 3 chars × 5 = 15
        # at 5x8 font. Total 23.
        result = estimate_content_width_logical(":heart: HI", font="5x8")
        assert result == 23

    def test_multiple_inline_emoji(self):
        # ":a::b:" → two 8-px sprites = 16 (no characters between).
        result = estimate_content_width_logical(":a::b:", font="5x8")
        assert result == 16

    def test_hires_font_uses_size_times_055(self):
        # Inter-Bold @ font_size=22, "HI" (2 chars).
        # Per-char width ≈ ceil(22 × 0.55) = 13. "HI" = 26.
        result = estimate_content_width_logical(
            "HI", font="Inter-Bold", font_size=22
        )
        assert result == 26

    def test_unknown_font_falls_back_to_6_per_char(self):
        # Unknown BDF alias → 6 px/char default.
        assert estimate_content_width_logical("HELLO", font="weird") == 30

    def test_empty_text_zero_width(self):
        assert estimate_content_width_logical("", font="5x8") == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_widgets.py::TestContentWidth -v`
Expected: ImportError for `estimate_content_width_logical`.

- [ ] **Step 3: Implement estimate_content_width_logical**

Append to `tools/gif_plan/widgets.py`:

```python
import math
import re

# BDF font alias → cell width in pixels. Covers the canonical aliases
# used across the demo configs. Unknown aliases fall back to 6.
_BDF_CELL_WIDTH = {
    "5x8": 5,
    "6x12": 6,
    "7x13": 7,
    "FONT_SMALL": 5,
    "FONT_DEFAULT": 6,
}

# Pattern matching :slug: inline emoji. Each slug renders as an 8-px
# sprite by default; the band cap may scale this up but 8 is a safe
# baseline for the planner.
_EMOJI_SPRITE_WIDTH = 8
_EMOJI_PATTERN = re.compile(r":[a-z0-9_]+:")


def estimate_content_width_logical(
    text: str,
    font: str = "5x8",
    font_size: int | None = None,
) -> int:
    """Estimate the rendered width of `text` in logical pixels.

    BDF fonts: `len × cell_width` from `_BDF_CELL_WIDTH`. Inline
    `:slug:` emoji counted as 8 logical px each.

    Hi-res fonts (anything not in the BDF map): `len × ceil(font_size
    × 0.55)`. The 0.55 ratio is an Inter-Bold-ish approximation —
    conservative (slight overestimate) so "will it fit in
    render-duration" checks err on the safe side. Caller must pass
    `font_size` for hi-res fonts.
    """
    if not text:
        return 0

    # Count inline emoji separately — each is 8 px regardless of font.
    emoji_count = len(_EMOJI_PATTERN.findall(text))
    stripped = _EMOJI_PATTERN.sub("", text)

    if font in _BDF_CELL_WIDTH:
        cell_w = _BDF_CELL_WIDTH[font]
    elif font_size is not None:
        cell_w = math.ceil(font_size * 0.55)
    else:
        # Unknown font, no size given — fall back to default cell width.
        cell_w = 6

    return emoji_count * _EMOJI_SPRITE_WIDTH + len(stripped) * cell_w
```

- [ ] **Step 4: Run tests to verify pass**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_widgets.py -v`
Expected: 11 passed (4 from Task 1 + 7 new).

- [ ] **Step 5: Commit**

```bash
git add tools/gif_plan/widgets.py tools/gif_plan/test_widgets.py
git commit -m "gif_plan: content-width estimator (BDF + hi-res + inline emoji)"
```

---

### Task 3: TickerMessage visit time

**Files:**
- Modify: `tools/gif_plan/widgets.py`
- Modify: `tools/gif_plan/test_widgets.py`

- [ ] **Step 1: Write failing tests**

Append to `tools/gif_plan/test_widgets.py`:

```python
from tools.gif_plan.widgets import ticker_message_visit_ms


class TestTickerMessageVisitMs:
    def test_static_text_fits_uses_hold_time(self):
        # Text fits → static hold. 4 seconds × 1000 = 4000 ms.
        widget = {"type": "message", "text": "HI", "font": "5x8"}
        section = {"hold_time": 4.0, "scroll_step_ms": 25}
        assert ticker_message_visit_ms(widget, section, canvas_w=160) == 4000

    def test_overflow_scrolls_one_pass(self):
        # text width = 160 (assume), canvas = 160 → pass = (160+160)×25 = 8000.
        widget = {
            "type": "message",
            # 32 chars × 5 = 160 (overflows 160 canvas, since 160 < 161).
            "text": "x" * 33,  # 33 × 5 = 165 px overflow
            "font": "5x8",
        }
        section = {"hold_time": 2.0, "scroll_step_ms": 25}
        result = ticker_message_visit_ms(widget, section, canvas_w=160)
        # Pass duration = (160 + 165) × 25 = 8125 ms; > hold so wins.
        # But we also add the hold to the total for pre+post-scroll pause.
        # Spec: pass_ms only; the engine's hold_time happens around it
        # but for "did the gif capture the full scroll" the pass is
        # what matters. Use pass_ms as the visit floor.
        assert result == 8125

    def test_text_wrap_uses_max_of_loops_or_hold(self):
        # text_wrap=true: max(text_loops × cycle_ms, hold × 1000).
        widget = {
            "type": "message",
            "text": "BREAK",            # 5 chars × 5 = 25 px
            "font": "5x8",
            "text_wrap": True,
            "text_separator": " • ",    # 3 chars × 5 = 15 px (approx)
            "text_loops": 3,
        }
        section = {"hold_time": 1.0, "scroll_step_ms": 25}
        # cycle = 25 + 15 = 40 px. 3 × 40 × 25 = 3000 ms. hold=1000ms.
        # max(3000, 1000) = 3000.
        result = ticker_message_visit_ms(widget, section, canvas_w=160)
        assert result == 3000

    def test_text_wrap_hold_wins_over_short_loops(self):
        widget = {
            "type": "message",
            "text": "HI",
            "font": "5x8",
            "text_wrap": True,
            "text_separator": " • ",
            "text_loops": 1,
        }
        section = {"hold_time": 10.0, "scroll_step_ms": 25}
        # cycle = 10 + 15 = 25 px. 1 × 25 × 25 = 625 ms. hold=10000ms.
        # max = 10000.
        result = ticker_message_visit_ms(widget, section, canvas_w=160)
        assert result == 10000
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_widgets.py::TestTickerMessageVisitMs -v`
Expected: ImportError.

- [ ] **Step 3: Implement ticker_message_visit_ms**

Append to `tools/gif_plan/widgets.py`:

```python
def ticker_message_visit_ms(
    widget: dict,
    section: dict,
    canvas_w: int,
) -> int:
    """Visit time in ms for a TickerMessage widget.

    Three paths:
      - text_wrap=True: marquee. visit = max(loops × cycle_ms,
        hold × 1000).
      - Text overflow (content_w > canvas_w): single-pass scroll.
        visit = (canvas_w + content_w) × scroll_step_ms.
      - Static fit: hold_time × 1000.
    """
    font = widget.get("font", "5x8")
    font_size = widget.get("font_size")
    step_ms = int(section.get("scroll_step_ms") or 50)
    hold_ms = int(float(section.get("hold_time") or 0) * 1000)

    text_wrap = bool(widget.get("text_wrap", False))
    if text_wrap:
        sep = widget.get("text_separator") or " • "
        cycle_px = (
            estimate_content_width_logical(widget.get("text", ""), font, font_size)
            + estimate_content_width_logical(sep, font, font_size)
        )
        cycle_ms = cycle_px * step_ms
        loops = int(widget.get("text_loops") or 0)
        loops_ms = loops * cycle_ms
        return max(loops_ms, hold_ms)

    content_w = estimate_content_width_logical(
        widget.get("text", ""), font, font_size
    )
    if content_w > canvas_w:
        return (canvas_w + content_w) * step_ms
    return hold_ms
```

- [ ] **Step 4: Run tests to verify pass**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_widgets.py -v`
Expected: 15 passed (11 prior + 4 new).

- [ ] **Step 5: Commit**

```bash
git add tools/gif_plan/widgets.py tools/gif_plan/test_widgets.py
git commit -m "gif_plan: ticker_message_visit_ms (static / overflow / wrap)"
```

---

### Task 4: TwoRowMessage visit time

**Files:**
- Modify: `tools/gif_plan/widgets.py`
- Modify: `tools/gif_plan/test_widgets.py`

- [ ] **Step 1: Write failing tests**

Append to `tools/gif_plan/test_widgets.py`:

```python
from tools.gif_plan.widgets import two_row_visit_ms


class TestTwoRowVisitMs:
    def _section(self, **kw):
        base = {"hold_time": 5.0, "scroll_step_ms": 25}
        base.update(kw)
        return base

    def test_default_short_bottom_fits_uses_hold(self):
        widget = {
            "type": "two_row",
            "top_text": "TOP",
            "bottom_text": "HI",  # fits 160 canvas
            "font": "5x8",
        }
        result = two_row_visit_ms(widget, self._section(), canvas_w=160)
        # Static bottom → hold_time × 1000.
        assert result == 5000

    def test_default_overflow_bottom_scrolls_one_pass(self):
        widget = {
            "type": "two_row",
            "top_text": "TOP",
            "bottom_text": "x" * 40,  # 40 × 5 = 200 px overflow
            "font": "5x8",
        }
        result = two_row_visit_ms(widget, self._section(), canvas_w=160)
        # pass = (160 + 200) × 25 = 9000 ms.
        assert result == 9000

    def test_wrap_uses_max_of_loops_or_hold(self):
        widget = {
            "type": "two_row",
            "top_text": "TOP",
            "bottom_text": "tap",          # 3 × 5 = 15 px
            "font": "5x8",
            "bottom_text_wrap": True,
            "bottom_text_separator": " * ",  # 3 × 5 = 15 px
            "bottom_text_loops": 3,
        }
        result = two_row_visit_ms(widget, self._section(hold_time=1.0), canvas_w=160)
        # cycle = 15+15 = 30. 3 × 30 × 25 = 2250 ms. hold=1000. max=2250.
        assert result == 2250

    def test_scroll_through_uses_max_of_loops_or_hold(self):
        widget = {
            "type": "two_row",
            "top_text": "TOP",
            "bottom_text": "x" * 40,  # 200 px
            "font": "5x8",
            "bottom_text_scroll": "scroll_through",
            "bottom_text_loops": 2,
        }
        result = two_row_visit_ms(widget, self._section(hold_time=1.0), canvas_w=160)
        # cycle = 160 + 200 = 360. 2 × 360 × 25 = 18000 ms. hold=1000.
        # max = 18000.
        assert result == 18000

    def test_scroll_through_hold_wins(self):
        widget = {
            "type": "two_row",
            "top_text": "TOP",
            "bottom_text": "HI",  # 10 px
            "font": "5x8",
            "bottom_text_scroll": "scroll_through",
            # No loops → defaults to 1.
        }
        result = two_row_visit_ms(widget, self._section(hold_time=20.0), canvas_w=160)
        # cycle = 160 + 10 = 170. 1 × 170 × 25 = 4250 ms. hold=20000.
        # max = 20000.
        assert result == 20000
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_widgets.py::TestTwoRowVisitMs -v`
Expected: ImportError.

- [ ] **Step 3: Implement two_row_visit_ms**

Append to `tools/gif_plan/widgets.py`:

```python
def two_row_visit_ms(
    widget: dict,
    section: dict,
    canvas_w: int,
) -> int:
    """Visit time in ms for a TwoRowMessage widget.

    Branches on bottom_text_scroll, bottom_text_wrap, and overflow:
      - bottom_text_scroll='scroll_through': max(loops × cycle_ms,
        hold × 1000). cycle = canvas_w + bottom_width.
      - bottom_text_wrap=True: max(loops × cycle_ms, hold × 1000).
        cycle = bottom_width + separator_width.
      - Default + overflow: (canvas_w + bottom_width) × step_ms.
      - Default + fits: hold_time × 1000.
    """
    font = widget.get("bottom_font") or widget.get("font", "5x8")
    font_size = widget.get("bottom_font_size") or widget.get("font_size")
    bottom_text = widget.get("bottom_text", "")
    step_ms = int(section.get("scroll_step_ms") or 50)
    hold_ms = int(float(section.get("hold_time") or 0) * 1000)
    bottom_w = estimate_content_width_logical(bottom_text, font, font_size)

    if widget.get("bottom_text_scroll") == "scroll_through":
        cycle_px = canvas_w + bottom_w
        cycle_ms = cycle_px * step_ms
        loops = int(widget.get("bottom_text_loops") or 0) or 1
        return max(loops * cycle_ms, hold_ms)

    if widget.get("bottom_text_wrap"):
        sep = widget.get("bottom_text_separator") or " • "
        sep_w = estimate_content_width_logical(sep, font, font_size)
        cycle_ms = (bottom_w + sep_w) * step_ms
        loops = int(widget.get("bottom_text_loops") or 0)
        return max(loops * cycle_ms, hold_ms)

    if bottom_w > canvas_w:
        return (canvas_w + bottom_w) * step_ms
    return hold_ms
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_widgets.py -v`
Expected: 20 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/gif_plan/widgets.py tools/gif_plan/test_widgets.py
git commit -m "gif_plan: two_row_visit_ms (marquee / wrap / scroll_through)"
```

---

### Task 5: Image + gif widget visit time

**Files:**
- Modify: `tools/gif_plan/widgets.py`
- Modify: `tools/gif_plan/test_widgets.py`

- [ ] **Step 1: Write failing tests**

Append to `tools/gif_plan/test_widgets.py`:

```python
from pathlib import Path
from PIL import Image as PILImage

from tools.gif_plan.widgets import image_visit_ms, gif_visit_ms


class TestImageVisitMs:
    def test_no_text_uses_hold_seconds(self):
        widget = {"type": "image", "path": "x.png", "hold_seconds": 6.0}
        section = {"scroll_step_ms": 25}
        assert image_visit_ms(widget, section, canvas_w=160) == 6000

    def test_with_bottom_text_scroll_through(self):
        widget = {
            "type": "image",
            "path": "x.png",
            "hold_seconds": 8.0,
            "top_text": "TOP",
            "bottom_text": "HI",  # 10 px
            "bottom_text_scroll": "scroll_through",
        }
        section = {"scroll_step_ms": 25}
        # cycle = 160+10 = 170. 1 × 170 × 25 = 4250 ms. hold=8000ms.
        # max = 8000.
        assert image_visit_ms(widget, section, canvas_w=160) == 8000


class TestGifVisitMs:
    def test_unresolvable_path_uses_fallback(self):
        widget = {
            "type": "gif",
            "path": "/nonexistent/path.gif",
            "gif_loops": 3,
        }
        section = {"scroll_step_ms": 25}
        # Fallback: 100ms × n_frames assumed = 100 × 10 = 1000 per loop
        # × 3 loops = 3000. Implementation falls back to 100×10 estimate.
        result = gif_visit_ms(widget, section, canvas_w=160)
        assert result > 0
        # Emits a warning via the caller; visit just doesn't crash.

    def test_gif_loops_zero_uses_hold_seconds(self, tmp_path):
        # Create a real tiny gif so the path resolves.
        gif_path = tmp_path / "tiny.gif"
        frames = [
            PILImage.new("RGB", (8, 8), (255, 0, 0)),
            PILImage.new("RGB", (8, 8), (0, 255, 0)),
        ]
        frames[0].save(
            gif_path, save_all=True, append_images=frames[1:], duration=100, loop=0
        )
        widget = {
            "type": "gif",
            "path": str(gif_path),
            "gif_loops": 0,
            "hold_seconds": 5.0,
        }
        section = {"scroll_step_ms": 25}
        # gif_loops=0 → use hold_seconds × 1000.
        assert gif_visit_ms(widget, section, canvas_w=160) == 5000

    def test_gif_loops_positive_uses_frame_sum(self, tmp_path):
        gif_path = tmp_path / "tiny.gif"
        frames = [
            PILImage.new("RGB", (8, 8), (255, 0, 0)),
            PILImage.new("RGB", (8, 8), (0, 255, 0)),
        ]
        # 2 frames × 100ms each = 200ms per loop × 3 loops = 600ms.
        frames[0].save(
            gif_path, save_all=True, append_images=frames[1:], duration=100, loop=0
        )
        widget = {"type": "gif", "path": str(gif_path), "gif_loops": 3}
        section = {"scroll_step_ms": 25}
        assert gif_visit_ms(widget, section, canvas_w=160) == 600
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_widgets.py::TestImageVisitMs tools/gif_plan/test_widgets.py::TestGifVisitMs -v`
Expected: ImportError.

- [ ] **Step 3: Implement image_visit_ms and gif_visit_ms**

Append to `tools/gif_plan/widgets.py`:

```python
from pathlib import Path

try:
    from PIL import Image as PILImage
except ImportError:  # pragma: no cover
    PILImage = None  # Pillow is in the repo env; guard for portability.


def image_visit_ms(
    widget: dict,
    section: dict,
    canvas_w: int,
) -> int:
    """Visit time in ms for an image widget.

    If `bottom_text` is set → two-row text-overlay path (delegates
    to two_row_visit_ms shape). Otherwise: hold_seconds × 1000.

    NOTE: image widget `hold_seconds` is a widget-level field
    (unlike message/two_row's section-level `hold_time`). We read
    widget.hold_seconds here, not section.hold_time.
    """
    if widget.get("bottom_text"):
        # Inject a synthetic section dict so two_row's math can run
        # using hold_seconds (widget) instead of hold_time (section).
        synth_section = dict(section)
        synth_section["hold_time"] = widget.get("hold_seconds") or 0.0
        return two_row_visit_ms(widget, synth_section, canvas_w)
    return int(float(widget.get("hold_seconds") or 0) * 1000)


def _gif_frame_durations_ms(path: Path) -> list[int]:
    """Read per-frame durations from a gif. Returns ms per frame.
    Raises FileNotFoundError or generic Exception on bad input."""
    if PILImage is None:
        raise RuntimeError("Pillow not available")
    durations: list[int] = []
    with PILImage.open(path) as im:
        n = getattr(im, "n_frames", 1)
        for i in range(n):
            im.seek(i)
            dur = im.info.get("duration", 100)
            durations.append(int(dur))
    return durations


def gif_visit_ms(
    widget: dict,
    section: dict,
    canvas_w: int,
) -> int:
    """Visit time in ms for a gif widget.

    gif_loops > 0: sum(frame_durations) × gif_loops.
    gif_loops == 0: hold_seconds × 1000 (PR-64 unified behavior).

    If the path can't be resolved → fall back to 100ms × 10 frames =
    1000 ms per loop. Caller flags this separately via the warning
    pathway; this function doesn't raise.
    """
    if widget.get("bottom_text"):
        # Same delegation as image_visit_ms for the text-overlay case.
        synth_section = dict(section)
        synth_section["hold_time"] = widget.get("hold_seconds") or 0.0
        return two_row_visit_ms(widget, synth_section, canvas_w)

    loops = int(widget.get("gif_loops") or 0)
    if loops == 0:
        return int(float(widget.get("hold_seconds") or 0) * 1000)

    path = Path(widget.get("path", ""))
    try:
        durations = _gif_frame_durations_ms(path)
        per_loop = sum(durations)
    except Exception:
        per_loop = 100 * 10  # 1000 ms fallback for unresolvable paths.
    return per_loop * loops
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_widgets.py -v`
Expected: 25 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/gif_plan/widgets.py tools/gif_plan/test_widgets.py
git commit -m "gif_plan: image_visit_ms + gif_visit_ms (with Pillow frame reader)"
```

---

### Task 6: Section + playlist totals

**Files:**
- Create: `tools/gif_plan/totals.py`
- Create: `tools/gif_plan/test_totals.py`

- [ ] **Step 1: Write failing tests**

Create `tools/gif_plan/test_totals.py`:

```python
"""Tests for tools/gif_plan/totals.py — section + playlist aggregation."""

from __future__ import annotations

from tools.gif_plan.totals import (
    section_total_ms,
    playlist_total_ms,
    recommended_render_duration_s,
)


class TestSectionTotal:
    def test_single_widget_swap(self):
        section = {
            "mode": "swap",
            "hold_time": 4.0,
            "scroll_step_ms": 25,
            "loop_count": 1,
            "widget": [{"type": "message", "text": "HI", "font": "5x8"}],
        }
        display = {"cols": 32, "chain": 5, "default_scale": 1}
        # Static text → 4000 ms × loop_count 1 = 4000.
        assert section_total_ms(section, display) == 4000

    def test_multi_widget_swap(self):
        section = {
            "mode": "swap",
            "hold_time": 4.0,
            "scroll_step_ms": 25,
            "loop_count": 2,
            "widget": [
                {"type": "message", "text": "HI", "font": "5x8"},
                {"type": "message", "text": "BYE", "font": "5x8"},
            ],
        }
        display = {"cols": 32, "chain": 5, "default_scale": 1}
        # Two static texts → (4000 + 4000) × 2 = 16000.
        assert section_total_ms(section, display) == 16000

    def test_forever_scroll_returns_none(self):
        section = {"mode": "forever_scroll", "widget": [{"type": "message", "text": "x"}]}
        display = {"cols": 32, "chain": 5, "default_scale": 1}
        # forever_scroll / infini_scroll are runtime-dependent. v1 emits
        # None for the caller to flag.
        assert section_total_ms(section, display) is None


class TestPlaylistTotal:
    def test_single_section(self):
        config = {
            "display": {"cols": 32, "chain": 5, "default_scale": 1},
            "playlist": {"section": [
                {
                    "mode": "swap",
                    "hold_time": 3.0,
                    "loop_count": 1,
                    "widget": [{"type": "message", "text": "HI", "font": "5x8"}],
                }
            ]},
        }
        assert playlist_total_ms(config) == 3000

    def test_two_sections(self):
        config = {
            "display": {"cols": 32, "chain": 5, "default_scale": 1},
            "playlist": {"section": [
                {
                    "mode": "swap",
                    "hold_time": 3.0,
                    "loop_count": 1,
                    "widget": [{"type": "message", "text": "HI", "font": "5x8"}],
                },
                {
                    "mode": "swap",
                    "hold_time": 5.0,
                    "loop_count": 1,
                    "widget": [{"type": "message", "text": "BYE", "font": "5x8"}],
                },
            ]},
        }
        # 3000 + 5000 = 8000.
        assert playlist_total_ms(config) == 8000

    def test_forever_scroll_excluded_from_total(self):
        config = {
            "display": {"cols": 32, "chain": 5, "default_scale": 1},
            "playlist": {"section": [
                {
                    "mode": "forever_scroll",
                    "widget": [{"type": "message", "text": "HI"}],
                },
                {
                    "mode": "swap",
                    "hold_time": 3.0,
                    "loop_count": 1,
                    "widget": [{"type": "message", "text": "HI", "font": "5x8"}],
                },
            ]},
        }
        # forever_scroll contributes nothing to the deterministic total.
        assert playlist_total_ms(config) == 3000


class TestRecommendedRenderDuration:
    def test_seven_seconds_total_plus_buffer(self):
        # 7000 ms → ceil(7) + 1 = 8.
        assert recommended_render_duration_s(7000) == 8

    def test_seven_point_one_seconds_rounds_up(self):
        # 7100 ms → ceil(7.1) + 1 = 9.
        assert recommended_render_duration_s(7100) == 9

    def test_zero_ms_still_returns_buffer(self):
        # Empty playlist → just the 1 sec buffer (sensible floor).
        assert recommended_render_duration_s(0) == 1
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_totals.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement totals**

Create `tools/gif_plan/totals.py`:

```python
"""Section + playlist aggregation for the gif planner."""

from __future__ import annotations

import math

from tools.gif_plan.widgets import (
    canvas_width_logical,
    ticker_message_visit_ms,
    two_row_visit_ms,
    image_visit_ms,
    gif_visit_ms,
)


_WIDGET_DISPATCH = {
    "message": ticker_message_visit_ms,
    "countdown": ticker_message_visit_ms,  # same engine path as message.
    "two_row": two_row_visit_ms,
    "image": image_visit_ms,
    "still": image_visit_ms,
    "gif": gif_visit_ms,
}


def _widget_visit_ms(widget: dict, section: dict, canvas_w: int) -> int:
    """Dispatch a single widget to its visit-time computer.
    Returns 0 for widget types the planner doesn't cover yet
    (weather, mlb, crypto, rss_feed, etc) — those have data-fetch
    timing that's not deterministic from config alone."""
    fn = _WIDGET_DISPATCH.get(widget.get("type", ""))
    if fn is None:
        return 0
    return fn(widget, section, canvas_w)


def section_total_ms(section: dict, display: dict) -> int | None:
    """Total ms for one section. Returns None for forever_scroll /
    infini_scroll (runtime-dependent — caller flags as info)."""
    mode = section.get("mode", "swap")
    if mode in ("forever_scroll", "infini_scroll"):
        return None
    canvas_w = canvas_width_logical(display, section)
    widgets = section.get("widget", [])
    per_visit = sum(_widget_visit_ms(w, section, canvas_w) for w in widgets)
    loop_count = int(section.get("loop_count") or 1)
    return per_visit * loop_count


def playlist_total_ms(config: dict) -> int:
    """Total ms across all swap-mode sections. forever_scroll and
    infini_scroll sections contribute 0 (their durations are
    runtime-dependent)."""
    display = config.get("display", {})
    sections = (config.get("playlist") or {}).get("section") or []
    total = 0
    for s in sections:
        section_ms = section_total_ms(s, display)
        if section_ms is not None:
            total += section_ms
    return total


def recommended_render_duration_s(total_ms: int) -> int:
    """Ceiling-of-seconds + 1 sec buffer to capture the trailing
    transition. Floor of 1 so empty playlists still produce something."""
    return max(1, math.ceil(total_ms / 1000) + 1)
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_totals.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/gif_plan/totals.py tools/gif_plan/test_totals.py
git commit -m "gif_plan: section + playlist totals + recommended render duration"
```

---

### Task 7: Heuristic flags

**Files:**
- Create: `tools/gif_plan/flags.py`
- Create: `tools/gif_plan/test_flags.py`

- [ ] **Step 1: Write failing tests**

Create `tools/gif_plan/test_flags.py`:

```python
"""Tests for tools/gif_plan/flags.py — heuristic checks."""

from __future__ import annotations

from tools.gif_plan.flags import check_all


class TestMidPassCutoff:
    def test_no_header_emits_suggestion(self):
        # No `# render-duration: N` → info-level suggestion, not error.
        flags = check_all(
            config={"display": {"cols": 32, "chain": 5}, "playlist": {"section": []}},
            playlist_total_ms=10000,
            render_duration_header=None,
            sections_summary=[],
        )
        codes = [f["code"] for f in flags]
        assert "render_duration_suggestion" in codes
        assert all(f["severity"] != "error" for f in flags if f["code"] == "render_duration_suggestion")

    def test_header_too_short_is_error(self):
        flags = check_all(
            config={"display": {"cols": 32, "chain": 5}, "playlist": {"section": []}},
            playlist_total_ms=10000,
            render_duration_header=5,  # User said 5s but math says 11s.
            sections_summary=[],
        )
        errs = [f for f in flags if f["code"] == "mid_pass_cutoff"]
        assert len(errs) == 1
        assert errs[0]["severity"] == "error"

    def test_header_long_enough_is_quiet(self):
        flags = check_all(
            config={"display": {"cols": 32, "chain": 5}, "playlist": {"section": []}},
            playlist_total_ms=10000,
            render_duration_header=12,
            sections_summary=[],
        )
        assert not any(f["code"] == "mid_pass_cutoff" for f in flags)


class TestScrollStepBounds:
    def test_too_fast_emits_warning(self):
        sections = [{"index": 0, "scroll_step_ms": 15}]
        flags = check_all(
            config={"display": {"cols": 32, "chain": 5}, "playlist": {"section": [{"scroll_step_ms": 15}]}},
            playlist_total_ms=0,
            render_duration_header=None,
            sections_summary=sections,
        )
        warns = [f for f in flags if f["code"] == "scroll_step_too_fast"]
        assert len(warns) == 1
        assert warns[0]["severity"] == "warning"
        assert "15" in warns[0]["message"]

    def test_too_slow_emits_warning(self):
        sections = [{"index": 0, "scroll_step_ms": 100}]
        flags = check_all(
            config={"display": {"cols": 32, "chain": 5}, "playlist": {"section": [{"scroll_step_ms": 100}]}},
            playlist_total_ms=0,
            render_duration_header=None,
            sections_summary=sections,
        )
        warns = [f for f in flags if f["code"] == "scroll_step_too_slow"]
        assert len(warns) == 1

    def test_in_band_is_quiet(self):
        sections = [{"index": 0, "scroll_step_ms": 25}]
        flags = check_all(
            config={"display": {"cols": 32, "chain": 5}, "playlist": {"section": [{"scroll_step_ms": 25}]}},
            playlist_total_ms=0,
            render_duration_header=None,
            sections_summary=sections,
        )
        assert not any(f["code"].startswith("scroll_step_") for f in flags)


class TestZeroCycle:
    def test_wrap_with_empty_text(self):
        config = {
            "display": {"cols": 32, "chain": 5},
            "playlist": {"section": [
                {
                    "mode": "swap",
                    "hold_time": 1.0,
                    "widget": [{
                        "type": "two_row",
                        "top_text": "T",
                        "bottom_text": "",  # zero content
                        "bottom_text_wrap": True,
                    }],
                },
            ]},
        }
        flags = check_all(
            config=config,
            playlist_total_ms=0,
            render_duration_header=None,
            sections_summary=[],
        )
        errs = [f for f in flags if f["code"] == "zero_cycle_width"]
        assert len(errs) == 1
        assert errs[0]["severity"] == "error"


class TestPixelMapperInfo:
    def test_pixel_mapper_config_present(self):
        config = {
            "display": {"cols": 64, "chain": 8, "pixel_mapper_config": "U-mapper"},
            "playlist": {"section": []},
        }
        flags = check_all(
            config=config,
            playlist_total_ms=0,
            render_duration_header=None,
            sections_summary=[],
        )
        info = [f for f in flags if f["code"] == "pixel_mapper_config_present"]
        assert len(info) == 1
        assert info[0]["severity"] == "info"
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_flags.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement flags**

Create `tools/gif_plan/flags.py`:

```python
"""Heuristic flags for the gif planner.

Each flag is a dict: {severity, location, code, message, fix}.
Severities: info | warning | error. Errors set the CLI exit code 2;
warnings set 1; info-only is 0.
"""

from __future__ import annotations

from tools.gif_plan.totals import recommended_render_duration_s
from tools.gif_plan.widgets import (
    canvas_width_logical,
    estimate_content_width_logical,
)


SCROLL_STEP_MIN = 20
SCROLL_STEP_MAX = 80


def _flag(severity: str, location: str, code: str, message: str, fix: str) -> dict:
    return {
        "severity": severity,
        "location": location,
        "code": code,
        "message": message,
        "fix": fix,
    }


def check_all(
    *,
    config: dict,
    playlist_total_ms: int,
    render_duration_header: int | None,
    sections_summary: list[dict],
) -> list[dict]:
    """Run every heuristic check and return the combined flag list."""
    flags: list[dict] = []
    flags.extend(_check_render_duration(playlist_total_ms, render_duration_header))
    flags.extend(_check_scroll_steps(config))
    flags.extend(_check_zero_cycles(config))
    flags.extend(_check_pixel_mapper_config(config))
    return flags


def _check_render_duration(
    playlist_total_ms: int,
    header: int | None,
) -> list[dict]:
    recommended = recommended_render_duration_s(playlist_total_ms)
    if header is None:
        if playlist_total_ms > 0:
            return [_flag(
                "info",
                "playlist",
                "render_duration_suggestion",
                f"No `# render-duration:` header found; recommended value is {recommended}.",
                f"Add a `# render-duration: {recommended}` comment to the top of the TOML.",
            )]
        return []
    if header * 1000 < playlist_total_ms:
        cut_ms = playlist_total_ms - header * 1000
        return [_flag(
            "error",
            "playlist",
            "mid_pass_cutoff",
            f"render-duration: {header} cuts ~{cut_ms}ms of playlist content mid-pass.",
            f"Bump to {recommended} (matches the deterministic playlist total + 1s buffer).",
        )]
    return []


def _check_scroll_steps(config: dict) -> list[dict]:
    flags: list[dict] = []
    sections = (config.get("playlist") or {}).get("section") or []
    for i, section in enumerate(sections):
        step = int(section.get("scroll_step_ms") or 50)
        if step < SCROLL_STEP_MIN:
            flags.append(_flag(
                "warning",
                f"section[{i}]",
                "scroll_step_too_fast",
                f"scroll_step_ms={step} below the readable range ({SCROLL_STEP_MIN}-{SCROLL_STEP_MAX}ms); canonical is 25-30.",
                f"Raise scroll_step_ms to 25 (canonical) or higher.",
            ))
        elif step > SCROLL_STEP_MAX:
            flags.append(_flag(
                "warning",
                f"section[{i}]",
                "scroll_step_too_slow",
                f"scroll_step_ms={step} above the readable range ({SCROLL_STEP_MIN}-{SCROLL_STEP_MAX}ms); canonical is 25-30.",
                f"Lower scroll_step_ms to 30 (canonical) or below.",
            ))
    return flags


def _check_zero_cycles(config: dict) -> list[dict]:
    """Detect wrap/scroll_through widgets with zero content_width."""
    flags: list[dict] = []
    display = config.get("display", {})
    sections = (config.get("playlist") or {}).get("section") or []
    for i, section in enumerate(sections):
        canvas_w = canvas_width_logical(display, section)
        for j, w in enumerate(section.get("widget", [])):
            wrap = w.get("text_wrap") or w.get("bottom_text_wrap")
            scroll_through = w.get("bottom_text_scroll") == "scroll_through"
            if not (wrap or scroll_through):
                continue
            text = (
                w.get("bottom_text")
                if (w.get("bottom_text_wrap") or scroll_through)
                else w.get("text", "")
            )
            font = w.get("font", "5x8")
            content_w = estimate_content_width_logical(text or "", font)
            if content_w == 0:
                flags.append(_flag(
                    "error",
                    f"section[{i}].widget[{j}]",
                    "zero_cycle_width",
                    "Widget has wrap/scroll_through enabled but the relevant text is empty — there's no cycle to count.",
                    "Set non-empty text or disable wrap/scroll_through.",
                ))
    return flags


def _check_pixel_mapper_config(config: dict) -> list[dict]:
    display = config.get("display", {})
    if "pixel_mapper_config" in display or "pixel_mapper_config" in display:
        return [_flag(
            "info",
            "display",
            "pixel_mapper_config_present",
            "pixel_mapper_config detected; canvas-width math is approximate for bigsign-style configs in v1.",
            "Sanity-check the recommended render-duration against the visual output.",
        )]
    return []
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_flags.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/gif_plan/flags.py tools/gif_plan/test_flags.py
git commit -m "gif_plan: heuristic flags (mid-pass, scroll-step, zero-cycle, pixel-mapper)"
```

---

### Task 8: CLI entry point

**Files:**
- Create: `tools/gif_plan/plan.py`
- Create: `tools/gif_plan/test_plan.py`

- [ ] **Step 1: Write failing tests**

Create `tools/gif_plan/test_plan.py`:

```python
"""Integration tests for tools/gif_plan/plan.py CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "python", str(REPO_ROOT / "tools" / "gif_plan" / "plan.py"), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def _write_config(tmp_path: Path, content: str, *, header: str = "") -> Path:
    cfg = tmp_path / "demo.toml"
    cfg.write_text((header + "\n" + content).strip() + "\n")
    return cfg


class TestCliExitCodes:
    def test_clean_config_exits_zero(self, tmp_path):
        cfg = _write_config(tmp_path, """
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1

[[playlist.section]]
mode = "swap"
hold_time = 4.0
scroll_step_ms = 25

[[playlist.section.widget]]
type = "message"
text = "HELLO"
font = "5x8"
""", header="# render-duration: 5")
        r = _run_cli(str(cfg), "--json")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["total_ms"] == 4000
        assert data["recommended_render_duration_s"] == 5
        # Header matches recommended → no mid_pass_cutoff flag.
        codes = [f["code"] for f in data["flags"]]
        assert "mid_pass_cutoff" not in codes

    def test_warning_config_exits_one(self, tmp_path):
        cfg = _write_config(tmp_path, """
[display]
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 2.0
scroll_step_ms = 10

[[playlist.section.widget]]
type = "message"
text = "HI"
font = "5x8"
""", header="# render-duration: 3")
        r = _run_cli(str(cfg), "--json")
        assert r.returncode == 1, r.stderr
        data = json.loads(r.stdout)
        codes = [f["code"] for f in data["flags"]]
        assert "scroll_step_too_fast" in codes

    def test_error_config_exits_two(self, tmp_path):
        cfg = _write_config(tmp_path, """
[display]
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 4.0
scroll_step_ms = 25

[[playlist.section.widget]]
type = "two_row"
top_text = "T"
bottom_text = ""
bottom_text_wrap = true
""", header="# render-duration: 5")
        r = _run_cli(str(cfg), "--json")
        # bottom_text_wrap=true with empty bottom_text → engine would
        # reject this at config-load. Our planner also flags it.
        # Note: this config would also fail led_ticker validation, but
        # the planner shouldn't require a valid config to plan.
        assert r.returncode == 2, r.stderr


class TestRenderDurationHeader:
    def test_reads_header_from_toml_comment(self, tmp_path):
        cfg = _write_config(tmp_path, """
[display]
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 4.0
scroll_step_ms = 25

[[playlist.section.widget]]
type = "message"
text = "HI"
font = "5x8"
""", header="# render-duration: 8")
        r = _run_cli(str(cfg), "--json")
        data = json.loads(r.stdout)
        assert data["render_duration_header"] == 8


class TestSchema:
    def test_json_output_has_required_keys(self, tmp_path):
        cfg = _write_config(tmp_path, """
[display]
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 3.0

[[playlist.section.widget]]
type = "message"
text = "HI"
font = "5x8"
""")
        r = _run_cli(str(cfg), "--json")
        data = json.loads(r.stdout)
        for key in (
            "config_path", "sections", "total_ms",
            "recommended_render_duration_s", "flags", "render_duration_header",
        ):
            assert key in data, f"Missing top-level key: {key}"
        section = data["sections"][0]
        for key in ("index", "mode", "section_total_ms", "widgets"):
            assert key in section, f"Missing section key: {key}"
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_plan.py -v`
Expected: subprocess errors / module not found.

- [ ] **Step 3: Implement the CLI**

Create `tools/gif_plan/plan.py`:

```python
"""CLI entry point for the led-ticker demo-gif planner.

Usage:
    uv run python tools/gif_plan/plan.py <config.toml> [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Mirror tools/render_demo/render.py — make the repo root importable so
# `from tools.gif_plan.x import y` works when invoked as a script.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Python 3.11+ has tomllib in stdlib.
try:
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from tools.gif_plan.flags import check_all  # noqa: E402
from tools.gif_plan.totals import (  # noqa: E402
    playlist_total_ms,
    recommended_render_duration_s,
    section_total_ms,
)
from tools.gif_plan.widgets import (  # noqa: E402
    canvas_width_logical,
    estimate_content_width_logical,
    gif_visit_ms,
    image_visit_ms,
    ticker_message_visit_ms,
    two_row_visit_ms,
)


_HEADER_RE = re.compile(r"^\s*#\s*render-duration\s*:\s*(\d+)\s*$", re.MULTILINE)


def _read_render_duration_header(text: str) -> int | None:
    m = _HEADER_RE.search(text)
    return int(m.group(1)) if m else None


_WIDGET_DISPATCH = {
    "message": ticker_message_visit_ms,
    "countdown": ticker_message_visit_ms,
    "two_row": two_row_visit_ms,
    "image": image_visit_ms,
    "still": image_visit_ms,
    "gif": gif_visit_ms,
}


def _summarize_widget(widget: dict, section: dict, canvas_w: int) -> dict:
    fn = _WIDGET_DISPATCH.get(widget.get("type", ""))
    if fn is None:
        return {
            "type": widget.get("type", "unknown"),
            "visit_ms": 0,
            "note": "widget type not modelled deterministically",
        }
    visit_ms = fn(widget, section, canvas_w)
    return {"type": widget.get("type"), "visit_ms": visit_ms}


def plan(config_path: Path) -> dict:
    raw = config_path.read_text(encoding="utf-8")
    header = _read_render_duration_header(raw)
    config = tomllib.loads(raw)
    display = config.get("display", {})
    sections_raw = (config.get("playlist") or {}).get("section") or []

    sections_summary: list[dict] = []
    for i, s in enumerate(sections_raw):
        canvas_w = canvas_width_logical(display, s)
        widgets = [_summarize_widget(w, s, canvas_w) for w in s.get("widget", [])]
        total = section_total_ms(s, display)
        sections_summary.append({
            "index": i,
            "mode": s.get("mode", "swap"),
            "hold_time": s.get("hold_time"),
            "scroll_step_ms": s.get("scroll_step_ms"),
            "loop_count": s.get("loop_count", 1),
            "canvas_w": canvas_w,
            "widgets": widgets,
            "section_total_ms": total,
        })

    total_ms = playlist_total_ms(config)
    flags = check_all(
        config=config,
        playlist_total_ms=total_ms,
        render_duration_header=header,
        sections_summary=sections_summary,
    )

    return {
        "config_path": str(config_path),
        "render_duration_header": header,
        "sections": sections_summary,
        "total_ms": total_ms,
        "recommended_render_duration_s": recommended_render_duration_s(total_ms),
        "flags": flags,
    }


def _exit_code(flags: list[dict]) -> int:
    severities = {f["severity"] for f in flags}
    if "error" in severities:
        return 2
    if "warning" in severities:
        return 1
    return 0


def _human_render(plan_data: dict) -> str:
    """Plain-text summary for terminal use."""
    lines: list[str] = []
    lines.append(f"config: {plan_data['config_path']}")
    lines.append(f"playlist_total: {plan_data['total_ms']}ms")
    lines.append(f"recommended_render_duration: {plan_data['recommended_render_duration_s']}s")
    header = plan_data["render_duration_header"]
    if header is not None:
        lines.append(f"header `# render-duration:` found: {header}s")
    lines.append("")
    for s in plan_data["sections"]:
        total = s["section_total_ms"]
        total_str = f"{total}ms" if total is not None else "runtime-dependent (forever_scroll)"
        lines.append(f"section[{s['index']}] mode={s['mode']} loop_count={s['loop_count']} → {total_str}")
        for j, w in enumerate(s["widgets"]):
            lines.append(f"  widget[{j}] type={w['type']} visit={w.get('visit_ms', 0)}ms")
    if plan_data["flags"]:
        lines.append("")
        lines.append("flags:")
        for f in plan_data["flags"]:
            lines.append(f"  [{f['severity'].upper()}] {f['location']} :: {f['code']}")
            lines.append(f"    {f['message']}")
            lines.append(f"    fix: {f['fix']}")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Plan a led-ticker demo gif")
    p.add_argument("config", type=Path, help="Path to the demo config TOML")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = p.parse_args()

    data = plan(args.config)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(_human_render(data))
    return _exit_code(data["flags"])


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_plan.py -v`
Expected: All passing.

- [ ] **Step 5: Run the CLI manually against an existing demo**

Run: `PYTHONPATH=. uv run python -m tools.gif_plan.plan docs/site/demos-pinned/two_row-wrap.toml`
Expected: human-readable output showing the demo's math, exit code 0 (clean).

- [ ] **Step 6: Commit**

```bash
git add tools/gif_plan/plan.py tools/gif_plan/test_plan.py
git commit -m "gif_plan: CLI entry point with --json + exit codes"
```

---

### Task 9: Dogfood + drift tripwire

**Files:**
- Create: `tools/gif_plan/test_dogfood.py`

- [ ] **Step 1: Write the dogfood test**

Create `tools/gif_plan/test_dogfood.py`:

```python
"""Dogfood: run the planner against every pinned demo config.

Two assertions:
  1. No false-positive mid_pass_cutoff errors on already-shipped demos.
  2. recommended_render_duration_s is within ±20% of each demo's
     `# render-duration:` header. Catches drift in formulas or canonical
     demos.

The 20% band is intentionally loose — the planner's content-width
estimates are approximations and we're not trying to match the render
engine's measurements exactly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.gif_plan.plan import plan

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO_ROOT / "docs" / "site" / "demos-pinned"


def _all_demo_configs() -> list[Path]:
    return sorted(DEMO_DIR.glob("*.toml"))


@pytest.mark.parametrize("cfg_path", _all_demo_configs(), ids=lambda p: p.name)
def test_no_false_positive_mid_pass(cfg_path: Path):
    """Each shipped demo's `# render-duration:` should NOT trigger a
    mid_pass_cutoff error. If one trips, either the demo is genuinely
    miscalibrated (file a bug) or the planner's math is off."""
    result = plan(cfg_path)
    errs = [f for f in result["flags"] if f["code"] == "mid_pass_cutoff"]
    assert not errs, (
        f"{cfg_path.name} would trip mid_pass_cutoff: {errs}. "
        f"Either the demo header is wrong or the planner overestimates."
    )


@pytest.mark.parametrize("cfg_path", _all_demo_configs(), ids=lambda p: p.name)
def test_recommendation_within_loose_band(cfg_path: Path):
    """Drift tripwire — recommendation within ±20% of header."""
    result = plan(cfg_path)
    header = result["render_duration_header"]
    if header is None:
        pytest.skip("no header to compare against")
    if result["total_ms"] == 0:
        pytest.skip("data-fetch widget — visit time not deterministic")
    rec = result["recommended_render_duration_s"]
    low = max(1, int(header * 0.8))
    high = int(header * 1.2) + 1
    assert low <= rec <= high, (
        f"{cfg_path.name}: header {header}s vs planner {rec}s out of "
        f"±20% band ({low}-{high})."
    )
```

- [ ] **Step 2: Run dogfood — see which demos fail**

Run: `PYTHONPATH=. uv run pytest tools/gif_plan/test_dogfood.py -v`
Expected: most pass; a few may need formula tweaks or skip patterns added. If a demo trips `mid_pass_cutoff`, investigate:
- Is the demo's `# render-duration:` actually too short? Then it's a real bug — open a follow-up issue, but `xfail` the test for now.
- Is the planner's content-width overestimating? Either bump the BDF cell width or special-case the demo.

For data-fetch widgets (weather, coinbase, mlb, rss_feed, etherscan, coingecko), the planner returns visit_ms=0 (handled by `_summarize_widget`'s fallback) — the test skips when `total_ms == 0`.

- [ ] **Step 3: Tune any formula or add per-demo skip until all pass**

If a real demo trips a flag, investigate first; only skip if the demo is genuinely covered by a known v1 limitation (e.g., bigsign pixel_mapper_config math).

- [ ] **Step 4: Commit**

```bash
git add tools/gif_plan/test_dogfood.py
git commit -m "gif_plan: dogfood against 35 pinned demos + drift tripwire"
```

---

### Task 10: Makefile target

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add the new target**

Open the `Makefile` at the repo root. Find the `.PHONY:` line near the top and append `plan-gif`. Add a new target near the existing `render-demo` target:

```makefile
plan-gif:  ## Plan a demo gif (math + flags). Usage: make plan-gif CONFIG=path/to.toml
	uv run python -m tools.gif_plan.plan $(CONFIG)
```

Make sure the target uses a real tab, not spaces.

- [ ] **Step 2: Sanity-check the target**

Run: `make plan-gif CONFIG=docs/site/demos-pinned/two_row-wrap.toml`
Expected: human-readable output, exit code 0.

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "make: plan-gif target wraps tools/gif_plan/plan.py"
```

---

### Task 11: SKILL.md — main file

**Files:**
- Create: `.claude/skills/making-a-gif/SKILL.md`

- [ ] **Step 1: Write the skill file**

Create `.claude/skills/making-a-gif/SKILL.md`:

````markdown
---
name: making-a-gif
description: Use when a user (or sub-agent) wants to plan or make a demo gif of a led-ticker config. Triggers on "make a gif of...", "demo gif for X", "what render-duration should I use", "preview this widget", or "let me see what this looks like". Computes deterministic playtime math via tools/gif_plan/, flags timing/scroll-step bugs, adds judgment-layer color/contrast guidance for LED panel quirks, and proposes the exact `make render-demo` command.
---

# Making a led-ticker Demo Gif

You are helping the user plan a demo gif for the led-ticker project. There are two modes: **docs** (polished, committed under `docs/site/public/demos-pinned/`) and **dev** (throwaway preview to `/tmp/`).

## Step 0: Detect mode

- **Docs mode** signals:
  - "demo for docs", "add to demos-pinned"
  - User points at a path under `docs/site/`
  - Mentions captions or commit message
  - Adding a new entry to a widget's docs page

- **Dev mode** signals:
  - "preview", "let me see what this looks like"
  - "spot check this", "render a quick gif"
  - Sub-agent context: iterating on a widget/transition feature
  - Output path is `/tmp/` or unset

If ambiguous, ask: "Polished demo for `docs/site/demos-pinned/`, or quick preview to `/tmp/`?"

Announce: "Using making-a-gif skill in **\<mode\>** mode."

## Step 1: Get a TOML to plan

- If the user pasted a config inline → save to `/tmp/gif-plan-<topic>.toml`.
- If the user gave a path → use it as-is.
- If the user only described intent ("make a gif of a two_row scroll_through with a long song title") → draft a minimal config inline, save to `/tmp/`, then proceed.

## Step 2: Run the deterministic planner

```bash
uv run python -m tools.gif_plan.plan <path> --json
```

Parse the JSON output. The schema:
- `total_ms`: deterministic playlist total.
- `recommended_render_duration_s`: ceiling-of-seconds + 1 buffer.
- `render_duration_header`: existing `# render-duration:` value (or null).
- `sections`: per-section breakdown.
- `flags`: list of `{severity, location, code, message, fix}`.

Exit code:
- `0` → clean.
- `1` → warnings only (relay, continue).
- `2` → errors (relay, stop until fixed).

## Step 3: Apply the judgment overlay

The CLI does NOT cover these — you do.

### LED panel color quirks

Scan the config's color fields (`font_color`, `top_color`, `bottom_color`, `bg_color`, `border`, separator colors). For each:

- **Pure black `[0, 0, 0]`** → LED panel renders this as INVISIBLE (off-pixels). Surface as a warning unless the user is intentionally using black as a "transparent" effect. Suggest `[10, 10, 10]` or a brand color.
- **Pure white `[255, 255, 255]`** → washes blue-white on the panel. Suggest `[254, 255, 204]` (cream, from `config.moonbunny.example.toml`) for warm-white or a brand color.
- **Dark-on-dark** (luminance Δ < 30): low contrast risk. Suggest previewing at `brightness = 60` first.

### Brand color palette (sampled from config.bigsign.example.toml + moonbunny configs)

Use these as fallback suggestions when the user's color is flagged:

- Magenta (IG brand): `[225, 48, 108]`
- Cream / warm white: `[254, 255, 204]` or `[255, 240, 200]`
- Cyan: `[120, 230, 255]`
- Soft pink: `[255, 176, 240]`
- Lavender: `[189, 169, 234]`

### Caption drafting (docs mode only)

Before writing a caption, read 2-3 existing `<DemoGif caption="...">` lines from the relevant docs page (`docs/site/src/content/docs/widgets/<widget>.mdx`) to match voice. Existing captions are matter-of-fact and visual: "held magenta `BREAKING` on top, cyan `tap to subscribe` wrapping continuously on the bottom with a rainbow `*` separator". Mirror that shape.

## Step 4: Surface the recommendation

Output to the user:

1. **Math summary**: total ms, recommended render-duration, per-section breakdown.
2. **Flags from CLI**: relay verbatim with severity icons.
3. **Color/contrast notes** (from Step 3).
4. **Exact command to run**:
   - Docs mode: `make render-demo CONFIG=docs/site/demos-pinned/<name>.toml OUT=docs/site/public/demos-pinned/<name>.gif` (and update the `# render-duration:` header in the source TOML if missing).
   - Dev mode: `make render-demo CONFIG=/tmp/gif-plan-<topic>.toml OUT=/tmp/preview-<topic>-<ts>.gif`.

For dev mode, recommend a SHORTER render-duration than `recommended_render_duration_s` — just one full pass + a half-second beat, since the goal is verification, not a polished loop. Formula: `ceil(longest_widget_pass_ms / 1000) + 1`.

## What this skill does NOT do

- Run `make render-demo` itself. Rendering takes ~10 seconds; the user often iterates on the config first. Always suggest the command, never execute.
- Modify the user's config file unless explicitly asked.
- Make math judgments the CLI is supposed to make. If you find yourself computing scroll-pass duration in your head, that's a sign the CLI should be doing it — re-invoke the CLI instead.

## Examples

See `examples/docs-mode.md` and `examples/dev-mode.md` for end-to-end walkthroughs.
````

- [ ] **Step 2: Commit**

```bash
mkdir -p .claude/skills/making-a-gif
git add .claude/skills/making-a-gif/SKILL.md
git commit -m "skill: making-a-gif SKILL.md (workflow + mode detection + color overlay)"
```

---

### Task 12: Examples — docs-mode + dev-mode walkthroughs

**Files:**
- Create: `.claude/skills/making-a-gif/examples/docs-mode.md`
- Create: `.claude/skills/making-a-gif/examples/dev-mode.md`

- [ ] **Step 1: Write docs-mode example**

Create `.claude/skills/making-a-gif/examples/docs-mode.md`:

````markdown
# Example: docs mode

**User**: "I want to add a demo gif for the new `scroll_through` mode on `two_row`."

**Skill response**:

> Using making-a-gif skill in **docs** mode.

Plan:

1. Create a new pinned-demo TOML: `docs/site/demos-pinned/two_row-scroll_through.toml`.
2. Add a `# render-duration:` header based on planner math.
3. Render via `make render-demo`.
4. Wire `<DemoGif>` into `docs/site/src/content/docs/widgets/two_row.mdx`.

**Initial config draft**:

```toml
# render-duration: <to be filled by planner>
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1

[[playlist.section]]
mode = "swap"
hold_time = 7.0
scroll_step_ms = 25

[[playlist.section.widget]]
type = "two_row"
top_text = "NOW PLAYING"
top_font = "5x8"
top_color = [225, 48, 108]
bottom_text = "Some Long Song Title — Album Name (2026)"
bottom_font = "5x8"
bottom_color = [120, 230, 255]
bottom_text_scroll = "scroll_through"
```

**Run planner**:

```bash
uv run python -m tools.gif_plan.plan /tmp/two_row-scroll_through.toml --json
```

**Output (abbrev)**:
- `total_ms`: 9000
- `recommended_render_duration_s`: 10
- Flags: only `render_duration_suggestion` (info) — no header yet.

**Color overlay**:
- Top color `[225, 48, 108]` — IG brand magenta, fine.
- Bottom color `[120, 230, 255]` — cyan, fine.
- No contrast issues against the default black background.

**Caption (matching voice from `widgets/two_row.mdx`)**:
> held magenta `NOW PLAYING` on top, cyan song title flies fully offscreen-to-offscreen on the bottom — one pass per visit

**Next steps for the user**:
1. Save to `docs/site/demos-pinned/two_row-scroll_through.toml` with `# render-duration: 10` header.
2. Run: `make render-demo CONFIG=docs/site/demos-pinned/two_row-scroll_through.toml OUT=docs/site/public/demos-pinned/two_row-scroll_through.gif`.
3. Wire into the docs page with the drafted caption.
4. Commit all three new files.
````

- [ ] **Step 2: Write dev-mode example**

Create `.claude/skills/making-a-gif/examples/dev-mode.md`:

````markdown
# Example: dev mode

**Sub-agent context**: "I'm iterating on the new `border_chase_speed` field for `RainbowChaseBorder`. Render a quick preview so I can spot-check the speed=20 setting."

**Skill response**:

> Using making-a-gif skill in **dev** mode.

Plan:

1. Draft a minimal TOML exercising the change.
2. Save to `/tmp/`.
3. Run the planner.
4. Suggest a SHORTER render-duration (one pass + half-second, not a polished loop).
5. Suggest `make render-demo` with `/tmp/` output.

**Draft config**:

```toml
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1

[[playlist.section]]
mode = "swap"
hold_time = 5.0
scroll_step_ms = 25

[[playlist.section.widget]]
type = "message"
text = "BORDER CHASE PREVIEW"
font = "5x8"
border = { style = "rainbow_chase", speed = 20 }
```

**Planner output**:
- `total_ms`: 5000 (static text + hold).
- `recommended_render_duration_s`: 6 (polished default).

**Dev-mode adjustment**:
- For a static `border` preview, ~3 seconds is enough to see two-three rainbow sweeps.
- Suggest `--duration 3` override.

**Color overlay**: no flags (text uses default white-ish — the engine renders it OK on black; this is a dev preview, not a customer-facing demo).

**Command for the user**:

```bash
make render-demo CONFIG=/tmp/border-chase-preview.toml OUT=/tmp/preview-border-chase-20.gif
# (Or with shorter duration:)
uv run python tools/render_demo/render.py /tmp/border-chase-preview.toml -o /tmp/preview-border-chase-20.gif --duration 3
```

**Skip**:
- No caption draft (dev mode).
- No commit suggestion (throwaway).
- No `# render-duration:` header in the TOML (dev mode treats render-duration as a CLI flag, not a file header).
````

- [ ] **Step 3: Commit**

```bash
mkdir -p .claude/skills/making-a-gif/examples
git add .claude/skills/making-a-gif/examples/
git commit -m "skill: making-a-gif examples (docs-mode + dev-mode walkthroughs)"
```

---

### Task 13: Tool README

**Files:**
- Create: `tools/gif_plan/README.md`

- [ ] **Step 1: Write the README**

Create `tools/gif_plan/README.md`:

````markdown
# gif-plan

Deterministic CLI that computes playtime + flags common timing bugs for led-ticker demo gifs. Sibling to `tools/render_demo/`.

## Usage

```bash
uv run python -m tools.gif_plan.plan <config.toml>
uv run python -m tools.gif_plan.plan <config.toml> --json
make plan-gif CONFIG=path/to.toml
```

## Output

**Human (default)**:
```
config: docs/site/demos-pinned/two_row-wrap.toml
playlist_total: 8000ms
recommended_render_duration: 9s
header `# render-duration:` found: 8s

section[0] mode=swap loop_count=1 → 8000ms
  widget[0] type=two_row visit=8000ms

flags:
  [ERROR] playlist :: mid_pass_cutoff
    render-duration: 8 cuts ~125ms of playlist content mid-pass.
    fix: Bump to 9 (matches the deterministic playlist total + 1s buffer).
```

**JSON (`--json`)**: same data, machine-parseable. Consumed by the `making-a-gif` skill.

## Exit codes

- `0` — clean.
- `1` — warnings only.
- `2` — errors (impossible math or mid-pass cutoff with header set).

## What it covers

Modes: `swap`.
Widgets: `message`, `countdown`, `two_row`, `image`, `still`, `gif`.

## What it does NOT cover (v1)

- `forever_scroll` / `infini_scroll` modes — timing is runtime-dependent.
- Data-fetch widgets (`weather`, `coinbase`, `mlb`, `rss_feed`, etherscan, `coingecko`) — visit time depends on fetched data.
- Bigsign pixel_mapper_config transformations — canvas-width math is approximate.

## Tests

```bash
PYTHONPATH=. uv run pytest tools/gif_plan/ -v
```

Includes:
- Per-formula unit tests (widgets + totals + flags).
- CLI integration tests.
- Dogfood against the 35 existing pinned demos with a ±20% drift tripwire.

## When NOT to invoke

If you need to render a gif, use `tools/render_demo/` directly (or `make render-demo`). This tool only plans; it doesn't render. The companion `.claude/skills/making-a-gif/` skill ties the two together.
````

- [ ] **Step 2: Commit**

```bash
git add tools/gif_plan/README.md
git commit -m "gif_plan: README (usage, schema, what's covered)"
```

---

### Task 14: End-to-end smoke test + open PR

**Files:** none (validation + git operations).

- [ ] **Step 1: Run full test suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -q`
Expected: all pass (1692+ existing + ~35 new gif_plan tests).

- [ ] **Step 2: Run lint**

Run: `make lint`
Expected: clean.

- [ ] **Step 3: Run the CLI against three real demos**

```bash
make plan-gif CONFIG=docs/site/demos-pinned/two_row-wrap.toml
make plan-gif CONFIG=docs/site/demos-pinned/gif-two_row-scroll_through.toml
make plan-gif CONFIG=docs/site/demos-pinned/image-static-logo.toml
```

For each: output should be human-readable, exit code 0 (or 1 if there's a real warning — investigate but not block).

- [ ] **Step 4: Push and open PR**

```bash
git push -u origin making-a-gif-skill
PATH=/Users/$(whoami)/.nvm/versions/node/v24.14.1/bin:$PATH gh pr create \
  --title "skill: making-a-gif (deterministic CLI + Claude judgment overlay)" \
  --body "$(cat <<'EOF'
## Summary

New project-local skill + companion CLI for planning led-ticker demo gifs.

- `tools/gif_plan/` — deterministic Python CLI. Computes per-widget visit time, section + playlist totals, recommended render-duration. Flags mid-pass cutoffs, out-of-band scroll_step_ms, zero-cycle widgets, pixel_mapper_config caveats.
- `.claude/skills/making-a-gif/` — Claude-facing skill that wraps the CLI, adds LED-panel color/contrast judgment, suggests captions for docs mode and `/tmp/` output paths for dev mode.

## Test plan

- [x] Per-formula unit tests for widgets, totals, flags.
- [x] CLI integration tests (JSON + exit codes).
- [x] Dogfood against 35 existing pinned demos — no false-positive mid_pass_cutoffs, recommended within ±20% of `# render-duration:` headers.
- [x] `make lint` clean.
- [x] CLI manually invoked against 3 representative demos.

Spec: `docs/superpowers/specs/2026-05-15-making-a-gif-skill-design.md`
Plan: `docs/superpowers/plans/2026-05-15-making-a-gif-skill.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 5: Return the PR URL**

---

## Self-review checklist

- [x] Every step has concrete code or commands (no "TBD"/"TODO").
- [x] Each task is independently committable.
- [x] Function names match between definition and use (`canvas_width_logical`, `estimate_content_width_logical`, `ticker_message_visit_ms`, `two_row_visit_ms`, `image_visit_ms`, `gif_visit_ms`, `section_total_ms`, `playlist_total_ms`, `recommended_render_duration_s`, `check_all`, `plan`).
- [x] Test expectations match the implementations.
- [x] Spec coverage: all sections of the spec map to a task.
- [x] No skipped requirements: math (Tasks 1-6), flags (Task 7), CLI (Task 8), skill files (Tasks 11-13), Makefile (Task 10), validation (Task 9), smoke + PR (Task 14).
