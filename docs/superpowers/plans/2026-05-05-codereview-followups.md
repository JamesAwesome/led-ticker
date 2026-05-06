# Code-Review Follow-ups for `presentation-emoji-per-char`

**Goal:** Land the fixes the reviewer flagged on top of `presentation-emoji-per-char` so the branch can merge clean.

**Architecture:** Six small, targeted commits. C1/C2 close real correctness gaps (per-char providers degrading on non-emoji paths). I1 generalizes the static-text fast path so Gradient/Random don't pay an unnecessary per-tick cost. I3 fixes a latent bug in `_scroll_and_delay` so animated title providers actually tick in non-swap modes. S2 plus tripwires close the smoke + test holes that let C1 hide.

**Branch:** Continue on `presentation-emoji-per-char`. Personal repo, direct-to-main authorized after the branch lands; no PR ceremony.

---

## Task 1: C1 — Image widget non-emoji path dispatches per-char providers

**Symptom:** A gif/image widget with `text = "HELLO"` (no `:slug:`) and `font_color = "rainbow"` renders as a single sweeping hue, not a per-character rainbow. The emoji path (`§3` of the smoke) was fixed; the plain-text path was not.

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py` (`_draw_text` lines 406-434, `_draw_row_text` lines 451-488)
- Test: `tests/test_widgets/test_image_base.py` (new class `TestPerCharProviderNonEmojiPath`)

**Steps:**

1. Write the failing tripwire first. Add to `test_image_base.py`:

```python
class TestPerCharProviderNonEmojiPath:
    """Tripwire: per-char providers (Rainbow, Gradient) must iterate
    chars on the plain-text path too — not just the emoji path. The
    smoke config §3 happens to use `:taco:` slugs so the bug hid; this
    test pins the non-emoji path explicitly."""

    def test_single_row_per_char_provider_iterates_chars(self):
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import FONT_DEFAULT

        class _TrackingProvider:
            per_char = True

            def __init__(self) -> None:
                self.calls: list[tuple[int, int, int]] = []

            def color_for(self, frame, char_index, total_chars):
                from rgbmatrix.graphics import Color
                self.calls.append((frame, char_index, total_chars))
                return Color(255, 255, 255)

        provider = _TrackingProvider()
        w = _DummyImage(text="ABC", font=FONT_DEFAULT, font_color=provider)
        canvas = _StubCanvas(width=64, height=16)
        w._draw_text(canvas, 0, 12, w.font_color)

        assert [c[1] for c in provider.calls] == [0, 1, 2]
        assert all(c[2] == 3 for c in provider.calls)

    def test_two_row_per_char_provider_iterates_chars(self):
        # Same shape, but for `_draw_row_text`.
        ...
```

Run: `pytest tests/test_widgets/test_image_base.py::TestPerCharProviderNonEmojiPath -v`
Expected: FAIL — current code calls `color_for(frame, 0, 1)` once, not 3 times with idx [0,1,2].

2. Implement `_draw_text` per-char branch:

```python
def _draw_text(self, canvas, x, baseline_y, color):
    if self._has_emoji():
        from led_ticker.pixel_emoji import draw_with_emoji
        return draw_with_emoji(
            canvas, self.font, x, baseline_y, color, self.text,
            emoji_y=baseline_y - 8, frame=self._frame_count,
        )
    # Per-char provider on plain text — iterate.
    if hasattr(color, "color_for") and color.per_char:
        from led_ticker.text_render import draw_text_per_char
        return draw_text_per_char(
            canvas, self.font, x, baseline_y, self.text,
            lambda idx, total: color.color_for(self._frame_count, idx, total),
        )
    # Whole-string provider or constant Color.
    if hasattr(color, "color_for"):
        color = color.color_for(self._frame_count, 0, len(self.text) or 1)
    return draw_text(canvas, self.font, x, baseline_y, color, self.text)
```

3. Implement same shape for `_draw_row_text`.

4. Run tests; the new tripwire passes; full suite passes.

5. Commit:
```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_base.py
git commit -m "Image widget non-emoji path: dispatch per-char providers"
```

---

## Task 2: C2 — TickerCountdown dispatches per-char providers

**Symptom:** §9 of the smoke (`9: rainbow + countdown`) renders as a single sweeping hue instead of per-char rainbow. `TickerCountdown.draw` materializes the provider once at `char_index=0`.

**Files:**
- Modify: `src/led_ticker/widgets/message.py:189-192`
- Test: `tests/test_widgets/test_message.py` (extend `TestTickerCountdownColorProvider`)

**Steps:**

1. Add tripwire to `TestTickerCountdownColorProvider`:

```python
def test_per_char_provider_iterates_chars(self):
    from datetime import date
    from rgbmatrix import _StubCanvas
    from led_ticker.widgets.message import TickerCountdown

    class _TrackingProvider:
        per_char = True
        def __init__(self): self.calls = []
        def color_for(self, frame, idx, total):
            from rgbmatrix.graphics import Color
            self.calls.append((frame, idx, total))
            return Color(255, 255, 255)

    provider = _TrackingProvider()
    widget = TickerCountdown(
        "Days", countdown_date=date(2027, 1, 1), font_color=provider,
    )
    canvas = _StubCanvas(width=160, height=16)
    widget.draw(canvas)
    # "Days: <N>" → at least 7 chars (label + colon + space + digits).
    assert len(provider.calls) >= 7
    assert provider.calls[0][1] == 0
    assert provider.calls[-1][1] == len(provider.calls) - 1
