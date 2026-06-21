---
name: making-a-gif
description: Use when a user or sub-agent wants to plan or make a demo gif of a led-ticker config. Triggers on "make a gif of...", "demo gif for X", "what render-duration should I use", "preview this widget". Gets the render --duration from tools/gif_plan, adds LED-panel colour/contrast judgement, and proposes the exact make render-demo command.
---

# Making a led-ticker Demo Gif

Two modes: **docs** (polished — source TOML committed under `docs/site/demos-pinned/`, rendered gif under `docs/site/public/demos-pinned/`) and **dev** (throwaway preview to `/tmp/`). Docs signals: "for docs", "add to demos-pinned", a `docs/site/` path, captions/commit. Dev signals: "preview", "spot check", sub-agent iterating on a feature, `/tmp/` output. If ambiguous, ask which. Announce: "Using making-a-gif skill in **<mode>** mode."

## Steps

1. **Get a TOML.** Pasted config → save to `/tmp/gif-plan-<topic>.toml`. A path → use as-is. Only an intent described → draft a minimal config, save to `/tmp/`.

2. **Get the duration:** `make plan-gif CONFIG=<path>` (from repo root). It prints `duration: <N>` and, if a `# render-duration:` header is too short, a `cutoff: header Xs < ~Ys needed` line (relay it verbatim) + non-zero exit.

   **The planner is a rough estimate for NEW configs only.** Its model has significant blind spots — a `cutoff:` on an EXISTING config is one signal, not a verdict:

   | Situation | What planner reports | What actually happens |
   |-----------|---------------------|----------------------|
   | `gif_loops = 999` | 999 × loop_ms (400s+) | Renderer captures cleanly at `H` |
   | `text_align = "scroll"` on gif widget | Partial overflow time | Always runs ≥ 1 full text pass (scroll floor) |
   | Intentional partial capture | "Too short" | Short `H` is deliberate (e.g. typewriter capturing part of hold) |
   | Hires fonts at `scale > 1` | 6 px/char BDF estimate | Narrower glyphs → text fits, no scroll → static GIF if re-rendered |
   | `bottom_text_loops`, `bottom_text_wrap` | Not modeled | Planner underestimates |
   | `bottom_text_scroll = "scroll_through"` | Partial overflow | Full pass = canvas_w + content_w ticks |

   **Existing configs (TOML has `# render-duration: H`):** render with `H`; never change it to `<N>` based on planner output. Surface a `cutoff:` only if none of the blind spots above explain it. Do NOT re-render existing pinned demos unless asked — even "correct" math doesn't guarantee the result looks better.

   **New configs (no header):** use `<N>` as the duration and add `# render-duration: <N>` to the TOML.

   Exit `3` = bad path/TOML (fix and re-run, not a planning result).

3. **Colour/contrast judgement** (the tool does NOT do this — you do). Scan colour fields (`font_color`, `top_color`, `bottom_color`, `bg_color`, `border`, separators):
   - Pure black `[0,0,0]` → renders INVISIBLE on the panel. Warn unless used intentionally as "transparent"; suggest `[10,10,10]` or a brand colour.
   - Pure white `[255,255,255]` → washes blue-white. Suggest cream `[255,244,214]`.
   - Dark-on-dark (luminance Δ < 30) → low-contrast risk; suggest previewing at `brightness = 60`.
   - Brand fallbacks (§6 Firebird phoenix-warm palette): flame `[255,92,38]`, ember `[214,40,57]`, amber `[255,183,3]`, cream `[255,244,214]`, dusk `[99,60,138]`. IG social-handle magenta `[225,48,108]` is the social handle color only, not a brand color.

4. **Caption (docs mode only).** Read 2-3 existing `<DemoGif caption="...">` lines from `docs/site/src/content/docs/widgets/<widget>.mdx` and match their matter-of-fact, visual voice.

5. **Surface the recommendation:** the chosen duration, any cutoff/colour notes, and the exact command. `make render-demo` does NOT pass `--duration`, so render at a specific length via the direct renderer:
   - Existing/pinned demo: `uv run python tools/render_demo/render.py docs/site/demos-pinned/<name>.toml -o docs/site/public/demos-pinned/<name>.gif --duration H`. (Or `make render-pinned-demos` to rebuild the whole pinned set from headers.)
   - New docs demo: add `# render-duration: <N>` to the TOML, then same command with `--duration <N>`.
   - Dev: `uv run python tools/render_demo/render.py /tmp/gif-plan-<topic>.toml -o /tmp/preview-<topic>.gif --duration <N>`. Shorter (one pass + a beat) is fine — verification, not a polished loop.

## Docs-sync audit (separate from planner)

When asked to verify that docs match generated GIFs, do a manual read-and-compare of the inline `<TomlExample code={...}>` blocks in `docs/site/src/content/docs/widgets/<widget>.mdx` against the actual pinned configs in `docs/site/demos-pinned/`. The planner does not help here. Key fields to verify: `hold_time`/`hold_seconds`, `path`, text content (`top_text`, `bottom_text`, `text`), and any fields called out in the adjacent caption.

## Don'ts

- Don't run the renderer yourself — rendering takes ~10s and the user usually iterates first. Suggest the command.
- Don't modify the user's config unless asked.
- Don't hand-compute durations — re-invoke `make plan-gif` instead.
- Don't change existing `# render-duration:` headers based on planner output without explicit user direction.

See `examples/example.md` for an end-to-end walkthrough.
