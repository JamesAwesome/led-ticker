# Hi-res transition plugin API (P2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an out-of-tree plugin drive the hi-res sprite-transition renderer with its own sprite, by making `render_hires_frame` take a `HiresSpec` directly (removing the core-internal `HIRES_REGISTRY` back-edge) and exporting both on the public `led_ticker.plugin` surface.

**Architecture:** Approach (b) from the spec. `render_hires_frame`/`load_hires` become pure functions of a `HiresSpec`; the built-in `nyancat`/`pokeball` classes resolve their spec from `HIRES_REGISTRY` at the call site and pass it (registry survives as the built-ins' private catalog). The one non-lookup use of `registry_name` (the `has_ball_class` gate for the procedural pokeball) becomes a kwarg gate (`show_pokeball`, default False) — behavior-preserving because pokeball always passes it explicitly and nyancat never does.

**Tech Stack:** Python 3.14, pytest (`PYTHONPATH=tests/stubs`), Pillow (sprite decode), attrs/dataclass.

**Spec:** `docs/superpowers/specs/2026-06-15-hires-transition-plugin-api-design.md` (read first).

**Worktree / branch:** all work in `.claude/worktrees/feat+hires-transition-plugin-api` on branch `worktree-feat+hires-transition-plugin-api`. NEVER commit to `main`. First action each task: `pwd && git branch --show-current` and confirm.

**Conventions:** tests `PYTHONPATH=tests/stubs uv run pytest <path> -q`; NO `from __future__ import annotations` in `src/`; pre-commit hooks (ruff/format) fire on commit — re-stage if reformatted; match surrounding style.

---

### Task 1: Loader takes a HiresSpec; built-ins resolve-then-pass

The signature change and all four call sites must change together (one commit) or imports break.

**Files:**
- Modify: `src/led_ticker/transitions/_hires_loader.py` (`load_hires` ~221-227, `render_hires_frame` signature ~230-236 + the `has_ball_class` block ~279-280)
- Modify: `src/led_ticker/transitions/nyancat.py` (`_frame_at_hires` in `NyanCat` ~286-290 and `NyanCatReverse` ~330-333)
- Modify: `src/led_ticker/transitions/pokeball.py` (`_frame_at_hires` in `Pokeball` ~874-885 and `PokeballReverse` ~935-946)
- Test: `tests/test_hires_loader.py` (new — spec-based unit tests)

- [ ] **Step 1: Write the failing test**

Create `tests/test_hires_loader.py`:

```python
"""render_hires_frame / load_hires take a HiresSpec directly (P2).

The renderer no longer reaches into the core HIRES_REGISTRY — a spec
that was never registered still decodes and renders, which is what lets
an out-of-tree plugin supply its own sprite.
"""

import inspect

from PIL import Image

from led_ticker.transitions._hires_loader import load_hires, render_hires_frame
from led_ticker.transitions._hires_registry import HiresSpec


def _make_sprite(path, frames=2, size=(8, 8)):
    imgs = [Image.new("RGBA", size, (255, 0, 0, 255)) for _ in range(frames)]
    imgs[0].save(
        path, save_all=True, append_images=imgs[1:], duration=50, loop=0
    )
    return path


def test_render_hires_frame_signature_takes_spec():
    params = list(inspect.signature(render_hires_frame).parameters)
    # positional contract: (t, canvas, outgoing, incoming, spec, **kwargs)
    assert params[:5] == ["t", "canvas", "outgoing", "incoming", "spec"]


def test_load_hires_decodes_an_unregistered_spec(tmp_path):
    sprite = _make_sprite(tmp_path / "s.gif")
    spec = HiresSpec(sprite_path=sprite, flip_horizontal=False, trail="none")
    frames = load_hires(spec)
    assert frames is not None
    assert frames.width > 0 and frames.height > 0


def test_load_hires_caches_on_spec(tmp_path):
    sprite = _make_sprite(tmp_path / "s.gif")
    spec = HiresSpec(sprite_path=sprite, flip_horizontal=False, trail="none")
    assert load_hires(spec) is load_hires(spec)  # same spec -> cached object
    flipped = HiresSpec(sprite_path=sprite, flip_horizontal=True, trail="none")
    assert load_hires(flipped) is not load_hires(spec)  # distinct entry
```

- [ ] **Step 2: Run, expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_hires_loader.py -q`
Expected: FAIL — `render_hires_frame`'s 5th param is `registry_name`, and `load_hires(spec)` passes a `HiresSpec` where a `str` is expected (the `HIRES_REGISTRY.get(spec)` returns None → `load_hires` returns None).

- [ ] **Step 3: Refactor the loader** (`src/led_ticker/transitions/_hires_loader.py`)

Replace `load_hires` (currently):
```python
@functools.cache
def load_hires(transition_name: str) -> HiresFrames | None:
    """Decode + cache a registered sprite. Returns None for unregistered names."""
    spec = HIRES_REGISTRY.get(transition_name)
    if spec is None:
        return None
    return _decode(spec)
```
with:
```python
@functools.cache
def load_hires(spec: HiresSpec) -> HiresFrames:
    """Decode + cache a sprite from its spec. Cached on the frozen, hashable
    HiresSpec, so callers (built-in transitions resolving from HIRES_REGISTRY,
    or a plugin holding its own spec) share decode work for identical specs."""
    return _decode(spec)
```
Ensure `HiresSpec` is imported in this file (it's defined in `_hires_registry.py`; if not already imported, add `from led_ticker.transitions._hires_registry import HiresSpec` — check existing imports first, `HIRES_REGISTRY`/`_decode` are already in scope).

Change `render_hires_frame`'s signature param `registry_name: str,` → `spec: HiresSpec,` (keep position 5). Update the docstring's "registry has an entry" phrasing to "for the given sprite spec". Then:
- Replace `sprite = load_hires(registry_name)` with `sprite = load_hires(spec)`. Keep the immediately-following `if sprite is None: return canvas` guard (harmless — `load_hires` no longer returns None, but the guard is cheap defensive code; OR remove it. Prefer to REMOVE it for clarity since the type is now non-Optional: delete the two lines `if sprite is None:` / `return canvas`).
- Replace the `has_ball_class` gate (currently):
  ```python
  has_ball_class = registry_name in ("pokeball", "pokeball_reverse")
  show_pokeball = kwargs.get("show_pokeball", True) if has_ball_class else False
  ```
  with:
  ```python
  # The procedural ball is opt-in via the show_pokeball kwarg (default
  # off). Behavior-preserving: the pokeball family always passes it
  # explicitly; nyancat never passes it (so stays ball-free). A plugin
  # can now opt into the ball by passing show_pokeball=True.
  show_pokeball = bool(kwargs.get("show_pokeball", False))
  ```
  Leave the `show_pikachu = kwargs.get("show_pikachu", True)` line and everything after unchanged.

- [ ] **Step 4: Update the four built-in call sites**

`nyancat.py` — both `NyanCat._frame_at_hires` (~286) and `NyanCatReverse._frame_at_hires` (~330) currently:
```python
        from led_ticker.transitions._hires_loader import render_hires_frame

        return render_hires_frame(
            t, canvas, outgoing, incoming, self._registry_name, **kwargs
        )
```
→ resolve the spec from the registry (already imported at module top as `HIRES_REGISTRY`) and pass it:
```python
        from led_ticker.transitions._hires_loader import render_hires_frame

        spec = HIRES_REGISTRY[self._registry_name]
        return render_hires_frame(t, canvas, outgoing, incoming, spec, **kwargs)
```

`pokeball.py` — both `Pokeball._frame_at_hires` (~874) and `PokeballReverse._frame_at_hires` (~935) currently:
```python
        from led_ticker.transitions._hires_loader import render_hires_frame

        return render_hires_frame(
            t,
            canvas,
            outgoing,
            incoming,
            self._registry_name,
            show_pikachu=self._show_pikachu,
            show_pokeball=self._show_pokeball,
            **kwargs,
        )
```
→
```python
        from led_ticker.transitions._hires_loader import render_hires_frame

        spec = HIRES_REGISTRY[self._registry_name]
        return render_hires_frame(
            t,
            canvas,
            outgoing,
            incoming,
            spec,
            show_pikachu=self._show_pikachu,
            show_pokeball=self._show_pokeball,
            **kwargs,
        )
```
(The dispatch gate `self._registry_name in HIRES_REGISTRY` and `_registry_name` class attrs stay UNCHANGED in all four classes.)

- [ ] **Step 5: Run the new + regression tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_hires_loader.py tests/test_nyancat.py tests/test_pokeball.py tests/test_transitions.py -q`
Expected: new loader tests pass; ALL existing nyancat/pokeball/transitions tests pass unchanged (built-in behavior preserved — including the pokeball-draws-a-ball / nyancat-draws-no-ball assertions, which now flow through the `show_pokeball` kwarg the classes already pass).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/transitions/_hires_loader.py src/led_ticker/transitions/nyancat.py src/led_ticker/transitions/pokeball.py tests/test_hires_loader.py
git commit -m "refactor: render_hires_frame takes a HiresSpec, not a registry name"
```

---

### Task 2: Export HiresSpec + render_hires_frame; update api-reference (drift)

**Files:**
- Modify: `src/led_ticker/plugin.py` (imports ~47-62, `__all__` ~92-123)
- Modify: `docs/site/src/content/docs/plugins/api-reference.mdx` (the `api-exports` table, ~114-184)

- [ ] **Step 1: Add the exports to plugin.py**

In the import block, alongside the existing `from led_ticker.transitions._hires_loader import SNAP_THRESHOLD, snap_reset` (line ~62), add `render_hires_frame`:
```python
from led_ticker.transitions._hires_loader import (
    SNAP_THRESHOLD,
    render_hires_frame,
    snap_reset,
)
```
And add `HiresSpec` import (from `_hires_registry`):
```python
from led_ticker.transitions._hires_registry import HiresSpec
```
Add both names to `__all__` (keep the list's existing ordering style — it's roughly alphabetical; place `"HiresSpec"` near `"HiresFont"` and `"render_hires_frame"` near `"resolve_font"`/`"snap_reset"`).

- [ ] **Step 2: Run the drift test, expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_plugin_api_drift.py -q`
Expected: FAIL — the `api-exports` region lists `__all__`, which now has two names the docs page lacks (`HiresSpec`, `render_hires_frame`).

- [ ] **Step 3: Add the two rows to the api-reference page**

In `docs/site/src/content/docs/plugins/api-reference.mdx`, inside the `{/* <!-- api-exports:start --> */} ... {/* <!-- api-exports:end --> */}` table, add two rows matching the existing column format (a `` `name` `` first column + description). Use:
```
| `HiresSpec`                                                                | Frozen sprite spec for a hi-res transition: `sprite_path` (Path to a gif/webp), `flip_horizontal`, `trail` (`"none"`/`"black"`/`"rainbow"`)                                                                                    |
| `render_hires_frame(t, canvas, outgoing, incoming, spec, **kwargs)`        | Paint one frame of a hi-res sprite traversing the panel for the given `HiresSpec` (use on a `ScaledCanvas`; pass `show_pokeball=True` for a procedural leading ball)                                                           |
```
Place them in the same relative order as in `__all__` (HiresSpec near the other Hi* entries; render_hires_frame near snap_reset/paint_hires). Exact column padding doesn't matter — the drift test extracts the backticked symbol; prettier will re-align.

- [ ] **Step 4: Run drift + lint**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_plugin_api_drift.py -q`
Expected: PASS.
Run: `make docs-lint` (node via nvm: `node --version`; else `source ~/.nvm/nvm.sh && nvm use`). If prettier reformats the table, re-stage.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/plugin.py docs/site/src/content/docs/plugins/api-reference.mdx
git commit -m "feat: export HiresSpec + render_hires_frame on the plugin surface"
```

---

### Task 3: Plugin-simulation proof test

**Files:**
- Test: `tests/test_plugins/test_hires_transition_plugin.py` (new)

- [ ] **Step 1: Write the test**

Create `tests/test_plugins/test_hires_transition_plugin.py`. It simulates an out-of-tree plugin: a transition class holding its OWN `HiresSpec` (sprite generated into `tmp_path`, name never in `HIRES_REGISTRY`), and asserts the hi-res path paints sprite pixels on a `ScaledCanvas`.

```python
"""Proof that a plugin can drive the hi-res transition renderer with its
own sprite, with no entry in the core HIRES_REGISTRY (P2)."""

from PIL import Image

# The exact symbols a plugin author imports — must be on the public surface.
from led_ticker.plugin import HiresSpec, ScaledCanvas, render_hires_frame
from led_ticker.transitions._hires_registry import HIRES_REGISTRY


class _StubCanvas:
    def __init__(self, w, h):
        self.width = w
        self.height = h
        self.pixels = {}

    def SetPixel(self, x, y, r, g, b):
        self.pixels[(x, y)] = (r, g, b)


class _StubWidget:
    def draw(self, canvas, cursor_pos=0, **kwargs):
        return canvas, 0


def _make_sprite(path):
    # bright green so painted sprite pixels are unmistakably non-black
    frames = [Image.new("RGBA", (8, 8), (0, 255, 0, 255)) for _ in range(2)]
    frames[0].save(
        path, save_all=True, append_images=frames[1:], duration=50, loop=0
    )
    return path


def test_public_surface_exposes_hires_symbols():
    # The import above is the real assertion; this pins the contract.
    assert HiresSpec is not None
    assert callable(render_hires_frame)


def test_plugin_sprite_renders_hires_without_registry_entry(tmp_path):
    sprite = _make_sprite(tmp_path / "plugin_sprite.gif")
    spec = HiresSpec(sprite_path=sprite, flip_horizontal=False, trail="black")
    assert "myplugin.zoom" not in HIRES_REGISTRY  # never registered in core

    real = _StubCanvas(64, 32)
    canvas = ScaledCanvas(real, scale=4, content_height=8)

    # mid-transition so the sprite is on-panel
    result = render_hires_frame(
        0.5, canvas, _StubWidget(), _StubWidget(), spec
    )
    assert result is not None
    # The hi-res path paints to the REAL canvas; a black trail + green
    # sprite means non-black pixels were written at physical resolution.
    assert real.pixels, "render_hires_frame painted nothing"
    assert any(
        rgb == (0, 255, 0) for rgb in real.pixels.values()
    ), "expected the plugin sprite's green pixels on the real canvas"
```

- [ ] **Step 2: Run, expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugins/test_hires_transition_plugin.py -q`
Expected: PASS (Task 1+2 already shipped the capability). If `ScaledCanvas(real, scale=4, content_height=8)` constructor args differ, match the signature used in `tests/test_borders.py`'s `test_unwraps_scaled_canvas_to_paint_real_pixels` (which constructs `ScaledCanvas(real, scale=4, content_height=8)`). If the sprite paints no green (e.g. fully covered by trail), widen the assertion to "any non-black pixel exists" and report — but green should appear since the sprite paints on top of the trail.

- [ ] **Step 3: Commit**

```bash
git add tests/test_plugins/test_hires_transition_plugin.py
git commit -m "test: prove a plugin can drive the hi-res renderer with its own sprite"
```

---

### Task 4: Authoring docs example

**Files:**
- Modify: a plugins authoring/extending page under `docs/site/src/content/docs/plugins/` (pick the page that documents adding a transition; likely `plugins/extending/` or an authoring chapter — read the dir first)

- [ ] **Step 1: Read DOCS-STYLE + find the home**

Read `docs/DOCS-STYLE.md`. List `docs/site/src/content/docs/plugins/` and its `authoring/` + `extending/` subdirs; find where transitions are documented for plugin authors. If a transitions-in-plugins section exists, extend it; otherwise add a short subsection to the most relevant extending/authoring page. Do NOT invent a whole new page.

- [ ] **Step 2: Add the example**

Add a concise subsection — "Hi-res sprite transitions" — explaining that a plugin transition can drive the bigsign hi-res renderer by holding its own `HiresSpec` and calling `render_hires_frame` on a `ScaledCanvas`, with a lo-res fallback. Use a `TomlExample`/code block matching the page's components. The code (mirrors the approved brainstorm snippet):

```python
from pathlib import Path
from led_ticker.plugin import HiresSpec, ScaledCanvas, render_hires_frame

_HERE = Path(__file__).parent
_SPEC = HiresSpec(
    sprite_path=_HERE / "sprites" / "zoom.gif",
    flip_horizontal=False,
    trail="black",   # "none" | "black" | "rainbow"
)

def register(api):
    @api.transition("zoom")
    class Zoom:
        def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
            if t >= 1.0:
                incoming.draw(canvas, cursor_pos=0)
                return canvas
            if isinstance(canvas, ScaledCanvas):   # bigsign → hi-res
                return render_hires_frame(t, canvas, outgoing, incoming, _SPEC)
            # small sign / tests → your own lo-res fallback
            return self._lowres(t, canvas, outgoing, incoming, **kwargs)
```

Note the sprite ships with the plugin (a gif/webp; scaled to panel height at decode) and that `trail` fills behind the sprite to erase outgoing text. Keep it tight — follow the DOCS-STYLE rubric.

- [ ] **Step 3: Lint**

Run: `make docs-lint`. Fix/`make docs-format` as needed.

- [ ] **Step 4: Commit**

```bash
git add docs/site/src/content/docs/plugins/
git commit -m "docs: authoring example for hi-res plugin transitions"
```

---

### Task 5: Full verification + PR

- [ ] **Step 1: Full suite + lint**

Run: `make test` — all pass (baseline was 2945+ passed / 2 skipped; this adds ~6 tests). Coverage ≥ 90%.
Run: `make lint` — clean.

- [ ] **Step 2: Confirm no stale `registry_name` caller remains**

Run: `grep -rn "load_hires(\|render_hires_frame(" src/ tests/ | grep -v "load_hires_font"`
Expected: every `render_hires_frame(` call passes a spec (the 4 built-in sites + the proof test); no call passes a bare registry-name string. `load_hires(` is called only inside `_hires_loader.py` + the new loader test, always with a spec.

- [ ] **Step 3: Push + PR**

```bash
git push -u origin worktree-feat+hires-transition-plugin-api
gh pr create --title "feat: hi-res transition plugin API (P2)" --body "$(cat <<'EOF'
## Summary
- `render_hires_frame` / `load_hires` now take a `HiresSpec` directly instead of looking it up by name in the core-internal `HIRES_REGISTRY` — removing the back-edge that made the hi-res sprite path unreachable by plugins (P2 from the extraction review).
- `HiresSpec` and `render_hires_frame` are now on the public `led_ticker.plugin` surface; `HIRES_REGISTRY` stays internal as the built-ins' catalog.
- Built-in `nyancat`/`pokeball` resolve their spec from the registry at the call site and pass it — behavior unchanged (the one non-lookup use of the name, the procedural-ball gate, became the `show_pokeball` kwarg the classes already pass).
- Unblocks extracting the sprite transitions into a plugin (`led-ticker-arcade`) without silently regressing to lo-res on the bigsign.

Spec: docs/superpowers/specs/2026-06-15-hires-transition-plugin-api-design.md

## Test plan
- [ ] `make test` green; `make lint` / `make docs-lint` clean
- [ ] New: tests/test_hires_loader.py (spec-based unit + cache), tests/test_plugins/test_hires_transition_plugin.py (out-of-tree plugin renders hi-res with no registry entry)
- [ ] Existing nyancat/pokeball/transitions tests unchanged (built-in behavior preserved)
- [ ] Plugin API drift guard updated for the two new exports

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes
- **Spec coverage:** loader refactor (Task 1) · built-in resolve-then-pass + `has_ball_class`→kwarg (Task 1) · public export (Task 2) · drift/docs (Task 2) · plugin-proof test with tmp_path sprite (Task 3) · cache-on-spec test (Task 1) · authoring example (Task 4) · grep for stale callers (Task 5). All spec sections mapped.
- **Type consistency:** `render_hires_frame(..., spec: HiresSpec, **kwargs)` and `load_hires(spec: HiresSpec) -> HiresFrames` used identically across Tasks 1, 3, the docs, and the proof test. `HiresSpec(sprite_path, flip_horizontal, trail)` constructor matches the frozen dataclass.
- **Regression guards:** existing nyancat/pokeball/transitions suites (Task 1 step 5) are the behavior-preservation proof; the `show_pokeball` default-False change is behavior-preserving because pokeball passes it explicitly and nyancat never did.
