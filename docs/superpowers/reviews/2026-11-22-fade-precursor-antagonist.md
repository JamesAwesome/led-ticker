# Antagonist loop — `fade` PRECURSOR PR (branch `fade-precursor`)

Target: the diff `origin/main..fade-precursor` (PixelBuffer Clear/Fill/SetImage +
pixel-equality tripwire; breaker helpers; runner kwargs + API (1, 5) + docs;
meta `end_firing` forward; `rgb_shape_error` relocation + import tripwires).
Design: `docs/superpowers/specs/2026-11-21-fade-design.md`. Plan:
`docs/superpowers/plans/2026-11-22-fade-transition.md`.
Rules: fresh reviewer per cycle, full diff each time, cap 5, exit when only
LOW/DOCS remain (folded in). Pre-existing issues outside the diff do not count.
Contract under test: behaviour-free for every existing config (dissolve demo
29/29 frames byte-identical vs origin/main before cycle 1).

## Cycle 1

Reviewer: fresh subagent. Baseline it verified: full suite 5367 passed / 5 skipped; 53/53 `frame_at` defs across both repos take `**kwargs` and every splat sink reads keys via `.get`; the import-cycle tripwire reproduces the cycle on a scratch copy; no Mock children reach `_PickAhead`. VERDICT: 0 HIGH, 1 MEDIUM, 2 LOW, 3 DOCS.

- MEDIUM `plugin.py` / CLAUDE.md documented `(1, 4)` as a shipped `frames_to_rest` guarantee that is NOT in this tree (#561 is unmerged). FOLDED: both now say "(1, 4) reserved by open PR #561, not in this tree; minors are never reused". Merge order (#561 first, or renumber) stays in the PR body.
- LOW 10 pyright errors in the two new test files. FOLDED: `text_kw: dict[str, Any]`; `_Recorder.min_frames = 0`.
- LOW the widget tripwire never drove `Fill` / `Clear` on `PixelBuffer` (image widgets without `bg_color` take `_paint_full`). FOLDED: `image_bg` parametrisation (gif/image with `bg_color` -> `reset_canvas` Fill + skip-black per-pixel path) and the hires font now also at the scale-2 geometry; 121 cells.
- DOCS the design said #561 claims `(1, 5)` (a global replace artefact). FOLDED: `(1, 4)`.
- DOCS api-reference enumerates (1,1),(1,2),(1,3),(1,5). ACCEPTED as is: the hole is true for this tree; the second PR to merge reconciles the sentence (noted in the PR body).
- DOCS user-facing text named `fade` before it exists. FOLDED: `docs/plugin-system.md` says "the upcoming core `fade`"; `colors.py` docstring generalised. Code comments in `render_breaker.py` / `transitions/__init__.py` / `meta.py` keep the name (the feature PR lands it).
- Pre-existing, out of scope: `HeadlessCanvas.SetImage` and the new slow path both `TypeError` on `L` / `P` images (the real binding rejects non-RGB anyway); `_normalize_bg` passes a list through; bare `uv run pyright` has 426 baseline errors.
