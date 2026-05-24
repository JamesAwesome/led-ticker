# Large (DR2): Complete Large #1 — `_build_widget` Decomposition

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch safety:** Before doing ANY work, run `git branch --show-current`. If it prints `main`, stop immediately and ask for a worktree.

**Goal:** Complete what Large #1 started. `_build_widget` is still a 308-line orchestrator with a `validate_only` toggle (`factories.py:95,389`) that serves two callers (construction vs. validation-only) with structurally different goals. Extract phase helpers, add `validate_widget_cfg` to eliminate the toggle, and reduce `_build_widget` to a thin orchestrator under 60 lines.

**Architecture:** One PR per extracted helper, plus a final PR that removes `validate_only` entirely. Each PR is independently reviewable and testable. The sequence: path resolution first (most self-contained) → font resolution → field validation → `validate_widget_cfg` (toggle removal). `_build_widget` is refactored incrementally — never broken between PRs.

**`_build_widget` current phases (in order):**

1. Migration checks (`text_scale`, `presentation`) — lines 115–151
2. Widget type extraction + class resolution — lines 153–156
3. Animation / border / wrap-key coercion and guard — lines 163–232
4. bg_color injection — lines 236–237
5. Font resolution (`font`, `font_size`, `font_threshold`, per-row fonts) — lines 239–306
6. Field mapping (`text→message`, asset path resolution, color coercion) — lines 308–355
7. Unknown-field check — lines 360–387
8. `validate_only` gate — lines 389–390
9. Construction (`cls(**widget_cfg)` or `cls.start(...)`) — lines 392–397

Phases 5, 6, and 7 become extracted helpers. Phase 8 is eliminated by extracting `validate_widget_cfg`.

**Tech Stack:** Python, attrs, asyncio, pytest

**Run tests with:** `PYTHONPATH=tests/stubs uv run pytest -x -q`

**Baseline:** Run `make test` before starting; note the count. After all tasks, the count should be higher (new tests added per helper) with zero regressions.

---

### Task 1: Extract `_resolve_asset_paths(widget_cfg, widget_type, config_dir)`

Phase 6 contains the path-resolution block (lines 328–335), which is the most self-contained logic in `_build_widget`. Extracting it first is a proof of concept for the decomposition pattern.

**Files:**
- Modify: `src/led_ticker/app/factories.py`
- Test: `tests/test_app_factories.py` (or add a new test class)

- [ ] **Step 1: Write failing tests**

In the test file for factories (check `tests/test_app.py` or `tests/test_app_factories_module.py` for existing coverage — look for tests that exercise path resolution):

```python
class TestResolveAssetPaths:
    """_resolve_asset_paths mutates widget_cfg in-place, converting a
    relative 'path' key to an absolute path anchored at config_dir."""

    def test_relative_path_resolved_to_absolute(self, tmp_path):
        from led_ticker.app.factories import _resolve_asset_paths
        from pathlib import Path

        cfg = {"path": "gifs/rainbow.gif"}
        config_dir = tmp_path / "config"
        _resolve_asset_paths(cfg, "gif", config_dir)
        assert cfg["path"] == str((config_dir / "gifs/rainbow.gif").resolve())

    def test_absolute_path_unchanged(self, tmp_path):
        from led_ticker.app.factories import _resolve_asset_paths

        absolute = "/home/pi/gifs/rainbow.gif"
        cfg = {"path": absolute}
        _resolve_asset_paths(cfg, "gif", tmp_path)
        assert cfg["path"] == absolute

    def test_non_gif_type_unchanged(self, tmp_path):
        from led_ticker.app.factories import _resolve_asset_paths

        cfg = {"path": "something.gif"}
        _resolve_asset_paths(cfg, "message", tmp_path)
        assert cfg["path"] == "something.gif"  # message type — path not touched

    def test_no_path_key_is_noop(self, tmp_path):
        from led_ticker.app.factories import _resolve_asset_paths

        cfg = {"text": "hello"}
        _resolve_asset_paths(cfg, "gif", tmp_path)  # no "path" key — should not raise
        assert "path" not in cfg

    def test_none_config_dir_leaves_path_unchanged(self):
        from led_ticker.app.factories import _resolve_asset_paths

        cfg = {"path": "gifs/rainbow.gif"}
        _resolve_asset_paths(cfg, "gif", None)
        assert cfg["path"] == "gifs/rainbow.gif"
```

