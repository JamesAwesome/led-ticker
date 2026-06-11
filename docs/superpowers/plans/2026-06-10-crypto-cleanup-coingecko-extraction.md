# Crypto Cleanup + CoinGecko Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the coinbase and etherscan widgets from led-ticker core and move coingecko into a new `led-ticker-crypto` plugin (namespace `crypto`, widget `crypto.coingecko`), as a faithful pixel-identical port.

**Architecture:** Three sequenced PRs. (Phase 0) promote `compute_cursor` to the `led_ticker.plugin` public surface in core. (Phase 1) stand up `led-ticker-crypto`, copying coingecko + the coinbase price-ticker renderer + the trend palette, rewired to the public surface and validated pixel-identical. (Phase 2) one core PR deletes the whole `crypto/` package, its tests/docs/demos/skill-refs, prunes orphaned font constants, and adds a migration error. Phase 3 (review of the live API + tests + enhancements) is a SEPARATE plan written after this lands, because its tasks depend on what the live-API check finds.

**Tech Stack:** Python 3.14, attrs, aiohttp, pytest (asyncio_mode=auto), ruff, uv, hatchling. Plugin contract: `register(api)` under the `led_ticker.plugins` entry point; import only `led_ticker.plugin`.

**Spec:** `docs/superpowers/specs/2026-06-10-crypto-cleanup-coingecko-extraction-design.md`

**Standing rules (every task):** never commit on `main` — each repo uses its own worktree + branch + PR; run `git branch --show-current` and abort if `main`. Commit with `--no-verify` (global hooksPath needs a venv not present here). End commit messages with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. No "footgun"/"gun" metaphors. Do NOT merge any PR without explicit user go-ahead. Do NOT run `gh repo create` without explicit user go-ahead (outward-facing).

---

## File map

**Core (`led-ticker`), Phase 0 — branch `feat/public-compute-cursor`:**
- Modify: `src/led_ticker/plugin.py` — import + export `compute_cursor`
- Modify: `tests/test_plugin_surface.py` — assert `compute_cursor` is importable + in `__all__`
- Modify: `docs/site/src/content/docs/plugins/api-reference.mdx` — add the `compute_cursor` row (drift-guarded)

**New repo `led-ticker-crypto`, Phase 1 — branch `main` then feature work:**
- Create: `pyproject.toml`, `README.md`, `CLAUDE.md`, `.github/workflows/ci.yml`, `.gitignore`
- Create: `src/led_ticker_crypto/__init__.py` — `register(api)`
- Create: `src/led_ticker_crypto/_colors.py` — trend palette (lazy)
- Create: `src/led_ticker_crypto/_ticker_render.py` — shared renderer + `_ConstantColor` + helpers
- Create: `src/led_ticker_crypto/coingecko.py` — the `crypto.coingecko` widget
- Create: `tests/conftest.py`, `tests/test_coingecko.py`, `tests/test_import_purity.py`, `tests/test_smoke.py`
- Create: `tools/compare_render.py` — pixel-identity check vs core (temporary, kept in repo)

**Core (`led-ticker`), Phase 2 — branch `chore/remove-crypto-widgets`:**
- Delete: `src/led_ticker/widgets/crypto/` (whole dir)
- Modify: `src/led_ticker/widgets/__init__.py` — drop the crypto import
- Modify: `src/led_ticker/app/factories.py` — drop the Coinbase/CoinGecko `FieldHint` block; add migration error
- Modify: `src/led_ticker/fonts/__init__.py` — prune orphaned `FONT_LABEL/FONT_DELTA/FONT_VALUE/FONT_VALUE_SMALL` IF unused elsewhere
- Delete: `tests/test_widgets/test_crypto.py`, `tests/test_widgets/test_crypto_colors.py`, `tests/test_widgets/test_etherscan.py`
- Create: `tests/test_widgets/test_crypto_migration.py` — migration-error unit test
- Delete: `docs/content-source/widgets/{coinbase,coingecko,etherscan}.md`, `docs/site/demos-long/widget-{coinbase,coingecko,etherscan}.toml`
- Modify: `.claude/skills/creating-a-config/{SKILL.md,references/widget-selection.md,references/snippets.md,references/asset-handling.md}`
- Modify: `CLAUDE.md` — drop crypto package-layout line; add `led-ticker-crypto` to Plugin ecosystem
- Modify: `config/config.example.toml`, `config/config.bigsign.example.toml` — drop any crypto blocks

---

## Phase 0 — Promote `compute_cursor` (core)

Work in a worktree off `led-ticker` main: `git worktree add -b feat/public-compute-cursor ../lt-compute-cursor main`.

### Task 0: Export `compute_cursor` from the public surface

**Files:**
- Modify: `src/led_ticker/plugin.py` (import block near line 35; `__all__` near line 104)
- Test: `tests/test_plugin_surface.py`
- Modify: `docs/site/src/content/docs/plugins/api-reference.mdx`

- [ ] **Step 1: Write the failing test.** Add to `tests/test_plugin_surface.py`:

```python
def test_compute_cursor_is_public():
    import led_ticker.plugin as P
    from led_ticker.drawing import compute_cursor as core_compute_cursor

    assert "compute_cursor" in P.__all__
    assert P.compute_cursor is core_compute_cursor
```

- [ ] **Step 2: Run it, expect FAIL.** `cd ../lt-compute-cursor && uv run pytest tests/test_plugin_surface.py::test_compute_cursor_is_public -q` → fails (`compute_cursor` not on `plugin`).

- [ ] **Step 3: Implement.** In `src/led_ticker/plugin.py`, add `compute_cursor` to the existing `from led_ticker.drawing import (...)` block (which already pulls `compute_baseline`, `compute_baseline_for_band`, `get_text_width`), and add `"compute_cursor",` to `__all__` next to `"compute_baseline"`.

- [ ] **Step 4: Run it, expect PASS.** Same command → passes.

- [ ] **Step 5: Update the drift-guarded docs.** Add a `compute_cursor` row to `docs/site/src/content/docs/plugins/api-reference.mdx` mirroring the `compute_baseline` row's format. Describe it: "Resolve a start cursor + end padding for content of a given width (centering / overflow math). Signature: `compute_cursor(canvas_width, content_width, cursor_pos, end_padding, center) -> (cursor_pos, end_padding)`."

- [ ] **Step 6: Run the drift + full suite.** `uv run pytest tests/test_docs_plugin_api_drift.py tests/test_plugin_surface.py -q` then `make test`. Expected: all pass.

- [ ] **Step 7: Commit.**

```bash
cd /Users/james/projects/github/jamesawesome/lt-compute-cursor
git add -A
git commit --no-verify -m "feat(plugin): promote compute_cursor to the public surface

compute_cursor is the sibling of the already-public compute_baseline /
get_text_width layout primitives; the led-ticker-crypto plugin's price-ticker
renderer needs it. Export + __all__ + api-reference row.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 8: Push + open PR (do NOT merge).** `git push --no-verify -u origin feat/public-compute-cursor`; `gh pr create --repo JamesAwesome/led-ticker --base main --title "feat(plugin): promote compute_cursor to the public surface" --body "..."`. Report the PR; wait for CI + user go-ahead to merge. **Phase 1 can start in parallel but the plugin's CI will only pass once this is merged** (the plugin imports `compute_cursor`).

---

## Phase 1 — `led-ticker-crypto` plugin (new repo)

### Task 1: Create the repo + scaffolding

**Confirm with the user before `gh repo create`.** Then:

- [ ] **Step 1: Create repo + local checkout** (sibling of led-ticker):

```bash
cd /Users/james/projects/github/jamesawesome
gh repo create JamesAwesome/led-ticker-crypto --public --description "CoinGecko crypto-price widget for led-ticker" --clone
cd led-ticker-crypto
git branch --show-current   # expect main; this repo has no protected history yet
```

- [ ] **Step 2: Create `pyproject.toml`** (adapted from led-ticker-pool):

```toml
[project]
name = "led-ticker-crypto"
version = "0.1.0"
description = "Crypto-price widgets for led-ticker (CoinGecko)."
readme = "README.md"
requires-python = ">=3.14"
authors = [{ name = "James Awesome", email = "james@morelli.nyc" }]
dependencies = ["led-ticker", "aiohttp"]

# Entry-point NAME ("crypto") is the plugin namespace → TOML `type = "crypto.coingecko"`.
[project.entry-points."led_ticker.plugins"]
crypto = "led_ticker_crypto:register"

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "ruff"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/led_ticker_crypto"]

[tool.uv.sources]
led-ticker = { path = "../led-ticker", editable = true }

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["../led-ticker/tests/stubs"]
```

- [ ] **Step 3: Create `.github/workflows/ci.yml`** — copy `led-ticker-pool/.github/workflows/ci.yml` verbatim, replacing every `led-ticker-pool` with `led-ticker-crypto` (the two checkout `path:`/`working-directory:` values and the job name). Keep `LED_TICKER_DEPLOY_KEY`, Python 3.14, `ruff check src tests`, `pytest -q`.

- [ ] **Step 4: Create `.gitignore`** — copy `led-ticker-pool/.gitignore` (or a standard Python one: `__pycache__/`, `*.pyc`, `.venv/`, `dist/`, `*.egg-info/`, `.pytest_cache/`, `uv.lock` if pool ignores it — match pool).

- [ ] **Step 5: Commit scaffolding.**

```bash
git add -A && git commit --no-verify -m "chore: scaffold led-ticker-crypto plugin (pyproject, CI, gitignore)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 2: Port the trend palette → `_colors.py`

**Files:** Create `src/led_ticker_crypto/_colors.py`, `src/led_ticker_crypto/__init__.py` (placeholder so the package imports).

- [ ] **Step 1: Create `src/led_ticker_crypto/_colors.py`** (verbatim from core, only the import changes to the public surface; keeps the lazy `__getattr__` so import touches no graphics):

