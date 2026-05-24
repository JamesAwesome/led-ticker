# Shimmer Color Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `shimmer` color provider that animates a bright cosine-shaped spot sweeping left-to-right across text, pausing between sweeps, for an attention-grabbing glint effect similar to the Claude CLI thinking animation.

**Architecture:** New `Shimmer` class in `color_providers.py` (per-char, frame-animated). Wired through the existing coercion registry in `app/coercion.py` with shorthand color resolution for `base`/`shimmer` fields. Docs updated in `concepts/color-providers.mdx`.

**Tech Stack:** Pure Python, `math.cos`, `require_graphics()` for Color construction (matching `Gradient` pattern), `ColorProviderBase` for the class hierarchy guard.

---

## File structure

- **Modify:** `src/led_ticker/color_providers.py` — add `Shimmer` class after `Gradient`
- **Modify:** `src/led_ticker/app/coercion.py` — add `_SHIMMER_COLOR_SHORTHANDS` dict; wire `"shimmer"` into `_provider_from_style` registry + special-case translation block
- **Create:** `tests/test_shimmer_provider.py` — all Shimmer and coercion tests
- **Modify:** `docs/site/src/content/docs/concepts/color-providers.mdx` — add Shimmer section
- **Modify:** `CLAUDE.md` — add Shimmer to the ColorProvider table

---

### Task 1: `Shimmer` class in `color_providers.py`

**Files:**
- Modify: `src/led_ticker/color_providers.py` (add after `Gradient`, before EOF)
- Create: `tests/test_shimmer_provider.py`

#### Background: color_provider conventions

Every new provider must:
- Subclass `ColorProviderBase` (triggers a TypeError at class definition time if `frame_invariant` is missing)
- Declare `per_char: bool` and `frame_invariant: bool` as class attributes
- Implement `color_for(self, frame: int, char_index: int, total_chars: int) -> Color`

**Shimmer is `per_char = True`, `frame_invariant = False`, `restart_on_visit = False`** (continuous phase across `loop_count` repetitions, like `Rainbow`).

#### Math

`_SHIMMER_FPS = 30.0` is a module-level constant approximating the tick rate. All timing is frame-based so the provider stays consistent with the existing `frame` counter interface.

At each call, given `chars = max(total_chars, 1)`:
```
sweep_frames = chars / speed * _SHIMMER_FPS
pause_frames = pause * _SHIMMER_FPS
cycle_frames = sweep_frames + pause_frames

t = float(frame) % cycle_frames

if t >= sweep_frames:
    return self._base          # in the pause period

center = t / sweep_frames * chars  # spot center in char space
d = abs(char_index - center)
half_width = self.width / 2.0

if d >= half_width:
    return self._base          # outside the spot

# cosine bell: 1.0 at center, 0.0 at edge
factor = 0.5 + 0.5 * math.cos(math.pi * d / half_width)

r = int(base.red   + (shimmer.red   - base.red)   * factor)
g = int(base.green + (shimmer.green - base.green) * factor)
b = int(base.blue  + (shimmer.blue  - base.blue)  * factor)
return graphics.Color(r, g, b)
```

- `speed` in chars/second (default 14.0)
- `width` in chars — full width of the bright spot (default 8.0)
- `pause` in seconds between sweeps (default 0.5)

Constructor validation: `speed > 0`, `width > 0`, `pause >= 0`.

#### `color_providers.py` addition

Add this near the top of the file (with other imports):
```python
import math
```

Add after the `Gradient` class, before EOF:

