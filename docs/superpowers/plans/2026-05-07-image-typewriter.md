# Image Typewriter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `animation = "typewriter"` to single-row image widgets (`gif`, `image`). Per-effect counters from PR #12 enable clean composition with `font_color = "rainbow"` and `border = "rainbow"`.

**Architecture:** One field on `_BaseImageWidget` (inherited by both `GifPlayer` and `StillImage`). Three validation rules in `_validate_common`. New `_visible_text` helper + optional `text_override` param on `_draw_text`. One-line fast-path bypass. `app._build_widget` allowlist extension.

**Tech Stack:** Python 3.13, attrs, pytest, existing `Typewriter` class in `animations.py` (no API changes).

---

## File Structure

**Modify:**
- `src/led_ticker/widgets/_image_base.py` — add field, validation, `_visible_text` helper, `_draw_text` text_override param, render-tick wiring, fast-path predicate
- `src/led_ticker/app.py` — extend animation-allowlist from `{message}` to `{message, gif, image}`
- `CLAUDE.md` — short paragraph in `_image_base` section
- `config/config.rainbow_border_test.example.toml` — optional §19 smoke demo

**Test (modify):**
- `tests/test_widgets/test_image_base.py` — new `TestImageTypewriter` class (5 tests)
- `tests/test_app.py` — `test_animation_field_accepted_on_image_widget` (1 test)

**No new files.**

---

## Task 1: Add `animation` field + post-init validation

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py:97` (add field after `text_loops`)
- Modify: `src/led_ticker/widgets/_image_base.py:266` (add validation block before two-row mode validation)
- Test: `tests/test_widgets/test_image_base.py` (append new class at end of file)

- [ ] **Step 1.1: Write the failing tests**

Append to `tests/test_widgets/test_image_base.py` at the end of the file:

```python
class TestImageTypewriter:
    """Single-row typewriter on image widgets. Validation + render
    + fast-path bypass + per-effect counter wiring."""

    def _make_still(self, tmp_path, **kwargs):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        return StillImage(path=img_path, **kwargs)

    def test_animation_with_bottom_text_raises(self, tmp_path):
        from led_ticker.animations import Typewriter

        with pytest.raises(ValueError, match="two-row mode"):
            self._make_still(
                tmp_path,
                top_text="hi",
                bottom_text="there",
                animation=Typewriter(),
            )

    def test_animation_with_scroll_align_raises(self, tmp_path):
        from led_ticker.animations import Typewriter

        with pytest.raises(ValueError, match="text_align"):
            self._make_still(
                tmp_path,
                text="Hello",
                text_align="scroll",
                fit="pillarbox",
                animation=Typewriter(),
            )

    def test_animation_with_scroll_over_align_raises(self, tmp_path):
        from led_ticker.animations import Typewriter

        with pytest.raises(ValueError, match="text_align"):
            self._make_still(
                tmp_path,
                text="Hello",
                text_align="scroll_over",
                animation=Typewriter(),
            )

    def test_animation_with_empty_text_raises(self, tmp_path):
        from led_ticker.animations import Typewriter

        with pytest.raises(ValueError, match="non-empty text"):
            self._make_still(
                tmp_path,
                text="",
                animation=Typewriter(),
            )

    def test_animation_field_accepts_typewriter(self, tmp_path):
        """No validation conflict: text_align=left, single-row, non-empty
        text → construction succeeds."""
        from led_ticker.animations import Typewriter

        widget = self._make_still(
            tmp_path,
            text="Hello",
            text_align="left",
            animation=Typewriter(),
        )
        assert widget.animation is not None
        assert isinstance(widget.animation, Typewriter)
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `uv run pytest tests/test_widgets/test_image_base.py::TestImageTypewriter -v`
Expected: 5 FAILED — `StillImage()` rejects `animation` kwarg (`TypeError: unexpected keyword argument 'animation'`).

- [ ] **Step 1.3: Add the field**

