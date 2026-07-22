# Pixel-Font-Aware Auto-Sizing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public core helper (`pixel_native_size`) so plugins can snap a dynamically-computed font size onto a pixel font's native grid; flair's lottery uses it so Spleen renders crisp on ball faces instead of blurry off-grid.

**Architecture:** Core exposes the existing private `_PIXEL_NATIVE` registry via a pure-lookup public function re-exported on `led_ticker.plugin`. Flair's `auto_font_size` restricts its candidate sizes to native multiples when the font is pixel-native. Config switches the halal lottery to `spleen-6x12`. Ships in dependency order: core → flair → config.

**Tech Stack:** Python, pytest. Repos: core (`/Users/james/projects/github/jamesawesome/led-ticker`, branch `pixel-native-public-api`) and the `led-ticker-plugins` monorepo (flair).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-21-pixel-font-auto-sizing-design.md`.
- **Dependency order is a hard gate:** core ships `pixel_native_size` and is MERGED + RELEASED (core minor → v4.26.0) BEFORE the flair task, because flair imports the helper and bumps its core floor to `>=4.26`. The flair release must precede the halal config switch (Task 4) so the committed example is crisp on current plugins.
- `pixel_native_size(name: str) -> int | None` — pure lookup of `_PIXEL_NATIVE`; returns 12/16/32 for `spleen-6x12`/`8x16`/`16x32`, `None` for outline fonts and unknowns. Added to `led_ticker.plugin`'s imports AND `__all__` AND `docs/site/src/content/docs/plugins/api-reference.mdx` (the `api-exports` marked region — else `tests/test_docs_plugin_api_drift.py` fails). `API_VERSION` does NOT bump (additive).
- Flair snap = restrict `auto_font_size`'s candidate sizes to native multiples; outline-font path unchanged; return `0` when even `native` doesn't fit (existing sentinel). Exact-size test assertions ARE allowed (integer grid).
- No `from __future__ import annotations` (either repo). Core lint gates from repo root: `uv run --extra dev ruff check src/ tests/`, `ruff format --check`, `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/` (2 pre-existing app/run.py+ticker.py errors known-acceptable). Git hooks broken — `git commit/push --no-verify` after manual gates. Known pre-existing local failure `test_no_legacy_mode_names_in_live_tree` — ignore.
- Every human gate (core merge+release, flair merge+release, config merge) is JAMES's — do not merge or approve a release deployment without his word.

---

### Task 1: Core — `pixel_native_size` public helper

**Files:**
- Modify: `src/led_ticker/fonts/hires_loader.py` (add the function beside `_PIXEL_NATIVE`, ~line 94)
- Modify: `src/led_ticker/plugin.py` (import + `__all__`)
- Modify: `docs/site/src/content/docs/plugins/api-reference.mdx` (api-exports table)
- Test: `tests/test_spleen_fonts.py` (append)

**Interfaces:**
- Produces: `led_ticker.fonts.hires_loader.pixel_native_size(name: str) -> int | None`, re-exported as `led_ticker.plugin.pixel_native_size`. Task 3 (flair) consumes `from led_ticker.plugin import pixel_native_size`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_spleen_fonts.py`)

```python
class TestPixelNativeSize:
    def test_spleen_names_return_native(self):
        from led_ticker.fonts.hires_loader import pixel_native_size

        assert pixel_native_size("spleen-6x12") == 12
        assert pixel_native_size("spleen-8x16") == 16
        assert pixel_native_size("spleen-16x32") == 32

    def test_outline_and_unknown_return_none(self):
        from led_ticker.fonts.hires_loader import pixel_native_size

        assert pixel_native_size("Inter-Bold") is None
        assert pixel_native_size("Inter-Regular") is None
        assert pixel_native_size("nonesuch") is None

    def test_exposed_on_plugin_surface(self):
        import led_ticker.plugin as plugin

        assert "pixel_native_size" in plugin.__all__
        assert plugin.pixel_native_size("spleen-6x12") == 12
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --no-sync python -m pytest tests/test_spleen_fonts.py -q -k PixelNativeSize`
Expected: FAIL (`pixel_native_size` undefined / not on plugin).