```python
_SHIMMER_FPS = 30.0


class Shimmer(ColorProviderBase):
    """Cosine bright-spot sweep across text characters.

    A `shimmer_color` spot glides left-to-right over the `base_color`
    text, then pauses, then repeats. `speed` (chars/second), `width`
    (chars), and `pause` (seconds) tune the feel.
    """

    per_char: bool = True
    frame_invariant: bool = False
    restart_on_visit: bool = False

    def __init__(
        self,
        base_color: Color,
        shimmer_color: Color,
        speed: float = 14.0,
        width: float = 8.0,
        pause: float = 0.5,
    ) -> None:
        if speed <= 0:
            raise ValueError(f"Shimmer speed must be > 0; got {speed!r}")
        if width <= 0:
            raise ValueError(f"Shimmer width must be > 0; got {width!r}")
        if pause < 0:
            raise ValueError(f"Shimmer pause must be >= 0; got {pause!r}")
        self._base = base_color
        self._shimmer = shimmer_color
        self.speed = speed
        self.width = width
        self.pause = pause

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        from led_ticker._compat import require_graphics

        graphics = require_graphics()
        chars = max(total_chars, 1)
        sweep_frames = chars / self.speed * _SHIMMER_FPS
        pause_frames = self.pause * _SHIMMER_FPS
        cycle_frames = sweep_frames + pause_frames

        t = float(frame) % cycle_frames

        if t >= sweep_frames:
            return self._base

        center = t / sweep_frames * chars
        d = abs(char_index - center)
        half_width = self.width / 2.0

        if d >= half_width:
            return self._base

        factor = 0.5 + 0.5 * math.cos(math.pi * d / half_width)
        r = int(self._base.red + (self._shimmer.red - self._base.red) * factor)
        g = int(self._base.green + (self._shimmer.green - self._base.green) * factor)
        b = int(self._base.blue + (self._shimmer.blue - self._base.blue) * factor)
        return graphics.Color(r, g, b)
```

**Also add `Shimmer` to the `TestColorProviderBase.test_existing_providers_satisfy_base` test in `tests/test_color_providers.py`** — the existing test checks every provider is a subclass:
```python
# In tests/test_color_providers.py, class TestColorProviderBase:
def test_existing_providers_satisfy_base(self):
    from led_ticker.color_providers import (
        ColorCycle,
        ColorProviderBase,
        Gradient,
        Rainbow,
        Random,
        Shimmer,  # add this
        _ConstantColor,
    )

    for cls in (_ConstantColor, Random, Rainbow, ColorCycle, Gradient, Shimmer):  # add Shimmer
        assert issubclass(cls, ColorProviderBase), f"{cls.__name__} not a subclass"
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_shimmer_provider.py`:

```python
"""Tests for the Shimmer color provider."""

from __future__ import annotations

import math

import pytest
from rgbmatrix.graphics import Color

from led_ticker.color_providers import Shimmer


class TestShimmerConstruction:
    def test_defaults(self):
        p = Shimmer(base_color=Color(60, 60, 80), shimmer_color=Color(255, 255, 255))
        assert p.speed == 14.0
        assert p.width == 8.0
        assert p.pause == 0.5

    def test_explicit_params(self):
        p = Shimmer(
            base_color=Color(10, 10, 20),
            shimmer_color=Color(200, 200, 255),
            speed=10.0,
            width=5.0,
            pause=1.0,
        )
        assert p.speed == 10.0
        assert p.width == 5.0
        assert p.pause == 1.0

    def test_speed_zero_raises(self):
        with pytest.raises(ValueError, match="speed"):
            Shimmer(base_color=Color(0, 0, 0), shimmer_color=Color(255, 255, 255), speed=0)

    def test_speed_negative_raises(self):
        with pytest.raises(ValueError, match="speed"):
            Shimmer(base_color=Color(0, 0, 0), shimmer_color=Color(255, 255, 255), speed=-1)

    def test_width_zero_raises(self):
        with pytest.raises(ValueError, match="width"):
            Shimmer(base_color=Color(0, 0, 0), shimmer_color=Color(255, 255, 255), width=0)

    def test_pause_negative_raises(self):
        with pytest.raises(ValueError, match="pause"):
            Shimmer(
                base_color=Color(0, 0, 0),
                shimmer_color=Color(255, 255, 255),
                pause=-0.1,
            )

    def test_pause_zero_is_valid(self):
        p = Shimmer(base_color=Color(0, 0, 0), shimmer_color=Color(255, 255, 255), pause=0)
        assert p.pause == 0


class TestShimmerClassAttributes:
    def test_per_char_is_true(self):
        assert Shimmer.per_char is True

    def test_frame_invariant_is_false(self):
        assert Shimmer.frame_invariant is False

    def test_restart_on_visit_is_false(self):
        assert Shimmer.restart_on_visit is False


class TestShimmerColorFor:
    """color_for behavior: center of spot, edge, outside, pause period."""

    def _make(self, **kwargs):
        return Shimmer(
            base_color=Color(0, 0, 0),
            shimmer_color=Color(255, 255, 255),
            **kwargs,
        )

    def test_center_of_spot_is_brighter_than_base(self):
        """char at spot center should be significantly brighter than base."""
        # With speed=10, width=4, pause=0, total_chars=10:
        # sweep_frames = 10/10 * 30 = 30 frames
        # center at frame 0 → char 0
        p = self._make(speed=10.0, width=4.0, pause=0)
        # frame=0, center=0.0, char_index=0 → d=0 → factor=1.0 → full shimmer
        c = p.color_for(frame=0, char_index=0, total_chars=10)
        assert c.red > 200, f"center char should be near shimmer color, got r={c.red}"
        assert c.green > 200
        assert c.blue > 200

    def test_outside_spot_returns_base(self):
        """char outside the spot width returns base color exactly."""
        p = self._make(speed=10.0, width=2.0, pause=0)
        # sweep_frames=30, frame=0 → center=0, half_width=1.0
        # char_index=5 → d=5, 5 >= 1.0 → returns base
        c = p.color_for(frame=0, char_index=5, total_chars=10)
        assert (c.red, c.green, c.blue) == (0, 0, 0)

    def test_during_pause_returns_base(self):
        """During the pause period every char returns base color."""
        # speed=10, pause=1.0, total_chars=10
        # sweep_frames = 10/10 * 30 = 30; pause_frames = 30; cycle = 60
        # frame=45 → t=45, 45 >= 30 → in pause
        p = self._make(speed=10.0, width=4.0, pause=1.0)
        for char_index in range(10):
            c = p.color_for(frame=45, char_index=char_index, total_chars=10)
            assert (c.red, c.green, c.blue) == (0, 0, 0), (
                f"char {char_index}: expected base during pause, got {c.red, c.green, c.blue}"
            )

    def test_edge_of_spot_is_darker_than_center(self):
        """char at edge of spot (d = half_width - epsilon) is dimmer than center."""
        p = self._make(speed=10.0, width=4.0, pause=0)
        # frame=0, center=0, half_width=2
        c_center = p.color_for(frame=0, char_index=0, total_chars=10)
        # char_index=1 → d=1, still inside (1 < 2); factor = 0.5 + 0.5*cos(π/2) = 0.5
        c_edge = p.color_for(frame=0, char_index=1, total_chars=10)
        assert c_center.red > c_edge.red, "center should be brighter than edge"

    def test_different_chars_get_different_colors_during_sweep(self):
        """Two chars at different distances from the spot center differ."""
        p = self._make(speed=10.0, width=8.0, pause=0)
        # frame=0: center=0; both chars 0 and 3 are inside, but d differs
        c0 = p.color_for(frame=0, char_index=0, total_chars=10)
        c3 = p.color_for(frame=0, char_index=3, total_chars=10)
        assert (c0.red, c0.green, c0.blue) != (c3.red, c3.green, c3.blue)

    def test_total_chars_one_does_not_divide_by_zero(self):
        """Single-char text must not raise ZeroDivisionError."""
        p = self._make(speed=10.0, width=4.0, pause=0)
        # Should not raise
        c = p.color_for(frame=0, char_index=0, total_chars=1)
        assert c is not None

    def test_cycle_repeats(self):
        """After one full cycle (sweep + pause), frame 0 and frame cycle_end give same output."""
        # speed=10, pause=0, total_chars=10: sweep_frames=30, cycle=30
        p = self._make(speed=10.0, width=4.0, pause=0)
        c_start = p.color_for(frame=0, char_index=0, total_chars=10)
        c_cycle = p.color_for(frame=30, char_index=0, total_chars=10)
        assert (c_start.red, c_start.green, c_start.blue) == (
            c_cycle.red, c_cycle.green, c_cycle.blue
        )

    def test_colored_base_and_shimmer(self):
        """With non-black base and non-white shimmer, interpolation is correct."""
        p = Shimmer(
            base_color=Color(100, 0, 0),  # dark red
            shimmer_color=Color(255, 255, 0),  # yellow
            speed=10.0,
            width=4.0,
            pause=0,
        )
        # frame=0, char_index=0 → factor=1.0 → full shimmer
        c = p.color_for(frame=0, char_index=0, total_chars=10)
        assert c.red == 255
        assert c.green == 255
        assert c.blue == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
pytest tests/test_shimmer_provider.py -v
```

Expected: FAIL with `ImportError: cannot import name 'Shimmer'`

- [ ] **Step 3: Add `import math` to `color_providers.py`**

In `src/led_ticker/color_providers.py`, add `import math` with the other imports at the top.

