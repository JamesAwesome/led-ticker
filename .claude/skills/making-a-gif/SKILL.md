---
name: making-a-gif
description: Use when a user or sub-agent wants to plan or make a demo gif of a led-ticker config. Triggers on "make a gif of...", "demo gif for X", "what render-duration should I use", "preview this widget". Gets the render --duration from tools/gif_plan, adds LED-panel colour/contrast judgement, and proposes the exact make render-demo command.
---

# Making a led-ticker Demo Gif

Two modes: **docs** (polished — source TOML committed under `docs/site/demos-pinned/`, rendered gif under `docs/site/public/demos-pinned/`) and **dev** (throwaway preview to `/tmp/`). Docs signals: "for docs", "add to demos-pinned", a `docs/site/` path, captions/commit. Dev signals: "preview", "spot check", sub-agent iterating on a feature, `/tmp/` output. If ambiguous, ask which. Announce: "Using making-a-gif skill in **<mode>** mode."

## Steps

1. **Get a TOML.** Pasted config → save to `/tmp/gif-plan-<topic>.toml`. A path → use as-is. Only an intent described → draft a minimal config, save to `/tmp/`.

2. **Get the duration:** `make plan-gif CONFIG=<path>` (from repo root). It prints `duration: <N>` and, if a `# render-duration:` header is too short, a `cutoff: header Xs < ~Ys needed` line (relay it verbatim) + non-zero exit.
   - **If the source TOML already has a `# render-duration: H` header, `H` is the intended capture window — render with `H`. `<N>`/`cutoff:` are advisory only; never override an existing header with `<N>`.** Looping / large-`gif_loops` demos (the `gif_loops = 999` "keep animating" idiom) deliberately pin a short `H` while `<N>` reports the multi-minute full playthrough — exit `2` there is *expected*, not a bug. Keep `H`.
   - Only when there is **no** header (a brand-new demo): use `<N>` as the `--duration` and add `# render-duration: <N>` to the TOML.
   - Exit `3` = bad path/TOML (fix and re-run, not a result).

3. **Colour/contrast judgement** (the tool does NOT do this — you do). Scan colour fields (`font_color`, `top_color`, `bottom_color`, `bg_color`, `border`, separators):
   - Pure black `[0,0,0]` → renders INVISIBLE on the panel. Warn unless used intentionally as "transparent"; suggest `[10,10,10]` or a brand colour.
   - Pure white `[255,255,255]` → washes blue-white. Suggest cream `[254,255,204]`.
   - Dark-on-dark (luminance Δ < 30) → low-contrast risk; suggest previewing at `brightness = 60`.
   - Brand fallbacks: magenta `[225,48,108]`, cream `[254,255,204]`, cyan `[120,230,255]`, soft pink `[255,176,240]`, lavender `[189,169,234]`.

4. **Caption (docs mode only).** Read 2-3 existing `<DemoGif caption="...">` lines from `docs/site/src/content/docs/widgets/<widget>.mdx` and match their matter-of-fact, visual voice.

5. **Surface the recommendation:** the chosen duration, any cutoff/colour notes, and the exact command. `make render-demo` does NOT pass `--duration` (it uses the renderer default), so render at a specific length via the direct renderer:
   - Docs, existing/pinned demo (TOML has `# render-duration: H`): render at the header — `uv run python tools/render_demo/render.py docs/site/demos-pinned/<name>.toml -o docs/site/public/demos-pinned/<name>.gif --duration H`. (Or `make render-pinned-demos` to rebuild the whole pinned set, which reads each header.) Do not change `H` to `<N>`.
   - Docs, new demo (no header yet): add `# render-duration: <N>` to the TOML, then `uv run python tools/render_demo/render.py docs/site/demos-pinned/<name>.toml -o docs/site/public/demos-pinned/<name>.gif --duration <N>`.
   - Dev: `uv run python tools/render_demo/render.py /tmp/gif-plan-<topic>.toml -o /tmp/preview-<topic>.gif --duration <N>`. A shorter duration (one pass + a beat) is fine — verification, not a polished loop.

## Don'ts

- Don't run `make render-demo` yourself — rendering takes ~10s and the user usually iterates the config first. Suggest the command.
- Don't modify the user's config unless asked.
- Don't hand-compute durations — that's what `make plan-gif` is for; re-invoke it instead.

See `examples/example.md` for an end-to-end walkthrough.
