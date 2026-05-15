# Making-a-gif Skill — Design

**Date**: 2026-05-15
**Repo**: led-ticker
**Status**: Spec approved by user via brainstorming session; ready for plan + implementation.

## Goal

Ship a project-local skill that assists with making LED-panel demo gifs from led-ticker configs. The skill should:

1. Compute deterministic playtime / cycle math (no Claude approximation).
2. Catch common mistakes before the user invokes `make render-demo` — especially "render-duration cuts the scroll mid-pass" and "scroll_step_ms out of readable range."
3. Add a judgment overlay for things that aren't easily deterministic — LED panel color/contrast quirks, caption drafting, suggesting which `# render-duration:` value to pick when several are reasonable.
4. Support two distinct use cases: (a) polished demos destined for `docs/site/public/demos-pinned/`, and (b) throwaway dev-mode previews for spot-checking work in progress.

## Non-goals

- Generic gif tooling outside led-ticker. The skill bakes in led-ticker assumptions (`tools/render_demo/`, the `# render-duration:` header convention, widget config schema, panel rendering quirks).
- Replacing or wrapping `tools/render_demo/render.py`. The skill helps users *plan* renders; it does not render.
- Running renders unprompted. Rendering takes ~10 seconds and the user often iterates on the config first.
- Validating `forever_scroll` / `infini_scroll` mode durations deterministically. Those modes' timing is data-dependent — the skill emits an info note and tells the user to render empirically.

## Architecture

Two pieces, each independently testable.

### 1. `tools/gif_plan/` — deterministic Python CLI

Pure math + simple heuristics. Reads a config TOML, outputs a structured plan. Sibling to `tools/render_demo/`. Uses `tomli`/`tomllib` for config parsing and Pillow for reading gif metadata (frame count, per-frame durations) — Pillow is already in the repo env via `tools/render_demo/`. No `led_ticker` runtime dependency: the CLI doesn't import the engine, doesn't render anything, doesn't construct widgets. It works on raw TOML dicts.

**Invocation**:

```
uv run python tools/gif_plan/plan.py <config.toml> [--json] [--section N]
```

Also exposed via Makefile:

```
make plan-gif CONFIG=path/to.toml
```

**Output schema (`--json`)**:

```json
{
  "config_path": "...",
  "sections": [
    {
      "index": 0, "mode": "swap", "hold_time": 7.0, "scroll_step_ms": 25,
      "widgets": [
        {
          "index": 0, "type": "two_row",
          "pass_ticks": 360,
          "pass_ms": 9000,
          "cycle_floor": 1,
          "effective_visit_ms": 9000,
          "flags": []
        }
      ],
      "section_total_ms": 9000
    }
  ],
  "total_ms": 9000,
  "recommended_render_duration_s": 10,
  "flags": [
    {
      "severity": "warning",
      "location": "section[0].widget[0]",
      "code": "scroll_step_too_fast",
      "message": "scroll_step_ms=15 is below the readable range (20-60ms)",
      "fix": "Raise to 25 (canonical) or 30."
    }
  ]
}
```

**Default output** (no `--json`): human-readable table, ANSI-colored severity. Equivalent data.

**Exit codes**:
- `0` — clean (no flags).
- `1` — warnings only.
- `2` — errors (impossible math, e.g. zero cycle width).

### 2. `.claude/skills/making-a-gif/` — Claude-facing skill

Thin orchestration layer. The skill instructs Claude to:

1. Detect mode (docs vs dev) and intent.
2. Save inline configs to `/tmp/` if pasted.
3. Run the CLI, parse JSON output.
4. Add the judgment overlay (color/contrast, caption drafting).
5. Surface the recommendation and the exact `make render-demo` command.

No math is hardcoded in skill prose — that's the CLI's job. The skill is the user-facing layer; the CLI is the source of truth.

## Deterministic math (CLI)

All durations in milliseconds; `scroll_step_ms` is the section-level step (default 50).

### Canvas width (logical px)

```
canvas_w = (display.cols × display.chain) / section.scale
```

The bigsign's vertical-serpentine `pixel_mapper` doesn't change logical width — that math is already correct from led-ticker's engine.

### Content width approximation

Good-enough for planning, exact-enough to catch mid-pass cutoffs:

