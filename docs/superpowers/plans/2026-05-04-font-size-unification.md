# Font-size Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the BDF `text_scale` knob with the HiresFont `font_size` knob into a single `font_size: int` (real pixels) on `_BaseImageWidget`, with a smart default for BDF on bigsign and a hard cutover (loud migration error) for stale configs.

**Architecture:** Single user-facing TOML knob `font_size` (real pixels). Internally, `_BaseImageWidget` computes a `_block_scale` for BDF from the resolved font_size at first paint via a new pure helper `block_scale_for_font_size(font, font_size)`. HiresFont keeps its required-explicit semantic. Smart default for BDF when `font_size` is unset: `cell_h × _logical_scale` (preserves bd61140 panel-scale behavior). `text_scale` is removed entirely; a `_build_widget`-level migration error catches any TOML still using it and tells the user the migration formula.

**Tech Stack:** Python 3.13 + asyncio + attrs + Pillow, RGB LED matrix toolkit. Tests run via `make test` (sets `PYTHONPATH=tests/stubs`). Hard cutover; personal repo so direct-to-main is authorized.

---

## File Structure

**Created:**
- (no new files; helper added to existing `fonts/__init__.py`)

**Modified:**
- `src/led_ticker/fonts/__init__.py` — add `block_scale_for_font_size` helper
- `src/led_ticker/widgets/_image_base.py` — replace `text_scale` field with `font_size`, add `_resolved_font_size` method, update `_play_with_text` and validation
- `src/led_ticker/widgets/gif.py` — schema table in docstring (replace `text_scale` row with `font_size`)
- `src/led_ticker/widgets/still.py` — same docstring update as gif.py
- `src/led_ticker/app.py` — `_build_widget` migration error for `text_scale`, drop `DEFAULT_HIRES_SIZE` fallback
- `config/config.gif_text.example.toml` — migrate 3 `text_scale` lines to `font_size`
- `config/config.gif_test.example.toml` — migrate 2 `text_scale` lines
- `config/config.image_test.example.toml` — migrate 4 `text_scale` lines
- `tests/test_fonts.py` — add `TestBlockScaleForFontSize` class
- `tests/test_widgets/test_image_base.py` — rename `TestSingleRowLogicalScaleWrap` → `TestSingleRowFontSize`, swap test inputs from `text_scale` to `font_size`
- `tests/test_app.py` — add `TestFontSizeMigration` class
- `CLAUDE.md` — replace bd61140 paragraph's `effective_scale` formula with `font_size` rule + migration formula

**Audited migration values (cell_h confirmed for each font via `font_line_height`):**
- BDF FONT_DEFAULT (6×12): cell_h = 12 → `text_scale = 2` becomes `font_size = 24`, `text_scale = 4` becomes `font_size = 48`
- BDF FONT_SMALL (5×8): cell_h = 8 → `text_scale = 2` becomes `font_size = 16`, `text_scale = 4` becomes `font_size = 32`

All `text_scale` lines in the in-tree configs are with default BDF (no `font = "5x8"` adjacent), so cell_h = 12 throughout the migration.

---

## Task 1: Add `block_scale_for_font_size` helper

Pure function that maps `(font, font_size)` to the integer block scale used by `ScaledCanvas`. For BDF: round-down to integer multiples of cell height; raise if below floor. For HiresFont: always 1 (the rasterizer handles size at construction).

**Files:**
- Modify: `src/led_ticker/fonts/__init__.py` (add helper after `font_line_height_logical`)
- Test: `tests/test_fonts.py` (new `TestBlockScaleForFontSize` class at end)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fonts.py`:

```python
class TestBlockScaleForFontSize:
    """`block_scale_for_font_size(font, font_size)` returns the integer
    block scale used by `ScaledCanvas` for BDF fonts. HiresFont always
    returns 1 (its rasterizer handles size at construction)."""

    def test_bdf_exact_multiple_returns_scale(self):
        from led_ticker.fonts import FONT_DEFAULT, block_scale_for_font_size

        # 6x12 cell — cell_h = 12
        assert block_scale_for_font_size(FONT_DEFAULT, 12) == 1
        assert block_scale_for_font_size(FONT_DEFAULT, 24) == 2
        assert block_scale_for_font_size(FONT_DEFAULT, 36) == 3
        assert block_scale_for_font_size(FONT_DEFAULT, 48) == 4

    def test_bdf_round_down_to_nearest_multiple(self):
        from led_ticker.fonts import FONT_DEFAULT, block_scale_for_font_size

        # 25 → 24 (scale 2); 47 → 36 (scale 3)
        assert block_scale_for_font_size(FONT_DEFAULT, 25) == 2
        assert block_scale_for_font_size(FONT_DEFAULT, 47) == 3

    def test_bdf_below_cell_height_raises(self):
        from led_ticker.fonts import FONT_DEFAULT, block_scale_for_font_size

        with pytest.raises(ValueError, match="below cell height"):
            block_scale_for_font_size(FONT_DEFAULT, 11)

    def test_bdf_small_font_uses_smaller_cell(self):
        from led_ticker.fonts import FONT_SMALL, block_scale_for_font_size

        # 5x8 cell — cell_h = 8
        assert block_scale_for_font_size(FONT_SMALL, 8) == 1
        assert block_scale_for_font_size(FONT_SMALL, 16) == 2
        # font_size = 7 < 8 → raises
        with pytest.raises(ValueError, match="below cell height"):
            block_scale_for_font_size(FONT_SMALL, 7)

    def test_hires_returns_one_regardless_of_font_size(self):
        from led_ticker.fonts import block_scale_for_font_size, resolve_font

        font = resolve_font("Inter-Regular", 24)
        assert block_scale_for_font_size(font, 24) == 1
        # HiresFont's rasterizer handled the size at construction; the
        # block_scale is always 1 (no wrap-based expansion needed).
        assert block_scale_for_font_size(font, 48) == 1
        assert block_scale_for_font_size(font, 12) == 1

    def test_bdf_zero_or_negative_raises(self):
        from led_ticker.fonts import FONT_DEFAULT, block_scale_for_font_size

        with pytest.raises(ValueError, match="must be > 0"):
            block_scale_for_font_size(FONT_DEFAULT, 0)
        with pytest.raises(ValueError, match="must be > 0"):
            block_scale_for_font_size(FONT_DEFAULT, -5)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_fonts.py::TestBlockScaleForFontSize -v
