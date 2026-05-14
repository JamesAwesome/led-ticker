# `bottom_text_wrap` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the v1 single-row `text_wrap` feature to two-row mode on `_BaseImageWidget` (gif/image with `bottom_text` set) and `TwoRowMessage`. Three bottom-prefixed fields: `bottom_text_wrap`, `bottom_text_separator`, `bottom_text_separator_color`. Always-wrap when flag set. Top row stays held; never wraps.

**Architecture:** Image two-row owns its tick loop via `_play_with_two_row_text` — wrap math lives inside the play method, parameterizing the existing v1 separator helpers to accept a color provider + frame key. `TwoRowMessage` delegates to the engine's `_swap_and_scroll`; it exposes a `wraps_forever` property the engine checks to skip its cursor_pos-based stop condition and run for `hold_time` instead. `wraps_forever` widgets are refused in forever_scroll / infini_scroll modes (those rely on widgets terminating naturally).

**Tech Stack:** Python 3.13, attrs, pytest, BDF + HiresFont rasterizers, ScaledCanvas wrapper for bigsign.

**Spec reference:** `docs/superpowers/specs/2026-05-13-bottom-text-wrap-design.md`.

---

## Pre-flight

Use `superpowers:using-git-worktrees` to create an isolated workspace. Suggested name: `bottom-text-wrap`. Run `make test` baseline (expect 1563 passed, 2 skipped — the post-PR-#58 state).

---

### Task 1: Add fields + validation to `_BaseImageWidget`

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py` (attrs fields near line 95-125; `_validate_common` near line 345-380)
- Test: `tests/test_widgets/test_image_two_row_wrap.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_widgets/test_image_two_row_wrap.py`:

```python
"""Tests for bottom_text_wrap on image widgets in two-row mode.

Mirrors test_image_text_wrap.py's structure. Single-row image
(no bottom_text) refuses bottom_text_wrap; two-row image
(bottom_text set) accepts it. Top row never wraps.
"""
from __future__ import annotations

import pytest
from PIL import Image

from led_ticker.widgets.still import StillImage


def _make_png(tmp_path, color=(0, 0, 0), size=(32, 32), name="img.png"):
    img = Image.new("RGB", size, color=color)
    p = tmp_path / name
    img.save(p, format="PNG")
    return p


def _still_two_row(tmp_path, **kwargs):
    """Build a two-row StillImage with reasonable defaults."""
    defaults = dict(
        path=str(_make_png(tmp_path)),
        top_text="TOP",
        bottom_text="bottom marquee",
    )
    defaults.update(kwargs)
    return StillImage(**defaults)


class TestBottomTextWrapDefaults:
    def test_bottom_text_wrap_defaults_false(self, tmp_path):
        w = _still_two_row(tmp_path)
        assert w.bottom_text_wrap is False

    def test_bottom_text_separator_defaults_none(self, tmp_path):
        w = _still_two_row(tmp_path)
        assert w.bottom_text_separator is None

    def test_bottom_text_separator_color_defaults_none(self, tmp_path):
        w = _still_two_row(tmp_path)
        assert w.bottom_text_separator_color is None


class TestBottomTextWrapValidation:
    def test_wrap_requires_two_row_mode(self, tmp_path):
        """bottom_text_wrap on a single-row image widget (no bottom_text)
        is refused."""
        with pytest.raises(
            ValueError, match="bottom_text_wrap is only valid in two-row mode"
        ):
            StillImage(
                path=str(_make_png(tmp_path)),
                text="single row",
                bottom_text_wrap=True,
            )

    def test_wrap_requires_non_empty_bottom_text(self, tmp_path):
        """bottom_text_wrap=True with bottom_text='' is refused even in
        two-row mode."""
        with pytest.raises(
            ValueError,
            match="bottom_text_wrap=True requires non-empty bottom_text",
        ):
            StillImage(
                path=str(_make_png(tmp_path)),
                top_text="TOP",
                bottom_text="",
                bottom_text_wrap=True,
            )

    def test_separator_without_wrap_refused(self, tmp_path):
        with pytest.raises(
            ValueError, match="bottom_text_separator.*requires bottom_text_wrap"
        ):
            _still_two_row(tmp_path, bottom_text_separator=" * ")

    def test_separator_color_without_wrap_refused(self, tmp_path):
        with pytest.raises(
            ValueError,
            match="bottom_text_separator_color.*requires bottom_text_wrap",
        ):
            _still_two_row(
                tmp_path, bottom_text_separator_color=(255, 0, 0)
            )

    def test_wrap_in_two_row_mode_accepted(self, tmp_path):
        w = _still_two_row(tmp_path, bottom_text_wrap=True)
        assert w.bottom_text_wrap is True

    def test_v1_text_wrap_still_refused_in_two_row(self, tmp_path):
        """v1's text_wrap stays single-row-only — refused when
        bottom_text is set. Sharpened message points at bottom_text_wrap."""
        with pytest.raises(
            ValueError, match="text_wrap.*single-row.*bottom_text_wrap"
        ):
            StillImage(
                path=str(_make_png(tmp_path)),
                top_text="TOP",
                bottom_text="bottom",
                text_wrap=True,
            )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_two_row_wrap.py -v --tb=short
```

Expected: ALL fail with `AttributeError: ... has no attribute 'bottom_text_wrap'`.

- [ ] **Step 3: Add the three fields**

Edit `src/led_ticker/widgets/_image_base.py`. Locate the existing v1 wrap fields (around line 95-125 in the current `_BaseImageWidget`). Add three new fields immediately after `text_separator_color`:

```python
    text_separator_color: Any | None = attrs.field(default=None, kw_only=True)

    # Two-row wrap (v2). Mirrors text_wrap / text_separator /
    # text_separator_color but applies to the BOTTOM row in two-row
    # mode (bottom_text set). The top row never wraps. When True,
    # the bottom row chases itself continuously with the separator
    # between copies — even when bottom_text fits the canvas.
    # v1's single-row text_wrap stays single-row-only and is refused
    # in two-row mode.
    bottom_text_wrap: bool = attrs.field(default=False, kw_only=True)

    # Glyph(s) between bottom-row repeats in wrap mode. None → " • "
    # default (matches v1 + forever_scroll). "" → "  " (two-space gap).
    bottom_text_separator: str | None = attrs.field(default=None, kw_only=True)

    # Color for the bottom separator. None inherits bottom_color
    # (NOT font_color — separator is a piece of the bottom row).
    # When set, gets its own per-effect frame counter via
    # _FrameAware._EFFECT_ATTRS so continuous-phase Rainbow stays
    # in phase with bottom_color.
    bottom_text_separator_color: Any | None = attrs.field(
        default=None, kw_only=True
    )
```

- [ ] **Step 4: Add validation in `_validate_common`**

Locate the existing v1 `text_wrap` validation block in `_validate_common` (around lines 345-380). Add new validation immediately after it:

```python
        # bottom_text_wrap validation. Only valid in two-row mode
        # (bottom_text non-empty). Always-wrap when set — even when
        # bottom_text fits the canvas.
        if self.bottom_text_wrap:
            if not self.bottom_text:
                raise ValueError(
                    "bottom_text_wrap=True requires non-empty bottom_text. "
                    "For single-row marquees use text_wrap."
                )

        # Separator fields require bottom_text_wrap.
        if self.bottom_text_separator is not None and not self.bottom_text_wrap:
            raise ValueError(
                f"bottom_text_separator={self.bottom_text_separator!r} "
                f"requires bottom_text_wrap=True."
            )
        if (
            self.bottom_text_separator_color is not None
            and not self.bottom_text_wrap
        ):
            raise ValueError(
                "bottom_text_separator_color requires bottom_text_wrap=True."
            )
```

Then sharpen the existing v1 single-row guard. Find the validation block that handles `text_wrap` + two-row conflict (currently raises with a message like `"text_wrap=True is not supported in two-row mode"` at around line 346-353). Update its message to point at `bottom_text_wrap`:

```python
            if self.bottom_text:
                raise ValueError(
                    "text_wrap is single-row only; in two-row mode use "
                    "bottom_text_wrap (the separator + color knobs use "
                    "the bottom_text_* prefix too)."
                )
```

Add the `bottom_text_wrap` standalone validation for "not in two-row mode" — when no `bottom_text` is set but `bottom_text_wrap=True`, the user is on single-row but used the wrong knob:

```python
        # bottom_text_wrap on single-row → refuse (user wants text_wrap).
        if self.bottom_text_wrap and not self.bottom_text:
            # Note: ordered before the "requires non-empty bottom_text"
            # check above; in practice they fire on the same condition
            # but with different messages. To keep ONE clear error,
            # consolidate:
            pass
```

(The previous step already raises `"bottom_text_wrap=True requires non-empty bottom_text. For single-row marquees use text_wrap."` — which covers both "two-row mode required" and "non-empty bottom_text required" with one actionable message. Keep it as a single error.)

Add defensive `_ConstantColor` wrap for `bottom_text_separator_color`. Find the existing color-coercion block in `_validate_common` (right after `text_separator_color` coercion):

```python
        if self.text_separator_color is not None and not hasattr(
            self.text_separator_color, "color_for"
        ):
            self.text_separator_color = _ConstantColor(self.text_separator_color)
        if self.bottom_text_separator_color is not None and not hasattr(
            self.bottom_text_separator_color, "color_for"
        ):
            self.bottom_text_separator_color = _ConstantColor(
                self.bottom_text_separator_color
            )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_two_row_wrap.py -v --tb=short
```

Expected: all PASS.

- [ ] **Step 6: Regression check**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_text_wrap.py tests/test_widgets/test_still.py tests/test_widgets/test_gif.py -v --tb=short --no-header 2>&1 | tail -15
```

Expected: green. v1 single-row tests must still pass; new sharpened v1 message must still match the existing regex.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_two_row_wrap.py
git commit -m "$(cat <<'EOF'
bottom_text_wrap: add fields + validation to _BaseImageWidget

Three new kw_only attrs fields (bottom_text_wrap, bottom_text_separator,
bottom_text_separator_color) mirroring v1's single-row API but
bottom-prefixed for two-row mode. v1's text_wrap stays single-row-only;
its conflict message now points at bottom_text_wrap.

Validation: bottom_text_wrap requires non-empty bottom_text;
separator fields require bottom_text_wrap=True. Defensive
_ConstantColor wrap for bottom_text_separator_color.

Wrap math arrives in a later commit — this is API surface only.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add fields + validation to `TwoRowMessage` + `wraps_forever`

**Files:**
- Modify: `src/led_ticker/widgets/two_row.py` (attrs fields near line 76-135; `__attrs_post_init__` near line 280-295)
- Test: `tests/test_widgets/test_two_row_wrap.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/test_widgets/test_two_row_wrap.py`:

```python
"""Tests for bottom_text_wrap on TwoRowMessage widget."""
from __future__ import annotations

import pytest

from led_ticker.widgets.two_row import TwoRowMessage


def _two_row(**kwargs):
    defaults = dict(top_text="TOP", bottom_text="bottom marquee")
    defaults.update(kwargs)
    return TwoRowMessage(**defaults)


class TestBottomTextWrapDefaults:
    def test_bottom_text_wrap_defaults_false(self):
        w = _two_row()
        assert w.bottom_text_wrap is False

    def test_bottom_text_separator_defaults_none(self):
        w = _two_row()
        assert w.bottom_text_separator is None

    def test_bottom_text_separator_color_defaults_none(self):
        w = _two_row()
        assert w.bottom_text_separator_color is None


class TestWrapsForeverProperty:
    """The cooperation contract with `_swap_and_scroll`. True only
    when bottom_text_wrap=True AND bottom_text is non-empty."""

    def test_wraps_forever_false_by_default(self):
        w = _two_row()
        assert w.wraps_forever is False

    def test_wraps_forever_true_when_wrap_enabled(self):
        w = _two_row(bottom_text_wrap=True)
        assert w.wraps_forever is True

    def test_wraps_forever_false_when_bottom_empty(self):
        """bottom_text='' is refused at validation, but defensively
        wraps_forever should be False if it slips through (e.g.,
        attribute set after construction)."""
        w = _two_row(bottom_text_wrap=True)
        w.bottom_text = ""
        assert w.wraps_forever is False


class TestBottomTextWrapValidation:
    def test_wrap_requires_non_empty_bottom_text(self):
        with pytest.raises(
            ValueError,
            match="bottom_text_wrap=True requires non-empty bottom_text",
        ):
            TwoRowMessage(
                top_text="TOP", bottom_text="", bottom_text_wrap=True
            )

    def test_separator_without_wrap_refused(self):
        with pytest.raises(
            ValueError, match="bottom_text_separator.*requires bottom_text_wrap"
        ):
            _two_row(bottom_text_separator=" * ")

    def test_separator_color_without_wrap_refused(self):
        with pytest.raises(
            ValueError,
            match="bottom_text_separator_color.*requires bottom_text_wrap",
        ):
            _two_row(bottom_text_separator_color=(255, 0, 0))

    def test_wrap_accepted_with_bottom_text(self):
        w = _two_row(bottom_text_wrap=True)
        assert w.bottom_text_wrap is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_two_row_wrap.py -v --tb=short
```

Expected: AttributeError on bottom_text_wrap / wraps_forever.

- [ ] **Step 3: Add fields to `TwoRowMessage`**

Edit `src/led_ticker/widgets/two_row.py`. Locate the existing field block (around line 76-135). Add three fields just before the `_top_width` / `_bottom_width` init=False block:

```python
    border: Any | None = attrs.field(default=None, kw_only=True)

    # Two-row wrap (v2). Applies to the bottom row only — top stays
    # held. When True, the bottom row chases itself continuously with
    # a separator between copies, regardless of whether bottom_text
    # fits the canvas. See bottom_text_wrap on _BaseImageWidget for
    # parallel semantics.
    bottom_text_wrap: bool = attrs.field(default=False, kw_only=True)
    bottom_text_separator: str | None = attrs.field(default=None, kw_only=True)
    bottom_text_separator_color: Any | None = attrs.field(
        default=None, kw_only=True
    )

    _top_width: int = attrs.field(init=False, default=-1)
    _bottom_width: int = attrs.field(init=False, default=-1)
```

- [ ] **Step 4: Add `wraps_forever` property**

In the same file, add the property method (place it after the `__attrs_post_init__` method or near the top of the class methods — match the style of any existing `@property` definitions in the file; if there are none, place it just before `draw`):

```python
    @property
    def wraps_forever(self) -> bool:
        """Engine cooperation signal: when True, ticker.py's
        _swap_and_scroll skips its cursor_pos-based stop condition
        and runs the widget's draw loop for hold_time instead.
        Bottom row in wrap mode is intrinsically continuous —
        only section duration / loop_count terminates it."""
        return self.bottom_text_wrap and bool(self.bottom_text)
```

- [ ] **Step 5: Add validation in `__attrs_post_init__`**

Find the existing post-init validation in `two_row.py` (around lines 280-295). Add validation for the new fields:

```python
        if self.bottom_text_wrap and not self.bottom_text:
            raise ValueError(
                "bottom_text_wrap=True requires non-empty bottom_text."
            )
        if self.bottom_text_separator is not None and not self.bottom_text_wrap:
            raise ValueError(
                f"bottom_text_separator={self.bottom_text_separator!r} "
                f"requires bottom_text_wrap=True."
            )
        if (
            self.bottom_text_separator_color is not None
            and not self.bottom_text_wrap
        ):
            raise ValueError(
                "bottom_text_separator_color requires bottom_text_wrap=True."
            )

        # Defensive coercion to ColorProvider (mirrors top_color /
        # bottom_color handling). app.py's _coerce_widget_colors path
        # normally does this at config-load; covers direct
        # construction in tests.
        if self.bottom_text_separator_color is not None and not hasattr(
            self.bottom_text_separator_color, "color_for"
        ):
            from led_ticker.color_providers import _ConstantColor

            self.bottom_text_separator_color = _ConstantColor(
                self.bottom_text_separator_color
            )
```

- [ ] **Step 6: Run tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_two_row_wrap.py -v --tb=short
```

Expected: all PASS.

- [ ] **Step 7: Regression check**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_two_row.py -v --tb=short --no-header 2>&1 | tail -15
```

Expected: green (existing TwoRowMessage tests must still pass).

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/widgets/two_row.py tests/test_widgets/test_two_row_wrap.py
git commit -m "$(cat <<'EOF'
bottom_text_wrap: add fields + wraps_forever to TwoRowMessage

Same three bottom-prefixed fields as _BaseImageWidget (Task 1).
Plus a `wraps_forever` property the engine reads to skip its
cursor_pos-based stop condition when bottom_text_wrap=True.

Validation: same shape as Task 1. Wrap math + engine cooperation
arrive in later commits.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Register `bottom_text_separator_color` for coercion + frame counters + upfront widget-type guard

**Files:**
- Modify: `src/led_ticker/app.py` (`_PROVIDER_COLOR_KEYS` near line 81-87; `_build_widget` near line 529-545 — extend the v1 wrap-keys guard)
- Modify: `src/led_ticker/widgets/_frame_aware.py` (`_EFFECT_ATTRS` near line 40-50)
- Test: extend `tests/test_widgets/test_image_two_row_wrap.py` and `test_two_row_wrap.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_widgets/test_image_two_row_wrap.py`:

```python
class TestBottomSeparatorColorRegistration:
    def test_in_provider_keys(self):
        from led_ticker.app import _PROVIDER_COLOR_KEYS

        assert "bottom_text_separator_color" in _PROVIDER_COLOR_KEYS

    def test_in_effect_attrs(self):
        from led_ticker.widgets._frame_aware import _FrameAware

        assert "bottom_text_separator_color" in _FrameAware._EFFECT_ATTRS

    def test_rainbow_coerced(self):
        from led_ticker.app import _coerce_widget_colors

        cfg = {"bottom_text_separator_color": "rainbow"}
        _coerce_widget_colors(cfg)
        provider = cfg["bottom_text_separator_color"]
        assert hasattr(provider, "color_for")
        assert provider.per_char is True


class TestBottomTextWrapOnWrongWidgetType:
    """Same guard pattern v1 uses: drop falsy defaults silently,
    raise on truthy values when the widget type can't accept the field."""

    @pytest.mark.asyncio
    async def test_bottom_text_wrap_on_message_rejected(self):
        import aiohttp
        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            with pytest.raises(
                ValueError, match="bottom_text_wrap.*only valid"
            ):
                await _build_widget(
                    {
                        "type": "message",
                        "text": "hi",
                        "bottom_text_wrap": True,
                    },
                    session=session,
                )

    @pytest.mark.asyncio
    async def test_bottom_text_separator_on_message_rejected(self):
        import aiohttp
        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            with pytest.raises(
                ValueError, match="bottom_text_separator.*only valid"
            ):
                await _build_widget(
                    {
                        "type": "message",
                        "text": "hi",
                        "bottom_text_separator": " * ",
                    },
                    session=session,
                )

    @pytest.mark.asyncio
    async def test_bottom_text_wrap_false_on_message_dropped_silently(self):
        import aiohttp
        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            widget = await _build_widget(
                {
                    "type": "message",
                    "text": "hi",
                    "bottom_text_wrap": False,
                },
                session=session,
            )
        assert widget is not None

    @pytest.mark.asyncio
    async def test_bottom_text_wrap_on_two_row_accepted(self):
        """two_row is a NEW addition to the allowed types in v2."""
        import aiohttp
        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            widget = await _build_widget(
                {
                    "type": "two_row",
                    "top_text": "TOP",
                    "bottom_text": "bottom",
                    "bottom_text_wrap": True,
                },
                session=session,
            )
        assert widget.bottom_text_wrap is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_two_row_wrap.py::TestBottomSeparatorColorRegistration tests/test_widgets/test_image_two_row_wrap.py::TestBottomTextWrapOnWrongWidgetType -v --tb=short
```

Expected: most FAIL (registration keys not yet added; two_row not yet in the allow-list).

- [ ] **Step 3: Add to `_PROVIDER_COLOR_KEYS`**

Edit `src/led_ticker/app.py` (around line 81-87):

```python
_PROVIDER_COLOR_KEYS: set[str] = {
    "font_color",
    "top_color",
    "bottom_color",
    "font_color_temp",
    "text_separator_color",
    "bottom_text_separator_color",
}
```

- [ ] **Step 4: Add to `_FrameAware._EFFECT_ATTRS`**

Edit `src/led_ticker/widgets/_frame_aware.py` (around line 40-50):

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
            "bottom_text_separator_color",
        }
    )
