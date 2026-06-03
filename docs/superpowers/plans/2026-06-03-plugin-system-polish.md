# Plugin System Polish Round — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the deferred code-polish items (A1–A12) from the post-Phase-E sweep: make plugin transitions config-driven with clean errors, let plugin widgets host plugin animations/borders, fix `--list-fields` accuracy, tighten loader/config robustness, finish the public surface, and improve the reference plugin + tests.

**Architecture:** Mostly small, surgical changes to existing files. The one substantive change (A1) gives `TransitionConfig` an `extra: dict` for non-built-in kwargs and routes plugin (namespaced/dotted) transitions through the existing `_build_plugin_style` helper — the same generic path providers/borders/animations already use — so a plugin transition gets clean `ValueError`s and can declare its own config fields.

**Tech Stack:** Python 3.14, pytest, attrs. No `from __future__ import annotations` (forbidden in src/). Native PEP 604/585; ruff forbids quoting resolvable annotations (UP037).

**Scope:** Code polish only. The **docs deliverables (B1–B5)** — docs-site Plugins page, CLAUDE.md plugin invariants, `config.example.toml` `[plugins]` block, documenting the `../` trust boundary + `validate_config` widget-only/pre-coercion timing — are a SEPARATE subsequent plan and are OUT of scope here.

**Genuinely out of scope (per spec "Out of scope (v1)", confirmed by the sweep — do NOT touch):** cross-cutting validation rules, structural surfaces (run-modes/busy-light/layouts as plugins), sandboxing, marketplace, hot-reload, loose-font workflow changes.

---

## File Structure (what changes, by task)

- `src/led_ticker/config.py` — `TransitionConfig.extra` + `_parse_transition` collects unknown table keys (A1); `_parse_plugins_block` strips `disable` entries (A5).
- `src/led_ticker/app/factories.py` — `_build_trans_obj` routes plugin transitions through `_build_plugin_style` (A1); animation/border guards gain a declared-field opt-in (A2); `_list_widget_fields` suppresses non-injected shared rows for plugin widgets (A3).
- `src/led_ticker/validate.py` — surface plugin-transition kwarg errors at validate time (A1).
- `src/led_ticker/_plugin_loader.py` — `read_plugins_config` narrows the catch (A4); `PluginInfo.names` + `_commit` records them (A8); stale comment (A10).
- `src/led_ticker/app/cli.py` — `--config` on the `plugins`/`validate` subparsers (A6); `_format_plugins` lists contribution names (A8).
- `src/led_ticker/plugin.py` — re-export `DrawResult` (A7); stale comments (A10).
- `examples/plugins/acme/__init__.py` — `Clock.draw` renders text+font_color, `Swoosh` a real interpolation, `acme.glow` hires a real sprite (A9).
- `tests/test_plugins/` — new + extended tests throughout; `test_run_integration.py` tripwire escape-hatch comment (A11); new AST import-boundary test (A12).

---

## Pre-flight (run once before Task P1)

- [ ] **Confirm branch + baseline**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-polish
git branch --show-current      # MUST print feat/plugin-polish — abort if main
make dev                       # uv sync (pre-commit-install step may fail harmlessly because core.hooksPath is set)
make test                      # baseline green (≈2568 passed at branch point)
```

---

## Task P1: Plugin transitions — config fields + clean errors (LEAD, A1)

**Problem:** A plugin transition can't receive any config kwargs (TransitionConfig carries only built-in keys), and a plugin transition with a required `__init__` arg raises a raw `TypeError` at build time while `led-ticker validate` reports "No issues found". Fix: carry unknown transition-table keys in `TransitionConfig.extra`, build plugin (dotted-type) transitions through `_build_plugin_style` (clean `ValueError`s + custom fields), and surface those errors at validate time.

**Files:**
- Modify: `src/led_ticker/config.py`, `src/led_ticker/app/factories.py`, `src/led_ticker/validate.py`
- Test: `tests/test_plugins/test_transition_plugins.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plugins/test_transition_plugins.py`:

```python
import textwrap

import pytest

from led_ticker import _plugin_loader as L
from led_ticker.app.factories import _build_trans_obj
from led_ticker.config import TransitionConfig, _parse_transition


def _load(tmp_path, body):
    L.reset_plugins()
    (tmp_path / "plugins").mkdir(exist_ok=True)
    (tmp_path / "plugins" / "acme.py").write_text(textwrap.dedent(body))
    L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)


def test_parse_transition_collects_unknown_keys_into_extra():
    cfg = _parse_transition(
        {"type": "acme.swoosh", "speed": 3, "trail": "x"}, TransitionConfig()
    )
    assert cfg.type == "acme.swoosh"
    assert cfg.extra == {"speed": 3, "trail": "x"}


def test_builtin_transition_keys_do_not_leak_into_extra():
    cfg = _parse_transition(
        {"type": "dissolve", "duration": 0.9, "transition_color": [1, 2, 3]},
        TransitionConfig(),
    )
    assert cfg.extra == {}  # duration/transition_color are built-in, not extra


def test_plugin_transition_receives_its_config_kwargs(tmp_path):
    _load(
        tmp_path,
        """
        from led_ticker.plugin import Transition
        def register(api):
            @api.transition("swoosh")
            class Swoosh:
                min_frames = 0
                def __init__(self, speed=1):
                    self.speed = speed
                def frame_at(self, t, canvas, outgoing, incoming, **kw):
                    return canvas
        """,
    )
    try:
        obj = _build_trans_obj(
            _parse_transition({"type": "acme.swoosh", "speed": 7}, TransitionConfig())
        )
        assert obj.speed == 7
    finally:
        L.reset_plugins()