- [ ] **Step 2: Run to confirm failure**

```bash
PYTHONPATH=tests/stubs uv run pytest -k "TestResolveAssetPaths" -v
```

Expected: `FAILED` — `_resolve_asset_paths` not yet defined.

- [ ] **Step 3: Extract `_resolve_asset_paths` into `factories.py`**

Add before `_build_widget`:

```python
def _resolve_asset_paths(
    widget_cfg: dict[str, Any],
    widget_type: str,
    config_dir: Path | None,
) -> None:
    """Resolve relative `path` values to absolute paths anchored at config_dir.

    Mutates widget_cfg in-place. Only applies to file-backed widget types
    (gif, image). Relative paths are resolved against config_dir; absolute
    paths and missing config_dir are left unchanged.
    """
    if widget_type not in ("gif", "image"):
        return
    if "path" not in widget_cfg:
        return
    if config_dir is None:
        return
    candidate = Path(widget_cfg["path"])
    if not candidate.is_absolute():
        widget_cfg["path"] = str((config_dir / candidate).resolve())
```

- [ ] **Step 4: Replace the inline block in `_build_widget` with a call**

In `_build_widget`, find lines 328–335 (the path resolution block):

```python
# Remove the old inline block:
    if (
        widget_type in ("gif", "image")
        and "path" in widget_cfg
        and config_dir is not None
    ):
        candidate = Path(widget_cfg["path"])
        if not candidate.is_absolute():
            widget_cfg["path"] = str((config_dir / candidate).resolve())

# Replace with:
    _resolve_asset_paths(widget_cfg, widget_type, config_dir)
```

- [ ] **Step 5: Run the tests**

```bash
PYTHONPATH=tests/stubs uv run pytest -k "TestResolveAssetPaths" -v
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: both pass. Behavior is unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app/factories.py tests/
git commit -m "refactor: extract _resolve_asset_paths helper from _build_widget (S22 phase 1)"
```

---

### Task 2: Extract `_resolve_fonts(widget_cfg, widget_type, cls, panel_h_for_warning)`

Lines 239–306 handle `font`, `font_size`, `font_threshold`, and per-row `top_font`/`bottom_font` resolution. This is the second-most self-contained block.

**Files:**
- Modify: `src/led_ticker/app/factories.py`
- Test: `tests/test_app.py` (or a new test class)

- [ ] **Step 1: Write failing tests**

```python
class TestResolveFonts:
    """_resolve_fonts resolves font name strings to Font/HiresFont objects
    and injects font_size into widget_cfg for image-type widgets."""

    def test_no_font_name_is_noop(self):
        from led_ticker.app.factories import _resolve_fonts
        cfg = {"text": "hello"}
        _resolve_fonts(cfg, "message", None, panel_h_for_warning=None)
        assert "font" not in cfg  # nothing injected

    def test_bdf_font_name_resolves_to_font_object(self):
        from led_ticker.app.factories import _resolve_fonts
        from led_ticker.fonts import BDFFont  # or whatever the BDF class is called

        cfg = {"font": "6x12"}
        _resolve_fonts(cfg, "message", None, panel_h_for_warning=None)
        assert "font" in cfg
        # The string "6x12" was replaced by a Font object:
        assert not isinstance(cfg["font"], str)

    def test_hires_font_without_font_size_raises(self):
        from led_ticker.app.factories import _resolve_fonts

        cfg = {"font": "Atkinson-Bold"}  # a hires font name
        with pytest.raises(ValueError, match="requires font_size"):
            _resolve_fonts(cfg, "message", None, panel_h_for_warning=None)

    def test_font_size_injected_for_image_widget_with_cls_field(self):
        from led_ticker.app.factories import _resolve_fonts
        from led_ticker.widgets.gif import GifPlayer

        cfg = {"font": "6x12", "font_size": 12}
        _resolve_fonts(cfg, "gif", GifPlayer, panel_h_for_warning=None)
        assert cfg.get("font_size") == 12

    def test_font_size_not_injected_for_message_widget(self):
        from led_ticker.app.factories import _resolve_fonts
        from led_ticker.widgets.message import TickerMessage

        cfg = {"font": "6x12", "font_size": 12}
        _resolve_fonts(cfg, "message", TickerMessage, panel_h_for_warning=None)
        # TickerMessage has no font_size field — must not be injected
        assert "font_size" not in cfg
```

