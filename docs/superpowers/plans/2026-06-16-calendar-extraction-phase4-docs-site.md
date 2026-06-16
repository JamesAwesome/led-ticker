# Calendar Extraction — Phase 4: Docs-Site Reframe — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reframe the docs site so `calendar` reads as an external plugin (`calendar.events` via led-ticker-calendar), exactly the way `pool` and `crypto.coingecko` are presented — without breaking the docs build.

**Architecture:** Replace the full core-widget `widgets/calendar.mdx` with a short plugin-stub page (mirror `widgets/pool.mdx`); delete the now-orphaned fact-pack `docs/content-source/widgets/calendar.md`; move calendar into the plugin rows of the widgets index + the sidebar plugin group; add a `led-ticker-calendar` section to `plugins/available.mdx`; and delete the stale calendar demo TOMLs/ICS (the `build-demos.mjs` step walks `demos/*.toml` and would fail rendering `type = "calendar"`, now removed from core). Non-breaking, independent of the Phase-3 core merge (the plugin already provides `calendar.events`).

**Tech Stack:** Astro / Starlight docs site (`docs/site`), pnpm + `scripts/build-demos.mjs`, pytest for docs drift tests, `cloudflared` for post-merge deploy verification.

---

## Prerequisites & scope
- Phases 1–3 merged: core no longer has the calendar widget; the led-ticker-calendar plugin provides `calendar.events`.
- Work on branch `worktree-calendar-phase4-docs` in the led-ticker worktree. NEVER `main`.
- The model pages already in the repo: `docs/site/src/content/docs/widgets/pool.mdx` and `widgets/crypto-coingecko.mdx` (extracted single-widget plugins). Mirror their framing. Follow `docs/DOCS-STYLE.md`.
- **Leave alone:** `concepts/busy-light.mdx` line 11 — its "Real calendar / Slack / Teams sources" mention is about a future *busy-light source*, NOT the calendar widget; it stays accurate.
- After merge (not in this PR): deploy-verify the live pages via `cloudflared access` (the site is behind Cloudflare Access; plain curl 302s).

---

### Task 1: Reframe `widgets/calendar.mdx` → plugin stub + delete the fact-pack

**Files:**
- Modify (replace whole file): `docs/site/src/content/docs/widgets/calendar.mdx`
- Delete: `docs/content-source/widgets/calendar.md`

- [ ] **Step 1: Replace `widgets/calendar.mdx` entirely** with a plugin stub mirroring `pool.mdx`:

