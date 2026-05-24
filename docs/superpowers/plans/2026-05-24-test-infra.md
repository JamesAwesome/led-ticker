# Batch 4 (DR2): Test Infrastructure

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch safety:** Before doing ANY work, run `git branch --show-current`. If it prints `main`, stop immediately and ask for a worktree.

**Goal:** Consolidate duplicated test fixtures, remove incompatible `no_sleep` definitions, replace real network setup in unit tests, harden the AST scanner, and eliminate unusual patching patterns. All changes are to test code only — no production behavior changes.

**Architecture:** Ten independent tasks. Tasks 1–2 (fixture consolidation) should land first so subsequent tasks that touch test files can use the canonical fixtures. Tasks 3–4 reduce test latency. Tasks 5–6 reduce implementation coupling. Tasks 7–9 are cosmetic consistency. Task 10 is a tripwire addition.

**Tech Stack:** pytest, unittest.mock, asyncio, Python AST

**Run tests with:** `PYTHONPATH=tests/stubs uv run pytest -x -q`

**Baseline:** Run `make test` before starting; note the count. After all tasks, the count should be the same or higher (not lower).

---

### Task 1: S15 — Consolidate `no_sleep` into `conftest.py`

`tests/test_ticker.py:149–155` defines `no_sleep` to yield with `await _real_sleep(0)` (real yield). `tests/test_ticker_display.py:15–21` defines its own `no_sleep` that does nothing (`pass`). Two incompatible behaviors for the same fixture name.

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_ticker.py`
- Modify: `tests/test_ticker_display.py`

- [ ] **Step 1: Read both existing `no_sleep` definitions**

```bash
sed -n '145,165p' tests/test_ticker.py
sed -n '12,25p' tests/test_ticker_display.py
```

Determine which variant is correct. The real-sleep-zero variant (`await _real_sleep(0)`) is the correct one — it yields to the event loop so other tasks can run, matching real async behavior.

- [ ] **Step 2: Add `no_sleep` to `conftest.py`**

In `tests/conftest.py`, add the fixture after the existing fixtures:

```python
@pytest.fixture
def no_sleep(monkeypatch):
    """Replace asyncio.sleep with a real-zero sleep that still yields to
    the event loop. Tests that need sleep calls to be no-ops but still
    want cooperative async behavior use this.

    Defined here (not per-file) so all test files share one consistent
    implementation. The real-sleep-zero variant is canonical.
    """
    _real_sleep = asyncio.sleep

    async def _zero_sleep(seconds: float) -> None:
        await _real_sleep(0)

    monkeypatch.setattr("asyncio.sleep", _zero_sleep)
    monkeypatch.setattr("led_ticker.ticker.asyncio.sleep", _zero_sleep)
    monkeypatch.setattr("led_ticker.widgets._image_base.asyncio.sleep", _zero_sleep)
```

Note: the `monkeypatch` targets mirror all the places `asyncio.sleep` is imported. If additional modules import it directly (check with `grep -rn "asyncio.sleep" src/led_ticker/`), add those targets too.

- [ ] **Step 3: Remove the local `no_sleep` from `test_ticker.py`**

In `tests/test_ticker.py`, find the local `no_sleep` definition (around line 149) and delete it. The conftest fixture will be used automatically.

- [ ] **Step 4: Remove the local `no_sleep` from `test_ticker_display.py`**

In `tests/test_ticker_display.py`, find the local `no_sleep` definition (around line 15) and delete it.

- [ ] **Step 5: Run the tests that use `no_sleep`**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_ticker.py tests/test_ticker_display.py -v -q
```

Expected: all pass. If a test that previously used the pass-variant `no_sleep` now fails because the sleep actually yields, the test's assumptions were wrong — fix the test, not the fixture.

- [ ] **Step 6: Run the full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: same count as baseline.

- [ ] **Step 7: Commit**

```bash
git add tests/conftest.py tests/test_ticker.py tests/test_ticker_display.py
git commit -m "fix: consolidate no_sleep into conftest.py with real-sleep-zero variant (S15)"
```