In `src/led_ticker/widgets/_image_base.py` after line 97 (`text_loops: int = ...`), add:

```python
    text_loops: int = attrs.field(default=0, kw_only=True)

    # Animation effect (currently Typewriter only). When set, text
    # types out one character per `frames_per_char` ticks. Single-row
    # only — `_validate_common` raises if `bottom_text` is set or
    # `text_align ∈ ("scroll", "scroll_over")`. Composes with
    # `font_color` (rainbow / gradient) and `border` (rainbow /
    # constant) on independent per-effect counters from PR #12.
    animation: Any | None = attrs.field(default=None, kw_only=True)
```

- [ ] **Step 1.4: Add the three validation rules**

In `src/led_ticker/widgets/_image_base.py` `_validate_common` method, find the line that begins the two-row validation block (currently around line 281: `if self.bottom_text:`). Insert this block IMMEDIATELY BEFORE that two-row block, after the existing footgun checks:

```python
        # Animation field validation (single-row typewriter only).
        # All three checks raise at config-load so the user sees the
        # conflict immediately instead of getting a silent surprise
        # on the panel. Bottom_text check fires first because two-row
        # mode is the most likely accidental conflict.
        if self.animation is not None:
            if self.bottom_text:
                raise ValueError(
                    "animation is not supported in two-row mode "
                    "(set on a single-row image widget; remove bottom_text)"
                )
            if self.text_align in ("scroll", "scroll_over"):
                raise ValueError(
                    f"animation is not compatible with "
                    f"text_align={self.text_align!r} "
                    "(typewriter on a moving marquee is incoherent; "
                    "use text_align=auto/left/right)"
                )
            if not self.text:
                raise ValueError(
                    "animation requires non-empty text "
                    "(typewriter has nothing to type out)"
                )
```

- [ ] **Step 1.5: Run tests to verify they pass**

Run: `uv run pytest tests/test_widgets/test_image_base.py::TestImageTypewriter -v`
Expected: 5 PASSED.

- [ ] **Step 1.6: Run full suite to confirm no regressions**

Run: `uv run pytest -q 2>&1 | tail -3`
Expected: all tests pass (1347 baseline + 5 new = 1352).

- [ ] **Step 1.7: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_base.py
git commit -m "image-typewriter: add animation field + post-init validation

Single-row only: raises if bottom_text != \"\", text_align is scroll
or scroll_over, or text is empty. Field defaults to None (no
animation) so existing configs are unchanged.

5 validation tests cover the three error paths + the happy path.
The render-tick wiring lands in the next task — this commit only
makes the field exist and reject conflicts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `_visible_text` helper + `_draw_text` text_override + render-tick wiring

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py:434` (add `text_override` param to `_draw_text`)
- Modify: `src/led_ticker/widgets/_image_base.py:618` (wire `_render_tick` left/right/auto branch through `_visible_text`)
- Modify: `src/led_ticker/widgets/_image_base.py` (add `_visible_text` helper near `_measure_text`)
- Test: `tests/test_widgets/test_image_base.py::TestImageTypewriter`

- [ ] **Step 2.1: Write the failing test**

Append to `TestImageTypewriter` class in `tests/test_widgets/test_image_base.py`:

```python
    def test_visible_text_slices_per_frame(self, tmp_path):
        """Pre-populate the animation per-effect counter to specific
        values; assert `_visible_text` returns the typed-so-far slice
        at each frame. At default frames_per_char=3 with chars_per_frame=1:
          frame=0 → 1 char (Typewriter's `progress = (0 // 3) + 1 = 1`)
          frame=2 → 1 char (still in the first frames_per_char window)
          frame=3 → 2 chars
          frame=6 → 3 chars
          frame=999 → all 5 chars (clamped to len(text)).
        """
        from rgbmatrix import _StubCanvas

        from led_ticker.animations import Typewriter

        widget = self._make_still(
            tmp_path,
            text="Hello",
            text_align="left",
            animation=Typewriter(),
        )
        canvas = _StubCanvas(width=64, height=16)

        # frame=0: 1 char visible
        widget._effect_frames["animation"] = 0
        assert widget._visible_text(0, canvas) == "H"

        # frame=3: 2 chars
        widget._effect_frames["animation"] = 3
        assert widget._visible_text(3, canvas) == "He"

        # frame=6: 3 chars
        widget._effect_frames["animation"] = 6
        assert widget._visible_text(6, canvas) == "Hel"

        # Way past completion: clamps to full text
        widget._effect_frames["animation"] = 999
        assert widget._visible_text(999, canvas) == "Hello"

    def test_visible_text_returns_full_text_when_no_animation(self, tmp_path):
        """`animation = None` (default): helper returns `self.text`
        unchanged so layout / draw code that always calls the helper
        is correct for the no-animation case too."""
        from rgbmatrix import _StubCanvas

        widget = self._make_still(tmp_path, text="Hello", text_align="left")
        canvas = _StubCanvas(width=64, height=16)
        assert widget.animation is None
        assert widget._visible_text(0, canvas) == "Hello"
        assert widget._visible_text(99, canvas) == "Hello"
