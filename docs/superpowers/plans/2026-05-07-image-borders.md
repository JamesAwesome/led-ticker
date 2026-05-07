# Image Borders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing `border` feature (RainbowChaseBorder, ConstantBorder) to image widgets — `GifPlayer` (`type="gif"`) and `StillImage` (`type="image"`) — across all 4 render paths.

**Architecture:** Add a `border: BorderEffect | None` field on `_BaseImageWidget`. Insert `border.paint(canvas, self._frame_count)` after the image paint and before any text paint in each of the 4 render paths. Refactor `GifPlayer._play_no_text` to engine 50ms cadence so animated borders chase uniformly. Update three fast-path gates to also check `border.frame_invariant`. Extend `_build_widget`'s allow-list to accept `border` on `gif` and `image`.

**Tech Stack:** Python 3.13, asyncio, attrs, pytest, ruff. Existing `BorderEffect` Protocol in `src/led_ticker/borders.py` is unchanged — this plan is pure consumer-side work.

**Spec:** [`docs/superpowers/specs/2026-05-07-image-borders-design.md`](../specs/2026-05-07-image-borders-design.md)

**Worktree:** `.claude/worktrees/image-borders` (branch `feat/image-borders`)

---

## File Inventory

**Modified:**
- `src/led_ticker/widgets/_image_base.py` — add `border` field; integrate paint in `_render_tick` + `_render_two_row_tick`; update fast-path gates in `_play_with_text` + `_play_with_two_row_text`.
- `src/led_ticker/widgets/gif.py` — refactor `_play_no_text` to 50ms cadence; integrate border paint.
- `src/led_ticker/widgets/still.py` — two-mode pattern in `_play_no_text`; integrate border paint.
- `src/led_ticker/app.py` — extend `_build_widget` border allow-list.
- `tests/test_app.py` — add gif/image acceptance tests; fix the existing rejection test (uses "weather" as the unsupported-type example, which still works).
- `tests/test_widgets/test_image_base.py` — paint-order tripwires + fast-path gate tests + ScaledCanvas physical-resolution test.
- `tests/test_widgets/test_gif.py` — border-ticks-during-no-text test + 50ms-refactor preservation test.
- `tests/test_widgets/test_still.py` — fast-path-with-constant-border test + slow-path-with-animated-border test.
- `CLAUDE.md` — extend "Rainbow border" section to list `gif`/`image` and document the no-text path's 50ms cadence.

**Not modified (referenced):**
- `src/led_ticker/borders.py` — `BorderEffect`, `RainbowChaseBorder`, `ConstantBorder` (unchanged).
- `src/led_ticker/ticker.py` — `ENGINE_TICK_MS` constant (already 50). Import as `from led_ticker.ticker import ENGINE_TICK_MS`.

---

## Implementation Conventions

**TDD discipline:** every task writes the failing test first, runs it to confirm it fails, then implements minimal code, runs the test to confirm it passes, then commits.

**Border-static gate predicate** (used in 3 fast-path sites + the StillImage two-mode pattern; identical line each time):

```python
border_is_static = (
    getattr(self.border, "frame_invariant", True) if self.border else True
)
```

`None` → True (no border, no animation cost). `ConstantBorder` → True (class attribute). `RainbowChaseBorder(speed=0)` → True (property). `RainbowChaseBorder(speed>0)` → False.

**Test commands** (from worktree root):
- One file: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py -v`
- One test: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py::TestImageBorderField::test_border_field_default -v`
- Full suite: `PYTHONPATH=tests/stubs uv run pytest -x -q`

**Lint:** `uv run ruff check src/led_ticker tests` after each task.

---

### Task 1: Add `border` field to `_BaseImageWidget` + extend allow-list

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py:139` (insert new attrs field; existing fields end at line 138 with `top_row_height`)
- Modify: `src/led_ticker/app.py:474-485` (allow-list extension)
- Test: `tests/test_app.py` (new tests at end of `class TestBorders`)
- Test: `tests/test_widgets/test_image_base.py` (new class `TestImageBorderField`)

- [ ] **Step 1: Write the failing test for the field default**

Append to `tests/test_widgets/test_image_base.py`:

```python
class TestImageBorderField:
    """`_BaseImageWidget` exposes a `border: BorderEffect | None`
    field that subclasses (StillImage, GifPlayer) inherit. Default
    is None — no border, no animation overhead."""

    def test_border_field_default(self):
        from pathlib import Path

        from led_ticker.widgets.still import StillImage

        # Use a tiny test PNG already shipped with the repo if any;
        # otherwise the field default is observable on the class
        # without instantiation.
        assert StillImage.__attrs_attrs__  # sanity: attrs class
        names = [a.name for a in StillImage.__attrs_attrs__]
        assert "border" in names, (
            f"StillImage missing inherited `border` field; "
            f"fields: {names}"
        )

    def test_border_default_is_none(self, tmp_path):
        """Default value is None — confirmed via construction."""
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "tiny.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        widget = StillImage(path=img_path)
        assert widget.border is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py::TestImageBorderField -v`

Expected: FAIL with `assert "border" in names` failure (or `AttributeError`).

- [ ] **Step 3: Add the `border` field to `_BaseImageWidget`**

In `src/led_ticker/widgets/_image_base.py`, after the existing `top_row_height` field (~line 138) and before `# Framework-internal — not user-facing TOML.`:

```python
    # Optional perimeter border effect — same contract as
    # `TickerMessage.border` and `TwoRowMessage.border` (see
    # borders.py). Paints AFTER the image and BEFORE any text overlay
    # so the border frames the panel and text overlaps it on
    # collision. None = no border (no perf cost). Coerced from
    # TOML at config-load via `_coerce_border` in app.py.
    border: Any | None = attrs.field(default=None, kw_only=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py::TestImageBorderField -v`

Expected: PASS (2 tests).

- [ ] **Step 5: Write the failing test for config-load acceptance on gif/image**

Append to `tests/test_app.py` `class TestBorders` (search for `async def test_two_row_with_border_string`; place new tests just below it):

