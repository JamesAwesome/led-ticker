# Large #1: Split app.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `src/led_ticker/app.py` (1535 lines, five concerns) into an `app/` package with four focused modules — `coercion.py`, `factories.py`, `run.py`, `cli.py` — while preserving every existing `from led_ticker.app import X` call site via `__init__.py` re-exports.

**Architecture:** Pure code-move refactor in five sequential tasks, each leaving tests green. Task 1 renames the file to a package (pure rename, no logic). Tasks 2–5 extract one concern per task: coercion layer, factory functions, run loop, CLI. `app/__init__.py` re-exports everything external callers use so `validate.py`, all tests, and the `led-ticker` entry point keep working without changes.

**Tech Stack:** Python 3.12, attrs, asyncio, aiohttp, pytest (`asyncio_mode = "auto"`), uv

---

## File Map

| Task | Action | Path | Responsibility |
|------|--------|------|----------------|
| Task 1 | Create | `src/led_ticker/app/__init__.py` | Initially: full copy of app.py |
| Task 1 | Delete | `src/led_ticker/app.py` | Dissolved into package |
| Task 2 | Create | `src/led_ticker/app/coercion.py` | `_validate_rgb`, `_coerce_*`, `_provider_from_style`, provider/widget constants |
| Task 2 | Modify | `src/led_ticker/app/__init__.py` | Import coercion names; delete coercion definitions |
| Task 3 | Create | `src/led_ticker/app/factories.py` | `_build_widget`, `_build_title`, `_build_trans_obj`, `build_frame_from_config`, helpers, `RANDOM_COLOR` |
| Task 3 | Modify | `src/led_ticker/app/__init__.py` | Import factory names; delete factory definitions |
| Task 4 | Create | `src/led_ticker/app/run.py` | `run()` async loop |
| Task 4 | Modify | `src/led_ticker/app/__init__.py` | Import `run`; delete run definition |
| Task 5 | Create | `src/led_ticker/app/cli.py` | `main()`, `_setup_logging()` |
| Task 5 | Modify | `src/led_ticker/app/__init__.py` | Import `main`; slim down to pure re-exports |

### Public surface that must remain accessible via `led_ticker.app`

All tests and `validate.py` use `from led_ticker.app import X`. The entry point `led-ticker = "led_ticker.app:main"` must work. Every name below must live in `app/__init__.py` as a re-export after the refactor:

```
RANDOM_COLOR            _build_title            _build_trans_obj
_build_widget           _cache_key              _coerce_animation
_coerce_border          _coerce_color           _coerce_color_provider
_coerce_widget_cfg      _coerce_widget_colors   _COLOR_KEYS
_configure_user_font_dir _is_hires_font_name    _list_widget_fields
_PROVIDER_COLOR_KEYS    _provider_from_style    _RAW_COLOR_KEYS
_resolve_buffer_msg     _resolve_title_delay    _validate_rgb
_WIDGET_ENUM_FIELDS     _WIDGET_FLOAT_FIELDS    _WIDGET_INT_FIELDS
build_frame_from_config main                    run
RUN_MODES
```

---

## Task 1: Convert app.py → app/__init__.py (pure rename)

**Files:**
- Create: `src/led_ticker/app/__init__.py`
- Delete: `src/led_ticker/app.py`

No logic changes. Python cannot have both `app.py` and `app/` in the same directory, so the rename must be atomic.

- [ ] **Step 1: Record baseline test count**

```bash
cd /path/to/worktree && uv run pytest --tb=short -q 2>&1 | tail -3
```

Record the exact pass count. You'll compare after the rename.

- [ ] **Step 2: Atomic rename**

```bash
# From repo root (adjust path to your worktree):
WORKTREE=.  # or your worktree path
mkdir "$WORKTREE/src/led_ticker/app"
cp "$WORKTREE/src/led_ticker/app.py" "$WORKTREE/src/led_ticker/app/__init__.py"
rm "$WORKTREE/src/led_ticker/app.py"
```

Verify:
```bash
ls src/led_ticker/app/
# Expected output: __init__.py
ls src/led_ticker/ | grep app
# Expected output: app/   (directory, no app.py file)
head -5 src/led_ticker/app/__init__.py
# Expected: """CLI entry point for led-ticker."""
```

