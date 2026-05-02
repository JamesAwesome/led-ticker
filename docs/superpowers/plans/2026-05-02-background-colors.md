# Background Colors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `bg_color` support across every widget type so users can set a non-black background at the section or per-widget level, with `top_bg_color`/`bottom_bg_color` per-row bands for `TwoRowMessage`.

**Architecture:** Hybrid model. Two new helpers in `widgets/_image_fit.py` (`reset_canvas`, `fill_band`). Every widget grows a `bg_color: Color | None = None` field. Text-widget bg painting is centralized in the orchestrator (`Ticker._swap_and_scroll`/`_scroll_one_by_one`/`_scroll_side_by_side` swap their `canvas.Clear()` calls for `reset_canvas(canvas, widget.bg_color)`). Image widgets handle their own internal resets and force the skip-black paint path when `bg_color` is set so pillarbox/letterbox/transparent regions reveal the bg. `TwoRowMessage` paints two row bands itself in `draw()`. Section-level `bg_color` is plumbed via `app._build_widget` — it injects into each widget's config when the widget config doesn't override.

**Tech Stack:** Python 3.13, attrs, asyncio, rgbmatrix, pytest.

---

## File Structure

**New code (no new files — helpers go into existing canonical home):**

- `src/led_ticker/widgets/_image_fit.py` — adds `reset_canvas(canvas, bg_color)` and `fill_band(canvas, y_start, y_end, color)`.

**Modified files (one new field + small edits each):**

- `src/led_ticker/config.py` — `SectionConfig.bg_color: tuple | None`.
- `src/led_ticker/app.py` — extend `_COLOR_KEYS` (add `bg_color`, `top_bg_color`, `bottom_bg_color`); inject section bg into widget config in `_build_widget`.
- `src/led_ticker/presentation.py` — `WidgetPresenter.bg_color` property forwards to wrapped widget.
- `src/led_ticker/ticker.py` — replace 3 `canvas.Clear()` sites with `reset_canvas(canvas, widget.bg_color)`.
- `src/led_ticker/widgets/_image_base.py` — `bg_color` field; new `_paint_image` dispatcher; `_render_tick` and `_play_with_text` static-text branch use `reset_canvas`.
- `src/led_ticker/widgets/gif.py` — `_play_no_text` uses `reset_canvas` + `_paint_image`.
- `src/led_ticker/widgets/still.py` — `_play_no_text` uses `reset_canvas` + `_paint_image`.
- `src/led_ticker/widgets/message.py` — `bg_color` field on `TickerMessage` and `TickerCountdown`.
- `src/led_ticker/widgets/two_row.py` — `bg_color`, `top_bg_color`, `bottom_bg_color`; row-band painting in `draw()`.
- `src/led_ticker/widgets/weather.py` — `bg_color` field.
- `src/led_ticker/widgets/rss_feed.py` — `bg_color`; thread through to story `TickerMessage`s.
- `src/led_ticker/widgets/mlb.py` — `bg_color`; thread through to story `TickerMessage`/`MLBGameMessage`s.
- `src/led_ticker/widgets/mlb_standings.py` — `bg_color`; thread through to stories.
- `src/led_ticker/widgets/crypto/coinbase.py` — `bg_color` field.
- `src/led_ticker/widgets/crypto/coingecko.py` — `bg_color` field.
- `src/led_ticker/widgets/crypto/etherscan.py` — `bg_color` field.

**New + modified tests:**

- `tests/test_widgets/test_image_fit.py` (new) — `reset_canvas`, `fill_band`.
- `tests/test_widgets/test_image_base.py` (new) — `_paint_image` dispatch + `_render_tick` bg path.
- `tests/test_widgets/test_message.py` — TickerMessage bg coverage.
- `tests/test_widgets/test_two_row.py` — per-row bands.
- `tests/test_widgets/test_gif.py` — gif bg path.
- `tests/test_widgets/test_still.py` — still bg path.
- `tests/test_ticker_display.py` — orchestrator `reset_canvas` dispatch.
- `tests/test_app.py` — section bg propagation + `_COLOR_KEYS`.
- `tests/test_config.py` — `SectionConfig.bg_color`.

---

## Conventions for this plan

- All new fields are `kw_only=True` so subclasses with positional fields keep working.
- `bg_color` default is always `None` — preserves today's `Clear()` behavior when not set.
- The widget's `bg_color` value is a `graphics.Color` object (after `_coerce_widget_colors`) or `None`. The helpers consume either.
- Use `attrs.field(default=None, kw_only=True)` for the new field. Match existing style.
- Tests use the `canvas` and `mock_frame` fixtures from `tests/conftest.py`. The stub canvas (`tests/stubs/rgbmatrix/__init__.py`) supports `Clear()`, `Fill(r, g, b)`, `SetPixel(x, y, r, g, b)`, and `get_pixel(x, y)` for assertions.
- `graphics.Color(r, g, b)` is available via `from led_ticker._compat import require_graphics; Color = require_graphics().Color`. In tests, simpler: `from rgbmatrix.graphics import Color`.

---

### Task 1: Add `reset_canvas` and `fill_band` helpers

**Files:**
- Modify: `src/led_ticker/widgets/_image_fit.py`
- Test: `tests/test_widgets/test_image_fit.py` (new file)

The helpers are tiny, but they're the foundation every other task imports. Test first.

- [ ] **Step 1: Create test file with failing tests**

```python
# tests/test_widgets/test_image_fit.py
"""Tests for the canvas reset / fill-band helpers."""

from __future__ import annotations

import unittest.mock as mock

from led_ticker.widgets._image_fit import fill_band, reset_canvas


class _StubColor:
    """Stand-in for graphics.Color (just RGB attrs)."""

    def __init__(self, r: int, g: int, b: int) -> None:
        self.red = r
        self.green = g
        self.blue = b


class TestResetCanvas:
    def test_none_calls_clear(self):
        canvas = mock.Mock()
        reset_canvas(canvas, None)
        canvas.Clear.assert_called_once_with()
        canvas.Fill.assert_not_called()

    def test_color_calls_fill_with_rgb(self):
        canvas = mock.Mock()
        reset_canvas(canvas, _StubColor(10, 20, 30))
        canvas.Fill.assert_called_once_with(10, 20, 30)
        canvas.Clear.assert_not_called()

    def test_explicit_black_uses_fill_not_clear(self):
        """bg_color = (0,0,0) is 'set' — Fill(0,0,0), not Clear()."""
        canvas = mock.Mock()
        reset_canvas(canvas, _StubColor(0, 0, 0))
        canvas.Fill.assert_called_once_with(0, 0, 0)
        canvas.Clear.assert_not_called()


class TestFillBand:
    def test_fills_only_specified_rows(self, canvas):
        """fill_band(canvas, 4, 8, color) writes y in [4, 8) — not row 3, not row 8."""
        color = _StubColor(255, 0, 128)
        fill_band(canvas, 4, 8, color)

        # Rows 0-3 untouched.
        for y in range(0, 4):
            for x in range(canvas.width):
                assert canvas.get_pixel(x, y) == (0, 0, 0), f"row {y} should be unset"
        # Rows 4-7 filled.
        for y in range(4, 8):
            for x in range(canvas.width):
                assert canvas.get_pixel(x, y) == (255, 0, 128), (
                    f"row {y} should be filled"
                )
        # Row 8 untouched.
        for x in range(canvas.width):
            assert canvas.get_pixel(x, 8) == (0, 0, 0), "row 8 should be unset"

    def test_fills_full_width(self, canvas):
        color = _StubColor(50, 60, 70)
        fill_band(canvas, 0, 1, color)
        for x in range(canvas.width):
            assert canvas.get_pixel(x, 0) == (50, 60, 70)

    def test_empty_band_is_no_op(self, canvas):
        color = _StubColor(99, 99, 99)
        fill_band(canvas, 5, 5, color)  # y_end == y_start
        # Nothing painted.
        assert all(v == (0, 0, 0) for v in (
            canvas.get_pixel(x, y)
            for y in range(canvas.height)
            for x in range(canvas.width)
        ))
```

