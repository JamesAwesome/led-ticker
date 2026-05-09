# Docs Site Content — Plan B3: Tools, Hardware, Reference, Showcase

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Author the third (and final) batch of docs site content — three Tools pages (render-demo, validate, creating-a-config), three Hardware pages (small-sign, bigsign, building-your-own), two Reference pages (config-options, cli), and the Showcase shell + a moonbunny placeholder entry. Plus a `.github/ISSUE_TEMPLATE/submit-sign.yml` so non-coders can submit signs without opening a PR. Plus the sidebar wiring that exposes the four new top-level sections.

**Architecture:** Same patterns as B1/B2 — every page = MDX + (optional) demo TOML or fact-pack. C-tier minimum: intro paragraph + ≥1 example or table + Pitfalls callouts (where applicable) + RelatedPages cluster. Use **"Pitfalls"** as the section heading, never "Footguns". Tool/hardware/reference pages are mostly text — no data-feed live-fetch problems, so demo gifs are added only where they genuinely help (e.g., the validator's CLI output is best shown as a code block, not a gif).

**Reference page strategy:** No `FIELD_REGISTRY` exists in `src/led_ticker/validate.py` (validator works via exception-message pattern matching, and per-widget options are documented as hand-curated `docs/content-source/widgets/<name>.md` fact-pack tables). `reference/config-options.mdx` is therefore hand-curated, organized by **section** (display, transitions, sections, widgets) rather than by widget — its job is the cross-cutting view, not to duplicate the per-widget tables. A follow-up issue will track auto-generation from the attrs class definitions once the registry is in place.

**Showcase strategy:** Per user input, ship the gallery shell *and* a moonbunny placeholder entry now (photos can be added in a follow-up PR). The entry uses a `[placeholder]` style image so the page builds without missing-asset errors.

**Tech stack:** No new infrastructure. Same components, same renderer, same lint pipeline. Subagents must run `pnpm run lint` from `docs/site/` before each commit. The pre-commit hook will catch drift but it's faster to clean up before commit.

---

## File map

### Tools pages (3)

| File | Action | Demo? |
|------|--------|-------|
| `docs/site/src/content/docs/tools/render-demo.mdx` | Create | no (the script *is* the demo pipeline; one example invocation) |
| `docs/site/src/content/docs/tools/validate.mdx` | Create | no (CLI output as code block) |
| `docs/site/src/content/docs/tools/creating-a-config.mdx` | Create | no (skill walkthrough) |

### Hardware pages (3)

| File | Action | Demo? |
|------|--------|-------|
| `docs/site/src/content/docs/hardware/small-sign.mdx` | Create | no |
| `docs/site/src/content/docs/hardware/bigsign.mdx` | Create | no |
| `docs/site/src/content/docs/hardware/building-your-own.mdx` | Create | no |

### Reference pages (2)

| File | Action | Demo? |
|------|--------|-------|
| `docs/site/src/content/docs/reference/config-options.mdx` | Create | no |
| `docs/site/src/content/docs/reference/cli.mdx` | Create | no (CLI snippets) |

### Showcase + submission (3)

| File | Action |
|------|--------|
| `docs/site/src/content/docs/showcase.mdx` | Create — gallery shell + moonbunny placeholder + "Submit your sign" CTA |
| `docs/site/public/showcase/moonbunny/placeholder.svg` | Create — minimal SVG placeholder so the entry builds |
| `.github/ISSUE_TEMPLATE/submit-sign.yml` | Create — issue form for non-coder submissions |

### Sidebar wiring (1)

| File | Action |
|------|--------|
| `docs/site/astro.config.mjs` | Modify — add Tools, Hardware, Reference top-level sections; add Showcase as a top-level link |

**Total: 12 new files, 1 modify.**

---

## Per-page contract (refresher from B1/B2)

Every page imports the standard component bundle from `../../../components/` (path depth varies by directory level — Tools/Hardware/Reference are one level deep; Showcase is at the root). Subagents must read one existing page from a comparable directory level as a style reference before drafting:

- For Tools / Hardware / Reference (one level): read `concepts/fonts.mdx` or `widgets/message.mdx`.
- For Showcase (root level): read `getting-started.mdx`.

Use `:::note` / `:::tip` / `:::caution` Starlight admonitions where a callout improves readability — same convention used throughout B1/B2.

---

## Task 1: Tools — render-demo page

**Files:**
- Create: `docs/site/src/content/docs/tools/render-demo.mdx`

Source-of-truth references:
- `tools/render_demo/README.md` — local-run instructions
- `tools/render_demo/render.py` — flags surface
- `Makefile` — `render-demo`, `render-long-demos`, `render-long-demo` targets
- `docs/site/scripts/build-demos.mjs` — the auto-pipeline that runs on every Cloudflare build, including the new `# render-duration:` comment convention

- [ ] **Step 1: Read the source**

```bash
cat tools/render_demo/README.md
cat tools/render_demo/render.py | head -60     # CLI flag surface
grep -E 'render-' Makefile
head -50 docs/site/scripts/build-demos.mjs
```

- [ ] **Step 2: Read the style reference**

```bash
cat docs/site/src/content/docs/concepts/fonts.mdx
```

Note: import depth (`../../../components/`), section headings, OptionsTable / TomlExample / DemoGif usage where applicable.

- [ ] **Step 3: Write the page**

Required sections (in order):

1. **Frontmatter** — `title: "Tool: render-demo"`, one-sentence description.
2. **Intro paragraph** — what render-demo is (a Python script that takes a TOML config and produces a gif at panel resolution by running the actual ticker engine against the test stub canvas), why it exists (visual docs without real hardware), and where it lives (`tools/render_demo/render.py`).
3. **Two pipelines** — auto-rendered (`docs/site/demos/`, regenerated on every Cloudflare build, output gitignored) vs long-running (`docs/site/demos-long/`, manual `make render-long-demos`, output committed). Same wording the docs/site README uses; cross-reference don't duplicate.
4. **Quick start** — `make render-demo CONFIG=<path> OUT=<path>` with example. Show one TomlExample of a tiny demo TOML and the resulting `make render-demo` invocation.
5. **CLI flags** — `--duration N` (capture window in seconds; default 5) and `--out` / `-o`. Document the per-demo `# render-duration: N` comment convention introduced in the previous PR (link to `build-demos.mjs`'s comment).
6. **API-key-required widgets** — `# requires-env: VAR` comment in long-demo TOMLs causes `make render-long-demos` to skip them when the env var isn't set. Reference the WeatherAPI / Etherscan widgets specifically.
7. **Pitfalls** — (a) the renderer captures every `SwapOnVSync` so durations match wall-clock playback, but live-API widgets in a 5-sec window often show cached / placeholder data; (b) the test stub canvas does NOT support hi-res TTF fonts the same way real hardware does, so panel-rendered output may differ slightly; (c) gifs at panel resolution can hit pillar-box scaling on docs site retina displays — that's expected.
8. **RelatedPages** — `tools/validate`, `tools/creating-a-config`, `concepts/display`.

- [ ] **Step 4: Lint and build**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3
```

Expected: 0 errors, page builds.

- [ ] **Step 5: Commit**

```bash
git add docs/site/src/content/docs/tools/render-demo.mdx
git commit -m "docs: tools/render-demo page"
```

---

## Task 2: Tools — validate page

**Files:**
- Create: `docs/site/src/content/docs/tools/validate.mdx`

Source-of-truth references:
- `src/led_ticker/validate.py` — rule list, JSON output shape, severity levels
- `src/led_ticker/app.py` — how the CLI exposes `validate` subcommand
- `docs/superpowers/specs/2026-05-07-config-validator-design.md` — original design

- [ ] **Step 1: Read the source**

```bash
head -120 src/led_ticker/validate.py
grep -E 'validate|--json' src/led_ticker/app.py | head
```

- [ ] **Step 2: Read the style reference**

```bash
cat docs/site/src/content/docs/concepts/fonts.mdx
```

- [ ] **Step 3: Write the page**

Required sections:

1. **Frontmatter** — `title: "Tool: validate"`, one-sentence description.
2. **Intro** — what `led-ticker validate` does (statically inspects a config TOML against the decision-rule registry, surfaces errors that would block the ticker at runtime and warnings the user might still want to see), why it exists (catch the most common config mistakes pre-deploy on the Pi).
3. **Quick start** — `led-ticker validate config/config.toml` (human-readable) and `led-ticker validate config/config.toml --json` (machine-readable; used by the `creating-a-config` skill). Show one example of each output.
4. **Output format** — describe the JSON shape: `{ "valid": bool, "errors": [...], "warnings": [...] }` with each issue having `rule`, `location`, `message`, `fix`, `severity`. Cite `src/led_ticker/validate.py` for the source-of-truth `ValidationIssue` dataclass.
5. **Rule index** — short table of currently-validated rules. Read `_ERROR_PATTERNS` in `validate.py` and any rule references in `docs/content-source/rules/*.md`. Three columns: `Rule #`, `Subject`, `Severity`. Don't try to be exhaustive — list the ones that have fact-pack files in `content-source/rules/` (those are the documented rules; the rest are validator-only).
6. **Pitfalls** — (a) the validator catches static / TOML-parse-level issues; widget-specific runtime errors (e.g., bad WeatherAPI key, missing image asset) only surface at runtime; (b) warnings are advisory — the ticker will still run, but the warning often points at a rendering quirk you don't want.
7. **RelatedPages** — `tools/creating-a-config`, `pitfalls`, `tools/render-demo`.

- [ ] **Step 4: Lint and build, commit**

Same pattern as Task 1, message: `docs: tools/validate page`.

---

## Task 3: Tools — creating-a-config skill page

**Files:**
- Create: `docs/site/src/content/docs/tools/creating-a-config.mdx`

Source-of-truth references:
- `.claude/skills/creating-a-config/SKILL.md` — the skill definition
- `.claude/skills/creating-a-config/references/` — snippets, hardware-guide, decision-rules, asset-handling, transitions, widgets
- `docs/superpowers/specs/2026-05-07-creating-a-config-skill-design.md` — original design

- [ ] **Step 1: Read the source**

```bash
cat .claude/skills/creating-a-config/SKILL.md | head -80
ls .claude/skills/creating-a-config/references/
```

- [ ] **Step 2: Read the style reference**

```bash
cat docs/site/src/content/docs/concepts/fonts.mdx
```

- [ ] **Step 3: Write the page**

Required sections:

1. **Frontmatter** — `title: "Tool: creating-a-config skill"`, one-sentence description.
2. **Intro** — what the skill does (interactive 3-mode wizard for building or refining a `config/config.toml` — modes: `new`, `add`, `refine`), where it lives (`.claude/skills/creating-a-config/`), what platforms support it (Claude Code's `/creating-a-config` slash command, plus the platforms listed in the skill's frontmatter).
3. **Modes** — three subsections:
   - `new` — 3-phase wizard (Outline → Per-section → Polish). Cite the 7 outline questions briefly.
   - `add` — append a section to an existing config. Cite the use-case auto-detection step.
   - `refine` — symptom-driven tuning. List the 8 stock symptoms verbatim from the skill ("Too small to read at viewing distance", etc.).
4. **Validation philosophy** — the skill never silently auto-fixes; every violation is flag-and-ask. Cross-reference `tools/validate`.
5. **Asset handling** — the skill places fonts in `config/fonts/` and images in `config/assets/`. Don't re-document the full asset matrix — link to the references in the skill source.
6. **Pitfalls** — (a) the skill's snippet library was authored before hi-res fonts existed in some places; the skill applies brand-font defaults across all text widgets in Phase 1, so you don't have to remember to set `font` on each. (b) running the skill outside Claude Code requires manually following the SKILL.md flow.
7. **RelatedPages** — `tools/validate`, `concepts/sections-and-modes`, `getting-started`.

- [ ] **Step 4: Lint and build, commit**

Message: `docs: tools/creating-a-config page`.

---

## Task 4: Hardware — small-sign page

**Files:**
- Create: `docs/site/src/content/docs/hardware/small-sign.mdx`

Source-of-truth references:
- `CLAUDE.md` — Hardware section ("Small sign (Pi 4)" subsection has the BOM)
- `config/config.example.toml` — small-sign-flavored config snippet
- `Makefile` — Docker build commands

- [ ] **Step 1: Read the source**

```bash
grep -A 15 'Small sign' CLAUDE.md
grep -A 5 '\[display\]' config/config.example.toml
```

- [ ] **Step 2: Read the style reference**

```bash
cat docs/site/src/content/docs/getting-started.mdx
```

- [ ] **Step 3: Write the page**

Required sections:

1. **Frontmatter** — `title: "Hardware: Small sign"`, one-sentence description.
2. **At a glance** — bullet list: Pi 4 Model B, 5× chained 32×16 panels = 160×16 pixels, ~20 fps, single Docker image, `default_scale = 1`.
3. **Bill of materials** — table: Component, Quantity, Notes. Cover Pi 4, the panels, the Adafruit RGB matrix bonnet (or HAT), 5V power supply (sized for the chain), shroud / case if relevant. Mention the `led_gpio_mapping = "adafruit-hat"` setting.
4. **Wiring** — short prose. Note the chain order matters (last panel = rightmost on screen); document the standard data-cable + power-cable layout. Reference the config snippet (next section) for `chain` and `parallel`.
5. **Config snippet** — a TomlExample with the minimal `[display]` block from `config.example.toml` (rows=16, cols=32, chain=5, default_scale=1, brightness=60, led_gpio_mapping="adafruit-hat", led_slowdown_gpio=2). Brief inline notes on each line.
6. **Pitfalls** — (a) `led_slowdown_gpio` is mandatory on Pi 4 — without it the panels glitch; bump it if flicker. (b) `default_scale` is 1 here; do NOT set it to >1 (no logical-to-physical wrapping on a 16-tall canvas). (c) brightness is 0–100 not 0–255.
7. **RelatedPages** — `hardware/bigsign`, `hardware/building-your-own`, `getting-started`.

- [ ] **Step 4: Lint and build, commit**

Message: `docs: hardware/small-sign page`.

---

## Task 5: Hardware — bigsign page

**Files:**
- Create: `docs/site/src/content/docs/hardware/bigsign.mdx`

Source-of-truth references:
- `CLAUDE.md` — Hardware section ("Bigsign (Pi 5)" subsection)
- `config/config.bigsign.example.toml` — bigsign-flavored example
- `docs/superpowers/specs/2026-04-29-pi5-bigsign-port-design.md` — original Pi 5 port design

- [ ] **Step 1: Read the source**

```bash
grep -A 20 'Bigsign' CLAUDE.md
head -60 config/config.bigsign.example.toml
```

- [ ] **Step 2: Read the style reference**

```bash
cat docs/site/src/content/docs/concepts/display.mdx
```

- [ ] **Step 3: Write the page**

Required sections:

1. **Frontmatter** — `title: "Hardware: Bigsign"`, one-sentence description.
2. **At a glance** — Pi 5, 8× P3 32×64 panels in a 2×4 vertical-serpentine layout = 256×64 pixels, `default_scale = 4`, drawing logic stays at 16-tall logical and `ScaledCanvas` blows it up. Same Docker image as the small sign.
3. **Bill of materials** — table. Cover Pi 5, the 8 panels, Adafruit HAT or equivalent, 5V power supply (sized for 8 panels), shroud / frame. Note the rgbmatrix library detects the SoC at runtime.
4. **The 2×4 serpentine layout** — one paragraph + a small ASCII diagram showing how the 8 panels are arranged and the data chain order. Reference `pixel_mapper` in the config snippet.
5. **Config snippet** — a TomlExample with the minimal `[display]` block from `config.bigsign.example.toml`. Include `rows`, `cols`, `chain`, `parallel`, `default_scale`, `pixel_mapper`, `pwm_bits`, `rp1_rio`, `led_slowdown_gpio`. Inline notes on the Pi-5-specific knobs.
6. **Pi-5 tuning** — 3 short subsections:
   - `pwm_bits = 8` (down from default 11) for ~8× faster refresh; minor color hit.
   - `rp1_rio = 1` (RIO mode — faster, more CPU; `0` = PIO mode, lower CPU).
   - `led_slowdown_gpio = 3` paired with `rp1_rio = 1`; raise to 4–5 if flicker.
7. **Pitfalls** — (a) **`content_height ≤ 16` ceiling**: at scale=4 panels are 64-tall, so `content_height = 20` makes the wrapper's `_y_offset` go negative and content clips silently; explicit warning. (b) `pixel_mapper` Remap string is sensitive to the panel chain order — the 2×4 serpentine string is what config.bigsign.example.toml uses. (c) hi-res emoji (`:moon:`, `:instagram:`) only render on bigsign at scale=4; on small-sign they fall back to 8×8 lo-res.
8. **RelatedPages** — `hardware/small-sign`, `concepts/display`, `concepts/fonts`.

- [ ] **Step 4: Lint and build, commit**

Message: `docs: hardware/bigsign page`.

---

## Task 6: Hardware — building-your-own page

**Files:**
- Create: `docs/site/src/content/docs/hardware/building-your-own.mdx`

Source-of-truth references:
- `CLAUDE.md` — full Hardware section
- `tools/render_demo/render.py` — proof you can develop without hardware
- `Makefile` — `make test` (no hardware needed) + `make build-docker`

- [ ] **Step 1: Read the source**

```bash
grep -A 50 '### Hardware' CLAUDE.md
```

- [ ] **Step 2: Read the style reference**

```bash
cat docs/site/src/content/docs/getting-started.mdx
```

- [ ] **Step 3: Write the page**

Required sections:

1. **Frontmatter** — `title: "Hardware: Building your own"`, one-sentence description.
2. **Intro** — for users who want to build from scratch. Two main reference designs: small-sign (pages → small-sign) and bigsign (pages → bigsign). This page covers the cross-cutting decisions and the no-hardware development path.
3. **Choosing a sign size** — short table: small-sign (5× 32×16), bigsign (8× P3 32×64), and rough cost / complexity / use-case bullet for each. Note that the renderer + test stub means you can develop without buying any hardware first.
4. **Power budgets** — call out the rule of thumb: 5V × (rows × cols × number_of_panels × 0.06A) at full white; in practice a 60A supply for the bigsign and 10A for the small sign. Cross-reference Adafruit's panel datasheets.
5. **Software-first development** — show the no-hardware path: `make dev`, `make test` (PYTHONPATH=tests/stubs auto-set), the renderer for visual feedback. One short TomlExample of a config running through the renderer locally.
6. **Deploying to the Pi** — high-level (3 bullets): build the Docker image (`make build-docker`), copy + run via systemd (`deploy/led-ticker.service`), mount config read-only. Don't recreate the deploy README — link to it.
7. **Pitfalls** — (a) the rgbmatrix library is hardcoded to a fork; the Dockerfile pins it; if you patch the Pi locally outside the image you'll diverge. (b) USB-C power supplies marketed as "5V 3A" don't always deliver under matrix load — use a dedicated 5V supply, not a phone charger. (c) heat: panels run hot at full brightness; a fan or shroud is recommended for sustained use.
8. **RelatedPages** — `hardware/small-sign`, `hardware/bigsign`, `tools/render-demo`, `getting-started`.

- [ ] **Step 4: Lint and build, commit**

Message: `docs: hardware/building-your-own page`.

---

## Task 7: Reference — config-options page

**Files:**
- Create: `docs/site/src/content/docs/reference/config-options.mdx`

Source-of-truth references:
- `src/led_ticker/config.py` — top-level config dataclasses (`AppConfig`, `DisplayConfig`, `SectionConfig`, `TitleConfig`, `TransitionsConfig`)
- `config/config.example.toml` and `config/config.bigsign.example.toml` — annotated examples
- `docs/content-source/widgets/*.md` — per-widget options (already documented; this page cross-cuts NOT duplicates)

- [ ] **Step 1: Read the source**

```bash
grep -E '^class |^\s+\w+:\s*[A-Z]' src/led_ticker/config.py | head -60
```

- [ ] **Step 2: Read the style reference**

```bash
cat docs/site/src/content/docs/concepts/sections-and-modes.mdx
```

- [ ] **Step 3: Write the page**

Required sections:

1. **Frontmatter** — `title: "Reference: Config options"`, one-sentence description.
2. **Intro** — this page is the cross-cutting view of every TOML knob, organized by section. Per-widget options live on each widget's page (link); this page covers `[display]`, `[title]`, `[transitions]`, and `[[playlist.section]]`.
3. **`[display]`** — markdown table: Field, Type, Default, Description. Cover: rows, cols, chain, parallel, default_scale, brightness, led_gpio_mapping, led_slowdown_gpio, pwm_bits, pwm_lsb_nanoseconds, rp1_rio, pixel_mapper, show_refresh. Cite Pi-5-only knobs explicitly.
4. **`[title]`** — table: delay (default 5).
5. **`[transitions]`** — table: default, duration, easing, between_sections.
6. **`[[playlist.section]]`** — table: mode, hold_time, loop_count, transition, transition_duration, transition_color, scale, content_height, bg_color, transition_specified. Briefly note the section-vs-global precedence.
7. **`[playlist.section.title]`** — same shape as a regular `message` widget's options; one-line note + link to `widgets/message`.
8. **`[[playlist.section.widget]]`** — single line: "Per-widget options live on each widget's page. See [Widgets](/widgets)."
9. **Pitfalls** — (a) section's `transition` field is BOTH the entry transition (when the section appears) and the inter-widget transition; document this. (b) `content_height * scale ≤ panel_h_real` ceiling (cross-link bigsign page).
10. **RelatedPages** — `reference/cli`, `concepts/sections-and-modes`, `widgets`.

NOTE: don't try to be exhaustive on every Pi-tuning knob — surface the common ones, point at `CLAUDE.md` for full Pi 5 tuning notes.

- [ ] **Step 4: Lint and build, commit**

Message: `docs: reference/config-options page`.

---

## Task 8: Reference — cli page

**Files:**
- Create: `docs/site/src/content/docs/reference/cli.mdx`

Source-of-truth references:
- `src/led_ticker/app.py` — the `led-ticker` CLI entry point
- `pyproject.toml` — script declarations
- `Makefile` — Make-target wrappers

- [ ] **Step 1: Read the source**

```bash
grep -E 'argparse|add_argument|def \w+' src/led_ticker/app.py | head -30
grep '\[project.scripts\]' -A 5 pyproject.toml
grep -E '^\w+:' Makefile | head -20
```

- [ ] **Step 2: Read the style reference**

```bash
cat docs/site/src/content/docs/concepts/sections-and-modes.mdx
```

- [ ] **Step 3: Write the page**

Required sections:

1. **Frontmatter** — `title: "Reference: CLI"`, one-sentence description.
2. **`led-ticker` (default)** — start the ticker. Document `--config`, `--led-rp1-rio` (Pi 5 only), and any other top-level flags. One example invocation.
3. **`led-ticker validate`** — link to `tools/validate` for full coverage; one-line summary here.
4. **Make targets** — table: `make dev`, `make test`, `make lint`, `make typecheck`, `make format`, `make build-docker`, `make docs-dev`, `make docs-build`, `make docs-lint`, `make docs-format`, `make render-demo`, `make render-long-demos`, `make render-long-demo NAME=...`. One-line description each.
5. **Docker** — one-line on `docker compose up` and pointer to the deploy README for systemd setup.
6. **Pitfalls** — (a) the CLI uses `--led-*` prefixes for rgbmatrix-passthrough flags; these mirror the C library's flag names. (b) `make test` automatically sets `PYTHONPATH=tests/stubs` so you don't need a real `rgbmatrix` install for unit tests.
7. **RelatedPages** — `reference/config-options`, `tools/validate`, `tools/render-demo`.

- [ ] **Step 4: Lint and build, commit**

Message: `docs: reference/cli page`.

---

## Task 9: Showcase — gallery shell + moonbunny placeholder + issue template

**Files:**
- Create: `docs/site/src/content/docs/showcase.mdx`
- Create: `docs/site/public/showcase/moonbunny/placeholder.svg`
- Create: `.github/ISSUE_TEMPLATE/submit-sign.yml`

Source-of-truth references:
- `docs/superpowers/specs/2026-05-08-docs-site-design.md` — Showcase section + submission template

- [ ] **Step 1: Read the source**

```bash
grep -A 30 'Showcase\|submit-sign' docs/superpowers/specs/2026-05-08-docs-site-design.md
```

- [ ] **Step 2: Write the placeholder SVG**

`docs/site/public/showcase/moonbunny/placeholder.svg` — a 256×64 SVG with a dark background, brand-pink (`#e1306c`) text "moonbunny", and a small "[showcase placeholder]" subtext. Keep it inline-simple — no external font dependencies. This file ships so the entry builds without a missing-asset error. Photos replace it in a follow-up.

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 64" width="256" height="64">
  <rect width="256" height="64" fill="#0a0a0f" />
  <text x="128" y="34" font-family="sans-serif" font-size="22" font-weight="700" fill="#e1306c" text-anchor="middle">moonbunny</text>
  <text x="128" y="52" font-family="sans-serif" font-size="9" fill="#8a8a98" text-anchor="middle">[showcase placeholder — photos coming soon]</text>
</svg>
```

- [ ] **Step 3: Write the showcase page**

Required sections:

1. **Frontmatter** — `title: "Showcase"`, one-sentence description.
2. **Intro** — short paragraph: "Real signs running led-ticker out in the world. Submit your own via the link at the bottom."
3. **Entries** — one entry per sign. For now: just moonbunny. Use a clean MDX layout (heading + image + 2-3 paragraph case-study + brief stat block: hardware, daily uptime, key widgets). Image src = `/showcase/moonbunny/placeholder.svg`. Stat block fields: Sign type (bigsign), Location (storefront window), Hardware (Pi 5 + 8× P3 32×64), Notable widgets (rss_feed, two_row, custom messages, gif). Note the placeholder explicitly: ":::note Placeholder image — real photos coming soon. The case study text is accurate.:::".
4. **Submit your sign** — a CTA section with a link to the issue template. Use `https://github.com/JamesAwesome/led-ticker/issues/new?template=submit-sign.yml` (don't render this as a button component — Starlight links work fine for the v1).
5. **RelatedPages** — `getting-started`, `hardware/small-sign`, `hardware/bigsign`.

- [ ] **Step 4: Write the issue template**

`.github/ISSUE_TEMPLATE/submit-sign.yml`:

```yaml
name: Submit your sign
description: Share a real-world led-ticker sign for the docs showcase
title: "[Showcase] <your sign name>"
labels: ["showcase"]
body:
  - type: input
    id: name
    attributes:
      label: Sign name
      description: A short name for the entry (e.g. "moonbunny", "kitchen weather sign")
    validations:
      required: true
  - type: dropdown
    id: hardware
    attributes:
      label: Hardware
      options:
        - small-sign (Pi 4, 5× 32×16)
        - bigsign (Pi 5, 8× P3 32×64)
        - other (describe below)
    validations:
      required: true
  - type: textarea
    id: description
    attributes:
      label: Where it lives + what it does
      description: 2-3 sentences. What's the use case? Who sees it?
    validations:
      required: true
  - type: textarea
    id: photos
    attributes:
      label: Photos / videos
      description: Drag-and-drop or paste links. At least one clear photo of the sign in its environment is ideal.
    validations:
      required: true
  - type: input
    id: handle
    attributes:
      label: Credit
      description: How would you like to be credited (name / handle / link)? Leave blank for "Anonymous".
    validations:
      required: false
  - type: textarea
    id: config
    attributes:
      label: Config (optional)
      description: Paste your config.toml or a sanitized excerpt. Skip if you'd rather not share.
    validations:
      required: false
```

- [ ] **Step 5: Lint and build, commit**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3
```

Expected: 0 errors, page builds, placeholder.svg copied to dist.

```bash
git add docs/site/src/content/docs/showcase.mdx docs/site/public/showcase/moonbunny/placeholder.svg .github/ISSUE_TEMPLATE/submit-sign.yml
git commit -m "docs: showcase shell + moonbunny placeholder + submit-sign issue template"
```

---

## Task 10: Sidebar wiring

**Files:**
- Modify: `docs/site/astro.config.mjs`

The sidebar currently has Concepts, Widgets, Transitions, Assets, Pitfalls. We need to add Tools, Hardware, Reference (each with `autogenerate`) and Showcase (a top-level link). Order: Home, Getting started, Concepts, Widgets, Transitions, Tools, Hardware, Reference, Assets, Showcase, Pitfalls.

- [ ] **Step 1: Read the current config**

```bash
sed -n '20,55p' docs/site/astro.config.mjs
```

- [ ] **Step 2: Edit the sidebar array**

After the `Transitions` block and before `Assets`, insert:

```js
{
  label: "Tools",
  items: [{ autogenerate: { directory: "tools" } }],
},
{
  label: "Hardware",
  items: [{ autogenerate: { directory: "hardware" } }],
},
{
  label: "Reference",
  items: [{ autogenerate: { directory: "reference" } }],
},
```

After the `Assets` block and before `Pitfalls`, insert:

```js
{
  label: "Showcase",
  link: "/showcase/",
},
```

- [ ] **Step 3: Lint and build**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3
```

Expected: 0 errors. Sidebar shows Tools / Hardware / Reference / Showcase entries.

- [ ] **Step 4: Commit**

```bash
git add docs/site/astro.config.mjs
git commit -m "docs: sidebar — Tools, Hardware, Reference, Showcase sections"
```

---

## Task 11: Final integration

- [ ] **Step 1: Full lint pass**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -5
```

Expected: 0 errors, 0 warnings.

- [ ] **Step 2: Full build**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
```

Expected: page count = previous (29 from end of B2) + 9 new pages = 38.

- [ ] **Step 3: Verify all expected files exist**

```bash
test -f docs/site/dist/tools/render-demo/index.html && echo OK render-demo
test -f docs/site/dist/tools/validate/index.html && echo OK validate
test -f docs/site/dist/tools/creating-a-config/index.html && echo OK creating-a-config
test -f docs/site/dist/hardware/small-sign/index.html && echo OK small-sign
test -f docs/site/dist/hardware/bigsign/index.html && echo OK bigsign
test -f docs/site/dist/hardware/building-your-own/index.html && echo OK building-your-own
test -f docs/site/dist/reference/config-options/index.html && echo OK config-options
test -f docs/site/dist/reference/cli/index.html && echo OK cli
test -f docs/site/dist/showcase/index.html && echo OK showcase
test -f docs/site/dist/showcase/moonbunny/placeholder.svg && echo OK svg
test -f .github/ISSUE_TEMPLATE/submit-sign.yml && echo OK issue-template
```

Expected: 11 OK lines.

- [ ] **Step 4: Run the Python test suite**

```bash
make test 2>&1 | tail -3
```

Expected: same pass count as B2 (no Python touched in this batch).

- [ ] **Step 5: Sidebar shows all the new sections**

Run `pnpm run dev` and visit `http://localhost:4321/`. Confirm sidebar order:
- Home, Getting started
- Concepts (7)
- Widgets (13)
- Transitions (4)
- Tools (3) ← new
- Hardware (3) ← new
- Reference (2) ← new
- Assets (1)
- Showcase ← new
- Pitfalls

- [ ] **Step 6: Push and open the PR**

```bash
git push -u origin worktree-feat-docs-content-b3
gh pr create --title "docs: site content B3 — Tools, Hardware, Reference, Showcase" --body "$(cat <<'EOF'
## Summary

Final batch of docs site content per the design spec at \`docs/superpowers/specs/2026-05-08-docs-site-design.md\`.

- 3 Tools pages: render-demo, validate, creating-a-config (skill walkthrough)
- 3 Hardware pages: small-sign, bigsign, building-your-own
- 2 Reference pages: config-options (cross-cutting; per-widget options stay on widget pages), cli
- Showcase shell + moonbunny placeholder entry + \`.github/ISSUE_TEMPLATE/submit-sign.yml\` for non-coder submissions
- Sidebar wired to expose the four new top-level sections

## Test plan

- [ ] \`pnpm run lint\` from \`docs/site/\` passes
- [ ] \`pnpm run build\` from \`docs/site/\` builds 38 pages (29 from B2 + 9 new)
- [ ] All 11 dist files in Task 11 step 3 exist
- [ ] Sidebar shows Tools / Hardware / Reference / Showcase entries

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review checklist (run after writing the plan)

- ✅ Spec coverage — every B3 deliverable from the design spec is a task here.
- ✅ No placeholders — every step has concrete file paths, verbatim source-of-truth pointers, and section requirements.
- ✅ Type consistency — sidebar labels match across config + verification step.
- ✅ Showcase placeholder shipped (per user input on this turn).
- ✅ Reference page hand-curated (no field-registry exists; follow-up tracked in PR description if a registry lands later).