```

Expected: 6 FAILs with `ImportError` (block_scale_for_font_size not defined yet).

- [ ] **Step 3: Implement the helper**

Edit `src/led_ticker/fonts/__init__.py`. Add at the end of the file (after `font_line_height_logical`):

```python
def block_scale_for_font_size(font: Font | HiresFont, font_size: int) -> int:
    """Return the integer block scale to wrap the canvas at, given a
    target `font_size` in real pixels.

    For BDF: cells are bitmaps; the wrapper block-expands them by the
    returned scale. We round down `font_size` to the nearest integer
    multiple of the font's cell height. Floor: the BDF cell can't
    render below its natural height, so `font_size < cell_h` raises
    with a hint pointing at smaller bundled BDFs.

    For HiresFont: always returns 1. HiresFont rasterizes at the real
    `font_size` at construction time and paints to the unwrapped real
    canvas, so the wrapper has no glyph-size impact.

    Raises ValueError on `font_size <= 0` or BDF `font_size < cell_h`.
    """
    if font_size <= 0:
        raise ValueError(f"font_size must be > 0; got {font_size!r}.")

    if isinstance(font, HiresFont):
        return 1

    cell_h = font_line_height(font)
    if font_size < cell_h:
        raise ValueError(
            f"font_size={font_size} below cell height {cell_h} for BDF "
            f"font. For smaller text use BDF '5x8' (cell_h=8) or a "
            f"HiresFont."
        )
    return font_size // cell_h
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_fonts.py::TestBlockScaleForFontSize -v
```

Expected: 6 PASS.

- [ ] **Step 5: Run the full suite to confirm nothing else broke**

```bash
uv run pytest -q
```

Expected: 1066+ passing (the new 6 add to the existing 1066).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/fonts/__init__.py tests/test_fonts.py
git commit -m "$(cat <<'EOF'
fonts: add block_scale_for_font_size helper

Pure function mapping (font, font_size) → integer block scale for
ScaledCanvas wrapping. For BDF: round-down to integer multiples of
cell_h, raise if below floor. For HiresFont: always 1 (rasterizer
handled size at construction, wrapper has no glyph-size impact).

Foundation for the upcoming font_size unification — replaces the
text_scale knob with a real-pixel font_size that works uniformly
across font types.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add `font_size` field + `_resolved_font_size` method on `_BaseImageWidget`

Add the new field alongside the existing `text_scale` (additive — both fields exist temporarily). The smart-default lives in `_resolved_font_size` and reads `_logical_scale`.

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py` (add field + method)
- Test: `tests/test_widgets/test_image_base.py` (new `TestResolvedFontSize` class)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_widgets/test_image_base.py` after `TestSingleRowLogicalScaleWrap`:

```python
class TestResolvedFontSize:
    """`_resolved_font_size()` is the smart-default hook. If
    `self.font_size` is set, it returns as-is. If None, BDF returns
    `cell_h × _logical_scale`; HiresFont returns its already-baked
    natural size (font.font_size attribute on HiresFont, or
    line_height for BDF as a back-stop)."""

    def test_explicit_font_size_returned_as_is(self):
        from led_ticker.fonts import FONT_DEFAULT

        w = _DummyImage(font=FONT_DEFAULT, font_size=24)
        assert w._resolved_font_size() == 24

    def test_bdf_smart_default_uses_cell_times_logical_scale(self):
        """BDF + `font_size=None` + bigsign (_logical_scale=4) →
        12 × 4 = 48 real px. Preserves bd61140 panel-scale behavior
        in the new vocabulary."""
        from led_ticker.fonts import FONT_DEFAULT

        w = _DummyImage(font=FONT_DEFAULT, font_size=None)
        w._logical_scale = 4
        assert w._resolved_font_size() == 48

    def test_bdf_smart_default_on_small_sign(self):
        """BDF + `font_size=None` + small sign (_logical_scale=1) →
        12 × 1 = 12 real px. Native BDF, no block-expansion."""
        from led_ticker.fonts import FONT_DEFAULT

        w = _DummyImage(font=FONT_DEFAULT, font_size=None)
        w._logical_scale = 1
        assert w._resolved_font_size() == 12

    def test_hires_uses_font_internal_size(self):
        """HiresFont's `font_size` is set at construction (from
        rasterizer target). When the widget's `self.font_size` is
        None, fall back to the HiresFont's own `font_size` attr."""
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        w = _DummyImage(font=font, font_size=None)
        w._logical_scale = 4
        # HiresFont remembers its rasterized size; that's the natural
        # default if the widget didn't get an explicit override.
        assert w._resolved_font_size() == 24

    def test_explicit_font_size_overrides_hires_natural_size(self):
        """Even with HiresFont, an explicit `font_size` on the widget
        takes precedence (rare — usually equal — but allowed)."""
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        w = _DummyImage(font=font, font_size=32)
        assert w._resolved_font_size() == 32

    def test_construction_rejects_zero_font_size(self):
        """`font_size = 0` is rejected at construction (validation
        layer, separate from the helper's same check)."""
        import pytest

        from led_ticker.fonts import FONT_DEFAULT

        with pytest.raises(ValueError, match="font_size must be > 0"):
            _DummyImage(font=FONT_DEFAULT, font_size=0)

    def test_construction_rejects_negative_font_size(self):
        import pytest

        from led_ticker.fonts import FONT_DEFAULT

        with pytest.raises(ValueError, match="font_size must be > 0"):
            _DummyImage(font=FONT_DEFAULT, font_size=-5)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_widgets/test_image_base.py::TestResolvedFontSize -v
```

Expected: 7 FAILs (`font_size` is not a valid kwarg yet, `_resolved_font_size` undefined).

- [ ] **Step 3: Add the field, method, and validation**

Edit `src/led_ticker/widgets/_image_base.py`. Find the existing `text_scale` field (around line 90) and add `font_size` alongside it:

```python
    text_scale: int = attrs.field(default=1, kw_only=True)
    text_loops: int = attrs.field(default=0, kw_only=True)
    # Real-pixel size knob — unifies BDF (block-scales via the wrapper)
    # and HiresFont (rasterizer target). None = smart default at first
    # paint (BDF: cell_h × _logical_scale). HiresFont with None falls
    # back to the font's natural size baked in at construction.
    font_size: int | None = attrs.field(default=None, kw_only=True)
```

Add the validation in `_validate_common`. Find the existing `text_scale < 1` check and add the `font_size` check right after it:

```python
        if self.text_scale < 1:
            raise ValueError(f"text_scale must be >= 1, got {self.text_scale!r}")
        if self.font_size is not None and self.font_size <= 0:
            raise ValueError(
                f"font_size must be > 0; got {self.font_size!r}."
            )
```

Add the `_resolved_font_size` method. Place it next to the `_has_text_content` method (around line 340):

```python
    def _resolved_font_size(self) -> int:
        """Return the effective font_size in real pixels. Hot-path
        method (called once per visit, cached in a local).

        If `self.font_size` is set, returned as-is. Otherwise:
        - BDF: `cell_h × _logical_scale` (smart default that preserves
          bd61140 panel-scale behavior).
        - HiresFont: the font's own `font_size` attribute (set by the
          loader at construction time).
        """
        if self.font_size is not None:
            return self.font_size
        if isinstance(self.font, _HiresFont):
            return self.font.font_size
        # BDF: smart default = cell_h × _logical_scale.
        cell_h = font_line_height(self.font)
        return cell_h * self._logical_scale
```

You'll also need to add `font_line_height` to the imports if not already there. Check the existing import line near the top:

```python
from led_ticker.fonts import FONT_DEFAULT, font_line_height_logical
```

Update to:

```python
from led_ticker.fonts import FONT_DEFAULT, font_line_height, font_line_height_logical
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_widgets/test_image_base.py::TestResolvedFontSize -v
```

Expected: 7 PASS.

- [ ] **Step 5: Run the full suite to confirm nothing else broke**

```bash
uv run pytest -q
```

Expected: 1073+ passing.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_base.py
git commit -m "$(cat <<'EOF'
_BaseImageWidget: add font_size field + _resolved_font_size method

Additive: font_size lives alongside text_scale temporarily until the
playback loop is wired (Task 3) and configs are migrated (Task 5).
Smart default for BDF: cell_h × _logical_scale at first paint (none
needed for HiresFont — its rasterized size is baked in at construction).

Validation: font_size > 0 if set. Tests cover explicit values, smart
default for both panel sizes, HiresFont fallback, override.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Wire `_play_with_text` to use `font_size` instead of `text_scale`

Replace the `effective_scale = max(text_scale, _logical_scale)` formula with `block_scale = block_scale_for_font_size(self.font, self._resolved_font_size())`. The old `text_scale` field still exists at this point but stops being read by the playback loop.

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py` (`_play_with_text` method, around line 540)
- Modify: `tests/test_widgets/test_image_base.py` (rename existing tests in `TestSingleRowLogicalScaleWrap` to use `font_size`)

- [ ] **Step 1: Write the new tests (additive — old `TestSingleRowLogicalScaleWrap` stays for now)**

Append to `tests/test_widgets/test_image_base.py` after `TestResolvedFontSize`:

```python
class TestSingleRowFontSize:
    """`_play_with_text` derives the wrap scale from `font_size` via
    `block_scale_for_font_size`. Smart default: BDF + `font_size=None`
    on bigsign wraps at scale=`_logical_scale`; small sign no wrap;
    explicit `font_size` honored exactly."""

    async def test_bdf_default_wraps_at_logical_scale_on_bigsign(
        self, swapping_frame
    ):
        """BDF + `font_size=None` (smart default) + bigsign → wraps at
        scale=4. Same observable behavior as the old `text_scale=1`
        path post-bd61140."""
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.scaled_canvas import ScaledCanvas

        w = _DummyImage(text="hi", font=FONT_DEFAULT, font_size=None)
        w._logical_scale = 4

        captured: list = []
        orig = _BaseImageWidget._render_tick

        def spy(self, canvas, text_canvas, *args):
            captured.append(
                {
                    "is_wrapped": isinstance(text_canvas, ScaledCanvas),
                    "scale": getattr(text_canvas, "scale", None),
                }
            )
            return orig(self, canvas, text_canvas, *args)

        _BaseImageWidget._render_tick = spy  # type: ignore[method-assign]
        real = _StubCanvas(width=256, height=64)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=256, height=64
        )

        try:
            await w._play_with_text(real, swapping_frame, n_ticks=1)
        finally:
            _BaseImageWidget._render_tick = orig  # type: ignore[method-assign]

        assert len(captured) >= 1
        assert all(c["is_wrapped"] for c in captured)
        assert all(c["scale"] == 4 for c in captured), (
            f"Expected wrapper at logical-scale (4); got {captured!r}"
        )

    async def test_explicit_font_size_24_wraps_at_2(self, swapping_frame):
        """Explicit `font_size=24` with BDF 6×12 on bigsign → block
        scale = 24 // 12 = 2. User intent honored over `_logical_scale`."""
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.scaled_canvas import ScaledCanvas

        w = _DummyImage(text="hi", font=FONT_DEFAULT, font_size=24)
        w._logical_scale = 4

        captured: list = []
        orig = _BaseImageWidget._render_tick

        def spy(self, canvas, text_canvas, *args):
            if isinstance(text_canvas, ScaledCanvas):
                captured.append(text_canvas.scale)
            return orig(self, canvas, text_canvas, *args)

        _BaseImageWidget._render_tick = spy  # type: ignore[method-assign]
        real = _StubCanvas(width=256, height=64)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=256, height=64
        )

        try:
            await w._play_with_text(real, swapping_frame, n_ticks=1)
        finally:
            _BaseImageWidget._render_tick = orig  # type: ignore[method-assign]

        assert captured, "Wrapper not used"
        assert all(s == 2 for s in captured), (
            f"Expected wrapper.scale=2 (24px / 12px cell); got {captured!r}"
        )

    async def test_no_wrap_on_small_sign_with_default(self, swapping_frame):
        """Small sign (`_logical_scale=1`) + BDF + `font_size=None` →
        block scale = 12 // 12 = 1 → no wrap."""
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.scaled_canvas import ScaledCanvas

        w = _DummyImage(text="hi", font=FONT_DEFAULT, font_size=None)
        w._logical_scale = 1

        captured: list = []
        orig = _BaseImageWidget._render_tick

        def spy(self, canvas, text_canvas, *args):
            captured.append(isinstance(text_canvas, ScaledCanvas))
            return orig(self, canvas, text_canvas, *args)

        _BaseImageWidget._render_tick = spy  # type: ignore[method-assign]
        real = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        try:
            await w._play_with_text(real, swapping_frame, n_ticks=1)
        finally:
            _BaseImageWidget._render_tick = orig  # type: ignore[method-assign]

        assert len(captured) >= 1, "_render_tick was never called"
        assert not any(captured), (
            f"Expected NO wrap at scale=1; got {captured!r}"
        )
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
uv run pytest tests/test_widgets/test_image_base.py::TestSingleRowFontSize -v
```