Current imports section:
```python
from __future__ import annotations

import random
from typing import Protocol

from led_ticker._types import Color
from led_ticker.color_lut import hue_color
```

Add `import math` after `import random`:
```python
from __future__ import annotations

import math
import random
from typing import Protocol

from led_ticker._types import Color
from led_ticker.color_lut import hue_color
```

- [ ] **Step 4: Add `_SHIMMER_FPS` constant and `Shimmer` class to `color_providers.py`**

Add after the `Gradient` class (just before EOF):

```python
_SHIMMER_FPS = 30.0


class Shimmer(ColorProviderBase):
    """Cosine bright-spot sweep across text characters.

    A `shimmer_color` spot glides left-to-right over the `base_color`
    text, then pauses, then repeats. `speed` (chars/second), `width`
    (chars), and `pause` (seconds) tune the feel.
    """

    per_char: bool = True
    frame_invariant: bool = False
    restart_on_visit: bool = False

    def __init__(
        self,
        base_color: Color,
        shimmer_color: Color,
        speed: float = 14.0,
        width: float = 8.0,
        pause: float = 0.5,
    ) -> None:
        if speed <= 0:
            raise ValueError(f"Shimmer speed must be > 0; got {speed!r}")
        if width <= 0:
            raise ValueError(f"Shimmer width must be > 0; got {width!r}")
        if pause < 0:
            raise ValueError(f"Shimmer pause must be >= 0; got {pause!r}")
        self._base = base_color
        self._shimmer = shimmer_color
        self.speed = speed
        self.width = width
        self.pause = pause

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        from led_ticker._compat import require_graphics

        graphics = require_graphics()
        chars = max(total_chars, 1)
        sweep_frames = chars / self.speed * _SHIMMER_FPS
        pause_frames = self.pause * _SHIMMER_FPS
        cycle_frames = sweep_frames + pause_frames

        t = float(frame) % cycle_frames

        if t >= sweep_frames:
            return self._base

        center = t / sweep_frames * chars
        d = abs(char_index - center)
        half_width = self.width / 2.0

        if d >= half_width:
            return self._base

        factor = 0.5 + 0.5 * math.cos(math.pi * d / half_width)
        r = int(self._base.red + (self._shimmer.red - self._base.red) * factor)
        g = int(self._base.green + (self._shimmer.green - self._base.green) * factor)
        b = int(self._base.blue + (self._shimmer.blue - self._base.blue) * factor)
        return graphics.Color(r, g, b)
```

- [ ] **Step 5: Add `Shimmer` to `test_existing_providers_satisfy_base` in `tests/test_color_providers.py`**

In `tests/test_color_providers.py`, find `test_existing_providers_satisfy_base` and add `Shimmer` to the import and the loop:

```python
def test_existing_providers_satisfy_base(self):
    from led_ticker.color_providers import (
        ColorCycle,
        ColorProviderBase,
        Gradient,
        Rainbow,
        Random,
        Shimmer,
        _ConstantColor,
    )

    for cls in (_ConstantColor, Random, Rainbow, ColorCycle, Gradient, Shimmer):
        assert issubclass(cls, ColorProviderBase), f"{cls.__name__} not a subclass"
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
pytest tests/test_shimmer_provider.py tests/test_color_providers.py -v
```

Expected: All PASS

- [ ] **Step 7: Run the full test suite to check for regressions**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
pytest --tb=short -q
```

Expected: All existing tests continue to pass; new tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/color_providers.py tests/test_shimmer_provider.py tests/test_color_providers.py
git commit -m "feat: add Shimmer color provider (cosine bright-spot sweep)"
```

---

### Task 2: Coercion wiring for `shimmer` in `coercion.py`

**Files:**
- Modify: `src/led_ticker/app/coercion.py`
- Modify: `tests/test_shimmer_provider.py` (add `TestShimmerCoercion` class)

#### Background: how `_provider_from_style` works

`_provider_from_style(style, kwargs)` is the dispatch point for `font_color = {style = "...", ...}`. It:
1. Looks up `style` in `registry` (maps to `(cls, allowed_kwargs)`)
2. Does special-case translation for `gradient` (pops `from`/`to`, pushes `from_color`/`to_color`) and `color_cycle` (similar hue translation)
3. Checks for unknown kwargs against `allowed_kwargs`
4. Returns `cls(**kwargs)`

