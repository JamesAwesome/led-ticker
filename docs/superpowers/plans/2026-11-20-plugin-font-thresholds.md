# Plugin-declared font thresholds (core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a plugin register a hi-res font with its own default `font_threshold`, and make core treat plugin fonts as hi-res everywhere it treats bundled ones that way.

**Architecture:** `api.font` grows an optional `threshold` kwarg that lands in a new `font_thresholds` buffer; the loader commits it into `hires_loader._PLUGIN_THRESHOLDS` through the same `_REGISTRY_MAP` path as `_PLUGIN_FONTS`, so reset and collision handling come for free. `default_threshold` consults that dict first, and `list_available_hires_fonts` adds the plugin font names so the one hi-res-name predicate (`coercion._is_hires_font_name`) sees them. Additive plugin API change: `API_VERSION` `(1, 2)` → `(1, 3)`.

**Tech Stack:** Python 3.14, pytest, ruff, pyright (pre-push only, `uv run pyright`).

**Spec:** `docs/superpowers/specs/2026-11-20-flair-display-fonts-design.md` (section "Core"). The flair half of that spec gets its own plan after this ships and is released.

## Global Constraints

- Work in a worktree, never the main checkout: `git worktree add ../led-ticker-wt-font-thr -b feat/plugin-font-thresholds main`. Verify `pwd` and branch before any git op.
- Threshold rule is the one `resolve_font` already uses: `int`, not `bool`, 0 ≤ t ≤ 255; else `ValueError`.
- Membership checks for threshold lookup, never truthiness (0 is legal).
- No `from __future__ import annotations`.
- Byte-identical for every existing config: no plugin registers a font today.
- `API_VERSION` tests pin `>=`, never `==`.
- `gh pr create` and merge need James's go; PR opens as draft. Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- `make test` and `make lint` green before each commit; `uv run pyright` before push.

## Review Focus

1. `threshold=0` registers and is honoured (not dropped as falsy). Pinned in Task 1 (`test_default_threshold_prefers_plugin_value` uses 0 in a parametrize).
2. `threshold=45.0` (float) and `threshold=True` are rejected at registration, not at first render. Pinned in Task 2.
3. A plugin font registered WITHOUT a threshold keeps 128 and appears in the hi-res listing. Pinned in Task 1 and Task 2.
4. Explicit `font_threshold = 45` equal to the plugin default beside an unset sibling: rule 2 stays quiet (both are "on default"). Pinned in Task 3.
5. A plugin hi-res font on a two-row `image` (`bottom_text` set) is refused at config-load the way `Inter-Bold` is. Pinned in Task 2 (factory) and Task 3 (validate rule 71).

---

### Task 0: Worktree and spec commit

**Files:**
- Move: `docs/superpowers/specs/2026-11-20-flair-display-fonts-design.md` (untracked in the main checkout) into the worktree at the same path.

- [ ] **Step 1: Create the worktree**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git worktree add ../led-ticker-wt-font-thr -b feat/plugin-font-thresholds main
mv docs/superpowers/specs/2026-11-20-flair-display-fonts-design.md ../led-ticker-wt-font-thr/docs/superpowers/specs/
cp docs/superpowers/plans/2026-11-20-plugin-font-thresholds.md ../led-ticker-wt-font-thr/docs/superpowers/plans/
cd ../led-ticker-wt-font-thr && pwd && git branch --show-current && make dev
```
Expected: `feat/plugin-font-thresholds`; `uv sync` completes.

- [ ] **Step 2: Commit spec + plan**

```bash
git add docs/superpowers/specs/2026-11-20-flair-display-fonts-design.md docs/superpowers/plans/2026-11-20-plugin-font-thresholds.md
git commit -m "docs(specs): flair display fonts design + core plan for plugin font thresholds"
```

---

### Task 1: Loader — `_PLUGIN_THRESHOLDS`, `default_threshold`, hi-res listing

**Files:**
- Modify: `src/led_ticker/fonts/hires_loader.py` (`DEFAULT_THRESHOLDS` block ~line 44, `default_threshold` ~47, `_PLUGIN_FONTS` ~266, `list_available_hires_fonts` ~290)
- Modify: `src/led_ticker/_plugin_loader.py` (`_REGISTRY_MAP` ~line 36, `_commit` ~112)
- Test: `tests/test_plugins/test_font_plugins.py`

**Interfaces:**
- Produces: `hires_loader._PLUGIN_THRESHOLDS: dict[str, int]` (dotted name → threshold); `default_threshold(name) -> int` returns the plugin value when `name in _PLUGIN_THRESHOLDS`; `list_available_hires_fonts()` includes every key of `_PLUGIN_FONTS`; `_REGISTRY_MAP["font_thresholds"] is _PLUGIN_THRESHOLDS`; `_commit` does not add `font_thresholds` to `PluginInfo.counts` / `.names`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plugins/test_font_plugins.py` (same `try/finally` pop + `L.reset_plugins()` cleanup style as the existing tests):