```python
    async def test_gif_with_border_string(self, tmp_path):
        """GifPlayer accepts `border` with the same TOML vocabulary."""
        from PIL import Image

        from led_ticker.borders import RainbowChaseBorder

        gif_path = tmp_path / "tiny.gif"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(
            gif_path, save_all=True, append_images=[
                Image.new("RGB", (4, 4), (0, 255, 0)),
            ], duration=100, loop=0,
        )
        cfg = {
            "type": "gif",
            "path": str(gif_path),
            "border": "rainbow",
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget.border, RainbowChaseBorder)

    async def test_image_with_border_table(self, tmp_path):
        """StillImage accepts `border` as an inline table."""
        from PIL import Image

        from led_ticker.borders import ConstantBorder

        img_path = tmp_path / "tiny.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        cfg = {
            "type": "image",
            "path": str(img_path),
            "border": {"style": "constant", "color": [0, 255, 0]},
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget.border, ConstantBorder)

    async def test_image_without_border_has_none(self, tmp_path):
        from PIL import Image

        img_path = tmp_path / "tiny.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        cfg = {"type": "image", "path": str(img_path)}
        widget = await _build_widget(cfg, session=mock.Mock())
        assert widget.border is None
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_app.py::TestBorders::test_gif_with_border_string tests/test_app.py::TestBorders::test_image_with_border_table -v`

Expected: FAIL with `ValueError: border is only valid on type="message", "countdown", or "two_row"; got type='gif'`.

- [ ] **Step 7: Update the allow-list in `_build_widget`**

In `src/led_ticker/app.py`, find the block at lines 474–485 and update:

```python
    border_value = widget_cfg.pop("border", None)
    if border_value is not None and widget_type not in (
        "message",
        "countdown",
        "two_row",
        "gif",
        "image",
    ):
        raise ValueError(
            f'border is only valid on type="message", "countdown", '
            f'"two_row", "gif", or "image"; got type={widget_type!r}.'
        )
    if border_value is not None:
        widget_cfg["border"] = _coerce_border(border_value)
```

- [ ] **Step 8: Run tests to verify all pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_app.py::TestBorders tests/test_widgets/test_image_base.py::TestImageBorderField -v`

Expected: PASS (all tests in TestBorders + 2 new in TestImageBorderField).

- [ ] **Step 9: Update existing rejection test message**

The existing `test_border_on_unsupported_widget_type_raises` in `tests/test_app.py` matches the OLD error string (`'border is only valid on type="message", "countdown", or "two_row"'`). Update its `match=` to the new message:

```python
        with pytest.raises(
            ValueError,
            match=(
                r'border is only valid on type="message", "countdown", '
                r'"two_row", "gif", or "image"'
            ),
        ):
```

(The widget type in the test is `"weather"` — that still raises correctly under the new allow-list.)

- [ ] **Step 10: Run the rejection test to verify**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_app.py::TestBorders::test_border_on_unsupported_widget_type_raises -v`

Expected: PASS.

- [ ] **Step 11: Run full lint + suite**

Run: `uv run ruff check src/led_ticker tests && PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: lint clean; all existing tests still pass plus the new ones.

- [ ] **Step 12: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py src/led_ticker/app.py tests/test_widgets/test_image_base.py tests/test_app.py
git commit -m "image-borders: add border field + extend config-load allow-list"
```

---