```python
"""Trend colors for crypto widgets (ported from led-ticker core crypto/_colors.py).

Positive / negative / neutral price movement. Constructed lazily via PEP 562
`__getattr__` (same pattern as core), so importing this module is a no-op
against the rgbmatrix graphics library.
"""

from typing import TYPE_CHECKING

from led_ticker.plugin import colors

if TYPE_CHECKING:
    from led_ticker.plugin import Color


_trend_palette = colors.lazy_palette(
    {
        "UP_TREND_COLOR": (46, 200, 46),
        "DOWN_TREND_COLOR": (194, 24, 7),
        "NEUTRAL_TREND_COLOR": (180, 180, 180),
    }
)


def __getattr__(name: str) -> "Color":
    return _trend_palette(name)
```

- [ ] **Step 2: Create a minimal `src/led_ticker_crypto/__init__.py`** (filled in fully in Task 4):

```python
"""led-ticker-crypto: crypto-price widgets for led-ticker (CoinGecko)."""
```

- [ ] **Step 3: Verify it imports.** `cd /Users/james/projects/github/jamesawesome/led-ticker-crypto && uv sync --extra dev && uv run python -c "from led_ticker_crypto._colors import UP_TREND_COLOR; print(UP_TREND_COLOR)"`. Expected: prints a Color (no error). NOTE: this needs Phase 0's `compute_cursor` only at Task 3+, not here.

- [ ] **Step 4: Commit.** `git add -A && git commit --no-verify -m "feat: port crypto trend palette (_colors.py)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"`

### Task 3: Port the price-ticker renderer → `_ticker_render.py`

**Files:** Create `src/led_ticker_crypto/_ticker_render.py`.