```python
@pytest.mark.parametrize("value", [0, 45, 255])
def test_default_threshold_prefers_plugin_value(value):
    hires_loader._PLUGIN_THRESHOLDS["acme.Brand"] = value
    try:
        assert hires_loader.default_threshold("acme.Brand") == value
    finally:
        hires_loader._PLUGIN_THRESHOLDS.pop("acme.Brand", None)


def test_default_threshold_without_plugin_value_keeps_loader_default():
    assert hires_loader.default_threshold("acme.Unlisted") == hires_loader.THRESHOLD
    assert hires_loader.default_threshold("Inter-Regular") == 80  # core table still wins for core names


def test_plugin_font_names_appear_in_hires_listing(tmp_path):
    hires_loader._PLUGIN_FONTS["acme.Brand"] = tmp_path / "Brand.ttf"  # file need not exist
    try:
        assert "acme.Brand" in list_available_hires_fonts()
        from led_ticker.app.coercion import _is_hires_font_name
        assert _is_hires_font_name("acme.Brand")
    finally:
        hires_loader._PLUGIN_FONTS.pop("acme.Brand", None)


def test_reset_plugins_clears_plugin_thresholds():
    hires_loader._PLUGIN_THRESHOLDS["acme.Brand"] = 45
    L.reset_plugins()
    assert "acme.Brand" not in hires_loader._PLUGIN_THRESHOLDS


def test_registry_map_routes_font_thresholds_and_commit_does_not_count_them():
    assert L._REGISTRY_MAP["font_thresholds"] is hires_loader._PLUGIN_THRESHOLDS
    api = L.PluginAPI("acme", root=None)
    api._buffers["font_thresholds"]["acme.Brand"] = 45
    info = L.PluginInfo(namespace="acme", source="test")
    try:
        L._commit(api, info)
        assert hires_loader._PLUGIN_THRESHOLDS["acme.Brand"] == 45
        assert "font_thresholds" not in info.counts
    finally:
        L.reset_plugins()
```

Add `from led_ticker.fonts import list_available_hires_fonts` to the imports.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_plugins/test_font_plugins.py -v`
Expected: the five new tests FAIL (`AttributeError: _PLUGIN_THRESHOLDS`, `KeyError: 'font_thresholds'`, listing assertion).

- [ ] **Step 3: Implement in `hires_loader.py`**

- `_PLUGIN_THRESHOLDS: dict[str, int] = {}` beside `_PLUGIN_FONTS`, with a comment mirroring its neighbour (populated by the loader's commit, cleared by `reset_plugins`).
- `default_threshold(name)`: `if name in _PLUGIN_THRESHOLDS: return _PLUGIN_THRESHOLDS[name]`, then the existing `DEFAULT_THRESHOLDS.get(name, THRESHOLD)`. Update its docstring and the "Fonts not listed (user, plugin, third-party) are unmeasured and keep THRESHOLD" comment: plugin fonts keep THRESHOLD only when their plugin declared none.
- `list_available_hires_fonts()`: `names.update(_PLUGIN_FONTS)` before sorting (registered-but-missing files are listed; `resolve_font` still raises the clear "file is missing" error for them).

- [ ] **Step 4: Implement in `_plugin_loader.py`**

- Import `_PLUGIN_THRESHOLDS` beside `_PLUGIN_FONTS`; add `"font_thresholds": _PLUGIN_THRESHOLDS` to `_REGISTRY_MAP`.
- Module constant `_UNCOUNTED_SURFACES: frozenset[str] = frozenset({"font_thresholds"})`; in `_commit`'s write pass, skip the `info.counts` / `info.names` update for surfaces in it (the threshold is an attribute of the font, not a contribution).

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_plugins/ tests/test_font_default_threshold.py tests/test_validate_rotation_rules.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/fonts/hires_loader.py src/led_ticker/_plugin_loader.py tests/test_plugins/test_font_plugins.py
git commit -m "feat(fonts): plugin-declared default thresholds; plugin fonts count as hi-res"
```