- [ ] **Step 3: Verify tests pass with same count**

```bash
uv run pytest --tb=short -q 2>&1 | tail -3
```

Expected: same count as Step 1 baseline. If any test fails, check that `app/__init__.py` is byte-for-byte identical to the original `app.py`.

- [ ] **Step 4: Verify CLI entry point still works**

```bash
uv run led-ticker --help
```

Expected: shows usage with `validate` subcommand. No traceback.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/app/__init__.py
git rm src/led_ticker/app.py
git commit -m "refactor: convert app.py to app/ package skeleton (no logic changes)"
```

---

## Task 2: Extract coercion layer → app/coercion.py

**Files:**
- Create: `src/led_ticker/app/coercion.py`
- Modify: `src/led_ticker/app/__init__.py`

**What moves to `coercion.py`** (all copied verbatim from `__init__.py`):
- Constants at lines 76–102: `_COLOR_KEYS`, `_PROVIDER_COLOR_KEYS`, `_RAW_COLOR_KEYS`
- `_coerce_color_provider` (lines 105–161)
- `_validate_rgb` (lines 164–177)
- `_rgb_to_hue` (lines 180–198)
- `_provider_from_style` (lines 201–296)
- `_coerce_color` (lines 299–303)
- `_coerce_border` (lines 306–443)
- `_coerce_animation` (lines 446–493)
- `_coerce_widget_colors` (lines 496–518)
- `_is_hires_font_name` (lines 521–528)
- Constants at lines 531–573: `_WIDGET_INT_FIELDS`, `_WIDGET_FLOAT_FIELDS`, `_WIDGET_ENUM_FIELDS`
- `_coerce_widget_cfg` (lines 576–604)

`coercion.py` depends only on: `led_ticker._compat`, `led_ticker.color_providers`, `led_ticker.borders`, `led_ticker.animations`, `led_ticker.fonts`, `led_ticker._coerce`, `led_ticker.widgets._image_base`, `led_ticker.widgets._image_fit`. All internal imports stay deferred (inside function bodies) exactly as they are in `__init__.py` today.

- [ ] **Step 1: Write the smoke test (it will fail — ImportError)**

Create `tests/test_app_coercion_module.py`:

```python
"""Smoke test: coercion submodule is importable at its own path."""


def test_coercion_submodule_importable():
    from led_ticker.app.coercion import (
        _COLOR_KEYS,
        _PROVIDER_COLOR_KEYS,
        _RAW_COLOR_KEYS,
        _WIDGET_ENUM_FIELDS,
        _WIDGET_FLOAT_FIELDS,
        _WIDGET_INT_FIELDS,
        _coerce_animation,
        _coerce_border,
        _coerce_color,
        _coerce_color_provider,
        _coerce_widget_cfg,
        _coerce_widget_colors,
        _is_hires_font_name,
        _provider_from_style,
        _validate_rgb,
    )
    assert callable(_coerce_color_provider)
    assert callable(_validate_rgb)
    assert isinstance(_COLOR_KEYS, set)
    assert isinstance(_WIDGET_INT_FIELDS, frozenset)


def test_coercion_names_still_on_app_module():
    """All coercion names remain importable from led_ticker.app (backwards compat)."""
    from led_ticker.app import (
        _COLOR_KEYS,
        _PROVIDER_COLOR_KEYS,
        _coerce_border,
        _coerce_color_provider,
        _coerce_widget_colors,
        _provider_from_style,
        _validate_rgb,
    )
    assert callable(_coerce_color_provider)
    assert isinstance(_COLOR_KEYS, set)
```

Run:
```bash
uv run pytest tests/test_app_coercion_module.py -v
```
Expected: `test_coercion_submodule_importable` FAILS with `ModuleNotFoundError`. `test_coercion_names_still_on_app_module` PASSES (they're still in `__init__.py`).

- [ ] **Step 2: Create `src/led_ticker/app/coercion.py`**

Create the file with this exact header, then copy the function bodies verbatim from `app/__init__.py` using the line ranges listed in the task description above. The function bodies are UNCHANGED — do not edit them.

```python
"""TOML → led-ticker object coercion layer.

Converts raw config values (strings, lists, dicts) to led-ticker objects:
ColorProvider, BorderEffect, Animation, Font. No dependencies on the
widget/ticker engine — only on provider registries and the _coerce helpers.
"""