- [ ] **Step 2: Run tests, verify they fail with ImportError**

Run: `make test ARGS="tests/test_widgets/test_image_fit.py -v"`
Expected: FAIL with `ImportError: cannot import name 'fill_band'` (or `reset_canvas`).

- [ ] **Step 3: Implement helpers in `_image_fit.py`**

Append to `src/led_ticker/widgets/_image_fit.py`:

```python
def reset_canvas(canvas, bg_color) -> None:
    """Clear canvas, or Fill it with `bg_color` if set.

    `bg_color` is a `graphics.Color` (with `.red`, `.green`, `.blue`
    attrs) or `None`. `(0, 0, 0)` is treated as "explicit black" — the
    Fill path runs, painting black across the whole canvas. Visually
    identical to Clear() but counts as a "set" bg for resolution rules.
    """
    if bg_color is None:
        canvas.Clear()
    else:
        canvas.Fill(bg_color.red, bg_color.green, bg_color.blue)


def fill_band(canvas, y_start: int, y_end: int, color) -> None:
    """Fill the half-open horizontal band [y_start, y_end) with `color`.

    Used for per-row backgrounds in `TwoRowMessage`. Goes through
    SetPixel so a `ScaledCanvas` wrapper expands each logical pixel to
    a scale×scale block on the real canvas.
    """
    set_px = canvas.SetPixel
    r, g, b = color.red, color.green, color.blue
    width = canvas.width
    for y in range(y_start, y_end):
        for x in range(width):
            set_px(x, y, r, g, b)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `make test ARGS="tests/test_widgets/test_image_fit.py -v"`
Expected: PASS (3 tests under TestResetCanvas + 3 under TestFillBand).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/_image_fit.py tests/test_widgets/test_image_fit.py
git commit -m "Add reset_canvas + fill_band helpers in _image_fit"
```

---

### Task 2: WidgetPresenter forwards `bg_color`

**Files:**
- Modify: `src/led_ticker/presentation.py:37-71`
- Test: `tests/test_presentation.py`

The orchestrator reads `widget.bg_color`. When a widget is wrapped by `WidgetPresenter` (for `presentation = "rainbow"` etc.), the orchestrator sees the presenter — which doesn't have `bg_color`. Forward it via a property.

- [ ] **Step 1: Add a failing test**

Append to `tests/test_presentation.py`:

```python
class TestBgColorForwarding:
    def test_bg_color_returns_wrapped_widget_bg(self):
        from led_ticker.presentation import WidgetPresenter, Rainbow
        from led_ticker.widgets.message import TickerMessage

        # Need a stub Color (graphics.Color isn't available in unit tests
        # without going through the compat shim).
        class StubColor:
            red, green, blue = 10, 20, 30

        msg = TickerMessage(message="hi", bg_color=StubColor())
        wrapped = WidgetPresenter(msg, Rainbow())
        assert wrapped.bg_color is msg.bg_color

    def test_bg_color_returns_none_when_widget_has_no_bg(self):
        from led_ticker.presentation import WidgetPresenter, Rainbow
        from led_ticker.widgets.message import TickerMessage

        msg = TickerMessage(message="hi")  # bg_color defaults to None
        wrapped = WidgetPresenter(msg, Rainbow())
        assert wrapped.bg_color is None
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_presentation.py::TestBgColorForwarding -v"`
Expected: FAIL — `TickerMessage` does not yet accept `bg_color` (will add in Task 3) AND `WidgetPresenter.bg_color` does not exist.

NOTE: If you reach this task before Task 3, the test errors on `TickerMessage(bg_color=...)`. That's fine — Task 3 fixes it. Run *only* the second test for now (`test_bg_color_returns_none_when_widget_has_no_bg`); it should still fail with `AttributeError: 'WidgetPresenter' object has no attribute 'bg_color'`. The first test will pass green after Task 3.

- [ ] **Step 3: Add `bg_color` property on `WidgetPresenter`**

In `src/led_ticker/presentation.py`, inside the `WidgetPresenter` class (after `resume`, before `draw`), add:

```python
    @property
    def bg_color(self):
        """Forward bg_color from the wrapped widget so the orchestrator
        sees the correct background regardless of presentation wrapping."""
        return getattr(self.widget, "bg_color", None)
```