---

### Task 2: API — `api.font(name, path, threshold=None)` and end-to-end through a local plugin

**Files:**
- Modify: `src/led_ticker/plugin.py` (`_buffers` dict ~line 280, `font` method ~427)
- Test: `tests/test_plugins/test_plugin_api.py`, `tests/test_plugins/test_font_plugins.py`

**Interfaces:**
- Consumes: Task 1's `_PLUGIN_THRESHOLDS`, `default_threshold`, listing.
- Produces: `PluginAPI.font(self, name: str, path: str, threshold: int | None = None) -> None`; buffer key `"font_thresholds"` holding `{qualified_name: int}` only when `threshold` was given.

- [ ] **Step 1: Write the failing API tests** (append to `test_plugin_api.py`, reusing its `api` construction from `test_font_buffers_resolved_absolute_path`)

```python
def test_font_threshold_is_buffered_when_given(tmp_path):
    api = PluginAPI("acme", root=tmp_path)
    api.font("Brand", "fonts/Brand.ttf", threshold=45)
    assert api._buffers["font_thresholds"]["acme.Brand"] == 45


def test_font_without_threshold_leaves_no_threshold_entry(tmp_path):
    api = PluginAPI("acme", root=tmp_path)
    api.font("Brand", "fonts/Brand.ttf")
    assert "acme.Brand" not in api._buffers["font_thresholds"]


@pytest.mark.parametrize("bad", [45.0, True, -1, 256, "45"])
def test_font_rejects_bad_threshold(tmp_path, bad):
    api = PluginAPI("acme", root=tmp_path)
    with pytest.raises(ValueError, match="threshold"):
        api.font("Brand", "fonts/Brand.ttf", threshold=bad)
    assert "acme.Brand" not in api._buffers["fonts"]  # nothing half-registered
```

- [ ] **Step 2: Write the failing end-to-end test** (append to `test_font_plugins.py`, modelled on `test_local_plugin_contributes_emoji_hires_and_font`: a package-dir local plugin under `tmp_path / "plugins" / "acme"`, copying `_a_bundled_font_path()` in as `Brand.ttf`)