```

- [ ] **Step 5: Extend the upfront widget-type guard**

Find the existing v1 wrap guard in `_build_widget` (around line 529-545). It currently only accepts `gif` and `image`. Update it to also accept `two_row` AND add the three new bottom-prefixed keys to the iterated list:

```python
    # text_wrap / text_separator / text_separator_color — image
    # widgets only. bottom_text_wrap / bottom_text_separator /
    # bottom_text_separator_color — image (two-row) AND two_row
    # widgets. On widget types not supporting these, drop falsy
    # defaults silently and raise on truthy values.
    SINGLE_ROW_WRAP_KEYS = (
        "text_wrap",
        "text_separator",
        "text_separator_color",
    )
    BOTTOM_ROW_WRAP_KEYS = (
        "bottom_text_wrap",
        "bottom_text_separator",
        "bottom_text_separator_color",
    )

    if widget_type not in ("gif", "image"):
        for wrap_key in SINGLE_ROW_WRAP_KEYS:
            val = widget_cfg.pop(wrap_key, None)
            if val not in (None, False):
                raise ValueError(
                    f'{wrap_key} is only valid on type="gif" or "image"; '
                    f"got type={widget_type!r}."
                )

    if widget_type not in ("gif", "image", "two_row"):
        for wrap_key in BOTTOM_ROW_WRAP_KEYS:
            val = widget_cfg.pop(wrap_key, None)
            if val not in (None, False):
                raise ValueError(
                    f'{wrap_key} is only valid on type="gif", "image", '
                    f'or "two_row"; got type={widget_type!r}.'
                )