---

### Task 2: S16 — Consolidate bigsign canvas helpers into `conftest.py`

Four test files each define their own `_bigsign_real_canvas()` helper that creates a 256×64 `_StubCanvas` via the pixel-mapper trick:

- `tests/test_widgets/test_gif.py:33–40`
- `tests/test_widgets/test_still.py:39–46`
- `tests/test_widgets/test_two_row.py:329–338` (check exact lines)
- `tests/test_scaled_canvas.py` (check exact location)

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_widgets/test_gif.py`
- Modify: `tests/test_widgets/test_still.py`
- Modify: `tests/test_widgets/test_two_row.py`
- Modify: `tests/test_scaled_canvas.py`

- [ ] **Step 1: Read all four helper definitions**

```bash
grep -n "_bigsign_real_canvas\|bigsign" tests/test_widgets/test_gif.py | head -5
sed -n '33,42p' tests/test_widgets/test_gif.py
grep -n "_bigsign_real_canvas" tests/test_widgets/test_still.py | head -3
grep -n "_bigsign_real_canvas" tests/test_widgets/test_two_row.py | head -3
grep -n "_bigsign_real_canvas\|bigsign" tests/test_scaled_canvas.py | head -5
```

Confirm all four definitions are identical (or near-identical) before consolidating.

- [ ] **Step 2: Add `bigsign_canvas` fixture to `conftest.py`**

In `tests/conftest.py`, add:

```python
@pytest.fixture
def bigsign_canvas():
    """256×64 real stub canvas simulating the bigsign panel layout.

    Uses the U-mapper pixel_mapper_config so the ScaledCanvas wrapper
    correctly computes y_offset_real for the 2×4 vertical-serpentine chain.
    Function-scoped (default) so each test gets a fresh canvas.
    """
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    opts = RGBMatrixOptions()
    opts.cols = 64
    opts.rows = 32
    opts.chain_length = 8
    opts.parallel = 1
    opts.pixel_mapper_config = "U-mapper"
    return RGBMatrix(options=opts).CreateFrameCanvas()
```

Note: if the helper in the existing files differs from the above (different options, different mapper), use the exact body from the existing helpers.

- [ ] **Step 3: Remove local definitions from each file**

For each of the four test files:
1. Delete the `_bigsign_real_canvas()` function definition
2. Replace `_bigsign_real_canvas()` call sites with `bigsign_canvas` (the fixture, passed as a parameter to test methods/functions)

The fixture must be added as a parameter to any test that was previously calling `_bigsign_real_canvas()` directly.

For module-level tests (not inside a class), add `bigsign_canvas` as a parameter. For class-based tests, add it to each test method or use a `@pytest.fixture(autouse=False)` approach.

Example transformation:

```python
# Before:
def test_foo():
    real = _bigsign_real_canvas()
    # ... use real

# After:
def test_foo(bigsign_canvas):
    real = bigsign_canvas
    # ... use real
```

- [ ] **Step 4: Run the affected test files**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_gif.py tests/test_widgets/test_still.py tests/test_widgets/test_two_row.py tests/test_scaled_canvas.py -v -q
```

Expected: same pass count as before consolidation.

- [ ] **Step 5: Run the full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_widgets/test_gif.py tests/test_widgets/test_still.py tests/test_widgets/test_two_row.py tests/test_scaled_canvas.py
git commit -m "fix: consolidate 4x bigsign canvas helpers into conftest.py fixture (S16)"
```

---

### Task 3: S17 — Replace real `aiohttp.ClientSession` in unit tests

`tests/test_app.py:406–456,459–520` creates real `aiohttp.ClientSession` contexts in tests that never make network calls. These add socket/fd overhead and produce `ResourceWarning: Unclosed client session` on abnormal exit.

**Files:**
- Modify: `tests/test_app.py`

- [ ] **Step 1: Find the affected tests**

```bash
grep -n "aiohttp.ClientSession\|async with aiohttp" tests/test_app.py | head -20
```

Identify all test methods/functions that open a real ClientSession.

- [ ] **Step 2: Replace with `mock.Mock()`**

For each affected test, replace:

```python
# Before:
async with aiohttp.ClientSession() as session:
    widget = await _build_widget(cfg, session, ...)