```

Run: should FAIL with `len(provider.calls) == 1`.

2. Implement: mirror `TickerMessage.draw`'s per-char branch.

```python
if provider.per_char:
    from led_ticker.text_render import draw_text_per_char
    cursor_pos += draw_text_per_char(
        canvas, self.font, cursor_pos, baseline_y + y_offset, text,
        lambda idx, total: provider.color_for(self._frame_count, idx, total),
    )
else:
    color = provider.color_for(self._frame_count, 0, len(text))
    cursor_pos += draw_text(
        canvas, self.font, cursor_pos, baseline_y + y_offset, color, text,
    )
```

3. Tests pass; full suite passes.

4. Commit:
```bash
git add src/led_ticker/widgets/message.py tests/test_widgets/test_message.py
git commit -m "TickerCountdown: dispatch per-char providers"
```

---

## Task 3: I1 — Generalize fast-path gate via `frame_invariant` attribute

**Symptom:** Static-image + static-text + `Gradient` (or `Random`) takes the per-tick loop unnecessarily because the gate checks `isinstance(font_color, _ConstantColor)`. Both are frame-invariant; they could fast-path.

**Files:**
- Modify: `src/led_ticker/color_providers.py` (add `frame_invariant` class attr to all 5 providers)
- Modify: `src/led_ticker/widgets/_image_base.py:694, 872-874` (replace `isinstance(_, _ConstantColor)` checks)
- Modify: `CLAUDE.md` constraint #12 wording (was "isinstance _ConstantColor", becomes "frame_invariant providers")
- Test: `tests/test_color_providers.py` (new test class asserting flag values)
- Test: `tests/test_widgets/test_image_base.py::TestPlayLoopAdvancesFrame` (extend with `Gradient` taking the fast path)

**Steps:**

1. Add `frame_invariant: bool` class attribute to each provider in `color_providers.py`:
   - `_ConstantColor` → `True`
   - `Random` → `True`
   - `Gradient` → `True`
   - `Rainbow` → `False`
   - `ColorCycle` → `False`

2. Add unit test pinning the flag values:

```python
class TestFrameInvariantFlag:
    def test_constant_color_is_frame_invariant(self):
        from rgbmatrix.graphics import Color
        from led_ticker.color_providers import _ConstantColor
        assert _ConstantColor(Color(0,0,0)).frame_invariant is True

    def test_random_is_frame_invariant(self):
        from led_ticker.color_providers import Random
        assert Random().frame_invariant is True

    def test_gradient_is_frame_invariant(self):
        from rgbmatrix.graphics import Color
        from led_ticker.color_providers import Gradient
        g = Gradient(Color(255,0,0), Color(0,0,255))
        assert g.frame_invariant is True

    def test_rainbow_is_not_frame_invariant(self):
        from led_ticker.color_providers import Rainbow
        assert Rainbow().frame_invariant is False

    def test_color_cycle_is_not_frame_invariant(self):
        from led_ticker.color_providers import ColorCycle
        assert ColorCycle().frame_invariant is False
```

3. Update `_image_base.py` fast-path gates:

```python
# Single-row (line ~694):
color_is_static = getattr(self.font_color, "frame_invariant", False)