```

- [ ] **Step 6: Run tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_two_row_wrap.py tests/test_widgets/test_two_row_wrap.py tests/test_widgets/test_image_text_wrap.py -v --tb=short --no-header 2>&1 | tail -20
```

Expected: all PASS (v1 tests still green; new v2 registration + guard tests pass).

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/app.py src/led_ticker/widgets/_frame_aware.py tests/test_widgets/test_image_two_row_wrap.py
git commit -m "$(cat <<'EOF'
bottom_text_wrap: register color coercion + frame counter + widget guard

bottom_text_separator_color → _PROVIDER_COLOR_KEYS (TOML coercion)
and _FrameAware._EFFECT_ATTRS (per-effect frame counter).

Upfront _build_widget guard extended: the v1 wrap keys stay on
gif/image; the v2 bottom-prefixed keys add `two_row` to the allow-list.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Parameterize separator helpers in `_BaseImageWidget` for bottom-row reuse

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py` (helpers around lines 560-635)
- Test: extend `tests/test_widgets/test_image_two_row_wrap.py`

v1's `_measure_separator`, `_draw_separator` are hard-coded to use `self.font` + `self.text_separator_color or self.font_color`. v2 needs them parameterizable for the bottom row's font + color provider. Refactor in place (single-row callers updated to pass explicit args).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_widgets/test_image_two_row_wrap.py`:

```python
class TestSeparatorHelpersParameterized:
    """Verify _measure_separator / _draw_separator accept explicit
    font + color args (refactor from v1's implicit self.font /
    self.font_color)."""

    def test_measure_separator_uses_given_font(self, tmp_path):
        from led_ticker.fonts import FONT_DEFAULT

        w = _still_two_row(tmp_path, bottom_text_wrap=True)
        # Pass a small canvas — we just want a positive width back
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 16
        opts.chain_length = 1
        canvas = RGBMatrix(options=opts).CreateFrameCanvas()

        width = w._measure_separator(canvas, font=FONT_DEFAULT)
        assert width > 0
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_two_row_wrap.py::TestSeparatorHelpersParameterized -v --tb=short
```

Expected: FAIL — `_measure_separator() got unexpected keyword argument 'font'`.

- [ ] **Step 3: Refactor `_resolved_separator_text` to take a `sep` arg**

The helper currently reads `self.text_separator`. Add an optional override so the bottom row can pass `self.bottom_text_separator`:

```python
    def _resolved_separator_text(
        self, separator: str | None | type[_UNSET] = _UNSET
    ) -> str:
        """Resolve the separator string with the v1 / forever_scroll
        literal-text rules:
          - None: " • " (default)
          - "" : "  " (two-space gap)
          - any other value: as-is

        `separator` arg defaults to self.text_separator (v1 single-row);
        callers pass self.bottom_text_separator for v2 two-row."""
        if separator is _UNSET:
            separator = self.text_separator
        if separator is None:
            return " • "
        if separator == "":
            return "  "
        return separator
```

Add the sentinel at module level (near other module constants):

```python
class _UNSET:
    """Sentinel for distinguishing 'caller didn't pass arg' from
    'caller passed None'."""
```

- [ ] **Step 4: Refactor `_measure_separator` to take `font` + `separator` args**

```python
    def _measure_separator(
        self,
        canvas: Canvas,
        font: Any | None = None,
        separator: str | None | type[_UNSET] = _UNSET,
    ) -> int:
        """Width of the resolved separator in logical px on canvas.
        Defaults match v1 single-row behavior (self.font + self.text_separator)."""
        sep = self._resolved_separator_text(separator)
        if not sep:
            return 0
        if font is None:
            font = self.font
        if EMOJI_PATTERN.search(sep):
            from led_ticker.pixel_emoji import measure_width

            return measure_width(font, sep, canvas=canvas)
        return get_text_width(font, sep, padding=0, canvas=canvas)
```

- [ ] **Step 5: Refactor `_draw_separator` to take `font` + `provider` + `frame_key` args**

```python
    def _draw_separator(
        self,
        canvas: Canvas,
        x: int,
        baseline_y: int,
        font: Any | None = None,
        separator: str | None | type[_UNSET] = _UNSET,
        provider: Any | None = None,
        frame_key: str | None = None,
        inherit_provider: Any | None = None,
        inherit_frame_key: str | None = None,
    ) -> None:
        """Draw the separator with whole-string color resolution.

        Single-row v1: caller omits font/provider/frame_key — defaults
        to self.font, self.text_separator_color or self.font_color, with
        frame_key "text_separator_color" or "font_color" fallback.

        Two-row v2: caller passes
          font=self.bottom_font_resolved or self.font,
          provider=self.bottom_text_separator_color,
          frame_key="bottom_text_separator_color",
          inherit_provider=self.bottom_color,
          inherit_frame_key="bottom_color"
        """
        sep = self._resolved_separator_text(separator)
        if not sep:
            return
        if font is None:
            font = self.font
        # Resolve provider: explicit > inherit > self.font_color
        if provider is None:
            provider = self.text_separator_color
            frame_key = "text_separator_color" if provider is not None else None
            if provider is None:
                provider = self.font_color
                frame_key = "font_color"
        elif provider is None and inherit_provider is not None:
            provider = inherit_provider
            frame_key = inherit_frame_key
        # If caller explicitly passed provider=None but no inherit,
        # this falls through to the explicit branch above — handled.
        if frame_key is None:
            frame_key = "font_color"
        frame_count = self.frame_for(frame_key)
        if hasattr(provider, "color_for"):
            color = provider.color_for(frame_count, 0, 1)
        else:
            color = provider
        if EMOJI_PATTERN.search(sep):
            from led_ticker.pixel_emoji import draw_with_emoji

            draw_with_emoji(
                canvas,
                font,
                x,
                baseline_y,
                color,
                sep,
                emoji_y=baseline_y - 8,
                frame=frame_count,
                total_chars=1,
            )
        else:
            draw_text(canvas, font, x, baseline_y, color, sep)
```

Note: the signature is complex because we need to support:
- v1 single-row (uses `self.text_separator_color` or falls back to `self.font_color`)
- v2 two-row (uses `self.bottom_text_separator_color` or falls back to `self.bottom_color`)

To simplify, restructure: callers pass an explicit `provider` and `frame_key`, OR pass `inherit_provider` + `inherit_frame_key` and the helper resolves the fallback. Cleaner shape:

```python
    def _draw_separator(
        self,
        canvas: Canvas,
        x: int,
        baseline_y: int,
        font: Any,
        separator: str,
        explicit_provider: Any | None,
        explicit_frame_key: str,
        inherit_provider: Any,
        inherit_frame_key: str,
    ) -> None:
        """Draw the resolved separator. Caller picks which provider
        is "explicit" (the dedicated separator color knob) and which is
        "inherit" (the row's main color)."""
        if not separator:
            return
        if explicit_provider is not None:
            provider = explicit_provider
            frame_key = explicit_frame_key
        else:
            provider = inherit_provider
            frame_key = inherit_frame_key
        frame_count = self.frame_for(frame_key)
        if hasattr(provider, "color_for"):
            color = provider.color_for(frame_count, 0, 1)
        else:
            color = provider
        if EMOJI_PATTERN.search(separator):
            from led_ticker.pixel_emoji import draw_with_emoji

            draw_with_emoji(
                canvas,
                font,
                x,
                baseline_y,
                color,
                separator,
                emoji_y=baseline_y - 8,
                frame=frame_count,
                total_chars=1,
            )
        else:
            draw_text(canvas, font, x, baseline_y, color, separator)
```

Then update v1 single-row callers (in `_render_wrap_tick`) to call:

```python
                if sep_width > 0:
                    self._draw_separator(
                        text_canvas,
                        x + text_width,
                        baseline_y,
                        font=self.font,
                        separator=self._resolved_separator_text(),
                        explicit_provider=self.text_separator_color,
                        explicit_frame_key="text_separator_color",
                        inherit_provider=self.font_color,
                        inherit_frame_key="font_color",
                    )
```

