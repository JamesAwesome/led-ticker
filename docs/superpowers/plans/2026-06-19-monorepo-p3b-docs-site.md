# Monorepo P3b — Docs-site Reference Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the docs site so every reference to the old per-plugin repos and pre-split type names points at the `led-ticker-plugins` monorepo with the finalized names — `feeds.rss`→`rss.feed`, `feeds.weather`→`weather.current`, `arcade.<fam>`→`<fam>.forward/.reverse/.alternating`, `:arcade.pokeball:`→`:pokeball.ball:` — and reflect the feeds→2 / arcade→4 package splits.

**Architecture:** The plugin/widget doc pages are already thin **pointer pages** (intro + DemoGif + "full docs in the repo README") and `plugins/available.mdx` is a hand-maintained catalog mirror. So this is a **reference-update sweep**, not a restructure: rename types, repoint install lines + repo links at the monorepo, and split the feeds/arcade entries. Follow `docs/DOCS-STYLE.md`.

**Tech Stack:** Astro Starlight (`.mdx`), prettier + astro check (`make docs-lint`), pnpm.

**Scope:** P3b is docs-only. The catalog/code cutover (P3a) is merged; archiving the 6 old repos (P3c) is separate and must follow. No code changes here. See `docs/superpowers/specs/2026-06-19-led-ticker-plugins-monorepo-design.md`.

**Working repo:** `/Users/james/projects/github/jamesawesome/led-ticker`. Create branch `feat/monorepo-p3b-docs-site` off `main` (has P3a). All work on that branch, never `main`. **Git hooks are broken in this checkout — commit AND push with `--no-verify`.**

## Global transformation rules (apply everywhere)

**Type renames:**
| old | new |
|---|---|
| `feeds.rss` | `rss.feed` |
| `feeds.weather` | `weather.current` |
| `arcade.nyancat` / `arcade.nyancat_reverse` / `arcade.nyancat_alternating` | `nyancat.forward` / `nyancat.reverse` / `nyancat.alternating` |
| `arcade.pokeball*` | `pokeball.forward` / `.reverse` / `.alternating` |
| `arcade.pacman*` | `pacman.forward` / `.reverse` / `.alternating` |
| `arcade.sailor_moon*` | `sailor_moon.forward` / `.reverse` / `.alternating` |
| `:arcade.pokeball:` | `:pokeball.ball:` |

**Install-line + repo-link mapping** (one per package; tags: all `-v0.1.0` except `rss`/`weather` which are `-v0.2.0`):
| package | install line | repo link (README) |
|---|---|---|
| pool | `git+https://github.com/JamesAwesome/led-ticker-plugins.git@pool-v0.1.0#subdirectory=plugins/pool` | `https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/pool` |
| baseball | `…@baseball-v0.1.0#subdirectory=plugins/baseball` | `…/tree/main/plugins/baseball` |
| crypto | `…@crypto-v0.1.0#subdirectory=plugins/crypto` | `…/tree/main/plugins/crypto` |
| calendar | `…@calendar-v0.1.0#subdirectory=plugins/calendar` | `…/tree/main/plugins/calendar` |
| rss | `…@rss-v0.2.0#subdirectory=plugins/rss` | `…/tree/main/plugins/rss` |
| weather | `…@weather-v0.2.0#subdirectory=plugins/weather` | `…/tree/main/plugins/weather` |
| nyancat | `…@nyancat-v0.1.0#subdirectory=plugins/nyancat` | `…/tree/main/plugins/nyancat` |
| pokeball | `…@pokeball-v0.1.0#subdirectory=plugins/pokeball` | `…/tree/main/plugins/pokeball` |
| pacman | `…@pacman-v0.1.0#subdirectory=plugins/pacman` | `…/tree/main/plugins/pacman` |
| sailor_moon | `…@sailor_moon-v0.1.0#subdirectory=plugins/sailor_moon` | `…/tree/main/plugins/sailor_moon` |

A README link `https://github.com/JamesAwesome/led-ticker-<old>#readme` becomes `https://github.com/JamesAwesome/led-ticker-plugins/blob/main/plugins/<name>/README.md`. Keep `.mdx` filenames as-is (URLs stay stable) even where the type changed (e.g. `widgets/rss_feed.mdx` keeps its name but documents `rss.feed`).

**Acceptance gate (run at the end):** `grep -rnE 'arcade\.|feeds\.|led-ticker-(pool|baseball|crypto|calendar|feeds|arcade)\b' docs/site/src/content/docs/` returns nothing except deliberate "was `feeds.rss`"-style migration notes. `make docs-lint` passes.

---

### Task 1: Substantive pages (catalog, sprite transitions, feeds pointer pages, install examples)

