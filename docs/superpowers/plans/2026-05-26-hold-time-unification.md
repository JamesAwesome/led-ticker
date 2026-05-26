# hold_time Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename `hold_seconds` → `hold_time` on `StillImage`, add widget-level `hold_time: float = 0.0` to eight more widget classes, and teach the engine to resolve `effective_hold = max(section.hold_time, widget.hold_time)`.

**Architecture:** `_show_one` in `ticker.py` is the single dispatch point for all widgets — one `getattr` check there propagates the override everywhere without touching individual widget render paths. `StillImage` already implements "longer wins" internally via `max(self.hold_seconds, hold_time_arg)` in `play()`; the field rename preserves that. Draw-only widgets get the field as a pure annotation; the engine reads it.

**Tech Stack:** Python 3.13, attrs, asyncio, pytest, ruff

---

### Task 1: Update StillImage test files to use `hold_time=` (make them fail)

**Files:**
- Modify: `tests/test_widgets/test_still.py`
- Modify: `tests/test_widgets/test_image_text_wrap.py`
- Modify: `tests/test_widgets/test_image_two_row_wrap.py`
- Modify: `tests/test_widgets/test_image_two_row_scroll_through.py`

- [ ] **Step 1: Replace all `hold_seconds=` kwargs with `hold_time=` in test files**

```bash
sed -i '' 's/hold_seconds=/hold_time=/g' \
  tests/test_widgets/test_still.py \
  tests/test_widgets/test_image_text_wrap.py \
  tests/test_widgets/test_image_two_row_wrap.py \
  tests/test_widgets/test_image_two_row_scroll_through.py
```

- [ ] **Step 2: Replace `hold_seconds` string literals in test_still.py**

In `tests/test_widgets/test_still.py` there is a `pytest.raises` match on the string `"hold_seconds"`. Update it to `"hold_time"`:

```python
# before
with pytest.raises(ValueError, match="hold_seconds"):
    StillImage(path=str(path), hold_seconds=-1.0)

# after
with pytest.raises(ValueError, match="hold_time"):
    StillImage(path=str(path), hold_time=-1.0)
```

- [ ] **Step 3: Run tests to confirm failures**

```bash
make test 2>&1 | grep -E "FAILED|ERROR|hold_seconds" | head -20
```

Expected: multiple failures mentioning `hold_seconds` or `unexpected keyword argument`.

---

### Task 2: Rename `hold_seconds` → `hold_time` on `StillImage`

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py`
- Modify: `src/led_ticker/widgets/still.py`

- [ ] **Step 1: Rename `HOLD_SECONDS_FLOOR` → `HOLD_TIME_FLOOR` in `_image_base.py`**

Find the constant (line ~102):
```python
HOLD_SECONDS_FLOOR: float = 0.05
```
Change to:
```python
HOLD_TIME_FLOOR: float = 0.05
```

Also update the export in `_image_base.py`'s import surface — search for any `__all__` or import of `HOLD_SECONDS_FLOOR` in `_image_base.py` itself and rename it.

- [ ] **Step 2: Update `still.py` import and all references**

At the top of `still.py`, update the import:
```python
# before
from led_ticker.widgets._image_base import HOLD_SECONDS_FLOOR, _BaseImageWidget

# after
from led_ticker.widgets._image_base import HOLD_TIME_FLOOR, _BaseImageWidget
```

Rename the field and all references in `StillImage`:
```python
# Field (was: hold_seconds: float = 5.0)
hold_time: float = 5.0

# __attrs_post_init__ validation (was: self.hold_seconds < HOLD_SECONDS_FLOOR)
if self.hold_time < HOLD_TIME_FLOOR:
    raise ValueError(
        f"hold_time must be >= {HOLD_TIME_FLOOR}, "
        f"got {self.hold_time!r}"
    )