def test_plugin_transition_unknown_kwarg_raises_clean_valueerror(tmp_path):
    _load(
        tmp_path,
        """
        def register(api):
            @api.transition("swoosh")
            class Swoosh:
                min_frames = 0
                def __init__(self, speed=1):
                    self.speed = speed
                def frame_at(self, t, canvas, outgoing, incoming, **kw):
                    return canvas
        """,
    )
    try:
        with pytest.raises(ValueError, match="unknown keys"):
            _build_trans_obj(
                _parse_transition(
                    {"type": "acme.swoosh", "nope": 1}, TransitionConfig()
                )
            )
    finally:
        L.reset_plugins()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_plugins/test_transition_plugins.py -q`
Expected: FAIL — `TransitionConfig` has no `extra`; plugin transition kwargs dropped / raw TypeError.

- [ ] **Step 3: Add `extra` to `TransitionConfig`**

In `src/led_ticker/config.py`, the `TransitionConfig` dataclass (config.py:44-53) — add an `extra` field (and ensure `field` is imported; it is, used elsewhere). Replace the dataclass with:

```python
@dataclass
class TransitionConfig:
    type: str = "cut"
    duration: float = 0.5
    easing: str = "linear"
    color: tuple[int, int, int] | None = None
    colors: list[tuple[int, int, int]] | None = None
    show_pikachu: bool = True
    show_pokeball: bool = True
    transition_fps: float | None = None  # None = use run_transition default (20 fps)
    # Non-built-in keys from a plugin transition's TOML table (e.g. {type=
    # "acme.swoosh", speed=3} -> extra={"speed": 3}). Passed to the plugin
    # transition's constructor; empty for built-in transitions.
    extra: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: `_parse_transition` collects unknown keys into `extra`**

In `src/led_ticker/config.py`, replace the table-form tail of `_parse_transition` (config.py:340-354, the `color = raw.get(...)` block through the `return TransitionConfig(...)`) with:

```python
    color = raw.get("transition_color")
    if color is not None:
        color = tuple(color)
    colors = raw.get("transition_colors")
    if colors is not None:
        colors = [tuple(c) for c in colors]
    # Any table key that isn't a built-in transition knob is plugin config —
    # carry it in `extra` for the plugin transition's constructor.
    _BUILTIN_TRANSITION_KEYS = {
        "type", "duration", "easing", "transition_color", "transition_colors",
        "show_pikachu", "show_pokeball", "transition_fps",
    }
    extra = {k: v for k, v in raw.items() if k not in _BUILTIN_TRANSITION_KEYS}
    return TransitionConfig(
        type=raw.get("type", default.type),
        duration=raw.get("duration", default.duration),
        easing=raw.get("easing", default.easing),
        color=color,
        colors=colors,
        show_pikachu=raw.get("show_pikachu", default.show_pikachu),
        show_pokeball=raw.get("show_pokeball", default.show_pokeball),
        transition_fps=raw.get("transition_fps", default.transition_fps),
        extra=extra,
    )
```

- [ ] **Step 5: Route plugin transitions through `_build_plugin_style` in `_build_trans_obj`**

In `src/led_ticker/app/factories.py`, replace `_build_trans_obj` (factories.py:369-391) tail (from `cls = get_transition_class(trans_cfg.type)` onward) with:

```python
    cls = get_transition_class(trans_cfg.type)
    # Plugin transitions (namespaced, dotted type) declare their own config
    # fields and are built through the generic plugin-style path, which gives a
    # clean ValueError for unknown/missing keys (not a raw TypeError). Built-in
    # transitions keep their special-cased kwargs.
    if "." in trans_cfg.type:
        return _build_plugin_style(
            cls, trans_cfg.extra, f"transition {trans_cfg.type!r}"
        )
    kwargs: dict[str, Any] = {}
    if trans_cfg.colors is not None:
        kwargs["colors"] = trans_cfg.colors
    elif trans_cfg.color is not None:
        kwargs["color"] = trans_cfg.color
    if not trans_cfg.show_pikachu:
        kwargs["show_pikachu"] = False
    if not trans_cfg.show_pokeball:
        kwargs["show_pokeball"] = False
    return cls(**kwargs)
```

Add the import at the top of `factories.py` if not already present: `from led_ticker.app.coercion import _build_plugin_style` (check the existing imports — `coercion` helpers are already imported there; add `_build_plugin_style` to that import).

- [ ] **Step 6: Run the build-path tests**

Run: `uv run pytest tests/test_plugins/test_transition_plugins.py -q` → PASS.

- [ ] **Step 7: Surface plugin-transition kwarg errors at validate time**

READ `src/led_ticker/validate.py` — find the transition-name check (the rule that validates `[transitions]` / section `transition` types exist; search for `get_transition_class` or "transition" + "Unknown"). It currently only checks the type NAME. Add: for a transition whose type is **dotted** (a plugin transition) given as a TABLE, attempt to build it and convert a `ValueError` into a validation error/issue. The cleanest hook: where the validator already parses each transition into a `TransitionConfig`, call `_build_trans_obj(cfg)` inside a `try/except ValueError` for dotted types and append the message as a validation error (mirror how other build errors are surfaced — `_run_build_checks` collects `validate_widget_cfg` errors similarly).

Add this behavioral test to `tests/test_plugins/test_transition_plugins.py` (it goes through the real `validate_config`):