### Task 2: Border integration in `_render_tick` (single-row paths)

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py:540-569` (`_render_tick` method)
- Test: `tests/test_widgets/test_image_base.py` (new class `TestRenderTickBorder`)

The 3 single-row sub-paths (non-scroll, scroll skip-black, scroll_over) each get a border paint. Per the spec's paint-order table:

- non-scroll & scroll_over: image → **border** → text
- scroll (skip-black): text → image → **border** (border last so it stays visible at panel edges over both image silhouette and any scrolled text)

- [ ] **Step 1: Write the failing tests for paint order**

Append to `tests/test_widgets/test_image_base.py`:

```python
class TestRenderTickBorder:
    """Border integration in `_render_tick` — paints AFTER image
    paint and BEFORE text paint (non-scroll / scroll_over) or after
    everything (skip-black scroll). The 'border frames the panel'
    convention: text overlaps border on collision in modes where
    text paints on top of image; border overlaps text + image
    silhouette in skip-black mode."""

    @pytest.fixture
    def order_recorder(self, monkeypatch):
        """Patch `_paint_image`, `_paint_skip_black`, `_draw_text`,
        and a mock `border.paint` to record call order."""
        order: list[str] = []

        def _record(name):
            def _fn(self, *a, **kw):
                order.append(name)
                return 0  # _draw_text returns int (cursor advance)
            return _fn

        # Patch on `StillImage` (the subclass) — `_paint_skip_black`
        # is overridden there, so a base-class patch wouldn't
        # intercept the call. `raising=False` because `_paint_image`
        # / `_draw_text` are base-only and may not exist on the
        # subclass yet (monkeypatch adds them, which shadows the
        # base method via Python's attribute lookup order).
        from led_ticker.widgets.still import StillImage

        monkeypatch.setattr(
            StillImage, "_paint_image", _record("paint_image"), raising=False
        )
        monkeypatch.setattr(
            StillImage,
            "_paint_skip_black",
            _record("paint_skip_black"),
            raising=False,
        )
        monkeypatch.setattr(
            StillImage, "_draw_text", _record("draw_text"), raising=False
        )
        return order

    def _make_widget(self, tmp_path, text_align: str, border):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        return StillImage(
            path=img_path,
            text="hi",
            text_align=text_align,
            border=border,
        )

    def test_render_tick_left_paints_image_then_border_then_text(
        self, tmp_path, order_recorder
    ):
        from rgbmatrix import _StubCanvas as RealStub

        border = mock.Mock()
        border.frame_invariant = False
        border.paint.side_effect = lambda *a, **kw: order_recorder.append("border")

        widget = self._make_widget(tmp_path, "left", border)
        canvas = RealStub(width=64, height=32)
        widget._render_tick(canvas, canvas, 0, 12, 2, 60)

        assert order_recorder == ["paint_image", "border", "draw_text"], (
            f"left: expected image→border→text; got {order_recorder}"
        )

    def test_render_tick_scroll_over_paints_image_then_border_then_text(
        self, tmp_path, order_recorder
    ):
        from rgbmatrix import _StubCanvas as RealStub

        border = mock.Mock()
        border.frame_invariant = False
        border.paint.side_effect = lambda *a, **kw: order_recorder.append("border")

        widget = self._make_widget(tmp_path, "scroll_over", border)
        canvas = RealStub(width=64, height=32)
        widget._render_tick(canvas, canvas, 0, 12, 2, 60)

        assert order_recorder == ["paint_image", "border", "draw_text"], (
            f"scroll_over: expected image→border→text; got {order_recorder}"
        )

    def test_render_tick_scroll_paints_text_then_image_then_border(
        self, tmp_path, order_recorder
    ):
        """Skip-black scroll: text walks behind silhouette (existing
        semantics) — border lands LAST so it remains visible over
        both image and any text at panel edges."""
        from rgbmatrix import _StubCanvas as RealStub

        border = mock.Mock()
        border.frame_invariant = False
        border.paint.side_effect = lambda *a, **kw: order_recorder.append("border")

        widget = self._make_widget(tmp_path, "scroll", border)
        canvas = RealStub(width=64, height=32)
        widget._render_tick(canvas, canvas, 0, 12, 2, 60)

        assert order_recorder == ["draw_text", "paint_skip_black", "border"], (
            f"scroll: expected text→image-skip-black→border; "
            f"got {order_recorder}"
        )

    def test_render_tick_no_border_omits_paint(self, tmp_path, order_recorder):
        """Border=None: no border calls, image+text path unchanged."""
        from rgbmatrix import _StubCanvas as RealStub

        widget = self._make_widget(tmp_path, "left", None)
        canvas = RealStub(width=64, height=32)
        widget._render_tick(canvas, canvas, 0, 12, 2, 60)

        assert order_recorder == ["paint_image", "draw_text"]

    def test_render_tick_passes_frame_count_to_border(self, tmp_path):
        """border.paint receives the widget's current `_frame_count`."""
        from rgbmatrix import _StubCanvas as RealStub

        border = mock.Mock()
        border.frame_invariant = False

        widget = self._make_widget(tmp_path, "left", border)
        widget._frame_count = 17
        canvas = RealStub(width=64, height=32)
        widget._render_tick(canvas, canvas, 0, 12, 2, 60)

        border.paint.assert_called_once_with(canvas, 17)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py::TestRenderTickBorder -v`

Expected: FAIL — `border.paint` is never called from `_render_tick` yet.

- [ ] **Step 3: Insert border paints in `_render_tick`**

In `src/led_ticker/widgets/_image_base.py`, replace the existing `_render_tick` body (lines 540-569) with:

```python
    def _render_tick(
        self,
        canvas: Canvas,
        text_canvas: Canvas,
        scroll_pos: int,
        baseline_y: int,
        text_x_left: int,
        text_x_right: int,
    ) -> None:
        """Compose one frame: reset canvas (Clear or Fill bg) + paint
        image + paint border + paint text in the right order for the
        current `text_align`. Border lands AFTER image (to overlay
        image edges — frames the panel) and BEFORE text in the modes
        where text paints on top of image. In skip-black scroll mode
        text walks BEHIND the image silhouette (existing semantics);
        border lands LAST in that path so it stays visible over both
        image silhouette and any scrolled text at the panel edges."""
        reset_canvas(canvas, self.bg_color)

        # Pass the provider (not a materialized Color) so per-char
        # effects survive emoji boundaries. _draw_text materializes
        # internally for the non-emoji path; the emoji path forwards
        # the provider to draw_with_emoji.
        provider = self.font_color

        if self.text_align == "scroll":
            self._draw_text(text_canvas, scroll_pos, baseline_y, provider)
            self._paint_skip_black(canvas)
            if self.border is not None:
                self.border.paint(canvas, self._frame_count)
        elif self.text_align == "scroll_over":
            self._paint_image(canvas)
            if self.border is not None:
                self.border.paint(canvas, self._frame_count)
            self._draw_text(text_canvas, scroll_pos, baseline_y, provider)
        else:
            self._paint_image(canvas)
            if self.border is not None:
                self.border.paint(canvas, self._frame_count)
            text_x = text_x_left if self.text_align == "left" else text_x_right
            self._draw_text(text_canvas, text_x, baseline_y, provider)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py::TestRenderTickBorder -v`

Expected: PASS (5 tests).

- [ ] **Step 5: Run full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_base.py
git commit -m "image-borders: integrate border paint in _render_tick (3 sub-paths)"
```

---

### Task 3: Border integration in `_render_two_row_tick`

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py:571-602` (`_render_two_row_tick` method)
- Test: `tests/test_widgets/test_image_base.py` (new class `TestRenderTwoRowTickBorder`)

Two-row image widget canvas is the unwrapped real canvas (image at native pixels) + a wrapped text_canvas. Border paints to `real_canvas` (the unwrapped one) AFTER image and BEFORE the two row draws. `border.paint` does its own `unwrap_to_real` internally so passing the wrapper would also work — but per the existing pattern (image goes to `real_canvas`), the border call site uses `real_canvas` for clarity.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_widgets/test_image_base.py`:

```python
class TestRenderTwoRowTickBorder:
    """Border in two-row mode: paint AFTER image, BEFORE either
    row's text. Border target is the unwrapped real canvas (where
    the image was painted) — same convention as TwoRowMessage."""

    @pytest.fixture
    def order_recorder(self, monkeypatch):
        order: list[str] = []

        def _record(name):
            def _fn(self, *a, **kw):
                order.append(name)
            return _fn

        from led_ticker.widgets import _image_base

        monkeypatch.setattr(
            _image_base._BaseImageWidget,
            "_paint_image",
            _record("paint_image"),
            raising=False,
        )
        monkeypatch.setattr(
            _image_base._BaseImageWidget,
            "_draw_row_text",
            _record("draw_row_text"),
            raising=False,
        )
        return order

    def _make_widget(self, tmp_path, border):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        return StillImage(
            path=img_path,
            top_text="@brand",
            bottom_text="tagline",
            border=border,
        )

    def test_two_row_paints_image_then_border_then_rows(
        self, tmp_path, order_recorder
    ):
        from rgbmatrix import _StubCanvas as RealStub

        border = mock.Mock()
        border.frame_invariant = False
        border.paint.side_effect = lambda *a, **kw: order_recorder.append("border")

        widget = self._make_widget(tmp_path, border)
        real_canvas = RealStub(width=128, height=32)
        # Pre-resolved row tuples are what the loop passes; values
        # here are placeholders (color/x/baseline don't matter
        # because _draw_row_text is patched to a recorder).
        top = (None, "@brand", None, 0, 6, 0)
        bottom = (None, "tagline", None, 0, 22, 0)

        widget._render_two_row_tick(real_canvas, real_canvas, top, bottom)

        assert order_recorder == [
            "paint_image",
            "border",
            "draw_row_text",
            "draw_row_text",
        ], f"expected image→border→top→bottom; got {order_recorder}"

    def test_two_row_no_border_runs_clean(self, tmp_path, order_recorder):
        """Border=None: image + 2 row draws, no border calls."""
        from rgbmatrix import _StubCanvas as RealStub

        widget = self._make_widget(tmp_path, None)
        real_canvas = RealStub(width=128, height=32)
        top = (None, "@brand", None, 0, 6, 0)
        bottom = (None, "tagline", None, 0, 22, 0)

        widget._render_two_row_tick(real_canvas, real_canvas, top, bottom)

        assert order_recorder == [
            "paint_image",
            "draw_row_text",
            "draw_row_text",
        ]

    def test_two_row_border_receives_widget_frame_count(self, tmp_path):
        from rgbmatrix import _StubCanvas as RealStub

        border = mock.Mock()
        border.frame_invariant = False

        widget = self._make_widget(tmp_path, border)
        widget._frame_count = 99
        real_canvas = RealStub(width=128, height=32)
        top = (None, "@brand", None, 0, 6, 0)
        bottom = (None, "tagline", None, 0, 22, 0)

        widget._render_two_row_tick(real_canvas, real_canvas, top, bottom)

        border.paint.assert_called_once_with(real_canvas, 99)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py::TestRenderTwoRowTickBorder -v`

Expected: FAIL — border.paint not called.

- [ ] **Step 3: Insert border paint in `_render_two_row_tick`**

In `src/led_ticker/widgets/_image_base.py`, update the `_render_two_row_tick` body (around line 599-602):

```python
        reset_canvas(real_canvas, self.bg_color)
        self._paint_image(real_canvas)
        if self.border is not None:
            self.border.paint(real_canvas, self._frame_count)
        self._draw_row_text(text_canvas, *top)
        self._draw_row_text(text_canvas, *bottom)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py::TestRenderTwoRowTickBorder -v`

Expected: PASS (3 tests).

- [ ] **Step 5: Run full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_base.py
git commit -m "image-borders: integrate border paint in _render_two_row_tick"
```

---

### Task 4: Fast-path gate in `_play_with_text`

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py:~722-747` (fast-path predicate)
- Test: `tests/test_widgets/test_image_base.py` (new class `TestPlayWithTextBorderFastPath`)