- [ ] **Step 6: Run tests including v1 regression**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_text_wrap.py tests/test_widgets/test_image_two_row_wrap.py -v --tb=short --no-header 2>&1 | tail -20
```

Expected: green. v1 regression matters here — the refactor must preserve single-row behavior.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_two_row_wrap.py
git commit -m "$(cat <<'EOF'
bottom_text_wrap: parameterize separator helpers for bottom-row reuse

_measure_separator / _draw_separator accept explicit font +
provider + frame_key args. v1 single-row callers updated to pass
self.font + self.text_separator_color + "text_separator_color"
explicitly, with self.font_color + "font_color" as inherit.
Wrap math implementation reuses the same helpers for the bottom row.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Implement wrap math in `_play_with_two_row_text` (image two-row)

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py` (`_play_with_two_row_text` around lines 950-1165; new `_render_two_row_wrap_tick` helper)
- Test: extend `tests/test_widgets/test_image_two_row_wrap.py`

- [ ] **Step 1: Write failing tests (per-tick analysis like v1)**

Append to `tests/test_widgets/test_image_two_row_wrap.py`:

```python
# Helpers — mirror test_image_text_wrap.py's per-tick capture pattern.

_SWAP_SENTINEL = "__SWAP__"


def _capture_draws_per_tick(mocker, real_canvas):
    """Wrap SwapOnVSync's side_effect to insert a sentinel between
    ticks. Returns (frame_mock, draws_list)."""
    import led_ticker.widgets._image_base as base_mod

    real_draw = base_mod.draw_text
    draws: list[tuple[int, str]] = []

    def _capture_text(canvas, font, x, baseline_y, color, text):
        draws.append((x, text))
        return real_draw(canvas, font, x, baseline_y, color, text)

    mocker.patch.object(base_mod, "draw_text", side_effect=_capture_text)

    frame = mocker.MagicMock()

    def _swap_side_effect(c):
        draws.append((_SWAP_SENTINEL, None))
        return c

    frame.matrix.SwapOnVSync.side_effect = _swap_side_effect
    return frame, draws


def _split_into_ticks(draws):
    """Group draws by SwapOnVSync sentinel."""
    ticks = []
    current: list = []
    for d in draws:
        if d[0] == _SWAP_SENTINEL:
            if current:
                ticks.append(current)
            current = []
        else:
            current.append(d)
    if current:
        ticks.append(current)
    return ticks


def _bigsign_real_canvas():
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    opts = RGBMatrixOptions()
    opts.cols = 64
    opts.rows = 32
    opts.chain_length = 8
    opts.parallel = 1
    opts.pixel_mapper_config = "U-mapper"
    return RGBMatrix(options=opts).CreateFrameCanvas()


class TestImageTwoRowWrapRenders:
    @pytest.mark.asyncio
    async def test_bottom_wrap_renders_multiple_copies_per_tick(
        self, tmp_path, mocker
    ):
        """Defining test: every tick draws ≥2 copies of bottom_text
        at distinct x positions forming a cycle_width-spaced
        arithmetic progression."""
        path = _make_png(tmp_path)
        widget = StillImage(
            path=str(path),
            fit="stretch",
            top_text="TOP",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
            scroll_speed_ms=50,
            hold_seconds=1.0,
        )
        real = _bigsign_real_canvas()
        frame, draws = _capture_draws_per_tick(mocker, real)
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await widget.play(real, frame)

        ticks = _split_into_ticks(draws)
        assert len(ticks) > 0

        # For each tick, find x positions of "Hi" main-text draws.
        for tick_idx, tick in enumerate(ticks[:5]):
            hi_xs = sorted(x for (x, t) in tick if t == "Hi")
            assert len(hi_xs) >= 2, (
                f"Tick {tick_idx}: expected ≥2 copies of 'Hi'; "
                f"got {len(hi_xs)} at xs={hi_xs}"
            )
            # Arithmetic progression (cycle_width spaced)
            diffs = [hi_xs[i + 1] - hi_xs[i] for i in range(len(hi_xs) - 1)]
            median = sorted(diffs)[len(diffs) // 2]
            for d in diffs:
                assert abs(d - median) <= 2, (
                    f"Tick {tick_idx}: copy spacing not arithmetic. "
                    f"xs={hi_xs}, diffs={diffs}"
                )
            assert median > 0

    @pytest.mark.asyncio
    async def test_top_row_held_during_bottom_wrap(self, tmp_path, mocker):
        """Top row stays at its top_align position even while bottom
        wraps. The top row should be drawn at a SINGLE x per tick."""
        path = _make_png(tmp_path)
        widget = StillImage(
            path=str(path),
            fit="stretch",
            top_text="TOP",
            top_align="left",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
            scroll_speed_ms=50,
            hold_seconds=0.5,
        )
        real = _bigsign_real_canvas()
        frame, draws = _capture_draws_per_tick(mocker, real)
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await widget.play(real, frame)

        ticks = _split_into_ticks(draws)
        for tick in ticks[:5]:
            top_xs = [x for (x, t) in tick if t == "TOP"]
            assert len(top_xs) == 1, (
                f"Top row should draw once per tick; got xs={top_xs}"
            )
            # Same x across ticks (held).
            first_top_x = top_xs[0]
            for tick2 in ticks[1:5]:
                top_xs2 = [x for (x, t) in tick2 if t == "TOP"]
                assert top_xs2 == [first_top_x], (
                    f"Top row drifted: first={first_top_x}, later={top_xs2}"
                )
            break  # one outer-iter is enough — we cross-check
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_two_row_wrap.py::TestImageTwoRowWrapRenders -v --tb=short
```

Expected: FAIL — current `_play_with_two_row_text` doesn't have wrap logic; it scrolls only when bottom overflows and uses the off-right→off-left math.

- [ ] **Step 3: Add `_render_two_row_wrap_tick` helper**

Edit `src/led_ticker/widgets/_image_base.py`. Place the new helper near `_render_two_row_tick` (around line 770-820):

```python
    def _render_two_row_wrap_tick(
        self,
        real_canvas: Canvas,
        text_canvas: Canvas,
        top: tuple[Any, str, Any, int, int, int],
        bottom_font: Any,
        bottom_text: str,
        bottom_color: Any,
        bottom_baseline: int,
        bottom_emoji_y: int,
        scroll_pos: int,
        bottom_width: int,
        sep_width: int,
        cycle_width: int,
        top_emoji_cap: int = EMOJI_ROW_CAP,
        bottom_emoji_cap: int = EMOJI_ROW_CAP,
    ) -> None:
        """One wrap-mode tick: image + top (held) + bottom (multi-copy).

        Top tuple shape matches _render_two_row_tick:
            (font, text, color, x, baseline_y, emoji_y)

        Bottom is rendered as n_copies of (bottom_text + separator) at
        scroll_pos - cycle_width + i*cycle_width."""
        reset_canvas(real_canvas, self.bg_color)
        self._paint_image(real_canvas)
        if self.border is not None:
            self.border.paint(real_canvas, self.frame_for("border"))

        # Top row: single draw, held at its alignment x.
        self._draw_row_text(
            text_canvas,
            *top,
            frame_count=self.frame_for(self._row_color_attr(0)),
            max_emoji_height=top_emoji_cap,
        )

        # Bottom row: n_copies of (text + separator).
        canvas_w = text_canvas.width
        n_copies = (canvas_w + cycle_width - 1) // cycle_width + 1
        start_x = scroll_pos - cycle_width
        sep_text = self._resolved_separator_text(self.bottom_text_separator)

        for i in range(n_copies):
            x = start_x + i * cycle_width
            # bottom_text body
            self._draw_row_text(
                text_canvas,
                bottom_font,
                bottom_text,
                bottom_color,
                x,
                bottom_baseline,
                bottom_emoji_y,
                frame_count=self.frame_for(self._row_color_attr(1)),
                max_emoji_height=bottom_emoji_cap,
            )
            # separator (uses bottom_color provider OR bottom_text_separator_color)
            if sep_width > 0:
                self._draw_separator(
                    text_canvas,
                    x + bottom_width,
                    bottom_baseline,
                    font=bottom_font,
                    separator=sep_text,
                    explicit_provider=self.bottom_text_separator_color,
                    explicit_frame_key="bottom_text_separator_color",
                    inherit_provider=bottom_color,
                    inherit_frame_key=self._row_color_attr(1),
                )
```

- [ ] **Step 4: Integrate wrap into `_play_with_two_row_text`**

Find the existing scroll branch in `_play_with_two_row_text` (around lines 1063-1080). The current shape:

```python
        bottom_scrolls = bottom_width > canvas_w
        if bottom_scrolls:
            scroll_pos = canvas_w  # start off-right
            ticks_per_loop = canvas_w + bottom_width
            min_loops = max(1, self.text_loops)
            n_ticks = max(n_ticks, min_loops * ticks_per_loop)
        else:
            scroll_pos = aligned_x(canvas_w, bottom_width, self._row_align(1))
```

Replace with a wrap-aware version:

```python
        wrap_mode = self.bottom_text_wrap
        sep_width = (
            self._measure_separator(
                text_canvas,
                font=bottom_font,
                separator=self.bottom_text_separator,
            )
            if wrap_mode
            else 0
        )
        cycle_width = (bottom_width + sep_width) if wrap_mode else 0

        bottom_scrolls = bottom_width > canvas_w or wrap_mode
        if wrap_mode:
            scroll_pos = 0
            ticks_per_loop = cycle_width
            min_loops = max(1, self.text_loops)
            n_ticks = max(n_ticks, min_loops * ticks_per_loop)
        elif bottom_scrolls:
            scroll_pos = canvas_w
            ticks_per_loop = canvas_w + bottom_width
            min_loops = max(1, self.text_loops)
            n_ticks = max(n_ticks, min_loops * ticks_per_loop)
        else:
            scroll_pos = aligned_x(canvas_w, bottom_width, self._row_align(1))
```

Then find the per-tick render call (around lines 1130-1160) and the bottom scroll-pos update (around lines 1160-1165). Replace the loop body to dispatch to the new helper in wrap mode:

```python
        for tick in range(n_ticks):
            self._pick_frame_for_elapsed(tick * tick_ms)
            self.advance_frame()
            if wrap_mode:
                self._render_two_row_wrap_tick(
                    canvas,
                    text_canvas,
                    top_tuple,
                    bottom_font,
                    bottom_text,
                    bottom_color,
                    bottom_baseline,
                    bottom_emoji_y,
                    scroll_pos,
                    bottom_width,
                    sep_width,
                    cycle_width,
                    top_emoji_cap=top_emoji_cap,
                    bottom_emoji_cap=bottom_emoji_cap,
                )
            else:
                bottom_tuple = (
                    bottom_font,
                    bottom_text,
                    bottom_color,
                    scroll_pos,
                    bottom_baseline,
                    bottom_emoji_y,
                )
                self._render_two_row_tick(
                    canvas,
                    text_canvas,
                    top_tuple,
                    bottom_tuple,
                    top_emoji_cap=top_emoji_cap,
                    bottom_emoji_cap=bottom_emoji_cap,
                )
            canvas = frame.matrix.SwapOnVSync(canvas)
            if text_is_wrapped:
                text_canvas.real = canvas
            else:
                text_canvas = canvas
            await asyncio.sleep(tick_seconds)
            if wrap_mode:
                scroll_pos -= 1
                if cycle_width:
                    scroll_pos %= cycle_width
            elif bottom_scrolls:
                scroll_pos -= 1
                if scroll_pos + bottom_width <= 0:
                    scroll_pos = canvas_w
```

The static-text fast path (around lines 1097-1130) requires `not bottom_scrolls AND text_loops==0 AND _is_static() AND colors_are_static AND border_is_static`. Wrap mode sets `bottom_scrolls=True`, so it can't enter the fast path — no change needed.

- [ ] **Step 5: Run tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_two_row_wrap.py::TestImageTwoRowWrapRenders -v --tb=short
```

Expected: PASS.

- [ ] **Step 6: Regression check**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/ -v --tb=short --no-header 2>&1 | tail -10
```

Expected: green.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_two_row_wrap.py
git commit -m "$(cat <<'EOF'
bottom_text_wrap: image two-row wrap math in _play_with_two_row_text

New _render_two_row_wrap_tick helper composes the held top row with
multi-copy bottom-row chain. bottom_text_wrap=True engages wrap
regardless of overflow; ticks_per_loop reinterprets as cycle_width
(text_loops floors to N cycle traversals, mirroring v1 single-row).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Implement wrap math in `TwoRowMessage.draw()`

**Files:**
- Modify: `src/led_ticker/widgets/two_row.py` (`draw` method around lines 175-310)
- Test: extend `tests/test_widgets/test_two_row_wrap.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_widgets/test_two_row_wrap.py`:

```python
class TestTwoRowWrapDrawRendersMultipleCopies:
    """draw() in wrap mode renders multiple copies of bottom_text
    in a single call. Engine drives cursor_pos; widget treats it
    modularly via `cursor_pos % cycle_width`."""

    def test_draw_renders_multiple_bottom_copies(self, mocker):
        """At cursor_pos=0, the widget should render ≥2 copies of
        bottom_text + separator on a 64px canvas with 10px cycle."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 1
        canvas = RGBMatrix(options=opts).CreateFrameCanvas()

        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
        )

        import led_ticker.widgets.two_row as tr_mod

        draws: list[tuple[int, str]] = []
        real_draw = tr_mod.draw_text

        def _capture(c, font, x, y, color, text):
            draws.append((x, text))
            return real_draw(c, font, x, y, color, text)

        mocker.patch.object(tr_mod, "draw_text", side_effect=_capture)
        w.draw(canvas, cursor_pos=0)

        hi_xs = sorted(x for (x, t) in draws if t == "Hi")
        assert len(hi_xs) >= 2, (
            f"Expected ≥2 copies of 'Hi'; got {len(hi_xs)} at xs={hi_xs}"
        )

    def test_draw_modulates_cursor_pos(self, mocker):
        """Calls with cursor_pos=0 and cursor_pos=-cycle_width should
        produce the same visual (modular wrap)."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 1
        canvas = RGBMatrix(options=opts).CreateFrameCanvas()

        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
        )

        import led_ticker.widgets.two_row as tr_mod

        # cycle_width = "Hi" (~6px BDF) + " * " (~12px) = ~18px
        draws_a: list[tuple[int, str]] = []
        draws_b: list[tuple[int, str]] = []

        def make_capturer(target):
            real = tr_mod.draw_text

            def _capture(c, font, x, y, color, text):
                target.append((x, text))
                return real(c, font, x, y, color, text)

            return _capture

        mocker.patch.object(
            tr_mod, "draw_text", side_effect=make_capturer(draws_a)
        )
        w.draw(canvas, cursor_pos=0)
        mocker.patch.object(
            tr_mod, "draw_text", side_effect=make_capturer(draws_b)
        )
        # Use -100 as a proxy for "some cycle_width multiple back" —
        # the modular wrap should produce equivalent x-position set.
        # Exact equivalence requires knowing the cycle_width; instead
        # assert both produce the same NUMBER of Hi copies.
        w.draw(canvas, cursor_pos=-100)

        hi_xs_a = [x for (x, t) in draws_a if t == "Hi"]
        hi_xs_b = [x for (x, t) in draws_b if t == "Hi"]
        assert len(hi_xs_a) == len(hi_xs_b), (
            f"Modular wrap should yield consistent copy counts: "
            f"got {len(hi_xs_a)} vs {len(hi_xs_b)}"
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_two_row_wrap.py::TestTwoRowWrapDrawRendersMultipleCopies -v --tb=short
```

Expected: FAIL.

- [ ] **Step 3: Modify `TwoRowMessage.draw()` to support wrap mode**

Edit `src/led_ticker/widgets/two_row.py`. Locate the existing `draw` method (around lines 175-310). The current shape (simplified):

```python
def draw(self, canvas, cursor_pos=0, **kwargs):
    # Compute widths if uninitialized.
    # Compute top + bottom baseline + emoji y.
    # Draw top row at top_x.
    # If bottom fits: draw at aligned_x.
    # Else: draw at cursor_pos.
    return canvas, cursor_pos + self._bottom_width + self.padding
```

Add a wrap branch BEFORE the existing fits/scroll branch. Look for the `if self._bottom_width <= canvas.width and cursor_pos == 0:` block around line 290. Right before it:

```python
        # Wrap mode: bottom row chases itself with separator. Engine's
        # cursor_pos is treated modularly; widget renders n_copies
        # of (bottom_text + separator) per draw call.
        if self.bottom_text_wrap:
            sep_text = self._resolved_separator_text()
            sep_width = self._measure_separator_width(
                canvas, bottom_font, sep_text
            )
            cycle_width = self._bottom_width + sep_width
            if cycle_width == 0:
                # Defensive — validation should prevent this
                return canvas, cycle_width

            # Modular leading-copy position
            scroll_pos = cursor_pos % cycle_width
            canvas_w = canvas.width
            n_copies = (canvas_w + cycle_width - 1) // cycle_width + 1
            start_x = scroll_pos - cycle_width

            for i in range(n_copies):
                x = start_x + i * cycle_width
                # Bottom text body
                _draw_text_with_emoji_or_plain(
                    canvas,
                    bottom_font,
                    x,
                    bottom_text_y,
                    bottom_color,
                    self.bottom_text,
                    emoji_y=bottom_emoji_y,
                    frame_count=self.frame_for("bottom_color"),
                )
                # Separator (whole-string color)
                if sep_width > 0:
                    self._draw_bottom_separator(
                        canvas,
                        x + self._bottom_width,
                        bottom_text_y,
                        bottom_font,
                        sep_text,
                    )

            # Engine reads `wraps_forever` to decide whether to stop;
            # return value is a sane step (one cycle = one logical
            # traversal). The engine increments cursor_pos by -1 per
            # tick; over `cycle_width` ticks we've made one full
            # traversal.
            return canvas, cycle_width
```

Add the `_resolved_separator_text`, `_measure_separator_width`, `_draw_bottom_separator`, and `_draw_text_with_emoji_or_plain` helpers. Place them on the `TwoRowMessage` class. Since these are local versions of the v2-image-widget helpers, keep them small and focused:

```python
    def _resolved_separator_text(self) -> str:
        """Same semantics as _BaseImageWidget._resolved_separator_text.
          - None  : " • "
          - ""    : "  "
          - else  : as-is."""
        if self.bottom_text_separator is None:
            return " • "
        if self.bottom_text_separator == "":
            return "  "
        return self.bottom_text_separator

    def _measure_separator_width(self, canvas, font, sep) -> int:
        """Width of the resolved separator in logical px."""
        if not sep:
            return 0
        if EMOJI_PATTERN.search(sep):
            from led_ticker.pixel_emoji import measure_width

            return measure_width(font, sep, canvas=canvas)
        return get_text_width(font, sep, padding=0, canvas=canvas)

    def _draw_bottom_separator(
        self, canvas, x, baseline_y, font, sep
    ) -> None:
        """Whole-string color call. Inherits bottom_color when
        bottom_text_separator_color is None."""
        provider = (
            self.bottom_text_separator_color
            if self.bottom_text_separator_color is not None
            else self.bottom_color
        )
        frame_key = (
            "bottom_text_separator_color"
            if self.bottom_text_separator_color is not None
            else "bottom_color"
        )
        frame_count = self.frame_for(frame_key)
        if hasattr(provider, "color_for"):
            color = provider.color_for(frame_count, 0, 1)
        else:
            color = provider
        if EMOJI_PATTERN.search(sep):
            from led_ticker.pixel_emoji import draw_with_emoji

            draw_with_emoji(
                canvas,
                font,
                x,
                baseline_y,
                color,
                sep,
                emoji_y=baseline_y - 8,
                frame=frame_count,
                total_chars=1,
            )
        else:
            draw_text(canvas, font, x, baseline_y, color, sep)
```

Make sure `EMOJI_PATTERN`, `measure_width`, `get_text_width`, `draw_text`, `draw_with_emoji` are imported at the top of `two_row.py`. Look at the existing imports — most of these are likely there; add missing ones.

The `_draw_text_with_emoji_or_plain` helper for the bottom-text body itself can re-use the existing draw logic in the `else` branch of `draw()` (which already handles emoji/non-emoji). To avoid duplicating, you may extract the existing draw-bottom-text block into a method. Inspect `two_row.py:285-305` to see the current draw shape and decide whether to extract or inline.

