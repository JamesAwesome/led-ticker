# Batch 7: Widget Contract Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the widget protocol surface: add a typed `Playable` protocol + make `_has_play` raise loudly on sync `play` attrs (Medium #8), and replace the `**kwargs` escape hatch in `Widget.draw` with explicit typed params (Medium #4).

**Architecture:** Two independent tasks. Task 1 adds a new `Playable` Protocol and tightens `_has_play`'s error behaviour. Task 2 surgically removes `**kwargs` from the `Widget.draw` Protocol and all 10 implementing `draw()` methods, hoisting `y_offset` and `font_color` as explicit keyword-only params.

**Tech Stack:** Python 3.12, attrs, asyncio, pytest (asyncio_mode="auto"), `inspect.iscoroutinefunction`

---

## File Map

### Task 1 (Medium #8 — Playable Protocol + assertive `_has_play`)

| Action | Path |
|--------|------|
| Modify | `src/led_ticker/widget.py` |
| Modify | `src/led_ticker/ticker.py` |
| Modify | `tests/test_ticker.py` |

### Task 2 (Medium #4 — drop `**kwargs`, hoist explicit params)

| Action | Path |
|--------|------|
| Modify | `src/led_ticker/widget.py` |
| Modify | `src/led_ticker/widgets/message.py` (TickerMessage + TickerCountdown) |
| Modify | `src/led_ticker/widgets/mlb.py` |
| Modify | `src/led_ticker/widgets/weather.py` |
| Modify | `src/led_ticker/widgets/crypto/etherscan.py` |
| Modify | `src/led_ticker/widgets/crypto/coinbase.py` |
| Modify | `src/led_ticker/widgets/crypto/coingecko.py` |
| Modify | `src/led_ticker/widgets/gif.py` |
| Modify | `src/led_ticker/widgets/two_row.py` |
| Modify | `src/led_ticker/widgets/still.py` |
| Modify | `tests/test_widget_protocol.py` |

---

## Task 1: Playable Protocol + assertive `_has_play`

**Files:**
- Modify: `src/led_ticker/widget.py`
- Modify: `src/led_ticker/ticker.py:774-781`
- Modify: `tests/test_ticker.py`

### Context

`src/led_ticker/widget.py` currently has `Widget` and `Updatable` protocols. There is no typed `Playable` protocol.

`src/led_ticker/ticker.py` `_has_play` (lines 774–781):
```python
def _has_play(widget: Any) -> bool:
    """True iff `widget`'s class declares an async `play` method.

    Looks at the class (not the instance) so Mocks — which auto-create
    a callable `.play` attribute on access — don't false-positive.
    """
    method = getattr(type(widget), "play", None)
    return inspect.iscoroutinefunction(method)
```

Problem: if `play` exists on the class but is NOT async, `_has_play` silently returns `False` → widget silently falls to the `draw()` path. A developer who forgets `async` on `play` gets no error.

### Steps

- [ ] **Step 1: Write the failing tests**

