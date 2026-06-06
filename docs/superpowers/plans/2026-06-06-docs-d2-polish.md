# Batch D2 — Cheap High-Value Docs Polish — Implementation Plan

> **For agentic workers:** subagent-driven; sequential implementer tasks (disjoint pages) + a tech-writer review.

**Goal:** Apply the audit's cheap high-value polish — tutorial stamps + "what you'll need" boxes, glosses, a light reader-naming touch, and ~6 concrete small per-page fixes. Docs-only.

**Source spec:** `docs/superpowers/specs/2026-06-06-docs-d2-polish-design.md`
**Worktree:** `.claude/worktrees/docs-d2`, branch `feat/docs-d2`. **Commit:** `git -c core.hooksPath=/dev/null commit`. All pages under `docs/site/src/content/docs/`.

**Shared rules:** keep facts correct; no release-history framing (DOCS-STYLE #17); "what you'll need" is a plain markdown bullet list (NOT inside an `Aside` — prettier mangles lists in JSX); run `make docs-format && make docs-build && make docs-lint` (both exit 0) before each commit.

---

### Task 1: Tutorial chapters — time stamp + "what you'll need"

**Files:** `tutorial/01-setup.mdx`, `02-first-config.mdx`, `03-multi-widget.mdx`, `04-custom-branding.mdx`, `05-polish.mdx`.

- [ ] For each chapter, read it, then near the top (after the intro line / before the first `##`):
  - Add a **time/effort stamp** line, e.g. `**~10 min · no hardware needed**` — estimate per chapter from its content (01 setup ~10 min; 02 first-config ~10 min; 03 multi-widget ~15 min; 04 branding ~15 min; 05 polish ~10 min; all "no hardware needed" since they preview via `make render-demo`).
  - Add a brief **What you'll need** plain-markdown bullet list ONLY where the chapter has real prerequisites — at minimum 01 (a laptop; the repo cloned + `make dev`; no hardware) and 04 (a brand font + a logo image file in `config/fonts/` and `config/assets/`). For 02/03/05 a "what you'll need" is optional (they continue from the prior chapter) — add a one-line "Picks up from chapter N" pointer instead if there are no new prereqs. Don't invent prereqs.
- [ ] Verify + commit:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-d2
make docs-format && make docs-build; echo "BUILD=$?"; make docs-lint; echo "LINT=$?"
git add docs/site/src/content/docs/tutorial
git -c core.hooksPath=/dev/null commit -m "docs: add time/effort stamps + what-you'll-need to tutorial chapters (D2)"
```
Expected BUILD=0, LINT=0.

---

### Task 2: Glosses + light reader-naming

**Files:** `concepts/borders.mdx`, `concepts/display.mdx`, `transitions/sprite.mdx`, `widgets/rss_feed.mdx`.

- [ ] **`ScaledCanvas` gloss** on `concepts/borders.mdx`, `concepts/display.mdx`, `transitions/sprite.mdx`: on first use, either gloss in one clause ("a `ScaledCanvas` — the wrapper that expands logical pixels onto a big sign") or, where the class name isn't needed for the config-author reader, replace with "a big / scaled sign (`default_scale > 1`)". Where natural, link `concepts/display` or `concepts/how-rendering-works` instead of re-explaining. Don't change facts.
- [ ] **`TickerMessage` gloss** on `widgets/rss_feed.mdx`: replace/annotate the bare `TickerMessage` with "a single scrolling line" (gloss the internal type).
- [ ] **Light reader-naming** on `concepts/borders.mdx` and `concepts/display.mdx` ONLY: where each drops developer terms (`SetPixel`, `frame_invariant`, source paths) into config-author prose, add a half-line signposting that those bits are for developers/plugin authors (or move them into a brief "For developers" aside). Keep it minimal — one clarifying clause per page, not a rewrite.
- [ ] Verify + commit:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-d2
make docs-format && make docs-build; echo "BUILD=$?"; make docs-lint; echo "LINT=$?"
git add docs/site/src/content/docs/concepts/borders.mdx docs/site/src/content/docs/concepts/display.mdx docs/site/src/content/docs/transitions/sprite.mdx docs/site/src/content/docs/widgets/rss_feed.mdx
git -c core.hooksPath=/dev/null commit -m "docs: gloss ScaledCanvas/TickerMessage + light reader signposts (D2)"
```

---

### Task 3: Small per-page fixes

Apply each exactly (read the page first):
- [ ] `widgets/index.mdx` — fill the empty "Use when" cell on the `image` row (e.g. "logos / single still graphics"); add "(plugin)" to the `pool` row label so the "12 built-in widget types" count is unambiguous.
- [ ] `transitions/index.mdx` — reword the `between_sections` Notes cell from "Default `cut`" to something like "Falls back to `default` (which is `cut` unless you change it)" (it inherits `default`, not a hardcoded `cut`).
- [ ] `concepts/color-providers.mdx` — near the top GIF whose caption says "(shimmer not shown)", add a one-line pointer to the dedicated shimmer GIF lower on the page.
- [ ] `widgets/coingecko.mdx` — align the rate-limit guidance with the fact-pack (the page says "~5-minute interval is safe for up to ~6 widgets"; the fact-pack says "keep at 60 s or above") — pick one consistent statement (check `docs/content-source/widgets/coingecko.md` and make the page agree).
- [ ] `tools/panel-test.mdx` — "a single `~50`-line script" → "a small script" (or "~95-line"; the file is ~96 lines).
- [ ] `reference/frame-counters.mdx` — the provider labeled `Constant (font_color)` is the class `_ConstantColor`; add a parenthetical (e.g. "`_ConstantColor`") so a developer grepping finds it.
- [ ] Verify + commit:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-d2
make docs-format && make docs-build; echo "BUILD=$?"; make docs-lint; echo "LINT=$?"
grep -n "Use when" docs/site/src/content/docs/widgets/index.mdx | head
grep -n -- "~50" docs/site/src/content/docs/tools/panel-test.mdx && echo "STILL ~50" || echo "panel-test count fixed"
git add docs/site/src/content/docs/widgets/index.mdx docs/site/src/content/docs/transitions/index.mdx docs/site/src/content/docs/concepts/color-providers.mdx docs/site/src/content/docs/widgets/coingecko.mdx docs/site/src/content/docs/tools/panel-test.mdx docs/site/src/content/docs/reference/frame-counters.mdx
git -c core.hooksPath=/dev/null commit -m "docs: small per-page fixes from the audit (D2)

widgets/index image 'use when' + pool '(plugin)' tag; transitions between_sections
default note; color-providers shimmer GIF pointer; coingecko rate-limit phrasing;
panel-test line count; frame-counters _ConstantColor label."
```

---

### Task 4: Tech-writer review + verify

- [ ] **Step 1:** Tech-writer reviewer over the edited pages — confirm the stamps/boxes/glosses read cleanly, the §3 checklist still passes (incl. #17), no facts broken, no `Aside`-list mangling. Apply must-fix; re-build/lint.
- [ ] **Step 2: Final verify:**
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/docs-d2
make docs-build; echo "BUILD=$?"; make docs-lint; echo "LINT=$?"
grep -riE "\blegacy\b|backward[- ]?compat|no longer (accepted|valid)|still works.*as before" docs/site/src/content/docs/ || echo "no history framing reintroduced"
```
Expected exit 0; no history framing.
- [ ] **Step 3:** Commit any review fixes.

---

## Self-Review

**1. Spec coverage:** tutorial stamps + boxes → Task 1. glosses + reader-naming → Task 2. small per-page fixes → Task 3. review + verify → Task 4. ✓ Deferred items (troubleshooting boxes, OptionsTable migration, broad reader-naming, the skill migration) → respected. ✓

**2. Placeholder scan:** No TBD/TODO; each edit names the page + the exact change (estimates/wording at the implementer's judgment within the stated bounds). ✓

**3. Consistency:** "What you'll need" is a plain markdown list (not Aside) per the prettier lesson; no release-history framing (DOCS-STYLE #17) honored in new copy; docs-only (no code). Tasks touch disjoint page sets, run sequentially. The small fixes match the audit findings exactly. ✓
