# Finish gate #1 — anonymization completion

**Date:** 2026-06-21
**Status:** approved (design)
**Goal:** Close the three classes of Moon-Bunny leak that #256's literal-string guard (needles
`moonbunny`/`aerial`) structurally could not catch and that shipped to `main` via #256 + #257: the rabbit
brand **voice**, **stale GIF pixels**, and the unattributed **pride.gif**; plus the `@firebird` handle gap.
Then harden the guard so each class can't recur.

## Background

A 5-lens review team + live-docs browsing found, all currently on `main`:

1. **Brand voice** (not the literal name): the retired studio's rabbit voice survives verbatim —
   `"May the Rabbit always be with you!"` + `"Always be your bunny best!"` in `config.example.toml:87,91`,
   `config.bigsign.example.toml:114,118`, `config.forever_scroll.toml:45,49`, `config.infini_scroll.toml:37,41`,
   `.claude/skills/creating-a-config/references/snippets.md:614,618`,
   `docs/site/src/content/docs/hardware/bigsign.mdx:256,260`, `hardware/smallsign.mdx:170,174` (all the same
   `#DevOps News` demo). Plus on-panel `"BIG BUNNY"`/`"…BEHIND THE BUNNY"`/`"…THROUGH THE BUNNY"`/
   `"Bunny says hi"` + `bunny` comments in `config.image_test.example.toml` (24, 296, 297),
   `config.rainbow_border_test.example.toml` (165, 231, 246, 590), `config.bg_color_test.example.toml` (90, 107),
   `config.bands_border_test.example.toml` (333), `docs/site/demos/widget-image.toml` (6, 26).