```python
from led_ticker.validate import validate_config as run_validate


async def test_validate_surfaces_plugin_transition_bad_kwarg(tmp_path):
    L.reset_plugins()
    (tmp_path / "plugins").mkdir(exist_ok=True)
    (tmp_path / "plugins" / "acme.py").write_text(
        textwrap.dedent(
            """
            def register(api):
                @api.transition("swoosh")
                class Swoosh:
                    min_frames = 0
                    def __init__(self, speed=1):
                        self.speed = speed
                    def frame_at(self, t, canvas, outgoing, incoming, **kw):
                        return canvas
            """
        )
    )
    (tmp_path / "config.toml").write_text(
        textwrap.dedent(
            """
            [display]
            rows = 16
            cols = 64
            [between_sections]
            type = "acme.swoosh"
            nope = 1

            [[playlist.section]]
            [[playlist.section.widget]]
            type = "message"
            text = "hi"
            """
        )
    )
    try:
        result = await run_validate(tmp_path / "config.toml")
        joined = " ".join(e.message for e in result.errors)
        assert "acme.swoosh" in joined and "unknown keys" in joined
        assert not result.valid
    finally:
        L.reset_plugins()
```

> If the config schema for the inter-section transition table differs (e.g. the key is `[transitions]` with a `between_sections` sub-key), adjust the TOML to whatever the parser reads for an inter-section transition — the goal is a config whose plugin transition carries a bad kwarg, validated, and the error surfaces. Read `config.py`'s transition parsing + `validate.py` to get the exact shape. If a per-section `transition = {type="acme.swoosh", nope=1}` is the simpler hook, use that instead.

- [ ] **Step 8: Make the validate test pass + regression**

Run: `uv run pytest tests/test_plugins/test_transition_plugins.py -q` → all PASS.
Run: `uv run pytest tests/ -q -k "transition or validate"` → PASS (built-in transitions unaffected — `extra` is empty for them, and the dotted-type branch never triggers).

- [ ] **Step 9: Lint + commit**

Run: `uv run ruff check src/led_ticker/config.py src/led_ticker/app/factories.py src/led_ticker/validate.py` → clean.

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-polish add src/led_ticker/config.py src/led_ticker/app/factories.py src/led_ticker/validate.py tests/test_plugins/test_transition_plugins.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-polish -c core.hooksPath=/dev/null commit -m "fix(plugins): plugin transitions take config kwargs via _build_plugin_style; clean errors at validate"
```

---

## Task P2: Plugin widgets can host plugin animation/border (A2)

**Problem:** The `animation`/`border` guards in `validate_widget_cfg` reject those knobs on any widget type not in a hardcoded built-in allowlist — so a plugin widget can't use a plugin animation/border. Open it via a declared-field opt-in: a widget that declares an `animation` (resp. `border`) attrs field is eligible.

**Files:**
- Modify: `src/led_ticker/app/factories.py`
- Test: `tests/test_plugins/test_animation_plugins.py` and `tests/test_plugins/test_border_plugins.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plugins/test_animation_plugins.py` (read its imports/style first; it already loads plugins):

```python
async def test_plugin_widget_declaring_animation_field_can_host_animation(tmp_path):
    import textwrap

    from led_ticker import _plugin_loader as L
    from led_ticker.app.factories import validate_widget_cfg

    L.reset_plugins()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "acme.py").write_text(
        textwrap.dedent(
            """
            import attrs
            from led_ticker.plugin import AnimationFrame
            def register(api):
                @api.animation("scramble")
                class Scramble:
                    def frame_for(self, frame, full_text, canvas_width, text_width):
                        return AnimationFrame(visible_text=full_text)
                @api.widget("banner")
                @attrs.define
                class Banner:
                    text: str = ""
                    animation: object = None
                    def draw(self, canvas, cursor_pos=0, **kw):
                        return canvas, cursor_pos
            """
        )
    )
    try:
        L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        cfg = {"type": "acme.banner", "animation": {"style": "acme.scramble"}}
        await validate_widget_cfg(cfg, session=None)  # must NOT raise
    finally:
        L.reset_plugins()


async def test_plugin_widget_without_animation_field_rejects_animation(tmp_path):
    import textwrap

    import pytest

    from led_ticker import _plugin_loader as L
    from led_ticker.app.factories import validate_widget_cfg

    L.reset_plugins()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "acme.py").write_text(
        textwrap.dedent(
            """
            import attrs
            def register(api):
                @api.widget("plain")
                @attrs.define
                class Plain:
                    text: str = ""
                    def draw(self, canvas, cursor_pos=0, **kw):
                        return canvas, cursor_pos
            """
        )
    )
    try:
        L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        with pytest.raises(ValueError, match="animation is only valid"):
            await validate_widget_cfg(
                {"type": "acme.plain", "animation": {"style": "x"}}, session=None
            )
    finally:
        L.reset_plugins()
```

Add the symmetric two tests to `tests/test_plugins/test_border_plugins.py` (replace `animation`→`border`, `acme.scramble`→`acme.neon` registering a `BorderEffectBase` with `frame_invariant=False` + `paint(self, canvas, frame_count)`, and the reject-message `match="border is only valid"`).

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_plugins/test_animation_plugins.py tests/test_plugins/test_border_plugins.py -q -k "host or reject"`
Expected: FAIL — plugin widget with the field is still rejected by the allowlist.

- [ ] **Step 3: Add a declared-field helper + open the guards**