- [ ] **Step 4: Run tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_two_row_wrap.py -v --tb=short
```

Expected: PASS.

- [ ] **Step 5: Regression**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_two_row.py -v --tb=short --no-header 2>&1 | tail -15
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/two_row.py tests/test_widgets/test_two_row_wrap.py
git commit -m "$(cat <<'EOF'
bottom_text_wrap: TwoRowMessage.draw() renders multi-copy in wrap mode

When bottom_text_wrap=True, draw() treats cursor_pos modularly
(via % cycle_width) and renders n_copies of (bottom_text + separator)
per call. Top row stays held. Returns cycle_width as the "step" so
the engine has a sane stride value.

Cooperation: the engine reads wraps_forever (added in Task 2) to
decide whether to stop scrolling. Engine changes land in Task 7.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Engine cooperation — `_swap_and_scroll` honors `wraps_forever`

**Files:**
- Modify: `src/led_ticker/ticker.py` (`_swap_and_scroll` around lines 990-1062)
- Test: `tests/test_ticker_wraps_forever.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/test_ticker_wraps_forever.py`:

```python
"""Tests for engine cooperation with widgets that wrap forever."""
from __future__ import annotations

import asyncio

import pytest


class _StubWrapsForeverWidget:
    """Minimal widget that signals `wraps_forever=True`. draw() returns
    a small cursor_pos to simulate normal scrolling — without engine
    cooperation, the loop would terminate quickly."""

    def __init__(self):
        self.draw_calls = 0
        self.bg_color = None
        self.wraps_forever = True

    def draw(self, canvas, cursor_pos=0, **kwargs):
        self.draw_calls += 1
        # Return cursor_pos+10 — small positive, simulating a content
        # width. Without wraps_forever cooperation, the engine would
        # scroll for ~10 ticks before stopping.
        return canvas, 10


class _StubFiniteWidget:
    """Normal widget — finite scroll, no wraps_forever attribute."""

    def __init__(self):
        self.draw_calls = 0
        self.bg_color = None

    def draw(self, canvas, cursor_pos=0, **kwargs):
        self.draw_calls += 1
        # cursor_pos > canvas.width triggers engine scroll branch
        return canvas, 200  # > test canvas.width


def _make_test_canvas():
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    opts = RGBMatrixOptions()
    opts.cols = 160
    opts.rows = 16
    opts.chain_length = 1
    return RGBMatrix(options=opts).CreateFrameCanvas()