```python
def test_local_plugin_font_threshold_reaches_resolve_font(tmp_path):
    # register(api): api.font("Brand", "Brand.ttf", threshold=45)
    ...load via L.load_plugins(tmp_path / "plugins")...
    try:
        font = resolve_font("acme.Brand", size=24)          # no threshold passed
        assert isinstance(font, HiresFont) and font.threshold == 45
        assert resolve_font("acme.Brand", size=24, threshold=100).threshold == 100  # explicit wins
        assert "acme.Brand" in list_available_hires_fonts()
    finally:
        L.reset_plugins()


async def test_plugin_hires_font_refused_on_two_row_image(tmp_path):
    # same local plugin; then
    from led_ticker.app.factories import validate_widget_cfg
    cfg = {"type": "image", "path": "x.png", "text": "a", "bottom_text": "b", "font": "acme.Brand"}
    with pytest.raises(ValueError, match="hi-res font on a two-row"):
        await validate_widget_cfg(cfg)   # async; check its remaining kwargs in factories.py:992
```
(`HiresFont.threshold` is a real attribute; `PluginAPI("acme", root=tmp_path)` is the constructor the existing tests use.)

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_plugins/test_plugin_api.py tests/test_plugins/test_font_plugins.py -v`
Expected: new tests FAIL (`TypeError: unexpected keyword 'threshold'`, `KeyError: 'font_thresholds'`, two-row refusal not raised).

- [ ] **Step 4: Implement in `plugin.py`**

- Add `"font_thresholds": {}` to `_buffers`.
- `def font(self, name: str, path: str, threshold: int | None = None) -> None`: validate `threshold` BEFORE touching any buffer (`isinstance(threshold, bool) or not isinstance(threshold, int) or not 0 <= threshold <= 255` → `ValueError(f"api.font({name!r}): threshold must be an int 0-255, got {threshold!r}")`); store the path as today; if `threshold is not None`, `self._buffers["font_thresholds"][self._qualify(name)] = threshold`. Extend the docstring: the threshold is the font's default `font_threshold` (what `default_threshold` returns and validate rule 2 treats as "on default"); omit it for 128.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_plugins/ -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/plugin.py tests/test_plugins/test_plugin_api.py tests/test_plugins/test_font_plugins.py
git commit -m "feat(plugin): api.font accepts a default threshold"
```

---

### Task 3: Validate — rule 2 honours plugin defaults; rule 71 sees plugin fonts

**Files:**
- Test: `tests/test_validate.py` (beside `test_rule2_*` ~line 395 and `test_rule71_*` ~line 5488)
- Modify: none expected (rule 2 already calls `default_threshold`; rule 71 already calls `_is_hires_font_name`). If a test fails, the fix belongs in `validate.py` next to that rule.

**Interfaces:**
- Consumes: Tasks 1-2.

- [ ] **Step 1: Write the tests.** Each registers a plugin font directly on the loader globals (`hires_loader._PLUGIN_FONTS["acme.Brand"] = <bundled font path>`, `hires_loader._PLUGIN_THRESHOLDS["acme.Brand"] = 45`) in `try/finally` with `L.reset_plugins()`, then builds a config with the `conf` fixture like `test_rule2_no_warning_for_the_per_font_defaults`:

```python
async def test_rule2_quiet_when_plugin_font_widgets_sit_on_plugin_default(conf):
    # two message widgets, font = "acme.Brand", font_size = 24; one with
    # font_threshold = 45 spelled out, one unset
    assert all(w.rule != 2 for w in result.warnings)


async def test_rule2_warns_when_one_plugin_font_widget_overrides(conf):
    # same, but one widget has font_threshold = 100
    assert any(w.rule == 2 for w in result.warnings)


async def test_rule71_fires_for_plugin_hires_font_in_two_row_mode(conf):
    # image widget with bottom_text and font = "acme.Brand"
    assert any(e.rule == 71 for e in result.errors)
```

- [ ] **Step 2: Run**

Run: `uv run pytest tests/test_validate.py -k "plugin_font or plugin_default or plugin_hires" -v`
Expected: PASS without source changes (Tasks 1-2 already wired both predicates). If rule 71 does not fire, fix the predicate in `validate.py`'s rule 71 the same way `_is_hires_font_name` was fixed, and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/test_validate.py
git commit -m "test(validate): rule 2 and rule 71 cover plugin fonts with declared thresholds"
```

---

### Task 4: `API_VERSION (1, 3)` and docs

**Files:**
- Modify: `src/led_ticker/plugin.py:192-197` (comment block + constant)
- Modify: `docs/site/src/content/docs/plugins/api-reference.mdx:42` (intro sentence), `:93` (`api.font` row)
- Modify: `docs/site/src/content/docs/plugins/authoring/01-scaffold.mdx:92`
- Modify: `docs/plugin-system.md` (bullet list ~line 236)
- Modify: `docs/site/src/content/docs/concepts/fonts.mdx:57`
- Modify: `CLAUDE.md:116` (`font_threshold` paragraph)
- Test: `tests/test_docs_plugin_api_drift.py` (existing), `tests/test_font_default_threshold.py`

- [ ] **Step 1: Add the version pin test** to `tests/test_font_default_threshold.py` beside `test_exported_through_the_plugin_api`:

```python
def test_plugin_font_thresholds_are_a_1_3_guarantee(self):
    from led_ticker import plugin
    assert plugin.API_VERSION >= (1, 3)