In `src/led_ticker/app/factories.py`, add a module-level helper (near the other widget helpers):

```python
def _widget_declares_field(cls: type, name: str) -> bool:
    """True if an (attrs) widget class declares a config field `name` — used to
    let a plugin widget opt into the `animation`/`border` knobs by declaring the
    field, without hardcoding plugin type names."""
    return any(a.name == name for a in getattr(cls, "__attrs_attrs__", ()))
```

In the animation guard (factories.py:734-738), change the condition so a widget declaring an `animation` field is allowed. `cls` is in scope (resolved earlier as `cls = get_widget_class(widget_type)`). Replace:

```python
    if animation_value is not None and widget_type not in (
        "message",
        "gif",
        "image",
    ):
```

with:

```python
    if (
        animation_value is not None
        and widget_type not in ("message", "gif", "image")
        and not _widget_declares_field(cls, "animation")
    ):
```

In the border guard (factories.py:756-762), replace:

```python
    if border_value is not None and widget_type not in (
        "message",
        "countdown",
        "two_row",
        "gif",
        "image",
    ):
```

with:

```python
    if (
        border_value is not None
        and widget_type not in ("message", "countdown", "two_row", "gif", "image")
        and not _widget_declares_field(cls, "border")
    ):
```

> Confirm `cls` is the resolved widget class in scope at both guard points (read the lines above — `validate_widget_cfg` resolves `cls = get_widget_class(widget_type)` near the top). If the guard runs before `cls` is available, resolve it locally with `get_widget_class(widget_type)`.

- [ ] **Step 4: Run + regression**

Run: `uv run pytest tests/test_plugins/test_animation_plugins.py tests/test_plugins/test_border_plugins.py -q` → PASS.
Run: `uv run pytest tests/ -q -k "widget or animation or border"` → PASS (built-in allowlist still works; the opt-in is additive).

- [ ] **Step 5: Lint + commit**

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-polish add src/led_ticker/app/factories.py tests/test_plugins/test_animation_plugins.py tests/test_plugins/test_border_plugins.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-polish -c core.hooksPath=/dev/null commit -m "fix(plugins): plugin widgets opt into animation/border by declaring the field"
```

---

## Task P3: `--list-fields` accuracy for plugin widgets (A3)

**Problem:** `_list_widget_fields` appends a "Shared fields" block including the `applicable_types=None` rows (`type`, `text`, `font`, `font_size`, `font_threshold`) for **every** type — but those font knobs are NOT injected into arbitrary plugin widgets, so they show fields the widget will reject. Suppress the non-injected shared rows for plugin (dotted) widget types; keep `type`.

**Files:**
- Modify: `src/led_ticker/app/factories.py`
- Test: `tests/test_plugins/test_cli_plugins.py` (extend, or `test_list_fields...`)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_plugins/test_cli_plugins.py`:

```python
def test_list_fields_plugin_widget_hides_uninjected_shared_fields(tmp_path):
    import textwrap

    from led_ticker import _plugin_loader as L
    from led_ticker.app.factories import _list_widget_fields

    L.reset_plugins()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "acme.py").write_text(
        textwrap.dedent(
            """
            import attrs
            def register(api):
                @api.widget("clock")
                @attrs.define
                class Clock:
                    text: str = "12:00"
                    def draw(self, canvas, cursor_pos=0, **kw):
                        return canvas, cursor_pos
            """
        )
    )
    try:
        L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        out = _list_widget_fields("acme.clock")
        # The widget's own field is shown:
        assert "text" in out
        # Built-in font knobs that are NOT injected into a plugin widget must
        # NOT be advertised (they'd be rejected as unknown fields):
        assert "font_size" not in out
        assert "font_threshold" not in out
    finally:
        L.reset_plugins()
```

> `text` here IS the widget's own declared attrs field (shown in the widget-level section), so `"text" in out` holds regardless; the load-bearing assertions are that `font_size`/`font_threshold` (uninjected shared rows) are gone. Confirm a built-in widget (`_list_widget_fields("message")`) STILL shows its shared rows (next step's regression).

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_plugins/test_cli_plugins.py -q -k "hides_uninjected"`
Expected: FAIL — `font_size`/`font_threshold` shown for `acme.clock`.

- [ ] **Step 3: Suppress non-injected shared rows for plugin widgets**

In `src/led_ticker/app/factories.py`, in the `_list_widget_fields` dispatch-rows loop (factories.py:1180-1203), add a guard so a plugin (dotted) widget type only shows shared rows it actually accepts. The `applicable_types is None` rows (`type`/`text`/`font`/`font_size`/`font_threshold`) are built-in conveniences not injected into plugin widgets — show only `type` for a plugin widget. Change the loop body's continue-conditions; replace:

```python
    for name, applicable_types in _DISPATCH_APPLICABLE_TYPES.items():
        if applicable_types is not None and widget_type not in applicable_types:
            continue
        if name in widget_field_names:
            continue  # already shown above
```

with:

```python
    is_plugin_widget = "." in widget_type
    for name, applicable_types in _DISPATCH_APPLICABLE_TYPES.items():
        if applicable_types is not None and widget_type not in applicable_types:
            continue
        # Plugin widgets don't auto-receive the built-in font knobs (the
        # `applicable_types is None` rows other than `type`); advertising them
        # would list fields the widget rejects. Only `type` is universal.
        if is_plugin_widget and applicable_types is None and name != "type":
            continue
        if name in widget_field_names:
            continue  # already shown above
