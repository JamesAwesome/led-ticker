# Docs Audit Findings (Phase 3a)

**Date:** 2026-06-06
**Scope:** 47 pre-rubric docs-site pages audited against `docs/DOCS-STYLE.md`, by 8 per-area technical-writer passes. **Read-only — no pages edited.** (The ~13 pages built to the rubric this effort were skipped.) Agents spot-verified factual claims against `src/`, the Makefile, and the CLI.

## Executive summary

**Overall health: good.** The vast majority of pages pass the rubric and are factually accurate — defaults, frame counts, color values, and config keys spot-checked against source overwhelmingly matched, every referenced demo GIF exists, and almost every internal link resolves. The gaps cluster into a small set of **accuracy/correctness bugs** (a handful of wrong commands/flags/field-names that would actually break or mislead a reader) plus broad, low-stakes **polish** (missing symptom-first troubleshooting boxes, unnamed readers, tutorial time-stamps).

**Worst-offending pages (grade "Needs work"):**
- `widgets/gif.mdx` — wrong field name `hold_seconds` (should be `hold_time`).
- `tools/render-demo.mdx` — documents a `--fps` flag that doesn't exist.
- `tutorial/02-first-config.mdx` — `--duration 20` is unrunnable via the documented `make render-demo`.

**Counts:** ~11 must-fix items across 10 pages; dozens of nice-to-haves (most are the same two patterns repeated: no local "if it doesn't work" box; reader not named at top).

### The must-fix list (the 11)