- [ ] **Step 4: Run only the no-bg test (TickerMessage doesn't accept bg yet)**

Run: `make test ARGS="tests/test_presentation.py::TestBgColorForwarding::test_bg_color_returns_none_when_widget_has_no_bg -v"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/presentation.py tests/test_presentation.py
git commit -m "WidgetPresenter forwards bg_color from wrapped widget"
```

---

### Task 3: TickerMessage and TickerCountdown gain `bg_color` field

**Files:**
- Modify: `src/led_ticker/widgets/message.py`
- Test: `tests/test_widgets/test_message.py`

The widget itself doesn't paint bg — the orchestrator does (Task 11). But the field has to exist so the orchestrator can read it.

- [ ] **Step 1: Add a failing test**

Append to `tests/test_widgets/test_message.py`:

```python
class TestBgColor:
    def test_bg_color_default_is_none(self):
        msg = TickerMessage(message="hi")
        assert msg.bg_color is None

    def test_bg_color_accepts_color(self):
        from rgbmatrix.graphics import Color
        bg = Color(20, 40, 60)
        msg = TickerMessage(message="hi", bg_color=bg)
        assert msg.bg_color is bg

    def test_countdown_bg_color_default_is_none(self):
        from datetime import date
        cd = TickerCountdown(message="X", countdown_date=date(2099, 1, 1))
        assert cd.bg_color is None

    def test_countdown_accepts_bg_color(self):
        from datetime import date
        from rgbmatrix.graphics import Color
        cd = TickerCountdown(
            message="X", countdown_date=date(2099, 1, 1), bg_color=Color(1, 2, 3)
        )
        assert cd.bg_color.red == 1
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_widgets/test_message.py::TestBgColor -v"`
Expected: FAIL — `TickerMessage.__init__()` got an unexpected keyword argument `bg_color`.

- [ ] **Step 3: Add `bg_color` field to both classes**

In `src/led_ticker/widgets/message.py`, find `class TickerMessage` (around line 24) and add `bg_color` after `font_color`:

```python
@register("message")
@attrs.define
class TickerMessage:
    """A static text message for the LED display."""

    message: str
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
    _content_width: int = attrs.field(init=False, default=-1)
    _has_emoji: bool = attrs.field(init=False, default=False)
```

And the same for `TickerCountdown` (around line 86):

```python
@register("countdown")
@attrs.define
class TickerCountdown:
    """A countdown to a specific date."""

    message: str
    countdown_date: date
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
```

- [ ] **Step 4: Run TickerMessage tests, verify pass + nothing else regressed**

Run: `make test ARGS="tests/test_widgets/test_message.py -v"`
Expected: PASS (all existing + 4 new).

Also run the WidgetPresenter test from Task 2 — it should now pass too:
Run: `make test ARGS="tests/test_presentation.py::TestBgColorForwarding -v"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/message.py tests/test_widgets/test_message.py
git commit -m "TickerMessage + TickerCountdown gain bg_color field"
```

---

### Task 4: Weather widget gains `bg_color` field

**Files:**
- Modify: `src/led_ticker/widgets/weather.py`
- Test: `tests/test_widgets/test_weather.py`

Same pattern as Task 3.

- [ ] **Step 1: Add a failing test**

Append to `tests/test_widgets/test_weather.py`:

```python
def test_weather_bg_color_default_is_none(monkeypatch):
    monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
    from led_ticker.widgets.weather import WeatherWidget
    w = WeatherWidget(location="London")
    assert w.bg_color is None


def test_weather_bg_color_accepts_color(monkeypatch):
    monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
    from led_ticker.widgets.weather import WeatherWidget
    from rgbmatrix.graphics import Color
    w = WeatherWidget(location="London", bg_color=Color(5, 10, 15))
    assert w.bg_color.red == 5
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_widgets/test_weather.py::test_weather_bg_color_default_is_none tests/test_widgets/test_weather.py::test_weather_bg_color_accepts_color -v"`
Expected: FAIL — unexpected kwarg `bg_color`.

- [ ] **Step 3: Add `bg_color` field**

In `src/led_ticker/widgets/weather.py`, find the field declarations (around line 34) and add:

```python
    font_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    font_color_temp: Color = attrs.Factory(lambda: RGB_WHITE)
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `make test ARGS="tests/test_widgets/test_weather.py -v"`
Expected: PASS (all existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/weather.py tests/test_widgets/test_weather.py
git commit -m "WeatherWidget gains bg_color field"
```

---

### Task 5: Crypto widgets gain `bg_color` field

**Files:**
- Modify: `src/led_ticker/widgets/crypto/coinbase.py`
- Modify: `src/led_ticker/widgets/crypto/coingecko.py`
- Modify: `src/led_ticker/widgets/crypto/etherscan.py`
- Test: `tests/test_widgets/test_crypto.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_widgets/test_crypto.py`:

```python
class TestCryptoBgColor:
    def test_coinbase_bg_color_default_is_none(self):
        from led_ticker.widgets.crypto.coinbase import CoinbasePriceMonitor
        w = CoinbasePriceMonitor(symbol="BTC-USD")
        assert w.bg_color is None

    def test_coinbase_accepts_bg_color(self):
        from led_ticker.widgets.crypto.coinbase import CoinbasePriceMonitor
        from rgbmatrix.graphics import Color
        w = CoinbasePriceMonitor(symbol="BTC-USD", bg_color=Color(7, 8, 9))
        assert w.bg_color.green == 8

    def test_coingecko_bg_color_default_is_none(self):
        from led_ticker.widgets.crypto.coingecko import CoinGeckoPriceMonitor
        w = CoinGeckoPriceMonitor(coin_id="bitcoin")
        assert w.bg_color is None

    def test_coingecko_accepts_bg_color(self):
        from led_ticker.widgets.crypto.coingecko import CoinGeckoPriceMonitor
        from rgbmatrix.graphics import Color
        w = CoinGeckoPriceMonitor(coin_id="bitcoin", bg_color=Color(11, 12, 13))
        assert w.bg_color.blue == 13

    def test_etherscan_bg_color_default_is_none(self):
        from led_ticker.widgets.crypto.etherscan import EtherscanGasMonitor
        w = EtherscanGasMonitor()
        assert w.bg_color is None

    def test_etherscan_accepts_bg_color(self):
        from led_ticker.widgets.crypto.etherscan import EtherscanGasMonitor
        from rgbmatrix.graphics import Color
        w = EtherscanGasMonitor(bg_color=Color(99, 100, 101))
        assert w.bg_color.red == 99
```

NOTE: The exact constructor args for each crypto widget may differ (e.g., the symbol/coin_id naming). Inspect each class's `__attrs_attrs__` first if any of these constructor calls fail with a different error. The shape of the test (default None + accepts Color) is what matters.

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_widgets/test_crypto.py::TestCryptoBgColor -v"`
Expected: FAIL — unexpected kwarg `bg_color` on each.

- [ ] **Step 3: Add `bg_color` field to each crypto widget**

For each of the three files, find the `font_color` field declaration and add `bg_color: Color | None = attrs.field(default=None, kw_only=True)` immediately after. Example for `coinbase.py`:

```python
    font_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
```

If a crypto widget doesn't have a `font_color` field, place `bg_color` after the last existing kw-compatible field. Run the tests after each file edit to make sure you didn't break anything.

- [ ] **Step 4: Run tests, verify pass**

Run: `make test ARGS="tests/test_widgets/test_crypto.py -v"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/crypto/ tests/test_widgets/test_crypto.py
git commit -m "Crypto widgets gain bg_color field"
```

---

### Task 6: Container widgets (RSS, MLB, MLB standings) gain `bg_color` and propagate to stories

**Files:**
- Modify: `src/led_ticker/widgets/rss_feed.py`
- Modify: `src/led_ticker/widgets/mlb.py`
- Modify: `src/led_ticker/widgets/mlb_standings.py`
- Test: `tests/test_widgets/test_rss_feed.py`, `tests/test_widgets/test_mlb.py`, `tests/test_widgets/test_mlb_standings.py`

These widgets don't `draw()` themselves — they expand into a `feed_stories: list[TickerMessage]` (and similar variants) that the orchestrator iterates over. To carry the bg through, set `bg_color` on each story `TickerMessage` at construction time.

- [ ] **Step 1: Add a failing test for RSS**

Append to `tests/test_widgets/test_rss_feed.py`:

```python
class TestRssBgColor:
    def test_default_bg_is_none(self):
        from led_ticker.widgets.rss_feed import RSSFeedMonitor
        w = RSSFeedMonitor.__new__(RSSFeedMonitor)  # construct without start()
        assert getattr(w, "bg_color", None) is None or hasattr(RSSFeedMonitor, "bg_color")

    def test_bg_color_propagates_to_stories(self, monkeypatch):
        """When bg_color is set on the container, every story TickerMessage
        in feed_stories carries the same bg_color."""
        from led_ticker.widgets.rss_feed import RSSFeedMonitor
        from led_ticker.widgets.message import TickerMessage
        from rgbmatrix.graphics import Color

        bg = Color(40, 50, 60)
        feed = RSSFeedMonitor(url="https://example.com/feed", bg_color=bg)
        # Manually populate stories the way `start()` would. Bypass
        # network: build the messages directly using the same kwargs
        # the production code uses.
        feed.feed_title = TickerMessage("Title", bg_color=bg)
        feed.feed_stories = [
            TickerMessage(item, bg_color=bg) for item in ("a", "b", "c")
        ]

        assert feed.bg_color is bg
        assert feed.feed_title.bg_color is bg
        assert all(s.bg_color is bg for s in feed.feed_stories)
```

NOTE: The tighter `test_bg_color_propagates_to_stories` test — a *real* one that runs `start()` and asserts on the actually-built stories — requires mocking the HTTP layer. The test above is a structural proxy: it confirms (a) the container accepts the field, and (b) when stories are built with that field threaded through, they carry it. Step 3 is where the production `start()` actually does the threading; if you have time, also add a network-mocked story-build test.

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_widgets/test_rss_feed.py::TestRssBgColor -v"`
Expected: FAIL — `RSSFeedMonitor.__init__()` doesn't accept `bg_color`.

- [ ] **Step 3: Thread `bg_color` through `RSSFeedMonitor`**

In `src/led_ticker/widgets/rss_feed.py`:

1. Add the field. Find the existing field block (around the `colors` field) and add:

```python
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
```

2. In `start()` (or wherever `feed_stories` and `feed_title` are constructed — see lines around 54-60 from the file scan), thread `bg_color=self.bg_color` into every `TickerMessage(...)` call. Example:

```python
            self.feed_title = TickerMessage(
                self.title or "",
                font_color=next(self.colors),
                bg_color=self.bg_color,
            )
            self.feed_stories = [
                TickerMessage(
                    item["title"],
                    font_color=next(self.colors),
                    bg_color=self.bg_color,
                )
                for item in items
            ]
```

3. Run the tests:

Run: `make test ARGS="tests/test_widgets/test_rss_feed.py -v"`
Expected: PASS.

- [ ] **Step 4: Repeat for MLB**

Add to `tests/test_widgets/test_mlb.py`:

```python
class TestMlbBgColor:
    def test_default_bg_is_none(self):
        from led_ticker.widgets.mlb import MLBScoreMonitor
        w = MLBScoreMonitor.__new__(MLBScoreMonitor)
        assert hasattr(MLBScoreMonitor, "__attrs_attrs__")
        names = {a.name for a in MLBScoreMonitor.__attrs_attrs__}
        assert "bg_color" in names

    def test_accepts_bg_color(self):
        from led_ticker.widgets.mlb import MLBScoreMonitor
        from rgbmatrix.graphics import Color
        w = MLBScoreMonitor(team="NYY", bg_color=Color(70, 80, 90))
        assert w.bg_color.red == 70
```

In `src/led_ticker/widgets/mlb.py`:

1. Add the `bg_color` field next to the existing color fields on `MLBScoreMonitor`.
2. Find every `TickerMessage(...)` and `MLBGameMessage(...)` construction inside this file (file scan showed many around lines 473, 480, 499, 504, 513, 518, 531, 547). Thread `bg_color=self.bg_color` into each.
3. Also add `bg_color` to `MLBGameMessage` (the score-display class — find its `@attrs.define` block and add the same field). Game messages are stories that go into `feed_stories`, so they need it for orchestrator to pick up.

Run: `make test ARGS="tests/test_widgets/test_mlb.py -v"`
Expected: PASS.

- [ ] **Step 5: Repeat for MLB standings**

Add to `tests/test_widgets/test_mlb_standings.py`:

```python
class TestMlbStandingsBgColor:
    def test_default_bg_is_none(self):
        from led_ticker.widgets.mlb_standings import MLBStandingsMonitor
        names = {a.name for a in MLBStandingsMonitor.__attrs_attrs__}
        assert "bg_color" in names

    def test_accepts_bg_color(self):
        from led_ticker.widgets.mlb_standings import MLBStandingsMonitor
        from rgbmatrix.graphics import Color
        w = MLBStandingsMonitor(bg_color=Color(11, 22, 33))
        assert w.bg_color.green == 22
```

In `src/led_ticker/widgets/mlb_standings.py`:

1. Add the `bg_color` field.
2. Thread `bg_color=self.bg_color` into every internal `TickerMessage(...)` construction.

Run: `make test ARGS="tests/test_widgets/test_mlb_standings.py -v"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/rss_feed.py src/led_ticker/widgets/mlb.py src/led_ticker/widgets/mlb_standings.py tests/test_widgets/
git commit -m "Container widgets propagate bg_color to story TickerMessages"
```

---

### Task 7: TwoRowMessage gains `bg_color`, `top_bg_color`, `bottom_bg_color` and per-row band painting

**Files:**
- Modify: `src/led_ticker/widgets/two_row.py`
- Test: `tests/test_widgets/test_two_row.py`

`TwoRowMessage` is the only widget that paints bands itself in `draw()` (per spec: "TwoRowMessage paints per-row bands itself"). Section/widget `bg_color` is handled by the orchestrator in Task 11; per-row bands paint on top of whatever `reset_canvas` left.

The row split formula: top band = rows `[0, h//2)`, bottom = rows `[h//2, h)`. At `content_height = 20` → top is rows 0-9, bottom is 10-19.

- [ ] **Step 1: Add failing tests**

Append to `tests/test_widgets/test_two_row.py`:

```python
class TestTwoRowBgColor:
    def test_default_bg_fields_are_none(self):
        w = TwoRowMessage(top_text="A", bottom_text="B")
        assert w.bg_color is None
        assert w.top_bg_color is None
        assert w.bottom_bg_color is None

    def test_top_bg_color_paints_only_top_band(self, canvas):
        """top_bg_color fills rows 0..(h//2) with the bg color; rows
        h//2..h are not filled by the band painter (orchestrator may
        Clear them)."""
        from rgbmatrix.graphics import Color

        bg = Color(255, 0, 128)
        w = TwoRowMessage(
            top_text="",  # empty so we only see the bg paint
            bottom_text="",
            top_bg_color=bg,
        )
        # canvas fixture is 160x16 (small sign default). Half = 8.
        canvas.Clear()
        w.draw(canvas, cursor_pos=0)
        h = canvas.height
        mid = h // 2
        # Top band (rows 0..mid-1) should be magenta.
        for y in range(0, mid):
            for x in range(canvas.width):
                assert canvas.get_pixel(x, y) == (255, 0, 128), (
                    f"top band: row {y} should be magenta, got {canvas.get_pixel(x, y)}"
                )
        # Bottom band (rows mid..h-1) should be untouched (black).
        for y in range(mid, h):
            for x in range(canvas.width):
                assert canvas.get_pixel(x, y) == (0, 0, 0), (
                    f"bottom band: row {y} should be unset, got {canvas.get_pixel(x, y)}"
                )

    def test_bottom_bg_color_paints_only_bottom_band(self, canvas):
        from rgbmatrix.graphics import Color

        bg = Color(20, 200, 50)
        w = TwoRowMessage(top_text="", bottom_text="", bottom_bg_color=bg)
        canvas.Clear()
        w.draw(canvas, cursor_pos=0)
        h = canvas.height
        mid = h // 2
        for y in range(0, mid):
            for x in range(canvas.width):
                assert canvas.get_pixel(x, y) == (0, 0, 0)
        for y in range(mid, h):
            for x in range(canvas.width):
                assert canvas.get_pixel(x, y) == (20, 200, 50)

    def test_both_bands_paint_independently(self, canvas):
        from rgbmatrix.graphics import Color

        top_bg = Color(255, 0, 0)
        bottom_bg = Color(0, 0, 255)
        w = TwoRowMessage(
            top_text="",
            bottom_text="",
            top_bg_color=top_bg,
            bottom_bg_color=bottom_bg,
        )
        canvas.Clear()
        w.draw(canvas, cursor_pos=0)
        h = canvas.height
        mid = h // 2
        # spot-check center of each band
        assert canvas.get_pixel(canvas.width // 2, mid // 2) == (255, 0, 0)
        assert canvas.get_pixel(canvas.width // 2, mid + (h - mid) // 2) == (0, 0, 255)

    def test_per_row_bg_overrides_widget_bg_visually(self, canvas):
        """The widget's own `bg_color` is applied by the orchestrator
        (canvas already filled when draw() runs). Per-row bands paint
        on top — verify they win on their respective half."""
        from rgbmatrix.graphics import Color
        from led_ticker.widgets._image_fit import reset_canvas

        widget_bg = Color(50, 50, 50)
        top_bg = Color(255, 0, 0)
        w = TwoRowMessage(
            top_text="",
            bottom_text="",
            bg_color=widget_bg,
            top_bg_color=top_bg,
        )

        # Simulate orchestrator: reset_canvas with widget.bg_color, then draw.
        reset_canvas(canvas, w.bg_color)
        w.draw(canvas, cursor_pos=0)

        h = canvas.height
        mid = h // 2
        # Top band: top_bg wins.
        assert canvas.get_pixel(0, 0) == (255, 0, 0)
        # Bottom band: widget_bg shows through (no bottom_bg_color).
        assert canvas.get_pixel(0, mid) == (50, 50, 50)
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_widgets/test_two_row.py::TestTwoRowBgColor -v"`
Expected: FAIL — `TwoRowMessage.__init__()` doesn't accept `bg_color`.

- [ ] **Step 3: Add fields and per-row paint logic**

In `src/led_ticker/widgets/two_row.py`:

1. Add the three new fields. Find the field block around line 78-88 and add:

```python
    top_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    bottom_color: Color = attrs.Factory(lambda: DEFAULT_COLOR)
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    top_bg_color: Color | None = attrs.field(default=None, kw_only=True)
    bottom_bg_color: Color | None = attrs.field(default=None, kw_only=True)
    # Horizontal alignment per row: ...
    top_align: str = "center"
```

2. Update the imports at the top of `two_row.py` (around line 39):

```python
from led_ticker.widgets._image_fit import fill_band
```

3. In `draw()` (around line 101), paint the per-row bands BEFORE the existing emoji/text drawing:

```python
    def draw(self, canvas: Canvas, cursor_pos: int = 0, **kwargs: Any) -> DrawResult:
        del kwargs  # widget is meant for swap mode; y_offset/transitions ignored

        canvas_height = getattr(canvas, "height", 16)
        mid = canvas_height // 2
        if self.top_bg_color is not None:
            fill_band(canvas, 0, mid, self.top_bg_color)
        if self.bottom_bg_color is not None:
            fill_band(canvas, mid, canvas_height, self.bottom_bg_color)

        top_text_y, top_emoji_y = _row_y(canvas_height, row_index=0)
        # ... rest of the existing draw() body unchanged ...
```

- [ ] **Step 4: Run tests, verify pass**

Run: `make test ARGS="tests/test_widgets/test_two_row.py -v"`
Expected: PASS (all existing + 5 new). The new tests use `top_text=""` / `bottom_text=""` to avoid pixel collisions with text drawing.

If `test_top_text_drawn_at_fixed_position_regardless_of_cursor` regresses: the fix is to make sure your `fill_band` calls happen *before* `_row_y` etc., so they don't perturb the existing logic. The tests in this task only add new fields; they shouldn't change paint behavior when bg fields are `None`.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/two_row.py tests/test_widgets/test_two_row.py
git commit -m "TwoRowMessage gains bg_color + top_bg_color/bottom_bg_color"
```

---

### Task 8: `_BaseImageWidget` gains `bg_color` and routes `_paint_full` through `_paint_image`

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py`
- Test: `tests/test_widgets/test_image_base.py` (new file)

The trickiest piece. With `bg_color` set, every paint must go through skip-black so pillarbox / letterbox / transparent regions reveal bg. The base class adds a `_paint_image(canvas)` dispatcher: if `bg_color` is None, calls subclass `_paint_full` (today's SetImage fast path); else calls `_paint_skip_black`. `_render_tick` and the static-text fast path in `_play_with_text` use `_paint_image` instead of `_paint_full` so they get the bg-aware behavior, and they swap their `canvas.Clear()` for `reset_canvas(canvas, self.bg_color)`.

- [ ] **Step 1: Create test file with failing tests**

Create `tests/test_widgets/test_image_base.py`:

```python
"""Tests for _BaseImageWidget bg_color handling and _paint_image dispatch."""

from __future__ import annotations

import unittest.mock as mock

import attrs

from led_ticker._types import Canvas
from led_ticker.widgets._image_base import _BaseImageWidget


@attrs.define
class _DummyImage(_BaseImageWidget):
    """Test stub: tracks which paint path was called."""

    paint_full_calls: list = attrs.field(factory=list)
    paint_skip_black_calls: list = attrs.field(factory=list)

    def __attrs_post_init__(self) -> None:
        self._validate_common(image_align="center", fit="pillarbox")

    def _paint_full(self, canvas: Canvas) -> None:
        self.paint_full_calls.append(canvas)

    def _paint_skip_black(self, canvas: Canvas) -> None:
        self.paint_skip_black_calls.append(canvas)

    def _load(self, panel_w: int = 0, panel_h: int = 0) -> None:
        pass


class TestPaintImageDispatch:
    def test_no_bg_uses_paint_full(self):
        """bg_color=None → _paint_image calls _paint_full (SetImage fast path)."""
        w = _DummyImage()
        canvas = mock.Mock()
        w._paint_image(canvas)
        assert len(w.paint_full_calls) == 1
        assert len(w.paint_skip_black_calls) == 0

    def test_bg_set_uses_skip_black(self):
        """bg_color set → _paint_image calls _paint_skip_black so the
        pre-painted bg shows through pillarbox/letterbox/transparency."""
        from rgbmatrix.graphics import Color
        w = _DummyImage(bg_color=Color(10, 20, 30))
        canvas = mock.Mock()
        w._paint_image(canvas)
        assert len(w.paint_skip_black_calls) == 1
        assert len(w.paint_full_calls) == 0


class TestRenderTickResetsCanvas:
    """`_render_tick` calls reset_canvas(canvas, bg_color) instead of Clear()."""

    def test_no_bg_calls_clear(self):
        w = _DummyImage()
        canvas = mock.Mock()
        text_canvas = mock.Mock()
        w.text_align = "left"
        w._render_tick(canvas, text_canvas, 0, 10, 0, 100)
        canvas.Clear.assert_called_once_with()
        canvas.Fill.assert_not_called()

    def test_bg_calls_fill(self):
        from rgbmatrix.graphics import Color
        w = _DummyImage(bg_color=Color(40, 50, 60))
        canvas = mock.Mock()
        text_canvas = mock.Mock()
        w.text_align = "left"
        w._render_tick(canvas, text_canvas, 0, 10, 0, 100)
        canvas.Clear.assert_not_called()
        canvas.Fill.assert_called_once_with(40, 50, 60)
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_widgets/test_image_base.py -v"`
Expected: FAIL — `_BaseImageWidget` has no `bg_color`, no `_paint_image`. (Also the `_render_tick` direct calls will fail because the helper takes `text_canvas` and other args — match the signature from the existing source.)

- [ ] **Step 3: Add `bg_color` field and `_paint_image` dispatcher**

In `src/led_ticker/widgets/_image_base.py`:

1. Add a new import at the top (with the other `widgets._image_fit` imports near line 33):

```python
from led_ticker.widgets._image_fit import VALID_IMAGE_ALIGNS, reset_canvas, validate_choice
```

2. Add the `bg_color` field to `_BaseImageWidget` (after `font_color`, around line 70):

```python
    font_color: Color = attrs.field(
        default=attrs.Factory(lambda: DEFAULT_COLOR), kw_only=True
    )
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
```

3. Add the `_paint_image` method right after `_paint_skip_black` declaration (around line 95):

```python
    def _paint_image(self, canvas: Canvas) -> None:
        """Dispatch to the right paint path for the current `bg_color`.

        With no bg, use the subclass `_paint_full` fast path (SetImage in
        a single C call). With bg set, use `_paint_skip_black` so
        pillarbox / letterbox / transparent regions reveal the bg
        instead of being painted black.
        """
        if self.bg_color is None:
            self._paint_full(canvas)
        else:
            self._paint_skip_black(canvas)
```

4. Update `_render_tick` (around line 219) to use `reset_canvas` and `_paint_image`:

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
        image + paint text in the right order for the current
        `text_align`."""
        reset_canvas(canvas, self.bg_color)

        if self.text_align == "scroll":
            self._draw_text(text_canvas, scroll_pos, baseline_y, self.font_color)
            self._paint_skip_black(canvas)
        elif self.text_align == "scroll_over":
            self._paint_image(canvas)
            self._draw_text(text_canvas, scroll_pos, baseline_y, self.font_color)
        else:
            self._paint_image(canvas)
            text_x = text_x_left if self.text_align == "left" else text_x_right
            self._draw_text(text_canvas, text_x, baseline_y, self.font_color)
```

NOTE: the `text_align == "scroll"` branch keeps `_paint_skip_black` regardless of bg. That's correct — scroll mode requires skip-black for the text-under-image effect, so it was already on that path.

- [ ] **Step 4: Run new tests, verify pass**

Run: `make test ARGS="tests/test_widgets/test_image_base.py -v"`
Expected: PASS.

Also run the existing image-widget tests to make sure nothing regressed:

Run: `make test ARGS="tests/test_widgets/test_gif.py tests/test_widgets/test_still.py -v"`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_base.py
git commit -m "_BaseImageWidget: bg_color field + _paint_image dispatch + reset_canvas in _render_tick"
```

---

### Task 9: GifPlayer `_play_no_text` honors `bg_color`

**Files:**
- Modify: `src/led_ticker/widgets/gif.py:262-277`
- Test: `tests/test_widgets/test_gif.py`

Today `_play_no_text` calls `canvas.Clear()` + `_paint_full(canvas)`. With bg, those need to become `reset_canvas` + `_paint_image`.

- [ ] **Step 1: Add a failing test**

Append to `tests/test_widgets/test_gif.py`:

```python
class TestGifBgColor:
    @pytest.mark.asyncio
    async def test_bg_color_default_paints_full(self, tmp_path, mocker):
        """No bg_color → _play_no_text uses canvas.Clear + _paint_full
        (existing fast path)."""
        from led_ticker.widgets.gif import GifPlayer
        # Tiny test gif: 2x2 red square, 2 frames.
        from PIL import Image

        path = tmp_path / "tiny.gif"
        frames = [Image.new("RGB", (2, 2), (255, 0, 0))] * 2
        frames[0].save(
            path, save_all=True, append_images=frames[1:], duration=50, loop=0
        )

        gif = GifPlayer(path=str(path))
        canvas = mocker.MagicMock()
        canvas.width = 4
        canvas.height = 4
        # Inject decoded frames directly to bypass actual decode in tests.
        gif._frames = [(b"\x00" * (4 * 4 * 3), 50), (b"\x00" * (4 * 4 * 3), 50)]
        gif._panel_w = 4
        gif._panel_h = 4

        frame_obj = mocker.MagicMock()
        frame_obj.matrix.SwapOnVSync.side_effect = lambda c: c
        await gif._play_no_text(canvas, frame_obj, loop_count=1)

        # No bg → Clear should have been called per-frame (2 frames × 1 loop = 2).
        assert canvas.Clear.call_count == 2
        canvas.Fill.assert_not_called()

    @pytest.mark.asyncio
    async def test_bg_color_set_uses_fill(self, tmp_path, mocker):
        """bg_color set → _play_no_text uses canvas.Fill(bg) per-frame."""
        from led_ticker.widgets.gif import GifPlayer
        from rgbmatrix.graphics import Color
        from PIL import Image

        path = tmp_path / "tiny.gif"
        frames = [Image.new("RGB", (2, 2), (255, 0, 0))] * 2
        frames[0].save(
            path, save_all=True, append_images=frames[1:], duration=50, loop=0
        )

        gif = GifPlayer(path=str(path), bg_color=Color(80, 90, 100))
        canvas = mocker.MagicMock()
        canvas.width = 4
        canvas.height = 4
        gif._frames = [(b"\x00" * (4 * 4 * 3), 50)]
        gif._panel_w = 4
        gif._panel_h = 4

        frame_obj = mocker.MagicMock()
        frame_obj.matrix.SwapOnVSync.side_effect = lambda c: c
        await gif._play_no_text(canvas, frame_obj, loop_count=1)

        canvas.Clear.assert_not_called()
        canvas.Fill.assert_called_with(80, 90, 100)
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_widgets/test_gif.py::TestGifBgColor -v"`
Expected: FAIL on `test_bg_color_set_uses_fill` — `canvas.Fill` was never called (Clear was). The default test should pass already.

- [ ] **Step 3: Update `_play_no_text` to use `reset_canvas` + `_paint_image`**

In `src/led_ticker/widgets/gif.py`, find `_play_no_text` (around line 262) and replace the inner loop body:

```python
from led_ticker.widgets._image_fit import reset_canvas
```

(Add this import near the top, with the other `widgets._image_fit`-related imports.)

```python
    async def _play_no_text(
        self, real_canvas: Canvas, frame: Any, loop_count: int
    ) -> Canvas:
        loops = max(1, loop_count)
        canvas = real_canvas

        for _ in range(loops):
            for idx, (_pixels, duration_ms) in enumerate(self._frames):
                self._current_frame_idx = idx
                reset_canvas(canvas, self.bg_color)
                self._paint_image(canvas)
                canvas = frame.matrix.SwapOnVSync(canvas)
                await asyncio.sleep(duration_ms / 1000)

        self._current_frame_idx = len(self._frames) - 1
        return canvas
```

NOTE: `_paint_image` lives on the shared `_BaseImageWidget` — added in Task 8.

- [ ] **Step 4: Run tests, verify pass**

Run: `make test ARGS="tests/test_widgets/test_gif.py -v"`
Expected: PASS (all existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/gif.py tests/test_widgets/test_gif.py
git commit -m "GifPlayer._play_no_text honors bg_color via reset_canvas + _paint_image"
```

---

### Task 10: StillImage `_play_no_text` honors `bg_color`

**Files:**
- Modify: `src/led_ticker/widgets/still.py:251-257`
- Test: `tests/test_widgets/test_still.py`

Same pattern as Task 9 but for the still widget.

- [ ] **Step 1: Add a failing test**

Append to `tests/test_widgets/test_still.py`:

```python
class TestStillBgColor:
    def test_default_bg_is_none(self, tmp_path):
        from PIL import Image
        from led_ticker.widgets.still import StillImage
        path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(path)
        s = StillImage(path=str(path))
        assert s.bg_color is None

    @pytest.mark.asyncio
    async def test_bg_color_set_uses_fill_in_play(self, tmp_path, mocker):
        from PIL import Image
        from rgbmatrix.graphics import Color
        from led_ticker.widgets.still import StillImage

        path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(path)
        s = StillImage(path=str(path), bg_color=Color(11, 22, 33))

        canvas = mocker.MagicMock()
        canvas.width = 4
        canvas.height = 4
        # Bypass decode; pre-populate panel dims and pixels.
        s._pixels = b"\x00" * (4 * 4 * 3)
        s._panel_w = 4
        s._panel_h = 4

        frame_obj = mocker.MagicMock()
        frame_obj.matrix.SwapOnVSync.side_effect = lambda c: c
        await s._play_no_text(canvas, frame_obj)

        canvas.Clear.assert_not_called()
        canvas.Fill.assert_called_once_with(11, 22, 33)
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_widgets/test_still.py::TestStillBgColor -v"`
Expected: FAIL — `Fill` not called (Clear was).

- [ ] **Step 3: Update `_play_no_text`**

In `src/led_ticker/widgets/still.py`, add the import and replace `_play_no_text`:

```python
from led_ticker.widgets._image_fit import reset_canvas
```

(near the top with existing `_image_fit` imports)

```python
    async def _play_no_text(self, real_canvas: Canvas, frame: Any) -> Canvas:
        canvas = real_canvas
        reset_canvas(canvas, self.bg_color)
        self._paint_image(canvas)
        canvas = frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(self.hold_seconds)
        return canvas
```

- [ ] **Step 4: Run tests, verify pass**

Run: `make test ARGS="tests/test_widgets/test_still.py -v"`
Expected: PASS (all existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/still.py tests/test_widgets/test_still.py
git commit -m "StillImage._play_no_text honors bg_color via reset_canvas + _paint_image"
```

---

### Task 11: Ticker orchestrator uses `reset_canvas(canvas, widget.bg_color)`

**Files:**
- Modify: `src/led_ticker/ticker.py` — three sites: `_swap_and_scroll` (lines 749, 769), `_scroll_one_by_one` (lines 361, 376), `_scroll_side_by_side` (line 423)
- Test: `tests/test_ticker_display.py`

The orchestrator is the bg-paint authority for text widgets. Use `getattr(widget, "bg_color", None)` so widgets that haven't been touched yet (anything we missed) still work.

- [ ] **Step 1: Add a failing test**

Append to `tests/test_ticker_display.py`:

```python
class TestSwapAndScrollUsesResetCanvas:
    @pytest.mark.asyncio
    async def test_no_bg_calls_clear(self, mock_frame):
        from led_ticker.ticker import _swap_and_scroll
        import unittest.mock as mock_mod

        canvas = mock_mod.MagicMock()
        canvas.width = 160
        canvas.height = 16
        widget = mock_mod.MagicMock()
        widget.bg_color = None
        widget.draw.return_value = (canvas, 100)

        await _swap_and_scroll(canvas, mock_frame, widget, hold_time=0.0)

        canvas.Clear.assert_called()
        canvas.Fill.assert_not_called()

    @pytest.mark.asyncio
    async def test_bg_color_set_calls_fill(self, mock_frame):
        from led_ticker.ticker import _swap_and_scroll
        from rgbmatrix.graphics import Color
        import unittest.mock as mock_mod

        canvas = mock_mod.MagicMock()
        canvas.width = 160
        canvas.height = 16
        widget = mock_mod.MagicMock()
        widget.bg_color = Color(70, 80, 90)
        widget.draw.return_value = (canvas, 100)

        await _swap_and_scroll(canvas, mock_frame, widget, hold_time=0.0)

        canvas.Clear.assert_not_called()
        canvas.Fill.assert_called_with(70, 80, 90)
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_ticker_display.py::TestSwapAndScrollUsesResetCanvas -v"`
Expected: FAIL on `test_bg_color_set_calls_fill` — Fill not called.

- [ ] **Step 3: Replace `canvas.Clear()` with `reset_canvas(canvas, widget.bg_color)` in three orchestrator sites**

In `src/led_ticker/ticker.py`:

1. Add the import near the top (with the existing `from led_ticker.widgets...` imports):

```python
from led_ticker.widgets._image_fit import reset_canvas
```

2. In `_swap_and_scroll` (around line 749), replace the two `canvas.Clear()` calls. Use a helper alias to keep the loop tight:

```python
async def _swap_and_scroll(
    canvas: Canvas,
    frame: Any,
    ticker_obj: Any,
    scroll_speed: float = 0.05,
    hold_time: float = 3,
    skip_initial_draw: bool = False,
    continuous: bool = False,
) -> tuple[Canvas, int, int]:
    """Display a widget. If it overflows, hold then scroll the full text."""
    pos = 0
    bg_color = getattr(ticker_obj, "bg_color", None)
    reset_canvas(canvas, bg_color)
    canvas, cursor_pos = ticker_obj.draw(canvas, pos)

    if not skip_initial_draw:
        canvas = _swap(canvas, frame)

    if cursor_pos > canvas.width:
        if not continuous:
            await asyncio.sleep(hold_time)

        padding = get_widget_padding(ticker_obj, default=0)
        stop_pos = -(cursor_pos - canvas.width) + padding
        while pos > stop_pos:
            pos -= 1
            reset_canvas(canvas, bg_color)
            canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
            canvas = _swap(canvas, frame)
            await asyncio.sleep(scroll_speed)

        if not continuous:
            await asyncio.sleep(hold_time)
    else:
        await asyncio.sleep(hold_time)

    return canvas, cursor_pos, pos
```

3. In `_scroll_one_by_one` (around line 327): the inner `canvas.Clear()` at line 361 and the trailing one at 376 both need replacement. The `bg_color` here changes per-widget as `ticker_object` is updated. Read the bg fresh each iteration:

```python
async def _scroll_one_by_one(
    canvas: Canvas,
    frame: Any,
    notif_queue: asyncio.Queue[Any],
    delay: float = 0,
    cursor_pos: int = 0,
    scroll_speed: float = 0.05,
) -> int:
    ticker_object = await notif_queue.get()
    pos = cursor_pos
    last_drawn_pos = pos

    if delay:
        canvas, cursor_pos = await _scroll_and_delay(
            canvas, frame, ticker_object, delay, cursor_pos=pos,
        )
        logging.info("Returned to _scroll_one_by_one ...")
        pos = 0
        last_drawn_pos = pos

    while True:
        reset_canvas(canvas, getattr(ticker_object, "bg_color", None))
        canvas, final_pos = ticker_object.draw(canvas, cursor_pos=pos)
        last_drawn_pos = pos
        pos -= 1

        if final_pos < 0:
            pos = canvas.width
            try:
                ticker_object = notif_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        canvas = _swap(canvas, frame)
        await asyncio.sleep(scroll_speed)

    canvas.Clear()  # final blank — keep as Clear (no specific widget bg here)
    canvas = _swap(canvas, frame)
    return last_drawn_pos
```

4. In `_scroll_side_by_side` (around line 384): the `canvas.Clear()` inside the outer `while True:` (around line 423) is more nuanced — multiple widgets can be drawn side-by-side in one frame, so there's no single `bg_color`. Per spec: "transition-time bg leak between sections" is an accepted footgun; same logic applies for side-by-side mixed bg widgets within a section. Resolve to **the FIRST buffered widget's** `bg_color` (the leftmost one currently visible).

```python
async def _scroll_side_by_side(...):
    # ... unchanged setup ...
    while True:
        first_widget = buffered_objects[0] if buffered_objects else None
        bg = getattr(first_widget, "bg_color", None) if first_widget else None
        reset_canvas(canvas, bg)
        # ... rest of loop unchanged ...
```

Insert at the top of the `while True:` (replacing the bare `canvas.Clear()`).

5. Also `_scroll_and_delay` (line 305) and the `while pos > 0` body inside it (line 317) — these also `Clear()`. Same treatment using the passed `ticker_obj`:

```python
async def _scroll_and_delay(
    canvas, frame, ticker_obj, delay, cursor_pos=0, scroll_speed=0.05,
):
    bg_color = getattr(ticker_obj, "bg_color", None)
    reset_canvas(canvas, bg_color)
    pos = cursor_pos

    canvas, cursor_pos = ticker_obj.draw(canvas, cursor_pos=pos)

    if pos <= 0:
        canvas = _swap(canvas, frame)

    while pos > 0:
        reset_canvas(canvas, bg_color)
        canvas, cursor_pos = ticker_obj.draw(canvas, cursor_pos=pos)
        pos -= 1
        canvas = _swap(canvas, frame)
        await asyncio.sleep(scroll_speed)

    await asyncio.sleep(delay)
    return canvas, cursor_pos
```

- [ ] **Step 4: Run tests, verify pass**

Run: `make test ARGS="tests/test_ticker_display.py -v"`
Expected: PASS — including the new `TestSwapAndScrollUsesResetCanvas` cases.

Also run the full ticker suite:

Run: `make test ARGS="tests/test_ticker.py tests/test_ticker_display.py -v"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker_display.py
git commit -m "Ticker orchestrator uses reset_canvas(widget.bg_color) in scroll/swap paths"
```

---

### Task 12: `SectionConfig.bg_color` and `app.py` plumbing

**Files:**
- Modify: `src/led_ticker/config.py:44-60, 151-161`
- Modify: `src/led_ticker/app.py:47, 71-123`
- Test: `tests/test_config.py`, `tests/test_app.py`

`SectionConfig` gains the field; `_COLOR_KEYS` extends to include `bg_color`/`top_bg_color`/`bottom_bg_color`; `_build_widget` injects the section default into widget configs that omit it.

- [ ] **Step 1: Add failing config tests**

Append to `tests/test_config.py`:

```python
def test_section_bg_color_defaults_to_none(tmp_path):
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        '[display]\nrows=16\ncols=32\nchain=5\n'
        '[[playlist.section]]\nmode="forever_scroll"\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].bg_color is None


def test_section_bg_color_parsed_from_toml(tmp_path):
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        '[display]\nrows=16\ncols=32\nchain=5\n'
        '[[playlist.section]]\nmode="forever_scroll"\n'
        'bg_color=[26, 59, 142]\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].bg_color == (26, 59, 142)
```

- [ ] **Step 2: Run, verify failure**

Run: `make test ARGS="tests/test_config.py::test_section_bg_color_defaults_to_none tests/test_config.py::test_section_bg_color_parsed_from_toml -v"`
Expected: FAIL — `SectionConfig.__init__()` doesn't accept `bg_color`.

- [ ] **Step 3: Add the field to `SectionConfig` and parse it**

In `src/led_ticker/config.py`:

1. Add to `SectionConfig` (around line 60):

```python
@dataclass
class SectionConfig:
    mode: str
    loop_count: int = 1
    title: dict | None = None
    widgets: list[dict] = field(default_factory=list)
    transition: TransitionConfig = field(default_factory=TransitionConfig)
    hold_time: float = 3.0
    continuous_scroll: bool = False
    scale: int = 1
    content_height: int = 16
    bg_color: tuple[int, int, int] | None = None
```

2. Parse it in `load_config` (around line 151):

```python
        bg_color_raw = section_raw.get("bg_color")
        bg_color = tuple(bg_color_raw) if bg_color_raw is not None else None

        section = SectionConfig(
            mode=section_raw.get("mode", "forever_scroll"),
            loop_count=section_raw.get("loop_count", 1),
            title=section_raw.get("title"),
            widgets=section_raw.get("widget", []),
            transition=trans,
            hold_time=section_raw.get("hold_time", 3.0),
            continuous_scroll=section_raw.get("continuous_scroll", False),
            scale=section_raw.get("scale", display.default_scale),
            content_height=section_raw.get("content_height", 16),
            bg_color=bg_color,
        )
```

- [ ] **Step 4: Run config tests, verify pass**

Run: `make test ARGS="tests/test_config.py -v"`
Expected: PASS.

- [ ] **Step 5: Add failing app-level tests**

Append to `tests/test_app.py`:

```python
class TestColorKeysExtended:
    def test_color_keys_includes_bg_keys(self):
        from led_ticker.app import _COLOR_KEYS
        assert "bg_color" in _COLOR_KEYS
        assert "top_bg_color" in _COLOR_KEYS
        assert "bottom_bg_color" in _COLOR_KEYS


class TestBuildWidgetSectionBgPropagation:
    @pytest.mark.asyncio
    async def test_section_bg_propagates_when_widget_omits_it(self):
        """When the section config has bg_color and the widget config
        doesn't, the widget receives the section bg as a default."""
        from led_ticker.app import _build_widget
        import aiohttp
        async with aiohttp.ClientSession() as session:
            widget_cfg = {"type": "message", "text": "hi"}
            widget = await _build_widget(
                widget_cfg, session, default_bg_color=(10, 20, 30),
            )
        assert widget.bg_color is not None
        assert widget.bg_color.red == 10
        assert widget.bg_color.green == 20
        assert widget.bg_color.blue == 30

    @pytest.mark.asyncio
    async def test_widget_bg_overrides_section_bg(self):
        """When both section and widget specify bg_color, widget wins."""
        from led_ticker.app import _build_widget
        import aiohttp
        async with aiohttp.ClientSession() as session:
            widget_cfg = {
                "type": "message",
                "text": "hi",
                "bg_color": [100, 100, 100],
            }
            widget = await _build_widget(
                widget_cfg, session, default_bg_color=(10, 20, 30),
            )
        assert widget.bg_color.red == 100  # widget value, not section

    @pytest.mark.asyncio
    async def test_no_section_bg_no_widget_bg_yields_none(self):
        from led_ticker.app import _build_widget
        import aiohttp
        async with aiohttp.ClientSession() as session:
            widget_cfg = {"type": "message", "text": "hi"}
            widget = await _build_widget(widget_cfg, session)
        assert widget.bg_color is None
```

- [ ] **Step 6: Run, verify failure**

Run: `make test ARGS="tests/test_app.py::TestColorKeysExtended tests/test_app.py::TestBuildWidgetSectionBgPropagation -v"`
Expected: FAIL — `_COLOR_KEYS` lacks new keys; `_build_widget` doesn't accept `default_bg_color`.

- [ ] **Step 7: Extend `_COLOR_KEYS` and `_build_widget` signature**

In `src/led_ticker/app.py`:

1. Extend `_COLOR_KEYS` (line 47):

```python
_COLOR_KEYS: set[str] = {
    "font_color",
    "color",
    "top_color",
    "bottom_color",
    "bg_color",
    "top_bg_color",
    "bottom_bg_color",
}
```

2. Update `_build_widget` signature and body (line 71):

```python
async def _build_widget(
    widget_cfg: dict[str, Any],
    session: aiohttp.ClientSession,
    config_dir: Path | None = None,
    default_bg_color: tuple[int, int, int] | None = None,
) -> Any:
    """Instantiate a widget from its config dict.

    `default_bg_color` is the section-level bg as an `(r, g, b)` tuple
    (or None). It's injected into `widget_cfg["bg_color"]` only when
    the widget config doesn't already specify it — preserving the
    "widget overrides section" precedence rule.
    """
    widget_type = widget_cfg.pop("type")
    cls = get_widget_class(widget_type)

    # Inject section default before color coercion runs. Skip when the
    # widget already specified bg_color (widget-level wins).
    if default_bg_color is not None and "bg_color" not in widget_cfg:
        widget_cfg["bg_color"] = list(default_bg_color)

    # ... rest of function unchanged ...
```

3. Update the `run()` function (around line 220) to pass section bg to `_build_widget`:

```python
                    cfg = dict(widget_cfg)
                    widget = await _build_widget(
                        cfg,
                        session,
                        config_dir=config_path.parent,
                        default_bg_color=section.bg_color,
                    )
```

- [ ] **Step 8: Run app tests, verify pass**

Run: `make test ARGS="tests/test_app.py::TestColorKeysExtended tests/test_app.py::TestBuildWidgetSectionBgPropagation -v"`
Expected: PASS.

- [ ] **Step 9: Run full suite to confirm nothing regressed**

Run: `make test`
Expected: PASS (everything; ~580+ tests). If any failure points at a widget that was missed in this plan, add the `bg_color: Color | None = attrs.field(default=None, kw_only=True)` field to that widget — the orchestrator's `getattr(widget, "bg_color", None)` should already cope, but `_COLOR_KEYS` coercion expects the field to accept a `Color` object.

- [ ] **Step 10: Commit**

```bash
git add src/led_ticker/config.py src/led_ticker/app.py tests/test_config.py tests/test_app.py
git commit -m "SectionConfig.bg_color + app.py propagation + extended _COLOR_KEYS"
```

---

## Done — final checks

After all 12 tasks:

- [ ] `make test` — full suite green.
- [ ] `make lint` — no new ruff warnings.
- [ ] Manual smoke check (config-only, no hardware): write a small TOML config with section `bg_color = [26, 59, 142]` and a widget that doesn't override; load via `from led_ticker.config import load_config` in a Python REPL; confirm the section's `bg_color` is `(26, 59, 142)`. Then run the app build path against a stubbed `aiohttp.ClientSession` and confirm the produced TickerMessage's `bg_color.red == 26`.

The hardware smoke test is whatever the user typically uses for visual verification on the bigsign — setting `bg_color = [26, 59, 142]` on a section with a `TickerMessage` should produce navy LEDs everywhere except the text glyphs.