Add a new `TestHasPlayDispatch` class to `tests/test_ticker.py`. Import `_has_play` from `led_ticker.ticker` (it's not in the current import block — add it).

```python
from led_ticker.ticker import (
    _build_ticker_iter,
    _CircleBufferMsg,
    _draw_hires_circle,
    _enqueue_ticker_objects,
    _has_index,
    _has_play,       # ← add this
    _maybe_wrap,
    _scroll_one_by_one,
    _scroll_side_by_side,
    _swap,
)
```

Add at end of `tests/test_ticker.py`:
```python
class TestHasPlayDispatch:
    def test_returns_true_for_async_play(self):
        class AsyncWidget:
            async def play(self, canvas): ...
        assert _has_play(AsyncWidget()) is True

    def test_returns_false_for_no_play(self):
        class DrawOnlyWidget:
            def draw(self, canvas, cursor_pos=0): ...
        assert _has_play(DrawOnlyWidget()) is False

    def test_raises_for_sync_play(self):
        class SyncPlayWidget:
            def play(self, canvas): ...
        with pytest.raises(RuntimeError, match="play.*not.*coroutine"):
            _has_play(SyncPlayWidget())

    def test_mock_returns_false_not_raises(self):
        """MagicMock auto-creates .play on access — must not raise."""
        w = MagicMock()
        assert _has_play(w) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
pytest tests/test_ticker.py::TestHasPlayDispatch -v
```

Expected: `test_raises_for_sync_play` FAILS (no RuntimeError raised currently).

- [ ] **Step 3: Add `Playable` Protocol to `widget.py`**

In `src/led_ticker/widget.py`, add `Playable` after `Updatable`:

```python
@runtime_checkable
class Playable(Protocol):
    """Any widget that runs its own async display loop via ``play()``."""

    async def play(self, canvas: Canvas) -> None:
        """Drive the display until cancelled."""
        ...
```

Also update the module-level import in the `from led_ticker.widget import ...` public surface. In `src/led_ticker/widget.py` there is no `__all__`, so just adding the class is enough. Update the module docstring if it lists exports:

```python
"""Widget protocols and shared lifecycle helpers."""
```

That docstring is fine as-is — no change needed.

- [ ] **Step 4: Update `_has_play` to raise on sync `play`**

In `src/led_ticker/ticker.py`, replace `_has_play` (lines 774–781):

```python
def _has_play(widget: Any) -> bool:
    """True iff ``widget``'s class declares an async ``play`` method.

    Looks at the class (not the instance) so Mocks — which auto-create
    a callable ``.play`` attribute on access — don't false-positive.

    Raises ``RuntimeError`` if the class has a ``play`` attribute that is
    NOT a coroutinefunction: that is almost certainly a missing ``async``
    keyword and would silently route the widget to the ``draw()`` path.
    """
    method = getattr(type(widget), "play", None)
    if method is None:
        return False
    if not inspect.iscoroutinefunction(method):
        raise RuntimeError(
            f"{type(widget).__name__}.play exists but is not a coroutine function. "
            "Did you forget 'async def play'?"
        )
    return True
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_ticker.py::TestHasPlayDispatch -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
pytest --tb=short -q
```

Expected: all tests pass (1833+4 = 1837 or similar).

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/widget.py src/led_ticker/ticker.py tests/test_ticker.py
git commit -m "feat: add Playable Protocol; raise on sync play attr in _has_play"
```

---

## Task 2: Drop `**kwargs` from `Widget.draw`, hoist explicit params

**Files:**
- Modify: `src/led_ticker/widget.py`
- Modify: `src/led_ticker/widgets/message.py`
- Modify: `src/led_ticker/widgets/mlb.py`
- Modify: `src/led_ticker/widgets/weather.py`
- Modify: `src/led_ticker/widgets/crypto/etherscan.py`
- Modify: `src/led_ticker/widgets/crypto/coinbase.py`
- Modify: `src/led_ticker/widgets/crypto/coingecko.py`
- Modify: `src/led_ticker/widgets/gif.py`
- Modify: `src/led_ticker/widgets/two_row.py`
- Modify: `src/led_ticker/widgets/still.py`
- Modify: `tests/test_widget_protocol.py`

### Context

Current `Widget.draw` in `src/led_ticker/widget.py` (lines 22–40):
```python
@runtime_checkable
class Widget(Protocol):
    """Any object that can draw itself to an LED canvas."""

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        **kwargs: Any,
    ) -> DrawResult:
        """Render to canvas starting at cursor_pos.

        Recognized kwargs:
        - ``y_offset`` (int): vertical offset from natural baseline
        - ``font_color`` (Color): override the widget's own font color

        ``scale`` is **not** a kwarg. ...

        Returns (canvas, new_cursor_pos).
        """
        ...
```

The `region` kwarg is dead — nothing consumes it in any widget `draw()`. `run_transition` still accepts `region` as an explicit named param for forward-compat, so `test_run_transition_accepts_region_kwarg` is kept.

All 10 widget `draw()` calls from callers pass `y_offset` and `font_color` as named keyword args (`outgoing.draw(canvas, cursor_pos=0, y_offset=...)`) — switching from `**kwargs` to explicit params doesn't break callers.

**Classification of widgets:**
- 7 that read from kwargs: `TickerMessage`, `TickerCountdown`, `mlb`, `weather`, `etherscan`, `coinbase`, `coingecko`
- 3 that just delete kwargs: `gif`, `two_row`, `still`

### Steps

- [ ] **Step 1: Write failing tests**

In `tests/test_widget_protocol.py`:

1. Delete `test_widget_protocol_accepts_region_kwarg` (the whole function, lines 17–27).

2. Update `SimpleWidget.draw` (line 43) and `SimpleAsyncWidget.draw` (line 53) to remove `**kwargs`:
```python
class SimpleWidget:
    """A minimal Widget implementation for testing."""

    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        return canvas, cursor_pos + 10