from __future__ import annotations

from typing import Any

from led_ticker.widgets._image_base import (
    VALID_SCROLL_DIRECTIONS,
    VALID_TEXT_ALIGNS,
    VALID_TEXT_VALIGNS,
)
from led_ticker.widgets._image_fit import VALID_FITS, VALID_IMAGE_ALIGNS

# --- Constants (copy verbatim from app/__init__.py lines 76-102) ---

_COLOR_KEYS: set[str] = { ... }         # copy lines 76-84
_PROVIDER_COLOR_KEYS: set[str] = { ... }  # copy lines 89-96
_RAW_COLOR_KEYS: set[str] = ...          # copy line 102

_WIDGET_INT_FIELDS = frozenset({ ... })  # copy lines 535-554
_WIDGET_FLOAT_FIELDS = frozenset({ ... }) # copy lines 556-560
_WIDGET_ENUM_FIELDS: dict[str, frozenset[str]] = { ... }  # copy lines 566-573


# --- Functions (copy verbatim from app/__init__.py) ---

def _coerce_color_provider(value: Any, context: str = "font_color") -> Any:
    # copy lines 105-161 verbatim
    ...

def _validate_rgb(rgb: Any, context: str) -> tuple[int, int, int]:
    # copy lines 164-177 verbatim
    ...

def _rgb_to_hue(rgb: list[int] | tuple[int, ...], context: str) -> float:
    # copy lines 180-198 verbatim
    ...

def _provider_from_style(style: str, kwargs: dict[str, Any]) -> Any:
    # copy lines 201-296 verbatim
    ...

def _coerce_color(value: Any) -> Any:
    # copy lines 299-303 verbatim
    ...

def _coerce_border(value: Any) -> Any:
    # copy lines 306-443 verbatim
    ...

def _coerce_animation(value: Any) -> Any:
    # copy lines 446-493 verbatim
    ...

def _coerce_widget_colors(cfg: dict[str, Any]) -> None:
    # copy lines 496-518 verbatim
    ...

def _is_hires_font_name(name: str) -> bool:
    # copy lines 521-528 verbatim
    ...

def _coerce_widget_cfg(
    widget_cfg: dict[str, Any],
    collector: list[Any] | None,
) -> None:
    # copy lines 576-604 verbatim
    ...
```

> **Implementation note:** The `{ ... }` and `# copy lines X-Y verbatim` markers above are scaffolding — replace each with the actual content from `app/__init__.py` at those line numbers. Every function body is identical to what's in `__init__.py` today; nothing is rewritten.

- [ ] **Step 3: Run smoke test — verify it passes**

```bash
uv run pytest tests/test_app_coercion_module.py -v
```
Expected: both tests PASS.

- [ ] **Step 4: Update `app/__init__.py` — import from coercion, delete the definitions**

At the top of `app/__init__.py`, after the existing `from __future__ import annotations` line, add:

```python
from led_ticker.app.coercion import (
    _COLOR_KEYS,
    _PROVIDER_COLOR_KEYS,
    _RAW_COLOR_KEYS,
    _WIDGET_ENUM_FIELDS,
    _WIDGET_FLOAT_FIELDS,
    _WIDGET_INT_FIELDS,
    _coerce_animation,
    _coerce_border,
    _coerce_color,
    _coerce_color_provider,
    _coerce_widget_cfg,
    _coerce_widget_colors,
    _is_hires_font_name,
    _provider_from_style,
    _validate_rgb,
)
```

Then delete these sections from `__init__.py`:
- Lines 76–102 (the three constant sets)
- Lines 105–604 (all ten coercion functions + `_WIDGET_*` constants)