This is the coinbase `_draw_price_ticker` (+ `_get_change_color`, `_get_price_font`, and a local `_ConstantColor`), adapted to the public surface. Adaptations vs core: (a) fonts via `resolve_font`/`FONT_DEFAULT`/`FONT_SMALL`; (b) the public `draw_text(canvas, font, text, x, y, color)` returns ABSOLUTE next-x → `cursor_pos = draw_text(...)` instead of `cursor_pos += draw_text(canvas, font, x, y, color, text)`; (c) the yellow `(255,255,0)` default constructed lazily in-function; (d) `_ConstantColor` defined locally (core's is private).

- [ ] **Step 1: Create `src/led_ticker_crypto/_ticker_render.py`:**

```python
"""Shared price-ticker renderer for crypto widgets.

Ported from led-ticker core's `widgets/crypto/coinbase._draw_price_ticker`
(coinbase was removed from core; the renderer travels with the plugin).
Lives as a shared module so a future `crypto.coinbase` could reuse it.

Adapted to the public `led_ticker.plugin` surface: the public `draw_text`
returns the ABSOLUTE next-x (and routes inline emoji), so core's
`cursor_pos += draw_text(canvas, font, x, y, color, text)` became
`cursor_pos = draw_text(canvas, font, text, x, y, color)` — pixel-identical
for plain text (proven by the led-ticker-baseball migration).
"""

from led_ticker.plugin import (
    FONT_DEFAULT,
    FONT_SMALL,
    Canvas,
    Color,
    ColorProvider,
    ColorProviderBase,
    DrawResult,
    Font,
    compute_baseline,
    compute_cursor,
    draw_text,
    get_text_width,
    make_color,
    resolve_font,
)

from led_ticker_crypto._colors import (
    DOWN_TREND_COLOR,
    NEUTRAL_TREND_COLOR,
    UP_TREND_COLOR,
)

# Core FONT_VALUE/FONT_VALUE_SMALL == 6x12/5x8 (FONT_DEFAULT/FONT_SMALL);
# FONT_LABEL/FONT_DELTA are the general 7x13/6x10 BDF faces.
FONT_LABEL: Font = resolve_font("7x13")
FONT_VALUE: Font = FONT_DEFAULT
FONT_VALUE_SMALL: Font = FONT_SMALL
FONT_DELTA: Font = resolve_font("6x10")


class _ConstantColor(ColorProviderBase):
    """Wraps a single Color so a plain `font_color = [r,g,b]` routes through
    the same `color_for` interface as effects. (Core's _ConstantColor is private.)"""

    per_char: bool = False
    frame_invariant: bool = True

    def __init__(self, color: Color) -> None:
        self._color = color

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        return self._color


def make_default_font_color() -> ColorProvider:
    """Core's default font_color: DEFAULT_COLOR == (255, 255, 0) (yellow)."""
    return _ConstantColor(make_color(255, 255, 0))


def _get_change_color(change_str: str) -> Color:
    try:
        value = float(change_str.rstrip("%"))
    except (ValueError, AttributeError):
        return NEUTRAL_TREND_COLOR
    if value < 0:
        return DOWN_TREND_COLOR
    if value > 0:
        return UP_TREND_COLOR
    return NEUTRAL_TREND_COLOR


def _get_price_font(price_str: str) -> Font:
    if len(price_str) > 10:
        return FONT_VALUE_SMALL
    return FONT_VALUE


def draw_price_ticker(
    canvas: Canvas,
    symbol: str,
    price_str: str,
    change_str: str,
    cursor_pos: int = 0,
    center: bool = True,
    padding: int = 6,
    end_padding: int = 6,
    y_offset: int = 0,
    font_color: ColorProvider | None = None,
    frame_count: int = 0,
) -> DrawResult:
    change_color = _get_change_color(change_str)
    font_price = _get_price_font(price_str)
    label_color = (
        font_color.color_for(frame_count, 0, 1)
        if font_color is not None
        else make_color(255, 255, 0)
    )

    content_width = (
        get_text_width(FONT_LABEL, symbol, padding=6, canvas=canvas)
        + get_text_width(font_price, price_str, padding=6, canvas=canvas)
        + get_text_width(FONT_DELTA, change_str, padding=0, canvas=canvas)
    )

    cursor_pos, end_padding = compute_cursor(
        canvas.width, content_width, cursor_pos, end_padding, center
    )

    baseline_y = compute_baseline(FONT_LABEL, canvas, valign="center") + y_offset
    cursor_pos = draw_text(canvas, FONT_LABEL, symbol, cursor_pos, baseline_y, label_color)
    cursor_pos += padding
    cursor_pos = draw_text(canvas, font_price, price_str, cursor_pos, baseline_y, label_color)
    cursor_pos += padding
    cursor_pos = draw_text(canvas, FONT_DELTA, change_str, cursor_pos, baseline_y, change_color)
    cursor_pos += end_padding

    return canvas, cursor_pos
```

- [ ] **Step 2: Verify import** (needs Phase 0 merged OR a local editable led-ticker with `compute_cursor` — if Phase 0 isn't merged yet, temporarily check out the `feat/public-compute-cursor` branch in the sibling `../led-ticker` so the import resolves): `uv run python -c "from led_ticker_crypto._ticker_render import draw_price_ticker; print('ok')"`. Expected: `ok`.

- [ ] **Step 3: Commit.** `git add -A && git commit --no-verify -m "feat: port price-ticker renderer (_ticker_render.py)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"`

### Task 4: Port the widget → `coingecko.py` + register

**Files:** Create `src/led_ticker_crypto/coingecko.py`; finalize `src/led_ticker_crypto/__init__.py`.

- [ ] **Step 1: Create `src/led_ticker_crypto/coingecko.py`** (core coingecko, minus the `@register` decorator, imports rewired, renderer from the local module, `_ConstantColor`/default from `_ticker_render`):

```python
"""CoinGecko price monitor widget (crypto.coingecko)."""

import logging
from typing import Any, Self

import aiohttp
import attrs

from led_ticker.plugin import (
    Canvas,
    Color,
    ColorProvider,
    DrawResult,
    FrameAwareBase,
    run_monitor_loop,
    spawn_tracked,
)

from led_ticker_crypto._ticker_render import (
    _ConstantColor,
    draw_price_ticker,
    make_default_font_color,
)

COINGECKO_API: str = "https://api.coingecko.com/api/v3"
COINGECKO_COIN_LIST: str = f"{COINGECKO_API}/coins/list"
COINGECKO_PRICE_API: str = f"{COINGECKO_API}/simple/price"


@attrs.define
class CoinGeckoPriceMonitor(FrameAwareBase):
    """Crypto price monitor using the CoinGecko API."""

    symbol: str
    symbol_id: str
    currency: str
    session: aiohttp.ClientSession
    center: bool = True
    padding: int = 6
    hold_time: float = 0.0
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider = attrs.field(default=None, kw_only=True)
    price_data: dict[str, str] = attrs.field(
        init=False,
        factory=lambda: {"price": "0.0000", "change_24h": "0.00%"},
    )

    def __attrs_post_init__(self) -> None:
        if self.font_color is None:
            self.font_color = make_default_font_color()
        elif not hasattr(self.font_color, "color_for"):
            self.font_color = _ConstantColor(self.font_color)

    @classmethod
    async def start(
        cls,
        symbol: str,
        symbol_id: str,
        currency: str,
        session: aiohttp.ClientSession,
        update_interval: int = 300,
        **kwargs: Any,
    ) -> Self:
        valid = {f.name for f in attrs.fields(cls)}
        widget = cls(
            symbol=symbol,
            symbol_id=symbol_id,
            currency=currency,
            session=session,
            **{k: v for k, v in kwargs.items() if k in valid},
        )
        await widget.update()
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self) -> None:
        logging.info("Updating monitor for %s via CoinGecko", self.symbol)
        params: dict[str, Any] = {
            "ids": [self.symbol_id],
            "vs_currencies": self.currency,
            "include_24hr_change": "true",
        }
        async with self.session.get(COINGECKO_PRICE_API, params=params) as response:
            price_data = await response.json()
            cur = self.currency.lower()
            cur_change = f"{cur}_24h_change"

            for coin_id, data in price_data.items():
                try:
                    price = f"{data[cur]:,.4f}"
                    change_24h = f"{data[cur_change]:.2f}%"
                except (KeyError, TypeError):
                    logging.warning("API data not complete for %s: %s", coin_id, data)
                    continue

                self.price_data = {"price": price, "change_24h": change_24h}

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        return draw_price_ticker(
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


async def _get_coingecko_coin_list(
    session: aiohttp.ClientSession,
) -> list[dict[str, Any]]:
    logging.info("Fetching CoinGecko coin list...")
    headers = {"Accept": "application/json"}
    async with session.get(COINGECKO_COIN_LIST, headers=headers) as response:
        return await response.json()


def _find_coingecko_symbol_id(
    coin_list: list[dict[str, Any]], symbol: str
) -> str | None:
    for coin_meta in coin_list:
        if symbol.lower() == coin_meta["symbol"].lower():
            return coin_meta["id"]
    return None
```

(Note: core's `start_coingecko_monitors` is dropped — it is engine-dead, only test-referenced; Phase 3 review owns any further dead-code decisions. `_find_coingecko_symbol_id` is kept because it has tests.)

- [ ] **Step 2: Finalize `src/led_ticker_crypto/__init__.py`:**

```python
"""led-ticker-crypto: crypto-price widgets for led-ticker (CoinGecko)."""

from led_ticker_crypto.coingecko import CoinGeckoPriceMonitor


def register(api):
    api.widget("coingecko")(CoinGeckoPriceMonitor)
```

- [ ] **Step 3: Verify it loads** `uv run python -c "import led_ticker_crypto; print(led_ticker_crypto.register)"`. Expected: prints the function.

- [ ] **Step 4: Commit.** `git add -A && git commit --no-verify -m "feat: port coingecko widget + register as crypto.coingecko\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"`

### Task 5: Tests (ported + tripwires)

**Files:** Create `tests/conftest.py`, `tests/test_coingecko.py`, `tests/test_import_purity.py`, `tests/test_smoke.py`.

- [ ] **Step 1: Create `tests/conftest.py`** — a `canvas` fixture matching core's test canvas. Copy the `canvas` fixture from `../led-ticker/tests/conftest.py` (a 160×16 stub canvas). If it can't be copied cleanly, build the stub from `../led-ticker/tests/stubs` (already on the pytest path):

```python
import pytest

from rgbmatrix import RGBMatrix, RGBMatrixOptions  # from ../led-ticker/tests/stubs


@pytest.fixture
def canvas():
    opts = RGBMatrixOptions()
    opts.cols = 160
    opts.rows = 16
    matrix = RGBMatrix(options=opts)
    return matrix.CreateFrameCanvas()
```

(If core's conftest builds the canvas differently, mirror it exactly so `canvas.width == 160`.)

- [ ] **Step 2: Create `tests/test_import_purity.py`** — copy `led-ticker-pool/tests/test_import_purity.py` verbatim, changing `SRC = ... / "led_ticker_pool"` to `"led_ticker_crypto"`.

- [ ] **Step 3: Create `tests/test_smoke.py`** — copy `led-ticker-pool/tests/test_smoke.py`, replacing `pool` → `crypto` and `pool.monitor` → `crypto.coingecko`:

```python
"""Smoke test: the package registers a `crypto` plugin via the ENTRY-POINT channel."""

from led_ticker import _plugin_loader as L


def test_entry_point_registers_crypto_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "crypto" in loaded, f"crypto plugin not discovered via entry point: {result}"

        from led_ticker.widgets import get_widget_class

        assert get_widget_class("crypto.coingecko") is not None
    finally:
        L.reset_plugins()
```

- [ ] **Step 4: Create `tests/test_coingecko.py`** — port the coingecko + renderer + helper tests from core's `tests/test_widgets/test_crypto.py`, rewired to the plugin modules:

```python
"""Tests for led_ticker_crypto (coingecko widget + shared renderer)."""

import unittest.mock as mock

import pytest

from led_ticker.plugin import Widget

from led_ticker_crypto._colors import (
    DOWN_TREND_COLOR,
    NEUTRAL_TREND_COLOR,
    UP_TREND_COLOR,
)
from led_ticker_crypto._ticker_render import (
    FONT_VALUE,
    FONT_VALUE_SMALL,
    _get_change_color,
    _get_price_font,
    draw_price_ticker,
)
from led_ticker_crypto.coingecko import (
    CoinGeckoPriceMonitor,
    _find_coingecko_symbol_id,
)


class TestRenderHelpers:
    def test_change_color_positive(self):
        assert _get_change_color("2.55%") == UP_TREND_COLOR

    def test_change_color_negative(self):
        assert _get_change_color("-1.23%") == DOWN_TREND_COLOR

    def test_change_color_zero_is_neutral(self):
        assert _get_change_color("0.00%") == NEUTRAL_TREND_COLOR
        assert _get_change_color("0%") == NEUTRAL_TREND_COLOR

    def test_change_color_unparseable_is_neutral(self):
        assert _get_change_color("N/A") == NEUTRAL_TREND_COLOR
        assert _get_change_color("") == NEUTRAL_TREND_COLOR

    def test_price_font_short(self):
        assert _get_price_font("1234.5678") == FONT_VALUE

    def test_price_font_long(self):
        assert _get_price_font("12345678.90") == FONT_VALUE_SMALL


class TestDrawPriceTicker:
    def test_returns_canvas(self, canvas):
        result, pos = draw_price_ticker(canvas, "BTC", "50000.00", "2.55%")
        assert result is canvas
        assert pos > 0

    def test_centered_fills_canvas(self, canvas):
        _, pos = draw_price_ticker(canvas, "BTC", "50000.00", "2.55%", center=True)
        assert pos == 160


class TestCoinGeckoPriceMonitor:
    @pytest.fixture
    def monitor(self):
        m = CoinGeckoPriceMonitor(
            symbol="ETH", symbol_id="ethereum", currency="USD", session=mock.Mock()
        )
        m.price_data = {"price": "3,000.0000", "change_24h": "1.50%"}
        return m

    def test_conforms_to_widget_protocol(self, monitor):
        assert isinstance(monitor, Widget)

    def test_draw_returns_canvas(self, canvas, monitor):
        result, pos = monitor.draw(canvas)
        assert result is canvas
        assert pos > 0

    def test_find_symbol_id(self):
        coin_list = [
            {"id": "ethereum", "symbol": "eth"},
            {"id": "dogecoin", "symbol": "doge"},
        ]
        assert _find_coingecko_symbol_id(coin_list, "ETH") == "ethereum"
        assert _find_coingecko_symbol_id(coin_list, "BTC") is None

    def test_bg_color_default_is_none(self):
        w = CoinGeckoPriceMonitor(
            symbol="ETH", symbol_id="ethereum", currency="USD", session=mock.Mock()
        )
        assert w.bg_color is None

    def test_accepts_bg_color(self):
        from led_ticker.plugin import make_color

        w = CoinGeckoPriceMonitor(
            symbol="ETH",
            symbol_id="ethereum",
            currency="USD",
            session=mock.Mock(),
            bg_color=make_color(10, 20, 30),
        )
        assert w.bg_color is not None

    async def test_update_parses_price(self):
        session = mock.Mock()
        resp = mock.AsyncMock()
        resp.json = mock.AsyncMock(
            return_value={"ethereum": {"usd": 3000.5, "usd_24h_change": 1.5}}
        )
        ctx = mock.AsyncMock()
        ctx.__aenter__ = mock.AsyncMock(return_value=resp)
        ctx.__aexit__ = mock.AsyncMock(return_value=False)
        session.get = mock.Mock(return_value=ctx)

        w = CoinGeckoPriceMonitor(
            symbol="ETH", symbol_id="ethereum", currency="USD", session=session
        )
        await w.update()
        assert w.price_data["price"] == "3,000.5000"
        assert w.price_data["change_24h"] == "1.50%"
```

(If core's `test_crypto.py` coingecko cases assert other specifics, fold those in too — the goal is to cover at least what core covered for coingecko plus an `update()` parse test.)

- [ ] **Step 5: Run the suite + lint.** `uv run pytest -q` and `uv run ruff check src tests`. Expected: all pass, lint clean. **If `compute_cursor` import fails, Phase 0 isn't merged yet** — check out `feat/public-compute-cursor` in `../led-ticker` to unblock locally.

- [ ] **Step 6: Commit.** `git add -A && git commit --no-verify -m "test: coingecko suite + import-purity + smoke tripwires\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"`

### Task 6: Prove pixel-identical to core, then docs + PR

**Files:** Create `tools/compare_render.py`; create `README.md`, `CLAUDE.md`.

- [ ] **Step 1: Write `tools/compare_render.py`** — render the SAME inputs through core's `CoinbasePriceMonitor._draw_price_ticker` path (via core `widgets.crypto.coingecko.CoinGeckoPriceMonitor.draw`) and the plugin's `draw_price_ticker`, capturing the stub canvas's SetPixel calls, and assert SHA-256 equality. Concretely: import core `CoinGeckoPriceMonitor` from `../led-ticker` checkout (pre-removal) and plugin `CoinGeckoPriceMonitor`; for several fixtures (`("BTC","50000.0000","2.55%")`, `("ETH","3,000.0000","-1.50%")`, `("DOGE","0.1234","0.00%")`, a long price `("BTC","12345678.90","1.00%")`), render both to fresh 160×16 stub canvases at `center=True` and `center=False`, hash the ordered list of `(x,y,r,g,b)` SetPixel tuples the stub recorded, and assert the hashes match per fixture.

- [ ] **Step 2: Run it.** `uv run python tools/compare_render.py`. Expected: prints `MATCH` for every fixture (or a clear diff). Any mismatch means an adaptation error — fix `_ticker_render.py` before proceeding. (This is the spec's pixel-identity gate.)

- [ ] **Step 3: Write `README.md`** — adapt `led-ticker-pool/README.md`'s shape: overview (CoinGecko price ticker), install (entry-point auto-register; container + standalone), the `crypto.coingecko` option table (`symbol`, `symbol_id`, `currency`, `center`, `padding`, `hold_time`, `bg_color`, `font_color`, `update_interval`), a config example (`type = "crypto.coingecko"`, `symbol_id = "bitcoin"`), and a Development section (sibling led-ticker checkout, not on PyPI).

- [ ] **Step 4: Write `CLAUDE.md`** — mirror the led-ticker-pool/baseball CLAUDE.md altitude: overview, commands (`uv run pytest -q`, `uv run ruff check src tests`, sibling-checkout note), file map (`__init__.py`, `coingecko.py`, `_ticker_render.py`, `_colors.py`), and the load-bearing invariants: import-only `led_ticker.plugin` (AST tripwire), PEP 649 (no `__future__` annotations), the `_ticker_render` `draw_text`-adaptation note + the yellow `(255,255,0)` default, the lazy `_colors` palette, register as `crypto.<name>`, test/CI map.

- [ ] **Step 5: Commit + push + PR (do NOT merge).**

```bash
git add -A && git commit --no-verify -m "docs: README + CLAUDE.md + pixel-identity render-compare tool

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git push --no-verify -u origin main   # first push of the new repo
```

Then open a PR only if the repo uses a PR flow for its first commit; otherwise the initial `main` push is the deliverable. **Report to the user; the plugin's CI needs Phase 0 merged to go green.** Wait for go-ahead before any merge.

---

## Phase 2 — Remove crypto from core

Work in a worktree off `led-ticker` main: `git worktree add -b chore/remove-crypto-widgets ../lt-remove-crypto main`. **Open this PR only after Phase 1's plugin is validated pixel-identical** (so `crypto.coingecko` exists as the replacement before the core widget disappears).

### Task 7: Delete the crypto package + tests; add migration error

**Files:** Delete `src/led_ticker/widgets/crypto/`; modify `src/led_ticker/widgets/__init__.py`, `src/led_ticker/app/factories.py`; delete the three crypto test files; create `tests/test_widgets/test_crypto_migration.py`.

- [ ] **Step 1: Write the failing migration test.** Create `tests/test_widgets/test_crypto_migration.py`:

```python
"""Old crypto widget types now live in the led-ticker-crypto plugin."""

import pytest

from led_ticker.app.factories import build_widget_cfg_error_for_type  # see Step 4


@pytest.mark.parametrize("old_type", ["coingecko", "coinbase", "etherscan"])
def test_removed_crypto_types_point_at_plugin(old_type):
    msg = build_widget_cfg_error_for_type(old_type)
    assert msg is not None
    assert "led-ticker-crypto" in msg
    assert "crypto.coingecko" in msg


def test_unrelated_unknown_type_has_no_crypto_hint():
    assert build_widget_cfg_error_for_type("definitely_not_a_widget") is None
```

- [ ] **Step 2: Run it, expect FAIL** (`build_widget_cfg_error_for_type` doesn't exist). `cd ../lt-remove-crypto && uv run pytest tests/test_widgets/test_crypto_migration.py -q`.

- [ ] **Step 3: Delete the crypto code + tests.**

```bash
cd /Users/james/projects/github/jamesawesome/lt-remove-crypto
git rm -r src/led_ticker/widgets/crypto
git rm tests/test_widgets/test_crypto.py tests/test_widgets/test_crypto_colors.py tests/test_widgets/test_etherscan.py
```

Then remove the crypto import line in `src/led_ticker/widgets/__init__.py` (`from led_ticker.widgets.crypto import coinbase, coingecko, etherscan  # noqa: E402, F401`).

- [ ] **Step 4: Add the migration helper + wire it.** In `src/led_ticker/app/factories.py`: (a) remove the `# --- Coinbase / CoinGecko ---` `FieldHint` block (the `symbol_id` hint and any sibling crypto-only hints at ~lines 210-218); (b) add a small mapping + helper and call it where an unknown widget type currently raises:

```python
_REMOVED_CRYPTO_TYPES = {"coingecko", "coinbase", "etherscan"}


def build_widget_cfg_error_for_type(widget_type: str) -> str | None:
    """Helpful message for widget types that moved out of core, else None."""
    if widget_type in _REMOVED_CRYPTO_TYPES:
        return (
            f"Widget type {widget_type!r} was removed from led-ticker core. "
            "CoinGecko now ships in the led-ticker-crypto plugin as "
            "'crypto.coingecko' — install led-ticker-crypto and use "
            "type = \"crypto.coingecko\". (coinbase/etherscan were retired.)"
        )
    return None
```

In `_build_widget` (or wherever `get_widget_class` returns None / raises "unknown widget"), call `build_widget_cfg_error_for_type(widget_type)` first and raise a `MigrationError`/`ValueError` with that message when non-None. Follow the existing MigrationError pattern in factories.py (the title `color`→`font_color` one).

- [ ] **Step 5: Run the migration test + full suite.** `uv run pytest tests/test_widgets/test_crypto_migration.py -q` (PASS), then `make test`. Expected: green, no dangling crypto imports.

- [ ] **Step 6: Commit.** `git add -A && git commit --no-verify -m "refactor(plugin): remove crypto widgets from core; migration error to led-ticker-crypto\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"`

### Task 8: Prune orphaned font constants (conditional)

**Files:** `src/led_ticker/fonts/__init__.py`.

- [ ] **Step 1: Check usage.** `grep -rn "FONT_LABEL\|FONT_DELTA\|FONT_VALUE\b\|FONT_VALUE_SMALL" src/ tests/` (after Task 7). Expected: zero non-test hits (crypto was the only consumer).

- [ ] **Step 2: Prune IF unused.** For each of `FONT_LABEL`, `FONT_DELTA`, `FONT_VALUE`, `FONT_VALUE_SMALL` with no remaining consumer, delete its definition line in `src/led_ticker/fonts/__init__.py`. KEEP the `"7x13"`/`"6x10"` entries in the resolve-by-name registry (the plugin resolves them). If any constant still has a consumer, LEAVE it (cheap to keep — same judgment as the `lazy_palette`/`GEOMETRIC_SHAPES` retention).

- [ ] **Step 3: Run suite.** `make test`. Expected: green.

- [ ] **Step 4: Commit.** `git add -A && git commit --no-verify -m "chore(fonts): drop crypto-only named font constants (registry entries retained)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"`

### Task 9: Docs, demos, skill fact-packs, CLAUDE.md, example configs

**Files:** as listed in the Phase-2 file map.

- [ ] **Step 1: Delete docs + demos.** `git rm docs/content-source/widgets/coinbase.md docs/content-source/widgets/coingecko.md docs/content-source/widgets/etherscan.md docs/site/demos-long/widget-coinbase.toml docs/site/demos-long/widget-coingecko.toml docs/site/demos-long/widget-etherscan.toml`. Also check `docs/site/src/content/docs/widgets/` for built coinbase/coingecko/etherscan pages and remove those + any sidebar/nav references (grep the docs-site config for the three names).

- [ ] **Step 2: Scrub skill fact-packs.** Edit `.claude/skills/creating-a-config/SKILL.md` (the `coinbase`→`personal_feed` inference line), `references/widget-selection.md` (the coinbase/coingecko/etherscan entries), `references/snippets.md` (the two `coinbase.personal_feed.*` snippets), `references/asset-handling.md` (the `[coinbase]` table row). Remove the three widgets; where the pack lists available widgets, leave a one-line note that crypto is now the external `led-ticker-crypto` plugin if the pack documents plugins, else just delete.

- [ ] **Step 3: Update `CLAUDE.md`.** Remove the `crypto/ # coinbase, coingecko, etherscan` package-layout line. In the **Plugin ecosystem** subsection add: `- [led-ticker-crypto](...) — crypto.coingecko (CoinGecko price ticker)`.

- [ ] **Step 4: Scrub example configs.** Remove any `[[...]]` crypto sections (`type = "coinbase"|"coingecko"|"etherscan"`) from `config/config.example.toml` and `config/config.bigsign.example.toml`. `grep -n "coinbase\|coingecko\|etherscan" config/*.toml` → expect zero after.

- [ ] **Step 5: Final sweep.** `grep -rn "coinbase\|coingecko\|etherscan" src/ tests/ docs/ config/ .claude/ CLAUDE.md` → the only remaining hits should be the intentional migration-error text and the Plugin-ecosystem link. Run the docs-config drift test if present: `uv run pytest tests/test_docs_config_options_drift.py -q`. Run `make test` + `uv run --extra dev ruff check src/ tests/`.

- [ ] **Step 6: Commit + push + PR (do NOT merge).**

```bash
git add -A && git commit --no-verify -m "docs: remove crypto widget docs/demos/skill-refs; CLAUDE.md plugin-ecosystem entry

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git push --no-verify -u origin chore/remove-crypto-widgets
gh pr create --repo JamesAwesome/led-ticker --base main --title "refactor(plugin): remove coinbase/etherscan; extract coingecko to led-ticker-crypto" --body "..."
```

Report all PRs; wait for user go-ahead to merge anything.

---

## Phase 3 — review (separate plan, after this lands)

NOT planned here. Once Phase 2 merges, write a follow-up plan from the spec's Phase-3 section: exercise the live CoinGecko v3 API (demo-key / rate-limit / endpoint drift), fix what's stale, harden the test suite, and bring any enhancement (configurable `vs_currency`, multiple coins, formatting) back for approval before building. Its tasks depend on what the live check finds, so they can't be pre-written.

---

## Self-review notes

- **Spec coverage:** Phase 0 (compute_cursor) ↔ Task 0; Phase 1 plugin ↔ Tasks 1-6 (scaffolding, _colors, _ticker_render, widget, tests, pixel-identity+docs); Phase 2 removal ↔ Tasks 7-9 (delete+migration, font prune, docs/skill/config); migration nicety ↔ Task 7; pixel-identity gate ↔ Task 6; Phase 3 explicitly deferred. All spec sections mapped.
- **Type/name consistency:** the package-internal renderer is `draw_price_ticker` (no leading underscore) everywhere it's referenced (Tasks 3, 4, 5, 6); `_ConstantColor` + `make_default_font_color` defined in `_ticker_render.py` and imported by `coingecko.py`; widget registered as `crypto.coingecko` in `__init__.py`, smoke test, and migration text consistently; `build_widget_cfg_error_for_type` defined (Task 7 Step 4) and consumed by its test (Task 7 Step 1).
- **DEFAULT_COLOR fidelity:** `(255, 255, 0)` (yellow) replicated in `make_default_font_color` and the renderer's None-branch — not white.