```

- [ ] **Step 4: Run + regression**

Run: `uv run pytest tests/test_plugins/test_cli_plugins.py -q` → PASS.
Run: `uv run pytest tests/ -q -k "list_fields or golden"` → PASS (built-in widgets' `--list-fields` output is unchanged — there is a golden test; confirm it stays green).

- [ ] **Step 5: Lint + commit**

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-polish add src/led_ticker/app/factories.py tests/test_plugins/test_cli_plugins.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-polish -c core.hooksPath=/dev/null commit -m "fix(plugins): --list-fields hides uninjected shared fields for plugin widgets"
```

---

## Task P4: Loader/config robustness (A4 + A5)

**Files:**
- Modify: `src/led_ticker/_plugin_loader.py` (A4), `src/led_ticker/config.py` (A5)
- Test: `tests/test_plugins/test_loader_config.py`, `tests/test_plugins/test_plugins_config.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plugins/test_loader_config.py`:

```python
import pytest as _pytest


def test_read_plugins_config_propagates_toml_syntax_error(tmp_path):
    # A broken-TOML config must NOT silently fall back to defaults — let the
    # decode error propagate so the CLI surfaces it (instead of "No plugins").
    p = tmp_path / "config.toml"
    p.write_text("[[[ not valid toml")
    with _pytest.raises(Exception):  # tomllib.TOMLDecodeError
        L.read_plugins_config(p)


def test_read_plugins_config_still_defaults_on_missing_file(tmp_path):
    pc = L.read_plugins_config(tmp_path / "nope.toml")
    assert pc.enabled is True and pc.dir == "plugins"
```

Append to `tests/test_plugins/test_plugins_config.py`:

```python
def test_disable_entries_are_whitespace_stripped():
    cfg = _parse_plugins_block({"plugins": {"disable": ["  acme  ", "x"]}})
    assert cfg.disable == ["acme", "x"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_plugins/test_loader_config.py tests/test_plugins/test_plugins_config.py -q -k "toml_syntax or stripped"`
Expected: FAIL — `read_plugins_config` swallows the TOML error; `disable` not stripped.

- [ ] **Step 3: Narrow the `read_plugins_config` catch**