Note: check the actual font name APIs before writing tests. Use `grep -rn "class.*Font\|BDFFont" src/led_ticker/fonts/` to find the base class names.

- [ ] **Step 2: Run to confirm failure**

```bash
PYTHONPATH=tests/stubs uv run pytest -k "TestResolveFonts" -v
```

Expected: FAILED — `_resolve_fonts` not yet defined.

- [ ] **Step 3: Extract `_resolve_fonts` into `factories.py`**

The function signature:

```python
def _resolve_fonts(
    widget_cfg: dict[str, Any],
    widget_type: str,
    cls: type | None,
    panel_h_for_warning: int | None,
) -> None:
    """Resolve font name strings to Font/HiresFont objects and inject
    font_size into widget_cfg for widgets that accept it.

    Mutates widget_cfg in-place. Pops: font, font_size, font_threshold,
    top_font, top_font_size, top_font_threshold, bottom_font, bottom_font_size,
    bottom_font_threshold. Inserts: font (resolved object), top_font,
    bottom_font (resolved objects), font_size (for image widgets only).

    Raises ValueError if a HiresFont name is given without font_size.
    """
```

Move the entirety of lines 239–306 from `_build_widget` into this function body. Replace the inline block in `_build_widget` with:

```python
    _resolve_fonts(widget_cfg, widget_type, cls, panel_h_for_warning)
```

Note: `cls` is needed to check `cls_fields` for the `font_size` injection (line 317). Pass it as an argument.

- [ ] **Step 4: Run the tests**

```bash
PYTHONPATH=tests/stubs uv run pytest -k "TestResolveFonts" -v
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/app/factories.py tests/
git commit -m "refactor: extract _resolve_fonts helper from _build_widget (S22 phase 2)"
```

---

### Task 3: Extract `_validate_cfg_fields(widget_cfg, cls)` — unknown-field check

Lines 360–387 compute `unknown = set(widget_cfg.keys()) - cls_init_fields` and raise a `ValueError` with did-you-mean suggestions. This is a distinct validation phase that can be tested in isolation.

**Files:**
- Modify: `src/led_ticker/app/factories.py`
- Test: tests for factories

- [ ] **Step 1: Write failing tests**

```python
class TestValidateCfgFields:
    """_validate_cfg_fields raises ValueError with did-you-mean hints on
    unknown kwargs so users see actionable error messages instead of
    a raw TypeError from attrs."""

    def test_unknown_field_raises_with_name(self):
        from led_ticker.app.factories import _validate_cfg_fields
        from led_ticker.widgets.message import TickerMessage

        cfg = {"message": "hello", "unknown_field": "value"}
        with pytest.raises(ValueError, match="unknown_field"):
            _validate_cfg_fields(cfg, TickerMessage)

    def test_did_you_mean_hint_included(self):
        from led_ticker.app.factories import _validate_cfg_fields
        from led_ticker.widgets.message import TickerMessage

        # "massage" is close to "message" — should suggest "message"
        cfg = {"massage": "hello"}
        with pytest.raises(ValueError, match="did you mean"):
            _validate_cfg_fields(cfg, TickerMessage)

    def test_valid_fields_do_not_raise(self):
        from led_ticker.app.factories import _validate_cfg_fields
        from led_ticker.widgets.message import TickerMessage

        cfg = {"message": "hello", "font_color": None}
        _validate_cfg_fields(cfg, TickerMessage)  # must not raise
```

- [ ] **Step 2: Run to confirm failure**

```bash
PYTHONPATH=tests/stubs uv run pytest -k "TestValidateCfgFields" -v
```

- [ ] **Step 3: Extract `_validate_cfg_fields` into `factories.py`**