```

- [ ] **Step 2.2: Run tests to verify they fail**

Run: `uv run pytest tests/test_widgets/test_image_base.py::TestImageTypewriter::test_visible_text_slices_per_frame tests/test_widgets/test_image_base.py::TestImageTypewriter::test_visible_text_returns_full_text_when_no_animation -v`
Expected: 2 FAILED — `_visible_text` does not exist (`AttributeError`).

- [ ] **Step 2.3: Add the `_visible_text` helper**

In `src/led_ticker/widgets/_image_base.py`, find `_measure_text` (around line 427) and add `_visible_text` IMMEDIATELY BEFORE it:

```python
    def _visible_text(self, frame_count: int, canvas: Canvas) -> str:
        """Apply animation to text. Returns full text when no animation
        is configured. Layout (cursor position, alignment math) operates
        against `self.text` regardless — the anchored layout uses the
        eventual full-text width while only the visible slice gets
        drawn. This is what makes typewriter feel 'anchored' under
        right-align: the partial text appears in the position the
        final text will occupy.

        Mirrors `TickerMessage.draw`'s animation branch: calls
        `Typewriter.frame_for(frame, full_text, canvas_width, text_width)`
        and reads `.visible_text` from the returned `AnimationFrame`.
        `cursor_override` is intentionally ignored — image widgets fix
        cursor via `text_align`, not animation overrides (Bounce was
        removed in the PR #11 rework).
        """
        if self.animation is None:
            return self.text
        text_width = self._measure_text(canvas)
        anim_frame = self.animation.frame_for(
            frame_count, self.text, canvas.width, text_width
        )
        return anim_frame.visible_text