# Two-row (line ~872):
colors_are_static = (
    getattr(top_color, "frame_invariant", False)
    and getattr(bottom_color, "frame_invariant", False)
)
```

4. Extend `TestPlayLoopAdvancesFrame` with one new test asserting `Gradient` + static text + static image takes the fast path (`_frame_count == 0` after 10 ticks).

5. Update CLAUDE.md constraint #12: replace "`isinstance(font_color, _ConstantColor)`" with "the provider's `frame_invariant` flag".

6. Tests pass; full suite passes.

7. Commit:
```bash
git add src/led_ticker/color_providers.py src/led_ticker/widgets/_image_base.py CLAUDE.md tests/test_color_providers.py tests/test_widgets/test_image_base.py
git commit -m "ColorProvider: add frame_invariant flag, generalize fast-path gate"
```

---

## Task 4: I3 — Title animations tick in `_scroll_and_delay` post-scroll hold

**Symptom:** In `forever_scroll` / `infini_scroll` modes, the post-scroll hold of `_scroll_and_delay` is a single swap + `asyncio.sleep(delay)`. A title with `color = "color_cycle"` holds at frame=0's hue for the full delay.

**Files:**
- Modify: `src/led_ticker/ticker.py` (`_scroll_and_delay` post-scroll branch around line 320-326)
- Test: `tests/test_ticker_display.py` (new test asserting `_advance_frame_if_supported` is called per tick during the post-scroll hold of `_scroll_and_delay`)

**Steps:**

1. Read `_scroll_and_delay` to confirm current shape.

2. Write tripwire test using a tracking widget that counts `advance_frame` calls during the post-scroll hold of a long delay (e.g., delay=0.5s with ENGINE_TICK_MS=50 → 10 ticks expected).

3. Replace the single-frame post-scroll hold with the same tick-loop pattern used in `_swap_and_scroll`:

```python
n_ticks = max(1, int(delay * 1000) // ENGINE_TICK_MS)
tick_seconds = ENGINE_TICK_MS / 1000
for _ in range(n_ticks):
    _advance_frame_if_supported(ticker_obj)
    reset_canvas(canvas, bg_color)
    canvas, _ = ticker_obj.draw(canvas, cursor_pos=stop_pos)
    canvas = _swap(canvas, frame)
    await asyncio.sleep(tick_seconds)
```

(Adjust to match `_scroll_and_delay`'s actual variable names — read first.)

4. Tests pass; full suite passes.

5. Commit:
```bash
git add src/led_ticker/ticker.py tests/test_ticker_display.py
git commit -m "_scroll_and_delay: tick post-scroll hold so animated providers animate"
```

---

## Task 5: Smoke config — close visual coverage holes (S2 subset)

Add three sections to demo:
1. **Plain-text image widget + rainbow** (catches C1 visually)
2. **HiresFont + emoji + per-char rainbow** (only matrix combo not currently demoed)
3. **Two-row image + rainbow** (exercises `_draw_row_text` per-char path post-C1)

**Files:**
- Modify: `config/config.presentation_test.example.toml`

**Steps:**

1. Decide section numbers. Current is 13 sections. Insert new ones:
   - §3b → renumber to §4: plain-text image (no emoji) + rainbow
   - §3c → renumber to §5: two-row image + rainbow
   - §11b → after §11: HiresFont + `:taco:` + rainbow
   - Renumber the rest accordingly.

   Or — simpler — add at the end as §14, §15, §16. The "new behaviors at the top" comment in the header is already broken by the existing §1-§4 ordering, so appending is fine.

   Recommend: **append as §14, §15, §16** to avoid re-renumbering everything else again.

2. Update the section-list comment block at the top of the file.

3. Add the three new sections at the end, each with a short prose comment block explaining what it demos.

4. Commit:
```bash
git add config/config.presentation_test.example.toml
git commit -m "presentation_test: smoke sections for non-emoji image rainbow + hires emoji + two-row image"
```

---

## Task 6: Polish — S3, S4

Small docstring + import hygiene.

**Files:**
- Modify: `src/led_ticker/text_render.py` (`draw_text_per_char` docstring — note frame is bound by caller via closure)
- Modify: `src/led_ticker/pixel_emoji.py` (hoist `from led_ticker.text_render import draw_text_per_char` to module level)

**Steps:**

1. Read `text_render.draw_text_per_char` and add one sentence to the docstring: "The color callback is `(idx, total) -> Color`; callers pre-bind `frame` via closure so the helper is frame-agnostic."

2. Move the lazy import in `pixel_emoji.draw_with_emoji` to the top of the file. Run the test suite to confirm no circular-import surprises (the lazy import was historically there for circularity reasons; if there's a problem, leave it but hoist it to the top of the function instead of inside the segment loop).

3. Tests pass; full suite passes.

4. Commit:
```bash
git add src/led_ticker/text_render.py src/led_ticker/pixel_emoji.py
git commit -m "Polish: docstring on draw_text_per_char, hoist lazy import"
```

---

## What's deferred

- **S5** (auto-discovery registry) — not worth the abstraction at 5 providers.
- **Reviewer's S1** other coverage suggestions — `TestPlayLoopAdvancesFrame` + the new `TestPerCharProviderNonEmojiPath` + the new HiresFont smoke section together cover the gaps the reviewer flagged. Pause/resume + per-char rainbow tripwire is overkill for now (`test_pause_freezes_frame_count` already pins the freeze contract; coupling color readout would tighten it but isn't necessary for correctness).

---

## Order of operations

The 6 commits land in this order so each is independently green:

1. C1 (image plain-text per-char)
2. C2 (countdown per-char)
3. I1 (frame_invariant attr — touches CLAUDE.md, color_providers, _image_base)
4. I3 (_scroll_and_delay tick loop)
5. Smoke (visual demos for everything above)
6. Polish

After commit 6: push, hardware-test the smoke config end-to-end on bigsign, then merge `presentation-emoji-per-char` into `main`.