| # | Page | Issue | Fix |
|---|------|-------|-----|
| 1 | `widgets/gif.mdx` | `hold_seconds` used twice (caption L155, note L178) — field doesn't exist; everywhere else (incl. image.mdx) it's `hold_time` | Rename both to `hold_time` |
| 2 | `widgets/etherscan.mdx` | Says the API key goes in `.env` as `ETHERSCAN_API_KEY`, but the widget reads ONLY the TOML `api_key` field — no env substitution exists in `config.py`, and `ETHERSCAN_API_KEY` appears nowhere in `src/`. A reader following the prose hits a `ValueError` at startup | Document the working path: a literal key in the TOML `api_key` string; drop/clarify the `.env` framing (same bug in the etherscan demo TOML + fact-pack) |
| 3 | `concepts/borders.mdx` | Lightbulbs example (L219–223) uses old `[[section]]`/`[[section.widget]]` while every other block uses `[[playlist.section.widget]]` | Use `[[playlist.section.widget]]` consistently |
| 4 | `tools/render-demo.mdx` | CLI-flags table lists a `--fps N` (default 20) flag that does NOT exist in `render.py` — running it errors | Remove the row; if worth noting, state the fixed 20fps/50ms cadence in prose |
| 5 | `reference/cli.mdx` | Omits the real `plugins` subcommand (`led-ticker plugins`) | Add a `plugins` subcommand section |
| 6 | `reference/cli.mdx` | `validate` flag table (and the Tips re-list) omits `--fix` (in-place auto-migration) | Add `--fix` to the table + the Tips enumeration |
| 7 | `tutorial/02-first-config.mdx` | "pass `--duration 20`" (L~176) — `make render-demo` doesn't forward `--duration`; the very next block is a bare `make render-demo` | Drop it, or show the direct `uv run python tools/render_demo/render.py … --duration 20` invocation |
| 8 | `tutorial/03-multi-widget.mdx` | "hi-res path activates when `default_scale > 1`" (L~294) contradicts the per-section-`scale` mechanism the chapter just taught (basic case has `default_scale=4` but lo-res via per-section `scale=1`) | Reword to "activates when the effective/per-section scale ≥ 2 and the band is tall enough" |
| 9 | `tutorial/05-polish.mdx` | Dead link `[Config pitfalls](/reference/config-pitfalls/)` (L~323) — the page is at `/pitfalls/` | Change to `/pitfalls/` |
| 10 | `pitfalls.mdx` | No bottom next-step CTA (rubric #16 applies to reference pages too) — page dead-ends at Rule 52 | Add a `RelatedPages` (e.g. tools/validate, getting-started, transitions) |
| 11 | `hardware/longboi.mdx` | `gpio_slowdown` row value is `5` but the "Why" says "Raise to 4–5 if flicker persists" — can't raise 5 to 4–5 | Change to "raise to 6+ if flicker persists" |

## Suggested fix batches (for the review gate — adjust as you like)

- **Batch A — Correctness fixes (high priority; misleading/broken).** Must-fixes #1, #3, #4, #7, #8, #9, #11 (pure wrong-text/link/field edits) + #5, #6 (cli additions). One PR (touches gif, borders, render-demo, cli, tutorial-02/03/05, longboi). Etherscan (#2) is also correctness but has a deeper question (see below) — could ride along or be its own.
- **Batch B — Etherscan key story (#2).** Decide: document the literal-TOML-key path (docs-only fix), OR wire `.env` indirection in code (bigger). Likely docs-only; small PR (page + demo TOML + fact-pack).
- **Batch C — Consistency (#10 + cross-cutting).** pitfalls CTA; unify the validate-command form (`make validate` vs bare `led-ticker validate`) site-wide; align the validation page's name ("Validation rules" vs tutorial's "Config pitfalls").
- **Batch D — Polish (optional, nice-to-have).** Symptom-first "if it doesn't work" boxes on widget pages; name-the-reader lines; tutorial time-stamps + "what you'll need" boxes; migrate hand-rolled field tables (gif/image/two_row) to `OptionsTable` or add tripwires; gloss `ScaledCanvas`/`TickerMessage` where they hit config-author readers.

### Cross-cutting nice-to-have themes
- **No symptom-first "if it doesn't work" box** (rubric #13) on most widget pages (message, countdown, two_row, mlb, mlb_standings, coinbase, rss_feed) — weather/gif/image/etherscan/coingecko already have good ones.
- **Reader not named at the top** (rubric #1/§1) on most widget + concept pages.
- **Developer jargon in config-author concept pages** without a gloss: `ScaledCanvas`, `SetPixel`, `frame_invariant` (borders, display, sprite); `TickerMessage` (rss_feed).
- **Hand-rolled field tables** (gif, image, two_row) duplicate what `OptionsTable` renders and can silently drift from the fact-pack (rubric #6).
- **A code bug, not a docs bug** (noted for a separate code fix): `src/led_ticker/validate.py:70` hint says animation is valid on "message, countdown, gif, image" but the real gate (`factories.py:703`) is message/gif/image only — the docs (message/countdown pages) are CORRECT.

---

## Findings by area

### Widgets

**widgets/gif.mdx — Needs work.** MUST-FIX: `hold_seconds` (L155 caption "keeps cycling within `hold_seconds`", L178 note "honored as a _floor_") → `hold_time` (verified: no `hold_seconds` in `src/`; image.mdx uses `hold_time` in the identical note). Nice-to-have: repeated loop-count "max semantics" math (share one callout); hand-rolled field tables risk drift → `OptionsTable`. Accuracy otherwise good; all links resolve.

**widgets/etherscan.mdx — Minor gaps.** MUST-FIX: the `.env` / `ETHERSCAN_API_KEY` story is wrong — code reads only TOML `api_key` (`crypto/etherscan.py` L53/70); no env substitution; `ETHERSCAN_API_KEY` is nowhere in `src/`. The demo TOML (`demos-long/widget-etherscan.toml`) shares the broken assumption. Thresholds verified exact (`<=50` green, `<=70` yellow, else red). Nice-to-have: no DemoGif is honestly justified (#9), a static screenshot would still add payoff.

**widgets/two_row.mdx — Minor gaps.** No must-fix. Nice-to-have: the `bottom_text_loops`/`hold_time` crossover formula is repeated ~3× near-verbatim → one shared callout (#10); hand-rolled field tables → `OptionsTable` (#6); no symptom-first box (the 3 Tips cover the ground but aren't framed that way). Accuracy good.

**widgets/message.mdx — Good.** No must-fix. Nice-to-have: add an "if it doesn't work" box (#13); name the reader (#1). Typewriter "only on message/gif/image" VERIFIED correct.

**widgets/countdown.mdx — Good.** No must-fix. Render format `<text>: <N>` and midnight-roll VERIFIED. Nice-to-have: no local troubleshooting box; reader not named.

**widgets/weather.mdx — Good.** No must-fix. Nice-to-have: a "what you'll need" box fits perfectly (the one widget needing an API key — `WEATHERAPI_KEY`); default `update_interval=10800` VERIFIED.

**widgets/image.mdx — Good.** No must-fix (uses `hold_time` correctly throughout, incl. where gif.mdx erred). `hold_time` ≥ 0.05 VERIFIED. Nice-to-have: hand-rolled tables → `OptionsTable`; shared crossover callout.

**widgets/index.mdx — Good.** No must-fix. "**12 built-in widget types**" VERIFIED (table's 13th row is the `pool` plugin — consider a "(plugin)" tag). Nice-to-have: `image` row's "Use when" cell is empty → fill it.

**widgets/mlb.mdx — Good.** No must-fix. Defaults (300/6/45s) VERIFIED. Nice-to-have: symptom-first box; prereqs box ("no API key, no hardware").

**widgets/mlb_standings.mdx — Good.** No must-fix. Defaults (86400/top_n=3) VERIFIED. Nice-to-have: symptom-first box; split the run-on lead sentence.

**widgets/coinbase.mdx — Good.** No must-fix. `update_interval=300`, `currency`/`symbol` required VERIFIED. Nice-to-have: reframe the rate-limit tip symptom-first.

**widgets/coingecko.mdx — Good.** No must-fix. `symbol_id`/`currency` required, `update_interval=300` VERIFIED; the "`btc` fails → use `bitcoin`" tip is exemplary blameless copy. Nice-to-have: align the rate-limit guidance phrasing with the fact-pack.

**widgets/rss_feed.mdx — Good.** No must-fix. `max_stories=5`, `update_interval=1800` VERIFIED. Nice-to-have: gloss `TickerMessage`; "exponential backoff" wording may overstate the code (retry is via `run_monitor_loop`) → soften unless confirmed.

**widgets/pool.mdx — Good** (slim pointer page). No must-fix. Reads correctly as a pointer to the external plugin. Nice-to-have: an explicit trailing CTA.

### Transitions

**transitions/index.mdx — Good.** No must-fix. Defaults (`cut`/`cut`/`0.5`/`linear`) VERIFIED. Nice-to-have: the `between_sections` "Default `cut`" cell is a half-truth — it actually inherits the value of `default` (only equals `cut` when `default` is unset); reword. Name the reader.

**transitions/push.mdx — Good.** No must-fix. DemoGif + OptionsTable bound. Nice-to-have: add a "Tuning" section (the fact-pack has guidance; wipe/sprite/special show theirs, push doesn't).

**transitions/wipe.mdx — Good.** No must-fix. Nice-to-have: the "four colors, one per direction" claim isn't tripwire-bound → link the fact-pack table.

**transitions/sprite.mdx — Good.** No must-fix. Six DemoGifs exist; baseball 4-frame (8-bit) vs 8-frame (hi-res) VERIFIED, not a contradiction. Nice-to-have: gloss/drop `ScaledCanvas` for the config-author reader.

**transitions/special.mdx — Good.** No must-fix. `split` magenta `255,0,255` VERIFIED. Nice-to-have: a one-line Aside distinguishing `scroll` (transition) from `forever_scroll` (mode).

### Concepts

**concepts/borders.mdx — Good** (but one must-fix). MUST-FIX: Lightbulbs example (L219–223) uses old `[[section]]`/`[[section.widget]]` vs `[[playlist.section.widget]]` everywhere else → make consistent. Defaults VERIFIED (`speed=4`, `char_offset=6`, color_cycle `speed=5`). Nice-to-have: gloss the developer terms (`ScaledCanvas`/`SetPixel`/`frame_invariant`/"static-text fast path") or move to a "how it renders" aside; lead with payoff before internals.

**concepts/display.mdx — Minor gaps.** No must-fix. Nice-to-have: surface the `content_height × scale ≤ panel_h_real` ceiling as a symptom-first recovery line; gloss `ScaledCanvas`/"block-expansion"/`SetPixel` or link `concepts/how-rendering-works` (a natural cross-link the `RelatedPages` omits).

**concepts/animations.mdx — Good.** No must-fix. `frames_per_char=3` VERIFIED. Nice-to-have: name the reader; the "Where it works" table + two Tips restate the same rule twice → collapse.

**concepts/color-providers.mdx — Good.** No must-fix. All speed/offset defaults VERIFIED. Nice-to-have: the "ColorCycle range" row reads as a 7th provider vs "the six providers" heading; signpost the shimmer GIF from the top GIF's "(shimmer not shown)" caption; name the reader.

**concepts/fonts.mdx — Good.** No must-fix. Font-alias table VERIFIED against source; cites a real tripwire test (strong #6). Nice-to-have: the `font_threshold` example references unbundled "Beloved Sans" files → add "assuming you've dropped it into `config/fonts/`"; flag the `?`-glyph fix as a developer action.

**concepts/sections-and-modes.mdx — Good.** No must-fix. Three mode GIFs exist; `default` vs `transition` override stated carefully. Nice-to-have: group the appendix-y sections under "Advanced"; note the `moon-transparent.png` asset ships in the repo.

**concepts/busy-light.mdx — Good.** No must-fix. EVERY config default + the entire HTTP surface VERIFIED against `config.py`/`busy_http.py` (exemplary). Nice-to-have: a short DemoGif of the corner dot would sell it; add a forward CTA for the HTTP-automation content.

### Tools

**tools/render-demo.mdx — Needs work.** MUST-FIX: phantom `--fps N` flag (default 20) — does NOT exist in `render.py` (real flags: `config` positional, `--output/-o`, `--duration`, `--upscale`, `--start-section`). Remove the row. Nice-to-have: the flags table omits the required `config` positional → add it (or note it's the post-Makefile surface). Other commands/paths VERIFIED correct.

**tools/panel-test.mdx — Minor gaps.** No must-fix. Nice-to-have: "a single `~50`-line script" — the file is 96 lines → change to "~95-line" or drop the count. Everything else (Makefile target, `--config`/`--hold` defaults, R→G→B→W→B cycle, Ctrl-C final black frame) VERIFIED. Excellent symptom→cause→fix table.

**tools/creating-a-config.mdx — Good.** No must-fix. Nice-to-have: name the reader; the "7 questions" counts will drift if the skill changes → soften.

**tools/validate.mdx — Good.** No must-fix. CLI surface VERIFIED against `cli.py` (positional `path`, `--json`/`--strict`/`--list-fields`/`--config`); exit codes 0/1/2 match; pitfalls anchor resolves. Nice-to-have: `severity` is in the field table but not the JSON examples → add it or note abbreviation. (Note: the real CLI also has `--fix`, undocumented here — see cli.mdx must-fix.)

**tools/gif-plan.mdx — Good.** No must-fix. `make plan-gif`, example config, exit codes 0/2/3 VERIFIED against `plan.py`. Nice-to-have: clarify the "exit 2 is ignorable" wording so readers don't ignore real clip warnings.

### Reference

**reference/config-options.mdx — Good.** No must-fix — every documented `[display]`/`[title]`/`[transitions]`/`[[playlist.section]]`/`[busy_light]` field and default VERIFIED against `config.py` (drift-guarded by `test_docs_config_options_drift.py`). Nice-to-have: the real top-level `[plugins]` block (`enabled`/`dir`/`disable`) is undocumented despite the "every TOML knob" framing → add a short table or scope it out + link the Plugins page; move the internal `transition_specified` to a footnote.

**reference/cli.mdx — Minor gaps.** MUST-FIX (×2): (a) omits the real `plugins` subcommand; (b) `validate` flag table + Tips omit `--fix` (in-place migration). Nice-to-have: note `validate` also takes `--config`/`-c`; the Make-targets table omits `hooks`/`clean`/`render-emoji-previews`/`setup-demo-fonts`. Documented targets + exit codes otherwise VERIFIED. (One thing for the implementer to spot-check: the exact `pyproject.toml` entry-point spelling, `app:main` vs `app.cli:main`.)

**reference/frame-counters.mdx — Good.** No must-fix — the whole model (`restart_on_visit` default True, `frame_invariant`, `frame_for`, `pause/resume/reset_frame`, 50ms tick, per-class policies) VERIFIED against source. Nice-to-have: the table labels the constant provider `Constant` but the class is `_ConstantColor`; the "Implementing a new effect" steps use `ClassVar[bool]` while real classes use plain `bool` → match house style or note it.

### Hardware

**hardware/longboi.mdx — Minor gaps.** MUST-FIX: `gpio_slowdown` row value `5` with "Raise to 4–5 if flicker persists" is self-contradictory → "raise to 6+". All tuning values VERIFIED against `config.longboi.toml`. Nice-to-have: no full `<details>` reference-config listing (smallsign/bigsign have one) → add for parity; photos are a tracked placeholder.

**hardware/smallsign.mdx — Good.** No must-fix. `[display]` snippet matches `config.example.toml`. Nice-to-have: no build-photo placeholder block (longboi has one) → add for parity.

**hardware/bigsign.mdx — Good.** No must-fix. Remap string VERIFIED byte-for-byte against `config.bigsign.example.toml`; the ASCII serpentine diagram is a strong visual. Nice-to-have: a "Photos coming soon" placeholder for parity; a real cable-run photo would land #7 harder.

**hardware/building-your-own.mdx — Good.** No must-fix. Commands are real Make targets; power table consistent with the per-build pages. Nice-to-have: a "what you'll need" box (#11) + time stamp (#12) for the software-first path; spot-check the `make build-docker` target name against the Makefile.

### Tutorial + top-level

**tutorial/02-first-config.mdx — Needs work.** MUST-FIX: `--duration 20` advice (L~176) is unrunnable via the documented `make render-demo` (no flag forwarding); next block is a bare `make render-demo`. Validate happy/error output strings VERIFIED verbatim against `validate.py`/`coercion.py`. Nice-to-have: no #11/#12.

**tutorial/03-multi-widget.mdx — Minor gaps.** MUST-FIX: "hi-res path activates when `default_scale > 1`" (L~294) contradicts the per-section-`scale` mechanism the chapter teaches → reword to effective/per-section scale. Ceiling math + rule numbers (28/29/30) VERIFIED against pitfalls. Nice-to-have: a reassurance line on the dense math (#15); no #11/#12.

**tutorial/05-polish.mdx — Minor gaps.** MUST-FIX: dead link `/reference/config-pitfalls/` → `/pitfalls/`. Deploy details (`/code/config:ro`, `docker compose up -d`) VERIFIED against memory. Nice-to-have: a "what you'll need on the Pi" box; no #12.

**tutorial/01-setup.mdx — Good.** No must-fix. `make dev`, `make render-demo`, the moonbunny config path VERIFIED. Nice-to-have: time stamp; an "if it doesn't work" box (uv/Python/`rgbmatrix` failures); a scannable prereqs box.

**tutorial/04-custom-branding.mdx — Minor gaps.** No must-fix. Nice-to-have: an "if it doesn't work" box for the natural Rule-24 (unknown font) failure; no #12.

**getting-started.mdx — Good.** No must-fix. All four config paths + commands VERIFIED; links to `/pitfalls/` correctly (the route tutorial-05 got wrong). Nice-to-have: a "what you'll need" box (prereqs are on the tutorial but not here, where a reader lands first).

**pitfalls.mdx — Minor gaps.** MUST-FIX: no bottom next-step CTA (#16 applies to reference pages) → add `RelatedPages`. Rule IDs map to the `--json` `rule` field (strong #6); error blocks VERIFIED. Nice-to-have: Errors-section rule numbering is out of order (defensible since IDs are stable/non-sequential — sort or say so); unify the validate-command form; align the page name ("Validation rules" vs tutorial's "Config pitfalls").

**showcase.mdx — Good.** No must-fix. Placeholder image is honestly flagged (#9). Nice-to-have: spot-check the `submit-sign.yml` issue-template exists; surface for the pending-photos follow-up.

**assets/emoji.mdx — Good.** No must-fix. OptionsTable is data-bound (slug list can't drift). Nice-to-have: the front-matter "40 glyphs (20 base…)" counts are hardcoded and don't cleanly match source (~22 base + variants) → soften/derive; one-line gloss of `:slug:`.

---

## Next step (review gate)

Pick the fix scope and order (the suggested batches above are a starting point). Each chosen batch becomes its own spec → plan → PR with the normal implementer + tech-writer review loop. **No page is edited until you choose.**