# After:
session = mock.Mock()
widget = await _build_widget(cfg, session, ...)
```

The session is never used for any network call in these test paths (only passed through to widget constructors that don't use it for font/message widgets).

- [ ] **Step 3: Remove the `import aiohttp` if no longer needed**

```bash
grep -n "aiohttp" tests/test_app.py
```

If `aiohttp` is only used for the `ClientSession` calls being replaced, remove the import.

- [ ] **Step 4: Run the affected tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_app.py -v -q
```

Expected: same pass count; no `ResourceWarning`.

- [ ] **Step 5: Run the full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_app.py
git commit -m "fix: replace real aiohttp.ClientSession with mock.Mock() in unit tests (S17)"
```

---

### Task 4: S18 — Replace subprocess CLI tests with in-process calls

`tests/test_validate.py:512–549` has four tests that invoke `subprocess.run(["uv", "run", "led-ticker", "validate", ...])`. Each spawns a fresh Python interpreter (slow) and requires `uv` in `PATH`. The underlying behavior is already covered by adjacent tests.

**Files:**
- Modify: `tests/test_validate.py`

- [ ] **Step 1: Read the four subprocess tests**

```bash
sed -n '510,555p' tests/test_validate.py
```

Note what each test checks (exit code mapping, JSON output format, specific error messages, etc.).

- [ ] **Step 2: Keep one as a `@pytest.mark.slow` smoke test**

Choose the most end-to-end subprocess test (likely one that checks the actual binary name and exit code). Add the marker and a `uv` availability check:

```python
@pytest.mark.slow
def test_validate_cli_smoke(tmp_path):
    """Smoke test: the installed CLI returns a non-zero exit on invalid config.
    Marked slow because it spawns a subprocess. Run with: pytest -m slow.
    Requires uv in PATH — skipped if not found.
    """
    import shutil
    if not shutil.which("uv"):
        pytest.skip("uv not in PATH")
    # ... keep the original subprocess.run call
```

- [ ] **Step 3: Replace the other three with in-process calls**

The `led-ticker validate` CLI entry point is `led_ticker.app:main`. Call it directly:

```python
from unittest import mock
from led_ticker.validate import validate_config  # or whatever the validate function is

async def test_validate_invalid_config_exit_code(tmp_path):
    """validate returns non-zero for invalid config without spawning a process."""
    bad_toml = tmp_path / "bad.toml"
    bad_toml.write_text("[display]\ncols = 0\n")
    result = validate_config(str(bad_toml))
    assert result != 0  # or check for a raised exception, depending on the API
```

Check what `validate_config` or the equivalent function returns — read `src/led_ticker/validate.py` to find the right function and signature.

- [ ] **Step 4: Run the validate tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -v -q
```

Expected: the `@pytest.mark.slow` test is NOT run (not slow-marked by default); in-process tests run and pass.

- [ ] **Step 5: Verify slow test works when explicitly run**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -m slow -v
```

Expected: the subprocess smoke test passes (requires `uv` in PATH).

- [ ] **Step 6: Run the full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: count slightly lower (subprocess tests removed; in-process tests added at similar or equal count).

- [ ] **Step 7: Commit**

```bash
git add tests/test_validate.py
git commit -m "fix: replace 3 subprocess CLI tests with in-process calls; keep 1 as @pytest.mark.slow (S18)"
```

---

### Task 5: S19 — Reroute `_frame_count` spy stubs to side-effect counters

`tests/test_ticker_display.py:1104–1218` and related spy stubs directly read `_frame_count` from widget stubs. If `_FrameAware` renames `_frame_count`, Mock stubs silently pass while explicit stubs break immediately — inconsistent failure mode.

**Files:**
- Modify: `tests/test_ticker_display.py`
- Modify: any other test files with `_frame_count` in stubs

- [ ] **Step 1: Find all `_frame_count` direct access in tests**

```bash
grep -rn "_frame_count" tests/ --include="*.py"
```

List all sites. For each one, understand what it's asserting.

- [ ] **Step 2: Replace direct counter reads with call-count assertions**

Instead of reading `widget._frame_count` to verify advance_frame was called N times, count `advance_frame` calls via a side-effect:

```python
# Pattern A: count calls via a spy
advance_calls = []
original = widget.advance_frame
widget.advance_frame = lambda: (advance_calls.append(1), original())[1]