```python
def _validate_cfg_fields(
    widget_cfg: dict[str, Any],
    cls: type,
) -> None:
    """Check that all keys in widget_cfg are recognized attrs fields of cls.

    Raises ValueError with did-you-mean suggestions on unknown keys.
    Also includes `cls.start()` parameter names for data widgets (widgets
    that use a class-method start factory instead of direct construction).
    """
```

Move lines 360–387 from `_build_widget` into this function. Replace the inline block with:

```python
    _validate_cfg_fields(widget_cfg, cls)
```

- [ ] **Step 4: Run the tests**

```bash
PYTHONPATH=tests/stubs uv run pytest -k "TestValidateCfgFields" -v
PYTHONPATH=tests/stubs uv run pytest -x -q
```

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/app/factories.py tests/
git commit -m "refactor: extract _validate_cfg_fields helper from _build_widget (S22 phase 3)"
```

---

### Task 4: Extract `validate_widget_cfg` and remove `validate_only` toggle (S1)

The `validate_only` toggle (`factories.py:95,389`) gates construction: when `True`, all phases run but the widget is never instantiated. The fix: extract `validate_widget_cfg(widget_cfg, ...) -> None` that runs all phases except construction. `_build_widget` becomes construction-only. `validate.py` calls `validate_widget_cfg` directly.

This is the S1 fix that completes the semantic goal of Large #1.

**Files:**
- Modify: `src/led_ticker/app/factories.py`
- Modify: `src/led_ticker/validate.py`
- Test: `tests/test_app.py`, `tests/test_validate.py`

- [ ] **Step 1: Write failing tests**

```python
class TestValidateWidgetCfg:
    """validate_widget_cfg runs all validation phases without instantiating
    the widget. It replaces the validate_only=True path in _build_widget
    and makes the construction/validation boundary explicit. (S1)
    """

    async def test_validate_widget_cfg_raises_on_unknown_field(self, tmp_path):
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {"type": "message", "text": "hello", "invalid_field": "value"}
        with pytest.raises(ValueError, match="invalid_field"):
            await validate_widget_cfg(
                cfg,
                session=None,
                config_dir=tmp_path,
            )

    async def test_validate_widget_cfg_raises_on_migration_error(self, tmp_path):
        from led_ticker.app.factories import validate_widget_cfg
        from led_ticker.validate import MigrationError

        cfg = {"type": "message", "text": "hello", "text_scale": 2}
        with pytest.raises(MigrationError):
            await validate_widget_cfg(cfg, session=None, config_dir=tmp_path)

    async def test_validate_widget_cfg_does_not_instantiate(self, tmp_path, monkeypatch):
        """validate_widget_cfg must not construct the widget class."""
        from led_ticker.app.factories import validate_widget_cfg

        constructed = []
        from led_ticker.widgets import message as msg_module
        original_init = msg_module.TickerMessage.__init__

        def _spy_init(self, *args, **kwargs):
            constructed.append(1)
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(msg_module.TickerMessage, "__init__", _spy_init)

        cfg = {"type": "message", "text": "hello"}
        await validate_widget_cfg(cfg, session=None, config_dir=tmp_path)
        assert not constructed, (
            "validate_widget_cfg must not call the widget constructor"
        )

    def test_build_widget_has_no_validate_only_parameter(self):
        """After this refactor, _build_widget must not accept validate_only."""
        import inspect
        from led_ticker.app.factories import _build_widget
        params = inspect.signature(_build_widget).parameters
        assert "validate_only" not in params, (
            "validate_only parameter must be removed from _build_widget. "
            "Use validate_widget_cfg instead."
        )