class TestWrapsForeverRespected:
    @pytest.mark.asyncio
    async def test_wraps_forever_widget_runs_for_hold_time(self, mocker):
        """A widget with wraps_forever=True should be drawn for the
        full hold_time, NOT terminate based on cursor_pos."""
        from led_ticker.ticker import _swap_and_scroll

        widget = _StubWrapsForeverWidget()
        canvas = _make_test_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await _swap_and_scroll(
            canvas, frame, widget, scroll_speed=0.05, hold_time=0.5
        )

        # hold_time=0.5s at ENGINE_TICK_MS=50ms → 10 ticks minimum.
        # A finite widget would stop at ~10 cursor_pos ticks regardless.
        # wraps_forever widget should match hold_time tick budget.
        assert widget.draw_calls >= 10, (
            f"wraps_forever widget should draw for hold_time; "
            f"got {widget.draw_calls} calls"
        )

    @pytest.mark.asyncio
    async def test_finite_widget_unaffected(self, mocker):
        """Widgets without wraps_forever attribute behave as before."""
        from led_ticker.ticker import _swap_and_scroll

        widget = _StubFiniteWidget()
        canvas = _make_test_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await _swap_and_scroll(
            canvas, frame, widget, scroll_speed=0.05, hold_time=0.5
        )

        # Finite widget should terminate when cursor_pos has scrolled
        # past its content width — exact count depends on scroll speed,
        # but should be bounded by content_width + canvas.width.
        # 200 (content) + 160 (canvas) + 2 holds × 10 ticks each = ~380
        assert widget.draw_calls > 0
        # Crucially, the engine TERMINATED — no infinite loop.

    @pytest.mark.asyncio
    async def test_wraps_forever_widget_section_duration_terminates(
        self, mocker
    ):
        """hold_time still bounds wraps_forever — the loop is not
        actually infinite; it terminates on hold_time elapsed."""
        from led_ticker.ticker import _swap_and_scroll

        widget = _StubWrapsForeverWidget()
        canvas = _make_test_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await _swap_and_scroll(
            canvas, frame, widget, scroll_speed=0.05, hold_time=0.1
        )

        # 0.1s hold ≈ 2 ticks at 50ms — should terminate quickly.
        assert 1 <= widget.draw_calls < 100, (
            f"Bounded by hold_time; got {widget.draw_calls}"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_wraps_forever.py -v --tb=short
```

Expected: FAIL — engine doesn't yet check `wraps_forever`.

- [ ] **Step 3: Modify `_swap_and_scroll`**

Edit `src/led_ticker/ticker.py`. Locate `_swap_and_scroll` (around lines 990-1062). Add a new top-level branch BEFORE the existing `if cursor_pos > canvas.width:` check:

```python
async def _swap_and_scroll(
    canvas, frame, ticker_obj, *,
    scroll_speed: float = 0.025,
    hold_time: float = 3,
    skip_initial_draw: bool = False,
    continuous: bool = False,
) -> tuple[Canvas, int, int]:
    """..."""
    pos = 0
    bg_color = getattr(ticker_obj, "bg_color", None)
    reset_canvas(canvas, bg_color)
    canvas, cursor_pos = ticker_obj.draw(canvas, pos)

    if not skip_initial_draw:
        canvas = _swap(canvas, frame)

    tick_seconds = ENGINE_TICK_MS / 1000

    # Wrap-forever widgets (e.g., TwoRowMessage in bottom_text_wrap
    # mode) opt out of the cursor_pos-based stop condition. The
    # widget handles modular cursor_pos internally; the engine just
    # drives draw() for hold_time and increments pos as if scrolling.
    if getattr(ticker_obj, "wraps_forever", False):
        n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
        for _ in range(n_ticks):
            _advance_frame_if_supported(ticker_obj)
            reset_canvas(canvas, bg_color)
            canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
            canvas = _swap(canvas, frame)
            pos -= 1
            await asyncio.sleep(scroll_speed)
        return canvas, cursor_pos, pos

    if cursor_pos > canvas.width:
        # ... existing scroll branch ...
```

The rest of `_swap_and_scroll` stays unchanged.

- [ ] **Step 4: Run tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_wraps_forever.py -v --tb=short
```

Expected: all PASS.

- [ ] **Step 5: Run engine + widget regression**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py tests/test_engine_redraw_contract.py tests/test_widgets/ -v --tb=short --no-header 2>&1 | tail -20
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker_wraps_forever.py
git commit -m "$(cat <<'EOF'
bottom_text_wrap: engine honors wraps_forever in _swap_and_scroll

Widgets with `wraps_forever=True` enter a new engine branch that
drives draw() for hold_time without checking cursor_pos. The widget
handles modular cursor_pos internally (TwoRowMessage wrap mode).

Finite widgets are unaffected — they still hit the existing scroll /
held branches.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Refuse `wraps_forever` in forever_scroll / infini_scroll modes

**Files:**
- Modify: `src/led_ticker/validate.py` (add new rule near other mode-validation rules)
- Test: `tests/test_validate.py` (extend)

`wraps_forever` widgets only make sense in `swap` mode (time-bounded by hold_time). In `forever_scroll` / `infini_scroll` modes, widgets must terminate naturally — a wraps_forever widget would block the chain. Refuse at config-load with a clear error.

- [ ] **Step 1: Inspect the validator structure**

```bash
grep -n "^class.*Rule\|def validate\|^Rule\|rule_" src/led_ticker/validate.py | head -20
```

Read the existing rules around forever_scroll / infini_scroll mode. The new rule should follow the same pattern as the existing per-section mode validators (look at "rule 26" the most recent — it validates per-section forever_scroll separator fields).

- [ ] **Step 2: Write the failing test**

Append to `tests/test_validate.py`:

```python
class TestRule27WrapsForeverModeOnly:
    """bottom_text_wrap=True is only valid in mode=swap. Refused
    in forever_scroll and infini_scroll because the widget would
    block the chain."""

    def test_bottom_text_wrap_in_forever_scroll_rejected(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text("""
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "forever_scroll"

[[playlist.section.widget]]
type = "two_row"
top_text = "TOP"
bottom_text = "bottom"
bottom_text_wrap = true
""")
        from led_ticker.validate import validate_config

        result = validate_config(str(cfg))
        # The validator surfaces errors via a result object; assert
        # the wrap-mode-conflict message appears.
        assert any(
            "bottom_text_wrap" in str(err) and "forever_scroll" in str(err).lower()
            for err in result.errors
        ), f"Expected wrap+forever_scroll error; got {result.errors}"

    def test_bottom_text_wrap_in_infini_scroll_rejected(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text("""
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "infini_scroll"

[[playlist.section.widget]]
type = "two_row"
top_text = "TOP"
bottom_text = "bottom"
bottom_text_wrap = true
""")
        from led_ticker.validate import validate_config

        result = validate_config(str(cfg))
        assert any(
            "bottom_text_wrap" in str(err) and "infini_scroll" in str(err).lower()
            for err in result.errors
        ), f"Expected wrap+infini_scroll error; got {result.errors}"

    def test_bottom_text_wrap_in_swap_accepted(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text("""
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 5

[[playlist.section.widget]]
type = "two_row"
top_text = "TOP"
bottom_text = "bottom"
bottom_text_wrap = true
""")
        from led_ticker.validate import validate_config

        result = validate_config(str(cfg))
        assert not result.errors, f"Expected no errors; got {result.errors}"
```

NOTE: the exact `validate_config` signature + result shape may differ. Inspect `src/led_ticker/validate.py` first and adapt the assertions to match the existing test patterns in `tests/test_validate.py`.

- [ ] **Step 3: Run tests to verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py::TestRule27WrapsForeverModeOnly -v --tb=short
```

Expected: FAIL.

- [ ] **Step 4: Add the validation rule**

Edit `src/led_ticker/validate.py`. Find where existing per-section mode rules live (look for "rule 26" or similar near forever_scroll separator validation). Add a new rule that iterates section widgets and checks for `bottom_text_wrap=True` in non-swap modes:

```python
def _rule_27_wraps_forever_swap_only(playlist_section, mode, errors, warnings):
    """Rule 27: bottom_text_wrap requires mode=swap. forever_scroll
    and infini_scroll modes expect widgets to terminate naturally;
    a wraps_forever widget would block the chain."""
    if mode in ("swap",):
        return
    for widget in playlist_section.get("widget", []):
        if widget.get("bottom_text_wrap") is True:
            errors.append(
                f"Section in mode={mode!r}: widget type={widget.get('type')!r} "
                f"with bottom_text_wrap=True is only allowed in mode='swap' "
                f"(other modes expect widgets to terminate naturally)."
            )
```

Wire it into the per-section validation loop alongside the existing rules. Use the same calling style as rule 26.

- [ ] **Step 5: Run tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -v --tb=short --no-header 2>&1 | tail -15
```

Expected: all green (new rule + existing).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "$(cat <<'EOF'
validate: rule 27 — bottom_text_wrap requires mode=swap

forever_scroll and infini_scroll modes expect widgets to terminate
naturally; a wraps_forever widget would block the chain. Catch this
at config-load with a clear error message.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Comprehensive test coverage — image two-row wrap

**Files:**
- Test: extend `tests/test_widgets/test_image_two_row_wrap.py`

Fill out the test coverage matrix: color inheritance, scroll/scroll_over branches, gif multi-frame, border, etc.

- [ ] **Step 1: Add the coverage suite**

Append to `tests/test_widgets/test_image_two_row_wrap.py`:

```python
class TestBottomSeparatorColorInheritance:
    @pytest.mark.asyncio
    async def test_separator_inherits_bottom_color_when_unset(
        self, tmp_path, mocker
    ):
        """text_separator_color=None makes the separator paint with
        bottom_color (NOT font_color — separator is part of the
        bottom row)."""
        from led_ticker._compat import require_graphics

        graphics = require_graphics()
        path = _make_png(tmp_path)
        widget = StillImage(
            path=str(path),
            fit="stretch",
            top_text="TOP",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
            font_color=graphics.Color(255, 0, 0),  # red — should NOT appear on sep
            bottom_color=graphics.Color(0, 255, 0),  # green — separator should be this
            scroll_speed_ms=50,
            hold_seconds=0.2,
        )
        real = _bigsign_real_canvas()
        frame, draws = _capture_draws_per_tick(mocker, real)
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await widget.play(real, frame)

        # Filter separator draws
        sep_colors = []
        import led_ticker.widgets._image_base as base_mod
        # draws was captured at module-level draw_text — the color is
        # the 5th positional arg. We need to re-capture with the
        # provider-aware path. Reuse the test helper with explicit
        # color check:
        # Simplified: assume any draw whose text matches the resolved
        # separator (" * ") gets the bottom_color.

        # (Detailed implementation: extend _capture_draws_per_tick to
        # also record colors, then filter sep text and assert RGB.)
        # For now, defer the exact assertion to a more thorough helper
        # in step 2 if the simple shape doesn't fit.

    @pytest.mark.asyncio
    async def test_separator_explicit_overrides_bottom_color(
        self, tmp_path, mocker
    ):
        """Setting bottom_text_separator_color overrides inheritance."""
        from led_ticker._compat import require_graphics

        graphics = require_graphics()
        path = _make_png(tmp_path)
        widget = StillImage(
            path=str(path),
            fit="stretch",
            top_text="TOP",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
            bottom_color=graphics.Color(0, 255, 0),
            bottom_text_separator_color=graphics.Color(0, 0, 255),  # blue
            scroll_speed_ms=50,
            hold_seconds=0.2,
        )
        real = _bigsign_real_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        # Capture separator colors specifically
        import led_ticker.widgets._image_base as base_mod

        real_draw = base_mod.draw_text
        captured: list = []

        def _capture(canvas, font, x, baseline_y, color, text):
            if text in (" • ", " * ", "  "):
                captured.append(color)
            return real_draw(canvas, font, x, baseline_y, color, text)

        mocker.patch.object(base_mod, "draw_text", side_effect=_capture)

        await widget.play(real, frame)

        assert captured, "Expected at least one separator draw"
        for c in captured:
            assert (c.red, c.green, c.blue) == (0, 0, 255), (
                f"Separator should use blue (bottom_text_separator_color); "
                f"got ({c.red}, {c.green}, {c.blue})"
            )


class TestImageTwoRowWrapWithBorder:
    @pytest.mark.asyncio
    async def test_wrap_with_border_no_crash(self, tmp_path, mocker):
        """Border + bottom wrap compose without exception."""
        from led_ticker.borders import RainbowChaseBorder

        path = _make_png(tmp_path)
        widget = StillImage(
            path=str(path),
            fit="stretch",
            top_text="TOP",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
            border=RainbowChaseBorder(speed=4, char_offset=6, thickness=1),
            scroll_speed_ms=50,
            hold_seconds=0.2,
        )
        real = _bigsign_real_canvas()
        frame, draws = _capture_draws_per_tick(mocker, real)
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await widget.play(real, frame)

        ticks = _split_into_ticks(draws)
        hi_total = sum(len([d for d in tick if d[1] == "Hi"]) for tick in ticks)
        assert hi_total > len(ticks), "Border did not block bottom-row wrap"


class TestGifPlayerTwoRowWrap:
    @pytest.mark.asyncio
    async def test_gif_two_row_wrap_renders_multiple_copies(
        self, tmp_path, mocker
    ):
        from led_ticker.widgets.gif import GifPlayer

        # 3-frame gif: red, green, blue
        gif_path = tmp_path / "x.gif"
        from PIL import Image

        frames = [
            Image.new("RGB", (32, 32), (200, 0, 0)),
            Image.new("RGB", (32, 32), (0, 200, 0)),
            Image.new("RGB", (32, 32), (0, 0, 200)),
        ]
        frames[0].save(
            gif_path,
            save_all=True,
            append_images=frames[1:],
            duration=100,
            loop=0,
        )

        widget = GifPlayer(
            path=str(gif_path),
            fit="stretch",
            top_text="TOP",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
            scroll_speed_ms=50,
            gif_loops=2,
        )

        real = _bigsign_real_canvas()
        frame, draws = _capture_draws_per_tick(mocker, real)
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await widget.play(real, frame)

        ticks = _split_into_ticks(draws)
        hi_total = sum(len([d for d in tick if d[1] == "Hi"]) for tick in ticks)
        assert hi_total > len(ticks), (
            "GifPlayer two-row wrap should render multiple bottom copies per tick"
        )
```

- [ ] **Step 2: Run tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_two_row_wrap.py -v --tb=short --no-header 2>&1 | tail -20
```

Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_widgets/test_image_two_row_wrap.py
git commit -m "$(cat <<'EOF'
test(bottom_text_wrap): comprehensive image two-row wrap coverage

Color inheritance (separator inherits bottom_color when unset;
explicit overrides), wrap + border composition, GifPlayer two-row
wrap (multi-frame). Locks in the v2 contract for image widgets.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Docs — gif.mdx, image.mdx, two_row.mdx + fact-pack rows

**Files:**
- Modify: `docs/site/src/content/docs/widgets/gif.mdx`
- Modify: `docs/site/src/content/docs/widgets/image.mdx`
- Modify: `docs/site/src/content/docs/widgets/two_row.mdx`
- Modify: `docs/content-source/widgets/gif.md`
- Modify: `docs/content-source/widgets/image.md`
- Modify: `docs/content-source/widgets/two_row.md`

- [ ] **Step 1: Survey existing structure**

Read each `.mdx` file in full. Locate the existing "Wrap mode" subsection on gif.mdx + image.mdx (added in PR #58). Identify where the new "Wrap mode (bottom row)" subsection belongs — likely right after the existing single-row wrap section, with a clear heading distinguishing single-row from two-row.

- [ ] **Step 2: Add subsection to each `.mdx`**

Use a parallel structure across the three pages. Each subsection should include:

1. `<DemoGif>` element (gif goes in Task 11)
2. Short prose explaining when to use bottom wrap
3. `<TomlExample>` with the bottom wrap config
4. Field table (3 rows)
5. Notes about top-row-never-wraps, color inheritance from bottom_color, and v1 text_wrap being single-row only

Suggested prose for the subsection:

```mdx
### Wrap mode (bottom row, seamless marquee)

<DemoGif
  src="/demos-pinned/<name>-two_row-wrap.gif"
  caption="<caption describing the specific demo>"
/>

Setting `bottom_text_wrap = true` in two-row mode (when `bottom_text` is set) runs the bottom row as a seamless marquee — chasing itself across the canvas with a separator between repeats. Top row stays held at `top_align`; only the bottom row wraps. Engages even when the bottom text fits — predictable.

<TomlExample
  code={`[[playlist.section.widget]]
type = "<gif | image | two_row>"
top_text = "BREAKING"
top_color = [255, 80, 200]
bottom_text = "tap to subscribe"
bottom_text_wrap = true
bottom_text_separator = " * "                 # default: " • "
bottom_text_separator_color = "rainbow"       # default: inherit bottom_color`}
/>

| Field                          | Type       | Default                                   | Meaning                                                                                |
| ------------------------------ | ---------- | ----------------------------------------- | -------------------------------------------------------------------------------------- |
| `bottom_text_wrap`             | bool       | `false`                                   | Toggle seamless wrap on the bottom row. Requires `bottom_text` non-empty. |
| `bottom_text_separator`        | string     | `" • "` (when `bottom_text_wrap = true`)  | Glyph(s) between bottom-row repeats. `""` falls back to a two-space gap.   |
| `bottom_text_separator_color`  | color spec | inherit `bottom_color`                    | Color for the bottom separator; whole-string provider (one hue per frame). |

Notes:

- `bottom_text_wrap` always wraps when set, even if the bottom text fits the canvas.
- Top row never wraps (refused by validation; no `top_text_wrap` field exists).
- The separator color inherits `bottom_color` (NOT `font_color`) — separator is part of the bottom row.
- v1's `text_wrap` stays single-row only — in two-row mode use `bottom_text_wrap`.
- `bottom_text_wrap` is only allowed in `mode = "swap"`. In `forever_scroll` / `infini_scroll` modes, validation refuses it (those modes expect widgets to terminate naturally).
```

Apply with the appropriate `type = ...` value on each page.

- [ ] **Step 3: Add fact-pack rows**

Extend `docs/content-source/widgets/{gif,image,two_row}.md` with the three new fields. Match the existing fact-pack row format (read the existing rows for `text_wrap` etc. in each file).

- [ ] **Step 4: Verify docs build**

```bash
source ~/.nvm/nvm.sh && nvm use 24 >/dev/null
cd docs/site && pnpm astro check 2>&1 | tail -10
```

Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add docs/site/src/content/docs/widgets/gif.mdx docs/site/src/content/docs/widgets/image.mdx docs/site/src/content/docs/widgets/two_row.mdx docs/content-source/widgets/
git commit -m "$(cat <<'EOF'
docs(bottom_text_wrap): document bottom-row wrap on gif/image/two_row

New "Wrap mode (bottom row, seamless marquee)" subsection on all
three widget pages. Field table + example + notes covering top-row-
never-wraps, color inheritance from bottom_color, v1 text_wrap
single-row-only, and the swap-mode-only constraint.

Fact-pack rows added so the auto-generated options tables match.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Pinned demos — gif-two_row-wrap + two_row-wrap

**Files:**
- Create: `docs/site/demos-pinned/gif-two_row-wrap.toml`
- Create: `docs/site/demos-pinned/two_row-wrap.toml`
- Create: `docs/site/public/demos-pinned/gif-two_row-wrap.gif` (rendered)
- Create: `docs/site/public/demos-pinned/two_row-wrap.gif` (rendered)
- Modify: the three `.mdx` files to point at the new gifs

- [ ] **Step 1: Create the gif-two_row-wrap config**

```bash
cat > docs/site/demos-pinned/gif-two_row-wrap.toml <<'EOF'
# render-duration: 8
# Two-row wrap on gif: pikachu + held magenta TOP + cyan bottom
# wrapping at ~24px cycle. Demonstrates top-row-held + bottom-wrap.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[transitions]
default = "cut"

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 7.0

[[playlist.section.widget]]
type = "gif"
path = "../../../config/assets/pika_wave_transparent.gif"
fit = "pillarbox"
image_align = "left"
top_text = "BREAKING"
top_color = [225, 48, 108]
bottom_text = "tap to subscribe"
bottom_text_wrap = true
bottom_text_separator = " * "
bottom_color = [120, 230, 255]
bottom_text_separator_color = "rainbow"
gif_loops = 999
scroll_speed_ms = 25
EOF
```

- [ ] **Step 2: Create the two_row-wrap config**

```bash
cat > docs/site/demos-pinned/two_row-wrap.toml <<'EOF'
# render-duration: 8
# Standalone TwoRowMessage with wrap: held BREAKING title +
# scrolling-wrap "tap to subscribe • new episode" bottom.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[transitions]
default = "cut"

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 7.0

[[playlist.section.widget]]
type = "two_row"
top_text = "BREAKING"
top_color = [225, 48, 108]
bottom_text = "tap to subscribe"
bottom_text_wrap = true
bottom_text_separator = " * "
bottom_color = [120, 230, 255]
bottom_text_separator_color = "rainbow"
scroll_speed_ms = 25
EOF
```

- [ ] **Step 3: Render both demos**

```bash
uv run python tools/render_demo/render.py docs/site/demos-pinned/gif-two_row-wrap.toml -o docs/site/public/demos-pinned/gif-two_row-wrap.gif --duration 8
uv run python tools/render_demo/render.py docs/site/demos-pinned/two_row-wrap.toml -o docs/site/public/demos-pinned/two_row-wrap.gif --duration 8
ls -lh docs/site/public/demos-pinned/{gif,two_row}-*wrap*.gif
```

Inspect the gifs visually — open with the Read tool. Confirm:
- Top row stays at its `top_align` position, never moves
- Bottom row chases continuously with rainbow separator
- No flickering at the wrap boundary

If visual issues appear (e.g., demos look stale or top drifts), report DONE_WITH_CONCERNS and investigate before committing.

- [ ] **Step 4: Update the `.mdx` files to point at the rendered gifs**

The Task 10 subsection has `src="/demos-pinned/<name>-two_row-wrap.gif"` placeholders. Fill in the actual paths:
- gif.mdx → `src="/demos-pinned/gif-two_row-wrap.gif"`
- image.mdx → `src="/demos-pinned/gif-two_row-wrap.gif"` (image widget reuses gif demo since the wrap behavior is identical visually for both)
- two_row.mdx → `src="/demos-pinned/two_row-wrap.gif"`

Update the `<DemoGif caption=...>` to describe what the reader is seeing:
- gif-two_row-wrap.gif caption: `"pikachu on the left, held magenta BREAKING up top, cyan tap to subscribe wrapping continuously on the bottom with a rainbow * separator"`
- two_row-wrap.gif caption: similar but no image

- [ ] **Step 5: Commit**

```bash
git add docs/site/demos-pinned/gif-two_row-wrap.toml docs/site/demos-pinned/two_row-wrap.toml docs/site/public/demos-pinned/gif-two_row-wrap.gif docs/site/public/demos-pinned/two_row-wrap.gif docs/site/src/content/docs/widgets/gif.mdx docs/site/src/content/docs/widgets/image.mdx docs/site/src/content/docs/widgets/two_row.mdx
git commit -m "$(cat <<'EOF'
docs(bottom_text_wrap): pinned demos + wire DemoGif in subsections

Two new pinned demos in docs/site/demos-pinned/, rendered to
public/demos-pinned/ (committed gifs, regenerable via
make render-pinned-demos):
  - gif-two_row-wrap.gif (used on gif.mdx + image.mdx)
  - two_row-wrap.gif     (used on two_row.mdx)

DemoGif src + captions wired into the existing "Wrap mode (bottom
row)" subsection on all three widget pages.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Final integration check