- **BDF font**: `len(text) × cell_width`. Inline `:slug:` emoji counted as 8 logical px each (or band cap when known).
- **Hi-res font**: `len(text) × ceil(font_size × 0.55)` — Inter-Bold-ish ratio. Conservative (slight overestimate is safer for "will it fit in render-duration?" checks).

The render engine measures content widths exactly at draw time; the planner approximates.

### Per-widget visit time (ms)

- **`TickerMessage` (single-row marquee)**:
  - Static fit, no wrap: `hold_time × 1000`.
  - Overflow scroll: `pass_ms = (canvas_w + content_w) × step_ms`.
  - With `text_wrap = true`: `visit_ms = max(text_loops × cycle_ms, hold_time × 1000)`. Cycle includes separator width.
- **`TwoRowMessage`**:
  - Default marquee, no wrap: bottom-row math same shape as TickerMessage scroll branch.
  - `bottom_text_wrap = true`: `visit_ms = max(bottom_text_loops × cycle_ms, hold_time × 1000)`. Cycle includes separator.
  - `bottom_text_scroll = "scroll_through"` (post PR-65 unified): `visit_ms = max(bottom_text_loops × cycle_ms, hold_time × 1000)`. Cycle = `canvas_w + bottom_width`.
- **`gif` / `image` two-row overlay**: identical shape to TwoRow scroll_through; uses `text_loops` instead of `bottom_text_loops` (CLI normalizes the cross-widget naming quirk).
- **`gif` widgets in `mode = "gif"`**: `visit_ms = sum(frame_durations) × gif_loops` if `gif_loops > 0`, else `hold_seconds × 1000` (PR-64 behavior). The CLI reads `frame_durations` via Pillow (`Image.open(path).info["duration"]` or per-frame `seek`/`info` for varying durations). If the gif path can't be resolved (missing asset, relative path with unknown root), the CLI emits a warning and falls back to assuming `100ms × n_frames` so the math doesn't crash.
- **`image` no-text-overlay**: `hold_seconds × 1000`.

### Section + playlist totals

- `section_total_ms = sum(widget_visit_ms) × section.loop_count` (for `mode = "swap"`).
- `playlist_total_ms = sum(section_total_ms)`.
- `recommended_render_duration_s = ceil(playlist_total_ms / 1000) + 1` (1s buffer to capture the trailing transition).

### Out of scope for v1

`forever_scroll` / `infini_scroll` modes. Surface as an info-severity note: "duration depends on runtime; render empirically and tune the `# render-duration:` header by inspection."

## Heuristic flags (CLI)

Three classes, each emitted as structured JSON entries.

### 1. Mid-pass cutoff (error)

- **Trigger**: a `# render-duration: N` header exists in the source TOML AND `N × 1000 < playlist_total_ms`.
- **Message**: `"render-duration: 8 cuts ~3500ms of section[1].widget[0]'s scroll mid-pass"`.
- **Fix**: suggest `recommended_render_duration_s`.
- **Special case**: if no header is present, emit an info-severity *suggestion* of `recommended_render_duration_s` instead.

### 2. Scroll-step out of band (warning)

- **Trigger**: `scroll_step_ms < 20` (too fast to read) or `scroll_step_ms > 80` (sluggish).
- **Range source**: project memory + existing demo configs (PR-59 and PR-60 both use 25-30).
- Quiet on values in [20, 80].

### 3. Zero-or-broken cycle (error)

- **Trigger**: a wrap or scroll_through widget with computed content width 0 (e.g., `text = " "` after stripping).
- **Surface**: as a math-impossible error so the user sees it before render rather than getting `ZeroDivisionError` at runtime.

### Excluded from CLI (handled by skill)

- LED panel color/contrast risks — judgment-heavy.
- Caption drafting for `<DemoGif>` tags — pure judgment.
- Picking which `# render-duration:` value when several are reasonable.

## Skill responsibilities (Claude side)

The skill at `.claude/skills/making-a-gif/SKILL.md` instructs Claude through this workflow.

### Mode detection (first step)

- **Docs mode**: signals = "demo for docs / docs-pinned", "add to widget X's docs", path under `docs/site/`, request for a caption. → Polished output: draft caption, set `# render-duration:` header in source TOML, suggest committing under `docs/site/public/demos-pinned/`.
- **Dev mode**: signals = "preview", "let me see what this looks like", "spot check", agent context like iterating on a feature, paths target `/tmp/`. → Minimal output: suggest `/tmp/preview-<topic>-<ts>.gif`, recommend a *shorter* render-duration (one pass + small beat, not a polished loop), skip caption.
- If ambiguous → one clarifying question.