For `shimmer`:
- User-visible keys: `base`, `shimmer`, `speed`, `width`, `pause`
- Translated to constructor args: `base_color`, `shimmer_color`, `speed`, `width`, `pause`
- `base` defaults to `[60, 60, 80]` (dim blue-gray) if absent
- `shimmer` defaults to `[255, 255, 255]` (white) if absent
- Both `base` and `shimmer` accept either `[r, g, b]` lists or string shorthands

#### String shorthands (`_SHIMMER_COLOR_SHORTHANDS`)

```python
_SHIMMER_COLOR_SHORTHANDS: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255),
    "gold": (255, 200, 50),
    "blue": (100, 180, 255),
    "cyan": (0, 220, 220),
}
```

Add this as a module-level constant in `coercion.py`, after the `_RAW_COLOR_KEYS` definition.

#### Changes to `_provider_from_style`

1. Add `Shimmer` to the local import:
   ```python
   from led_ticker.color_providers import (
       ColorCycle,
       Gradient,
       Rainbow,
       Random,
       Shimmer,
   )
   ```

2. Add to `registry`:
   ```python
   "shimmer": (Shimmer, {"speed", "width", "pause", "base_color", "shimmer_color"}),
   ```
   Note: `allowed_kwargs` uses the post-translation names (`base_color`, `shimmer_color`) because the unknown-kwargs check runs after the special-case translation. `base` and `shimmer` are popped in the special-case block before reaching the check.

3. Add to `_user_allowed` (used in error messages):
   ```python
   "shimmer": {"base", "shimmer", "speed", "width", "pause"},
   ```

4. Add the shimmer special-case translation block after the `color_cycle` block (before the unknown-kwargs check):

```python
if style == "shimmer":
    base_val = kwargs.pop("base", None)
    shimmer_val = kwargs.pop("shimmer", None)

    # Resolve base color (default: dim blue-gray)
    if base_val is None:
        base_rgb: tuple[int, int, int] = (60, 60, 80)
    elif isinstance(base_val, str):
        if base_val not in _SHIMMER_COLOR_SHORTHANDS:
            raise ValueError(
                f"font_color shimmer 'base' shorthand {base_val!r} unknown; "
                f"available: {sorted(_SHIMMER_COLOR_SHORTHANDS)} or use [r, g, b]"
            )
        base_rgb = _SHIMMER_COLOR_SHORTHANDS[base_val]
    else:
        base_rgb = _validate_rgb(base_val, "font_color shimmer 'base'")

    # Resolve shimmer (highlight) color (default: white)
    if shimmer_val is None:
        shimmer_rgb: tuple[int, int, int] = (255, 255, 255)
    elif isinstance(shimmer_val, str):
        if shimmer_val not in _SHIMMER_COLOR_SHORTHANDS:
            raise ValueError(
                f"font_color shimmer 'shimmer' shorthand {shimmer_val!r} unknown; "
                f"available: {sorted(_SHIMMER_COLOR_SHORTHANDS)} or use [r, g, b]"
            )
        shimmer_rgb = _SHIMMER_COLOR_SHORTHANDS[shimmer_val]
    else:
        shimmer_rgb = _validate_rgb(shimmer_val, "font_color shimmer 'shimmer'")

    kwargs["base_color"] = graphics.Color(*base_rgb)
    kwargs["shimmer_color"] = graphics.Color(*shimmer_rgb)
```

Also update the error message in the unknown-style branch to reference `"shimmer"`:
```python
raise ValueError(
    f"unknown font_color style {style!r}; available: {sorted(registry.keys())}"
)
```
This already includes it once `"shimmer"` is in `registry`.

- [ ] **Step 1: Write the failing coercion tests**

Add `TestShimmerCoercion` class to `tests/test_shimmer_provider.py`:

```python
class TestShimmerCoercion:
    """_coerce_color_provider wiring for shimmer style."""

    def _coerce(self, value):
        from led_ticker.app.coercion import _coerce_color_provider
        return _coerce_color_provider(value)

    def test_basic_shimmer_dict(self):
        """Minimal dict returns a Shimmer instance."""
        from led_ticker.color_providers import Shimmer

        p = self._coerce({"style": "shimmer"})
        assert isinstance(p, Shimmer)

    def test_defaults_applied(self):
        """Absent base/shimmer get their documented defaults."""
        from led_ticker.color_providers import Shimmer

        p = self._coerce({"style": "shimmer"})
        assert isinstance(p, Shimmer)
        assert (p._base.red, p._base.green, p._base.blue) == (60, 60, 80)
        assert (p._shimmer.red, p._shimmer.green, p._shimmer.blue) == (255, 255, 255)
        assert p.speed == 14.0
        assert p.width == 8.0
        assert p.pause == 0.5

    def test_base_rgb_list(self):
        p = self._coerce({"style": "shimmer", "base": [100, 50, 200]})
        assert (p._base.red, p._base.green, p._base.blue) == (100, 50, 200)

    def test_shimmer_rgb_list(self):
        p = self._coerce({"style": "shimmer", "shimmer": [255, 220, 100]})
        assert (p._shimmer.red, p._shimmer.green, p._shimmer.blue) == (255, 220, 100)

    def test_base_string_white(self):
        p = self._coerce({"style": "shimmer", "base": "white"})
        assert (p._base.red, p._base.green, p._base.blue) == (255, 255, 255)

    def test_shimmer_string_gold(self):
        p = self._coerce({"style": "shimmer", "shimmer": "gold"})
        assert (p._shimmer.red, p._shimmer.green, p._shimmer.blue) == (255, 200, 50)

    def test_shimmer_string_blue(self):
        p = self._coerce({"style": "shimmer", "shimmer": "blue"})
        assert (p._shimmer.red, p._shimmer.green, p._shimmer.blue) == (100, 180, 255)

    def test_shimmer_string_cyan(self):
        p = self._coerce({"style": "shimmer", "shimmer": "cyan"})
        assert (p._shimmer.red, p._shimmer.green, p._shimmer.blue) == (0, 220, 220)

    def test_unknown_base_shorthand_raises(self):
        with pytest.raises(ValueError, match="unknown"):
            self._coerce({"style": "shimmer", "base": "magenta"})

    def test_unknown_shimmer_shorthand_raises(self):
        with pytest.raises(ValueError, match="unknown"):
            self._coerce({"style": "shimmer", "shimmer": "magenta"})

    def test_custom_speed_width_pause(self):
        p = self._coerce({
            "style": "shimmer",
            "speed": 20.0,
            "width": 5.0,
            "pause": 1.5,
        })
        assert p.speed == 20.0
        assert p.width == 5.0
        assert p.pause == 1.5

    def test_unknown_kwarg_raises(self):
        with pytest.raises(ValueError, match="unknown"):
            self._coerce({"style": "shimmer", "bogus": 42})

    def test_invalid_base_rgb_raises(self):
        with pytest.raises(ValueError):
            self._coerce({"style": "shimmer", "base": [300, 0, 0]})

    def test_invalid_shimmer_rgb_raises(self):
        with pytest.raises(ValueError):
            self._coerce({"style": "shimmer", "shimmer": [0, 0, -1]})

    def test_all_four_shorthands_resolve(self):
        """Each shorthand in _SHIMMER_COLOR_SHORTHANDS resolves without error."""
        from led_ticker.app.coercion import _SHIMMER_COLOR_SHORTHANDS

        for name in _SHIMMER_COLOR_SHORTHANDS:
            p = self._coerce({"style": "shimmer", "shimmer": name})
            expected = _SHIMMER_COLOR_SHORTHANDS[name]
            assert (p._shimmer.red, p._shimmer.green, p._shimmer.blue) == expected, (
                f"shorthand {name!r} did not resolve to {expected}"
            )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
pytest tests/test_shimmer_provider.py::TestShimmerCoercion -v
```

Expected: FAIL with `ValueError: unknown font_color style 'shimmer'`

- [ ] **Step 3: Add `_SHIMMER_COLOR_SHORTHANDS` to `coercion.py`**

In `src/led_ticker/app/coercion.py`, after the `_RAW_COLOR_KEYS` definition (around line 45), add:

```python
_SHIMMER_COLOR_SHORTHANDS: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255),
    "gold": (255, 200, 50),
    "blue": (100, 180, 255),
    "cyan": (0, 220, 220),
}
```

- [ ] **Step 4: Wire `shimmer` into `_provider_from_style` in `coercion.py`**

In `src/led_ticker/app/coercion.py`, in the `_provider_from_style` function:

**4a.** Add `Shimmer` to the local import:
```python
from led_ticker.color_providers import (
    ColorCycle,
    Gradient,
    Rainbow,
    Random,
    Shimmer,
)
```