```

- [ ] **Step 2: Run to confirm failure**

```bash
PYTHONPATH=tests/stubs uv run pytest -k "TestValidateWidgetCfg" -v
```

Expected: FAILED — `validate_widget_cfg` not yet defined; `validate_only` still in `_build_widget` signature.

- [ ] **Step 3: Extract `validate_widget_cfg` in `factories.py`**

`validate_widget_cfg` is `_build_widget` minus steps 8 and 9 (the `validate_only` gate and construction). Because `_build_widget` now delegates to the phase helpers from Tasks 1–3, `validate_widget_cfg` can call the same helpers:

```python
async def validate_widget_cfg(
    widget_cfg: dict[str, Any],
    session: aiohttp.ClientSession | None,
    config_dir: Path | None = None,
    default_bg_color: tuple[int, int, int] | None = None,
    panel_h_for_warning: int | None = None,
    coercion_collector: list[Any] | None = None,
) -> None:
    """Run all widget configuration validation phases without constructing
    the widget instance.

    Equivalent to the former _build_widget(validate_only=True) path but
    with an explicit signature and return type. Used by validate.py so
    the construction/validation boundary is explicit.

    Raises ValueError, MigrationError, or other exceptions on invalid config.
    """
    from led_ticker.validate import MigrationError

    # Phase 1: migration checks
    if "text_scale" in widget_cfg:
        raise MigrationError(...)  # same text as in _build_widget
    if "presentation" in widget_cfg:
        raise MigrationError(...)  # same text as in _build_widget

    # Phase 2: type extraction
    widget_type = widget_cfg.pop("type")
    cls = get_widget_class(widget_type)

    # Phase 3: field coercion
    _coerce_widget_cfg(widget_cfg, coercion_collector)

    # ... animation, border, wrap-key guards (copy from _build_widget) ...

    # bg_color injection
    if default_bg_color is not None and "bg_color" not in widget_cfg:
        widget_cfg["bg_color"] = list(default_bg_color)

    # Phase 5: font resolution
    _resolve_fonts(widget_cfg, widget_type, cls, panel_h_for_warning)

    # Phase 6: asset path resolution and field mapping
    _resolve_asset_paths(widget_cfg, widget_type, config_dir)
    _coerce_widget_colors(widget_cfg)
    # ... text→message mapping, top_color/bottom_color guard ...

    # Phase 7: unknown field check
    _validate_cfg_fields(widget_cfg, cls)
    # Done — no construction
```

Note: copy the animation/border/wrap-key guard code from `_build_widget` into `validate_widget_cfg`. The duplication between `validate_widget_cfg` and `_build_widget` is temporary — in Step 4 below, `_build_widget` will call `validate_widget_cfg`.

- [ ] **Step 4: Refactor `_build_widget` to call `validate_widget_cfg`**

After `validate_widget_cfg` is defined, `_build_widget` can be simplified to:

```python
async def _build_widget(
    widget_cfg: dict[str, Any],
    session: aiohttp.ClientSession,
    config_dir: Path | None = None,
    default_bg_color: tuple[int, int, int] | None = None,
    panel_h_for_warning: int | None = None,
    coercion_collector: list[Any] | None = None,
) -> Any:
    """Instantiate a widget from its config dict."""
    # Run all validation phases first. widget_cfg is mutated in-place by
    # validate_widget_cfg (colors coerced, paths resolved, type popped, etc.).
    # We need the widget type and class, so save them before they're popped.
    widget_type = widget_cfg.get("type")  # peek, don't pop yet

    await validate_widget_cfg(
        widget_cfg,
        session=session,
        config_dir=config_dir,
        default_bg_color=default_bg_color,
        panel_h_for_warning=panel_h_for_warning,
        coercion_collector=coercion_collector,
    )
    # widget_cfg is now fully coerced and validated. "type" has been popped
    # by validate_widget_cfg — get the class from the saved type name.
    cls = get_widget_class(widget_type)

    if hasattr(cls, "start"):
        return await cls.start(session=session, **widget_cfg)
    return cls(**widget_cfg)
```

Note: `validate_widget_cfg` pops `"type"` from `widget_cfg`. Save it BEFORE calling `validate_widget_cfg`. Alternatively, have `validate_widget_cfg` return the class instead of being pure-void. Choose whichever design keeps `_build_widget` simplest.

- [ ] **Step 5: Remove `validate_only` parameter from `_build_widget`**

With `validate_widget_cfg` in place, `validate_only` is no longer needed. Remove the parameter and the `if validate_only: return None` gate.

- [ ] **Step 6: Update `validate.py` to call `validate_widget_cfg`**

In `src/led_ticker/validate.py:_run_build_checks`, replace the `_build_widget(validate_only=True, ...)` call:

```python
# Before:
await _build_widget(
    copy.deepcopy(widget_cfg),
    session=None,
    config_dir=config_dir,
    validate_only=True,
    coercion_collector=widget_warnings,
)