- [ ] **Step 3: Add the helper** (in `hires_loader.py`, immediately after the `_PIXEL_NATIVE` dict)

```python
def pixel_native_size(name: str) -> int | None:
    """Native pixel height of a bundled pixel font (``spleen-6x12`` -> 12),
    or ``None`` if ``name`` isn't a pixel-native font.

    A pixel font is crisp (exact 1-bit, no antialiasing) ONLY at its native
    size or an integer multiple. A caller that computes a font size
    dynamically (e.g. auto-fitting text to a shape) should restrict its
    candidates to native multiples so the result stays sharp. Outline fonts
    (Inter, DejaVu, user TTFs) return ``None`` — they render at any size, so
    callers leave them on their existing continuous path."""
    return _PIXEL_NATIVE.get(name)
```

- [ ] **Step 4: Export on `led_ticker.plugin`**

In `src/led_ticker/plugin.py` change the hires import:

```python
from led_ticker.fonts.hires_loader import HiresFont, pixel_native_size
```

and add to `__all__` (next to `"HiresFont",`):

```python
    "pixel_native_size",
```

- [ ] **Step 5: Add to the plugin API reference**

In `docs/site/src/content/docs/plugins/api-reference.mdx`, inside the `api-exports` marked region (after the `font_line_height_logical` row, ~line 206), add a row:

```markdown
| `pixel_native_size(name)`                                                  | Native px of a bundled [pixel font](/concepts/fonts/) (`spleen-6x12` → 12), else `None` — snap a computed size onto its grid to keep pixel text crisp |
```

- [ ] **Step 6: Run tests + gates**

Run: `uv run --no-sync python -m pytest tests/test_spleen_fonts.py tests/test_docs_plugin_api_drift.py -q` → green. Then the three lint gates. Then `cd docs/site && pnpm run build` (exit 0).

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/fonts/hires_loader.py src/led_ticker/plugin.py docs/site/src/content/docs/plugins/api-reference.mdx tests/test_spleen_fonts.py
git commit --no-verify -m "feat(plugin): expose pixel_native_size — snap dynamic sizes onto a pixel font's grid"
```

---

### Task 2: Core — commit the longboi config additions + open the core PR (HARD GATE)

**Files:**
- Commit (already modified, uncommitted on this branch): `config/config.longboi.toml`

**Interfaces:** none (config data + PR).

- [ ] **Step 1: Confirm the longboi change validates the same as before**

The longboi additions (stocks/baseball/flight/transitions) were made + validated earlier this session. Re-confirm: `uv run --no-sync led-ticker validate config/config.longboi.toml` — the ONLY errors are locally-uninstalled plugins (`weather`/`rss`/`pool`/`flight`); zero field/transition/toml errors. (Verify with `git diff config/config.longboi.toml` that it's the intended additions.)

- [ ] **Step 2: Commit the config**

```bash
git add config/config.longboi.toml
git commit --no-verify -m "config(longboi): add stocks/baseball/flight sections + flair transitions"
```

- [ ] **Step 3: Full suite + gates**

`uv run --no-sync python -m pytest tests/ -q` (only the known stale-worktree failure allowed) + the three lint gates. Record the pass count.

- [ ] **Step 4: Push + open the core PR**

Push `pixel-native-public-api`; `gh pr create`. Body: the auto-sizing problem (lottery off-grid on pixel fonts); the `pixel_native_size` public helper (additive, no API_VERSION bump); that flair consumes it next (core ships first); the longboi config additions; release = core minor (v4.26.0). Note the flair + halal-config follow-ups are separate PRs in the dependency chain.

- [ ] **Step 5: HARD STOP — James merges + cuts the core release**

`gh pr checks --watch`, report green. STOP. James merges and releases core **v4.26.0** (and approves the publish-environment deployment). Do NOT proceed to Task 3 until v4.26.0 is released — flair's floor bump references it.

---

### Task 3: Flair — grid-aware `auto_font_size` (HARD GATE)

**Repo:** the `led-ticker-plugins` monorepo. **Branch off `origin/main`** — a working checkout exists at `/Users/james/projects/github/jamesawesome/led-ticker-plugins-flight` but it is on `stickers-cap-readme`; do NOT stack on that branch. `git fetch origin` then create the flair branch from `origin/main` in a clean checkout.

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/lottery.py` (`auto_font_size`, ~line 217)
- Modify: `plugins/flair/pyproject.toml` (core floor `led-ticker-core>=4.18` → `>=4.26`)
- Test: `plugins/flair/tests/test_flair_lottery.py` (append)