```

- [ ] **Step 2.4: Run helper tests to verify pass**

Run: `uv run pytest tests/test_widgets/test_image_base.py::TestImageTypewriter::test_visible_text_slices_per_frame tests/test_widgets/test_image_base.py::TestImageTypewriter::test_visible_text_returns_full_text_when_no_animation -v`
Expected: 2 PASSED.

- [ ] **Step 2.5: Add `text_override` parameter to `_draw_text`**

In `src/led_ticker/widgets/_image_base.py`, replace the entire `_draw_text` method (currently lines 434-479) with:

```python
    def _draw_text(
        self,
        canvas: Canvas,
        x: int,
        baseline_y: int,
        color: Any,
        text_override: str | None = None,
    ) -> int:
        """Route to draw_with_emoji when text contains slugs; otherwise
        plain BDF/HiresFont rasterizer. Emoji's 8-px sprite is anchored
        so its bottom row sits on the text baseline (works for any
        valign/scale).

        `color` accepts a Color or a ColorProvider. For text with emoji,
        the provider passes through to `draw_with_emoji` which dispatches
        on `provider.per_char` — per-char providers iterate text segments
        with continuous char_index across emoji boundaries. Plain text
        with a per-char provider iterates via `draw_text_per_char` so
        rainbow/gradient render with per-character hue offsets; whole-
        string providers materialize once and use `draw_text`.

        `text_override`: when set (typewriter mid-cycle), draws this
        string instead of `self.text`. Per-char providers receive
        `total_chars=len(self.text)` (the eventual full length) so a
        char that types in at position N gets the same hue mid-type
        as it will at completion — anchors hue to char identity, not
        to current visible position.
        """
        text = text_override if text_override is not None else self.text
        # Per-char total: the eventual full-text length, so hue stays
        # anchored to char identity across typewriter's reveal.
        per_char_total = len(self.text) if self.text else 1
        if self._has_emoji():
            from led_ticker.pixel_emoji import draw_with_emoji

            return draw_with_emoji(
                canvas,
                self.font,
                x,
                baseline_y,
                color,
                text,
                emoji_y=baseline_y - 8,
                frame=self.frame_for("font_color"),
            )
        # Plain-text per-char path: rainbow / gradient iterate chars so
        # each character renders with its own hue. Mirrors
        # `TickerMessage.draw`'s per-char branch.
        if hasattr(color, "color_for") and color.per_char:
            return draw_text_per_char(
                canvas,
                self.font,
                x,
                baseline_y,
                text,
                lambda idx, total: color.color_for(
                    self.frame_for("font_color"), idx, per_char_total
                ),
            )
        # Whole-string provider or constant Color.
        if hasattr(color, "color_for"):
            color = color.color_for(
                self.frame_for("font_color"), 0, per_char_total
            )
        return draw_text(canvas, self.font, x, baseline_y, color, text)
```

- [ ] **Step 2.6: Wire `_render_tick` left/right/auto branch through `_visible_text`**

In `src/led_ticker/widgets/_image_base.py`, find the `else:` branch in `_render_tick` (currently around line 613-618). Replace lines 617-618:

```python
            text_x = text_x_left if self.text_align == "left" else text_x_right
            self._draw_text(text_canvas, text_x, baseline_y, provider)
```

with:

```python
            text_x = text_x_left if self.text_align == "left" else text_x_right
            # Apply animation to the visible text. `_visible_text`
            # returns `self.text` when animation is None (no extra
            # work for non-animated widgets) and the typewriter
            # slice when set. Layout (text_x, baseline_y) is already
            # computed against the FULL text width by the caller —
            # we only override the rendered string here.
            text_override = self._visible_text(
                self.frame_for("animation"), text_canvas
            )
            self._draw_text(
                text_canvas, text_x, baseline_y, provider,
                text_override=text_override,
            )
```

- [ ] **Step 2.7: Run full suite to verify no regressions**

Run: `uv run pytest -q 2>&1 | tail -3`
Expected: all tests pass (1352 with the new tests).

- [ ] **Step 2.8: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_base.py
git commit -m "image-typewriter: _visible_text helper + render-tick wiring

New \`_visible_text(frame, canvas)\` helper mirrors TickerMessage's
animation branch — calls \`Typewriter.frame_for(...)\` and returns
\`.visible_text\`. Layout always uses self.text (anchored to
eventual full-text dimensions); only the rendered string changes
mid-type. \`_draw_text\` gains optional \`text_override\` param;
per-char total is len(self.text) so hue stays anchored to char
identity across the reveal.

\`_render_tick\` left/right/auto branch now routes through the
helper. Scroll branches unchanged (animation+scroll forbidden by
post-init validation in Task 1).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Fast-path bypass

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py:783-789` (extend predicate)
- Test: `tests/test_widgets/test_image_base.py::TestImageTypewriter`

- [ ] **Step 3.1: Write the failing test**

Append to `TestImageTypewriter` class:

```python
    async def test_fast_path_bypassed_with_animation(self, tmp_path, mocker):
        """Static still + text_align=left + animation=Typewriter must
        bypass the paint-once-and-sleep fast path so the typewriter's
        per-tick reveal actually runs. Mirrors the existing
        TestPlayWithTextBorderFastPath bypass for animated borders.

        Fast path: `SwapOnVSync.call_count == 1`. Slow path:
        `SwapOnVSync.call_count > 1`. We assert > 1.
        """
        from led_ticker.animations import Typewriter

        widget = self._make_still(
            tmp_path,
            text="Hello",
            text_align="left",
            hold_seconds=0.5,
            animation=Typewriter(),
        )

        frame = mocker.MagicMock()
        # Each swap returns a fresh canvas (mirrors swapping_frame fixture
        # — see CLAUDE.md tripwire #1).
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await widget.play(
            frame.matrix.SwapOnVSync.return_value, frame, loop_count=1
        )

        # Slow path runs N ticks; we just need > 1 to prove fast path
        # was bypassed. Default `hold_seconds=0.5` → ~10 ticks at 50ms.
        assert frame.matrix.SwapOnVSync.call_count > 1, (
            f"animation=Typewriter must force per-tick loop; "
            f"got SwapOnVSync.call_count={frame.matrix.SwapOnVSync.call_count} "
            f"(==1 means fast path ran, freezing typewriter at frame=0)"
        )
```

- [ ] **Step 3.2: Run test to verify it fails**

Run: `uv run pytest tests/test_widgets/test_image_base.py::TestImageTypewriter::test_fast_path_bypassed_with_animation -v`
Expected: FAILED — `SwapOnVSync.call_count == 1` (fast path runs because color, border, and source are all static and animation isn't checked).

- [ ] **Step 3.3: Extend the fast-path predicate**

In `src/led_ticker/widgets/_image_base.py`, find the fast-path gate (currently lines 783-789):

```python
        if (
            not scrolling
            and self.text_loops == 0
            and self._is_static()
            and color_is_static
            and border_is_static
        ):
```

Replace with:

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

- [ ] **Step 3.4: Run test to verify it passes**

Run: `uv run pytest tests/test_widgets/test_image_base.py::TestImageTypewriter::test_fast_path_bypassed_with_animation -v`
Expected: PASSED.

- [ ] **Step 3.5: Run full suite**

Run: `uv run pytest -q 2>&1 | tail -3`
Expected: all tests pass (1353).

- [ ] **Step 3.6: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_base.py
git commit -m "image-typewriter: fast-path bypass when animation is set

\`_play_with_text\` static-text fast path adds \`AND animation is None\`
to its predicate — same shape as the existing \`color.frame_invariant\`
and \`border.frame_invariant\` clauses. Without this, a static still
with typewriter would paint once and sleep, freezing the typewriter
at its initial visible-char count.

Tripwire test asserts SwapOnVSync.call_count > 1 when animation is
set (fast path: ==1; slow path: >1).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Extend `app._build_widget` allowlist

**Files:**
- Modify: `src/led_ticker/app.py:458-464`
- Test: `tests/test_app.py` (append to existing test class or add new)

- [ ] **Step 4.1: Write the failing test**

In `tests/test_app.py`, find the existing `_build_widget` / animation tests and add this test (search for "animation" to find related tests; if none exist, add a new top-level function):

```python
def test_animation_field_accepted_on_image_widget(tmp_path):
    """`type = "image"` with `animation = "typewriter"` builds without
    error. Mirrors the existing TickerMessage animation acceptance.
    Uses a real PNG so _load() doesn't trip."""
    from PIL import Image

    from led_ticker.app import _build_widget

    img_path = tmp_path / "x.png"
    Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)

    cfg = {
        "type": "image",
        "path": str(img_path),
        "text": "Hello",
        "text_align": "left",
        "animation": "typewriter",
    }
    widget = _build_widget(cfg, default_scale=1)
    assert widget.animation is not None