Also remove these imports from `__init__.py`'s own import block (they're no longer used in `__init__.py`; `coercion.py` will import them itself):
```python
from led_ticker.widgets._image_base import (
    VALID_SCROLL_DIRECTIONS,
    VALID_TEXT_ALIGNS,
    VALID_TEXT_VALIGNS,
)
from led_ticker.widgets._image_fit import VALID_FITS, VALID_IMAGE_ALIGNS
```

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest --tb=short -q
```
Expected: same count as Task 1 baseline, all pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app/coercion.py src/led_ticker/app/__init__.py tests/test_app_coercion_module.py
git commit -m "refactor: extract coercion layer into app/coercion.py"
```

---

## Task 3: Extract factory functions → app/factories.py

**Files:**
- Create: `src/led_ticker/app/factories.py`
- Modify: `src/led_ticker/app/__init__.py`

**What moves to `factories.py`** (verbatim from `__init__.py` after Task 2):
- `RANDOM_COLOR` module-level cycle (lines 44–56 of original `app.py`)
- `_cache_key` (line 71–73)
- `_build_trans_obj` (lines 607–629)
- `_build_widget` (lines 632–940) — async, 308 lines
- `_build_title` (lines 943–991) — async
- `_resolve_title_delay` (lines 994–1001)
- `_resolve_buffer_msg` (lines 1004–1056)
- `RUN_MODES` dict (lines 1059–1064)
- `build_frame_from_config` (lines 1067–1114)
- `_configure_user_font_dir` (lines 1117–1137)
- `_list_widget_fields` (lines 1360–1436)

`factories.py` imports from `coercion.py` (same package) plus `config`, `frame`, `ticker`, `transitions`, `widgets`, `colors`. The deferred `from led_ticker.validate import MigrationError` inside `_build_widget` stays deferred to avoid the circular import (`validate.py` imports `_build_widget` at function-call time).

- [ ] **Step 1: Write the smoke test (it will fail — ImportError)**

Create `tests/test_app_factories_module.py`:

```python
"""Smoke test: factories submodule importable and public names accessible."""


def test_factories_submodule_importable():
    from led_ticker.app.factories import (
        RANDOM_COLOR,
        RUN_MODES,
        _build_title,
        _build_trans_obj,
        _build_widget,
        _cache_key,
        _configure_user_font_dir,
        _list_widget_fields,
        _resolve_buffer_msg,
        _resolve_title_delay,
        build_frame_from_config,
    )
    import itertools

    assert isinstance(RANDOM_COLOR, itertools.cycle)
    assert callable(_build_widget)
    assert callable(build_frame_from_config)
    assert isinstance(RUN_MODES, dict)


def test_factory_names_still_on_app_module():
    """Backwards-compat: factory names remain importable from led_ticker.app."""
    from led_ticker.app import (
        RANDOM_COLOR,
        _build_title,
        _build_trans_obj,
        _build_widget,
        build_frame_from_config,
    )
    assert callable(_build_widget)
    assert callable(build_frame_from_config)
```

Run:
```bash
uv run pytest tests/test_app_factories_module.py -v
```
Expected: `test_factories_submodule_importable` FAILS with `ModuleNotFoundError`. `test_factory_names_still_on_app_module` PASSES.

- [ ] **Step 2: Create `src/led_ticker/app/factories.py`**