**Interfaces:**
- Consumes: `led_ticker.plugin.pixel_native_size` (Task 1, released in core v4.26.0). Constants already in `lottery.py`: `_MAX_FONT_FACTOR = 0.45`, `_MIN_FONT_SIZE = 8`, `_CHORD_FACTOR = 0.72`, `_FACE_THRESHOLD = 80`, `_REAL_SCALE1_STUB = SimpleNamespace(scale=1)`.

- [ ] **Step 1: Write the failing tests** (append to `test_flair_lottery.py`; match its existing import/style)

```python
class TestAutoFontSizePixelGrid:
    def test_pixel_font_returns_only_native_multiples(self):
        from led_ticker_flair.flair.lottery import auto_font_size

        # Across a range of ball diameters, a pixel font must resolve to a
        # native multiple (or 0 = doesn't fit) — never an off-grid size.
        for diam in (40, 48, 56, 64, 80):
            for word in ("HALAL", "GYRO", "RICE"):
                size = auto_font_size(word, diam, "spleen-6x12", 4)
                assert size == 0 or size % 12 == 0, (diam, word, size)

    def test_pixel_font_snaps_down_not_up(self):
        # A diameter whose continuous fit lands between 12 and 24 must snap
        # DOWN to 12 (fits), never up to 24 (would overflow).
        from led_ticker_flair.flair.lottery import auto_font_size

        size = auto_font_size("RICE", 48, "spleen-6x12", 4)
        assert size in (0, 12, 24, 36)  # on-grid only
        # 48px ball: continuous fit ~15 -> snaps to 12
        assert size == 12

    def test_tiny_ball_returns_zero_when_native_overflows(self):
        from led_ticker_flair.flair.lottery import auto_font_size

        # A ball too small for even native 12px pixel text -> 0 (doesn't fit).
        assert auto_font_size("HALAL", 16, "spleen-6x12", 4) == 0

    def test_outline_font_unchanged(self):
        # Inter keeps the continuous search (may return any int).
        from led_ticker_flair.flair.lottery import auto_font_size

        size = auto_font_size("RICE", 48, "Inter-Bold", 4)
        assert size > 0  # unchanged continuous behavior
```

- [ ] **Step 2: Run to verify failure**

Run (from `plugins/flair/`): `uv run --no-sync python -m pytest tests/test_flair_lottery.py -q -k PixelGrid`
Expected: FAIL (pixel font currently returns off-grid sizes like 15).

- [ ] **Step 3: Implement the grid-aware search**

In `lottery.py`, add the import near the top (with the other `led_ticker.plugin` imports — check how the file imports `resolve_font`/`get_text_width` and match):

```python
from led_ticker.plugin import pixel_native_size
```

Rework `auto_font_size`'s candidate loop. Current body (~line 250):

```python
    threshold = diameter_px * _CHORD_FACTOR
    for size in range(int(diameter_px * _MAX_FONT_FACTOR), _MIN_FONT_SIZE - 1, -1):
        font = resolve_font(font_name, size, _FACE_THRESHOLD)
        width = get_text_width(font, word, padding=0, canvas=_REAL_SCALE1_STUB)
        if width <= threshold:
            return size
    return 0
```

Replace with:

```python
    threshold = diameter_px * _CHORD_FACTOR
    ceil = int(diameter_px * _MAX_FONT_FACTOR)
    native = pixel_native_size(font_name)
    if native is not None:
        # Pixel font: only native multiples render crisp — search those,
        # largest first. If even `native` overflows, fall through to 0.
        candidates = range(ceil - (ceil % native), native - 1, -native)
    else:
        # Outline font: continuous search (unchanged).
        candidates = range(ceil, _MIN_FONT_SIZE - 1, -1)
    for size in candidates:
        font = resolve_font(font_name, size, _FACE_THRESHOLD)
        width = get_text_width(font, word, padding=0, canvas=_REAL_SCALE1_STUB)
        if width <= threshold:
            return size
    return 0
```

Note: `range(ceil - (ceil % native), native - 1, -native)` yields the largest multiple `<= ceil` down to `native`. If `ceil < native` the start is `0` and the range is empty → returns `0` (doesn't fit) without ever resolving an off-grid size. Update `auto_font_size`'s docstring to note pixel fonts search native multiples only.

- [ ] **Step 4: Bump the core floor**

In `plugins/flair/pyproject.toml`: `"led-ticker-core>=4.18"` → `"led-ticker-core>=4.26"`.

- [ ] **Step 5: Run tests + gates**

From `plugins/flair/`: `uv run --no-sync python -m pytest tests/test_flair_lottery.py -q` → green (the new class + all existing lottery tests). Run the monorepo's lint (`ruff check`/`ruff format --check` per its RELEASING/CI config) + pyright if configured.

- [ ] **Step 6: Commit**

```bash
git add plugins/flair/src/led_ticker_flair/flair/lottery.py plugins/flair/pyproject.toml plugins/flair/tests/test_flair_lottery.py
git commit --no-verify -m "feat(lottery): auto-size pixel fonts to their native grid (crisp Spleen ball faces)"
```

- [ ] **Step 7: Visual gate (James) + flair PR — HARD STOP**

Render the halal lottery in `spleen-6x12` (a throwaway config with the four lottery widgets set to `font = "spleen-6x12"`, rendered via the core render_demo against the editable flair) → contact sheet. Confirm the ball faces are crisp (on-grid) vs the prior soft off-grid. Send James the sheet. On approval, push the flair branch + `gh pr create` (body: the off-grid problem, the native-multiple search, the core-floor bump to 4.26, the visual gate; release = flair minor). STOP — James merges + releases flair.

---

### Task 4: Config — halal lottery → Spleen (HARD GATE)

**Repo:** core. **Files:** Modify `config/config.halal-cart.example.toml` (the four `flair.lottery` widgets).

- [ ] **Step 1: Branch + set the font**

Off core `main` (after Task 2's core merge), a fresh branch. Add `font = "spleen-6x12"` to each of the four `flair.lottery` widget blocks in `config/config.halal-cart.example.toml`.

- [ ] **Step 2: Validate**

`uv run --no-sync led-ticker validate config/config.halal-cart.example.toml` — 0 errors (a flair.lottery font is a valid field; requires led-ticker-flair which is installed locally). Confirm no new rule-69 warning (the widget auto-sizes internally — the config carries no static `font_size`, so rule 69 doesn't apply).

- [ ] **Step 3: Commit + PR + HARD STOP**

Commit (`config(halal): lottery balls in spleen-6x12 — crisp pixel faces`), push, `gh pr create` (body: pairs with flair's grid-aware auto-size, released as flair vX; balls now render crisp). STOP — James merges.

---

## Self-review (done at write time)

- **Spec coverage:** §1 core helper = Task 1; §2 flair snap = Task 3; §3 config = Task 4; sequencing/gates = Tasks 2/3/4 hard stops; longboi additions ride Task 2; tests (core helper, flair native-multiples/zero/outline-unchanged, visual gate) all present; API_VERSION-no-bump + api-reference drift = Task 1.
- **Placeholder scan:** none.
- **Type consistency:** `pixel_native_size(name: str) -> int | None` identical across Task 1 (def), Task 1 tests, Task 3 (consume). `native` local reused consistently in the flair loop. `auto_font_size(word, diameter_px, font_name, scale) -> int` signature unchanged.

---

## Rework (2026-07-21) — lottery accepts a config-selected font

The original Tasks 1–2 SHIPPED (core `pixel_native_size` + longboi config, core v4.26.0). The original Task 3 flair grid-snap was built (commit `c20c316`, reviewed clean) but NOT merged — it folds into Task B below. This rework adds the missing piece (spec Addendum): a self-sizing widget can keep its `font` as a raw name. Same 3-gate cadence; all gates are James's.

### Task A: Core — `RESOLVES_OWN_FONT` opt-out

**Files:**
- Modify: `src/led_ticker/app/factories.py` (`_resolve_fonts`, ~line 482)
- Modify: `docs/site/src/content/docs/plugins/api-reference.mdx` (a note; the marker is read off the widget class — no new `__all__` name, so the drift test is unaffected, but document the contract)
- Test: `tests/test_factories.py` (or wherever `_resolve_fonts` is tested — grep `_resolve_fonts`; append there)

**Interfaces:**
- Produces: core honors a widget class attribute `RESOLVES_OWN_FONT: bool` (default `False`). When `True`, `_resolve_fonts` leaves the widget's `font` value as the raw NAME string (no resolve-to-`Font`, no "requires font_size"). Task B (flair) sets this on the lottery.

- [ ] **Step 1: Write the failing tests** (find the existing `_resolve_fonts` tests first — `grep -rn "_resolve_fonts" tests/` — and match their idiom)

```python
def test_resolves_own_font_leaves_raw_name():
    import attrs
    from led_ticker.app.factories import _resolve_fonts

    @attrs.define
    class _SelfSizer:
        RESOLVES_OWN_FONT = True
        font: str = "Inter-Bold"

    cfg = {"font": "spleen-6x12"}  # hires name, NO font_size
    _resolve_fonts(cfg, _SelfSizer, None)
    assert cfg["font"] == "spleen-6x12"  # raw name, not a Font object, no raise

def test_normal_widget_still_requires_font_size_for_hires():
    import pytest

    from led_ticker.app.factories import _resolve_fonts

    class _Normal:  # no marker
        pass

    with pytest.raises(ValueError, match="requires font_size"):
        _resolve_fonts({"font": "spleen-6x12"}, _Normal, None)
```

- [ ] **Step 2: Run to verify failure** — `test_resolves_own_font_leaves_raw_name` raises "requires font_size".

- [ ] **Step 3: Implement the opt-out** — in `_resolve_fonts`, after `cls_fields = ...` (line 480) and inside `if font_name is not None:` (line 482), branch on the marker BEFORE the hires-size check:

```python
    if font_name is not None:
        if getattr(cls, "RESOLVES_OWN_FONT", False):
            # Widget self-resolves its font (e.g. flair.lottery auto-sizes
            # each ball face) — leave the raw NAME string in place; no
            # coercion to a Font object, no font_size requirement. font_size/
            # font_threshold fall through to the existing "re-insert only if
            # the class declares the field" logic below (dropped otherwise).
            if cls is None or "font" in cls_fields:
                widget_cfg["font"] = font_name
        else:
            if _is_hires_font_name(font_name) and font_size is None:
                raise ValueError(
                    f"HiresFont {font_name!r} requires font_size (real "
                    f"pixels). e.g. font_size = 24 for bigsign, "
                    f"font_size = 12 for small sign."
                )
            font = resolve_font(font_name, font_size, threshold=font_threshold)
            if cls is None or "font" in cls_fields:
                widget_cfg["font"] = font
            # ... keep the existing hires-panel-height warning block here ...
```

(Preserve the existing panel-height warning block inside the `else`. The `font_size`/`small_font`/`top_font`/`bottom_font` handling AFTER the `if font_name` block is unchanged.)

- [ ] **Step 4: API-reference note** — in `docs/site/src/content/docs/plugins/api-reference.mdx`, add a short line (in the widget-authoring prose or a nearby note) that a widget class may set `RESOLVES_OWN_FONT = True` to receive its `font` as a raw name it resolves itself. Prettier-format + `pnpm run build`.

- [ ] **Step 5: Run tests + gates** — the new tests + the existing `_resolve_fonts`/factories tests + the three lint gates. `pnpm run build` (docs).

- [ ] **Step 6: Commit** — `git commit --no-verify -m "feat(factories): RESOLVES_OWN_FONT — let a self-sizing widget keep its font as a raw name"`.

- [ ] **Step 7: Longboi/other configs unaffected** — full suite green (only known stale-worktree failure). Push + core PR. **HARD STOP: James merges + releases core v4.27.0** (BLOCKS Task B's floor bump).

### Task B: Flair — lottery takes a config font (folds in the grid-snap)

**Repo:** `led-ticker-plugins`. Rebase/cherry-pick the grid-snap commit `c20c316` (Task 3) onto a fresh branch off `origin/main`, then add this task's changes on top. Bump core floor to `>=4.27`.

**Files:**
- Modify: `plugins/flair/src/led_ticker_flair/flair/lottery.py` (add `RESOLVES_OWN_FONT = True` to the widget class; relax `_font_is_a_name`; keep the grid-aware `auto_font_size` from `c20c316`)
- Modify: `plugins/flair/pyproject.toml` (`led-ticker-core>=4.26` → `>=4.27`)
- Test: `plugins/flair/tests/test_flair_lottery.py`

**Interfaces:** Consumes core v4.27.0's `RESOLVES_OWN_FONT` honoring + v4.26.0's `pixel_native_size`.

- [ ] **Step 1: Write the failing test** — a config-set `font` on the lottery now loads and is used:

```python
def test_config_font_is_accepted_and_used():
    # With RESOLVES_OWN_FONT, core leaves `font` a raw name; the lottery
    # accepts it and auto-sizes it. A pixel font stays on-grid.
    from led_ticker.app.factories import validate_widget_cfg  # or the build path

    cfg = {"type": "flair.lottery", "words": ["HALAL"], "font": "spleen-6x12"}
    # Must NOT raise (previously rejected by _font_is_a_name / requires font_size)
    validate_widget_cfg(cfg)  # adapt to the test's actual call/signature
```

Plus: the lottery widget class has `RESOLVES_OWN_FONT = True`; `_font_is_a_name` accepts `"spleen-6x12"` (a valid name) and still rejects an unknown font name.

- [ ] **Step 2: Run to verify failure** — currently `_font_is_a_name` rejects any config font.

- [ ] **Step 3: Implement** — set `RESOLVES_OWN_FONT = True` on the lottery widget class. Rewrite `_font_is_a_name` to accept a font NAME string (validate it resolves — e.g. via a cheap `resolve_font` name check or the known-font set — erroring clearly on an unknown name) instead of rejecting all strings-that-came-from-config. Keep the grid-aware `auto_font_size` (`c20c316`). The lottery's existing default (`font = "Inter-Bold"`, omitted-config path) stays working.

- [ ] **Step 4: Floor bump** — `pyproject.toml` core floor → `>=4.27`.

- [ ] **Step 5: Run tests + gates** — new tests + all existing lottery tests (86+) + monorepo lint. (The 5 pre-existing `test_flair_stickers_transition.py` failures on main are unrelated — ignore, but flag.)

- [ ] **Step 6: Commit.**

- [ ] **Step 7: Visual gate + PR — HARD STOP** — render the halal lottery in `spleen-6x12` (from the monorepo env: `uv run --no-sync python <core>/tools/render_demo/render.py <cfg> -o out.gif`), contact sheet. Confirm ball faces are crisp Spleen vs auto-sized Inter-Bold. Send James. **OFF-RAMP:** if Spleen isn't clearly better at ~12–24px, stop before Task C. On approval: flair PR. James merges + releases flair.

### Task C: Config — halal lottery → Spleen (HARD GATE)

**Repo:** core. **File:** `config/config.halal-cart.example.toml` (the four `flair.lottery` widgets).

- [ ] Add `font = "spleen-6x12"` to each of the four lottery widgets. Validate (0 errors — now accepted). Commit + core PR. **HARD STOP: James merges.**