def test_animation_field_accepted_on_gif_widget(tmp_path):
    """`type = "gif"` with `animation = "typewriter"` builds. Same
    contract as image — the field lives on `_BaseImageWidget`."""
    from PIL import Image

    from led_ticker.app import _build_widget

    gif_path = tmp_path / "x.gif"
    Image.new("RGB", (4, 4), (255, 0, 0)).save(gif_path)

    cfg = {
        "type": "gif",
        "path": str(gif_path),
        "text": "Hello",
        "text_align": "left",
        "animation": "typewriter",
    }
    widget = _build_widget(cfg, default_scale=1)
    assert widget.animation is not None
```

- [ ] **Step 4.2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py::test_animation_field_accepted_on_image_widget tests/test_app.py::test_animation_field_accepted_on_gif_widget -v`
Expected: 2 FAILED — `_build_widget` raises `'animation is only valid on type="message"'`.

- [ ] **Step 4.3: Extend the allowlist**

In `src/led_ticker/app.py`, replace the current animation-allowlist block (currently lines 456-466):

```python
    # Animation field (TickerMessage-only). Pop before construction so
    # it doesn't reach the widget constructor as an unknown kwarg.
    animation_value = widget_cfg.pop("animation", None)
    if animation_value is not None and widget_type != "message":
        raise ValueError(
            f'animation is only valid on type="message"; got '
            f"type={widget_type!r}. For color effects on other widgets, "
            f"use font_color = 'rainbow' (or similar)."
        )
    if animation_value is not None:
        widget_cfg["animation"] = _coerce_animation(animation_value)
```

with:

```python
    # Animation field. Currently allowed on `message`, `gif`, and
    # `image` — image widgets restrict to single-row mode (validated
    # in `_BaseImageWidget._validate_common`). Pop before construction
    # so it doesn't reach the widget constructor as an unknown kwarg
    # for widget types that don't accept it.
    animation_value = widget_cfg.pop("animation", None)
    if animation_value is not None and widget_type not in (
        "message",
        "gif",
        "image",
    ):
        raise ValueError(
            f'animation is only valid on type="message", "gif", or '
            f'"image"; got type={widget_type!r}. For color effects on '
            f"other widgets, use font_color = 'rainbow' (or similar)."
        )
    if animation_value is not None:
        widget_cfg["animation"] = _coerce_animation(animation_value)
```

- [ ] **Step 4.4: Run tests to verify pass**

Run: `uv run pytest tests/test_app.py::test_animation_field_accepted_on_image_widget tests/test_app.py::test_animation_field_accepted_on_gif_widget -v`
Expected: 2 PASSED.

- [ ] **Step 4.5: Run full suite**

Run: `uv run pytest -q 2>&1 | tail -3`
Expected: all tests pass (1355).

- [ ] **Step 4.6: Commit**

```bash
git add src/led_ticker/app.py tests/test_app.py
git commit -m "image-typewriter: extend _build_widget animation allowlist

\`animation\` field now accepted on type=\"gif\" and type=\"image\" in
addition to \"message\". The single-row constraints (no bottom_text,
no scroll modes, non-empty text) are enforced by
\`_BaseImageWidget._validate_common\` from Task 1, so this commit
just unlocks the config surface.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: CLAUDE.md update + smoke §19 demo

**Files:**
- Modify: `CLAUDE.md`
- Modify: `config/config.rainbow_border_test.example.toml`

- [ ] **Step 5.1: Update CLAUDE.md**

In `CLAUDE.md`, find the `_image_base` section (search for "GIF widget (`type = "gif"`) and Still-image widget"). Add this paragraph at the end of that section, before the next bold heading:

```markdown
**Typewriter on image widgets** (`animation = "typewriter"` on `gif` / `image`): single-row only — raises if `bottom_text != ""`, `text_align ∈ ("scroll", "scroll_over")`, or `text == ""`. Reads its per-effect counter via `frame_for("animation")` so it composes cleanly with continuous-phase `font_color` and `border` (rainbow text + rainbow border + typewriter all tick on independent counters). Forces the slow path in `_play_with_text` (gate predicate adds `AND animation is None`). Layout uses full-text width; only the visible slice is drawn — characters appear in their final positions, never shifting. Per-char providers receive `total_chars = len(self.text)` so hue is anchored to char identity across the reveal. Tripwires: `tests/test_widgets/test_image_base.py::TestImageTypewriter` (5 tests).
```

- [ ] **Step 5.2: Add smoke §19 to the rainbow-border test config**

In `config/config.rainbow_border_test.example.toml`, find the §18 section (or the current last section). Append:

```toml

