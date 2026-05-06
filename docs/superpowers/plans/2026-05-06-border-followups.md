# Rainbow Border PR — Deferred Item Cleanup

> **Status: planning. Four small follow-ups from PR #5's review, batched
> into one branch + PR since each is trivial. Should land as a single
> commit if everything stays clean; can be split if any one item grows.**

**Goal:** Close out the four deferred items from the rainbow-border
PR review so nothing's left dangling. None of these block anything;
this is just hygiene.

**Branch:** `fix/border-followups` (off main).

---

## Items

### 1. Test gap — per-frame cycling at char_offset=0 (~5 LOC)

`test_char_offset_zero_uniform_per_frame` asserts that with
`char_offset=0` every perimeter pixel shares one hue at frame=0
(synchronized whole-border cycle). It does NOT assert that the
shared hue cycles across frames. Add a sister test that paints at
two different frames and asserts the (uniform) color differs.

**File**: `tests/test_borders.py` — add to `TestRainbowChaseBorder`.

```python
def test_char_offset_zero_cycles_across_frames(self):
    """With char_offset=0 and speed>0, all perimeter pixels share
    one hue per frame, but the hue changes between frames. Pairs
    with `test_char_offset_zero_uniform_per_frame`."""
    c0 = _StubCanvas(20, 8)
    c1 = _StubCanvas(20, 8)
    RainbowChaseBorder(char_offset=0, speed=4).paint(c0, frame_count=0)
    RainbowChaseBorder(char_offset=0, speed=4).paint(c1, frame_count=10)
    # Each canvas has a single uniform color
    color0 = next(iter(set(c0.pixels.values())))
    color1 = next(iter(set(c1.pixels.values())))
    assert color0 != color1, (
        f"Expected the synchronized cycle to advance; got identical "
        f"hue {color0} at frame=0 and frame=10."
    )
```

### 2. `speed=0` should be frame_invariant (~10 LOC)

When a `RainbowChaseBorder` is constructed with `speed=0`, the
chase doesn't advance — output is genuinely identical every frame.
But `frame_invariant` is a hardcoded class-level `False`, so any
future fast-path gate would over-render this case. Convert the
flag to an instance-level property that returns True when speed
and char_offset combine to produce frame-invariant output.

The condition: `frame_invariant = (speed == 0)`. (`char_offset` is
indexed by perimeter position, not frame, so it doesn't affect
frame-invariance — only `speed` does.)

**File**: `src/led_ticker/borders.py` — `RainbowChaseBorder` class.

```python
class RainbowChaseBorder:
    # ... (no class-level frame_invariant)

    def __init__(self, speed=4, char_offset=6, thickness=1):
        self.speed = speed
        self.char_offset = char_offset
        self.thickness = thickness

    @property
    def frame_invariant(self) -> bool:
        """True when speed is 0 — the chase doesn't advance per
        frame, so paint output is identical every tick. Lets a
        future fast-path gate skip per-tick redraws on a pinned
        rainbow without animation."""
        return self.speed == 0
```

`ConstantBorder.frame_invariant` stays as a class-level `True`
(no params can change it).

**Tests** to add in `TestRainbowChaseBorder`:

```python
def test_frame_invariant_dynamic_for_speed_zero(self):
    assert RainbowChaseBorder(speed=0).frame_invariant is True

def test_frame_invariant_false_for_default_speed(self):
    # Existing test_frame_invariant_is_false still applies; rename
    # for clarity.
    assert RainbowChaseBorder(speed=4).frame_invariant is False
```

The existing `test_frame_invariant_is_false` either gets renamed or
absorbed into the new dynamic check.

### 3. Out-of-range RGB int validation in `_coerce_border` (~10 LOC)

`_coerce_border([300, -50, 999])` currently passes through to
`ConstantBorder._rgb` unmodified. The reviewer flagged this. The
fix: validate each component is `0 <= c <= 255`.

**Scope decision**: do this for `_coerce_border` ONLY, not for
`_coerce_color_provider` (which has the same gap but is widely
used and changing it would be a broader hardening pass). Document
in the commit message that the pattern can be extended to the
other coercion sites in a follow-up if desired.

**File**: `src/led_ticker/app.py` — `_coerce_border`.

Currently:
```python
if (
    isinstance(value, list | tuple)
    and len(value) == 3
    and all(isinstance(c, int) and not isinstance(c, bool) for c in value)
):
    return ConstantBorder(color=tuple(value))
```