```python
"""Widget, transition, and frame factory functions.

Converts resolved config objects into live led-ticker instances.
All coercion of raw TOML values happens in coercion.py before these
functions are called.
"""

from __future__ import annotations

import difflib
import inspect
import itertools
import logging
from pathlib import Path
from typing import Any

import aiohttp

from led_ticker.colors import (
    BLUE, CYAN, GREEN, ORANGE, PINK, PURPLE, RED, RGB_WHITE, YELLOW,
)
from led_ticker.config import SectionConfig, TransitionConfig
from led_ticker.frame import LedFrame
from led_ticker.ticker import Ticker, _maybe_wrap
from led_ticker.transitions import get_transition_class
from led_ticker.widgets import get_widget_class
from led_ticker.widgets.message import TickerMessage
from led_ticker.widgets.mlb import MLBScoreMonitor
from led_ticker.widgets.mlb_standings import MLBStandingsMonitor
from led_ticker.widgets.rss_feed import RSSFeedMonitor

from led_ticker.app.coercion import (
    _coerce_animation,
    _coerce_border,
    _coerce_widget_cfg,
    _coerce_widget_colors,
    _is_hires_font_name,
    _coerce_color_provider,
)

# Section-title random color cycle. One stable color per section visit.
# Module-level mutable singleton — lives here, next to _build_title which
# is its only consumer. Exported via app/__init__.py so existing
# `app.RANDOM_COLOR` references still work.
RANDOM_COLOR: itertools.cycle = itertools.cycle(
    [RED, GREEN, BLUE, YELLOW, ORANGE, PURPLE, CYAN, PINK]
)

RUN_MODES: dict[str, str] = {
    "forever_scroll": "run_forever_scroll",
    "infini_scroll": "run_infini_scroll",
    "swap": "run_swap",
    "gif": "run_gif",
}


def _cache_key(widget_cfg: dict[str, Any]) -> str:
    # copy body from app/__init__.py lines 71-73 verbatim
    ...


def _build_trans_obj(trans_cfg: TransitionConfig) -> Any:
    # copy body from app/__init__.py lines 607-629 verbatim
    ...


async def _build_widget(
    widget_cfg: dict[str, Any],
    session: aiohttp.ClientSession,
    config_dir: Path | None = None,
    default_bg_color: tuple[int, int, int] | None = None,
    panel_h_for_warning: int | None = None,
    validate_only: bool = False,
    coercion_collector: list[Any] | None = None,
) -> Any:
    # copy body from app/__init__.py lines 632-940 verbatim
    # The deferred `from led_ticker.validate import MigrationError` inside
    # the body MUST remain deferred — validate.py imports _build_widget at
    # call time to avoid a circular import.
    ...


async def _build_title(
    title_cfg: dict[str, Any] | None,
    *,
    session: aiohttp.ClientSession,
    config_dir: Path | None = None,
    default_bg_color: tuple[int, int, int] | None = None,
    panel_h_for_warning: int | None = None,
) -> TickerMessage | None:
    # copy body from app/__init__.py lines 943-991 verbatim
    ...


def _resolve_title_delay(section_start_hold: float | None, global_delay: int) -> float:
    # copy body from app/__init__.py lines 994-1001 verbatim
    ...


def _resolve_buffer_msg(section: SectionConfig) -> TickerMessage | None:
    # copy body from app/__init__.py lines 1004-1056 verbatim
    ...


def build_frame_from_config(display: Any) -> LedFrame:
    # copy body from app/__init__.py lines 1067-1114 verbatim
    ...


def _configure_user_font_dir(config_path: Path) -> None:
    # copy body from app/__init__.py lines 1117-1137 verbatim
    ...


def _list_widget_fields(widget_type: str) -> str:
    # copy body from app/__init__.py lines 1360-1436 verbatim
    ...
```

> **Implementation note:** Replace each `# copy body from ... verbatim` comment with the actual function body pasted from `app/__init__.py` at the stated line range. Signatures and docstrings are unchanged.

- [ ] **Step 3: Run smoke test — verify it passes**

```bash
uv run pytest tests/test_app_factories_module.py -v
```
Expected: both tests PASS.

- [ ] **Step 4: Update `app/__init__.py` — import from factories, delete definitions**

Add to `app/__init__.py` imports:

```python
from led_ticker.app.factories import (
    RANDOM_COLOR,
    RUN_MODES,
    _build_title,
    _build_trans_obj,
    _build_widget,
    _cache_key,
    _configure_user_font_dir,
    _list_widget_fields,
    _resolve_buffer_msg,
    _resolve_title_delay,
    build_frame_from_config,
)
```

Then delete from `__init__.py`:
- The `RANDOM_COLOR` definition (the `itertools.cycle(...)` line + comment block, originally lines 44–56)
- `_cache_key` function definition
- `_build_trans_obj` function definition
- `_build_widget` function definition
- `_build_title` function definition
- `_resolve_title_delay` function definition
- `_resolve_buffer_msg` function definition
- `RUN_MODES` dict definition
- `build_frame_from_config` function definition
- `_configure_user_font_dir` function definition
- `_list_widget_fields` function definition