**4b.** Add to the `registry` dict:
```python
"shimmer": (Shimmer, {"speed", "width", "pause", "base_color", "shimmer_color"}),
```

**4c.** Add to `_user_allowed`:
```python
"shimmer": {"base", "shimmer", "speed", "width", "pause"},
```

**4d.** Add the shimmer special-case translation block after the `if style == "color_cycle":` block and before `unknown = set(kwargs.keys()) - allowed_kwargs`:

```python
if style == "shimmer":
    base_val = kwargs.pop("base", None)
    shimmer_val = kwargs.pop("shimmer", None)

    if base_val is None:
        base_rgb: tuple[int, int, int] = (60, 60, 80)
    elif isinstance(base_val, str):
        if base_val not in _SHIMMER_COLOR_SHORTHANDS:
            raise ValueError(
                f"font_color shimmer 'base' shorthand {base_val!r} unknown; "
                f"available: {sorted(_SHIMMER_COLOR_SHORTHANDS)} or use [r, g, b]"
            )
        base_rgb = _SHIMMER_COLOR_SHORTHANDS[base_val]
    else:
        base_rgb = _validate_rgb(base_val, "font_color shimmer 'base'")

    if shimmer_val is None:
        shimmer_rgb: tuple[int, int, int] = (255, 255, 255)
    elif isinstance(shimmer_val, str):
        if shimmer_val not in _SHIMMER_COLOR_SHORTHANDS:
            raise ValueError(
                f"font_color shimmer 'shimmer' shorthand {shimmer_val!r} unknown; "
                f"available: {sorted(_SHIMMER_COLOR_SHORTHANDS)} or use [r, g, b]"
            )
        shimmer_rgb = _SHIMMER_COLOR_SHORTHANDS[shimmer_val]
    else:
        shimmer_rgb = _validate_rgb(shimmer_val, "font_color shimmer 'shimmer'")

    kwargs["base_color"] = graphics.Color(*base_rgb)
    kwargs["shimmer_color"] = graphics.Color(*shimmer_rgb)
```

- [ ] **Step 5: Run coercion tests to verify they pass**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
pytest tests/test_shimmer_provider.py -v
```

Expected: All PASS

- [ ] **Step 6: Run full suite**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
pytest --tb=short -q
```

Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/app/coercion.py tests/test_shimmer_provider.py
git commit -m "feat: wire shimmer color provider into coercion with string shorthands"
```

---

### Task 3: Docs and CLAUDE.md

**Files:**
- Modify: `docs/site/src/content/docs/concepts/color-providers.mdx`
- Modify: `CLAUDE.md`

No TDD step — these are documentation changes. Verify by reading the files after edit.

#### Changes to `color-providers.mdx`

1. **Update the frontmatter description** from "Constant, rainbow, gradient, color_cycle, and random" to include "shimmer".

2. **Update the intro paragraph** (line 10) — add shimmer to the list of providers.

3. **Update the provider table** — add a Shimmer row.

4. **Add a `## Shimmer` section** after the `## Gradient` section and before `## Random`.

5. **Update the "Which to use" section** — add a Shimmer bullet.

**Updated frontmatter:**
```
description: Constant, rainbow, gradient, color_cycle, shimmer, and random — how font_color accepts more than just an RGB list.
```

**Updated intro paragraph (replace lines 10–10):**
```
`font_color` accepts six forms: a `[r, g, b]` list (constant), the string shorthands `"rainbow"`, `"color_cycle"`, `"shimmer"`, and `"random"`, or an inline table for a gradient, a ranged color cycle, or a tuned shimmer. The first three cover most signs. The same field on `top_color` / `bottom_color` for `two_row` and image widgets behaves identically — pick once per widget, swap providers without changing anything else.
```

**Updated table** (add Shimmer row after Gradient):
```
| Provider         | Syntax                                                                       | Per-char? | Animates?                          |
| ---------------- | ---------------------------------------------------------------------------- | --------- | ---------------------------------- |
| Constant         | `[r, g, b]`                                                                  | no        | no                                 |
| Rainbow          | `"rainbow"`                                                                  | **yes**   | yes — hue sweeps per frame         |
| ColorCycle       | `"color_cycle"`                                                              | no        | yes — whole-string hue rotation    |
| ColorCycle range | `{style = "color_cycle", from = [...], to = [...], speed=N}`                 | no        | yes — restricted hue arc           |
| Gradient         | `{style = "gradient", from = [...], to = [...]}`                             | **yes**   | no — frozen interpolation          |
| Shimmer          | `"shimmer"` or `{style = "shimmer", shimmer = "gold", ...}`                 | **yes**   | yes — bright-spot sweep with pause |
| Random           | `"random"`                                                                   | no        | no — picks once on visit           |
```

