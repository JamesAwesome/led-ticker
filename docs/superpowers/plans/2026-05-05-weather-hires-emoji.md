# Weather Widget Hi-Res Emoji Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the weather widget render hi-res emoji on the bigsign by routing icon drawing through `pixel_emoji`'s existing hires-aware dispatcher instead of blitting low-res sprites directly via `SetPixel`.

**Architecture:** Today `weather_icons.draw_weather_icon` paints `(x, y, r, g, b)` low-res pixel data through `canvas.SetPixel`. On a `ScaledCanvas` (bigsign, scale=4) every pixel block-expands to 4×4 — chunky 32×32 output, even though `HIRES_REGISTRY` already contains genuine 32×32 hires variants for **sun, cloud, rain, snow, thunder, fog**. The fix: extract a public `draw_emoji_at(canvas, slug, x, y)` helper from `pixel_emoji.draw_with_emoji`'s per-emoji branch, have `_match_condition` return slug strings, and refactor `weather.py` to call the new helper. `partly_cloudy` (no hires variant exists yet) gets registered as a low-res slug in `EMOJI_REGISTRY` so it routes through the same code path and stays low-res on bigsign for now.

**Tech Stack:** Python 3.13, attrs, pytest, the existing rgbmatrix stub. No new dependencies.

---

## File Structure

**New code:**
- `pixel_emoji.draw_emoji_at(canvas, slug, x, y, *, max_emoji_height=None) -> int` — single-slug hires-aware draw. Returns advance (sprite width + `EMOJI_PADDING`).