class SimpleAsyncWidget:
    """A minimal AsyncWidget implementation for testing."""

    def __init__(self):
        self.update_count = 0

    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        return canvas, cursor_pos + 10

    async def update(self):
        self.update_count += 1
```

3. Add a new test asserting that `Widget.draw` does NOT accept arbitrary kwargs:
```python
def test_widget_draw_rejects_unknown_kwargs():
    from led_ticker.frame import LedFrame
    from led_ticker.widgets.message import TickerMessage

    msg = TickerMessage(message="hi")
    frame = LedFrame(led_cols=32, led_chain=5)
    canvas = frame.get_clean_canvas()
    with pytest.raises(TypeError):
        msg.draw(canvas, cursor_pos=0, region="should-fail")
```

- [ ] **Step 2: Run tests to verify the new test fails**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
pytest tests/test_widget_protocol.py::test_widget_draw_rejects_unknown_kwargs -v
```

Expected: FAIL — `TickerMessage.draw` currently accepts `**kwargs` so no `TypeError` is raised.

- [ ] **Step 3: Update `Widget` Protocol in `widget.py`**

In `src/led_ticker/widget.py`, replace the `Widget` Protocol's `draw` signature and docstring:

```python
@runtime_checkable
class Widget(Protocol):
    """Any object that can draw itself to an LED canvas."""

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        """Render to canvas starting at cursor_pos.

        ``y_offset``: vertical offset from the widget's natural baseline.
        ``font_color``: override the widget's own font color (Color or ColorProvider).

        ``scale`` is **not** a param. If ``canvas`` is a ``ScaledCanvas``,
        scaling is transparent. Widgets that need to read scale can use
        ``getattr(canvas, "scale", 1)``.

        Returns (canvas, new_cursor_pos).
        """
        ...
```

Note: `Any` is still imported. No new imports needed.

- [ ] **Step 4: Update `TickerMessage.draw` in `widgets/message.py`**

Replace the signature and kwargs extraction at line 56 onward:

```python
def draw(
    self,
    canvas: Canvas,
    cursor_pos: int = 0,
    *,
    y_offset: int = 0,
    font_color: Any = None,
) -> DrawResult:
    # Allow callers to override font_color (coerce raw Color to provider).
    if font_color is not None and not hasattr(font_color, "color_for"):
        font_color = _ConstantColor(font_color)
    provider: ColorProvider = font_color or self.font_color
```

Remove `import Any` if it becomes unused — but `Any` is imported from `typing` for `animation: Any | None` on the class, so leave `from typing import Any` in place.

The body of `draw` after the kwargs extraction doesn't change — `y_offset` and `provider` are still used the same way.

- [ ] **Step 5: Update `TickerCountdown.draw` in `widgets/message.py`**

Same pattern — `TickerCountdown.draw` starts at line 229. Replace:

```python
def draw(
    self,
    canvas: Canvas,
    cursor_pos: int = 0,
    *,
    y_offset: int = 0,
    font_color: Any = None,
) -> DrawResult:
    # Allow callers to override font_color (coerce raw Color to provider).
    if font_color is not None and not hasattr(font_color, "color_for"):
        font_color = _ConstantColor(font_color)
    provider: ColorProvider = font_color or self.font_color
```

- [ ] **Step 6: Update `mlb.py` `MlbScores.draw`**

In `src/led_ticker/widgets/mlb.py`, line 273. Replace the signature and `y_offset` extraction:

```python
def draw(
    self,
    canvas: Canvas,
    cursor_pos: int = 0,
    *,
    y_offset: int = 0,
    font_color: Any = None,
) -> DrawResult:
```

Remove the line `y_offset: int = kwargs.get("y_offset", 0)` that follows.

