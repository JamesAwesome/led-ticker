# Design: reduce `gif_plan` to the token-saving kernel

**Date:** 2026-05-18
**Status:** Approved (brainstorm), pending spec review → implementation plan
**Branch:** `slim-gif-plan`

## Problem

`tools/gif_plan/` grew to ~2,000 lines + 169 tests across `widgets.py` /
`totals.py` / `flags.py` / `plan.py`, four review rounds, an unmerged
"shared leaf" PR (#73), and a measured-engine spike. Its actual job is
narrow: help **Claude** (via the `making-a-gif` skill) not burn tokens
re-rendering demo gifs because the `--duration` was guessed wrong. The
elaborate per-widget fidelity, seven heuristic flags, JSON breakdown,
and long skill prose are machinery bloat — token cost paid on every
invocation/skill-load — out of proportion to that job, and the chief
source of the recurring transcription bugs.

Decision (brainstorm): cut hard. Keep only what stops a wasted
re-render — a calibrated-enough `--duration` and a one-line "the
pinned header is too short, it will clip" guard. Accept a rougher
estimate.

## Goal / non-goals

**Goal:** the smallest deterministic surface that lets Claude pick a
`--duration` in one shot and not ship a clipped gif.

**Non-goals:** precise per-widget timing; the 6 advisory flags;
JSON/per-section breakdown; engine-accuracy parity; the shared-leaf or
measured-engine architectures.

## Design

### Estimator (`tools/gif_plan/plan.py`, single module ~80–100 lines)

- `canvas_w = cols * chain // scale`.
- One coarse `widget_ms(widget, section)` — dominant magnitude terms
  only (keeps the binary clip call trustworthy; drops every nuance that
  caused the bugs):
  - text (`message` / `countdown` / `two_row`):
    `hold_ms + max(0, content_w − canvas_w) × step_ms`, where
    `hold_ms = section.hold_time` (default 3.0s),
    `content_w = len(text) × 6  +  8 × emoji_count`,
    `step_ms = section.scroll_step_ms or 50`. No font-size / hires /
    two-row-overlay / wrap / scroll_through branching.
  - `image` / `still`: `hold_seconds × 1000` (default 5.0).
  - `gif`: `sum(frame_durations) × gif_loops` if the path resolves,
    else `section.hold_time`; `gif_loops == 0` → `section.hold_time`.
    Path resolved against the **config file's directory** (the one
    fix retained from the critical round-3 bug — ~4 lines).
- `total` = Σ `widget_ms × loop_count` over `swap`-mode sections.
  `forever_scroll` / `infini_scroll` / `loop_count == 0` sections
  contribute 0 (documented out of scope).
- `recommended = max(1, ceil(total / 1000) + 1)`.
- Cutoff: a `# render-duration: N` header present with
  `N * 1000 < total` is a clip.

### CLI contract

Reads a TOML path. Output is at most two lines:

```
duration: 8
```

…and, only when the header clips:

```
duration: 8
cutoff: header 5s < ~8s needed
```

Exit codes: `0` clean · `2` cutoff · `3` tool error (missing/malformed
TOML, message on stderr, stdout empty). No `1`/warnings tier, no
`--json`, no flags, no per-section/widget breakdown.

### Files

- **Rewrite:** `plan.py` (the single module above).
- **Delete:** `widgets.py`, `totals.py`, `flags.py`, `README.md`,
  `test_widgets.py`, `test_totals.py`, `test_flags.py`,
  `test_dogfood.py`.
- **Keep:** `__init__.py`, `conftest.py` (sys.path shim for the tests).
- **New:** one `test_plan.py`, ~12–15 tests — `widget_ms` per type,
  the cutoff comparison, exit codes 0/2/3, config-relative gif path
  resolution, and a thin sanity loop over every pinned demo asserting
  **exit ∈ {0, 2} and `recommended` is a positive int** (no accuracy
  assertion at all). This replaces the 70-case ±20% dogfood + the
  xfail list outright — the precision pin is deleted, not loosened.

Net: ~2,000 lines + 169 tests → ~120 lines + ~15 tests.

### Docs

- `docs/site/src/content/docs/tools/gif-plan.mdx`: cut to a short page
  — one-paragraph "what it does", the one command, the two-line
  output, the exit codes, one out-of-scope sentence
  (`forever_scroll` / `loop_count=0` / data-fetch / `pixel_mapper_config` /
  rough estimate). Delete the flag table, the `# render-duration:`
  deep-dive, the sharp-edge subsection, per-widget detail.
- `docs/site/src/content/docs/reference/cli.mdx`: `make plan-gif` row
  kept (still accurate).

### Skill (the per-load token cost — the real target)

- `.claude/skills/making-a-gif/SKILL.md`: ~100 → ~35–45 lines.
  Keep: condensed docs-vs-dev mode detection, the
  `make plan-gif → duration → render` step, brief docs-mode
  contrast/caption judgment. Drop: JSON-schema block, exit-code table,
  long bullet lists, redundant prose.
- `.claude/skills/making-a-gif/examples/`: collapse `dev-mode.md` +
  `docs-mode.md` into one short `example.md` (~25 lines).

### CI / packaging

No change. PR #71's gated `gif-plan-test` job and the `pyproject`
`testpaths` entry stay valid (fewer tests, same wiring). `make
plan-gif`, `Makefile` target unchanged.

### In-flight cleanup (outward/destructive — confirm at execution)

- Close PR #73 (leaf spike): its premise (maintain a shared mirror) is
  largely deleted.
- Remove spike worktrees + branches `spike/gif-plan-engine-coupling`
  and `spike/measured-plan-harness`. `main` is clean (none merged) —
  nothing to revert there.

## Risks / accepted trade-offs

- **Rougher estimate.** Ignores wrap floors, two-row overlay marquee,
  scroll-step nuance, hires width. Accepted: it stays calibrated for a
  binary "will it clip?", not as a precise predictor. The pinned-demo
  sanity test asserts only "no crash + positive int" — there is no
  accuracy band; the old ±20% pin is deleted, not relaxed.
- **Some demos may now read as borderline** where the precise tool was
  exact. Acceptable: the cost of a slightly-off duration is one
  re-render; the cost of the machinery was perpetual maintenance + the
  bug stream.
- **Lost capability** (per-widget JSON, advisory flags) is intentional
  YAGNI for the Claude-token goal; recoverable from git if ever needed.

## Success criteria

- `tools/gif_plan/` is one module + one test file; no `widgets/totals/
  flags` split.
- CLI emits ≤2 lines; exit codes 0/2/3 only.
- `make plan-gif` runs clean on every pinned demo and emits an integer
  duration.
- SKILL.md + examples materially shorter (target ≥ 50% fewer lines).
- Full suite green; CI `gif-plan-test` job green with the pruned tests.
