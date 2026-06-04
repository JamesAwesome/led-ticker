# Phase 6 — Plugin Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `led-ticker-pool`'s README the canonical pool documentation (with the rendered GIF screenshots), and give led-ticker a docs-site Plugins overview page, a slimmed `widgets/pool.mdx` pointer, a CLAUDE.md plugin-invariants section, and a config note.

**Architecture:** Documentation-only, across two repos / two PRs. Part A rewrites the `led-ticker-pool` README and copies in the two pool GIFs. Part B adds a lean docs-site Plugins page, slims the existing pool widget page to a pointer (preserving its URL), adds a Plugins nav group, a CLAUDE.md section, and refines a config comment. No production code changes. The deep plugin **authoring guide** is a future phase.

**Tech Stack:** Markdown, Astro Starlight (`docs/site/`, pnpm), Makefile docs targets.

**Spec:** `docs/superpowers/specs/2026-06-03-plugin-docs-phase6-design.md`

**Note on TDD:** this is a docs change — "tests" are build + lint + link/content checks, not failing-test-first. Each task ends with a concrete verification command.

**Worktrees / branches:**
- **Part A** — repo `/Users/james/projects/github/jamesawesome/led-ticker-pool`, on a new branch `docs/readme` (the pool repo is normally worked on `main`; use a branch here for the PR). Commit with `git -c core.hooksPath=/dev/null commit`.
- **Part B** — worktree `/Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-docs`, branch `feat/plugin-docs-phase6`. Verify the branch first (`git -C <wt> branch --show-current` → `feat/plugin-docs-phase6`). Commit with `git -C <wt> -c core.hooksPath=/dev/null commit`. Use ABSOLUTE worktree paths.

Do Part A first (so Part B can link to a real canonical README).

---

## File Structure

**Part A (led-ticker-pool):**
- Create: `docs/widget-pool.gif`, `docs/widget-pool-two-row.gif` (copied from led-ticker)
- Modify: `README.md` (scaffold → full canonical pool docs)

**Part B (led-ticker):**
- Create: `docs/site/src/content/docs/plugins/index.mdx` (Plugins overview)
- Modify: `docs/site/src/content/docs/widgets/pool.mdx` (→ slim pointer)
- Modify: `docs/site/astro.config.mjs` (add Plugins nav group)
- Modify: `CLAUDE.md` (add Plugin invariants section)
- Modify: `config/config.example.toml` (refine pool install comment)

---

# PART A — led-ticker-pool README (PR in the pool repo)

### Task A1: Copy GIFs + rewrite the README

**Files:**
- Create: `/Users/james/projects/github/jamesawesome/led-ticker-pool/docs/widget-pool.gif`
- Create: `/Users/james/projects/github/jamesawesome/led-ticker-pool/docs/widget-pool-two-row.gif`
- Modify: `/Users/james/projects/github/jamesawesome/led-ticker-pool/README.md`