Also remove `from typing import Any` if it's only used for `**kwargs: Any` — but check the rest of the file first. `Any` appears in `from typing import Any, Self` (line 12) and is used for `font_color: Color | ColorProvider` which comes from `_types`. Leave the import as-is.

- [ ] **Step 7: Update `weather.py` `WeatherWidget.draw`**

In `src/led_ticker/widgets/weather.py`, line 118. Replace the signature and `y_offset` extraction:

```python
def draw(
    self,
    canvas: Canvas,
    cursor_pos: int = 0,
    *,
    y_offset: int = 0,
    font_color: Any = None,
) -> DrawResult:
```

Remove the line `y_offset: int = kwargs.get("y_offset", 0)`.

Note: `weather.py` doesn't use `font_color` from kwargs at all (the widget uses its own hardcoded colors), so `font_color` becomes a no-op param. That's fine — Protocol conformance requires the signature match.

- [ ] **Step 8: Update `etherscan.py` `EtherscanWidget.draw`**

In `src/led_ticker/widgets/crypto/etherscan.py`, line 110. Replace the signature and `y_offset` extraction:

```python
def draw(
    self,
    canvas: Canvas,
    cursor_pos: int = 0,
    *,
    y_offset: int = 0,
    font_color: Any = None,
) -> DrawResult:
```

Remove `y_offset: int = kwargs.get("y_offset", 0)`.

Note: `etherscan.py` uses `y_offset` in `baseline_y = compute_baseline(...) + y_offset` — that line stays as-is.

- [ ] **Step 9: Update `coinbase.py` `CoinbaseWidget.draw`**

In `src/led_ticker/widgets/crypto/coinbase.py`, line 125. Replace the signature and kwarg pass-through:

```python
def draw(
    self,
    canvas: Canvas,
    cursor_pos: int = 0,
    *,
    y_offset: int = 0,
    font_color: Any = None,
) -> DrawResult:
    change_str = f"{self.change_24h:.2f}%"
    price_str = f"{self.price:.4f}"
    return _draw_price_ticker(
        canvas,
        self.symbol,
        price_str,
        change_str,
        cursor_pos=cursor_pos,
        center=self.center,
        padding=self.padding,
        end_padding=self.padding,
        y_offset=y_offset,
        font_color=self.font_color,
        frame_count=self.frame_for("font_color"),
    )
```

(Replace `kwargs.get("y_offset", 0)` with `y_offset`.)

- [ ] **Step 10: Update `coingecko.py` `CoingeckoWidget.draw`**

In `src/led_ticker/widgets/crypto/coingecko.py`, line 97. Same pattern:

```python
def draw(
    self,
    canvas: Canvas,
    cursor_pos: int = 0,
    *,
    y_offset: int = 0,
    font_color: Any = None,
) -> DrawResult:
    return _draw_price_ticker(
        canvas,
        self.symbol,
        self.price_data["price"],
        self.price_data["change_24h"],
        cursor_pos=cursor_pos,
        center=self.center,
        padding=self.padding,
        end_padding=self.padding,
        y_offset=y_offset,
        font_color=self.font_color,
        frame_count=self.frame_for("font_color"),
    )
```

- [ ] **Step 11: Update `gif.py`, `two_row.py`, `still.py` (del-kwargs widgets)**

These three just `del kwargs` (or `del cursor_pos, kwargs`). Replace with explicit params and remove the `del kwargs`:

**`src/led_ticker/widgets/gif.py`** line 233:
```python
def draw(
    self,
    canvas: Canvas,
    cursor_pos: int = 0,
    *,
    y_offset: int = 0,
    font_color: Any = None,
) -> DrawResult:
    """Paint the current frame to the real canvas at native res.

    Used for transition compositing (entry/exit dissolves). Text is
    intentionally NOT painted here — the dissolve looks cleaner
    with just the gif, and there's no scroll-position state at
    draw time.
    """
    del cursor_pos, y_offset, font_color
    real = unwrap_to_real(canvas)
    ...
```