# After:
from led_ticker.app.factories import validate_widget_cfg
await validate_widget_cfg(
    copy.deepcopy(widget_cfg),
    session=None,
    config_dir=config_dir,
    coercion_collector=widget_warnings,
)
```

- [ ] **Step 7: Run all tests**

```bash
PYTHONPATH=tests/stubs uv run pytest -k "TestValidateWidgetCfg" -v
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: all pass. The `validate_only` parameter is gone; `validate.py` uses the explicit API.

- [ ] **Step 8: Verify `_build_widget` is under 60 lines**

```bash
grep -n "^async def _build_widget\|^def _build_widget" src/led_ticker/app/factories.py
# Then count lines to the end of the function
```

Target: under 60 lines. If over, identify which phase logic wasn't moved to a helper and extract it.

- [ ] **Step 9: Commit**

```bash
git add src/led_ticker/app/factories.py src/led_ticker/validate.py tests/
git commit -m "refactor: extract validate_widget_cfg, remove validate_only toggle from _build_widget (S1, S22 phase 4)"
```

---

### Task 5: Final self-check and verification

- [ ] **Step 1: Confirm `validate_only` is fully gone**

```bash
grep -rn "validate_only" src/ tests/ --include="*.py"
```

Expected: zero results. If any remain, investigate and remove.

- [ ] **Step 2: Confirm `_build_widget` line count**

```bash
python3 -c "
import ast, pathlib
src = pathlib.Path('src/led_ticker/app/factories.py').read_text()
tree = ast.parse(src)
for node in ast.walk(tree):
    if isinstance(node, ast.AsyncFunctionDef) and node.name == '_build_widget':
        print(f'_build_widget: lines {node.lineno}–{node.end_lineno} = {node.end_lineno - node.lineno + 1} lines')
"
```

Target: under 60 lines.

- [ ] **Step 3: Run the full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: higher count than baseline (new tests per extracted helper); zero failures.

- [ ] **Step 4: Verify docs config options drift test still passes**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_docs_config_options_drift.py -v
```

Expected: all pass (the validate path is unchanged in behavior).

- [ ] **Step 5: Final commit**

```bash
git add src/led_ticker/app/factories.py src/led_ticker/validate.py tests/
git commit -m "refactor: Large #1 complete — _build_widget decomposed, validate_only eliminated"
```

---

## Self-Review

**Spec coverage:**

| Finding | Task | Status |
|---------|------|--------|
| S1 — validate_only toggle survives Large #1 | Task 4 | ✅ |
| S22 phase 1 — extract _resolve_asset_paths | Task 1 | ✅ |
| S22 phase 2 — extract _resolve_fonts | Task 2 | ✅ |
| S22 phase 3 — extract _validate_cfg_fields | Task 3 | ✅ |
| S22 phase 4 — _build_widget as thin orchestrator | Tasks 4–5 | ✅ |

**Placeholder scan:**

- Task 4 Step 3: the `MigrationError(...)` ellipses are intentional — copy the exact text from the current `_build_widget` at execution time. The plan cannot hardcode message text that might drift.
- Task 4 Step 4 note: "Choose whichever design keeps `_build_widget` simplest" — the two options (save type before validate vs. return class from validate) are both valid; the implementer decides at execution time.

**Type consistency:**

- `_resolve_asset_paths` → `None` (mutates in-place)
- `_resolve_fonts` → `None` (mutates in-place)
- `_validate_cfg_fields` → `None` (raises on error)
- `validate_widget_cfg` → `None` (raises on error)
- `_build_widget` → `Any` (returns the constructed widget)

**Sequencing constraint:** Tasks 1–3 are fully independent and produce individually reviewable PRs. Task 4 depends on Tasks 1–3 being complete so `validate_widget_cfg` can delegate to the extracted helpers rather than duplicating them. Do NOT start Task 4 until Tasks 1–3 are merged.