**Modified:**
- `src/led_ticker/pixel_emoji.py` — add `draw_emoji_at`; add `"partly_cloudy"` to `EMOJI_REGISTRY` via `_build_emoji_registry`.
- `src/led_ticker/widgets/weather_icons.py` — `_match_condition` returns slug strings; delete `draw_weather_icon`. Module remains the canonical home for the low-res sprite data + condition→slug mapping.
- `src/led_ticker/widgets/weather.py` — call `pixel_emoji.draw_emoji_at` instead of `draw_weather_icon`. Lazy-import preserved.
- `tests/test_weather_icons.py` — `_match_condition` assertions switch from `is SUN` to `== "sun"`. Drop the `draw_weather_icon` test class (function gone). Migrate icon-drawing coverage into `test_pixel_emoji.py` (already covers `draw_with_emoji`'s lowres + hires paths) and `tests/test_widgets/test_weather.py` (new tripwire).
- `tests/test_pixel_emoji.py` — add `draw_emoji_at` tests: lowres on plain canvas, hires on ScaledCanvas, `max_emoji_height` fallback, KeyError on unknown slug, `partly_cloudy` registry presence.
- `tests/test_widgets/test_weather.py` — add bigsign tripwire: WeatherWidget on a `ScaledCanvas` paints hires sprite pixels (real canvas count > scale²×lowres count).

**Untouched:**
- `_build_widget` — Weather widget construction is unchanged.
- ColorProvider plumbing — no interaction with the icon path.

## Risk Notes

- **Import cycle**: `pixel_emoji` already imports from `weather_icons` lazily inside `_build_emoji_registry`. Going forward, `weather_icons` does NOT import from `pixel_emoji` (the helper lives in `pixel_emoji`, called by `weather.py` directly). No cycle.
- **partly_cloudy on bigsign**: stays low-res (block-expanded 8×8). Adding a hires variant is explicit follow-up scope; not in this plan.
- **`draw_weather_icon` removal**: out-of-tree callers (none in this repo) would break. Repo-only public surface, so safe.
- **`_match_condition` return type**: switches from `PixelData` to `str`. Internal helper (leading `_`), no out-of-tree callers expected; tests are the only consumers.

---

### Task 1: Add `partly_cloudy` to the low-res emoji registry

**Why first:** `_match_condition` will return `"partly_cloudy"` in Task 3; the registry must contain it before that lands so the helper doesn't `KeyError`.

**Files:**
- Modify: `src/led_ticker/pixel_emoji.py:2415-2460` (`_build_emoji_registry`)
- Test: `tests/test_pixel_emoji.py` (append at end)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pixel_emoji.py`:

```python
def test_partly_cloudy_in_lowres_registry():
    """partly_cloudy is a weather slug; the helper resolves it via the
    lowres registry. No hires variant exists yet — that's intentional
    follow-up scope."""
    from led_ticker.pixel_emoji import HIRES_REGISTRY, _get_registry

    registry = _get_registry()
    assert "partly_cloudy" in registry
    assert "partly_cloudy" not in HIRES_REGISTRY
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_pixel_emoji.py::test_partly_cloudy_in_lowres_registry -v
```

Expected: FAIL with `assert 'partly_cloudy' in registry`.

- [ ] **Step 3: Implement**

In `src/led_ticker/pixel_emoji.py`, update the import block inside `_build_emoji_registry` (currently at line ~2417) to also pull `PARTLY_CLOUDY`, and add the registry entry:

```python
def _build_emoji_registry() -> dict[str, PixelData]:
    """Build the emoji registry with all available icons."""
    from led_ticker.widgets.weather_icons import (
        CLOUD,
        FOG,
        PARTLY_CLOUDY,
        RAIN,
        SNOW,
        SUN,
        THUNDER,
    )

    registry = {
        # Sports
        "baseball": BASEBALL,
        "flower": FLOWER,
        "star": STAR,
        # Food
        "taco": TACO,
        # Weather
        "sun": SUN,
        "cloud": CLOUD,
        "partly_cloudy": PARTLY_CLOUDY,
        "rain": RAIN,
        "snow": SNOW,
        "thunder": THUNDER,
        "fog": FOG,
        # Celestial
        "moon": MOON,
        # Social
        "instagram": INSTAGRAM,
        "email": EMAIL,
        # Animals
        "bunny": BUNNY,
        "cat": CAT,
        # Symbols
        "heart": HEART,
    }
    # ... (rest unchanged)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_pixel_emoji.py::test_partly_cloudy_in_lowres_registry -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite to confirm no regression**

```bash
make test
```

Expected: all tests pass (existing suite is ~580 tests, ~15s).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/pixel_emoji.py tests/test_pixel_emoji.py
git commit -m "Register :partly_cloudy: in the lowres emoji registry

Routes the weather widget's partly-cloudy icon through the same
slug-based draw path as the other weather icons. No hires variant
yet — bigsign keeps the block-expanded 8x8 sprite for now."
```

---

### Task 2: Add `pixel_emoji.draw_emoji_at` single-slug helper

**Why:** Extract the per-emoji branch of `draw_with_emoji` so widgets that draw a single icon (weather, future MLB rework, etc.) can opt into the hires/lowres dispatcher without going through the text-segment parser.

**Files:**
- Modify: `src/led_ticker/pixel_emoji.py` (add new function, after `draw_with_emoji`)
- Test: `tests/test_pixel_emoji.py` (append a `TestDrawEmojiAt` class)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_pixel_emoji.py`:

```python
class TestDrawEmojiAt:
    """Single-slug helper that picks hires on ScaledCanvas, lowres elsewhere."""

    def test_lowres_on_plain_canvas_returns_advance(self):
        """On a non-ScaledCanvas, lowres path is used. Returns
        sprite_width + EMOJI_PADDING."""
        from rgbmatrix import _StubCanvas

        from led_ticker.pixel_emoji import EMOJI_PADDING, draw_emoji_at

        canvas = _StubCanvas(width=160, height=16)
        advance = draw_emoji_at(canvas, "sun", x=0, y=4)
        # SUN is 8 wide
        assert advance == 8 + EMOJI_PADDING
        assert canvas.count_nonzero() > 0

    def test_hires_on_scaled_canvas_paints_to_real(self):
        """On a ScaledCanvas, hires path is used. The real canvas should
        receive 32x32-density sprite pixels — far more than scale^2 *
        lowres_count."""
        from led_ticker.pixel_emoji import draw_emoji_at
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _bigsign_real_canvas()
        sc = ScaledCanvas(real, scale=4)

        # Establish lowres pixel count on a plain canvas so we can compare.
        from rgbmatrix import _StubCanvas

        plain = _StubCanvas(width=64, height=64)
        draw_emoji_at(plain, "sun", x=0, y=0)
        lowres_count = plain.count_nonzero()
        # If hires fired, the real canvas should have noticeably more
        # painted pixels than scale^2 * lowres_count would imply
        # (lowres pixels are dense colored squares; hires has finer
        # detail). We just need a count strictly greater than
        # lowres_count to prove the SetPixel calls hit `real` directly,
        # not via the wrapper.
        draw_emoji_at(sc, "sun", x=0, y=0)
        # On the real bigsign canvas, hires sun paints individual LEDs
        # at native resolution.
        # Count real-canvas pixels by querying the stub directly.
        # _StubCanvas exposes _pixels; bigsign real canvas is the
        # rgbmatrix stub which also exposes it.
        assert getattr(real, "count_nonzero", lambda: 0)() > lowres_count

    def test_hires_falls_back_when_max_height_too_small(self):
        """A two-row caller passes max_emoji_height=4 (canvas.height // 2
        on a 16-tall logical canvas wrapped at scale=2). Hires sprite is
        32 // 2 = 16 logical tall, which exceeds 4 — must fall back to
        lowres so it doesn't overflow the row band."""
        from led_ticker.pixel_emoji import EMOJI_PADDING, draw_emoji_at
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _bigsign_real_canvas()
        sc = ScaledCanvas(real, scale=2)
        advance = draw_emoji_at(sc, "sun", x=0, y=0, max_emoji_height=4)
        # Lowres advance is 8 + EMOJI_PADDING; hires would be different
        # (16 logical at scale=2 etc.). We just assert the lowres value.
        assert advance == 8 + EMOJI_PADDING

    def test_unknown_slug_raises(self):
        """Drop-it-loud behavior: a typo'd slug raises KeyError instead
        of silently drawing nothing."""
        from rgbmatrix import _StubCanvas

        from led_ticker.pixel_emoji import draw_emoji_at

        canvas = _StubCanvas(width=160, height=16)
        with pytest.raises(KeyError):
            draw_emoji_at(canvas, "definitely_not_a_slug", x=0, y=0)

    def test_partly_cloudy_resolves_via_lowres(self):
        """partly_cloudy has no hires variant; even on a ScaledCanvas
        the helper should pick the lowres sprite without raising."""
        from led_ticker.pixel_emoji import EMOJI_PADDING, draw_emoji_at
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _bigsign_real_canvas()
        sc = ScaledCanvas(real, scale=4)
        advance = draw_emoji_at(sc, "partly_cloudy", x=0, y=0)
        # PARTLY_CLOUDY low-res is 8 wide
        assert advance == 8 + EMOJI_PADDING
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_pixel_emoji.py::TestDrawEmojiAt -v
```

Expected: FAIL on every test with `ImportError: cannot import name 'draw_emoji_at'`.

- [ ] **Step 3: Implement `draw_emoji_at`**

In `src/led_ticker/pixel_emoji.py`, add directly after `draw_with_emoji` (search for `def _draw_hires_emoji` and insert above it):

```python
def draw_emoji_at(
    canvas: Canvas,
    slug: str,
    x: int,
    y: int,
    *,
    max_emoji_height: int | None = None,
) -> int:
    """Draw a single emoji slug at logical (x, y). Returns the advance.

    Mirrors `draw_with_emoji`'s per-emoji dispatch but for a single icon
    with no surrounding text — convenient for widgets that draw exactly
    one icon at a known position (weather, future MLB rework, etc.).

    The advance is `sprite_width + EMOJI_PADDING`, matching
    `draw_with_emoji`'s convention so callers can `cursor_pos += advance`.

    Hires fires only when (a) `canvas` is a `ScaledCanvas`, (b) a hires
    variant exists in `HIRES_REGISTRY`, and (c) the sprite fits within
    `max_emoji_height` (if specified). Otherwise falls back to the 8x8
    low-res sprite painted via `canvas.SetPixel`.

    Raises `KeyError` if `slug` isn't in the low-res `EMOJI_REGISTRY`.
    """
    use_hires = isinstance(canvas, ScaledCanvas)

    hires: HiResEmoji | None = None
    if use_hires and slug in HIRES_REGISTRY:
        candidate = HIRES_REGISTRY[slug]
        logical_h = candidate.physical_size // canvas.scale
        if max_emoji_height is None or logical_h <= max_emoji_height:
            hires = candidate

    if hires is not None:
        _draw_hires_emoji(canvas, hires, x, y)
        return hires.logical_width(canvas.scale) + EMOJI_PADDING

    icon = _get_registry()[slug]  # KeyError on unknown slug — intentional
    iw = _emoji_width(icon)
    w = canvas.width
    h = getattr(canvas, "height", 16)
    for px, py, r, g, b in icon:
        dx = x + px
        dy = y + py
        if 0 <= dx < w and 0 <= dy < h:
            canvas.SetPixel(dx, dy, r, g, b)
    return iw + EMOJI_PADDING
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_pixel_emoji.py::TestDrawEmojiAt -v
```

Expected: 5 PASS.

- [ ] **Step 5: Run full test suite**

```bash
make test
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/pixel_emoji.py tests/test_pixel_emoji.py
git commit -m "Add pixel_emoji.draw_emoji_at single-slug helper

Extracts the per-emoji dispatch branch from draw_with_emoji so widgets
that draw a single icon at a known (x, y) can opt into hires/lowres
selection without going through the text-segment parser. Falls back to
lowres when no ScaledCanvas wrapper is present, when the slug has no
hires variant, or when max_emoji_height would be overrun."
```

---

### Task 3: Migrate `_match_condition` to return slug strings

**Why:** The new helper takes a slug string. Today `_match_condition` returns `PixelData` (the actual lowres tuple list). Since the consumer is changing in Task 4, we change the return contract here.

**Files:**
- Modify: `src/led_ticker/widgets/weather_icons.py:271-287` (`_match_condition`)
- Modify: `tests/test_weather_icons.py:19-75` (`TestMatchCondition`)

- [ ] **Step 1: Rewrite the existing tests to expect slug strings**

Replace the `TestMatchCondition` class in `tests/test_weather_icons.py` (lines 19-75) with:

```python
class TestMatchCondition:
    def test_sunny(self):
        assert _match_condition("Sunny") == "sun"

    def test_clear(self):
        assert _match_condition("Clear") == "sun"

    def test_partly_cloudy(self):
        assert _match_condition("Partly cloudy") == "partly_cloudy"

    def test_cloudy(self):
        assert _match_condition("Cloudy") == "cloud"

    def test_overcast(self):
        assert _match_condition("Overcast") == "cloud"

    def test_light_rain(self):
        assert _match_condition("Light rain") == "rain"

    def test_heavy_rain(self):
        assert _match_condition("Heavy rain") == "rain"

    def test_moderate_rain_shower(self):
        assert _match_condition("Moderate or heavy rain shower") == "rain"

    def test_drizzle(self):
        assert _match_condition("Light drizzle") == "rain"

    def test_light_snow(self):
        assert _match_condition("Light snow") == "snow"

    def test_blizzard(self):
        assert _match_condition("Blizzard") == "snow"

    def test_ice_pellets(self):
        assert _match_condition("Ice pellets") == "snow"

    def test_sleet(self):
        assert _match_condition("Light sleet") == "snow"

    def test_thunder(self):
        assert _match_condition("Moderate or heavy rain with thunder") == "thunder"

    def test_thundery_outbreaks(self):
        assert _match_condition("Thundery outbreaks possible") == "thunder"

    def test_fog(self):
        assert _match_condition("Fog") == "fog"

    def test_mist(self):
        assert _match_condition("Mist") == "fog"

    def test_freezing_fog(self):
        assert _match_condition("Freezing fog") == "fog"

    def test_unknown_defaults_to_sun(self):
        assert _match_condition("Something weird") == "sun"
```

Also remove the `SUN, CLOUD, PARTLY_CLOUDY, RAIN, SNOW, THUNDER, FOG` imports (top of file, lines 5-16) — they're no longer referenced. The remaining imports are `ICON_WIDTH`, `_match_condition`, and (temporarily, until Task 4) `draw_weather_icon`.

After this edit, the top of `tests/test_weather_icons.py` should read:

```python
"""Tests for weather icons."""

from rgbmatrix import _StubCanvas

from led_ticker.widgets.weather_icons import (
    ICON_WIDTH,
    _match_condition,
    draw_weather_icon,
)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_weather_icons.py::TestMatchCondition -v
```

Expected: 19 FAIL — all assert `_match_condition(...) == "sun"` etc., but it returns a `PixelData` list.

- [ ] **Step 3: Update `_match_condition` to return slug strings**

In `src/led_ticker/widgets/weather_icons.py`, replace the body of `_match_condition` (currently at line 271):

```python
def _match_condition(condition: str) -> str:
    """Map a WeatherAPI condition string to an emoji slug."""
    c = condition.lower()
    if "thunder" in c:
        return "thunder"
    if "snow" in c or "blizzard" in c or "ice" in c or "sleet" in c:
        return "snow"
    if "rain" in c or "drizzle" in c or "shower" in c:
        return "rain"
    if "fog" in c or "mist" in c:
        return "fog"
    if "partly" in c:
        return "partly_cloudy"
    if "cloud" in c or "overcast" in c:
        return "cloud"
    # Sunny, Clear, or anything else
    return "sun"
```

Also update the `PixelData` import at the top of the file — it's still used by the sprite-data constants, leave it. The function's return-type annotation is the only signature change.

- [ ] **Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_weather_icons.py::TestMatchCondition -v
```

Expected: 19 PASS.

- [ ] **Step 5: Run full test suite**

```bash
make test
```

Expected: all green. (`draw_weather_icon` still works, since it calls `_match_condition` only as `icon = _match_condition(...)` — but that's about to change in the same module. We patch it now to keep `draw_weather_icon` functional through this commit.)

Update `draw_weather_icon` in the same file to look up the sprite from a local mapping:

```python
def draw_weather_icon(canvas: Canvas, condition: str, x: int, y_offset: int = 4) -> int:
    """Draw an 8x8 weather icon on the canvas.

    Args:
        canvas: LED canvas with SetPixel(x, y, r, g, b)
        condition: WeatherAPI condition text (e.g., "Clear", "Light rain")
        x: left edge x position
        y_offset: top edge y position (default 4 centers 8px icon in 16px height)

    Returns:
        The x position after the icon (x + ICON_WIDTH + ICON_PADDING).
    """
    slug = _match_condition(condition)
    sprites: dict[str, PixelData] = {
        "sun": SUN,
        "cloud": CLOUD,
        "partly_cloudy": PARTLY_CLOUDY,
        "rain": RAIN,
        "snow": SNOW,
        "thunder": THUNDER,
        "fog": FOG,
    }
    icon = sprites[slug]
    for px, py, r, g, b in icon:
        canvas.SetPixel(x + px, y_offset + py, r, g, b)
    return x + ICON_WIDTH + ICON_PADDING
```

(This shim keeps the existing `TestDrawWeatherIcon` tests green for one commit, before Task 4 deletes the function entirely. Splitting the migration prevents one giant unreviewable commit.)

- [ ] **Step 6: Run full test suite again**

```bash
make test
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/widgets/weather_icons.py tests/test_weather_icons.py
git commit -m "_match_condition returns slug strings, not pixel data

Preparation for routing the weather widget's icon draw through
pixel_emoji.draw_emoji_at. The condition->slug mapping now matches
the EMOJI_REGISTRY's vocabulary; draw_weather_icon survives this
commit as a shim and is removed in the follow-up."
```

---

### Task 4: Refactor `weather.py` to use `draw_emoji_at`; delete `draw_weather_icon`

**Why:** This is the actual bug fix — the weather widget now picks hires sprites on `ScaledCanvas`. Splits the change off from Task 3 so the slug-migration commit and the route-change commit can be reviewed (and reverted) independently.

**Files:**
- Modify: `src/led_ticker/widgets/weather.py:169-179` (icon draw block in `draw()`)
- Modify: `src/led_ticker/widgets/weather_icons.py` (delete `draw_weather_icon`)
- Modify: `tests/test_weather_icons.py` (delete `TestDrawWeatherIcon`, drop unused imports)

- [ ] **Step 1: Write the failing tripwire test**

Append to `tests/test_widgets/test_weather.py`:

```python
class TestWeatherWidgetHiresOnScaledCanvas:
    """Tripwire for the weather widget's hires-on-bigsign path.

    Regression: pre-fix, draw_weather_icon called canvas.SetPixel on
    the lowres 8x8 sprite. On a ScaledCanvas at scale=4 the wrapper
    block-expanded each pixel into a 4x4 square — chunky 32x32 output
    instead of using the available 32x32 hires sprite. The fix routes
    icon draw through pixel_emoji.draw_emoji_at so HIRES_REGISTRY
    sprites paint at native resolution to the underlying real canvas.
    """

    def test_draw_uses_hires_sprite_on_scaled_canvas(self, monkeypatch):
        """On a ScaledCanvas (bigsign), the weather widget paints the
        hires sun sprite directly to the real canvas via _draw_hires_emoji
        — bypassing the wrapper's 4x4 block expansion. We assert by
        hooking _draw_hires_emoji and confirming it was called for the
        weather icon."""
        monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker import pixel_emoji
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.widgets.weather import WeatherWidget

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 8
        opts.parallel = 1
        opts.pixel_mapper_config = "U-mapper"
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        sc = ScaledCanvas(real, scale=4)

        calls: list[str] = []
        original = pixel_emoji._draw_hires_emoji

        def spy(canvas, hires, ix, iy):
            calls.append("hires")
            return original(canvas, hires, ix, iy)

        monkeypatch.setattr(pixel_emoji, "_draw_hires_emoji", spy)

        w = WeatherWidget(session=mock.Mock(), location="NYC", message="NYC")
        w.current_temp = 72
        w.weather = "Clear"  # -> "sun" -> SUN_HIRES exists
        w.draw(sc)

        assert calls, (
            "Expected pixel_emoji._draw_hires_emoji to fire for the weather "
            "icon on a ScaledCanvas. The widget is still using the old "
            "lowres-blit path."
        )

    def test_draw_uses_lowres_for_partly_cloudy_on_scaled_canvas(
        self, monkeypatch
    ):
        """partly_cloudy has no hires variant — ensure the widget
        gracefully falls back to lowres without crashing."""
        monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.widgets.weather import WeatherWidget

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 8
        opts.parallel = 1
        opts.pixel_mapper_config = "U-mapper"
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        sc = ScaledCanvas(real, scale=4)

        w = WeatherWidget(session=mock.Mock(), location="NYC", message="NYC")
        w.current_temp = 72
        w.weather = "Partly cloudy"
        # Should not raise.
        result_canvas, cursor_pos = w.draw(sc)
        assert cursor_pos > 0
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_weather.py::TestWeatherWidgetHiresOnScaledCanvas -v
```

Expected: `test_draw_uses_hires_sprite_on_scaled_canvas` FAILs with `assert calls` (the spy is never called). The `partly_cloudy` test may pass already through the existing `draw_weather_icon` shim — that's fine; both end up green after Task 4 lands.

- [ ] **Step 3: Update `weather.py` to call `draw_emoji_at`**

In `src/led_ticker/widgets/weather.py`, replace the `if self.show_icon:` block (currently lines 169-179) with:

```python
        if self.show_icon:
            from led_ticker.pixel_emoji import draw_emoji_at
            from led_ticker.widgets.weather_icons import _match_condition

            slug = _match_condition(self.weather)
            cursor_pos += draw_emoji_at(
                canvas,
                slug,
                int(cursor_pos),
                4 + y_offset,
            )
```

The `+= advance` style matches the `draw_text` calls above and below it; previously `draw_weather_icon` returned an absolute x and was assigned (not added) — that worked because its return was `x + ICON_WIDTH + ICON_PADDING`, exactly an advance from the input x. The new helper returns the same advance shape, so the math is identical and we get the conventional `+=` pattern.

- [ ] **Step 4: Run the new tripwires**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_weather.py::TestWeatherWidgetHiresOnScaledCanvas -v
```

Expected: 2 PASS.

- [ ] **Step 5: Delete `draw_weather_icon` and its tests**

In `src/led_ticker/widgets/weather_icons.py`, delete the `draw_weather_icon` function (currently around lines 290-305). The constants `ICON_WIDTH`, `ICON_HEIGHT`, `ICON_PADDING` stay — no callers remain in this repo, but they're cheap module-level constants that document the lowres icon footprint and may be used by tests or future tooling.

In `tests/test_weather_icons.py`:

- Drop `TestDrawWeatherIcon` (the entire class, currently lines 78-111).
- Drop the `draw_weather_icon` import (top of file).
- Drop the now-unused `_StubCanvas` import (only `TestDrawWeatherIcon` used it).

After this edit, `tests/test_weather_icons.py` should be entirely the `TestMatchCondition` class plus its imports:

```python
"""Tests for weather icons."""

from led_ticker.widgets.weather_icons import _match_condition


class TestMatchCondition:
    # ... (the 19 tests from Task 3)
```

- [ ] **Step 6: Run the full test suite**

```bash
make test
```

Expected: all green.

- [ ] **Step 7: Run lint**

```bash
make lint
```

Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/widgets/weather.py src/led_ticker/widgets/weather_icons.py tests/test_weather_icons.py tests/test_widgets/test_weather.py
git commit -m "Weather widget: use hires emoji on bigsign

Routes the icon draw through pixel_emoji.draw_emoji_at, which picks
the 32x32 hires sprite when the canvas is a ScaledCanvas and the slug
has a HIRES_REGISTRY entry (sun/cloud/rain/snow/thunder/fog).
partly_cloudy stays lowres on bigsign — no hires variant exists yet.

Removes draw_weather_icon (no longer needed); _match_condition stays
as the canonical condition->slug mapper. Adds a tripwire that hooks
pixel_emoji._draw_hires_emoji and asserts it fires when the weather
widget draws on a ScaledCanvas."
```

---

### Task 5: Update CLAUDE.md to document the new helper + the routing change

**Why:** CLAUDE.md is the project's living documentation; the "Inline Emoji" section currently describes only `draw_with_emoji` (text + emoji parser). Future contributors need to know `draw_emoji_at` exists for single-slug widget use.

**Files:**
- Modify: `CLAUDE.md` (the "Inline Emoji" / "Hi-res emoji on the bigsign" paragraphs)

- [ ] **Step 1: Add a sentence to the "Hi-res emoji on the bigsign" paragraph**

Locate in `CLAUDE.md` the paragraph starting `**Hi-res emoji on the bigsign**:` (around the inline-emoji documentation block). Append:

```
Widgets that draw a single icon at a known (x, y) — e.g. the weather widget's condition icon — should call `pixel_emoji.draw_emoji_at(canvas, slug, x, y)` rather than blitting their own pixel data; the helper handles the hires/lowres pick automatically. The `_match_condition` helper in `weather_icons.py` returns slug strings (`"sun"`, `"cloud"`, ...) that feed straight into `draw_emoji_at`.
```

- [ ] **Step 2: Run lint to confirm CLAUDE.md isn't accidentally broken**

(No CLAUDE.md linter; this is a no-op step. Skip if the project doesn't have a markdown lint rule.)

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "CLAUDE.md: document pixel_emoji.draw_emoji_at"
```

---

## Self-Review Checklist

- [x] **Spec coverage**:
  - "fix bug where weather doesn't use hires emoji on hires sign" → Tasks 2 + 4 (helper + routing change), Task 5 tripwire.
  - "opinion on dedup" → already addressed in conversation; the data is shared via `pixel_emoji._build_emoji_registry` already, only the draw path was duplicated. Task 4 dedupes the draw path.
  - `partly_cloudy` gap noted in conversation → Task 1 adds it to the lowres registry.
- [x] **Placeholder scan**: every step contains the actual code/command/expected output. No "TODO" / "implement later".
- [x] **Type consistency**: `draw_emoji_at(canvas, slug, x, y, *, max_emoji_height=None) -> int` — same name + signature in Task 2 (definition), Task 2 tests, Task 4 weather.py call site, Task 5 CLAUDE.md note. `_match_condition(condition: str) -> str` — same in Task 3 def + tests + Task 4 call site.
- [x] **Commit hygiene**: 5 commits, each independently green. Task 3 explicitly keeps `draw_weather_icon` working as a shim so the tree stays green between Tasks 3 and 4.