**`src/led_ticker/widgets/two_row.py`** line 405:
```python
def draw(
    self,
    canvas: Canvas,
    cursor_pos: int = 0,
    *,
    y_offset: int = 0,
    font_color: Any = None,
) -> DrawResult:
    del y_offset, font_color  # widget is meant for swap mode; transitions ignored
    ...
```

**`src/led_ticker/widgets/still.py`** line 216:
```python
def draw(
    self,
    canvas: Canvas,
    cursor_pos: int = 0,
    *,
    y_offset: int = 0,
    font_color: Any = None,
) -> DrawResult:
    """Paint the image to the real canvas at native res. Used for
    transition compositing only (text is not painted here — see
    :meth:`GifPlayer.draw` for rationale)."""
    del cursor_pos, y_offset, font_color
    real = unwrap_to_real(canvas)
    ...
```

- [ ] **Step 12: Run tests**

```bash
pytest --tb=short -q
```

Expected: all tests pass. In particular:
- `test_widget_draw_rejects_unknown_kwargs` PASSES (TypeError raised)
- `test_run_transition_accepts_region_kwarg` still PASSES (run_transition unchanged)
- All widget draw tests still pass (no positional callers broken)

If any test passes a `region=` kwarg directly to a widget draw method, it will now fail — update that test to remove the `region=` kwarg. The only such test was `test_widget_protocol_accepts_region_kwarg` which is already deleted in Step 1.

- [ ] **Step 13: Commit**

```bash
git add src/led_ticker/widget.py \
        src/led_ticker/widgets/message.py \
        src/led_ticker/widgets/mlb.py \
        src/led_ticker/widgets/weather.py \
        src/led_ticker/widgets/crypto/etherscan.py \
        src/led_ticker/widgets/crypto/coinbase.py \
        src/led_ticker/widgets/crypto/coingecko.py \
        src/led_ticker/widgets/gif.py \
        src/led_ticker/widgets/two_row.py \
        src/led_ticker/widgets/still.py \
        tests/test_widget_protocol.py
git commit -m "refactor: drop **kwargs from Widget.draw; hoist explicit y_offset/font_color params"
```

---

## Self-Review

### Spec Coverage

| Requirement | Task | Status |
|-------------|------|--------|
| Add `Playable` Protocol to `widget.py` | Task 1 Step 3 | ✅ |
| `_has_play` raises on sync `play` attr | Task 1 Step 4 | ✅ |
| `_has_play` returns False for no-play | Task 1 Step 4 | ✅ |
| `_has_play` returns True for async play | Task 1 Step 4 | ✅ |
| Drop `**kwargs` from `Widget.draw` Protocol | Task 2 Step 3 | ✅ |
| Hoist `y_offset: int = 0` as explicit param | Task 2 Steps 3–11 | ✅ |
| Hoist `font_color: Color \| None = None` param | Task 2 Steps 3–11 | ✅ |
| Update TickerMessage.draw | Task 2 Step 4 | ✅ |
| Update TickerCountdown.draw | Task 2 Step 5 | ✅ |
| Update mlb.draw | Task 2 Step 6 | ✅ |
| Update weather.draw | Task 2 Step 7 | ✅ |
| Update etherscan.draw | Task 2 Step 8 | ✅ |
| Update coinbase.draw | Task 2 Step 9 | ✅ |
| Update coingecko.draw | Task 2 Step 10 | ✅ |
| Update gif / two_row / still | Task 2 Step 11 | ✅ |
| Delete dead `region` from Widget docstring | Task 2 Step 3 | ✅ |
| Delete `test_widget_protocol_accepts_region_kwarg` | Task 2 Step 1 | ✅ |
| Update SimpleWidget / SimpleAsyncWidget | Task 2 Step 1 | ✅ |
| Keep `test_run_transition_accepts_region_kwarg` | Task 2 Step 1 (kept) | ✅ |

### Placeholder Scan

No "TBD", "TODO", or "implement later" strings. All steps include code. Types, method signatures, and property names are consistent throughout.

### Type Consistency

- `font_color: Any = None` used consistently in all 10 widget signatures — matches `Widget` Protocol param name
- `y_offset: int = 0` consistent across Protocol and all implementations
- `_has_play` raises `RuntimeError` consistently
- `Playable.play(self, canvas: Canvas) -> None` — `Canvas` already imported in `widget.py`