**Files (substantive — need prose edits, not just find/replace):**
- `docs/site/src/content/docs/plugins/available.mdx`
- `docs/site/src/content/docs/transitions/sprite.mdx`
- `docs/site/src/content/docs/widgets/weather.mdx`
- `docs/site/src/content/docs/widgets/rss_feed.mdx`
- `docs/site/src/content/docs/hardware/smallsign.mdx`
- `docs/site/src/content/docs/tutorial/05-polish.mdx`

- [ ] **Step 1: Branch**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git checkout main && git pull --ff-only origin main
git checkout -b feat/monorepo-p3b-docs-site
git branch --show-current   # MUST be feat/monorepo-p3b-docs-site — if main, STOP
```

- [ ] **Step 2: `plugins/available.mdx` — rewrite to the monorepo + 10 packages**

The page's intro currently says "Plugins live in their own repositories." Update it to: the first-party plugins live in the **[led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins)** monorepo, installed per-plugin via `#subdirectory=`. Then convert each `### [led-ticker-<x>](old-url)` section: keep one section per plugin but split the two combined ones — the old `led-ticker-feeds` section becomes TWO sections (`rss` → `rss.feed`, `weather` → `weather.current`); the old `led-ticker-arcade` section becomes FOUR (`nyancat`, `pokeball`, `pacman`, `sailor_moon`) OR one "Sprite-trail transitions" section that lists the 4 packages with their 4 install lines — pick the form that reads best per DOCS-STYLE.md, but every package's install line + type(s) must appear. Each section: heading links to the monorepo subdirectory, prose keeps the existing per-plugin description (updated type names), and the ```text install block uses the new monorepo line from the mapping. Preserve the pool/baseball/crypto/calendar descriptions (just swap their install line + repo link + the README link).

- [ ] **Step 3: `transitions/sprite.mdx` — now FOUR separate packages**

This page previously documented ONE `led-ticker-arcade` install for all four families. Rewrite:
- Intro: the sprite transitions are provided by four packages in the **led-ticker-plugins** monorepo — `nyancat`, `pokeball`, `pacman`, `sailor_moon` — each with `.forward` / `.reverse` / `.alternating` variants. Reference by slug, e.g. `transition = "pokeball.forward"`.
- Install section: replace the single arcade line with the four monorepo install lines (nyancat/pokeball/pacman/sailor_moon from the mapping), noting you only install the families you use. The `:pokeball.ball:` emoji ships with the `pokeball` package.
- Every `arcade.<x>` slug in prose, DemoGif captions, and any OptionsTable → the new `<fam>.<variant>` name.
- The bare-name migration note: `transition = "nyancat"` → now points at `nyancat.forward`.

- [ ] **Step 4: `widgets/weather.mdx` + `widgets/rss_feed.mdx` — pointer pages**

For `weather.mdx`: frontmatter `title`/`description` and body → `weather.current` provided by the `weather` package in led-ticker-plugins; install line → weather mapping; "full documentation … README" link → the weather package README in the monorepo. Add a one-line note: "(was `feeds.weather` before the plugin split)." Same shape for `rss_feed.mdx` → `rss.feed`, `rss` package, "(was `feeds.rss`)".

- [ ] **Step 5: `hardware/smallsign.mdx` + `tutorial/05-polish.mdx` — install examples**

These contain example `requirements-plugins.txt` lines / config snippets referencing old repos + types. Update every install line to the monorepo mapping and every type name to the new names. Keep the surrounding tutorial/hardware prose intact; only the plugin lines + type references change. (If smallsign shows a `git+…led-ticker-arcade…` line giving "sprite transitions", replace with the specific family line(s) the example uses, e.g. `nyancat` — match whatever transition the example actually demonstrates.)

- [ ] **Step 6: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git add docs/site/src/content/docs/plugins/available.mdx docs/site/src/content/docs/transitions/sprite.mdx docs/site/src/content/docs/widgets/weather.mdx docs/site/src/content/docs/widgets/rss_feed.mdx docs/site/src/content/docs/hardware/smallsign.mdx docs/site/src/content/docs/tutorial/05-polish.mdx
git commit --no-verify -m "docs: repoint catalog, sprite transitions + feeds pages at the monorepo (P3b substantive)"
```

---

### Task 2: Mechanical sweep of the remaining pages

**Files (incidental 1–4 references each — apply the global rules):**
`widgets/crypto-coingecko.mdx`, `widgets/pool.mdx`, `widgets/mlb.mdx`, `widgets/mlb_standings.mdx`, `widgets/calendar.mdx`, `widgets/index.mdx`, `transitions/index.mdx`, `plugins/index.mdx`, `plugins/extending/writing-a-transition.mdx`, `plugins/authoring/03-package.mdx`, `plugins/authoring/04-beyond-widgets.mdx`, `tools/render-demo.mdx`, `tools/gif-plan.mdx`, `tools/creating-a-config.mdx`, `index.mdx`, `showcase.mdx`, `reference/config-options.mdx`, `concepts/sections-and-modes.mdx`, `concepts/fonts.mdx`, `concepts/borders.mdx`, `concepts/animations.mdx`, `pitfalls.mdx`

- [ ] **Step 1: Apply the global rules to each file**

For every file above, replace each occurrence per the global rules (type renames, install lines, repo links). Most are a single mention (a transition slug in an example, a repo link, an install line). Read each occurrence in context — do NOT blind-sed, because some mentions are in prose that needs the surrounding words adjusted (e.g. "the led-ticker-arcade plugin" → "the nyancat/pokeball/pacman/sailor_moon packages" or "the led-ticker-plugins monorepo" depending on context). Use:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
grep -rnE 'arcade\.|feeds\.|led-ticker-(pool|baseball|crypto|calendar|feeds|arcade)\b' docs/site/src/content/docs/<file>
```
per file to find each spot, then edit in context.