In `src/led_ticker/_plugin_loader.py`, in `read_plugins_config` (_plugin_loader.py:371-386), narrow the `except Exception` to `FileNotFoundError` so a TOML syntax error propagates (the CLI's existing `except (FileNotFoundError, ValueError)` reports it; for `validate`/`run`, `load_config` would also surface it). Replace:

```python
    try:
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)
    except Exception:
        return PluginsConfig()
    return _parse_plugins_block(raw)
```

with:

```python
    try:
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError:
        return PluginsConfig()
    return _parse_plugins_block(raw)
```

Also update the docstring's first sentence to say "Returns defaults only if the file is missing; a TOML syntax error or a structural ``[plugins]`` error propagates so the caller can report it."

> NOTE: a `tomllib.TOMLDecodeError` is now raised. The CLI `plugins` handler catches `(FileNotFoundError, ValueError)` — `TOMLDecodeError` is a `ValueError` subclass, so it IS caught and printed cleanly. Confirm `issubclass(tomllib.TOMLDecodeError, ValueError)` (it is in CPython). The `--list-fields` and `validate` handlers similarly catch `ValueError`. Verify the CLI still exits cleanly (not a traceback) on a broken-TOML config.

- [ ] **Step 4: Strip `disable` entries**

In `src/led_ticker/config.py`, in `_parse_plugins_block` (config.py:172-207), after the `disable` list/str-type validation passes (the `if not isinstance(cfg.disable, list) ...` check), add:

```python
    cfg.disable = [n.strip() for n in cfg.disable]
```

(Place it just before `return cfg`.)

- [ ] **Step 5: Run + regression**

Run: `uv run pytest tests/test_plugins/test_loader_config.py tests/test_plugins/test_plugins_config.py -q` → PASS.
Run: `uv run pytest tests/ -q -k "plugin or config or cli"` → PASS.
Manual: a broken-TOML config through the CLI prints a clean error, not a traceback:
```bash
printf '[[[ bad\n' > /tmp/pp_bad.toml
uv run led-ticker --config /tmp/pp_bad.toml plugins; echo "exit: $status"
```
Expected: a clean one-line TOML error + non-zero exit (no Python traceback).

- [ ] **Step 6: Lint + commit**

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-polish add src/led_ticker/_plugin_loader.py src/led_ticker/config.py tests/test_plugins/test_loader_config.py tests/test_plugins/test_plugins_config.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-polish -c core.hooksPath=/dev/null commit -m "fix(plugins): surface broken-TOML on plugins CLI; strip plugins.disable entries"
```

---

## Task P5: CLI affordances — `--config` ordering + `plugins` lists names (A6 + A8)

**Files:**
- Modify: `src/led_ticker/app/cli.py`, `src/led_ticker/_plugin_loader.py`
- Test: `tests/test_plugins/test_cli_plugins.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plugins/test_cli_plugins.py`:

```python
def test_format_plugins_lists_contribution_names():
    from led_ticker._plugin_loader import LoadedPlugins, PluginInfo

    info = PluginInfo(
        namespace="acme",
        source="/p/acme.py",
        counts={"widgets": 1, "transitions": 1},
        names={"widgets": ["acme.clock"], "transitions": ["acme.swoosh"]},
    )
    out = _format_plugins(LoadedPlugins(loaded=[info], failed=[]))
    assert "acme.clock" in out
    assert "acme.swoosh" in out


def test_plugins_subcommand_accepts_config_after_subcommand(tmp_path):
    import subprocess
    import sys

    (tmp_path / "config.toml").write_text("[display]\nrows=16\ncols=64\n")
    proc = subprocess.run(
        ["led-ticker", "plugins", "--config", str(tmp_path / "config.toml")],
        capture_output=True, text=True,
    )
    # --config after the subcommand should be accepted (exit 0), not
    # "unrecognized arguments".
    assert proc.returncode == 0, proc.stderr
    assert "unrecognized arguments" not in proc.stderr
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_plugins/test_cli_plugins.py -q -k "names or config_after"`
Expected: FAIL — `PluginInfo` has no `names`; `--config` after subcommand unrecognized.

- [ ] **Step 3: Add `names` to `PluginInfo` + record in `_commit`**

In `src/led_ticker/_plugin_loader.py`, extend `PluginInfo` (_plugin_loader.py:43-47):

```python
@dataclass
class PluginInfo:
    namespace: str
    source: str
    counts: dict[str, int] = field(default_factory=dict)
    # Per-surface qualified contribution names (e.g. {"widgets": ["acme.clock"]})
    # — what an operator references in TOML.
    names: dict[str, list[str]] = field(default_factory=dict)
```

In `_commit`, where counts are recorded (_plugin_loader.py:107-114), add the names alongside:

```python
        for name, obj in buf.items():
            registry[name] = obj
        if buf:
            info.counts[surface] = len(buf)
            info.names[surface] = sorted(buf)
```

- [ ] **Step 4: `_format_plugins` lists names**

In `src/led_ticker/app/cli.py`, change `_format_plugins` (cli.py:28-45) so the per-plugin line shows contribution NAMES (falling back to counts/`(hooks only)`):

```python
def _format_plugins(result) -> str:
    """Human-readable summary of loaded + failed plugins for `led-ticker plugins`."""
    lines: list[str] = []
    if not result.loaded and not result.failed:
        return "No plugins found."
    if result.loaded:
        lines.append(f"Loaded {len(result.loaded)} plugin(s):")
        for info in result.loaded:
            lines.append(f"  {info.namespace}  [{info.source}]")
            names = getattr(info, "names", {}) or {}
            if names:
                for surface in sorted(names):
                    lines.append(f"      {surface}: {', '.join(names[surface])}")
            elif info.counts:
                contrib = ", ".join(f"{k}: {v}" for k, v in sorted(info.counts.items()))
                lines.append(f"      {contrib}")
            else:
                lines.append("      (hooks only)")
    if result.failed:
        lines.append(f"Failed {len(result.failed)} plugin(s):")
        for ns, err in result.failed:
            lines.append(f"  {ns}: {err}")
    return "\n".join(lines)
```

- [ ] **Step 5: Add `--config` to the `plugins` and `validate` subparsers**

In `src/led_ticker/app/cli.py`, the `plugins` subparser (cli.py:113-117) takes no args. Add a `--config` option to it (and to the `validate` subparser) so `--config` works after the subcommand too. Since `--config` already exists on the top-level parser (cli.py:54-60), add it to the subparsers as well; argparse will use whichever is provided. Replace the `plugins` subparser registration with:

```python
    # `plugins` subcommand
    plugins_parser = subparsers.add_parser(
        "plugins",
        help="List loaded plugins (and any that failed) for the config",
    )
    plugins_parser.add_argument(
        "--config", "-c", type=Path, default=None,
        help="Path to TOML config file (defaults to the top-level --config)",
    )
```

And on the `validate` subparser (find `val_parser = subparsers.add_parser("validate", ...)`), add the same `--config` option.

Then where the handlers use `args.config`: a subcommand-level `--config` lands in `args.config` too (argparse merges same-dest options — but the subparser default `None` would OVERRIDE the top-level default). To avoid clobbering, give the subparser option `default=argparse.SUPPRESS` instead of `None` so it only sets `args.config` when actually provided. Use:

```python
    plugins_parser.add_argument(
        "--config", "-c", type=Path, default=argparse.SUPPRESS,
        help="Path to TOML config file (defaults to the top-level --config)",
    )
```

> IMPORTANT: argparse with the SAME dest on parent + subparser can clobber — the subparser's value (or its default) wins when the subcommand runs. Using `default=argparse.SUPPRESS` means the attribute is only set when the user passes it, preserving the top-level value otherwise. VERIFY both orderings work: `led-ticker --config X plugins` AND `led-ticker plugins --config X` both load from X. If SUPPRESS interacts badly, an alternative is a shared parent parser (`argparse.ArgumentParser(add_help=False)` with `--config`, passed as `parents=[...]` to each subparser) — use whichever cleanly makes both orderings work, and keep the test from Step 1 passing.

- [ ] **Step 6: Run + regression**

Run: `uv run pytest tests/test_plugins/test_cli_plugins.py -q` → PASS (incl. both new tests).
Run: `uv run pytest tests/ -q -k "cli or plugins"` → PASS.
Manual: confirm both orderings:
```bash
printf '[display]\nrows=16\ncols=64\n' > /tmp/pp_ord.toml
uv run led-ticker --config /tmp/pp_ord.toml plugins
uv run led-ticker plugins --config /tmp/pp_ord.toml
```
Both print "No plugins found." (exit 0).

- [ ] **Step 7: Lint + commit**

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-polish add src/led_ticker/app/cli.py src/led_ticker/_plugin_loader.py tests/test_plugins/test_cli_plugins.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-polish -c core.hooksPath=/dev/null commit -m "feat(plugins): plugins CLI lists contribution names; --config works after subcommand"
```

---

## Task P6: Public surface + cleanups (A7 + A10 + A11 + A12)

**Files:**
- Modify: `src/led_ticker/plugin.py` (A7, A10), `src/led_ticker/_plugin_loader.py` (A10), `tests/test_plugins/test_run_integration.py` (A11), `tests/test_plugins/test_plugin_api.py` (A7)
- Create: `tests/test_plugins/test_public_surface_boundary.py` (A12)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plugins/test_plugin_api.py`:

```python
def test_draw_result_is_exported():
    import led_ticker.plugin as p

    assert hasattr(p, "DrawResult")
    assert "DrawResult" in p.__all__
```

Create `tests/test_plugins/test_public_surface_boundary.py` (A12 — the spec's "plugins never import internal modules" tripwire):

```python
import ast
from pathlib import Path

EXAMPLE = (
    Path(__file__).resolve().parents[2]
    / "examples" / "plugins" / "acme" / "__init__.py"
)


def test_reference_plugin_imports_only_public_led_ticker():
    tree = ast.parse(EXAMPLE.read_text())
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "led_ticker"
        ):
            if node.module != "led_ticker.plugin":
                bad.append(node.module)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("led_ticker") and alias.name != "led_ticker.plugin":
                    bad.append(alias.name)
    assert not bad, f"reference plugin imports non-public led_ticker modules: {bad}"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_plugins/test_plugin_api.py tests/test_plugins/test_public_surface_boundary.py -q -k "draw_result or imports_only"`
Expected: `draw_result` FAILS (not exported); the boundary test PASSES already (the reference plugin imports only `led_ticker.plugin` — this test pins it going forward).

- [ ] **Step 3: Re-export `DrawResult`**

In `src/led_ticker/plugin.py`, add `DrawResult` to the `_types` import (plugin.py:22) → `from led_ticker._types import Canvas, Color, DrawResult, Font, PixelData`, and add `"DrawResult"` to `__all__` (among the type names, e.g. after `"Color"`).

- [ ] **Step 4: Rewrite stale "later phases / Phase E" comments (A10)**

- `src/led_ticker/plugin.py:62` — replace `# (registry surfaces + lifecycle hooks complete; Phase E adds config/CLI/docs.)` with `# Public plugin surface: registry contributions + lifecycle hooks.`
- `src/led_ticker/plugin.py:111` — replace `# is a single generic loop as later phases add surfaces.` with `# is a single generic loop over all registry surfaces.`
- `src/led_ticker/_plugin_loader.py:95` — replace `# committed here (hook surfaces are collected separately in later phases).` with `# committed here (hook surfaces are collected separately — see _load_one).`