- [ ] **Step 1: Create the branch + copy the GIFs**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-pool
git checkout main && git pull --ff-only 2>/dev/null; git checkout -b docs/readme
mkdir -p docs
cp /Users/james/projects/github/jamesawesome/led-ticker/docs/site/public/demos-long/widget-pool.gif docs/widget-pool.gif
cp /Users/james/projects/github/jamesawesome/led-ticker/docs/site/public/demos-long/widget-pool-two-row.gif docs/widget-pool-two-row.gif
ls -l docs/*.gif   # both present
```

- [ ] **Step 2: Replace `README.md` with the full canonical docs**

Overwrite `/Users/james/projects/github/jamesawesome/led-ticker-pool/README.md` with EXACTLY:

````markdown
# led-ticker-pool

A pool water-temperature monitor **widget** for [led-ticker](https://github.com/JamesAwesome/led-ticker), backed by an InfluxDB v2 server (e.g. [pool_monitor](https://github.com/JamesAwesome/pool_monitor)). It's a led-ticker **plugin** — installing this package contributes a `pool.monitor` widget you reference in your led-ticker config.

It cycles four screens — a title card, today's current temperature with a trend arrow (▲/▼/–) and hi/lo, a 7-day mean with hi/lo, and a season (current-year) hi/lo. Temperature is zone-colored — blue below 70°F, green 70–79°F, orange 80–89°F, red 90°F+ — so the comfort level is readable at a glance. Data is fetched in the background via async polling, so the display keeps running even if the server is briefly unreachable.

## Screenshots

**`layout = "ticker"`** (default — single-row segmented screens, smallsign-friendly):

![Pool widget in ticker layout — single-row segmented screens with trend arrow and hi/lo](docs/widget-pool.gif)

**`layout = "two_row"`** (stacked label-on-top / big-number-on-bottom, bigsign / longboi):

![Pool widget in two_row layout — stacked label-on-top, big-number-on-bottom](docs/widget-pool-two-row.gif)

## Install

The widget auto-registers via the `led_ticker.plugins` entry point — once the package is installed, no `[plugins]` config change is needed.

**Into a containerized led-ticker (recommended):** add this package to `config/requirements-plugins.txt` (copy it from `config/requirements-plugins.example.txt`, which already lists it), then rebuild:

```bash
# in your led-ticker checkout
cp config/requirements-plugins.example.txt config/requirements-plugins.txt
docker compose up -d --build
```

**Standalone (bare-metal / a venv that already has led-ticker):**

```bash
pip install "git+https://github.com/JamesAwesome/led-ticker-pool.git@main"
```

(led-ticker isn't on PyPI; in the image it's already installed, so the plugin resolves without it. See the led-ticker [Plugins docs](https://docs.ledticker.dev/plugins/) for the constraint-based install.)

## Configuration

Reference the widget in a playlist section by `type = "pool.monitor"`:

```toml
[[playlist.section.widget]]
type = "pool.monitor"
title = "POOL TEMPS"
units = "imperial"
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `title` | string | `"POOL TEMPS"` | Label shown on the title screen. |
| `sensor_id` | string | none | Sensor ID to filter on. Omit to use the only/first sensor in the bucket. Must match `[A-Za-z0-9_-]+`. |
| `units` | string | `"imperial"` | `"imperial"` (°F) or `"metric"` (°C). |
| `update_interval` | int | `300` | Seconds between InfluxDB fetches (5 min default). |
| `current_window` | string | `"-24h"` | How far back to search for the latest reading, as a negative Flux duration (`"-24h"`, `"-90m"`). Older than this → `--` placeholder. Widen it if your sensor reports infrequently. |
| `stale_after` | int | `14400` | Seconds since the last reading before the temperature dims to gray (stale signal). 4 h default. |
| `influxdb_url` | string | `$INFLUXDB_URL` / `"http://influxdb:8086"` | InfluxDB v2 base URL. Config overrides the env var. |
| `influxdb_org` | string | `$INFLUXDB_ORG` / `"pool"` | InfluxDB organization. |
| `influxdb_bucket` | string | `$INFLUXDB_BUCKET` / `"pool_temps"` | InfluxDB bucket. |
| `influxdb_token` | string | `$INFLUXDB_TOKEN` | InfluxDB v2 token. **Required** — the widget raises `ValueError` at startup if it's missing. |
| `layout` | `"ticker"` \| `"two_row"` | `"ticker"` | Render mode (see below). |
| `label_color` | `[r,g,b]` | white | Color for prefix labels / separators. |
| `top_font` / `top_font_size` / `top_font_threshold` | font / int / int | inherit | **two_row only:** top (label) row font knobs. |
| `bottom_font` / `bottom_font_size` / `bottom_font_threshold` | font / int / int | inherit | **two_row only:** bottom (value) row font knobs. |
| `top_row_height` | int (logical rows) | `None` | **two_row only:** top band height. `None` = symmetric 8/8 split. |

The per-row knobs apply ONLY when `layout = "two_row"`; setting them under `ticker` fails config validation.

### Layouts

- **`ticker`** (default) — single-row segmented screens; the today screen shows current temp + trend arrow and hi/lo, the 7-day screen the mean + hi/lo, the season screen HI/LO together. Best for small panels (smallsign 160×16).
- **`two_row`** — stacked label-on-top / big-number-on-bottom. Top row a label (`POOL 24H`, `POOL 7D AVG`, `POOL SEASON HI`, `POOL SEASON LO`); bottom row the headline value in a semantic color. The trend arrow is dropped (bottom is the value only); season splits into HI and LO screens. Best for bigsign / longboi (256×64 / 512×64).

A `two_row` example:

```toml
[[playlist.section.widget]]
type = "pool.monitor"
title = "POOL TEMPS"
layout = "two_row"
units = "imperial"
font = "Inter-Regular"
font_size = 32
label_color = [130, 220, 255]
```

## InfluxDB setup

The widget reads connection details from your led-ticker `.env` (or per-widget overrides). `INFLUXDB_TOKEN` is required; the rest default to the standard pool_monitor Docker Compose stack.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `INFLUXDB_TOKEN` | **yes** | — | InfluxDB v2 auth token. |
| `INFLUXDB_URL` | no | `http://influxdb:8086` | Base URL. |
| `INFLUXDB_ORG` | no | `pool` | Organization. |
| `INFLUXDB_BUCKET` | no | `pool_temps` | Bucket. |

The widget queries water-temperature readings with Flux over HTTP and computes today / 7-day / season aggregates. Stale data (older than `stale_after`) renders dim gray; the trend arrow compares the latest reading to a 30-minute trailing average (sub-0.5°F shows `–`).

## Development

led-ticker isn't on PyPI, so install it editable from a sibling checkout. This repo's `pyproject.toml` pins `led-ticker` to `../led-ticker` via `[tool.uv.sources]`:

```bash
git clone https://github.com/JamesAwesome/led-ticker ../led-ticker   # sibling checkout
git clone https://github.com/JamesAwesome/led-ticker-pool && cd led-ticker-pool
uv venv
uv pip install -e ../led-ticker -e ".[dev]"
uv run pytest -q
```

> **Note:** led-ticker's `graphics` surface works headless via its bundled stub, but the full `RGBMatrix`/canvas test stub lives in led-ticker's `tests/stubs/` and isn't shipped. This repo's tests put it on the path via `pyproject.toml`'s `[tool.pytest.ini_options] pythonpath = ["../led-ticker/tests/stubs"]`.

## Links

- led-ticker project: <https://github.com/JamesAwesome/led-ticker>
- led-ticker plugin system: <https://docs.ledticker.dev/plugins/>
````

- [ ] **Step 3: Verify content + GIFs**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-pool
test -f docs/widget-pool.gif && test -f docs/widget-pool-two-row.gif && echo "gifs ok"
grep -q "pool.monitor" README.md && grep -q "docs/widget-pool.gif" README.md && grep -q "docs/widget-pool-two-row.gif" README.md && echo "content ok"
# no stale scaffold language:
grep -q "Phase 2 scaffold" README.md && echo "FAIL: stale status line still present" || echo "status line removed ok"
# code fences balanced:
python3 -c "import pathlib; t=pathlib.Path('README.md').read_text(); assert t.count('\`\`\`') % 2 == 0, 'unbalanced fences'; print('fences ok')"
```
Expected: `gifs ok`, `content ok`, `status line removed ok`, `fences ok`.

- [ ] **Step 4: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-pool
git add README.md docs/widget-pool.gif docs/widget-pool-two-row.gif
git -c core.hooksPath=/dev/null commit -m "docs: full pool README with screenshots, options, layouts, InfluxDB setup"
```

### Task A2: Push + open the pool-repo PR

- [ ] **Step 1: Push the branch**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-pool
git -c core.hooksPath=/dev/null push -u origin docs/readme
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --repo JamesAwesome/led-ticker-pool --base main --head docs/readme \
  --title "docs: full pool README (canonical docs + screenshots)" \
  --body "Expands the scaffold README into the canonical pool documentation: intro, ticker/two_row screenshots (rendered GIFs), install (requirements-plugins.txt / Docker / standalone), options table, layouts, example configs, InfluxDB setup, and the dev section. Part of led-ticker plugin-docs Phase 6."
```

- [ ] **Step 3: Watch CI** (the pool repo runs lint + tests on PRs; this is a docs-only change so it should pass)

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-pool
PR=$(gh pr view docs/readme --json number --jq .number)
gh pr checks "$PR" --watch --interval 15 2>&1 | tail -8
```
Expected: green. (Do NOT merge — the controller confirms merges with the user.)

---

# PART B — led-ticker docs (PR in the worktree `feat/plugin-docs-phase6`)

`<wt>` = `/Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-docs`. Verify branch first: `git -C <wt> branch --show-current` → `feat/plugin-docs-phase6`.

### Task B1: Plugins overview page

**Files:**
- Create: `<wt>/docs/site/src/content/docs/plugins/index.mdx`

- [ ] **Step 1: Create the page**

Create `<wt>/docs/site/src/content/docs/plugins/index.mdx` with EXACTLY:

````mdx
---
title: Plugins
description: Extend led-ticker with external plugins — widgets, transitions, emojis, fonts, and lifecycle hooks — installed via a requirements file and auto-registered at startup.
---

Plugins extend led-ticker without forking core. A plugin is a small Python package that registers extra **widgets, transitions, color providers, animations, borders, easings, emojis, fonts, or lifecycle hooks** through led-ticker's public plugin API. The flagship example is the [pool water-temperature widget](https://github.com/JamesAwesome/led-ticker-pool), which lives in its own repo and contributes `type = "pool.monitor"`.

## Installing a plugin

Plugins are declared in `config/requirements-plugins.txt` (a pip requirements file). Copy the tracked template and add or keep the plugins you want, then rebuild:

```bash
cp config/requirements-plugins.example.txt config/requirements-plugins.txt
# edit the list, then:
docker compose up -d --build
```

- The Docker image installs the listed plugins at build time, **constrained to core's dependency versions** (a plugin can bring its own new libraries but can't move a version core pins — a conflict fails the build instead of breaking silently at runtime).
- Bare-metal installs (`deploy/install.sh`) do the same.
- The live `config/requirements-plugins.txt` is gitignored — it's yours to customize per sign. A fresh clone installs **no** plugins until you create it.

Once installed, a plugin **auto-registers** via its `led_ticker.plugins` entry point — no config change is needed to make its widgets available.

## Relationship to the `[plugins]` config block

These are complementary layers:

- **`config/requirements-plugins.txt`** controls what is **installed** (build time).
- The optional **`[plugins]` block** in `config.toml` controls what is **loaded**: `enabled` toggles plugin loading, `disable = ["namespace"]` skips a plugin, and `dir` points at a local-plugin directory. It does not install anything.

A plugin must be installed **and** not disabled to be active.

## Writing a plugin

A plugin imports only from `led_ticker.plugin` (the curated public surface) and exposes a `register(api)` function under the `led_ticker.plugins` entry-point group; `api.widget("name")(cls)` registers a namespaced widget (`<plugin>.<name>`). The engineering reference — the `register(api)` contract, the public surface, authoring patterns, and lifecycle hooks — is in [`docs/plugin-system.md`](https://github.com/JamesAwesome/led-ticker/blob/main/docs/plugin-system.md). A full step-by-step authoring guide is planned.

## Available plugins

- **[led-ticker-pool](https://github.com/JamesAwesome/led-ticker-pool)** — pool water-temperature widget (`pool.monitor`), backed by InfluxDB. Full docs + screenshots in its README.
````

- [ ] **Step 2: Verify it parses (deferred to the Task B6 build).** For now confirm the file exists and frontmatter is present:

```bash
head -4 <wt>/docs/site/src/content/docs/plugins/index.mdx   # shows the --- title: Plugins --- frontmatter
```

- [ ] **Step 3: Commit**

```bash
git -C <wt> add docs/site/src/content/docs/plugins/index.mdx
git -C <wt> -c core.hooksPath=/dev/null commit -m "docs(site): add Plugins overview page"
```

### Task B2: Slim `widgets/pool.mdx` to a pointer

**Files:**
- Modify: `<wt>/docs/site/src/content/docs/widgets/pool.mdx`

- [ ] **Step 1: Replace the page** with EXACTLY:

````mdx
---
title: pool widget
description: The pool water-temperature widget is now the external led-ticker-pool plugin (type = "pool.monitor").
---

The **pool** widget has moved out of led-ticker core into its own plugin, **[led-ticker-pool](https://github.com/JamesAwesome/led-ticker-pool)**, referenced in config as `type = "pool.monitor"`.

- **Full documentation** — options, `ticker` vs `two_row` layouts, InfluxDB setup, and screenshots — lives in the [led-ticker-pool README](https://github.com/JamesAwesome/led-ticker-pool#readme).
- **How to install it** into your sign: see [Plugins](/plugins/).

Pool is the flagship example of led-ticker's [plugin system](/plugins/) — a way to add widgets that aren't part of core.
````

- [ ] **Step 2: Verify** no dangling component imports remain (the slim page uses none):

```bash
grep -qE "OptionsTable|DemoGif|TomlExample|RelatedPages" <wt>/docs/site/src/content/docs/widgets/pool.mdx && echo "FAIL: stale component import" || echo "clean (no component imports)"
```
Expected: `clean (no component imports)`.

- [ ] **Step 3: Commit**

```bash
git -C <wt> add docs/site/src/content/docs/widgets/pool.mdx
git -C <wt> -c core.hooksPath=/dev/null commit -m "docs(site): slim pool widget page to a pointer (pool is now a plugin)"
```

### Task B3: Add the Plugins nav group

**Files:**
- Modify: `<wt>/docs/site/astro.config.mjs`

- [ ] **Step 1: Insert the Plugins group** directly AFTER the `Widgets` sidebar group's closing `},` and BEFORE the `Transitions` group. Find this exact text in `astro.config.mjs`:

```javascript
            { label: "pool", link: "/widgets/pool/" },
          ],
        },
        {
          label: "Transitions",
```
and replace it with:

```javascript
            { label: "pool", link: "/widgets/pool/" },
          ],
        },
        {
          label: "Plugins",
          items: [
            { label: "Plugins overview", link: "/plugins/" },
            {
              label: "pool (led-ticker-pool)",
              link: "https://github.com/JamesAwesome/led-ticker-pool#readme",
            },
          ],
        },
        {
          label: "Transitions",
```
(This keeps `pool` under Widgets as the pointer page AND adds a Plugins group with the overview + the external canonical README link.)

- [ ] **Step 2: Verify JS is still valid**

```bash
cd <wt>/docs/site && node --check astro.config.mjs && echo "astro.config.mjs parses ok"
```
Expected: `astro.config.mjs parses ok`.

- [ ] **Step 3: Commit**

```bash
git -C <wt> add docs/site/astro.config.mjs
git -C <wt> -c core.hooksPath=/dev/null commit -m "docs(site): add Plugins sidebar group"
```

### Task B4: CLAUDE.md plugin-invariants section

**Files:**
- Modify: `<wt>/CLAUDE.md`

- [ ] **Step 1: Add the section.** Read `<wt>/CLAUDE.md`, find the "Adding a New Widget" guidance section (grep `Adding a New Widget`). Insert this new section immediately BEFORE it (if that heading isn't found, append the section at the end of the file). Insert EXACTLY:

```markdown
## Plugin invariants

led-ticker is extensible via plugins; the `pool.monitor` widget lives in the external [`led-ticker-pool`](https://github.com/JamesAwesome/led-ticker-pool) repo. When touching plugin-related code:

- **Public surface:** plugins import ONLY from `led_ticker.plugin` (the curated re-export module). Never import `led_ticker.<internal>` from a plugin. `led_ticker.plugin.__all__` is the contract; adding to it is an API change.
- **Registration:** a plugin ships a `register(api)` function under the `led_ticker.plugins` entry-point group; `api.widget("name")(cls)` (and the sibling `transition`/`emoji`/`font`/… surfaces) register into a namespaced registry (`<plugin>.<name>`, e.g. `pool.monitor`). `API_VERSION` gates compatibility.
- **Install:** plugins are installed from `config/requirements-plugins.txt` (copied from `.example`), built with `-c constraints-core.txt` — NOT `--no-deps` — so they may bring new deps but can't move core's pinned versions. Entry points auto-register at startup; the `[plugins]` config block only controls loading/disable, not installation.
- **Validation:** a widget plugin may define `validate_config(cls, cfg) -> list[str]` (pre-coercion); it runs inside `validate_widget_cfg`.
- **Python 3.14 / PEP 649:** no `from __future__ import annotations` in plugin source (same rule as core).
- Deep reference: `docs/plugin-system.md`. User-facing overview: the docs-site [Plugins page](https://docs.ledticker.dev/plugins/).
```

- [ ] **Step 2: Verify**

```bash
grep -q "## Plugin invariants" <wt>/CLAUDE.md && grep -q "led_ticker.plugins" <wt>/CLAUDE.md && echo "section added ok"
```
Expected: `section added ok`.

- [ ] **Step 3: Commit**

```bash
git -C <wt> add CLAUDE.md
git -C <wt> -c core.hooksPath=/dev/null commit -m "docs: add Plugin invariants section to CLAUDE.md"
```

### Task B5: Refine the config.example pool install comment

**Files:**
- Modify: `<wt>/config/config.example.toml`

- [ ] **Step 1: Update the comment.** Find the pool install comment block in `config/config.example.toml` (grep `led-ticker-pool` — it currently mentions `pip install "git+...led-ticker-pool.git@main"`). Replace that comment block (the 3-4 lines from `# The pool widget is now the` through the `pip install ...`/entry-point line) with EXACTLY:

```toml
# The pool widget is the `led-ticker-pool` plugin (type = "pool.monitor"). To
# install it, add it to config/requirements-plugins.txt (copy the tracked
# .example, which already lists it) and rebuild — see
# https://docs.ledticker.dev/plugins/ . The entry point auto-registers it.
```
Leave the `[[playlist.section.widget]]` pool block itself unchanged.

- [ ] **Step 2: Validate the config still parses** (with the plugin installed, via the pool repo venv which has both):

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-pool && uv run led-ticker validate <wt>/config/config.example.toml 2>&1 | grep -vE "plugin 'pool' loaded|^$" | tail -3
```
Expected: `No issues found.`

- [ ] **Step 3: Commit**

```bash
git -C <wt> add config/config.example.toml
git -C <wt> -c core.hooksPath=/dev/null commit -m "docs: point config.example pool comment at requirements-plugins + Plugins docs"
```

### Task B6: Build the docs site, run checks, open the led-ticker PR

**Files:** none (verification + PR)

- [ ] **Step 1: Build the docs site** (catches broken MDX, frontmatter, and internal links)

```bash
cd <wt> && make docs-build 2>&1 | tail -20
```
Expected: build succeeds (`pnpm run build` → astro build completes, `docs/site/dist/` produced). If a broken internal link is reported (e.g. `/plugins/`), confirm the new page exists at `docs/site/src/content/docs/plugins/index.mdx`.

- [ ] **Step 2: Docs lint** (prettier + astro check)

```bash
cd <wt> && make docs-lint 2>&1 | tail -20
```
Expected: clean. If prettier flags formatting, run `cd <wt> && make docs-format`, then re-run `make docs-lint`, and `git add` + amend or new commit the formatting.

- [ ] **Step 3: Full Python suite** (the slimmed pool.mdx must not break any docs/config-drift test; `docs/content-source/widgets/pool.md` is intentionally left in place)

```bash
cd <wt> && make test 2>&1 | tail -6
```
Expected: green. If a test asserts every `docs/content-source/widgets/*.md` is referenced by a docs page and now fails for `pool.md` (orphaned after the slim), the minimal fix is to keep a single `<OptionsTable source="widgets/pool" />` reference is NOT desired (we want the pointer) — instead adjust that test to exclude `pool` (plugin-provided), with a comment. Report which test and how you handled it.

- [ ] **Step 4: Commit any lint/format fixups, then push**

```bash
git -C <wt> status --porcelain   # commit anything from format fixups first
git -C <wt> -c core.hooksPath=/dev/null push -u origin feat/plugin-docs-phase6
```

- [ ] **Step 5: Open the PR**

```bash
gh pr create --repo JamesAwesome/led-ticker --base main --head feat/plugin-docs-phase6 \
  --title "docs: plugin system documentation (Plugins page, pool pointer, CLAUDE.md invariants)" \
  --body "Phase 6 of the pool extraction (led-ticker side). Adds a docs-site Plugins overview page (install via requirements-plugins.txt, entry-point auto-registration, [plugins] relationship, authoring teaser → plugin-system.md), slims widgets/pool.mdx to a pointer at the canonical led-ticker-pool README (URL preserved), adds the Plugins nav group, a CLAUDE.md plugin-invariants section, and refines the config.example pool comment. Pairs with led-ticker-pool#<README PR>. Full authoring guide deferred to a later phase."
```

- [ ] **Step 6: Watch CI**

```bash
cd <wt> && gh pr checks $(gh pr view feat/plugin-docs-phase6 --json number --jq .number) --watch --interval 15 2>&1 | tail -10
```
Expected: green (incl. `docs-lint`). Do NOT merge — the controller confirms merges with the user.

---

## Notes for the implementer

- **Do Part A before Part B** so the docs-site Plugins page links to a live canonical README.
- The two PRs are independent repos; neither merges without the user's explicit go-ahead.
- Don't delete `docs/content-source/widgets/pool.md` — it may feed generation/tests; the README carries its own options copy.
- The slim `widgets/pool.mdx` deliberately drops the `<OptionsTable>`/`<DemoGif>` components — the GIFs now live in the pool repo and the options live in the README.
- No production `src/` code changes in this phase.