- [ ] **Step 2: Verify the acceptance grep is clean**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
grep -rnE 'arcade\.|feeds\.|led-ticker-(pool|baseball|crypto|calendar|feeds|arcade)\b' docs/site/src/content/docs/
```
Expected: nothing, EXCEPT intentional "(was `feeds.rss`)" / "(was `arcade.nyancat`)" migration notes you deliberately added. Confirm each remaining hit is such a note; otherwise fix it.

- [ ] **Step 3: Commit**

```bash
git add docs/site/src/content/docs/
git commit --no-verify -m "docs: monorepo + new plugin names across remaining pages (P3b sweep)"
```

---

### Task 3: Lint, verify, open PR

**Files:** none.

- [ ] **Step 1: Docs lint + build**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
make docs-lint 2>&1 | tail -20
```
Expected: prettier --check + astro check pass. If prettier flags formatting, run `make docs-format`, re-check, and amend the relevant commit (or add a follow-up format commit). If astro check reports a broken internal link (e.g. a `/widgets/...` slug that changed), fix it — but filenames were kept stable, so links should hold.

- [ ] **Step 2: Final acceptance grep**

```bash
grep -rnE 'arcade\.|feeds\.|led-ticker-(pool|baseball|crypto|calendar|feeds|arcade)\b' docs/site/src/content/docs/ || echo "clean — only intentional migration notes remain"
```

- [ ] **Step 3: Push + open PR (no merge without consent)**

```bash
git push --no-verify -u origin feat/monorepo-p3b-docs-site
gh pr create --repo JamesAwesome/led-ticker --base main --head feat/monorepo-p3b-docs-site \
  --title "P3b: docs site — repoint plugin references at the led-ticker-plugins monorepo" \
  --body "Docs-only reference sweep for the plugin monorepo (led-ticker#235). Renames feeds.rss->rss.feed, feeds.weather->weather.current, arcade.<fam>-><fam>.forward/.reverse/.alternating, :arcade.pokeball:->:pokeball.ball: across the docs site; repoints install lines + repo links at led-ticker-plugins #subdirectory= installs; splits the feeds (rss/weather) and arcade (4 families) catalog/transition pages. Pointer-page architecture unchanged. make docs-lint passes. Old-repo archival (P3c) is the separate follow-up. Do NOT merge without consent."
```

- [ ] **Step 4: Confirm CI green (docs-lint now runs)**

```bash
gh pr checks <PR#> --repo JamesAwesome/led-ticker
```
Expected: `docs-lint` runs (docs changed) and passes; other jobs pass/skip.

---

## Self-review

**Spec coverage (P3b = the "Docs site (~19 pages)" P3 item):**
- Catalog mirror (`available.mdx`) → monorepo + splits → Task 1 Step 2. ✓
- Sprite transitions page (4 separate packages now) → Task 1 Step 3. ✓
- feeds pointer pages → Task 1 Step 4. ✓
- Install-example pages (hardware, tutorial) → Task 1 Step 5. ✓
- All remaining incidental mentions → Task 2. ✓
- Lint + link integrity → Task 3. ✓
- Old-repo archival → out of scope (P3c). ✓

**Placeholder scan:** No TBD/TODO; the global rules table + per-file notes give exact mappings. `<PR#>` is a runtime value. Substantive pages have explicit rewrite direction; incidental pages have the rules + a per-file grep to drive edits-in-context. ✓

**Type/name consistency:** the rename table + install/tag/repo-link mapping are defined once and referenced by both tasks; tags match those cut in P2 (rss/weather v0.2.0, rest v0.1.0) and the P3a catalog. Filenames kept stable to preserve URLs. ✓

**Pitfalls flagged inline:** sprite.mdx is a real rewrite (1 install → 4 packages), not a rename; don't blind-sed prose ("the led-ticker-arcade plugin" needs contextual rewording); keep `.mdx` filenames to avoid breaking links; commit/push with `--no-verify` (broken local hook); run `make docs-format` if prettier complains; the acceptance grep must come back clean except deliberate migration notes; no merge without consent.
