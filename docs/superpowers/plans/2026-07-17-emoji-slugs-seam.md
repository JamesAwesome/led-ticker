# emoji_slugs() Plugin-Surface Seam Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export `emoji_slugs()` on `led_ticker.plugin` so plugins can enumerate the currently drawable emoji set (spec: monorepo `docs/superpowers/specs/2026-07-17-flair-stickers-transition-design.md` — the `flair.stickers` transition's random mode and slug validation both consume it).

**Architecture:** One pure accessor in `pixel_emoji.py` (union of the lazily-materialized low-res registry and `HIRES_REGISTRY`, so plugin-committed slugs are included), re-exported through `plugin.py` `__all__`, with the api-reference docs row the drift test demands.

**Tech Stack:** Python 3.14, pytest. Working copy: `/Users/james/projects/github/jamesawesome/led-ticker-emoji-seam`, branch `emoji-slugs-seam` (run `git branch --show-current` first; abort if it prints anything else).

## Global Constraints

- No `from __future__ import annotations`.
- The accessor must include plugin-registered slugs committed into either registry at call time, and must trigger built-in materialization (call `_get_registry()`, never read `EMOJI_REGISTRY` raw — the lazy-load sentinel comment at `pixel_emoji._get_registry` explains why).
- Test command: `uv run --extra dev pytest <file> -q`. Lint before push: `uv run --extra dev ruff check src/ tests/`.

---

### Task 1: The accessor + docs row + tests

**Files:**
- Modify: `src/led_ticker/pixel_emoji.py` (new function, after `_get_registry`)
- Modify: `src/led_ticker/plugin.py` (import + `__all__`)
- Modify: `docs/site/src/content/docs/plugins/api-reference.mdx` (one table row)
- Test: `tests/test_pixel_emoji.py` (append), `tests/test_docs_plugin_api_drift.py` (no edit needed — it must PASS after the mdx row lands)

**Interfaces:**
- Produces: `led_ticker.plugin.emoji_slugs() -> tuple[str, ...]` — sorted, deduped; the flair plan consumes exactly this name/signature.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pixel_emoji.py`:

```python
class TestEmojiSlugs:
    def test_returns_sorted_core_slugs(self):
        from led_ticker.pixel_emoji import emoji_slugs

        slugs = emoji_slugs()
        assert isinstance(slugs, tuple)
        assert list(slugs) == sorted(set(slugs)), "sorted + deduped"
        for known in ("taco", "sun", "moon", "star", "heart", "pride"):
            assert known in slugs
        assert "fire" not in slugs  # not in the set; the flagship typo

    def test_includes_plugin_committed_slugs(self, monkeypatch):
        from led_ticker import pixel_emoji

        monkeypatch.setitem(
            pixel_emoji.EMOJI_REGISTRY, "testplug.widget", [(0, 0, 255, 0, 0)]
        )
        assert "testplug.widget" in pixel_emoji.emoji_slugs()

    def test_exported_on_plugin_surface(self):
        import led_ticker.plugin as plugin

        assert "emoji_slugs" in plugin.__all__
        assert plugin.emoji_slugs is not None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --extra dev pytest tests/test_pixel_emoji.py -q -k EmojiSlugs`
Expected: FAIL (`cannot import name 'emoji_slugs'`).

- [ ] **Step 3: Implement the accessor**

In `src/led_ticker/pixel_emoji.py`, directly below `_get_registry`:

```python
def emoji_slugs() -> tuple[str, ...]:
    """Sorted slugs currently drawable inline (built-ins + plugin-registered).

    Union of the low-res registry (via the lazy `_get_registry()`
    materializer) and `HIRES_REGISTRY`, so a slug present in either form is
    listed. Public via `led_ticker.plugin` — plugins use it to enumerate or
    validate emoji (e.g. flair.stickers' random mode / knob validation).
    """
    return tuple(sorted(set(_get_registry()) | set(HIRES_REGISTRY)))
```

In `src/led_ticker/plugin.py`: add `emoji_slugs` to the existing `from led_ticker.pixel_emoji import (...)` block (alphabetical position, next to `draw_emoji_at`) and to `__all__` (alphabetical position).

- [ ] **Step 4: Run the new tests + the drift test to see the docs gap**

Run: `uv run --extra dev pytest tests/test_pixel_emoji.py -q -k EmojiSlugs tests/test_docs_plugin_api_drift.py -q`
Expected: EmojiSlugs tests PASS; the drift test FAILS naming `emoji_slugs` as missing from the mdx.

- [ ] **Step 5: Add the api-reference row**

In `docs/site/src/content/docs/plugins/api-reference.mdx`, in the same drift-guarded table that holds the `hires_text_width(...)` row (line ~188), add (matching the surrounding table format exactly):

```
| `emoji_slugs()`                                                            | Sorted tuple of every slug currently drawable inline — built-ins plus plugin-registered emoji. Enumerate for random pickers; validate config-provided slugs against it |
```

- [ ] **Step 6: Full verification**

Run: `uv run --extra dev pytest tests/test_pixel_emoji.py tests/test_docs_plugin_api_drift.py tests/test_plugin_surface.py -q` (skip the last file if it doesn't exist) then `uv run --extra dev ruff check src/ tests/`
Expected: all pass, lint clean.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/pixel_emoji.py src/led_ticker/plugin.py docs/site/src/content/docs/plugins/api-reference.mdx tests/test_pixel_emoji.py
git commit -m "feat(plugin): emoji_slugs() — enumerate drawable emoji on the plugin surface"
```

---

### Task 2: Full suite, push, PR

- [ ] **Step 1:** `uv run --extra dev pytest -q` from the repo root. Expected: full suite passes (4151+).
- [ ] **Step 2:** `git push -u origin emoji-slugs-seam`, then `gh pr create` — title `feat(plugin): emoji_slugs() enumeration seam`, body: what/why (three sentences: flair.stickers needs enumeration for random mode + config-load slug validation; spec link to the monorepo spec path; one-function seam + docs row + tests), standard footer. Watch `gh pr checks` to green. Do NOT merge without user go-ahead.
- [ ] **Step 3 (post-merge, on approval):** release core vNext via `uv run python scripts/cut_release.py minor --notes <notes-file>` (minor: new public API). The flair PR floors this release.