```mdx
---
title: calendar widget
description: The calendar (.ics) widget is provided by the led-ticker-calendar plugin (type = "calendar.events").
---

The **calendar** widget is provided by the **[led-ticker-calendar](https://github.com/JamesAwesome/led-ticker-calendar)** plugin, referenced in config as `type = "calendar.events"`. It pulls upcoming events from any subscribed iCal (`.ics`) feed and shows them as a rotating **agenda**, a live **next**-event countdown, or a held-top **two_row** card.

- **To add it to your sign:** add `git+https://github.com/JamesAwesome/led-ticker-calendar.git@main` to `config/requirements-plugins.txt` and rebuild — see [Plugins](/plugins/) for the full flow.
- **Full documentation** — options, the `agenda` / `next` / `two_row` layouts, keyword filter/highlight, and colors — lives in the [led-ticker-calendar README](https://github.com/JamesAwesome/led-ticker-calendar#readme).

See the [plugin system](/plugins/) for how plugin widgets work.
```

(This removes the `import` lines, `OptionsTable`, `DemoGif`, and the full layouts/options/colors sections — those now live in the plugin README, matching how `pool.mdx` defers to its repo.)

- [ ] **Step 2: Delete the orphaned fact-pack.** The stub no longer uses `<OptionsTable source="widgets/calendar" />`, so its data file is dead.

```bash
git rm docs/content-source/widgets/calendar.md
```

> Phase 3 already removed `calendar` from `tests/test_border_surface_drift.py`'s `FACT_PACK_FILES`, so nothing else references this fact-pack. Confirm with `grep -rn "widgets/calendar" docs/site/src tests/` — expect only the `widgets/calendar.mdx` page link references (the `/widgets/calendar/` route), not an `OptionsTable source="widgets/calendar"`.

- [ ] **Step 3: Commit.**

```bash
git add -A && git commit --no-verify -m "docs: reframe calendar widget page as a plugin stub; drop fact-pack"
```

---

### Task 2: Move calendar to the plugin sections (index + available + sidebar)

**Files:**
- Modify: `docs/site/src/content/docs/widgets/index.mdx`
- Modify: `docs/site/src/content/docs/plugins/available.mdx`
- Modify: `docs/site/astro.config.mjs`

- [ ] **Step 1: `widgets/index.mdx` — move the calendar row to the plugin block.** In the "By data source" table, DELETE the current core row:

```
| [`calendar`](/widgets/calendar/)                            | iCal / .ics URL             | upcoming events, agenda or next-event line |
```

and ADD a plugin-tagged row alongside the other `_(plugin)_` rows (after `crypto.coingecko`):

```
| [`calendar.events`](/widgets/calendar/) _(plugin)_          | iCal / .ics URL             | upcoming events, agenda / next / two_row   |
```

(Match the column alignment of the surrounding rows — pad to the same widths.)

- [ ] **Step 2: `widgets/index.mdx` — fix the "Live data" sentence.** It currently reads:

```
- **Live data (background fetch):** `weather`, `rss_feed`, `calendar`, plus the plugin widgets `pool`, `baseball.scores`, `baseball.standings`, and `crypto.coingecko`. Each has retry + exponential backoff.
```

Change it to drop `calendar` from the core list and add `calendar.events` to the plugin list:

```
- **Live data (background fetch):** `weather`, `rss_feed`, plus the plugin widgets `pool`, `baseball.scores`, `baseball.standings`, `crypto.coingecko`, and `calendar.events`. Each has retry + exponential backoff.
```

- [ ] **Step 3: `plugins/available.mdx` — add the led-ticker-calendar section.** Mirror the pool/crypto entries' shape (heading link, one-paragraph summary with the `type`, and the install snippet). Add after the crypto section:

```mdx
### [led-ticker-calendar](https://github.com/JamesAwesome/led-ticker-calendar)

Calendar (.ics) widget (`type = "calendar.events"`). Pulls upcoming events from any subscribed iCal feed (Google / iCloud / Outlook) and shows them as a rotating `agenda`, a live `next`-event countdown, or a held-top `two_row` card, with keyword `filter`/`highlight` and two-tone day/time coloring. Full docs, options, and screenshots in the [repo README](https://github.com/JamesAwesome/led-ticker-calendar#readme).
```

followed by the install code block in the same style the other entries use (a fenced block containing):

```
git+https://github.com/JamesAwesome/led-ticker-calendar.git@main
```

> Read the exact fence/format the pool & crypto entries use for their install snippet (a `requirements-plugins.txt` code block) and match it precisely, including any surrounding prose like "Add to `config/requirements-plugins.txt`:".

- [ ] **Step 4: `astro.config.mjs` — move the sidebar entry to the plugin group.** Remove the core-position entry:

```js
            { label: "calendar", link: "/widgets/calendar/" },
```

(currently between `countdown` and `clock`) and ADD it with the other plugin entries at the end of that `items` array (after `pool`), relabeled:

```js
            { label: "calendar.events (plugin)", link: "/widgets/calendar/" },
```

- [ ] **Step 5: Commit.**

```bash
git add -A && git commit --no-verify -m "docs: list calendar.events as a plugin (index, available, sidebar)"
```

---

### Task 3: Delete the stale calendar demos

The `build-demos.mjs` step walks `docs/site/demos/*.toml` and renders each — a `type = "calendar"` TOML now fails (widget removed from core). The reframed stub references no calendar gif, so these are dead.

**Files (delete):**
- `docs/site/demos/widget-calendar.toml`, `docs/site/demos/widget-calendar-next.toml`
- `docs/site/demos/calendar_sample.ics`, `docs/site/demos/calendar_next_sample.ics`
- any committed `docs/site/public/demos/widget-calendar*.gif`

- [ ] **Step 1: Delete the demo TOMLs + their ICS fixtures.**

```bash
git rm docs/site/demos/widget-calendar.toml docs/site/demos/widget-calendar-next.toml
git rm docs/site/demos/calendar_sample.ics docs/site/demos/calendar_next_sample.ics
```

- [ ] **Step 2: Remove any committed rendered gif.** Check whether the calendar demo gif is tracked:

```bash
git ls-files docs/site/public/demos/ | grep -i calendar
```

If it lists `widget-calendar*.gif`, `git rm` them. If nothing is listed, the gifs are auto-rendered/untracked — nothing to remove.

- [ ] **Step 3: Confirm `build-demos.mjs` is glob-based (no hardcoded calendar reference).** `grep -ni calendar docs/site/scripts/build-demos.mjs` — expect NO hits (it `readdirSync`s `demos/`). If it hardcodes a demo list including calendar, remove the calendar entry there too.

- [ ] **Step 4: Confirm no remaining reference to the deleted demos.**

```bash
grep -rn "widget-calendar\|calendar_sample\|calendar_next" docs/site/
```

Expect no hits (the reframed `calendar.mdx` no longer embeds a `DemoGif`).

- [ ] **Step 5: Commit.**

```bash
git add -A && git commit --no-verify -m "docs: remove stale calendar demo TOMLs/ICS (type calendar gone from core)"
```

---

### Task 4: Build the docs + verify + open PR

**Files:** none (verification + PR)

- [ ] **Step 1: Build the demos + site.** From `docs/site`, with the toolchain (corepack/pnpm):

```bash
cd docs/site
corepack enable 2>/dev/null || true
pnpm install
node scripts/build-demos.mjs
pnpm run build
```

Expected: `build-demos.mjs` completes with NO attempt to render a calendar TOML (they're deleted), and the Astro build succeeds with no broken-link / missing-import errors for the calendar page. 

> If the toolchain is unavailable in this environment, report that you could not run the local build and that you are relying on the `docs-lint` / `build-and-deploy` CI jobs to validate — do NOT mark this step done without either a local build or a clear note that CI must validate. At minimum, sanity-check: the reframed `calendar.mdx` has no dangling `import`/component references, and every internal link you touched (`/plugins/`, `/widgets/calendar/`) resolves to an existing page.

- [ ] **Step 2: Run the docs-related pytest drift tests.**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/calendar-phase4-docs
PYTHONPATH=tests/stubs uv run pytest tests/ -k "docs" -q
```

Expected: PASS. (Calendar isn't a `config.py` dataclass field, so `test_docs_config_options_drift` is unaffected; this confirms nothing else regressed.)

- [ ] **Step 3: Final grep — no stray core-widget calendar framing left in docs-site.**

```bash
grep -rn '"calendar"' docs/site/src docs/site/astro.config.mjs
grep -rn 'type = "calendar"' docs/site/
```

Expect: no `type = "calendar"` anywhere (only `calendar.events`); any remaining `calendar` references should be the plugin framing (`calendar.events`, the `/widgets/calendar/` route, the plugin links).

- [ ] **Step 4: Push + open PR (non-breaking).**

```bash
git push --no-verify -u origin worktree-calendar-phase4-docs
gh pr create --base main --title "docs: reframe calendar as the led-ticker-calendar plugin (Phase 4)" --body "<summary + test plan + post-merge cloudflared deploy-verify note>"
```

The PR body should note: this is the docs-site half of the calendar extraction (Phases 1–3 already shipped the code); it's non-breaking; and a post-merge step is to deploy-verify `/widgets/calendar/` + `/plugins/available/` via `cloudflared access` once `build-and-deploy` publishes.

- [ ] **Step 5: Watch CI to green (esp. `docs-lint` / `build-and-deploy`), then STOP.** Report PR URL + CI status. Do not merge without explicit go-ahead.

---

## Self-Review

**Spec coverage (Phase-4 portion of the design):**
- Reframe `widgets/calendar.mdx` as a plugin page (mirror pool/baseball) → Task 1. ✓
- Fix the orphaned `docs/content-source/widgets/calendar.md` → Task 1 (deleted — it's dead once the stub drops `OptionsTable`). ✓
- Update index / sidebar / plugins-available listings → Task 2. ✓
- Busy-light mention → deliberately left (it's a future busy-source, not the widget — documented in scope). ✓
- Deploy-verify via cloudflared → post-merge note in Task 4 (can't verify a live page before the deploy job runs). ✓
- Stale demos that would break the build → Task 3 (a build-correctness item the design implied via "demo files"). ✓

**Placeholder scan:** The PR-body `<...>` in Task 4 Step 4 is filled at PR time; its required content is specified. The `>` notes are verification/fallback instructions (match the exact install-snippet format; rely on CI if no local toolchain), not unfinished work.

**Consistency:** Every new reference uses `calendar.events` + the `led-ticker-calendar` repo URL `git+https://github.com/JamesAwesome/led-ticker-calendar.git@main`, matching the Phase-3 catalog entry and the plugin's actual type. The `/widgets/calendar/` route is preserved (page reframed, not removed), so existing inbound links and the sidebar/index entries stay valid.