# §19 — typewriter on image: caption types in over a held still.
# Three-effect composition: typewriter (restart_on_visit=True) +
# rainbow font color + rainbow border (both restart_on_visit=False)
# on the SAME image widget. Border keeps its chase phase across
# loop_count > 1; font rainbow sweeps continuously; caption retypes
# each loop. The architectural payoff of PR #12 extended to image
# widgets.
[[sections]]
hold_time = 6
loop_count = 3
transition = "cut"

  [[sections.widgets]]
  type = "image"
  path = "config/test.png"
  text = "Hello!"
  text_align = "left"
  animation = "typewriter"
  font_color = "rainbow"
  border = "rainbow"
```

Note: this section assumes a `config/test.png` exists. If it doesn't, leave §19 commented out; the user can supply an image path when they run the smoke locally.

- [ ] **Step 5.3: Verify smoke config loads (sanity)**

Run: `uv run python -c "from led_ticker.config import load_config; load_config('config/config.rainbow_border_test.example.toml')" 2>&1 | tail -3`
Expected: no output (silent success). If `test.png` doesn't exist, comment out §19 first or skip this step.

- [ ] **Step 5.4: Commit**

```bash
git add CLAUDE.md config/config.rainbow_border_test.example.toml
git commit -m "image-typewriter: CLAUDE.md doc + smoke §19 three-effect demo

Documentation paragraph in the _image_base section explains the
single-row constraint, the per-effect counter wiring, the fast-
path bypass, and the per-char hue-anchoring rule. Smoke §19 adds
a hardware-validatable three-effect composition: typewriter
retypes each loop while rainbow text + rainbow border phase
continuously. This is the same architectural pattern §17/§18
demonstrated for TickerMessage in PR #12.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] **All tasks complete: run full suite + lint**

```bash
uv run pytest -q 2>&1 | tail -3
make lint 2>&1 | tail -3
```

Expected: all 1355 tests pass; ruff clean.

- [ ] **Push branch + open PR**

```bash
git push -u origin feat/image-typewriter
gh pr create --title "image widgets: animation = \"typewriter\" support (single-row)" --body "$(cat <<'EOF'
## Summary

Adds `animation = "typewriter"` to single-row `gif` and `image` widgets. Per-effect counters from PR #12 enable clean composition with `font_color = "rainbow"` and `border = "rainbow"` on the same widget — three independent frame systems, no shared state.

Single-row only by design: scroll modes and two-row mode raise at config-load.

## Test Plan

- [x] All 1355 tests pass (1347 baseline + 8 new)
- [x] Ruff + pyright clean
- [ ] Hardware validation on bigsign §19 of `config.rainbow_border_test.example.toml`
- [ ] Verify typewriter retypes on `loop_count = 3` while rainbow font + border keep continuous phase

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Out of Scope (do NOT add)

- Two-row typewriter (separate spec)
- Typewriter on `text_align ∈ ("scroll", "scroll_over")` — explicitly forbidden
- Per-image typewriter speed override (use existing inline-table syntax)
- Bounce or other animations — only Typewriter has a `visible_chars`-style surface