```

In `play()` (three occurrences — search for `self.hold_seconds`):
```python
# all three: replace self.hold_seconds with self.hold_time
n_ticks = max(1, int(self.hold_time * 1000) // tick_ms)
# ...
await asyncio.sleep(self.hold_time)
# ...
n_ticks = max(1, int(self.hold_time * 1000) // ENGINE_TICK_MS)
```

- [ ] **Step 3: Update module docstring references in `still.py`**

The module docstring and class docstring reference `hold_seconds` in several places. Do a find-replace within the file:

```bash
sed -i '' 's/hold_seconds/hold_time/g' src/led_ticker/widgets/still.py
```

Then verify no `hold_seconds` remains:
```bash
grep -n "hold_seconds" src/led_ticker/widgets/still.py
```

Expected: no output.

- [ ] **Step 4: Run the StillImage tests to confirm they pass**

```bash
pytest tests/test_widgets/test_still.py tests/test_widgets/test_image_text_wrap.py \
  tests/test_widgets/test_image_two_row_wrap.py \
  tests/test_widgets/test_image_two_row_scroll_through.py -v 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py src/led_ticker/widgets/still.py \
  tests/test_widgets/test_still.py tests/test_widgets/test_image_text_wrap.py \
  tests/test_widgets/test_image_two_row_wrap.py \
  tests/test_widgets/test_image_two_row_scroll_through.py
git commit -m "refactor: rename hold_seconds → hold_time on StillImage"
```

---

### Task 3: Add `hold_time: float = 0.0` to draw()-only widgets

**Files:**
- Modify: `src/led_ticker/widgets/message.py`
- Modify: `src/led_ticker/widgets/two_row.py`
- Modify: `src/led_ticker/widgets/weather.py`
- Modify: `src/led_ticker/widgets/mlb.py`
- Modify: `src/led_ticker/widgets/mlb_standings.py`
- Modify: `src/led_ticker/widgets/crypto/coinbase.py`
- Modify: `src/led_ticker/widgets/crypto/coingecko.py`
- Modify: `src/led_ticker/widgets/crypto/etherscan.py`

- [ ] **Step 1: Add `hold_time` to `TickerMessage` in `message.py`**

In the `TickerMessage` class (after `@register("message")` / `@attrs.define`), add the field after the existing `padding` field:

```python
padding: int = 6
hold_time: float = 0.0
```

Do NOT add it to `TickerCountdown` — countdown has a natural terminal state.

- [ ] **Step 2: Add `hold_time` to `TwoRowMessage` in `two_row.py`**

Find the `TwoRowMessage` class (`@register("two_row")` / `@attrs.define`). Add after the `bg_color` or similar float/int field near the top of the field list:

```python
hold_time: float = 0.0
```

- [ ] **Step 3: Add `hold_time` to `WeatherWidget` in `weather.py`**

```python
hold_time: float = 0.0
```

Add after existing simple scalar fields.

- [ ] **Step 4: Add `hold_time` to `MLBScoreMonitor` in `mlb.py`**

```python
hold_time: float = 0.0
```

- [ ] **Step 5: Add `hold_time` to `MLBStandingsMonitor` in `mlb_standings.py`**

```python
hold_time: float = 0.0
```

- [ ] **Step 6: Add `hold_time` to the three crypto widgets**

`src/led_ticker/widgets/crypto/coinbase.py` → `CoinbasePriceMonitor`:
```python
hold_time: float = 0.0
```

`src/led_ticker/widgets/crypto/coingecko.py` → `CoinGeckoPriceMonitor`:
```python
hold_time: float = 0.0
```

`src/led_ticker/widgets/crypto/etherscan.py` → `EtherscanGasMonitor`:
```python
hold_time: float = 0.0
```

- [ ] **Step 7: Verify field is accepted without errors**

```bash
python -c "
from led_ticker.widgets.message import TickerMessage
from led_ticker.widgets.two_row import TwoRowMessage
from led_ticker.widgets.weather import WeatherWidget
w = TickerMessage(text='hi', hold_time=5.0)
assert w.hold_time == 5.0
w2 = TickerMessage(text='hi')
assert w2.hold_time == 0.0
print('OK')
"
```

Expected: `OK`

- [ ] **Step 8: Run full test suite to confirm nothing broke**

```bash
make test 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add src/led_ticker/widgets/message.py src/led_ticker/widgets/two_row.py \
  src/led_ticker/widgets/weather.py src/led_ticker/widgets/mlb.py \
  src/led_ticker/widgets/mlb_standings.py \
  src/led_ticker/widgets/crypto/coinbase.py \
  src/led_ticker/widgets/crypto/coingecko.py \
  src/led_ticker/widgets/crypto/etherscan.py
git commit -m "feat: add widget-level hold_time field to draw()-only widgets"
```

---

### Task 4: Engine — resolve effective_hold in `_show_one`

**Files:**
- Modify: `tests/test_ticker_display.py`
- Modify: `src/led_ticker/ticker.py`

- [ ] **Step 1: Write the failing test**

Add a new test class to `tests/test_ticker_display.py`. Find a good insertion point near the existing `_show_one` tests (search for `class.*ShowOne` or `test_show_one`).

```python
class TestShowOneWidgetHoldTimeOverride:
    """Widget-level hold_time raises the effective hold above section hold_time."""

    async def test_widget_hold_time_overrides_section_when_larger(
        self, mock_frame, plain_canvas
    ):
        from led_ticker.ticker import ENGINE_TICK_MS, Ticker
        from led_ticker.widgets.message import TickerMessage

        ticker = Ticker(
            widgets=[],
            frame=mock_frame,
            transition_config=None,
            hold_time=0.1,  # section: 0.1 s → 2 ticks at 50ms
        )
        # Widget requests 0.3 s → 6 ticks; widget should win
        widget = TickerMessage(text="hi", hold_time=0.3)

        swap_calls_before = mock_frame.matrix.SwapOnVSync.call_count
        await ticker._show_one(plain_canvas, widget, hold_time=0.1)
        n_swaps = mock_frame.matrix.SwapOnVSync.call_count - swap_calls_before

        expected_ticks = max(1, int(0.3 * 1000) // ENGINE_TICK_MS)  # 6
        assert n_swaps >= expected_ticks, (
            f"Expected >= {expected_ticks} swaps (widget hold_time=0.3 wins), "
            f"got {n_swaps}"
        )

    async def test_section_hold_time_wins_when_larger(
        self, mock_frame, plain_canvas
    ):
        from led_ticker.ticker import ENGINE_TICK_MS, Ticker
        from led_ticker.widgets.message import TickerMessage

        ticker = Ticker(
            widgets=[],
            frame=mock_frame,
            transition_config=None,
            hold_time=0.3,  # section: 0.3 s → 6 ticks; should win
        )
        # Widget requests 0.1 s; section should win
        widget = TickerMessage(text="hi", hold_time=0.1)

        swap_calls_before = mock_frame.matrix.SwapOnVSync.call_count
        await ticker._show_one(plain_canvas, widget, hold_time=0.3)
        n_swaps = mock_frame.matrix.SwapOnVSync.call_count - swap_calls_before

        expected_ticks = max(1, int(0.3 * 1000) // ENGINE_TICK_MS)  # 6
        assert n_swaps >= expected_ticks, (
            f"Expected >= {expected_ticks} swaps (section hold_time=0.3 wins), "
            f"got {n_swaps}"
        )

    async def test_widget_hold_time_zero_defers_to_section(
        self, mock_frame, plain_canvas
    ):
        from led_ticker.ticker import ENGINE_TICK_MS, Ticker
        from led_ticker.widgets.message import TickerMessage

        ticker = Ticker(
            widgets=[],
            frame=mock_frame,
            transition_config=None,
            hold_time=0.15,
        )
        widget = TickerMessage(text="hi", hold_time=0.0)  # 0 = defer

        swap_calls_before = mock_frame.matrix.SwapOnVSync.call_count
        await ticker._show_one(plain_canvas, widget, hold_time=0.15)
        n_swaps = mock_frame.matrix.SwapOnVSync.call_count - swap_calls_before

        expected_ticks = max(1, int(0.15 * 1000) // ENGINE_TICK_MS)  # 3
        assert n_swaps >= expected_ticks
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
pytest tests/test_ticker_display.py::TestShowOneWidgetHoldTimeOverride -v
```

Expected: the override test fails (wrong swap count), the defer test may or may not pass depending on default behavior.

- [ ] **Step 3: Implement effective_hold in `_show_one`**

In `src/led_ticker/ticker.py`, find `_show_one` (the method that starts with `self, canvas: Any, widget: Any, *, section_hold_time: float = 3.0` — wait, the actual signature is `hold_time: float`). Add one line at the top of the method body, after the `reset_frame` block:

```python
async def _show_one(
    self,
    canvas: Canvas,
    widget: Any,
    hold_time: float,
    skip_initial_draw: bool = False,
    continuous: bool = False,
) -> tuple[Canvas, int]:
    """..."""
    self._visit_counter += 1
    self._current_visit = self._visit_counter
    if hasattr(widget, "reset_frame"):
        widget.reset_frame()
    # Widget-level hold_time overrides section hold_time when larger.
    # Default 0.0 on widgets means "defer to section".
    hold_time = max(hold_time, getattr(widget, "hold_time", 0.0))
    if Ticker._has_play(widget):
        ...
```

Add exactly this one line after the `reset_frame` block:
```python
hold_time = max(hold_time, getattr(widget, "hold_time", 0.0))
```

- [ ] **Step 4: Run the new tests to confirm they pass**

```bash
pytest tests/test_ticker_display.py::TestShowOneWidgetHoldTimeOverride -v
```

Expected: all three pass.

- [ ] **Step 5: Run the full test suite**

```bash
make test 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker_display.py
git commit -m "feat: engine resolves effective_hold = max(section, widget) in _show_one"
```

---

### Task 5: Update coercion, factories, and Rule 8 validation

**Files:**
- Modify: `src/led_ticker/app/coercion.py`
- Modify: `src/led_ticker/app/factories.py`
- Modify: `src/led_ticker/validate.py`
- Modify: `tests/test_validate.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Update `_WIDGET_FLOAT_FIELDS` in `coercion.py`**

Find the set containing `"hold_seconds"` (line ~604):
```python
_WIDGET_FLOAT_FIELDS = frozenset(
    {
        "hold_seconds",
    }
)
```
Change to:
```python
_WIDGET_FLOAT_FIELDS = frozenset(
    {
        "hold_time",
    }
)
```

- [ ] **Step 2: Update `FieldHint` in `factories.py`**

Find the `"hold_seconds"` key in the `FieldHint` dict (line ~122):
```python
"hold_seconds": FieldHint(
    "float (seconds)",
    "minimum display time for still images; section hold_time wins if longer",
    "0.0",
),
```
Change key and description:
```python
"hold_time": FieldHint(
    "float (seconds)",
    "per-widget minimum hold; section hold_time wins if longer (0.0 = defer to section)",
    "0.0",
),
```

- [ ] **Step 3: Update Rule 8 in `validate.py`**

Find Rule 8 (search for `# Rule 8`). It currently reads:
```python
hold_s = widget_cfg.get("hold_seconds")
```
Change to:
```python
hold_s = widget_cfg.get("hold_time")
```

Update the error message strings in the same block — replace any reference to `hold_seconds` with `hold_time` and `HOLD_SECONDS_FLOOR` with `HOLD_TIME_FLOOR` if they appear. Verify:
```bash
grep -n "hold_seconds\|HOLD_SECONDS" src/led_ticker/validate.py
```
Expected: no matches.

- [ ] **Step 4: Update Rule 8 test in `test_validate.py`**

Find `test_rule8_hold_seconds_too_short`. Update the test fixture and name:
```python
async def test_rule8_hold_time_too_short(conf):
    extra = textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "image"
        path = "x.png"
        hold_time = 0.001
        """)
    result = await validate_config(conf(GOOD_CONFIG + extra))
    assert not result.valid
    assert any(e.rule == 8 for e in result.errors)
```

- [ ] **Step 5: Update field listing test in `test_app.py`**

Find `test_hold_seconds_description_appears_on_image`:
```python
def test_hold_time_description_appears_on_image(self):
    from led_ticker.app import _list_widget_fields

    output = _list_widget_fields("image")
    assert "hold_time" in output
    assert "minimum" in output.lower() or "defer" in output.lower()
```

- [ ] **Step 6: Run the updated tests**

```bash
pytest tests/test_validate.py::test_rule8_hold_time_too_short \
  tests/test_app.py -v -k "hold_time" 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 7: Run full test suite**

```bash
make test 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/app/coercion.py src/led_ticker/app/factories.py \
  src/led_ticker/validate.py tests/test_validate.py tests/test_app.py
git commit -m "refactor: update coercion, factories, and Rule 8 for hold_time rename"
```

---

### Task 6: Update `config/` example files

**Files:**
- Modify: all `config/*.toml` files containing `hold_seconds`

- [ ] **Step 1: Replace `hold_seconds` with `hold_time` in all config files**

```bash
grep -rl "hold_seconds" config/ | xargs sed -i '' 's/hold_seconds/hold_time/g'
```

- [ ] **Step 2: Verify no `hold_seconds` remains**

```bash
grep -r "hold_seconds" config/
```

Expected: no output.

- [ ] **Step 3: Verify configs still validate**

```bash
make validate CONFIG=config/config.example.toml 2>&1 | tail -5
make validate CONFIG=config/config.image_test.example.toml 2>&1 | tail -5
make validate CONFIG=config/config.moonbunny.example.toml 2>&1 | tail -5
```

Expected: each prints `Config is valid` (or equivalent success message).

- [ ] **Step 4: Run full test suite one final time**

```bash
make test 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add config/
git commit -m "config: rename hold_seconds → hold_time in all example configs"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] `hold_seconds` → `hold_time` on `StillImage` — Task 2
- [x] `max(section.hold_time, widget.hold_time)` engine resolution — Task 4
- [x] `hold_time` on `message`, `two_row`, `weather`, `mlb`, `mlb_standings`, `coinbase`, `coingecko`, `etherscan` — Task 3
- [x] `gif`, `countdown`, `rss_feed` not touched — Tasks 3 skips them
- [x] No migration error; did-you-mean covers stale `hold_seconds` — no migration task needed (factory already handles this)
- [x] Config example files updated — Task 6
- [x] Rule 8 validation updated — Task 5
- [x] Coercion and factories updated — Task 5
- [x] `TickerCountdown` NOT getting `hold_time` — explicit note in Task 3 Step 1