2. **Stale GIF pixels** (a guard can't see inside a GIF): `tutorial-04a-font.gif` still shows moonbunny text
   (last rendered in #44, pre-firebird). Could not re-render because of the render-tool font bug (below);
   same root cause as the #256-deferred `tutorial-04c-image-with-text` + `tutorial-05a-transitions`.
3. **`pride.gif` / `pride_trans.gif`** = unattributed third-party Progress-Pride flag artwork.

Plus: the §6 short Instagram handle is bare `@firebird` (dropped the `.demo` fictional marker — could collide
with a real account); `~41` usages + the §6 rule.

## Decisions (locked with the user)

- Approach: full brainstorm → spec → plan → subagent-driven-development.
- Replacement voice copy: **generic, theme-appropriate filler** (these are generic starter/test configs, NOT
  the Firebird showcase — the Firebird voice stays in `config.firebird.example.toml`).
- `pride.gif`: **generate a project-original CC0 replacement** — a **classic 6-stripe rainbow** (clean
  provenance; the band arrangement is generic/public-domain).
- Handle: `@firebird` → **`@firebird.demo`**.

## Work-streams

### A. Brand-voice sweep

**Ticker filler (all 7 `#DevOps News` spots — same pair everywhere):**
- `"May the Rabbit always be with you!"` → `"May the uptime be with you!"`
- `"Always be your bunny best!"` → `"Always be shipping!"`
(Dev-flavored, generic, no brand voice; fits the `#DevOps News` demo. Apply to: the 4 configs +
`snippets.md` + `hardware/bigsign.mdx` + `hardware/smallsign.mdx`.)

**On-panel / comment "bunny" → "phoenix"** (accurate to the now-rendered phoenix asset):
- `config.image_test.example.toml`: `:297 text = "BIG BUNNY"` → `"BIG PHOENIX"`; `:296` comment `bunny pinned`
  → `phoenix pinned`; `:24` comment `bunny image` → `phoenix image`.
- `config.rainbow_border_test.example.toml`: `:165 "TEXT WALKS BEHIND THE BUNNY"` → `"… THE PHOENIX"`;
  `:246 "DOUBLE RAINBOW THROUGH THE BUNNY"` → `"… THE PHOENIX"`; `:231`, `:590` comments `bunny` → `phoenix`.
- `config.bg_color_test.example.toml`: `:90`, `:107` comments `Bunny image`/`Bunny silhouette` →
  `phoenix image`/`phoenix silhouette`.
- `config.bands_border_test.example.toml`: `:333` comment `the bunny holds` → `the phoenix holds`.
- `docs/site/demos/widget-image.toml`: `:26 text = "Bunny says hi"` → `"Phoenix says hi"` (keeps it wider than
  `"Hello!"` so the line-6 marquee-pass rationale stays true); update the `:6` comment to name the new text.

After: `git grep -in "bunny\|rabbit" -- config docs .claude ':!docs/superpowers'` returns only the legitimate
`:bunny:` EMOJI slug + `bunny-low/hi.png` emoji-catalog rows (the generic rabbit emoji), nothing else.

### B. Guard — brand-voice needles

Extend `tests/test_no_real_brand.py` with a **voice-phrase** check asserting zero matches (outside
`docs/superpowers/` + the test file) for the PRECISE phrases: `"May the Rabbit"`, `"bunny best"`,
`"be your bunny"`. Phrase-level (NOT bare `bunny`/`rabbit`) so it cannot false-positive on the `:bunny:`
emoji slug / `bunny-low.png` / "Bunny silhouette" emoji-catalog text. Reuse the existing `git grep` +
`assert res.returncode in (0,1)` pattern; add a comment explaining why the needles are phrases. Must be GREEN
after stream A.

### C. Render-tool font-bug fix + tripwire (keystone — must precede all re-renders)

`tools/render_demo/render.py` (≈87/101/113) monkeypatches `app_mod._configure_user_font_dir` to suppress the
app's font-dir re-anchor, but `src/led_ticker/app/run.py:32` did `from … import _configure_user_font_dir`
(a local binding), so `run.py:436` calls the **unpatched** original → the gitignored demo font
(`AtkinsonHyperlegible-Bold` in `docs/site/demos-long/fonts/`) is lost.

**Fix:** in `render.py`'s suppress/restore block, also patch the binding where `run.py` looks it up — i.e.
`import led_ticker.app.run as run_mod; run_mod._configure_user_font_dir = lambda _p: None` (save + restore in
`finally`, mirroring the existing `app_mod` handling). Keep the existing `app_mod` patch too.

**Tripwire** (closes the `project_render_font_anchor_tripwire` gap): a test in `tools/render_demo/` that
renders a tiny config whose widget uses a custom font living in `<config_dir>/fonts/`, and asserts the glyphs
actually paint (non-blank) — i.e. the demo font dir was honored. Without the fix it renders blank; with it,
lit pixels. (Use the existing render-demo test harness / a synthetic BDF or the Atkinson ttf if present;
skip gracefully if the font asset is absent, like the existing font-dependent tests.)

### D. Re-render the stale moonbunny GIFs

With C in place, re-render the font-blocked demos so their pixels show Firebird, not moonbunny:
`tutorial-04a-font`, `tutorial-04c-image-with-text`, `tutorial-05a-transitions` (and any other GIF a scan
shows still renders moonbunny text). For each: `make render-demo CONFIG=… OUT=…`; verify `> 2` **distinct**
full-frames AND (spot-check) no moonbunny text. If one still can't render, DIAGNOSE + flag (don't fake).

### E. CC0 pride flag

`tools/derive_pride_assets.py` (committed, Pillow — sibling to `derive_phoenix_assets.py`) generates, from
solid RGB bands, a **6-stripe rainbow** flag:
- `config/assets/pride.gif` — animated (a gentle horizontal shimmer/wave over a handful of frames so the gif
  widget demo still animates), sized to match the retired asset's footprint so the demos render the same.
- `config/assets/pride_trans.gif` — a transparent variant (for any scroll-behind use).
Add a `make derive-pride` target; add a `config/assets/ATTRIBUTION.md` entry (project-generated, CC0, the
6 band RGBs). **Same filenames → no repoint needed** — regenerate the binaries + re-render the pride demos
(`config.gif_test.example.toml` / `config.gif_text.example.toml` referents). A light test
(`tests/test_pride_assets.py` or fold into `test_phoenix_assets.py`) asserts the 2 files exist + are animated.
Resolve the no-longer-true "third-party never committed" wording so ATTRIBUTION covers pride too.

### F. `@firebird` → `@firebird.demo`

Replace the `~41` bare short-handle usages across configs/demos/.mdx. **Precision (critical):** match
`@firebird` **only when NOT followed by `yoga`** — a naive replace corrupts `@firebirdyoga.demo` →
`@firebird.demoyoga.demo`. Use a word-boundary / negative-lookahead (e.g. `@firebird(?!yoga)` →
`@firebird.demo`). Update the §6 rule in `docs/DOCS-STYLE.md` (short handle row `@firebird` →
`@firebird.demo`) and any "≤12 chars" caption (now 14). Re-render the affected GIFs (the handle shows in
`tutorial-03c`/`03d` etc.).

## SDD task ordering

1. **C** — render-tool font fix + tripwire (unblocks all re-renders).
2. **A** — brand-voice copy sweep (configs/docs/snippets/hardware + on-panel texts).
3. **F** — handle `@firebird` → `@firebird.demo` (+ §6 rule, captions).
4. **E** — CC0 pride flag (derive script + assets + ATTRIBUTION + test).
5. **D + re-renders** — re-render every affected GIF (stale moonbunny font GIFs + the voice/handle/pride
   demos) now that fonts load.
6. **B** — guard voice-needles (GREEN after A).
7. **Final verify.**

## Testing / verification (final gate)

- All guards green: `tests/test_no_real_brand.py` (name + content + filename + palette + asset + **voice**).
- `git grep -in "bunny\|rabbit" -- config docs .claude ':!docs/superpowers'` → only the legitimate `:bunny:`
  emoji slug / `bunny-low/hi.png` rows remain.
- All-asset-paths-resolve audit (the #257 audit) → `none ✓`; pride.gif/pride_trans.gif present + animated.
- Render-tool tripwire passes; the stale font GIFs re-render with **no moonbunny pixels** (visual spot-check)
  and `>2` distinct frames.
- `@firebirdyoga.demo` intact (not corrupted); bare `@firebird` gone; §6 rule updated.
- Full suite green; `uv run --extra dev ruff check` + `pyright src/`; `make docs-format && docs-build &&
  docs-lint` clean (never pipe docs-lint to tail).

## Non-goals (stay focused — tracked elsewhere)

- `config/assets/heart-tunnel-opaque.jpg` + `moonscape-opaque.jpg` provenance (separate follow-up).
- `show_pikachu` pokeball-plugin field rename (separate plugins-monorepo repo).
- git-history scrub of the removed binaries (open-source-prep step).
- Restyling demos beyond the copy/asset/handle changes.

## Constraints

- The render-tool fix MUST let the custom-font demos re-render correctly (it's the keystone).
- No real-brand voice or copyrighted media may ship; the CC0 pride derive is reproducible from code.
- Voice needles must be phrase-precise (no false-positive on the `:bunny:` emoji).
- `@firebird` replacement must not corrupt `@firebirdyoga.demo`.
- No release-history framing in rewritten prose (DOCS-STYLE principle 17).