Expected: FAILs (the wrap math still uses `text_scale`, so explicit `font_size=24` doesn't yet result in scale=2).

- [ ] **Step 3: Rewrite `_play_with_text`'s wrap-scale resolution**

Edit `src/led_ticker/widgets/_image_base.py`. Find the section in `_play_with_text` that computes `effective_scale` (around line 543):

```python
        effective_scale = (
            self.text_scale if self.text_scale > 1 else self._logical_scale
        )
        text_canvas: Canvas = self._wrap_for_text(canvas, effective_scale)
```

Replace with:

```python
        # Resolve the wrap scale. Two concerns share this knob:
        #   - BDF glyph size: the wrapper block-expands BDF cells by
        #     `wrap_scale`, so it must equal `block_scale_for_font_size`.
        #   - Hi-res emoji gate: `pixel_emoji.draw_with_emoji` checks
        #     `isinstance(canvas, ScaledCanvas)` to decide whether to
        #     paint hires sprites. Any wrap > 1 satisfies it.
        # For BDF: `block_scale` handles both (wraps the cell to match
        # font_size; emoji gate fires if scale > 1).
        # For HiresFont: glyphs paint to the unwrapped real canvas via
        # `_draw_hires_text` regardless of wrap; `block_scale` is always
        # 1 (no glyph effect). Wrap at `_logical_scale` so the emoji
        # gate fires on bigsign — that's the whole point of this path.
        font_size = self._resolved_font_size()
        block_scale = block_scale_for_font_size(self.font, font_size)
        wrap_scale = (
            self._logical_scale
            if isinstance(self.font, _HiresFont)
            else block_scale
        )
        text_canvas: Canvas = self._wrap_for_text(canvas, wrap_scale)
```

Add `block_scale_for_font_size` to the imports near the top of the file. Find:

```python
from led_ticker.fonts import FONT_DEFAULT, font_line_height, font_line_height_logical
```

Update to:

```python
from led_ticker.fonts import (
    FONT_DEFAULT,
    block_scale_for_font_size,
    font_line_height,
    font_line_height_logical,
)
```

The error message in the rows-fit check (around line 567) still references `text_scale`:

```python
        if text_h < font_lh_logical:
            raise ValueError(
                f"effective_scale={effective_scale} (text_scale="
                f"{self.text_scale}, section logical scale="
                f"{self._logical_scale}) leaves text_canvas only "
                f"{text_h} rows on a {canvas.height}-tall panel — font "
                f"requires {font_lh_logical} logical rows. Reduce "
                f"text_scale, pick a smaller font_size, or use a taller "
                f"panel."
            )
```

Update to use the new vocabulary:

```python
        if text_h < font_lh_logical:
            raise ValueError(
                f"font_size={font_size} (block_scale={block_scale}, "
                f"section logical scale={self._logical_scale}) leaves "
                f"text_canvas only {text_h} rows on a {canvas.height}-tall "
                f"panel — font requires {font_lh_logical} logical rows. "
                f"Reduce font_size or use a taller panel."
            )
```

**NOTE for the implementer:** existing tests in `tests/test_widgets/test_gif.py` and `tests/test_widgets/test_still.py` that pass `text_scale=2` to widgets and assert wrap-scale behavior become invalid in this task — `_play_with_text` no longer reads `text_scale`. Update those tests to either: (a) drop `text_scale=2` and explicitly set `widget._logical_scale = 4` to simulate bigsign, OR (b) leave them with `text_scale=2` and update the assertion to expect the smart-default path (block_scale derived from `_resolved_font_size`). The expedient choice is (a). The corollary test updates are part of T3.

- [ ] **Step 4: Run new tests to verify they pass**

```bash
uv run pytest tests/test_widgets/test_image_base.py::TestSingleRowFontSize -v
```

Expected: 3 PASS.

- [ ] **Step 5: Run the full suite — old `TestSingleRowLogicalScaleWrap` may still pass since it uses `text_scale=1` (default); confirm**

```bash
uv run pytest -q
```

Expected: 1076+ passing. The old `text_scale`-based tests still pass because `text_scale` field still exists (we removed it from the playback math but not the field itself).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_base.py
git commit -m "$(cat <<'EOF'
_play_with_text: derive wrap scale from font_size

Replace the `effective_scale = max(text_scale, _logical_scale)` formula
with `block_scale = block_scale_for_font_size(font, _resolved_font_size())`.
text_scale field still exists but no longer drives the playback loop —
it'll be removed in Task 6 once configs are migrated.

Error message updated to reference font_size + block_scale instead of
text_scale + effective_scale.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add migration error in `_build_widget` for stale `text_scale`

Detect `text_scale` keyword in the widget config dict and raise a `ValueError` with the migration formula. This catches stale configs at config-load time, before the widget is instantiated. Lands BEFORE example-config migration (Task 5) so the error is in place when those configs change shape.

**Files:**
- Modify: `src/led_ticker/app.py` (`_build_widget`, around line 100)
- Test: `tests/test_app.py` (new `TestFontSizeMigration` class)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:

```python
class TestFontSizeMigration:
    """`_build_widget` rejects stale `text_scale` configs with a clear
    migration message. Loud failure at config-load (vs. silent ignore
    or TypeError at construction)."""

    async def test_text_scale_in_config_raises_migration_error(self, tmp_path):
        """Any `text_scale` key in a widget config dict triggers the
        migration error. Message includes the conversion formula."""
        import io

        import aiohttp
        import pytest
        from PIL import Image

        from led_ticker.app import _build_widget

        # Real on-disk gif so path resolution doesn't error first.
        gif_path = tmp_path / "tiny.gif"
        Image.new("RGB", (4, 4)).save(gif_path, format="GIF")

        cfg = {
            "type": "gif",
            "path": str(gif_path),
            "fit": "stretch",
            "text": "hi",
            "text_scale": 4,
        }

        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError, match="text_scale removed"):
                await _build_widget(cfg, s, config_dir=tmp_path)

    async def test_migration_message_includes_conversion_formula(
        self, tmp_path
    ):
        """The error message must tell the user *how* to migrate, not
        just that they need to. Formula: font_size = N × cell_h."""
        import io

        import aiohttp
        import pytest
        from PIL import Image

        from led_ticker.app import _build_widget

        gif_path = tmp_path / "tiny.gif"
        Image.new("RGB", (4, 4)).save(gif_path, format="GIF")

        cfg = {
            "type": "gif",
            "path": str(gif_path),
            "fit": "stretch",
            "text": "hi",
            "text_scale": 2,
        }

        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError) as exc_info:
                await _build_widget(cfg, s, config_dir=tmp_path)

        msg = str(exc_info.value)
        # Must include the formula and concrete examples.
        assert "font_size" in msg
        assert "cell_h" in msg or "cell height" in msg
        assert "× 12" in msg or "* 12" in msg or "12" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_app.py::TestFontSizeMigration -v
```

Expected: 2 FAILs (no migration error raised yet — `text_scale` still works).

- [ ] **Step 3: Add the migration check in `_build_widget`**

Edit `src/led_ticker/app.py`. Find the start of `_build_widget`'s body (after the docstring, around line 103):

```python
    widget_type = widget_cfg.pop("type")
    cls = get_widget_class(widget_type)
```

Add the migration check right BEFORE the widget_type pop (so it fires on all widget types, not just instantiated ones):

```python
    # Migration check: text_scale was the BDF block-expansion knob.
    # Replaced by font_size (real pixels) which works uniformly for
    # BDF and HiresFont. Loud failure here catches stale TOMLs at
    # load time rather than letting them silently render wrong.
    if "text_scale" in widget_cfg:
        raise ValueError(
            "text_scale removed in favor of font_size (real pixels). "
            "Migrate: font_size = N × cell_h_of_your_font. "
            "For BDF 6×12: font_size = N × 12 (e.g. text_scale=2 → "
            "font_size=24, text_scale=4 → font_size=48). "
            "For BDF 5×8: font_size = N × 8."
        )

    widget_type = widget_cfg.pop("type")
    cls = get_widget_class(widget_type)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_app.py::TestFontSizeMigration -v
```

Expected: 2 PASS.

- [ ] **Step 5: Run the full suite — note that this WILL break tests that load configs containing `text_scale`. The example configs we migrate in Task 5 still use `text_scale` at this point, so any test loading them fails. Audit:**

```bash
uv run pytest -q 2>&1 | tail -10
```

Expected: 1078+ passing. We confirmed earlier that `tests/` doesn't load `gif_text/gif_test/image_test` example configs — only `bigsign` and `moonbunny`, neither of which use `text_scale`. So no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app.py tests/test_app.py
git commit -m "$(cat <<'EOF'
_build_widget: migration error for stale text_scale configs

text_scale is being replaced by font_size (real pixels). Catch any
config that still uses text_scale at config-load and raise with the
conversion formula (font_size = N × cell_h) so users know exactly how
to migrate.

Lands before the example configs are migrated (Task 5) so the safety
net is in place during the cutover. Audited: no test loads any of the
3 in-tree configs that currently use text_scale.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Migrate in-tree example configs

Mechanical replacement: `text_scale = N` → `font_size = N × 12` (cell_h confirmed = 12 for default BDF in all sites; no FONT_SMALL adjacent uses). Three files, 11 occurrences total (2 in gif_text + 4 in image_test + 5 in gif_test).

**Files:**
- Modify: `config/config.gif_text.example.toml`
- Modify: `config/config.gif_test.example.toml`
- Modify: `config/config.image_test.example.toml`

- [ ] **Step 1: Update `config.gif_text.example.toml`**

Find lines containing `text_scale = ` (uncomment-only — comments mentioning `text_scale` are documentation references and stay):

Line containing `text_scale = 2` (Section 3 — TRANS RIGHTS):

```toml
text_scale = 2
```

Replace with:

```toml
font_size = 24
```

Line containing `text_scale = 4` (Section 4 — HAPPY PRIDE emoji):

```toml
text_scale = 4
```

Replace with:

```toml
font_size = 48
```

Line containing `text_scale = 2` (Section 5 — kpop dance):

```toml
text_scale = 2
```

Replace with:

```toml
font_size = 24
```

Update the comment in Section 4 that references `text_scale = 4`:

Find:

```
# pride.gif backdrop with white ":heart: HAPPY PRIDE :heart:" scrolling
# over it. `:slug:` tokens render as inline pixel-art sprites (not as
# literal text); `text_scale = 4` block-expands each glyph pixel so
# text fills ~75% of panel height — readable from across a room.
```

Replace with:

```
# pride.gif backdrop with white ":heart: HAPPY PRIDE :heart:" scrolling
# over it. `:slug:` tokens render as inline pixel-art sprites (not as
# literal text); `font_size = 48` block-expands each glyph pixel (BDF
# 6×12 cell × 4) so text fills ~75% of panel height — readable from
# across a room.
```

Update the Section 1 comment that references `text_scale = 1`:

Find:

```
# Text size: explicit `font = "Inter-Bold"` + `font_size = 24` keeps
# "PIKACHU!" sharp at ~24 real px tall × ~110 wide — sits cleanly in
# the right pillar. With default BDF on bigsign, `text_scale = 1`
# now means panel-scale (= the section's logical scale = 4), which
# would render "PIKACHU!" at ~192 wide and bleed into Pikachu's body.
# To get tiny native-12-px text on bigsign, opt in via HiresFont with
# `font_size = 12`.
```

Replace with:

```
# Text size: explicit `font = "Inter-Bold"` + `font_size = 24` keeps
# "PIKACHU!" sharp at ~24 real px tall × ~110 wide — sits cleanly in
# the right pillar. With default BDF on bigsign, omitting `font_size`
# defaults to panel-scale (cell_h × _logical_scale = 48), which would
# render "PIKACHU!" at ~192 wide and bleed into Pikachu's body. To get
# tiny native-12-px text on bigsign, opt in via HiresFont with
# `font_size = 12`.
```

- [ ] **Step 2: Update `config.gif_test.example.toml`**

Run a grep first to enumerate `text_scale` lines:

```bash
grep -n "^text_scale\|^  text_scale\|^    text_scale" config/config.gif_test.example.toml
```

For each line returned, apply the conversion:
- `text_scale = 2` → `font_size = 24`
- `text_scale = 4` → `font_size = 48`

Comment-line references to `text_scale` (lines starting with `#`) get rewritten to mention `font_size` and the equivalent value. Specifically:

Find:

```
# bump up so the cutout is actually readable
```

(adjacent to the `text_scale = 2` line)

Leave the comment; replace only the live config line.

Find:

```
# Demonstrates `text_scale = 4` (text painted via a ScaledCanvas wrapper
```

Replace with:

```
# Demonstrates `font_size = 48` (text painted via a ScaledCanvas wrapper
```

Find:

```
# inline `:slug:` emoji rendering. Without text_scale the BDF glyphs
```

Replace with:

```
# inline `:slug:` emoji rendering. Without font_size the BDF glyphs
```

Find:

```
# With text_scale=4 the same font fills 75% of the panel height.
```

Replace with:

```
# With font_size=48 the same font fills 75% of the panel height.
```

- [ ] **Step 3: Update `config.image_test.example.toml`**

Apply the same conversion:

```bash
grep -n "^text_scale\|^  text_scale\|^    text_scale" config/config.image_test.example.toml
```

For each line returned:
- `text_scale = 2` → `font_size = 24`
- `text_scale = 4` → `font_size = 48`

Comment line referencing `text_scale=2` (above the live `text_scale = 2`):

Find:

```
# letters cut a "knockout" through the heart-tunnel image. text_scale=2
```

Replace with:

```
# letters cut a "knockout" through the heart-tunnel image. font_size=24
```

- [ ] **Step 4: Verify all configs parse**

```bash
uv run python -c "
import tomllib
for p in ['config/config.gif_text.example.toml',
         'config/config.gif_test.example.toml',
         'config/config.image_test.example.toml']:
    cfg = tomllib.loads(open(p).read())
    n = len(cfg['playlist']['section'])
    print(f'{p}: {n} sections, parses OK')
"
```

Expected output: 3 lines, each saying "parses OK".

- [ ] **Step 5: Run the full suite**

```bash
uv run pytest -q
```

Expected: 1078+ passing.

- [ ] **Step 6: Verify no live `text_scale` lines remain in any config**

```bash
grep -rn "^text_scale\|^  text_scale\|^    text_scale" config/*.toml
```

Expected: empty output. Comment references (`# ... text_scale ...`) are tolerated; live config keys are not.

- [ ] **Step 7: Commit**

```bash
git add config/config.gif_text.example.toml config/config.gif_test.example.toml config/config.image_test.example.toml
git commit -m "$(cat <<'EOF'
gif/image example configs: migrate text_scale → font_size

Mechanical conversion using `font_size = N × cell_h` (cell_h = 12 for
all in-tree uses since they all use default BDF FONT_DEFAULT 6×12):
- text_scale = 2 → font_size = 24
- text_scale = 4 → font_size = 48

11 live config-key occurrences updated across:
- config.gif_text.example.toml (3)
- config.gif_test.example.toml (3)
- config.image_test.example.toml (5)

Comment references rewritten in the same pass for vocabulary
consistency. The migration error in _build_widget (Task 4) catches
any out-of-tree configs still using the old knob.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Remove `text_scale` field + drop related validation

Now safe to remove the field from `_BaseImageWidget`. Any config using `text_scale` would have been caught by the migration error in Task 4, so the field is purely vestigial.

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py` (remove field + validation)
- Modify: `tests/test_widgets/test_image_base.py` (delete obsolete `text_scale` tests)

- [ ] **Step 1: Identify the obsolete tests**

```bash
grep -n "text_scale" tests/test_widgets/test_image_base.py
```

Expected hits in:
- `TestFieldSurface.USER_FACING_FIELDS` (set entry `"text_scale"`)
- `TestFieldSurface.test_dummy_image_constructs_with_every_user_kwarg` (kwarg `text_scale=1`)
- `TestHiresFontTextScaleRejection` (entire class — `text_scale > 1 with HiresFont` rejection)
- `TestSingleRowLogicalScaleWrap.test_user_text_scale_still_honored` (the explicit-text_scale test)
- Any test in `TestTwoRowMode` referencing `text_scale=2 raises`

Each gets removed or rewritten in this task.

- [ ] **Step 2: Update `TestFieldSurface` to drop text_scale**

In `tests/test_widgets/test_image_base.py`, find the `USER_FACING_FIELDS` set:

```python
    USER_FACING_FIELDS = {
        "text",
        "text_align",
        "text_valign",
        "text_y_offset",
        "text_x_offset",
        "scroll_direction",
        "font_color",
        "bg_color",
        "scroll_speed_ms",
        "text_scale",
        "text_loops",
        "font",
    }
```

Replace `"text_scale"` with `"font_size"`:

```python
    USER_FACING_FIELDS = {
        "text",
        "text_align",
        "text_valign",
        "text_y_offset",
        "text_x_offset",
        "scroll_direction",
        "font_color",
        "bg_color",
        "scroll_speed_ms",
        "font_size",
        "text_loops",
        "font",
    }
```

Find `test_dummy_image_constructs_with_every_user_kwarg`:

```python
        _DummyImage(
            text="hi",
            text_align="left",
            text_valign="top",
            text_y_offset=2,
            text_x_offset=3,
            scroll_direction="left",
            bg_color=None,
            scroll_speed_ms=50,
            text_scale=1,
            text_loops=0,
            font=FONT_DEFAULT,
        )
```

Replace `text_scale=1` with `font_size=24`:

```python
        _DummyImage(
            text="hi",
            text_align="left",
            text_valign="top",
            text_y_offset=2,
            text_x_offset=3,
            scroll_direction="left",
            bg_color=None,
            scroll_speed_ms=50,
            font_size=24,
            text_loops=0,
            font=FONT_DEFAULT,
        )
```

- [ ] **Step 3: Delete obsolete test classes**

Delete `TestHiresFontTextScaleRejection` (the entire class, ~25 lines). Locate it via:

```bash
grep -n "class TestHiresFontTextScaleRejection" tests/test_widgets/test_image_base.py
```

Delete from the `class TestHiresFontTextScaleRejection:` line through to the next `class ` declaration (exclusive — keep the blank line before the next class).

Delete `TestSingleRowLogicalScaleWrap` entirely. Locate:

```bash
grep -n "class TestSingleRowLogicalScaleWrap" tests/test_widgets/test_image_base.py
```

Delete the whole class — `TestSingleRowFontSize` (added in Task 3) supersedes it.

- [ ] **Step 4: Update `TestTwoRowMode.test_with_text_scale_2_raises`**

```bash
grep -n "test_with_text_scale\|test_two_row_with_text_scale" tests/test_widgets/test_image_base.py
```

Find the test and rewrite it to test the new field name. The existing assertion was about `text_scale > 1` being refused in two-row mode; the new equivalent is `font_size` being refused in two-row mode (use `top_font_size` / `bottom_font_size`).

Find:

```python
    def test_with_text_scale_2_raises(self):
        """text_scale > 1 conflicts with two-row mode (the per-row band
        wraps would shrink each row's effective scale)."""
        import pytest

        with pytest.raises(ValueError, match="text_scale"):
            _DummyImage(
                top_text="A",
                bottom_text="B",
                text_scale=2,
            )
```

Replace with:

```python
    def test_with_font_size_raises(self):
        """font_size is the single-row knob; two-row mode uses
        top_font_size / bottom_font_size for per-row sizing."""
        import pytest

        with pytest.raises(ValueError, match="font_size"):
            _DummyImage(
                top_text="A",
                bottom_text="B",
                font_size=24,
            )
```

- [ ] **Step 5: Run tests to verify the survivors fail (or skip — depends on what's left)**

```bash
uv run pytest tests/test_widgets/test_image_base.py -v 2>&1 | tail -30
```

Expected: a few FAILs around the new font_size test (because the field still exists, but the validation hasn't refused it in two-row mode yet). That's the green-step trigger.

- [ ] **Step 6: Update `_BaseImageWidget` — remove `text_scale` field + add two-row `font_size` rejection**

Edit `src/led_ticker/widgets/_image_base.py`.

Remove the `text_scale` field (around line 90):

```python
    text_scale: int = attrs.field(default=1, kw_only=True)
```

Just delete that line.

Find the validation block in `_validate_common`:

```python
        if self.text_scale < 1:
            raise ValueError(f"text_scale must be >= 1, got {self.text_scale!r}")
```

Delete those two lines.

Find the HiresFont + text_scale rejection (around line 246):

```python
        if isinstance(self.font, _HiresFont) and self.text_scale > 1:
            raise ValueError(
                f"text_scale={self.text_scale} is BDF block-expansion only — "
                f"hi-res font {self.font.name!r} would render at native "
                f"physical pixels and ignore the wrapper. Set text_scale=1 "
                f"or switch to a BDF font."
            )
```

Delete the entire block — HiresFont + font_size > 1 is the natural case now.

Find the two-row + text_scale rejection (around line 260):

```python
        if self.bottom_text and self.text_scale > 1:
            raise ValueError(
                f"text_scale={self.text_scale} is incompatible with "
                f"two-row mode (bottom_text non-empty). Drop text_scale "
                f"or use single-row mode."
            )
```

Replace with the font_size-mode rejection:

```python
        if self.bottom_text and self.font_size is not None:
            raise ValueError(
                f"font_size={self.font_size!r} is the single-row knob; "
                f"in two-row mode use top_font_size and bottom_font_size."
            )
```

- [ ] **Step 7: Run tests to verify everything passes**

```bash
uv run pytest -q
```

Expected: 1071+ passing (we removed obsolete tests so the count drops a bit, but stays positive overall).

- [ ] **Step 8: Final grep for stragglers**

```bash
grep -rn "text_scale" src/ tests/ --include="*.py"
```

Expected: empty output. Comments and old removed references should be gone.

```bash
grep -rn "text_scale" config/*.toml
```

Expected: empty output (live keys + comments cleaned up in Task 5).

- [ ] **Step 9: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_base.py
git commit -m "$(cat <<'EOF'
_BaseImageWidget: remove text_scale field, add two-row font_size guard

text_scale is fully superseded by font_size (real pixels) — no remaining
read sites in the codebase. The migration error in _build_widget
(Task 4) catches any external configs that miss the cutover.

Validation changes:
- Drop `text_scale >= 1` check.
- Drop `text_scale > 1 with HiresFont` rejection (no longer applicable;
  HiresFont's natural unit IS font_size).
- Replace `text_scale > 1 in two-row mode` rejection with
  `font_size in two-row mode` rejection (top_font_size / bottom_font_size
  are the per-row knobs).

Tests updated: TestSingleRowFontSize supersedes TestSingleRowLogicalScaleWrap;
TestHiresFontTextScaleRejection deleted; TestFieldSurface and TwoRow tests
swap text_scale for font_size.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: HiresFont required-explicit `font_size` in `_build_widget`

The current `_build_widget` defaults missing `font_size` to `DEFAULT_HIRES_SIZE`. The spec says HiresFont must require explicit `font_size` (the rasterizer needs a real-px target at construction; smart default applies to BDF only). Audited: every existing HiresFont config in the repo pairs `font` with `font_size`, so removing the default is safe.

**Files:**
- Modify: `src/led_ticker/app.py` (drop `DEFAULT_HIRES_SIZE` fallback for HiresFont)
- Test: `tests/test_app.py` (extend `TestFontSizeMigration`)

- [ ] **Step 1: Write the failing test**

Append to `TestFontSizeMigration` in `tests/test_app.py`:

```python
    async def test_hires_font_without_font_size_raises(self, tmp_path):
        """HiresFont (any TTF/OTF name resolved to a HiresFont) requires
        explicit `font_size` — the rasterizer needs a real-px target.
        BDF fonts get the smart default, but HiresFont cannot."""
        import io

        import aiohttp
        import pytest
        from PIL import Image

        from led_ticker.app import _build_widget

        gif_path = tmp_path / "tiny.gif"
        Image.new("RGB", (4, 4)).save(gif_path, format="GIF")

        cfg = {
            "type": "gif",
            "path": str(gif_path),
            "fit": "stretch",
            "text": "hi",
            "font": "Inter-Bold",
            # No font_size!
        }

        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError, match="HiresFont.*requires font_size"):
                await _build_widget(cfg, s, config_dir=tmp_path)

    async def test_bdf_without_font_size_succeeds(self, tmp_path):
        """BDF font without font_size is the natural case — smart
        default kicks in at first paint. _build_widget shouldn't
        complain."""
        import io

        import aiohttp
        from PIL import Image

        from led_ticker.app import _build_widget

        gif_path = tmp_path / "tiny.gif"
        Image.new("RGB", (4, 4)).save(gif_path, format="GIF")

        cfg = {
            "type": "gif",
            "path": str(gif_path),
            "fit": "stretch",
            "text": "hi",
            "font": "6x12",
            # No font_size — should resolve to default BDF, no error.
        }

        async with aiohttp.ClientSession() as s:
            widget = await _build_widget(cfg, s, config_dir=tmp_path)

        assert widget.font_size is None  # smart default, not yet resolved
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_app.py::TestFontSizeMigration::test_hires_font_without_font_size_raises tests/test_app.py::TestFontSizeMigration::test_bdf_without_font_size_succeeds -v
```

Expected: `test_hires_font_without_font_size_raises` FAILs (still falls back to DEFAULT_HIRES_SIZE); `test_bdf_without_font_size_succeeds` may PASS or FAIL depending on whether `font_size` makes it onto the widget (likely passes since BDF doesn't need a size).

- [ ] **Step 3: Update `_build_widget` to require font_size for HiresFont**

Edit `src/led_ticker/app.py`. Find the font resolution block (around line 121):

```python
    font_name = widget_cfg.pop("font", None)
    font_size = widget_cfg.pop("font_size", None)
    font_threshold = widget_cfg.pop("font_threshold", None)
    if font_name is not None:
        from led_ticker.fonts import DEFAULT_HIRES_SIZE, resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        size = font_size if font_size is not None else DEFAULT_HIRES_SIZE
        font = resolve_font(font_name, size, threshold=font_threshold)
        widget_cfg["font"] = font
```

Note that `font_size` is also passed to BDF widgets (which ignore it inside `resolve_font` for BDF aliases). The widget's own `font_size` field needs the original int (for the smart default's "explicit user value" branch). Restructure:

Replace the block above with:

```python
    font_name = widget_cfg.pop("font", None)
    font_size = widget_cfg.pop("font_size", None)
    font_threshold = widget_cfg.pop("font_threshold", None)
    if font_name is not None:
        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        # Resolve the font WITHOUT forcing a default size — `resolve_font`
        # passes None through to BDF (which ignores size; cells are fixed)
        # and raises if a HiresFont gets None size.
        if _is_hires_font_name(font_name) and font_size is None:
            raise ValueError(
                f"HiresFont {font_name!r} requires font_size (real "
                f"pixels). e.g. font_size = 24 for bigsign, "
                f"font_size = 12 for small sign."
            )
        font = resolve_font(font_name, font_size, threshold=font_threshold)
        widget_cfg["font"] = font

        # Pass through to widget so its `_resolved_font_size` smart
        # default sees the explicit value when set.
        if font_size is not None:
            widget_cfg["font_size"] = font_size
```

Add the `_is_hires_font_name` helper near the top of `app.py` (above `_build_widget`):

```python
def _is_hires_font_name(name: str) -> bool:
    """True if `name` resolves to a HiresFont (TTF/OTF), False if BDF
    alias. Verified `list_available_hires_fonts` exists in
    `fonts/__init__.py` and is the canonical way to enumerate hires
    font names."""
    from led_ticker.fonts import list_available_hires_fonts

    return name in list_available_hires_fonts()
```

The error message must mention "HiresFont" and "requires font_size" verbatim — the test uses a regex match on those words.

Also update the per-row font block (around line 154) for `top_font` / `bottom_font` consistency. Same pattern: if the resolved font would be a HiresFont and no `top_font_size` / `bottom_font_size` was given, raise.

Find:

```python
    for prefix in ("top_font", "bottom_font"):
        row_name = widget_cfg.pop(prefix, None)
        row_size = widget_cfg.pop(f"{prefix}_size", None)
        row_threshold = widget_cfg.pop(f"{prefix}_threshold", None)
        if row_name is not None:
            from led_ticker.fonts import DEFAULT_HIRES_SIZE, resolve_font

            size = row_size if row_size is not None else DEFAULT_HIRES_SIZE
            widget_cfg[prefix] = resolve_font(row_name, size, threshold=row_threshold)
```

Replace with:

```python
    for prefix in ("top_font", "bottom_font"):
        row_name = widget_cfg.pop(prefix, None)
        row_size = widget_cfg.pop(f"{prefix}_size", None)
        row_threshold = widget_cfg.pop(f"{prefix}_threshold", None)
        if row_name is not None:
            from led_ticker.fonts import resolve_font

            if _is_hires_font_name(row_name) and row_size is None:
                raise ValueError(
                    f"HiresFont {row_name!r} requires {prefix}_size "
                    f"(real pixels). e.g. {prefix}_size = 22 for "
                    f"bigsign two-row layouts."
                )
            widget_cfg[prefix] = resolve_font(
                row_name, row_size, threshold=row_threshold
            )
```

- [ ] **Step 4: Update `resolve_font` to accept `size=None` for BDF**

Edit `src/led_ticker/fonts/__init__.py`. The current signature (verified at line 78) is:

```python
def resolve_font(
    name: str, size: int = DEFAULT_HIRES_SIZE, threshold: int | None = None
) -> Font | HiresFont:
```

Update the signature to make `size` Optional with no default:

```python
def resolve_font(
    name: str, size: int | None = None, threshold: int | None = None
) -> Font | HiresFont:
```

The current function body (lines 97-121) has:

```python
    if size < 8:
        raise ValueError(f"font_size must be >= 8 for legible rendering; got {size}")
    if threshold is not None:
        # ... (threshold validation, unchanged)
    from led_ticker.fonts.hires_loader import THRESHOLD

    effective = THRESHOLD if threshold is None else threshold
    hires = load_hires_font(name, size, effective)
    if hires is not None:
        return hires
    if name in _BDF_ALIASES:
        return _BDF_ALIASES[name]
    available = list_available_fonts()
    raise UnknownFontError(f"unknown font {name!r}; available: {available}")
```

The `size < 8` check fires before the BDF branch, which means with `size=None` it would raise `TypeError: '<' not supported`. Restructure to check BDF FIRST so size is irrelevant for that path:

```python
    # BDF first — cells are fixed by the .bdf file, size is irrelevant
    # there. This also lets the caller pass `size=None` for BDF without
    # tripping the `size < 8` legibility check.
    if name in _BDF_ALIASES:
        return _BDF_ALIASES[name]

    # HiresFont path — size is required (rasterizer needs a real-px
    # target).
    if size is None:
        raise ValueError(
            f"HiresFont {name!r} requires a size (real pixels)."
        )
    if size < 8:
        raise ValueError(f"font_size must be >= 8 for legible rendering; got {size}")
    if threshold is not None:
        if not isinstance(threshold, int) or isinstance(threshold, bool):
            raise ValueError(
                f"font_threshold must be an int 0-255; got {type(threshold).__name__} "
                f"({threshold!r})"
            )
        if not (0 <= threshold <= 255):
            raise ValueError(f"font_threshold must be 0-255; got {threshold}")
    from led_ticker.fonts.hires_loader import THRESHOLD

    effective = THRESHOLD if threshold is None else threshold
    hires = load_hires_font(name, size, effective)
    if hires is not None:
        return hires
    available = list_available_fonts()
    raise UnknownFontError(f"unknown font {name!r}; available: {available}")
```

Note: `_BDF_ALIASES` is defined at line 63 and `list_available_fonts` at line 124 — both already in scope. No new imports needed.

The duplicate check between `_build_widget` (caller-side, TOML-friendly message) and `resolve_font` (library-side, defensive fallback) is intentional.

Verify the restructure works for both paths:

```bash
PYTHONPATH=tests/stubs uv run python -c "
from led_ticker.fonts import resolve_font
print('BDF None:', resolve_font('6x12', None))
print('BDF int:', resolve_font('6x12', 12))
try:
    resolve_font('Inter-Regular', None)
except ValueError as e:
    print('Hires None:', repr(str(e)))
print('Hires int:', resolve_font('Inter-Regular', 24))
"
```

Expected: BDF cases return Font objects; "Hires None" prints a ValueError mentioning "requires a size"; "Hires int" returns a HiresFont.

- [ ] **Step 5: Flip the two obsolete tests that asserted DEFAULT_HIRES_SIZE fallback**

The codebase has two tests that asserted "HiresFont without size → falls back to DEFAULT_HIRES_SIZE." Now that we require explicit size, both must flip to assert the raise.

In `tests/test_hires_font_loader.py` (around line 293), find:

```python
    def test_default_size_used_when_size_omitted(self):
        from led_ticker.fonts import DEFAULT_HIRES_SIZE, resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        font = resolve_font("Inter-Regular")
        assert isinstance(font, HiresFont)
        assert font.size == DEFAULT_HIRES_SIZE
```

Replace with:

```python
    def test_resolve_font_hires_without_size_raises(self):
        """HiresFont requires explicit size at resolve time — the
        rasterizer needs a real-px target and silent fallback to
        DEFAULT_HIRES_SIZE could mismatch the panel."""
        import pytest

        from led_ticker.fonts import resolve_font

        with pytest.raises(ValueError, match="requires a size"):
            resolve_font("Inter-Regular")
```

In `tests/test_app.py` (around line 401), find:

```python
    @pytest.mark.asyncio
    async def test_default_size_when_font_size_omitted(self):
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.fonts import DEFAULT_HIRES_SIZE
        from led_ticker.fonts.hires_loader import HiresFont

        async with aiohttp.ClientSession() as session:
            widget_cfg = {
                "type": "message",
                "text": "hi",
                "font": "Inter-Regular",
                # no font_size
            }
            widget = await _build_widget(widget_cfg, session)
        assert isinstance(widget.font, HiresFont)
        assert widget.font.size == DEFAULT_HIRES_SIZE
```

Replace with:

```python
    @pytest.mark.asyncio
    async def test_hires_without_font_size_raises(self):
        """HiresFont in a TOML widget config without explicit
        font_size raises with the size-hint error message — caught at
        config-load via `_is_hires_font_name`."""
        import aiohttp
        import pytest

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            widget_cfg = {
                "type": "message",
                "text": "hi",
                "font": "Inter-Regular",
                # no font_size
            }
            with pytest.raises(ValueError, match="HiresFont.*requires font_size"):
                await _build_widget(widget_cfg, session)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/test_app.py::TestFontSizeMigration tests/test_app.py::test_hires_without_font_size_raises tests/test_hires_font_loader.py::test_resolve_font_hires_without_size_raises -v
```

Expected: all PASS.

- [ ] **Step 7: Run the full suite**

```bash
uv run pytest -q
```

Expected: 1073+ passing. (Same count as before; we replaced 2 obsolete tests with 2 new ones plus added 2 in Task 4 + 2 in this task's earlier step.)

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/app.py src/led_ticker/fonts/__init__.py tests/test_app.py tests/test_hires_font_loader.py
git commit -m "$(cat <<'EOF'
_build_widget: HiresFont requires explicit font_size

The previous fallback (DEFAULT_HIRES_SIZE when font_size missing) was
silently rasterizing at a fixed default that may not have matched the
panel. Now HiresFont configs must specify font_size explicitly — the
rasterizer needs a real-px target at construction.

Audit confirmed every existing HiresFont config in the repo pairs
`font` with `font_size`, so removing the fallback is safe.

BDF still defaults to None (smart default at first paint via
_resolved_font_size). resolve_font accepts size=None for BDF (cells
are fixed), raises for HiresFont (rasterizer needs a target).

Same enforcement applied to per-row top_font / bottom_font in TwoRow
mode. Two obsolete tests (test_default_size_used_when_size_omitted,
test_default_size_when_font_size_omitted) flipped to assert the raise.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Update widget schema docstrings

The TOML schema tables in `gif.py` and `still.py` module docstrings still document `text_scale`. Update both to reference `font_size` and the smart-default behavior.

**Files:**
- Modify: `src/led_ticker/widgets/gif.py` (module docstring)
- Modify: `src/led_ticker/widgets/still.py` (module docstring)

- [ ] **Step 1: Update `gif.py` schema row**

Edit `src/led_ticker/widgets/gif.py`. Find the schema row for `text_scale`:

```
``text_scale``      ``1``              Block-scale glyphs (1=native; set 2-4 on
                                       bigsign for readable text).
```

Replace with:

```
``font_size``       (smart default)    Real-pixel text size. Default: BDF
                                       cell_h × _logical_scale (= 12 on small
                                       sign, 48 on bigsign for FONT_DEFAULT).
                                       HiresFont configs must specify explicitly.
                                       For BDF, snaps down to the nearest
                                       integer multiple of the cell height.
```

Find the constraint block:

```
Constraints validated at construction:
    - ``text_scale >= 1``
    - ``gif_loops >= 1``
```

Replace with:

```
Constraints validated at construction:
    - ``font_size > 0`` (if set)
    - ``gif_loops >= 1``
```

Find the paint-time validation block:

```
Validated at first paint (panel dims unknown until then):
    - ``panel_h // text_scale >= 12`` (BDF cell needs 12 logical rows)
```

Replace with:

```
Validated at first paint (panel dims unknown until then):
    - ``font_size >= cell_h`` for BDF (raises with hint if smaller)
    - ``font_size`` resolved value's logical line-height fits the panel
```

- [ ] **Step 2: Update `still.py` schema row**

Apply the same conversion as Step 1 to `src/led_ticker/widgets/still.py` — same row, same constraint blocks. The exact line numbers may differ but the text is identical.

Find:

```
``text_scale``      ``1``              Block-scale text glyphs (1=native; 2-4
                                       on bigsign for distance readability).
```

Replace with:

```
``font_size``       (smart default)    Real-pixel text size. Default: BDF
                                       cell_h × _logical_scale (= 12 on small
                                       sign, 48 on bigsign for FONT_DEFAULT).
                                       HiresFont configs must specify explicitly.
                                       For BDF, snaps down to the nearest
                                       integer multiple of the cell height.
```

Find:

```
Constraints validated at construction:
    - ``text_scale >= 1``
    - ``hold_seconds >= 0.05``
```

Replace with:

```
Constraints validated at construction:
    - ``font_size > 0`` (if set)
    - ``hold_seconds >= 0.05``
```

Find:

```
Validated at first paint (panel dims unknown until then):
    - ``panel_h // text_scale >= 12`` (BDF cell needs 12 logical rows)
```

Replace with:

```
Validated at first paint (panel dims unknown until then):
    - ``font_size >= cell_h`` for BDF (raises with hint if smaller)
    - ``font_size`` resolved value's logical line-height fits the panel
```

- [ ] **Step 3: Verify no `text_scale` references survive in widget docstrings**

```bash
grep -n "text_scale" src/led_ticker/widgets/gif.py src/led_ticker/widgets/still.py
```

Expected: empty output.

- [ ] **Step 4: Run the full suite to confirm nothing broke**

```bash
uv run pytest -q
```

Expected: 1073+ passing (docstring changes don't affect tests, but defensive).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/gif.py src/led_ticker/widgets/still.py
git commit -m "$(cat <<'EOF'
gif/still widgets: update schema docstrings for font_size

Replace `text_scale` row in the TOML schema tables with `font_size`,
documenting the smart default (cell_h × _logical_scale for BDF) and
the HiresFont required-explicit semantic.

Constraint blocks updated to reference font_size at construction
(must be > 0 if set) and at first paint (>= cell_h for BDF, fits
panel logical rows).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Update CLAUDE.md

Replace the bd61140 paragraph's `effective_scale` formula with the new `font_size` rule. Add the migration formula for any external configs that may still use `text_scale`.

**Files:**
- Modify: `CLAUDE.md` (the "Single-row image text on bigsign" paragraph + migration note)

- [ ] **Step 1: Locate the existing paragraph**

```bash
grep -n "Single-row image text on bigsign" CLAUDE.md
```

Expected hit around line 111 — the paragraph that starts with "Single-row image text on bigsign — wrap fires on `_logical_scale`".

- [ ] **Step 2: Rewrite the paragraph**

Find:

```
**Single-row image text on bigsign — wrap fires on `_logical_scale`**: `_play_with_text` computes `effective_scale = max(text_scale, _logical_scale)` and wraps when > 1. ...
```

Replace the entire paragraph with:

```
**Single-row image text — `font_size` is the unified knob**: `_play_with_text` resolves the user-facing `font_size` (real pixels) at first paint, then converts to an integer block scale for the ScaledCanvas wrap via `block_scale_for_font_size(font, font_size)`. For BDF: rounds down to nearest multiple of cell height (raises if `font_size < cell_h`). For HiresFont: always 1 (rasterizer handled size at construction). Smart default for BDF when `font_size` is unset: `cell_h × _logical_scale` (= 12 on small sign, 48 on bigsign for FONT_DEFAULT). HiresFont configs must specify `font_size` explicitly — `_build_widget` raises with the e.g.-24-on-bigsign hint. **Migration from text_scale**: `font_size = N × cell_h_of_your_font`. For BDF 6×12: text_scale=2 → font_size=24, text_scale=4 → font_size=48. The migration error in `_build_widget` catches stale TOMLs at config-load with the formula in the error message. Tripwires: `TestSingleRowFontSize` (3 tests), `TestResolvedFontSize` (7 tests), `TestBlockScaleForFontSize` (6 tests), `TestFontSizeMigration` (4 tests).
```

- [ ] **Step 3: Confirm no other CLAUDE.md sections reference `text_scale`**

```bash
grep -n "text_scale" CLAUDE.md
```

Expected: empty output. If anything remains, rewrite it inline using `font_size` vocabulary.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
CLAUDE.md: replace text_scale paragraph with font_size rule

The bd61140 paragraph's `effective_scale = max(text_scale, _logical_scale)`
formula is gone; replaced with the `font_size` resolution + smart default
description. Migration note included for external configs.

Tripwire references updated: TestSingleRowFontSize supersedes
TestSingleRowLogicalScaleWrap; new tripwires for TestResolvedFontSize,
TestBlockScaleForFontSize, TestFontSizeMigration.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Final verification + push

End-to-end sanity check + push to main.

- [ ] **Step 1: Full test suite**

```bash
uv run pytest -q
```

Expected: 1073+ passing, 1 skipped, 0 failures.

- [ ] **Step 2: Lint**

```bash
make lint 2>&1 | tail -5
```

Expected: clean (or auto-fixable).

- [ ] **Step 3: Verify all in-tree configs parse and would `_build_widget` cleanly**

```bash
PYTHONPATH=tests/stubs uv run python -c "
import asyncio
import tomllib
from pathlib import Path
import aiohttp
from led_ticker.app import _build_widget

async def main():
    for p in Path('config').glob('config.*.example.toml'):
        with open(p) as f:
            cfg = tomllib.loads(f.read())
        sections = cfg.get('playlist', {}).get('section', [])
        async with aiohttp.ClientSession() as s:
            for i, sec in enumerate(sections):
                for j, w in enumerate(sec.get('widget', [])):
                    try:
                        await _build_widget(dict(w), s, config_dir=p.parent)
                    except Exception as e:
                        print(f'{p.name} section {i+1} widget {j+1}: {type(e).__name__}: {e}')
                        return
        print(f'{p.name}: {len(sections)} sections OK')

asyncio.run(main())
"
```

Expected: every example config builds without error. Any failure means a config still has `text_scale` or a HiresFont missing `font_size`.

- [ ] **Step 4: Push**

```bash
git push origin main
```

Expected: pushed cleanly. Pre-commit hooks run pyright + pytest, all pass.

- [ ] **Step 5: Hardware verification (manual)**

On the bigsign Pi:

```bash
git pull
docker compose up -d --build
docker compose logs -f
```

Cycle through `config.gif_text.example.toml` (which the user has copied to `config.toml`) and visually verify:
- Section 1 (PIKACHU): Inter-Bold @ 24, sits in right pillar, doesn't overlap.
- Section 3 (TRANS RIGHTS): scroll-over knockout text, font_size=24 (was text_scale=2).
- Section 4 (HAPPY PRIDE): block-expanded BDF + emoji, font_size=48 (was text_scale=4).
- Section 5 (kpop dance): scroll-over, font_size=24 (was text_scale=2).

If any section looks wrong, file a separate issue — out of scope for this PR.

- [ ] **Step 6: Update the user's bigsign config.toml (out of repo)**

Same migration formula applies. Search/replace on the Pi:

```bash
ssh pi@bigsign
cd /path/to/config
grep -n "text_scale" config.toml
# For each match: text_scale = N → font_size = N × cell_h
```

If their config.toml inherited from `config.gif_text.example.toml` directly (which they did), they can re-copy:

```bash
cp config/config.gif_text.example.toml config/config.toml
```

The migration error in `_build_widget` will catch any missed sites at startup with the formula in the message.

---

## Summary

10 tasks, each with a single commit and TDD discipline. The cutover is hard but the migration error in `_build_widget` (Task 4) lands BEFORE the field removal (Task 6), giving a 2-step safety net for any external configs.

**Acceptance:**
- All 1073+ tests pass.
- `text_scale` appears nowhere in `src/`, `tests/`, or `config/*.toml` (greppable check).
- `config.gif_text.example.toml` PIKACHU section renders cleanly on hardware.
- Migration error message tested (verbatim) for stale `text_scale` configs.
- HiresFont without `font_size` raises with the size-hint message.
