# ColorBandsBorder (`style = "bands"`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new core `BorderEffect` that marches discrete solid-color bands around the panel perimeter, with named palettes (`rainbow`, `rasta`, `usa`, `christmas`, `halloween`, `candy_cane`) or explicit RGB lists.

**Architecture:** New `ColorBandsBorder(BorderEffectBase)` class + `BAND_PALETTES` registry in `src/led_ticker/borders.py`, reusing the cached `_perimeter_pixels()` walk and `unwrap_to_real` physical-resolution painting. A new `case "bands":` arm in `_coerce_border` (`src/led_ticker/app/coercion.py`) handles TOML validation and palette resolution. No widget-side changes — the `border` field already dispatches through shared coercion on `message`, `countdown`, `two_row`, `gif`, `image`.

**Tech Stack:** Python 3.14, pytest (stubs in `tests/stubs`), Astro docs site (pnpm via nvm), render-demo GIF tooling.

**Spec:** `docs/superpowers/specs/2026-06-11-bands-border-design.md` (read it first).

**Branch:** all work on `feat/bands-border` (already exists; the spec commits are on it). NEVER commit to `main`.

**Conventions that apply to every task:**
- Run tests with `make test` (sets `PYTHONPATH=tests/stubs`) or, for a single file, `PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py -v`.
- Pre-commit hooks run ruff + ruff-format automatically; if a commit fails on formatting, re-stage and retry.
- The docs-lint pre-commit hook runs pnpm — node comes from nvm. If `pnpm` is not on PATH, run `source ~/.nvm/nvm.sh && nvm use` (or verify `node --version`) before committing docs changes.
- This project has NO `from __future__ import annotations` in `src/` (PEP 649 / Python 3.14 rule). `tests/test_borders.py` already has it at the top — leave it alone.

---

### Task 1: `ColorBandsBorder` effect class + `BAND_PALETTES` (TDD)

**Files:**
- Modify: `src/led_ticker/borders.py` (class after `ConstantBorder` ~line 374; palettes + registry at the bottom ~line 504; module docstring)
- Test: `tests/test_borders.py` (append new test classes at end of file)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_borders.py`. The file already imports `pytest`, `_perimeter_pixels`, `ScaledCanvas`, and defines `_StubCanvas` (line 108: captures `SetPixel` into a `.pixels` dict). Add `BAND_PALETTES` and `ColorBandsBorder` to the existing `from led_ticker.borders import (...)` block at the top of the file.

```python
class TestBandPalettes:
    """BAND_PALETTES registry sanity — every named palette must be a
    usable bands spec: >= 2 colors, each a valid (r, g, b) tuple."""

    def test_expected_palettes_present(self):
        assert set(BAND_PALETTES) == {
            "rainbow",
            "rasta",
            "usa",
            "christmas",
            "halloween",
            "candy_cane",
        }

    def test_all_palettes_valid(self):
        for name, colors in BAND_PALETTES.items():
            assert len(colors) >= 2, f"palette {name!r} needs >= 2 colors"
            for c in colors:
                assert len(c) == 3, f"palette {name!r} entry {c!r} not RGB"
                for v in c:
                    assert isinstance(v, int) and not isinstance(v, bool)
                    assert 0 <= v <= 255, f"palette {name!r} value {v} out of range"