Add a range check after the type check, raise on out-of-range:
```python
if isinstance(value, list | tuple) and len(value) == 3:
    # Reject bool first (bool is an int subclass)
    if not all(isinstance(c, int) and not isinstance(c, bool) for c in value):
        # Fall through to the generic error below — keeps the existing
        # "must be a string, table, or [r,g,b]" message for non-int lists.
        pass
    elif not all(0 <= c <= 255 for c in value):
        raise ValueError(
            f"border RGB values must be 0-255; got {list(value)!r}"
        )
    else:
        return ConstantBorder(color=tuple(value))
```

(Restructure cleanly — the current early-return path skips validation;
need to push the int-check INTO the validation arm.)

**Tests** to add in `TestCoerceBorder`:

```python
def test_out_of_range_rgb_rejected(self):
    from led_ticker.app import _coerce_border

    with pytest.raises(ValueError, match="0-255"):
        _coerce_border([300, 50, 100])
    with pytest.raises(ValueError, match="0-255"):
        _coerce_border([0, -1, 100])
    with pytest.raises(ValueError, match="0-255"):
        _coerce_border([255, 256, 0])

def test_inline_constant_table_validates_color_range(self):
    """Range check applies to the inline-table form too."""
    from led_ticker.app import _coerce_border

    with pytest.raises(ValueError, match="0-255"):
        _coerce_border({"style": "constant", "color": [256, 0, 0]})
```

The inline-table form needs the same check inside the `style ==
"constant"` branch.

### 4. TickerCountdown border field (~15 LOC)

Wire `border` into `TickerCountdown` mirroring TickerMessage's
implementation. Update `_build_widget` to allow border on either
widget type. Use case: rainbow chase frame around a "Days to NYE"
countdown.

**Files**:
- `src/led_ticker/widgets/message.py` — add field + paint call to
  `TickerCountdown` mirroring `TickerMessage`.
- `src/led_ticker/app.py` — extend the `_build_widget` validation
  to allow `widget_type in ("message", "countdown")`.

**TickerCountdown changes**:
```python
@register("countdown")
@attrs.define
class TickerCountdown(_FrameAware):
    # ... existing fields ...
    border: Any | None = attrs.field(default=None, kw_only=True)

    def draw(self, canvas, cursor_pos=0, **kwargs):
        # ... existing setup ...
        baseline_y = compute_baseline(self.font, canvas, valign="center")

        # Paint border before text — same contract as TickerMessage.
        if self.border is not None:
            self.border.paint(canvas, self._frame_count)

        # ... existing text rendering ...
```

**`_build_widget` change**:
```python
if border_value is not None and widget_type not in ("message", "countdown"):
    raise ValueError(
        f'border is only valid on type="message" or "countdown"; got '
        f"type={widget_type!r}."
    )
```

**Tests** in `TestBuildWidgetWithBorder`:
- Replace `test_border_on_countdown_raises` with
  `test_countdown_with_border_string` — countdown with `border =
  "rainbow"` should build cleanly and have a `RainbowChaseBorder`.
- Add `test_border_on_weather_raises` so the rejection path is
  still covered with a different widget type.
- Mirror one paint-order test in `test_widgets/test_message.py` for
  `TickerCountdown` — border paints before text on countdown too.

---

## Order of operations

All in one commit if everything stays trivial:

1. Branch `fix/border-followups` off main.
2. Item 2 first (frame_invariant property) — simplest, no test
   coupling with other items.
3. Item 1 (cycling test) — pairs with the rest of the rainbow tests.
4. Item 3 (range validation) — touches `_coerce_border` and its
   tests.
5. Item 4 (TickerCountdown border) — touches a different file
   (`message.py`) plus _build_widget.
6. Run full suite + lint.
7. Commit, push, open PR.

If any item turns out to be non-trivial in implementation (e.g.,
TickerCountdown's draw flow has a wrinkle I haven't spotted),
split it into its own commit on the branch. PR can carry multiple
commits.

---

## What's NOT in this plan

- **Apply range validation to `_coerce_color_provider` and other
  RGB coercion sites** — explicitly out of scope. That's a broader
  hardening pass affecting bg_color, font_color, top_color,
  bottom_color, font_color_temp, transition colors. Worth doing
  someday for consistency, but a separate PR.

- **Border on two-row widgets** — TwoRowMessage / two_row image
  overlays don't have border support. Not requested today; would
  be its own design conversation.

- **Border interaction with `TickerMessage` content_height >
  default** — borders paint on the panel perimeter regardless of
  `content_height`. That's correct behavior, but if a future config
  uses a non-full-panel content_height, the border still draws at
  the panel edges. Worth a docs note someday but not urgent.