# ... run the code under test ...

assert len(advance_calls) == expected_n_ticks

# Pattern B: for Mock stubs, use call_count
mock_widget.advance_frame.call_count
```

For tests that check reset behavior (verifying counter goes back to 0 after a visit), use `frame_for()` to observe the effect rather than reading the raw counter:

```python
# Check that the frame counter restarted (typewriter at frame 0 = no chars shown)
widget.reset_frame()
frame = AnimationFrame(visible_text="")  # whatever frame_for(0) should return
assert widget.frame_for("animation") == expected_at_frame_0
```

- [ ] **Step 3: Run the affected tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py -v -q -k "frame"
```

Expected: all pass.

- [ ] **Step 4: Run the full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_ticker_display.py
git commit -m "fix: replace _frame_count private access in spy stubs with call-count assertions (S19)"
```

---

### Task 6: S20 — Add AST scanner tripwire for extracted-helper swap count

`tests/test_engine_redraw_contract.py:81–102` scans `ticker.py` for `_swap(` calls as the "this is a redraw loop" signal. If `advance_frame + draw + _swap` is ever extracted into a helper, the scanner silently stops checking. The scanner's docstring acknowledges this but there is no mechanical enforcement.

**Files:**
- Modify: `tests/test_engine_redraw_contract.py`

- [ ] **Step 1: Count current `_swap(` occurrences in `ticker.py`**

```bash
grep -c "_swap(" src/led_ticker/ticker.py
```

Note the exact count. This is the constant the new test will assert.

- [ ] **Step 2: Add the tripwire test**

In `tests/test_engine_redraw_contract.py`, add a new test after the existing ones:

```python
# If this constant drifts from the actual count, update it AND update
# the AST scanner's loop-detection logic so it still covers all sites.
_EXPECTED_SWAP_CALL_COUNT = <N>  # replace <N> with the count from Step 1


class TestSwapCallCountTripwire:
    """Mechanical tripwire for the AST scanner's loop-detection assumption.

    The scanner finds redraw loops by looking for `_swap(` calls in the
    loop body. If a future refactor extracts `advance_frame + draw + _swap`
    into a helper method, `_swap(` disappears from the loop body and the
    scanner silently stops checking the advance_frame requirement.

    This test asserts the count of `_swap(` calls in ticker.py matches a
    declared constant. Changing the constant requires also updating the
    AST scanner to maintain its coverage. (S20)
    """

    def test_swap_call_count_matches_expected(self):
        import ast
        import textwrap

        source = Path("src/led_ticker/ticker.py").read_text()
        tree = ast.parse(source)

        swap_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_swap"
        ]
        assert len(swap_calls) == _EXPECTED_SWAP_CALL_COUNT, (
            f"Expected {_EXPECTED_SWAP_CALL_COUNT} _swap( calls in ticker.py, "
            f"found {len(swap_calls)}. If you extracted a helper that wraps _swap, "
            "update _EXPECTED_SWAP_CALL_COUNT here AND update the AST scanner in "
            "this file to detect the new pattern."
        )
```

Replace `<N>` with the actual count from Step 1.

- [ ] **Step 3: Run the test**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_engine_redraw_contract.py -v
```

Expected: all pass including the new test.

- [ ] **Step 4: Run the full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_engine_redraw_contract.py
git commit -m "fix: add AST tripwire asserting _swap( call count in ticker.py (S20)"
```

---

### Task 7: M15 — Replace `pytest-mock` usage in `test_ticker_wraps_forever.py`

`tests/test_ticker_wraps_forever.py` is the only test file using `mocker.MagicMock()`, `mocker.AsyncMock()`, `mocker.patch()` from `pytest-mock`. All other files use `unittest.mock`.

**Files:**
- Modify: `tests/test_ticker_wraps_forever.py`

- [ ] **Step 1: Find all `mocker` usages**

```bash
grep -n "mocker\." tests/test_ticker_wraps_forever.py
```

- [ ] **Step 2: Replace with `unittest.mock` equivalents**

```python
# Replacements:
mocker.MagicMock()          → mock.MagicMock()
mocker.AsyncMock()          → mock.AsyncMock()
mocker.patch("x.y")         → monkeypatch.setattr("x.y", ...)  # or @mock.patch decorator
mocker.patch.object(a, "b") → monkeypatch.setattr(a, "b", ...)
```

Remove `mocker` from test function signatures and add `monkeypatch` where needed.

- [ ] **Step 3: Run the file's tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_wraps_forever.py -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_ticker_wraps_forever.py
git commit -m "fix: replace pytest-mock with unittest.mock in test_ticker_wraps_forever.py (M15)"
```

---

### Task 8: M16 — Replace class-level method patching in `TestTwoRowLogicalUnits`

`tests/test_widgets/test_image_base.py:389–406,430–450,493–512` patches `_BaseImageWidget._render_two_row_tick` directly on the class with `try/finally` restoration. This is not thread-safe and is unusual enough to confuse contributors.

**Files:**
- Modify: `tests/test_widgets/test_image_base.py`

- [ ] **Step 1: Find the patching sites**

```bash
grep -n "_render_two_row_tick\|_BaseImageWidget\._render" tests/test_widgets/test_image_base.py | head -15
```

- [ ] **Step 2: Replace with `patch.object`**

The `try/finally` pattern:

```python
# Before:
original = _BaseImageWidget._render_two_row_tick
try:
    _BaseImageWidget._render_two_row_tick = some_spy
    # ... test body ...
finally:
    _BaseImageWidget._render_two_row_tick = original

# After (using monkeypatch for pytest-style):
def test_something(monkeypatch):
    render_calls = []
    def spy(*args, **kwargs):
        render_calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(_BaseImageWidget, "_render_two_row_tick", spy)
    # ... test body ...

# Or using mock.patch.object as a context manager:
with mock.patch.object(_BaseImageWidget, "_render_two_row_tick") as m:
    # ... test body ...
    assert m.called
```

Apply the appropriate replacement to each of the three patching sites.

- [ ] **Step 3: Run the affected tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py::TestTwoRowLogicalUnits -v
```

Expected: all pass.

- [ ] **Step 4: Run the full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_widgets/test_image_base.py
git commit -m "fix: replace class-level method patching with mock.patch.object (M16)"
```

---

### Task 9: M17 — Consolidate 4 smoke app-module test files

`tests/test_app_factories_module.py`, `tests/test_app_coercion_module.py`, `tests/test_app_cli_module.py`, `tests/test_app_run_module.py` — each contains only 2 "assert callable/importable" smoke tests from the Large #1 refactor.

**Files:**
- Create: `tests/test_app_submodule_imports.py`
- Delete: `tests/test_app_factories_module.py`
- Delete: `tests/test_app_coercion_module.py`
- Delete: `tests/test_app_cli_module.py`
- Delete: `tests/test_app_run_module.py`

- [ ] **Step 1: Read all four files**

```bash
cat tests/test_app_factories_module.py tests/test_app_coercion_module.py tests/test_app_cli_module.py tests/test_app_run_module.py
```

- [ ] **Step 2: Create consolidated file**

Create `tests/test_app_submodule_imports.py` with parametrized assertions:

```python
"""Smoke tests: backward-compatible import paths from the Large #1 app.py split.

These verify that the re-exported symbols in led_ticker.app still work after
the split into app/cli.py, app/factories.py, app/coercion.py, app/run.py.
"""

import importlib

import pytest


@pytest.mark.parametrize(
    "module, symbol",
    [
        # factories.py
        ("led_ticker.app.factories", "_build_widget"),
        ("led_ticker.app.factories", "_build_trans_obj"),
        # coercion.py
        ("led_ticker.app.coercion", "_coerce_color_provider"),
        ("led_ticker.app.coercion", "_coerce_border"),
        # cli.py
        ("led_ticker.app.cli", "main"),
        # run.py
        ("led_ticker.app.run", "run"),
        # ... add all symbols that were in the original four files
    ],
)
def test_symbol_importable(module, symbol):
    mod = importlib.import_module(module)
    assert callable(getattr(mod, symbol)), f"{module}.{symbol} should be callable"
```

Copy all the parametrize values from the original four files — do not skip any symbol.

- [ ] **Step 3: Delete the old files**

```bash
git rm tests/test_app_factories_module.py tests/test_app_coercion_module.py tests/test_app_cli_module.py tests/test_app_run_module.py
```

- [ ] **Step 4: Run the new consolidated file**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_app_submodule_imports.py -v
```

Expected: all parametrize combinations pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_app_submodule_imports.py
git commit -m "fix: consolidate 4 app submodule smoke test files into parametrized test (M17)"
```

---

### Task 10: M18 — Express scroll stop assertions as computed formulas

`tests/test_ticker_display.py:112–113,139–143` asserts `scroll_pos == -440` with only an inline comment. If canvas width changes, the magic value silently becomes wrong.

**Files:**
- Modify: `tests/test_ticker_display.py`

- [ ] **Step 1: Find the magic number assertions**

```bash
sed -n '108,150p' tests/test_ticker_display.py
```

Read the comment explaining the formula (e.g., `# 440 = content_width - canvas_width`).

- [ ] **Step 2: Replace with computed expressions**

```python
# Before:
assert scroll_pos == -440  # content_width=600 - canvas_width=160

# After:
expected_stop = -(content_width - canvas.width)
assert scroll_pos == expected_stop, (
    f"Expected scroll stop at {expected_stop} "
    f"(content_width={content_width} - canvas.width={canvas.width}), "
    f"got {scroll_pos}"
)
```

Where `content_width` is whatever the test uses to control the widget's text width.

- [ ] **Step 3: Run the affected tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py -v -q -k "scroll"
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_ticker_display.py
git commit -m "fix: express scroll stop assertions as computed formulas instead of magic numbers (M18)"
```

---

## Self-Review

**Spec coverage:**

| Finding | Task | Status |
|---------|------|--------|
| S15 — incompatible no_sleep fixtures | Task 1 | ✅ |
| S16 — 4× duplicate bigsign helpers | Task 2 | ✅ |
| S17 — real aiohttp.ClientSession in unit tests | Task 3 | ✅ |
| S18 — subprocess CLI tests | Task 4 | ✅ |
| S19 — _frame_count private access | Task 5 | ✅ |
| S20 — AST scanner false-negative | Task 6 | ✅ |
| M15 — pytest-mock in one file | Task 7 | ✅ |
| M16 — class-level method patching | Task 8 | ✅ |
| M17 — 4 smoke test files | Task 9 | ✅ |
| M18 — magic number assertions | Task 10 | ✅ |

**Placeholder scan:** Task 4 (S18) has "check what validate_config returns — read the function" — this is intentional, as the validate API varies and must be read at execution time. Task 6 (S20) requires the implementer to fill in `<N>` from a grep count. Both are documented clearly.

**Order note:** Task 1 (no_sleep) before Tasks 2–10. Task 2 (bigsign fixture) benefits from being before Tasks 3–4 which may touch the same test files.