- [ ] **Step 5: Annotate the brittle tripwire (A11)**

In `tests/test_plugins/test_run_integration.py`, `test_run_wires_lifecycle_hooks` — add an escape-hatch comment matching the emoji tripwire's, just before the `assert "_run_startup_hooks" in src` line:

```python
    # If this fails after a legitimate refactor of run(), delete these source
    # assertions — test_loaded_plugin_hooks_are_consumable_by_run exercises the
    # real runners and is the behavioral guard.
```

- [ ] **Step 6: Run + commit**

Run: `uv run pytest tests/test_plugins/ -q` → PASS.
Run: `uv run python -c "import led_ticker.plugin"` → clean; `uv run ruff check src/led_ticker/plugin.py` → clean.

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-polish add src/led_ticker/plugin.py src/led_ticker/_plugin_loader.py tests/test_plugins/test_plugin_api.py tests/test_plugins/test_run_integration.py tests/test_plugins/test_public_surface_boundary.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-polish -c core.hooksPath=/dev/null commit -m "chore(plugins): export DrawResult; AST import-boundary test; tidy stale comments + tripwire"
```

---

## Task P7: Reference plugin teaching quality (A9)

**Problem:** The reference plugin's `Clock.draw` paints nothing (doesn't render `text` or use `font_color`); `Swoosh.frame_at` is a no-op; `acme.glow` hi-res is a single pixel. As the canonical "copy me" sample, it should model real behavior.

**Files:**
- Modify: `examples/plugins/acme/__init__.py`
- Test: `tests/test_plugins/test_example_plugin.py` (extend)

- [ ] **Step 1: Make `Clock.draw` render text (+ honor font_color)**

In `examples/plugins/acme/__init__.py`, the `Clock.draw` currently returns the canvas unchanged. Replace its body to actually render its `text` via the public `draw_text` helper, honoring `font_color` when it's a provider. Import `draw_text`, `resolve_font`, `make_color` from `led_ticker.plugin` (extend the existing import). New `draw`:

```python
        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
            font = resolve_font("6x12")
            color = make_color(255, 255, 255)
            # If a color provider was injected via the `font_color` field, use
            # its first color; otherwise default to white.
            provider = self.font_color
            if provider is not None and hasattr(provider, "color_for"):
                color = provider.color_for(0, 0, len(self.text))
            return canvas, draw_text(canvas, font, self.text, cursor_pos, 10, color)