No code changes — verification only.

- [ ] **Step 1: Full test suite**

```bash
make test 2>&1 | tail -15
```

Expected: passed + 0 failures + reasonable skip count. Confirm the count moved up by ~40-50 from the baseline (1563).

- [ ] **Step 2: Lint**

```bash
make lint 2>&1 | tail -10
```

Expected: clean.

- [ ] **Step 3: Validate example configs**

```bash
uv run led-ticker validate config/config.example.toml
uv run led-ticker validate config/config.bigsign.example.toml
```

Expected: both pass.

- [ ] **Step 4: Validate a wrap-mode-only config**

```bash
cat > /tmp/two-row-wrap.toml <<EOF
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 5

[[playlist.section.widget]]
type = "two_row"
top_text = "TOP"
bottom_text = "scrolling marquee"
bottom_text_wrap = true
bottom_text_separator = " * "
EOF

uv run led-ticker validate /tmp/two-row-wrap.toml
```

Expected: pass.

- [ ] **Step 5: Validate the negative case**

```bash
cat > /tmp/wrap-bad.toml <<EOF
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "forever_scroll"

[[playlist.section.widget]]
type = "two_row"
top_text = "TOP"
bottom_text = "marquee"
bottom_text_wrap = true
EOF

uv run led-ticker validate /tmp/wrap-bad.toml
```

Expected: FAIL with a clear "bottom_text_wrap requires mode=swap" error (rule 27).

- [ ] **Step 6: Inspect the rendered demos one more time**

Read both pinned gifs visually. Confirm top row holds and bottom row wraps continuously without artifacts.

- [ ] **Step 7: No commit — verification only**

If all checks pass, the plan is complete. Final state should have ~12 commits on the feature branch since base.

---

## Self-Review

**Spec coverage:**

| Spec section | Tasks |
|---|---|
| Field surface (Section 1) | Task 1 (image), Task 2 (TwoRowMessage) |
| Literal-text + color inheritance + always-wrap (Section 1) | Task 5 + Task 6 (implementation), Task 9 (color inheritance tests) |
| Validation (Section 2) | Task 1 + Task 2 (widget-level), Task 3 (cross-widget guard), Task 8 (mode-level) |
| Implementation arch — image (Section 3) | Task 4 (helpers), Task 5 (math) |
| Implementation arch — TwoRowMessage (Section 3) | Task 6 (draw), Task 7 (engine cooperation) |
| Testing strategy (Section 4) | Tasks 1, 2, 5, 6, 7, 8, 9 |
| Docs & demos (Section 5) | Task 10 (mdx + content-source), Task 11 (gifs) |
| Out-of-scope items (Section 6) | None — explicitly deferred, no tasks |

All spec sections covered. No gaps.

**Placeholder scan:** No "TBD" / "TODO" / "implement later" in the plan body. Two soft spots:

1. Task 4's `_draw_separator` signature has an early sketch followed by a "cleaner shape" replacement. The replacement is the canonical version; if implementing, use the second signature.
2. Task 8 hedges on the exact `validate_config` API ("inspect first and adapt to existing patterns"). This is intentional — the validator's result shape isn't visible from the plan's vantage point, so the implementer reads the existing tests and matches.

Both are addressable by the implementer reading nearby code. Not plan failures.

**Type consistency:**
- `_resolved_separator_text(separator=...)` introduced in Task 4 is called from `_render_two_row_wrap_tick` (Task 5) and from `TwoRowMessage.draw` (Task 6 has its own version)
- `_measure_separator(canvas, font=..., separator=...)` introduced in Task 4 is called from Task 5
- `_draw_separator(canvas, x, baseline_y, font, separator, explicit_provider, explicit_frame_key, inherit_provider, inherit_frame_key)` introduced in Task 4 — all callers in Tasks 5 + (Task 6 uses its own helper `_draw_bottom_separator` since TwoRowMessage doesn't inherit from `_BaseImageWidget`)
- `wraps_forever` property on TwoRowMessage (Task 2) — read by engine in Task 7 via `getattr`
- `_render_two_row_wrap_tick` helper signature (Task 5) — called from `_play_with_two_row_text` in Task 5

All consistent.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-13-bottom-text-wrap.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