```

- [ ] **Step 2: Run drift + pin tests to see them fail**

Run: `uv run pytest tests/test_docs_plugin_api_drift.py tests/test_font_default_threshold.py -q`
Expected: the new pin FAILS; drift tests pass (not yet changed).

- [ ] **Step 3: Bump and document**

- `plugin.py`: `API_VERSION = (1, 3)`; add to the comment block: `(1, 3) — api.font accepts threshold=; default_threshold honours it; plugin fonts appear in the hi-res listing (so validate/factories treat them as hi-res).`
- `api-reference.mdx:42`: `currently \`(1, 3)\``; append to the minor-bumps sentence: `(1, 3) lets api.font declare the font's default font_threshold.` Row 93: `` `api.font(name, path, threshold=None)` | call | A font file; `path` is relative to the plugin root; `threshold` (int 0-255) is the font's default `font_threshold` (omit for 128) ``. Check `_documented_methods` in the drift test still parses the row (it keys on the method name).
- `01-scaffold.mdx:92`: `currently \`(1, 3)\``.
- `plugin-system.md`: new bullet after the single-file-plugins font bullet: `**Plugin fonts carry their own default threshold** — api.font(..., threshold=45) sets what default_threshold returns for that font (core API (1, 3)); guard with API_VERSION >= (1, 3) if the plugin must load on older cores. Plugin font names are hi-res to validate and the factories (two-row image refusal, font_size hints).`
- `fonts.mdx:57`: replace `Every other hi-res font — user-supplied or plugin-contributed — defaults to 128.` with `User-supplied fonts default to 128; a plugin font defaults to whatever its plugin declared (128 if it declared nothing).`
- `CLAUDE.md:116` paragraph: after `Fonts not in DEFAULT_THRESHOLDS (user/plugin/third-party) are unmeasured and keep 128; thin-stroked ones need ~80 set explicitly.` add `A plugin may declare its font's default via api.font(..., threshold=) (API (1, 3)); default_threshold checks _PLUGIN_THRESHOLDS before the core table, and list_available_hires_fonts includes plugin names so _is_hires_font_name sees them.`

- [ ] **Step 4: Run the full suite, lint, docs drift**

Run: `make test && make lint && uv run pytest tests/test_docs_plugin_api_drift.py tests/test_docs_config_options_drift.py -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/plugin.py docs/ CLAUDE.md tests/test_font_default_threshold.py
git commit -m "feat(plugin): API_VERSION 1.3 — plugin font thresholds; docs"
```

---

### Task 5: Pre-push checks and draft PR (needs James's go to open)

- [ ] **Step 1: pyright + full test**

Run: `uv run pyright && make test`
Expected: 0 errors; suite green.

- [ ] **Step 2: Write the PR body** to `/private/tmp/claude-501/-Users-james-projects-github-jamesawesome-led-ticker/c6556a8c-18eb-466f-96b1-87a68aa284aa/scratchpad/pr-font-thr.md`: summary (why: flair display fonts need 45, default 128 shatters them; what: `api.font` threshold, `default_threshold`, hi-res listing, API 1.3), test list, "byte-identical for existing configs", link to the spec path, trailer `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

- [ ] **Step 3: Push and ask**

```bash
git push -u origin feat/plugin-font-thresholds
```
Then ask James for the go before `gh pr create --draft --title "feat(plugin): plugin fonts declare their default threshold (API 1.3)" --body-file <path>`.

---

## After merge

Release core (James clicks publish). Then write the flair plan from the spec's "Flair" section with the released version as the floor (check `git tag` first; the dev version lags tags).