```

> Confirm the Widget protocol's `draw` return shape (`tuple[Canvas, int]` = `DrawResult`). The original returned `(canvas, cursor_pos)`; here we return `(canvas, <new cursor x>)` from `draw_text`. Read `widget.py` Widget protocol to confirm the second element is the post-draw cursor — adjust if the protocol expects something else.

- [ ] **Step 2: Give `Swoosh.frame_at` a minimal real interpolation**

Replace `Swoosh.frame_at` so it does a real (if simple) thing — e.g. return the incoming canvas once past the midpoint, else the outgoing (a hard wipe at t=0.5), demonstrating the `t` parameter:

```python
        def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
            # Minimal real transition: show outgoing in the first half, incoming
            # in the second. A real transition would composite/slide per `t`.
            return incoming if t >= 0.5 else outgoing
```

> Confirm the `Transition.frame_at` contract (params + return) from `transitions/__init__.py` — return the frame canvas. Adjust if `outgoing`/`incoming` aren't canvases (they should be).

- [ ] **Step 3: Make `acme.glow` hi-res a real multi-pixel sprite**

Replace the single-pixel `acme.glow` hires registration with a real small sprite (a filled diamond/box), matching the spirit of its 8×8 low-res pair:

```python
    api.hires_emoji(
        "glow",
        HiResEmoji(
            pixels=tuple(
                (x, y, 255, 200, 0)
                for x in range(16)
                for y in range(16)
                if 4 <= x < 12 and 4 <= y < 12
            ),
            physical_size=16,
        ),
    )
```

- [ ] **Step 4: Extend the example test to assert the widget renders**

Append to `tests/test_plugins/test_example_plugin.py`:

```python
def test_example_clock_actually_renders_text():
    from led_ticker.widgets import get_widget_class

    L.reset_plugins()
    try:
        L.load_plugins(EXAMPLES, entry_points_enabled=False)
        cls = get_widget_class("acme.clock")
        widget = cls(text="hi")
        # Build a real stub canvas the way other render tests do (grep the
        # suite for the construction) and call draw; assert the cursor advanced.
        canvas = _make_stub_canvas(width=64, height=16)  # see note
        _, end_x = widget.draw(canvas, cursor_pos=0)
        assert end_x > 0
    finally:
        L.reset_plugins()
```

> Replace `_make_stub_canvas(...)` with the real stub-canvas construction the existing render tests use (grep `tests/` for `CreateFrameCanvas`/`_StubCanvas`/`RGBMatrixOptions`). The assertion (cursor advanced after drawing "hi") proves `draw` renders rather than no-ops.

- [ ] **Step 5: Run + verify no warning + commit**

Run: `uv run pytest tests/test_plugins/test_example_plugin.py -q` → PASS.
Run: `uv run ruff check examples/plugins/acme/__init__.py` → clean.
Confirm the example still loads with no unpaired-hires warning (glow is still paired low+hi-res).

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-polish add examples/plugins/acme/__init__.py tests/test_plugins/test_example_plugin.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-polish -c core.hooksPath=/dev/null commit -m "docs(plugins): reference plugin renders real text/transition/hires sprite"
```

---

## Task P8: Final verification + whole-phase review

**Files:** none (verification only)

- [ ] **Step 1: Lint** — `make lint` → `All checks passed!` (also `uv run ruff check examples/`).
- [ ] **Step 2: Typecheck** — `make typecheck` → `0 errors`.
- [ ] **Step 3: Full suite + coverage** — `make test` → all green, coverage ≥ floor (≈95%).
- [ ] **Step 4: CLI smokes** — with a tmp config + the reference plugin copied to its `plugins/` dir: `led-ticker --config X plugins` lists contribution NAMES (`acme.clock`, `acme.swoosh`, …); `led-ticker plugins --config X` (config after subcommand) works; `led-ticker --config X validate --list-fields acme.clock` shows the widget's fields WITHOUT the uninjected font knobs; a `transition={type="acme.swoosh", nope=1}` config reports a clean validate error.
- [ ] **Step 5: Report** — summarize A1–A12 done, confirm the docs deliverables (B1–B5) are still pending as the next plan, and hand back for the whole-phase review + `finishing-a-development-branch`.

---

## Self-Review

**Coverage of the sweep's (A) items:** A1→P1, A2→P2, A3→P3, A4+A5→P4, A6+A8→P5, A7+A10+A11+A12→P6, A9→P7. All twelve code-polish items are assigned. Docs (B1–B5) explicitly deferred to the next plan.

**Placeholder scan:** Concrete code for every change. A handful of steps say "read X to confirm the exact surrounding code / stub-canvas construction" (validate.py transition hook in P1; `cls`-in-scope in P2; the stub canvas in P7) — these are localized verification directives with a behavioral test that pins the outcome, not placeholders. The riskiest (P1 validate surfacing) has an explicit fallback (per-section transition form).

**Type/name consistency:** `TransitionConfig.extra: dict[str, Any]` (P1) is read by `_build_trans_obj` via `_build_plugin_style(cls, trans_cfg.extra, label)` (P1). `_widget_declares_field(cls, name)` (P2) is used at both guard sites. `PluginInfo.names: dict[str, list[str]]` (P5) is written in `_commit` and read by `_format_plugins`. `DrawResult` re-export (P6) matches `_types.DrawResult = tuple[Canvas, int]`. `is_plugin_widget = "." in widget_type` (P3) matches the namespacing convention used in P1 (`"." in trans_cfg.type`) and elsewhere.

**Risk notes:** P1 is the largest (transition build + validate); built-in transitions are unaffected because `extra` is empty and the dotted-type branch never fires for them — the regression run (`-k "transition or validate"`) is the guard. P3 touches a golden-tested function — the regression run includes the golden test. P5's argparse `--config`-on-subparser has a documented SUPPRESS-vs-parent-parser fallback.