### Workflow steps

1. If the user pasted a config inline → save to a temp TOML in `/tmp/`. If they referenced a path → use as-is.
2. Run `uv run python tools/gif_plan/plan.py <path> --json`. Capture stdout + exit code.
3. Parse the JSON. Exit code 2 → relay errors verbatim, stop. Exit code 1 → continue but surface warnings.
4. **Judgment overlay**: read the config's color fields. Apply project-memory rules:
   - `[0, 0, 0]` font or bg → "LED panel renders pure black as invisible; use `[10, 10, 10]` or a brand color."
   - `[255, 255, 255]` → "Pure white washes blue-white on the panel; reference `config.moonbunny.example.toml` brand palette."
   - Dark-on-dark (luminance Δ < 30) → "Low contrast risk — preview at `brightness = 60` first."
   - A small lookup table of "good brand colors" sampled from `config.bigsign.example.toml` is included in SKILL.md for fallback suggestions.
5. Surface to the user:
   - The recommended `# render-duration:` value.
   - Any flags (mid-pass, speed-out-of-band) with suggested fixes.
   - Color/contrast judgment notes.
   - The exact `make render-demo CONFIG=... OUT=...` command (path varies by mode).
6. If the user asks for a docs caption → draft one matching project style. The skill instructs Claude to read 2-3 existing `<DemoGif caption="...">` lines from a docs page first to match voice.

### What the skill stays out of

- Running `make render-demo` unprompted. Rendering takes ~10 seconds and the user often iterates on the config first.
- Modifying the user's config file unless explicitly asked.

## Trigger detection

The skill description (`description:` frontmatter) tells Claude to activate on signals including:

- "make a gif of …"
- "demo gif for X"
- "add a demo for widget Y"
- "what render-duration should I use for X"
- A pasted config + request for a gif
- "preview this widget", "let me see what this looks like" (dev mode signals)
- Agent context: working on a widget / transition feature and wanting visual verification

## File layout

```
tools/gif_plan/
├── __init__.py
├── plan.py              # CLI entry point + main logic
├── widgets.py           # per-widget math (one function per widget type)
├── flags.py             # heuristic checks (mid-pass, scroll-step, zero-cycle)
├── test_plan.py         # CLI + integration tests
├── test_widgets.py      # per-widget formula tests
└── README.md            # tool-level docs (usage + when to run)

.claude/skills/making-a-gif/
├── SKILL.md             # ~150 lines: workflow with docs/dev branch, color guidance
└── examples/
    ├── docs-mode.md     # walk through a polished docs demo
    └── dev-mode.md      # walk through a feature-iteration preview

Makefile addition:
plan-gif:  ## Plan a gif demo. Usage: make plan-gif CONFIG=path/to.toml
    uv run python tools/gif_plan/plan.py $(CONFIG)
```

## Testing

- **CLI unit tests** (`tools/gif_plan/test_plan.py`, `test_widgets.py`): one test per formula (scroll-pass duration for each widget type, wrap-cycle floor, multi-section total), one test per flag (mid-pass cutoff, scroll-step bounds, zero-cycle). ~12-15 tests. Pytest, no network.
- **Dogfood validation**: run the CLI against the 35 existing pinned demos in `docs/site/demos-pinned/`. All should produce sensible math; none should produce false-positive mid-pass cutoffs. This is a one-shot validation, not an automated suite.
- **Drift tripwire (optional)**: one test asserting CLI's `recommended_render_duration_s` is within ±10% of each existing demo's `# render-duration:` header. Catches drift if either the formulas or canonical demos change.

## Error handling

- CLI exits non-zero on math errors (zero cycle width, malformed TOML). Skill relays verbatim.
- Skill handles missing CLI gracefully: if `tools/gif_plan/plan.py` doesn't exist (skill installed in a repo where it hasn't been built yet), the skill says so and points at the build path.
- Color-judgment overlay is best-effort: if config has no explicit colors, the skill says "no color flags" rather than making things up.

## Dependencies

- `tomllib` (Python 3.11+ stdlib) with `tomli` fallback (already in the repo).
- `Pillow` (already in the repo env via `tools/render_demo/`).
- `pytest` (already used for the existing test suite).
- No new dependencies introduced.

## Open questions

None — all answered during brainstorming. The design is ready for an implementation plan.