Also remove these imports that are no longer used in `__init__.py` directly (they're now in `factories.py`):
```python
# Remove these from __init__.py's import block:
import difflib
import inspect
import itertools
import aiohttp
from led_ticker.colors import (BLUE, CYAN, GREEN, ORANGE, PINK, PURPLE, RED, RGB_WHITE, YELLOW)
from led_ticker.config import SectionConfig, TransitionConfig, load_config
from led_ticker.frame import LedFrame
from led_ticker.ticker import Ticker, _maybe_wrap
from led_ticker.transitions import get_transition_class, run_transition
from led_ticker.widgets import get_widget_class
from led_ticker.widgets.message import TickerMessage
from led_ticker.widgets.mlb import MLBScoreMonitor
from led_ticker.widgets.mlb_standings import MLBStandingsMonitor
from led_ticker.widgets.rss_feed import RSSFeedMonitor
```

> Keep `load_config` and anything still needed by `run()` in `__init__.py` until Task 4 moves `run()` out.

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest --tb=short -q
```
Expected: same count as baseline, all pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app/factories.py src/led_ticker/app/__init__.py tests/test_app_factories_module.py
git commit -m "refactor: extract factory functions into app/factories.py"
```

---

## Task 4: Extract run loop → app/run.py

**Files:**
- Create: `src/led_ticker/app/run.py`
- Modify: `src/led_ticker/app/__init__.py`

**What moves to `run.py`:**
- `run()` async function (original lines 1140–1358)

`run.py` calls `_build_widget`, `_build_title`, `_build_trans_obj`, `build_frame_from_config`, `_configure_user_font_dir`, `_cache_key`, `_resolve_buffer_msg`, `_resolve_title_delay`, `RANDOM_COLOR`, `RUN_MODES` — all imported from `factories.py`. It also uses `run_transition` from `transitions` and `Ticker`, `_maybe_wrap` from `ticker`.

- [ ] **Step 1: Write the smoke test (it will fail — ImportError)**

Create `tests/test_app_run_module.py`:

```python
"""Smoke test: run submodule importable."""


def test_run_submodule_importable():
    from led_ticker.app.run import run
    import inspect
    assert inspect.iscoroutinefunction(run)


def test_run_still_on_app_module():
    from led_ticker.app import run
    import inspect
    assert inspect.iscoroutinefunction(run)
```

Run:
```bash
uv run pytest tests/test_app_run_module.py -v
```
Expected: `test_run_submodule_importable` FAILS. `test_run_still_on_app_module` PASSES.

- [ ] **Step 2: Create `src/led_ticker/app/run.py`**

```python
"""Main application async loop.

Loads config, builds the LED frame, and iterates over playlist sections
indefinitely. Widget construction and coercion happen in factories.py;
the run loop here only orchestrates.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiohttp

from led_ticker.config import load_config
from led_ticker.ticker import _maybe_wrap
from led_ticker.transitions import run_transition
from led_ticker.widgets.mlb import MLBScoreMonitor
from led_ticker.widgets.mlb_standings import MLBStandingsMonitor
from led_ticker.widgets.rss_feed import RSSFeedMonitor

from led_ticker.app.factories import (
    RUN_MODES,
    _build_title,
    _build_trans_obj,
    _build_widget,
    _cache_key,
    _configure_user_font_dir,
    _resolve_buffer_msg,
    _resolve_title_delay,
    build_frame_from_config,
)


async def run(config_path: Path) -> None:
    # copy body from app/__init__.py lines 1140-1358 verbatim
    ...
```

> Replace `# copy body ... verbatim` with the actual function body from `app/__init__.py` lines 1140–1358.

- [ ] **Step 3: Run smoke test — verify it passes**

```bash
uv run pytest tests/test_app_run_module.py -v
```
Expected: both tests PASS.

- [ ] **Step 4: Update `app/__init__.py`**

Add import:
```python
from led_ticker.app.run import run
```

Delete `run()` function definition from `__init__.py`.

Remove any imports that were only used by `run()` and are now unused in `__init__.py` (e.g. `load_config`, `run_transition`, `_maybe_wrap`, widget container imports).

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest --tb=short -q
```
Expected: same count as baseline, all pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app/run.py src/led_ticker/app/__init__.py tests/test_app_run_module.py
git commit -m "refactor: extract run() async loop into app/run.py"
```

---

## Task 5: Extract CLI → app/cli.py, slim __init__.py to pure re-exports

**Files:**
- Create: `src/led_ticker/app/cli.py`
- Modify: `src/led_ticker/app/__init__.py`

**What moves to `cli.py`:**
- `_setup_logging()` (lines 59–68)
- `main()` (lines 1439–1535)

After this task, `app/__init__.py` becomes a pure re-export hub — no function bodies, only imports.

- [ ] **Step 1: Write the smoke test (it will fail — ImportError)**

Create `tests/test_app_cli_module.py`:

```python
"""Smoke test: cli submodule importable; main accessible from app."""


def test_cli_submodule_importable():
    from led_ticker.app.cli import main, _setup_logging
    assert callable(main)
    assert callable(_setup_logging)


def test_main_still_on_app_module():
    """Entry point led_ticker.app:main must remain accessible."""
    from led_ticker.app import main
    assert callable(main)
```

Run:
```bash
uv run pytest tests/test_app_cli_module.py -v
```
Expected: `test_cli_submodule_importable` FAILS. `test_main_still_on_app_module` PASSES.

- [ ] **Step 2: Create `src/led_ticker/app/cli.py`**

```python
"""CLI entry point for led-ticker.

Parses argv, dispatches to `validate` subcommand or the main run loop.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from led_ticker.app.run import run
from led_ticker.app.factories import _list_widget_fields


def _setup_logging() -> None:
    # copy body from app/__init__.py lines 59-68 verbatim
    ...


def main() -> None:
    # copy body from app/__init__.py lines 1439-1535 verbatim
    # The deferred `from led_ticker.validate import ...` inside main()
    # MUST stay deferred — it avoids a top-level circular import.
    ...
```

> Replace the `# copy body` comments with the actual function bodies from `app/__init__.py`.

- [ ] **Step 3: Run smoke test — verify it passes**

```bash
uv run pytest tests/test_app_cli_module.py -v
```
Expected: both tests PASS.

- [ ] **Step 4: Update `app/__init__.py` — import from cli, slim to pure re-exports**

Add import:
```python
from led_ticker.app.cli import _setup_logging, main
```

Delete `_setup_logging()` and `main()` definitions from `__init__.py`.

At this point `app/__init__.py` should have ONLY imports and re-exports — no function definitions. It should look like:

```python
"""led_ticker.app — application package.

This package replaces the former app.py module. All names remain
importable from this namespace for backwards compatibility.
"""

from __future__ import annotations

# Coercion layer
from led_ticker.app.coercion import (
    _COLOR_KEYS,
    _PROVIDER_COLOR_KEYS,
    _RAW_COLOR_KEYS,
    _WIDGET_ENUM_FIELDS,
    _WIDGET_FLOAT_FIELDS,
    _WIDGET_INT_FIELDS,
    _coerce_animation,
    _coerce_border,
    _coerce_color,
    _coerce_color_provider,
    _coerce_widget_cfg,
    _coerce_widget_colors,
    _is_hires_font_name,
    _provider_from_style,
    _validate_rgb,
)

# Factory functions
from led_ticker.app.factories import (
    RANDOM_COLOR,
    RUN_MODES,
    _build_title,
    _build_trans_obj,
    _build_widget,
    _cache_key,
    _configure_user_font_dir,
    _list_widget_fields,
    _resolve_buffer_msg,
    _resolve_title_delay,
    build_frame_from_config,
)

# Run loop
from led_ticker.app.run import run

# CLI
from led_ticker.app.cli import _setup_logging, main

__all__ = [
    "RANDOM_COLOR",
    "RUN_MODES",
    "_build_title",
    "_build_trans_obj",
    "_build_widget",
    "_cache_key",
    "_coerce_animation",
    "_coerce_border",
    "_coerce_color",
    "_coerce_color_provider",
    "_coerce_widget_cfg",
    "_coerce_widget_colors",
    "_COLOR_KEYS",
    "_configure_user_font_dir",
    "_is_hires_font_name",
    "_list_widget_fields",
    "_PROVIDER_COLOR_KEYS",
    "_provider_from_style",
    "_RAW_COLOR_KEYS",
    "_resolve_buffer_msg",
    "_resolve_title_delay",
    "_setup_logging",
    "_validate_rgb",
    "_WIDGET_ENUM_FIELDS",
    "_WIDGET_FLOAT_FIELDS",
    "_WIDGET_INT_FIELDS",
    "build_frame_from_config",
    "main",
    "run",
]
```

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest --tb=short -q
```
Expected: same count as Task 1 baseline, all pass.

- [ ] **Step 6: Update the RANDOM_COLOR tripwire test docstring**

`tests/test_app_random_color.py` has the docstring `"""Tripwire: RANDOM_COLOR lives in app.py with the 8-color palette."""`. Update it to reflect the new location:

```python
"""Tripwire: RANDOM_COLOR lives in app/factories.py; re-exported via app/__init__.py."""
```

- [ ] **Step 7: Run tests once more to confirm the updated tripwire test still passes**

```bash
uv run pytest tests/test_app_random_color.py -v
```
Expected: all 3 tests PASS.

- [ ] **Step 8: Verify CLI still works**

```bash
uv run led-ticker --help
uv run led-ticker validate --list-fields message
```
Expected: no error, expected output.

- [ ] **Step 9: Commit**

```bash
git add src/led_ticker/app/cli.py src/led_ticker/app/__init__.py \
        tests/test_app_cli_module.py tests/test_app_random_color.py
git commit -m "refactor: extract CLI into app/cli.py; slim __init__.py to pure re-exports"
```

---

## Self-Review

### Spec Coverage

| Requirement | Task | Status |
|-------------|------|--------|
| Split coercion into `app/coercion.py` | Task 2 | ✅ |
| Split factories into `app/factories.py` | Task 3 | ✅ |
| Split run loop into `app/run.py` | Task 4 | ✅ |
| Split CLI into `app/cli.py` | Task 5 | ✅ |
| `from led_ticker.app import X` still works for all names | `__init__.py` re-exports | ✅ |
| `led-ticker = "led_ticker.app:main"` entry point works | `main` re-exported | ✅ |
| `RANDOM_COLOR` accessible as `app.RANDOM_COLOR` | `RANDOM_COLOR` re-exported | ✅ |
| `validate.py` continues to import `_build_widget`, `_configure_user_font_dir` | `__init__.py` re-exports | ✅ |
| Circular import `validate.py` ↔ `factories.py` avoided | Deferred import stays deferred | ✅ |
| Tests pass at every task boundary | Full suite after each task | ✅ |

### Placeholder Scan

Tasks 2, 3, 4, and 5 use `# copy body from app/__init__.py lines X-Y verbatim` in code blocks. These are exact line-range references to unchanged source material, not vague placeholders — the function bodies are mechanically copied without modification. The line numbers reference the state of `__init__.py` after Task 1 (identical to the original `app.py`).

### Type Consistency

- `_build_widget` signature is unchanged — `async def _build_widget(widget_cfg, session, config_dir, ...)` — same in `factories.py` as in the original.
- `RANDOM_COLOR: itertools.cycle` annotation matches what `_build_title` calls `next()` on.
- `run(config_path: Path)` signature is unchanged.
- `main() -> None` signature is unchanged.
- All deferred imports (`from led_ticker.validate import MigrationError` inside `_build_widget`, `from led_ticker.validate import ...` inside `main`) remain deferred — no new circular imports introduced.

### Key Invariant: No Logic Changes

This is a pure mechanical code move. If any test fails after any task, the cause is either:
1. A function body that was not copied completely (missing closing `return` or early-exit path)
2. An import that was removed from `__init__.py` before the submodule that needed it was created
3. A missing re-export in `__init__.py`

The fix in all three cases is to check `__init__.py` re-exports against the public surface table at the top of this plan.
