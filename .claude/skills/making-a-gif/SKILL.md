---
name: making-a-gif
description: Use when a user (or sub-agent) wants to plan or make a demo gif of a led-ticker config. Triggers on "make a gif of...", "demo gif for X", "what render-duration should I use", "preview this widget", or "let me see what this looks like". Computes deterministic playtime math via tools/gif_plan/, flags timing/scroll-step bugs, adds judgment-layer color/contrast guidance for LED panel quirks, and proposes the exact `make render-demo` command.
---

# Making a led-ticker Demo Gif

You are helping the user plan a demo gif for the led-ticker project. There are two modes: **docs** (polished — the source TOML is committed under `docs/site/demos-pinned/` and the rendered gif under `docs/site/public/demos-pinned/`) and **dev** (throwaway preview to `/tmp/`).

## Step 0: Detect mode

- **Docs mode** signals:
  - "demo for docs", "add to demos-pinned"
  - User points at a path under `docs/site/`
  - Mentions captions or commit message
  - Adding a new entry to a widget's docs page

- **Dev mode** signals:
  - "preview", "let me see what this looks like"
  - "spot check this", "render a quick gif"
  - Sub-agent context: iterating on a widget/transition feature
  - Output path is `/tmp/` or unset

If ambiguous, ask: "Polished demo for `docs/site/demos-pinned/`, or quick preview to `/tmp/`?"

Announce: "Using making-a-gif skill in **\<mode\>** mode."

## Step 1: Get a TOML to plan

- If the user pasted a config inline → save to `/tmp/gif-plan-<topic>.toml`.
- If the user gave a path → use it as-is.
- If the user only described intent ("make a gif of a two_row scroll_through with a long song title") → draft a minimal config inline, save to `/tmp/`, then proceed.

## Step 2: Run the deterministic planner

```bash
# From the repo root — preferred entry point (human-readable output):
make plan-gif CONFIG=<path>

# Or direct, for JSON output (requires `cd` to repo root first):
uv run python tools/gif_plan/plan.py <path> --json
```

The make target emits a human-readable summary; the direct CLI with
`--json` emits the structured payload below. Parse the JSON output. The schema:
- `total_ms`: deterministic playlist total.
- `recommended_render_duration_s`: ceiling-of-seconds + 1 buffer.
- `render_duration_header`: existing `# render-duration:` value (or null).
- `sections`: per-section breakdown.
- `flags`: list of `{severity, location, code, message, fix}`.

Exit code:
- `0` → clean.
- `1` → warnings only (relay, continue).
- `2` → errors (relay, stop until fixed).

## Step 3: Apply the judgment overlay

The CLI does NOT cover these — you do.

### LED panel color quirks

Scan the config's color fields (`font_color`, `top_color`, `bottom_color`, `bg_color`, `border`, separator colors). For each:

- **Pure black `[0, 0, 0]`** → LED panel renders this as INVISIBLE (off-pixels). Surface as a warning unless the user is intentionally using black as a "transparent" effect. Suggest `[10, 10, 10]` or a brand color.
- **Pure white `[255, 255, 255]`** → washes blue-white on the panel. Suggest `[254, 255, 204]` (cream, from `config.bigsign.moonbunny.example.toml`) for warm-white or a brand color.
- **Dark-on-dark** (luminance Δ < 30): low contrast risk. Suggest previewing at `brightness = 60` first.

### Brand color palette (sampled from config.bigsign.example.toml + moonbunny configs)

Use these as fallback suggestions when the user's color is flagged:

- Magenta (IG brand): `[225, 48, 108]`
- Cream / warm white: `[254, 255, 204]` or `[255, 240, 200]`
- Cyan: `[120, 230, 255]`
- Soft pink: `[255, 176, 240]`
- Lavender: `[189, 169, 234]`

### Caption drafting (docs mode only)

Before writing a caption, read 2-3 existing `<DemoGif caption="...">` lines from the relevant docs page (`docs/site/src/content/docs/widgets/<widget>.mdx`) to match voice. Existing captions are matter-of-fact and visual: "held magenta `BREAKING` on top, cyan `tap to subscribe` wrapping continuously on the bottom with a rainbow `*` separator". Mirror that shape.

## Step 4: Surface the recommendation

Output to the user:

1. **Math summary**: total ms, recommended render-duration, per-section breakdown.
2. **Flags from CLI**: relay verbatim with severity icons.
3. **Color/contrast notes** (from Step 3).
4. **Exact command to run**:
   - Docs mode: `make render-demo CONFIG=docs/site/demos-pinned/<name>.toml OUT=docs/site/public/demos-pinned/<name>.gif` (and update the `# render-duration:` header in the source TOML if missing).
   - Dev mode: `make render-demo CONFIG=/tmp/gif-plan-<topic>.toml OUT=/tmp/preview-<topic>-<ts>.gif`.

For dev mode, recommend a SHORTER render-duration than `recommended_render_duration_s` — just one full pass + a half-second beat, since the goal is verification, not a polished loop. Formula: `ceil(longest_widget_pass_ms / 1000) + 1`.

## What this skill does NOT do

- Run `make render-demo` itself. Rendering takes ~10 seconds; the user often iterates on the config first. Always suggest the command, never execute.
- Modify the user's config file unless explicitly asked.
- Make math judgments the CLI is supposed to make. If you find yourself computing scroll-pass duration in your head, that's a sign the CLI should be doing it — re-invoke the CLI instead.

## Examples

See `examples/docs-mode.md` and `examples/dev-mode.md` for end-to-end walkthroughs.