class TestColorBandsBorder:
    """Discrete solid-color bands marching around the perimeter.
    Band at perimeter index `idx`, frame `f`:
    ((idx - f * speed) // band_width) % len(colors)."""

    RED = (255, 0, 0)
    WHITE = (255, 255, 255)

    def _border(self, **kw):
        kw.setdefault("colors", [self.RED, self.WHITE])
        return ColorBandsBorder(**kw)

    def test_satisfies_protocol(self):
        b = self._border()
        assert hasattr(b, "frame_invariant")
        assert isinstance(b.frame_invariant, bool)
        assert callable(b.paint)

    def test_defaults(self):
        b = self._border()
        assert b.band_width == 6
        assert b.speed == 1
        assert b.thickness == 1

    def test_frame_invariant_false_for_default_speed(self):
        assert self._border().frame_invariant is False

    def test_frame_invariant_true_for_speed_zero(self):
        assert self._border(speed=0).frame_invariant is True

    def test_restart_on_visit_is_false(self):
        """Continuous march across loop_count boundaries, like the
        other animated borders."""
        assert ColorBandsBorder.restart_on_visit is False

    def test_band_pattern_at_frame_zero(self):
        """First band_width perimeter pixels are color 0, next
        band_width are color 1, wrapping modulo len(colors)."""
        b = self._border(band_width=4, speed=1)
        c = _StubCanvas(20, 8)
        b.paint(c, frame_count=0)
        px = _perimeter_pixels(20, 8, 1)
        for i in range(4):
            assert c.pixels[px[i]] == self.RED, f"idx {i}"
        for i in range(4, 8):
            assert c.pixels[px[i]] == self.WHITE, f"idx {i}"
        # Wraps modulo: idx 8 starts the next RED band.
        assert c.pixels[px[8]] == self.RED

    def test_paints_every_perimeter_pixel(self):
        c = _StubCanvas(20, 8)
        self._border().paint(c, frame_count=0)
        assert len(c.pixels) == 2 * (20 + 8) - 4  # 52

    def test_positive_speed_marches_clockwise(self):
        """At frame f the pattern is the frame-0 pattern shifted
        forward (clockwise) by f * speed perimeter pixels:
        color(idx + shift, f) == color(idx, 0)."""
        b = self._border(band_width=4, speed=1)
        c0, c2 = _StubCanvas(20, 8), _StubCanvas(20, 8)
        b.paint(c0, frame_count=0)
        b.paint(c2, frame_count=2)
        px = _perimeter_pixels(20, 8, 1)
        for i in range(len(px) - 2):
            assert c2.pixels[px[i + 2]] == c0.pixels[px[i]], f"idx {i}"

    def test_negative_speed_reverses(self):
        """speed=-1 marches counter-clockwise:
        color(idx, f=1) == color(idx + 1, 0)."""
        b = self._border(band_width=4, speed=-1)
        c0, c1 = _StubCanvas(20, 8), _StubCanvas(20, 8)
        b.paint(c0, frame_count=0)
        b.paint(c1, frame_count=1)
        px = _perimeter_pixels(20, 8, 1)
        for i in range(len(px) - 1):
            assert c1.pixels[px[i]] == c0.pixels[px[i + 1]], f"idx {i}"

    def test_speed_zero_is_static(self):
        b = self._border(speed=0)
        c0, c7 = _StubCanvas(20, 8), _StubCanvas(20, 8)
        b.paint(c0, frame_count=0)
        b.paint(c7, frame_count=7)
        assert c0.pixels == c7.pixels

    def test_three_color_palette_cycles_in_order(self):
        b = ColorBandsBorder(
            colors=[(255, 0, 0), (255, 191, 0), (0, 255, 0)], band_width=2
        )
        c = _StubCanvas(20, 8)
        b.paint(c, frame_count=0)
        px = _perimeter_pixels(20, 8, 1)
        assert c.pixels[px[0]] == (255, 0, 0)
        assert c.pixels[px[2]] == (255, 191, 0)
        assert c.pixels[px[4]] == (0, 255, 0)
        assert c.pixels[px[6]] == (255, 0, 0)  # wraps

    def test_accepts_color_objects(self):
        """Constructor materializes .red/.green/.blue objects to plain
        tuples (same trick as ConstantBorder)."""
        import types

        b = ColorBandsBorder(
            colors=[
                types.SimpleNamespace(red=10, green=20, blue=30),
                (40, 50, 60),
            ]
        )
        c = _StubCanvas(20, 8)
        b.paint(c, frame_count=0)
        px = _perimeter_pixels(20, 8, 1)
        assert c.pixels[px[0]] == (10, 20, 30)

    def test_unwraps_scaled_canvas_to_paint_real_pixels(self):
        """Paints at PHYSICAL resolution — 1 px border = 1 real LED on
        bigsign, not a scale x scale block (mirrors the RainbowChase
        test of the same name)."""
        real = _StubCanvas(64, 32)
        wrapper = ScaledCanvas(real, scale=4, content_height=8)
        self._border().paint(wrapper, frame_count=0)
        assert len(real.pixels) == 2 * (64 + 32) - 4  # 188

    def test_thickness_2_paints_both_rings(self):
        c = _StubCanvas(10, 4)
        self._border(thickness=2).paint(c, frame_count=0)
        # Outer ring 24 + inner ring 16 (matches TestPerimeterGeometry).
        assert len(c.pixels) == 40
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py -v -k "BandPalettes or ColorBands"`
Expected: collection error — `ImportError: cannot import name 'BAND_PALETTES' from 'led_ticker.borders'`

- [ ] **Step 3: Implement `ColorBandsBorder` + `BAND_PALETTES`**

In `src/led_ticker/borders.py`, insert after the `ConstantBorder` class (ends ~line 373, before `class LightbulbBorder`):

```python
class ColorBandsBorder(BorderEffectBase):
    """Discrete solid-color bands marching around the perimeter.

    The geometry of `RainbowChaseBorder` (continuous per-pixel
    perimeter walk) but with a user-supplied list of solid colors
    instead of a continuous hue ramp — candy-cane / barber-pole /
    flag-ribbon looks. Band at perimeter index `idx` and frame `f`:

        band = ((idx - f * speed) // band_width) % len(colors)

    Positive `speed` marches the pattern clockwise by `speed`
    perimeter pixels per frame; negative reverses; 0 is static bands.
    Python floor division gives correct wraparound for negative
    offsets. Note the band pattern only tiles seamlessly when the
    perimeter length is a multiple of `band_width * len(colors)` —
    otherwise two same-color bands meet at the top-left seam, same
    class of artifact as the rainbow chase's hue seam. Accepted.

    `colors` comes from the config layer already resolved to a list of
    RGB tuples (named palettes in `BAND_PALETTES` resolve at coercion
    time). For `thickness = 2` the perimeter index continues from the
    outer ring into the inner ring (same continuous enumeration the
    rainbow chase uses) — bands don't perfectly align ring-to-ring.

    `frame_invariant` is dynamic: True only when `speed == 0` (static
    bands are a meaningful pattern, and the image-widget fast path can
    then skip per-tick redraws — same shape as `RainbowChaseBorder`).
    """

    # Continuous march: phase advances across loop_count boundaries
    # within a section. See `FrameAwareBase.reset_frame`.
    restart_on_visit: bool = False

    def __init__(
        self,
        colors: Any,
        band_width: int = 6,
        speed: int = 1,
        thickness: int = 1,
    ) -> None:
        # Each entry accepts a `graphics.Color` or an `(r, g, b)`
        # tuple. Materialize to plain tuples at construction so
        # paint() is hot-loop friendly (same trick as ConstantBorder).
        self._colors: list[tuple[int, int, int]] = [
            (c.red, c.green, c.blue) if hasattr(c, "red") else tuple(c)
            for c in colors
        ]
        self.band_width = band_width
        self.speed = speed
        self.thickness = thickness

    @property
    def frame_invariant(self) -> bool:
        return self.speed == 0

    def paint(self, canvas: Canvas, frame_count: int) -> None:
        real = unwrap_to_real(canvas)
        offset = frame_count * self.speed
        n = len(self._colors)
        for idx, (x, y) in enumerate(
            _perimeter_pixels(real.width, real.height, self.thickness)
        ):
            band = ((idx - offset) // self.band_width) % n
            r, g, b = self._colors[band]
            real.SetPixel(x, y, r, g, b)
```

At the bottom of the file, insert before `_BORDER_REGISTRY`:

```python
# Named palettes for ColorBandsBorder's `colors` field. Resolved at
# config-load by `_coerce_border` (the class itself always receives a
# concrete color list). Distinct from `colors.lazy_palette`, which maps
# name -> ONE color; this maps name -> a band sequence. Saturated
# primaries read best on the panels; black is invisible (unlit LED),
# so palettes exclude it.
BAND_PALETTES: dict[str, list[tuple[int, int, int]]] = {
    # Discrete ROYGBIV bands — vs. the continuous `style = "rainbow"` chase.
    "rainbow": [
        (255, 0, 0),
        (255, 128, 0),
        (255, 255, 0),
        (0, 255, 0),
        (0, 0, 255),
        (128, 0, 255),
    ],
    "rasta": [(255, 0, 0), (255, 191, 0), (0, 255, 0)],
    "usa": [(255, 0, 0), (255, 255, 255), (0, 0, 255)],
    "christmas": [(255, 0, 0), (0, 255, 0)],
    "halloween": [(255, 100, 0), (128, 0, 255)],
    "candy_cane": [(255, 0, 0), (255, 255, 255)],
}
```

Add the registry entry inside `_BORDER_REGISTRY` (keep alphabetical-ish grouping; exact dict):

```python
_BORDER_REGISTRY: dict[str, type] = {
    "rainbow": RainbowChaseBorder,
    "color_cycle": ColorCycleBorder,
    "constant": ConstantBorder,
    "lightbulbs": LightbulbBorder,
    "bands": ColorBandsBorder,
}
```

Update the module docstring (line 10): change `Four flavors today:` to `Five flavors today:` and add this bullet after the `ConstantBorder` bullet:

```
- `ColorBandsBorder` — discrete solid-color bands marching around the
  perimeter (candy-cane / barber-pole / flag ribbons). Colors come
  from an explicit RGB list or a named `BAND_PALETTES` entry, resolved
  at config-load. `frame_invariant` only when `speed == 0`.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py -v`
Expected: all PASS (new tests AND the pre-existing border tests).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/borders.py tests/test_borders.py
git commit -m "feat: ColorBandsBorder — solid color bands marching the perimeter"
```

---

### Task 2: TOML coercion — `case "bands":` arm with palette resolution (TDD)

**Files:**
- Modify: `src/led_ticker/app/coercion.py` (`_coerce_border`: docstring ~line 339, function-local import ~line 356, new case arm before `case _:` ~line 529)
- Test: `tests/test_borders.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_borders.py` (`_coerce_border` is already imported at the top of the file):

```python
class TestBandsBorderCoercion:
    """TOML surface for style='bands' — palette strings, explicit
    lists, and the validation matrix."""

    def test_palette_string_resolves(self):
        b = _coerce_border({"style": "bands", "colors": "rasta"})
        assert isinstance(b, ColorBandsBorder)
        assert b._colors == [tuple(c) for c in BAND_PALETTES["rasta"]]

    def test_every_palette_builds(self):
        for name in BAND_PALETTES:
            b = _coerce_border({"style": "bands", "colors": name})
            assert isinstance(b, ColorBandsBorder), name

    def test_explicit_list_with_all_knobs(self):
        b = _coerce_border(
            {
                "style": "bands",
                "colors": [[255, 0, 0], [0, 0, 255]],
                "band_width": 8,
                "speed": -2,
                "thickness": 2,
            }
        )
        assert b._colors == [(255, 0, 0), (0, 0, 255)]
        assert b.band_width == 8
        assert b.speed == -2
        assert b.thickness == 2

    def test_defaults_from_table(self):
        b = _coerce_border({"style": "bands", "colors": "candy_cane"})
        assert b.band_width == 6
        assert b.speed == 1
        assert b.thickness == 1

    def test_speed_zero_allowed_and_frame_invariant(self):
        """Unlike color_cycle (speed=0 rejected), static bands are a
        meaningful pattern with no simpler spelling."""
        b = _coerce_border({"style": "bands", "colors": "christmas", "speed": 0})
        assert b.frame_invariant is True

    def test_missing_colors_raises(self):
        with pytest.raises(ValueError, match="requires 'colors'"):
            _coerce_border({"style": "bands"})

    def test_unknown_palette_lists_available(self):
        with pytest.raises(ValueError, match="candy_cane"):
            _coerce_border({"style": "bands", "colors": "jamaica"})

    def test_single_entry_list_hint(self):
        with pytest.raises(ValueError, match=r"use border = \[r, g, b\] instead"):
            _coerce_border({"style": "bands", "colors": [[255, 0, 0]]})

    def test_empty_list_rejected(self):
        with pytest.raises(ValueError, match="empty"):
            _coerce_border({"style": "bands", "colors": []})

    def test_non_list_non_string_rejected(self):
        with pytest.raises(ValueError, match="palette name string or a list"):
            _coerce_border({"style": "bands", "colors": 7})

    def test_invalid_rgb_entry_rejected(self):
        with pytest.raises(ValueError, match=r"colors\[1\]"):
            _coerce_border(
                {"style": "bands", "colors": [[255, 0, 0], [300, 0, 0]]}
            )

    def test_unknown_keys_rejected(self):
        """from/to stay exclusive to rainbow / color_cycle."""
        with pytest.raises(ValueError, match="unknown keys"):
            _coerce_border(
                {
                    "style": "bands",
                    "colors": "rasta",
                    "from": [255, 0, 0],
                    "to": [0, 0, 255],
                }
            )

    def test_bool_band_width_rejected(self):
        with pytest.raises(ValueError, match="band_width"):
            _coerce_border({"style": "bands", "colors": "rasta", "band_width": True})

    def test_zero_band_width_rejected(self):
        with pytest.raises(ValueError, match="band_width"):
            _coerce_border({"style": "bands", "colors": "rasta", "band_width": 0})

    def test_bool_speed_rejected(self):
        with pytest.raises(ValueError, match="speed"):
            _coerce_border({"style": "bands", "colors": "rasta", "speed": True})

    def test_bare_string_bands_raises_missing_colors(self):
        """No string shorthand: the generic _BORDER_REGISTRY fallback's
        _build_plugin_style introspects the constructor and reports the
        missing required key — no special-case code."""
        with pytest.raises(ValueError, match=r"missing required keys \['colors'\]"):
            _coerce_border("bands")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py::TestBandsBorderCoercion -v`
Expected: MOSTLY FAIL. The dict path's `match` has no `"bands"` arm yet, so it falls into `case _:` → `_build_plugin_style`, which does generic kwarg matching but no palette resolution or RGB validation — e.g. `test_palette_string_resolves` constructs `ColorBandsBorder(colors="rasta")`, which iterates the string into garbage single-char tuples and fails the `_colors` assertion.

Exactly two tests PASS pre-implementation, because the generic fallback already provides their behavior: `test_unknown_keys_rejected` (generic unknown-keys check) and `test_bare_string_bands_raises_missing_colors` (constructor introspection). Everything else must FAIL — including `test_missing_colors_raises`, whose generic message ("missing required keys ['colors']") doesn't match the arm's `requires 'colors'` wording.

- [ ] **Step 3: Implement the coercion arm**

In `src/led_ticker/app/coercion.py`:

1. Add `BAND_PALETTES` and `ColorBandsBorder` to `_coerce_border`'s function-local import (line ~356):

```python
    from led_ticker.borders import (
        BAND_PALETTES,
        ColorBandsBorder,
        ColorCycleBorder,
        ConstantBorder,
        LightbulbBorder,
        RainbowChaseBorder,
    )
```

2. In the `_coerce_border` docstring's "Accepts:" list, add after the `constant` bullets:

```
    - `{style = "bands", colors = "candy_cane" | [[r,g,b], ...], band_width = N,
      speed = N, thickness = N}` → `ColorBandsBorder`. `colors` is required:
      a `BAND_PALETTES` name or a list of >= 2 RGB colors.
```

3. Add the case arm inside the `match style:` block, after `case "lightbulbs":` and before `case _:` (~line 529):

```python
            case "bands":
                allowed = {"colors", "band_width", "speed", "thickness"}
                unknown = set(kwargs.keys()) - allowed
                if unknown:
                    raise ValueError(
                        f"border style 'bands' got unknown keys "
                        f"{sorted(unknown)!r}; allowed: {sorted(allowed)}"
                    )
                if "colors" not in kwargs:
                    raise ValueError(
                        "border style 'bands' requires 'colors': a named "
                        "palette string or a list of [r, g, b] colors, e.g. "
                        "border = {style='bands', colors='candy_cane'}"
                    )
                colors = kwargs.pop("colors")
                if isinstance(colors, str):
                    if colors not in BAND_PALETTES:
                        raise ValueError(
                            f"border 'bands' unknown palette {colors!r}; "
                            f"available: {sorted(BAND_PALETTES)}"
                        )
                    colors = BAND_PALETTES[colors]
                elif isinstance(colors, list | tuple):
                    if len(colors) == 0:
                        raise ValueError(
                            "border 'bands' colors must not be empty"
                        )
                    if len(colors) == 1:
                        raise ValueError(
                            "border 'bands' colors has a single entry — "
                            "use border = [r, g, b] instead"
                        )
                    colors = [
                        tuple(_validate_rgb(c, f"border 'bands' colors[{i}]"))
                        for i, c in enumerate(colors)
                    ]
                else:
                    raise ValueError(
                        f"border 'bands' colors must be a palette name "
                        f"string or a list of [r, g, b]; got "
                        f"{type(colors).__name__}"
                    )
                kwargs["colors"] = colors
                if "band_width" in kwargs:
                    bw = kwargs["band_width"]
                    if isinstance(bw, bool) or not isinstance(bw, int) or bw < 1:
                        raise ValueError(
                            f"border 'bands' band_width must be an int >= 1; "
                            f"got {bw!r}"
                        )
                if "speed" in kwargs:
                    sp = kwargs["speed"]
                    if isinstance(sp, bool) or not isinstance(sp, int):
                        raise ValueError(
                            f"border 'bands' speed must be an int "
                            f"(negative reverses, 0 = static); got {sp!r}"
                        )
                return ColorBandsBorder(**kwargs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/app/coercion.py tests/test_borders.py
git commit -m "feat: TOML coercion for border style 'bands' with named palettes"
```

---

### Task 3: Fast-path gate tripwires on image widgets (test-only)

The image-widget fast-path predicate reads `border.frame_invariant` generically, so bands already behave correctly — these tests are tripwires pinning that behavior (same rationale as `TestPlayWithTextBorderFastPath`).

**Files:**
- Test: `tests/test_widgets/test_image_base.py` (append after `TestPlayWithTextBorderFastPath`, which ends ~line 1640)

- [ ] **Step 1: Write the tests**

Append (the file already imports `pytest`, `mock`; `mock_frame` is a conftest fixture). Mirror the fixture from `TestPlayWithTextBorderFastPath` at line 1573:

```python
class TestPlayWithTextBandsBorderFastPath:
    """Bands border vs. the static-text fast path: speed=0 is
    frame_invariant (fast path stays valid, render once); speed>0
    forces the per-tick loop. Tripwire for the generic
    border.frame_invariant gate — bands must not need special-casing."""

    @pytest.fixture
    def static_widget(self, tmp_path):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        return StillImage(
            path=img_path,
            text="HI",
            text_align="left",
            hold_time=0.5,  # 10 ticks at 50ms
        )

    async def test_static_bands_keeps_fast_path(self, static_widget, mock_frame):
        from led_ticker.borders import ColorBandsBorder

        static_widget.border = ColorBandsBorder(
            colors=[(255, 0, 0), (255, 255, 255)], speed=0
        )
        with (
            mock.patch.object(type(static_widget), "_render_tick") as render_mock,
            mock.patch("asyncio.sleep", new=mock.AsyncMock()),
        ):
            await static_widget._play_with_text(
                mock_frame.swap.return_value,
                mock_frame,
                n_ticks=10,
            )
        assert render_mock.call_count == 1, (
            f"speed=0 bands is frame_invariant — must take the fast path; "
            f"got {render_mock.call_count} render calls"
        )

    async def test_animated_bands_bypasses_fast_path(self, static_widget, mock_frame):
        from led_ticker.borders import ColorBandsBorder

        static_widget.border = ColorBandsBorder(
            colors=[(255, 0, 0), (255, 255, 255)], speed=1
        )
        with (
            mock.patch.object(type(static_widget), "_render_tick") as render_mock,
            mock.patch("asyncio.sleep", new=mock.AsyncMock()),
        ):
            await static_widget._play_with_text(
                mock_frame.swap.return_value,
                mock_frame,
                n_ticks=10,
            )
        assert render_mock.call_count == 10, (
            f"speed=1 bands is animated — per-tick loop must run; "
            f"got {render_mock.call_count} render calls"
        )
```

- [ ] **Step 2: Run tests — expect PASS immediately**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py -v -k BandsBorder`
Expected: both PASS with no implementation change (the gate is generic). If either FAILS, that's a real bug in the gate — STOP and investigate before proceeding; do not adjust the test to pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_widgets/test_image_base.py
git commit -m "test: tripwires — bands border vs image-widget fast path"
```

---

### Task 4: Docs page, pinned demos, preview review

**Files:**
- Create: `docs/site/demos-pinned/border-bands-candy-cane.toml`
- Create: `docs/site/demos-pinned/border-bands-rasta.toml`
- Create (generated): `docs/site/public/demos-pinned/border-bands-candy-cane.gif`, `docs/site/public/demos-pinned/border-bands-rasta.gif`
- Modify: `docs/site/src/content/docs/concepts/borders.mdx` (new `### Bands` section after `### Constant`, ~line 192)

- [ ] **Step 1: Read the docs style guide**

Read `docs/DOCS-STYLE.md` in full before touching the mdx — it is the review rubric for all docs work.

- [ ] **Step 2: Create the demo TOMLs**

`docs/site/demos-pinned/border-bands-candy-cane.toml`:

```toml
# render-duration: 6
# ColorBandsBorder with the candy_cane palette — red/white bands
# marching clockwise around the perimeter.
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
hold_time = 5.0
scroll_step_ms = 30

[[playlist.section.widget]]
type = "message"
text = "Candy"
font = "5x8"
font_color = [255, 255, 255]
border = {style = "bands", colors = "candy_cane"}
```

`docs/site/demos-pinned/border-bands-rasta.toml`:

```toml
# render-duration: 6
# ColorBandsBorder with the rasta palette, wider bands, slow march.
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
hold_time = 5.0
scroll_step_ms = 30

[[playlist.section.widget]]
type = "message"
text = "Irie"
font = "5x8"
font_color = [255, 255, 255]
border = {style = "bands", colors = "rasta", band_width = 8, speed = 1, thickness = 2}
```

- [ ] **Step 3: Render previews to /tmp and review with James**

```bash
make render-demo CONFIG=docs/site/demos-pinned/border-bands-candy-cane.toml OUT=/tmp/border-bands-candy-cane.gif
make render-demo CONFIG=docs/site/demos-pinned/border-bands-rasta.toml OUT=/tmp/border-bands-rasta.gif
```

Read both GIFs with the Read tool and SHOW them to James before committing (this is the project's standard pixel-art iteration flow — small visual steps, approval before commit). Iterate on band_width/speed/palette values if he wants changes, re-rendering to /tmp each time.

- [ ] **Step 4: Render the committed GIFs**

After approval:

```bash
make render-demo CONFIG=docs/site/demos-pinned/border-bands-candy-cane.toml OUT=docs/site/public/demos-pinned/border-bands-candy-cane.gif
make render-demo CONFIG=docs/site/demos-pinned/border-bands-rasta.toml OUT=docs/site/public/demos-pinned/border-bands-rasta.gif
```

- [ ] **Step 5: Write the `### Bands` docs section**

In `docs/site/src/content/docs/concepts/borders.mdx`, insert after the `### Constant` section (ends with the "With thickness" TomlExample, ~line 192) and before `## Where it works`. Match the page's existing voice and component usage (`<DemoGif>`, `<TomlExample>`); adjust during the DOCS-STYLE review pass as needed:

```mdx
### Bands

Discrete solid-color bands marching around the perimeter — the geometry of the rainbow chase, but with a list of solid colors instead of a continuous hue ramp. Candy-cane, barber-pole, and flag-ribbon looks.

<DemoGif
  src="/demos-pinned/border-bands-candy-cane.gif"
  caption="candy_cane palette — red/white bands marching clockwise"
/>

`colors` is required: a named palette or an explicit list of two or more RGB colors. There is no bare-string shorthand for this style.

<TomlExample
  title="Named palette"
  code={`[[playlist.section.widget]]
type = "message"
text = "Candy"
border = {style = "bands", colors = "candy_cane"}`}
/>

<TomlExample
  title="Explicit colors (Italy), wider bands, reverse march"
  code={`[[playlist.section.widget]]
type = "message"
text = "Ciao"
border = {style = "bands", colors = [[0, 146, 70], [255, 255, 255], [206, 43, 55]], band_width = 8, speed = -1}`}
/>

#### Named palettes

| Palette      | Bands                                        |
| ------------ | -------------------------------------------- |
| `rainbow`    | red, orange, yellow, green, blue, purple — discrete bands, vs. the continuous `rainbow` chase |
| `rasta`      | red, gold, green                             |
| `usa`        | red, white, blue                             |
| `christmas`  | red, green                                   |
| `halloween`  | orange, purple                               |
| `candy_cane` | red, white                                   |

<DemoGif
  src="/demos-pinned/border-bands-rasta.gif"
  caption="rasta palette, band_width = 8, thickness = 2"
/>

#### Fields

| Field        | Default      | Meaning                                                                 |
| ------------ | ------------ | ----------------------------------------------------------------------- |
| `colors`     | — (required) | palette name or list of `[r, g, b]` (2+ entries), repeating in order    |
| `band_width` | `6`          | perimeter pixels per band                                               |
| `speed`      | `1`          | pixels the pattern advances per frame; negative reverses; `0` = static  |
| `thickness`  | `1`          | concentric rings (`2` = two-pixel border)                               |

With `speed = 0` the bands are static — like a constant border, the engine's fast path applies and the border is painted once per hold.
```

- [ ] **Step 6: Run the docs review rubric**

Apply the `docs/DOCS-STYLE.md` per-page rubric to the modified page. Verify node/pnpm are available (`node --version`; if missing, `source ~/.nvm/nvm.sh && nvm use`), then run `make docs-lint`.
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add docs/site/demos-pinned/border-bands-*.toml docs/site/public/demos-pinned/border-bands-*.gif docs/site/src/content/docs/concepts/borders.mdx
git commit -m "docs: bands border — concepts page section + pinned demos"
```

---

### Task 5: Housekeeping, full verification, PR

**Files:**
- Modify: `CLAUDE.md` (package-layout line for `borders.py`, ~line 60)

- [ ] **Step 1: Update CLAUDE.md package layout**

Change the `borders.py` line in the package-layout block:

```
  borders.py           # BorderEffect protocol + RainbowChaseBorder, ConstantBorder
```

to:

```
  borders.py           # BorderEffect protocol + chase/cycle/bands/constant/lightbulb borders + BAND_PALETTES
```

- [ ] **Step 2: Full test suite + lint**

```bash
make test
make lint
```

Expected: all 1438+ tests (plus the ~30 new ones) PASS; ruff clean. If `make test` reports failures anywhere — including pre-existing-looking ones — report them verbatim, do not paper over.

- [ ] **Step 3: Commit + push + PR**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md — borders.py layout line covers bands + palettes"
git push -u origin feat/bands-border
gh pr create --title "feat: bands border — solid color bands marching the perimeter" --body "$(cat <<'EOF'
## Summary
- New `ColorBandsBorder` (`border = {style = "bands", ...}`): discrete solid-color bands marching around the panel perimeter — rainbow-chase geometry with a color list instead of a hue ramp
- Named palettes via `colors = "<name>"`: rainbow, rasta, usa, christmas, halloween, candy_cane (`BAND_PALETTES`); explicit `[[r,g,b], ...]` lists also accepted; `colors` required, no bare-string shorthand
- `speed` px/frame (negative reverses, 0 = static + frame_invariant fast path), `band_width`, `thickness`
- Docs: concepts/borders section + two pinned demo GIFs; fast-path tripwires on image widgets

Spec: docs/superpowers/specs/2026-06-11-bands-border-design.md

## Test plan
- [ ] `make test` (new: TestBandPalettes, TestColorBandsBorder, TestBandsBorderCoercion, TestPlayWithTextBandsBorderFastPath)
- [ ] `make lint` / `make docs-lint`
- [ ] Demo GIFs reviewed frame-by-frame before commit

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
