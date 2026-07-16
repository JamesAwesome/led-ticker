# Core: `hires_text_width` + `fit_text_size` public API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Promote the measured-clearance layout mechanism (proven in the stocks plugin's collision fixes, needed next by flight) to core's public plugin surface, so first- and third-party plugins can guard positioned hi-res text without hand-rolling width math.

**Architecture:** Two small functions in `drawing.py`, re-exported via `led_ticker.plugin` (`__all__` is the contract): `hires_text_width` (real-px advance, riding `HiresFont.resolve_glyph` so measurement is glyph-fallback-aware and can never drift from the draw — the U+2212 class) and `fit_text_size` (the generic shrink-to-fit ladder). **Mechanism only — ladder values stay per-plugin** (they're design decisions; PM review 2026-07-16).

**Tech Stack:** core `led-ticker` repo, Python 3.14, pytest; docs-site api-reference drift test guards `__all__`.

## Global Constraints

- **Public API is a one-way door** — exactly these two functions, minimal signatures, nothing else (no ladder constants, no layout helpers).
- Adding to `plugin.__all__` REQUIRES updating `docs/site/src/content/docs/plugins/api-reference.mdx` inside the `<!-- api-exports:start/end -->` markers — `tests/test_docs_plugin_api_drift.py` fails loudly otherwise.
- No `from __future__ import annotations` in new code paths that plugins touch.
- Gates before any commit: `uv run --extra dev pytest -q` (full suite), `uv run --extra dev ruff check src/ tests/`, `make docs-build` + `make docs-lint` if the docs page changed.
- Commit messages end with exactly:
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_015czjSP4i45aZxX717Zh9yS

## File Structure

- `src/led_ticker/drawing.py` — **modify**: add the two functions (natural home; `get_text_width` lives here and its hires branch is the advance-summing pattern to reuse).
- `src/led_ticker/plugin.py` — **modify**: import + `__all__` entries.
- `docs/site/src/content/docs/plugins/api-reference.mdx` — **modify**: the `api-exports` region (+ a short row describing each).
- Test: `tests/test_drawing.py`, `tests/test_docs_plugin_api_drift.py` (existing, must stay green).

---

## Task 1: the two functions in `drawing.py`

**Interfaces (produces):**
- `hires_text_width(text: str, size: int, *, font: str = "Inter-Bold", threshold: int | None = None) -> int` — physical advance width. Resolves via `resolve_font(font, size[, threshold])`; for a `HiresFont`, sums `resolve_glyph(c).advance` (fallback-aware — U+2212 measures as the hyphen it will draw as, per the #393 mechanism) with the `'?'` advance for unknowns; for a BDF font, sums `CharacterWidth` (logical px). `threshold=None` uses core's default; plugins that paint at a custom threshold (stocks/flight use 80) pass it so the font-cache entry is shared with their paint.
- `fit_text_size(text: str, sizes: Sequence[int], max_width: int, *, font: str = "Inter-Bold", threshold: int | None = None) -> int` — largest size in `sizes` (try in order) at which the text fits `max_width`; the LAST entry is the floor (returned even if it doesn't fit — callers ship a floor they can live with). Empty `sizes` raises `ValueError`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_drawing.py`:

```python
class TestHiresTextWidthAndFit:
    def test_width_positive_and_grows_with_size(self):
        from led_ticker.drawing import hires_text_width

        w22 = hires_text_width("EUR/USD", 22)
        w11 = hires_text_width("EUR/USD", 11)
        assert w22 > w11 > 0

    def test_minus_sign_measures_as_hyphen(self):
        """U+2212 draws as the hyphen glyph (resolve_glyph fallback) — the
        measurement must agree with the draw, or right-aligned negatives
        drift (the stocks '?'-overlap class)."""
        from led_ticker.drawing import hires_text_width

        assert hires_text_width("−1.98%", 22) == hires_text_width("-1.98%", 22)

    def test_threshold_param_accepted(self):
        from led_ticker.drawing import hires_text_width

        # Same advances regardless of threshold (threshold affects lit
        # pixels, not advances) — the param exists for font-cache sharing.
        assert hires_text_width("AAPL", 22, threshold=80) == hires_text_width(
            "AAPL", 22
        )

    def test_fit_keeps_design_size_when_it_fits(self):
        from led_ticker.drawing import fit_text_size

        assert fit_text_size("AAPL", (22, 18, 11), 10_000) == 22

    def test_fit_steps_down_and_result_fits(self):
        from led_ticker.drawing import fit_text_size, hires_text_width

        budget = hires_text_width("64,906.62", 22) - 1  # 22 must NOT fit
        size = fit_text_size("64,906.62", (22, 18, 16, 14, 12, 11), budget)
        assert size < 22
        assert hires_text_width("64,906.62", size) <= budget or size == 11

    def test_fit_floor_when_nothing_fits(self):
        from led_ticker.drawing import fit_text_size

        assert fit_text_size("WWWWWWWWWW", (22, 11), 1) == 11

    def test_fit_empty_sizes_raises(self):
        import pytest

        from led_ticker.drawing import fit_text_size

        with pytest.raises(ValueError):
            fit_text_size("X", (), 100)
```

- [ ] **Step 2: Run to verify failure** — `uv run --extra dev pytest tests/test_drawing.py -q -k HiresTextWidth` → FAIL (ImportError).

- [ ] **Step 3: Implement** in `src/led_ticker/drawing.py` (module scope, near `get_text_width`; reuse its imports — `HiresFont` is already imported there; add `resolve_font` import from `led_ticker.fonts` and `Sequence` from `collections.abc` if absent):

```python
def hires_text_width(
    text: str, size: int, *, font: str = "Inter-Bold", threshold: int | None = None
) -> int:
    """Physical advance width of `text` in hi-res `font` at `size`.

    Measures with the SAME glyph resolution the renderer draws with
    (`HiresFont.resolve_glyph`, ASCII-fallback-aware), so collision math in
    widget/plugin layouts can never drift from the paint — a 'clearance'
    computed here is a real on-panel clearance on any platform's font
    metrics. `threshold` is forwarded to `resolve_font` so a caller that
    paints at a custom threshold shares the same font-cache entry.
    """
    if threshold is None:
        resolved = resolve_font(font, size)
    else:
        resolved = resolve_font(font, size, threshold)
    if isinstance(resolved, HiresFont):
        fallback = resolved.glyphs.get("?")
        fallback_advance = fallback.advance if fallback else 0
        total = 0
        for ch in text:
            glyph = resolved.resolve_glyph(ch)
            total += glyph.advance if glyph is not None else fallback_advance
        return total
    return sum(resolved.CharacterWidth(ord(ch)) for ch in text)


def fit_text_size(
    text: str,
    sizes: "Sequence[int]",
    max_width: int,
    *,
    font: str = "Inter-Bold",
    threshold: int | None = None,
) -> int:
    """Largest size in `sizes` (tried in order) at which `text` fits
    `max_width` physical px; the LAST entry is the floor, returned even when
    nothing fits — pick a floor you can live with. The shrink-to-fit half of
    the measured-clearance pattern: content keeps its design size unless it
    would actually collide, then steps down a caller-owned ladder (ladder
    VALUES are per-layout design decisions and do not live in core).
    """
    last: int | None = None
    for size in sizes:
        last = size
        if hires_text_width(text, size, font=font, threshold=threshold) <= max_width:
            return size
    if last is None:
        raise ValueError("fit_text_size: `sizes` must be non-empty")
    return last
```

(Adjust the `resolve_font` call to its actual signature — verify whether `threshold` is positional or keyword in `led_ticker.fonts.resolve_font` and match it.)

- [ ] **Step 4: Run to verify pass** — the new tests + the whole `tests/test_drawing.py`.
- [ ] **Step 5: Full suite + ruff.** Expected: all pass (only additions).
- [ ] **Step 6: Commit** — `feat(drawing): hires_text_width + fit_text_size — measured-clearance layout primitives`.

---

## Task 2: export on the plugin surface + docs

- [ ] **Step 1: RED via the drift test.** Add to `src/led_ticker/plugin.py`: extend the existing `from led_ticker.drawing import (...)` block with `fit_text_size, hires_text_width` (alphabetical) and add both names to `__all__` (alphabetical). Run `uv run --extra dev pytest tests/test_docs_plugin_api_drift.py -q` → FAILS naming the two missing symbols (proves the tripwire sees them).
- [ ] **Step 2: GREEN — update the docs page.** In `docs/site/src/content/docs/plugins/api-reference.mdx`, inside `<!-- api-exports:start -->…end -->`, add the two entries following the page's existing row format, with one-line descriptions: *`hires_text_width` — physical advance width of hi-res text, measured with the renderer's own glyph resolution (collision math can't drift from the paint)*; *`fit_text_size` — largest size from a caller-owned ladder at which text fits a px budget (shrink-to-fit guard for positioned layouts)*. Re-run the drift test → PASS.
- [ ] **Step 3: Gates.** Full suite + ruff + `make docs-build` + `make docs-lint`.
- [ ] **Step 4: Commit** — `feat(plugin): export hires_text_width + fit_text_size on the public surface`.

---

## Post-implementation

- **PR** (core): include the motivation (stocks #54's three collision surfaces; flight is the next consumer; third-party availability requires the public surface). CI green → **core release vNext** (James approves; release automation ships it). The plugins sweep (companion plan in the monorepo: `2026-07-16-layout-guards-sweep.md`) gates its code tasks on this release.
- Note in the PR: mechanism only — ladders deliberately NOT in core.

## Self-Review

Coverage: both functions (T1) ✓, export + drift-guarded docs (T2) ✓, release handoff ✓. Placeholders: none — full code + tests inline; the one verify-against-source note (resolve_font's threshold parameter shape) is explicit. Type consistency: `font: str`/`threshold: int | None` identical across both; `fit_text_size` delegates to `hires_text_width`.