**New `## Shimmer` section** — insert between `## Gradient` and `## Random`:

```mdx
## Shimmer

A bright spot glides left-to-right across the text — one `shimmer_color` highlight sweeping over a `base_color` rest state — then pauses, then repeats. The spot fades in and out with a cosine curve so it blends smoothly rather than clipping abruptly.

<TomlExample
  code={`[[playlist.section.widget]]
type = "message"
text = "Now Hiring"
font_color = "shimmer"`}
/>

`"shimmer"` as a plain string uses the defaults: dim blue-gray base, white highlight, 14 chars/second, 8-char-wide spot, 0.5 s pause between sweeps. Tune with an inline table:

<TomlExample
  code={`[[playlist.section.widget]]
type = "message"
text = "Grand Opening"
font_color = {style = "shimmer", base = [40, 40, 60], shimmer = "gold", speed = 10, width = 6, pause = 1.0}`}
/>

| Field     | Default       | Description                                                    |
| --------- | ------------- | -------------------------------------------------------------- |
| `base`    | `[60, 60, 80]`| Rest color. `[r, g, b]` or a shorthand: `"white"`, `"gold"`, `"blue"`, `"cyan"`. |
| `shimmer` | `"white"`     | Highlight color. Same formats as `base`.                       |
| `speed`   | `14.0`        | Chars per second the spot travels. Lower = slower, dreamier.   |
| `width`   | `8.0`         | Spot width in chars. Wider = broader glow; narrower = sharper. |
| `pause`   | `0.5`         | Seconds of rest (base color only) between sweeps.              |

Shimmer is a continuous-phase provider — it does not reset between `loop_count` repetitions, so the sweep keeps flowing across playlist loops rather than snapping back to the start.

**Shimmer with a dark base color:** The base defaults to a dark blue-gray (`[60, 60, 80]`). If you want truly black resting characters, set `base = [0, 0, 0]`. High-contrast setups (dark base, bright shimmer) look best; a light base with a slightly-brighter shimmer produces a subtle, professional feel.
```

**Updated "Which to use" section** — add:
```
- **Shimmer** — a gliding bright-spot sweep; good for drawing attention to a single message, "now open" signage, or any case where you want motion without full-rainbow energy.
```

#### Changes to `CLAUDE.md`

Find the ColorProvider section in `CLAUDE.md` (likely a table or list of providers). Add `Shimmer` as an entry:

```
- `Shimmer` — cosine bright-spot sweep. `per_char=True`, `frame_invariant=False`, `restart_on_visit=False`. Fields: `base_color` (Color), `shimmer_color` (Color), `speed` (float, chars/sec, default 14.0), `width` (float, chars, default 8.0), `pause` (float, seconds, default 0.5). Wired in `coercion.py`; TOML keys `base`/`shimmer` accept `[r,g,b]` or string shorthands (white, gold, blue, cyan).
```

- [ ] **Step 1: Update `docs/site/src/content/docs/concepts/color-providers.mdx`**

Apply all changes described above:
- Update frontmatter description
- Update intro paragraph
- Add Shimmer row to the provider table
- Add `## Shimmer` section between Gradient and Random
- Add Shimmer to the "Which to use" list

- [ ] **Step 2: Update `CLAUDE.md`**

Add Shimmer entry to the ColorProvider section.

- [ ] **Step 3: Verify by reading the changed files**

```bash
grep -n "shimmer\|Shimmer" docs/site/src/content/docs/concepts/color-providers.mdx | head -20
grep -n "shimmer\|Shimmer" CLAUDE.md | head -10
```

Expected: shimmer appears in the table, in the new section, and in CLAUDE.md.

- [ ] **Step 4: Run full test suite one final time**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
pytest --tb=short -q
```

Expected: All pass (docs changes don't affect test suite).

- [ ] **Step 5: Commit**

```bash
git add docs/site/src/content/docs/concepts/color-providers.mdx CLAUDE.md
git commit -m "docs: add Shimmer color provider to color-providers page and CLAUDE.md"
```