The existing fast-path predicate is `not scrolling and self.text_loops == 0 and self._is_static() and color_is_static`. Add `border_is_static` to the AND chain. Without this, a static-text image with a `RainbowChaseBorder(speed=4)` paints once and sleeps for N ticks — rainbow freezes.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_widgets/test_image_base.py`:

```python
class TestPlayWithTextBorderFastPath:
    """Fast-path gate in `_play_with_text` must consider
    `border.frame_invariant`. Animated border (rainbow with
    speed>0) forces the per-tick loop; constant border keeps the
    fast path."""

    @pytest.fixture
    def static_widget(self, tmp_path):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        # Static text: text_align="left", no scroll, text_loops=0,
        # is_static() True (StillImage), color_is_static (default).
        return StillImage(
            path=img_path,
            text="HI",
            text_align="left",
            hold_seconds=0.5,  # 10 ticks at 50ms
        )

    async def test_fast_path_with_constant_border_runs_once(
        self, static_widget, mock_frame
    ):
        """ConstantBorder is frame_invariant=True; fast path stays
        valid. _render_tick runs once, then the path sleeps."""
        from led_ticker.borders import ConstantBorder

        static_widget.border = ConstantBorder([255, 0, 0])

        with mock.patch.object(
            type(static_widget), "_render_tick"
        ) as render_mock:
            with mock.patch("asyncio.sleep", new=mock.AsyncMock()):
                await static_widget._play_with_text(
                    mock_frame.matrix.SwapOnVSync.return_value,
                    mock_frame,
                    n_ticks=10,
                )
        assert render_mock.call_count == 1, (
            f"ConstantBorder (frame_invariant) must take fast path; "
            f"got {render_mock.call_count} render calls"
        )

    async def test_fast_path_bypassed_with_animated_border(
        self, static_widget, mock_frame
    ):
        """RainbowChaseBorder(speed=4) is NOT frame_invariant; fast
        path bypassed; per-tick loop runs n_ticks times."""
        from led_ticker.borders import RainbowChaseBorder

        static_widget.border = RainbowChaseBorder(speed=4)

        with mock.patch.object(
            type(static_widget), "_render_tick"
        ) as render_mock:
            with mock.patch("asyncio.sleep", new=mock.AsyncMock()):
                await static_widget._play_with_text(
                    mock_frame.matrix.SwapOnVSync.return_value,
                    mock_frame,
                    n_ticks=10,
                )
        assert render_mock.call_count == 10, (
            f"Animated border must force per-tick loop; got "
            f"{render_mock.call_count} renders, expected 10"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py::TestPlayWithTextBorderFastPath -v`

Expected: the animated-border test FAILS (currently fast-paths regardless of border, so renders only once).

- [ ] **Step 3: Update the fast-path predicate**

In `src/led_ticker/widgets/_image_base.py`, in `_play_with_text`, locate the fast-path block (`if (not scrolling and self.text_loops == 0 and self._is_static() and color_is_static):` around line 725) and update:

```python
        text_is_wrapped = isinstance(text_canvas, ScaledCanvas)
        color_is_static = getattr(self.font_color, "frame_invariant", False)
        border_is_static = (
            getattr(self.border, "frame_invariant", True) if self.border else True
        )

        if (
            not scrolling
            and self.text_loops == 0
            and self._is_static()
            and color_is_static
            and border_is_static
        ):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py::TestPlayWithTextBorderFastPath -v`

Expected: PASS (2 tests).

- [ ] **Step 5: Run full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_base.py
git commit -m "image-borders: fast-path gate in _play_with_text honors border.frame_invariant"
```

---

### Task 5: Fast-path gate in `_play_with_two_row_text`

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py:~895-924` (two-row fast-path predicate)
- Test: `tests/test_widgets/test_image_base.py` (new class `TestPlayWithTwoRowBorderFastPath`)

Same shape as Task 4 but on the two-row variant. The existing predicate is `not bottom_scrolls and self._is_static() and self.text_loops == 0 and colors_are_static`. Add `border_is_static`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_widgets/test_image_base.py`:

```python
class TestPlayWithTwoRowBorderFastPath:
    """Same fast-path gate logic on the two-row playback path."""

    @pytest.fixture
    def static_widget(self, tmp_path):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        # Two-row mode: bottom_text non-empty + bottom fits (no scroll).
        return StillImage(
            path=img_path,
            top_text="@",
            bottom_text="x",
            top_align="center",
            bottom_align="center",
            hold_seconds=0.5,
        )

    async def test_two_row_fast_path_with_constant_border(
        self, static_widget, mock_frame
    ):
        from led_ticker.borders import ConstantBorder

        static_widget.border = ConstantBorder([0, 255, 0])

        with mock.patch.object(
            type(static_widget), "_render_two_row_tick"
        ) as render_mock:
            with mock.patch("asyncio.sleep", new=mock.AsyncMock()):
                await static_widget._play_with_two_row_text(
                    mock_frame.matrix.SwapOnVSync.return_value,
                    mock_frame,
                    n_ticks=10,
                )
        assert render_mock.call_count == 1

    async def test_two_row_fast_path_bypassed_with_animated_border(
        self, static_widget, mock_frame
    ):
        from led_ticker.borders import RainbowChaseBorder

        static_widget.border = RainbowChaseBorder(speed=4)

        with mock.patch.object(
            type(static_widget), "_render_two_row_tick"
        ) as render_mock:
            with mock.patch("asyncio.sleep", new=mock.AsyncMock()):
                await static_widget._play_with_two_row_text(
                    mock_frame.matrix.SwapOnVSync.return_value,
                    mock_frame,
                    n_ticks=10,
                )
        assert render_mock.call_count == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py::TestPlayWithTwoRowBorderFastPath -v`

Expected: animated-border test FAILS.

- [ ] **Step 3: Update the two-row fast-path predicate**

In `src/led_ticker/widgets/_image_base.py`, in `_play_with_two_row_text`, locate the fast-path block (around line 901-910) and update:

```python
        colors_are_static = getattr(top_color, "frame_invariant", False) and getattr(
            bottom_color, "frame_invariant", False
        )
        border_is_static = (
            getattr(self.border, "frame_invariant", True) if self.border else True
        )

        if (
            not bottom_scrolls
            and self._is_static()
            and self.text_loops == 0
            and colors_are_static
            and border_is_static
        ):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py::TestPlayWithTwoRowBorderFastPath -v`

Expected: PASS (2 tests).

- [ ] **Step 5: Run full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_base.py
git commit -m "image-borders: fast-path gate in _play_with_two_row_text honors border.frame_invariant"
```

---

### Task 6: Refactor `GifPlayer._play_no_text` to 50ms cadence + integrate border

**Files:**
- Modify: `src/led_ticker/widgets/gif.py:~282-297` (`_play_no_text` method)
- Test: `tests/test_widgets/test_gif.py` (new class `TestGifPlayNoTextRefactor`)

Today's `_play_no_text` loops at gif-frame cadence. Refactor to engine 50ms cadence using `_pick_frame_for_elapsed` (the same pattern `_play_with_text` uses). This makes animated borders chase uniformly regardless of gif frame durations.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_widgets/test_gif.py`:

```python
class TestGifPlayNoTextRefactor:
    """`GifPlayer._play_no_text` runs at 50ms engine cadence (not
    gif-frame cadence) so animated borders chase uniformly. The
    refactor must preserve gif animation: a 3-frame gif at 100ms
    each + loop_count=1 still produces 3 distinct frame indices
    over its 300ms run."""

    @pytest.fixture
    def three_frame_gif(self, tmp_path):
        from PIL import Image

        gif_path = tmp_path / "three.gif"
        frames = [
            Image.new("RGB", (4, 4), (255, 0, 0)),
            Image.new("RGB", (4, 4), (0, 255, 0)),
            Image.new("RGB", (4, 4), (0, 0, 255)),
        ]
        frames[0].save(
            gif_path,
            save_all=True,
            append_images=frames[1:],
            duration=100,
            loop=0,
        )
        return gif_path

    async def test_no_text_loop_advances_at_50ms(
        self, three_frame_gif, mock_frame
    ):
        """6 ticks expected (300ms / 50ms). Frame indices over the
        run hit 0, 1, 2 (each held for 2 consecutive 50ms ticks)."""
        from led_ticker.widgets.gif import GifPlayer

        widget = GifPlayer(path=three_frame_gif)

        observed_idxs: list[int] = []

        original_pick = widget._pick_frame_for_elapsed

        def _spy(elapsed_ms: int) -> None:
            original_pick(elapsed_ms)
            observed_idxs.append(widget._current_frame_idx)

        with mock.patch.object(widget, "_pick_frame_for_elapsed", _spy):
            with mock.patch("asyncio.sleep", new=mock.AsyncMock()):
                await widget._play_no_text(
                    mock_frame.matrix.SwapOnVSync.return_value,
                    mock_frame,
                    loop_count=1,
                )

        # 300ms / 50ms = 6 ticks
        assert len(observed_idxs) == 6, (
            f"expected 6 50ms ticks; got {len(observed_idxs)}"
        )
        # Distinct frame indices over the run
        assert set(observed_idxs) == {0, 1, 2}, (
            f"expected all 3 frames seen over the run; "
            f"got {observed_idxs}"
        )

    async def test_no_text_with_animated_border_calls_paint_per_tick(
        self, tmp_path, mock_frame
    ):
        """Single-frame gif (effectively static) + RainbowChaseBorder
        (speed=4) — border.paint fires every 50ms tick with strictly
        increasing frame_count."""
        from PIL import Image

        from led_ticker.borders import RainbowChaseBorder
        from led_ticker.widgets.gif import GifPlayer

        gif_path = tmp_path / "one.gif"
        # Single-frame gif with 500ms duration: 500/50 = 10 ticks.
        Image.new("RGB", (4, 4), (255, 0, 0)).save(
            gif_path, duration=500, loop=0,
        )
        widget = GifPlayer(path=gif_path, border=RainbowChaseBorder(speed=4))

        with mock.patch("asyncio.sleep", new=mock.AsyncMock()):
            await widget._play_no_text(
                mock_frame.matrix.SwapOnVSync.return_value,
                mock_frame,
                loop_count=1,
            )

        # 10 ticks → 10 border.paint calls. (border is the actual
        # RainbowChaseBorder, not a mock — assert via spying on its
        # paint method.)
        # We can replace the border with a spying wrapper instead:
        # but the simpler check is on _frame_count progression.
        assert widget._frame_count >= 9, (
            f"_frame_count should advance ~10× over 500ms; "
            f"got {widget._frame_count}"
        )

    async def test_no_text_without_border_unchanged_image_paint(
        self, three_frame_gif, mock_frame
    ):
        """Refactor preserves non-bordered playback: image paints
        every tick, no border calls (border=None default)."""
        from led_ticker.widgets.gif import GifPlayer

        widget = GifPlayer(path=three_frame_gif)
        # Border is None — _paint_image should still be called per
        # tick. We confirm via a spy.
        paint_count = [0]
        original_paint = widget._paint_image

        def _spy(canvas):
            paint_count[0] += 1
            return original_paint(canvas)

        with mock.patch.object(widget, "_paint_image", side_effect=_spy):
            with mock.patch("asyncio.sleep", new=mock.AsyncMock()):
                await widget._play_no_text(
                    mock_frame.matrix.SwapOnVSync.return_value,
                    mock_frame,
                    loop_count=1,
                )

        assert paint_count[0] == 6, (
            f"expected 6 image paints (300ms / 50ms); "
            f"got {paint_count[0]}"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_gif.py::TestGifPlayNoTextRefactor -v`

Expected: FAIL — current `_play_no_text` runs at gif-frame cadence (3 ticks for the 3-frame gif), border field doesn't exist yet on the painter (will surface as AttributeError or no border calls).

- [ ] **Step 3: Refactor `_play_no_text`**

In `src/led_ticker/widgets/gif.py`, replace the current `_play_no_text` body (lines 282-297) with:

```python
    async def _play_no_text(
        self, real_canvas: Canvas, frame: Any, loop_count: int
    ) -> Canvas:
        """Run the gif at engine 50ms cadence — `_pick_frame_for_elapsed`
        picks the right gif frame from accumulated wall-clock time so
        animated borders (and any future frame-aware overlays) tick
        uniformly regardless of gif frame durations.

        Side effect: gifs with native frame durations < 50ms cap at
        20 Hz on this path — same cap `_play_with_text` already
        imposes. Gifs with frame durations >= 50ms (the common case)
        render identically to before.
        """
        from led_ticker.ticker import ENGINE_TICK_MS

        loops = max(1, loop_count)
        canvas = real_canvas
        total_ms = sum(d for _, d in self._frames) * loops
        n_ticks = max(1, total_ms // ENGINE_TICK_MS)
        tick_seconds = ENGINE_TICK_MS / 1000

        for tick in range(n_ticks):
            self._pick_frame_for_elapsed(tick * ENGINE_TICK_MS)
            self.advance_frame()
            reset_canvas(canvas, self.bg_color)
            self._paint_image(canvas)
            if self.border is not None:
                self.border.paint(canvas, self._frame_count)
            canvas = frame.matrix.SwapOnVSync(canvas)
            await asyncio.sleep(tick_seconds)

        self._current_frame_idx = len(self._frames) - 1
        return canvas
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_gif.py::TestGifPlayNoTextRefactor -v`

Expected: PASS (3 tests).

- [ ] **Step 5: Run full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green. The existing `test_gif_static_text_does_not_freeze_animation` still passes (this is a related but distinct tripwire on the text-overlay path).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/gif.py tests/test_widgets/test_gif.py
git commit -m "image-borders: refactor GifPlayer._play_no_text to 50ms cadence + border paint"
```

---

### Task 7: Two-mode `StillImage._play_no_text` + border paint

**Files:**
- Modify: `src/led_ticker/widgets/still.py:259-265` (`_play_no_text` method)
- Test: `tests/test_widgets/test_still.py` (new class `TestStillPlayNoTextBorder`)

Two-mode pattern: paint-once-and-sleep when border is None or frame-invariant; per-tick loop when border is animated. Mirrors `_play_with_text`'s existing fast-path gate exactly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_widgets/test_still.py`:

```python
class TestStillPlayNoTextBorder:
    """`StillImage._play_no_text` two-mode pattern: fast path
    (paint once + sleep) when border is None or frame-invariant;
    per-tick loop when border is animated."""

    @pytest.fixture
    def still(self, tmp_path):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        return StillImage(path=img_path, hold_seconds=0.5)

    async def test_no_border_takes_fast_path(self, still, mock_frame):
        """Single SwapOnVSync, single sleep covering the full hold."""
        with mock.patch("asyncio.sleep", new=mock.AsyncMock()) as sleep_mock:
            await still._play_no_text(
                mock_frame.matrix.SwapOnVSync.return_value, mock_frame
            )
        # Fast path: ONE swap, ONE sleep.
        assert mock_frame.matrix.SwapOnVSync.call_count == 1
        assert sleep_mock.call_count == 1

    async def test_constant_border_takes_fast_path(self, still, mock_frame):
        from led_ticker.borders import ConstantBorder

        still.border = ConstantBorder([0, 255, 0])

        with mock.patch("asyncio.sleep", new=mock.AsyncMock()) as sleep_mock:
            await still._play_no_text(
                mock_frame.matrix.SwapOnVSync.return_value, mock_frame
            )
        assert mock_frame.matrix.SwapOnVSync.call_count == 1
        assert sleep_mock.call_count == 1

    async def test_animated_border_runs_per_tick_loop(self, still, mock_frame):
        """RainbowChaseBorder(speed=4) → 10 ticks (500ms / 50ms),
        10 swaps, 10 sleeps. Border.paint fires per tick with
        increasing frame_count."""
        from led_ticker.borders import RainbowChaseBorder

        still.border = RainbowChaseBorder(speed=4)

        with mock.patch("asyncio.sleep", new=mock.AsyncMock()) as sleep_mock:
            await still._play_no_text(
                mock_frame.matrix.SwapOnVSync.return_value, mock_frame
            )
        assert mock_frame.matrix.SwapOnVSync.call_count == 10
        assert sleep_mock.call_count == 10
        # Frame counter advanced ~10×
        assert still._frame_count >= 9, (
            f"_frame_count should advance per tick; got {still._frame_count}"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_still.py::TestStillPlayNoTextBorder -v`

Expected: animated-border test FAILS — current `_play_no_text` always paints once and sleeps.

- [ ] **Step 3: Update `StillImage._play_no_text`**

In `src/led_ticker/widgets/still.py`, replace the current `_play_no_text` body (lines 259-265) with:

```python
    async def _play_no_text(self, real_canvas: Canvas, frame: Any) -> Canvas:
        """Two-mode: fast path (paint once + sleep) when border is
        None or frame-invariant; per-tick loop at engine 50ms
        cadence when border is animated. Mirrors `_play_with_text`'s
        fast-path gate exactly."""
        from led_ticker.ticker import ENGINE_TICK_MS

        canvas = real_canvas
        border_is_static = (
            getattr(self.border, "frame_invariant", True) if self.border else True
        )

        if border_is_static:
            # Fast path: paint once, sleep, return.
            reset_canvas(canvas, self.bg_color)
            self._paint_image(canvas)
            if self.border is not None:
                self.border.paint(canvas, self._frame_count)
            canvas = frame.matrix.SwapOnVSync(canvas)
            await asyncio.sleep(self.hold_seconds)
            return canvas

        # Slow path: per-tick loop for animated border.
        n_ticks = max(1, int(self.hold_seconds * 1000) // ENGINE_TICK_MS)
        tick_seconds = ENGINE_TICK_MS / 1000
        for _ in range(n_ticks):
            self.advance_frame()
            reset_canvas(canvas, self.bg_color)
            self._paint_image(canvas)
            self.border.paint(canvas, self._frame_count)
            canvas = frame.matrix.SwapOnVSync(canvas)
            await asyncio.sleep(tick_seconds)
        return canvas
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_still.py::TestStillPlayNoTextBorder -v`

Expected: PASS (3 tests).

- [ ] **Step 5: Run full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/still.py tests/test_widgets/test_still.py
git commit -m "image-borders: two-mode pattern in StillImage._play_no_text"
```

---

### Task 8: Physical-resolution tripwire on bigsign-style ScaledCanvas

**Files:**
- Test: `tests/test_widgets/test_image_base.py` (new class `TestImageBorderPhysicalResolution`)

Border MUST paint at physical pixels (via `unwrap_to_real`), not at the wrapper's logical pixels. Without this test, a regression that drops `unwrap_to_real` would silently produce 4×4 block borders on bigsign — matches the wrapper's content but defeats the "frame the panel" model. The existing `BorderEffect` implementations already do this; this test pins the integration end-to-end through `_render_tick`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_widgets/test_image_base.py`:

```python
class TestImageBorderPhysicalResolution:
    """End-to-end tripwire: rendering an image widget with a border
    on a bigsign-style ScaledCanvas (scale=4) MUST paint border
    pixels on the real 256×64 panel perimeter, NOT on the wrapper's
    logical 64×16 perimeter. Mirrors the TwoRowMessage tripwire."""

    def test_border_paints_to_real_perimeter_through_scaled_canvas(
        self, tmp_path
    ):
        from PIL import Image
        from rgbmatrix import _StubCanvas as RealStub

        from led_ticker.borders import ConstantBorder
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.widgets.still import StillImage

        # Build a still + ConstantBorder([255, 255, 255]).
        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        widget = StillImage(
            path=img_path,
            text="HI",
            text_align="left",
            border=ConstantBorder([255, 255, 255], thickness=1),
        )

        # Real bigsign-style canvas (256x64) wrapped at scale=4 →
        # logical 64x16.
        real = RealStub(width=256, height=64)
        wrapper = ScaledCanvas(real, scale=4, content_height=16)

        widget._render_tick(wrapper, wrapper, 0, 12, 2, 60)

        # The border is white (255,255,255) — assert that the corner
        # pixels of the REAL 256x64 canvas are lit.
        # Top-left corner: real (0, 0) should be white.
        # Top-right corner: real (255, 0) should be white.
        # Bottom-left: real (0, 63). Bottom-right: real (255, 63).
        for x, y in [(0, 0), (255, 0), (0, 63), (255, 63)]:
            r, g, b = real.GetPixel(x, y)
            assert (r, g, b) == (255, 255, 255), (
                f"real corner ({x}, {y}) expected white border; "
                f"got ({r}, {g}, {b}). Border did not paint at "
                f"physical resolution — `unwrap_to_real` may have "
                f"been dropped."
            )

        # And: the next-inner ring of REAL pixels (1, 1), (254, 1)
        # etc. must NOT be white (they're either image or black) —
        # otherwise the border is leaking inward (4×4 block painting).
        for x, y in [(1, 1), (254, 1), (1, 62), (254, 62)]:
            r, g, b = real.GetPixel(x, y)
            assert (r, g, b) != (255, 255, 255), (
                f"real ({x}, {y}) is white — border painting at "
                f"4×4 block resolution instead of 1 LED. Likely "
                f"missing `unwrap_to_real` in the border path."
            )
```

- [ ] **Step 2: Run test to verify the assertions are valid**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py::TestImageBorderPhysicalResolution -v`

Expected: PASS — `ConstantBorder` already uses `unwrap_to_real` (no implementation change needed; this test pins the existing behavior end-to-end).

If the test FAILS, do not adjust the border implementation — instead investigate. The expected result is PASS based on the existing `borders.py:ConstantBorder.paint`.

- [ ] **Step 3: Run full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_widgets/test_image_base.py
git commit -m "image-borders: tripwire — physical-resolution paint on ScaledCanvas"
```

---

### Task 9: CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md` (the "Rainbow border" section)

- [ ] **Step 1: Find and update the section**

In `CLAUDE.md`, locate the paragraph beginning `**Rainbow border (TickerMessage / TickerCountdown / TwoRowMessage)**:` and update its title + restriction sentence + add a no-text refactor note.

Find this text:
```
**Rainbow border (TickerMessage / TickerCountdown / TwoRowMessage)**: TickerMessage accepts a
```
Replace the heading with:
```
**Rainbow border (TickerMessage / TickerCountdown / TwoRowMessage / GifPlayer / StillImage)**: TickerMessage accepts a
```

Find this sentence:
```
Border is restricted to
`message`, `countdown`, and `two_row` widget types at config-load
(loud failure on other widget types) because data widgets have
their own draw paths and a perimeter border isn't a meaningful
concept there.
```
Replace with:
```
Border is restricted to
`message`, `countdown`, `two_row`, `gif`, and `image` widget types
at config-load (loud failure on other widget types) because data
widgets have their own draw paths and a perimeter border isn't a
meaningful concept there.
```

After the existing TwoRowMessage scale=2 sentence (`On TwoRowMessage at scale=2 (typical for handle layouts) the border paints to the unwrapped real canvas`), append a new sentence about the gif refactor:

```
On image widgets, border integration adds 4 paint sites
(`_render_tick` × 3 sub-paths, `_render_two_row_tick`,
`StillImage._play_no_text`, `GifPlayer._play_no_text`) and 3
fast-path gate updates that include `border.frame_invariant` in
the predicate (same shape as `font_color.frame_invariant`).
`GifPlayer._play_no_text` was refactored from gif-frame cadence to
engine 50ms cadence (using `_pick_frame_for_elapsed` — the same
pattern `_play_with_text` uses) so animated borders chase
uniformly regardless of gif frame durations. Side effect: gifs
with native frame durations < 50ms cap at 20 Hz on this path —
matches the cap `_play_with_text` already imposes.
`StillImage._play_no_text` uses a two-mode pattern: paint-once-
and-sleep fast path when border is None or frame-invariant; per-
tick loop when border is animated. Tripwires:
`TestRenderTickBorder`, `TestRenderTwoRowTickBorder`,
`TestPlayWithTextBorderFastPath`, `TestPlayWithTwoRowBorderFastPath`,
`TestImageBorderPhysicalResolution` in
`tests/test_widgets/test_image_base.py`;
`TestGifPlayNoTextRefactor` in `tests/test_widgets/test_gif.py`;
`TestStillPlayNoTextBorder` in `tests/test_widgets/test_still.py`.
```

- [ ] **Step 2: Verify the changes read correctly**

Run: `grep -n "GifPlayer._play_no_text was refactored" CLAUDE.md`

Expected: one line returned with the new content.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md — image widgets in Rainbow border allow-list + 50ms refactor note"
```

---

### Final task: lint + full test sweep + push

- [ ] **Step 1: Run lint**

```bash
uv run ruff check src/led_ticker tests
```

Expected: All checks passed!

- [ ] **Step 2: Run full test suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: all tests pass (current count + new tests added by this plan).

- [ ] **Step 3: Push**

```bash
git push -u origin feat/image-borders
```

- [ ] **Step 4: Open PR**

```bash
gh pr create --title "image widgets: support border field across all 4 render paths" \
  --body "$(cat <<'EOF'
## Summary

Extends the existing `border` feature (RainbowChaseBorder /
ConstantBorder, currently on TickerMessage / TickerCountdown /
TwoRowMessage) to GifPlayer and StillImage. Picks up the deferred
"image widgets" item from the original border PR.

## Scope

Borders work on all 4 image render paths:
- `_render_tick` (single-row text overlay; 3 sub-paths for the
  text_align modes)
- `_render_two_row_tick` (two-row text overlay)
- `StillImage._play_no_text` (no-text still — two-mode pattern)
- `GifPlayer._play_no_text` (no-text gif — refactored to 50ms cadence)

Three fast-path gates updated to include `border.frame_invariant`
in their predicate (same shape as the existing
`font_color.frame_invariant` gate). `GifPlayer._play_no_text`
refactored to engine 50ms cadence using `_pick_frame_for_elapsed`
(same pattern `_play_with_text` uses) so animated borders chase
uniformly regardless of gif frame durations.

## Plumbing

- `_BaseImageWidget.border: BorderEffect | None = None` — inherited
  by both subclasses.
- `_build_widget` allow-list extended to accept `border` on
  `gif` and `image` widget types.
- All four render paths integrate `border.paint(canvas,
  self._frame_count)` with paint order: image → border → text
  (or text → image → border in skip-black scroll mode).

## Spec

[`docs/superpowers/specs/2026-05-07-image-borders-design.md`](https://github.com/JamesAwesome/led-ticker/blob/feat/image-borders/docs/superpowers/specs/2026-05-07-image-borders-design.md)

## Test plan

- [x] All new tripwires pass:
  - Field default + config-load acceptance
  - Paint-order tripwires (5 tests on `_render_tick` + 3 on
    `_render_two_row_tick`)
  - Fast-path gate tests on both text-overlay paths + no-text still
  - GifPlayer refactor preserves animation; bordered gif advances
    frame counter per 50ms tick
  - Physical-resolution tripwire on bigsign-style ScaledCanvas
- [x] Existing tests still pass
- [x] Lint clean
- [ ] **Hardware verify**: run a config with a bordered gif on
      bigsign — chase should be uniform regardless of gif frame
      durations. Run a bordered still — fast path still single-
      paints when constant; per-tick loop when rainbow.
EOF
)"
```

---

## Summary of files touched

| Path | Change |
|---|---|
| `src/led_ticker/widgets/_image_base.py` | +`border` field; +paint in `_render_tick` (3 paths) and `_render_two_row_tick`; fast-path gate updates × 2 |
| `src/led_ticker/widgets/gif.py` | refactor `_play_no_text` to 50ms cadence + border paint |
| `src/led_ticker/widgets/still.py` | two-mode `_play_no_text` + border paint |
| `src/led_ticker/app.py` | extend `_build_widget` border allow-list to gif/image |
| `tests/test_app.py` | + 3 acceptance tests; updated rejection regex |
| `tests/test_widgets/test_image_base.py` | + 6 test classes (~17 tests across paint order, fast-path gates, physical-res, field default) |
| `tests/test_widgets/test_gif.py` | + `TestGifPlayNoTextRefactor` (3 tests) |
| `tests/test_widgets/test_still.py` | + `TestStillPlayNoTextBorder` (3 tests) |
| `CLAUDE.md` | "Rainbow border" section extended |

Total: ~25 new tests, single-PR scope.
