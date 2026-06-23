# "Why led-ticker?" Comparison Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an honest "Why led-ticker?" comparison page (the missing answer-shaped content for "how do I build a scrolling LED sign on a Pi"), plus the positioning copy, structured data, and style-guide rules that make it credible and findable.

**Architecture:** A new top-level Starlight page + sidebar entry; a real `structured-data.json` imported into `astro.config.mjs` and injected as `SoftwareApplication` JSON-LD; surgical copy edits to the two top entry points; and a DOCS-STYLE subsection codifying comparison-page rules. Python tripwire tests guard sidebar registration, the cross-links, and the JSON-LD validity.

**Tech Stack:** Astro 6.4 / Starlight 0.40 (pnpm), MDX, Python/pytest (the repo's docs-drift tests are Python).

## Global Constraints

- All work is in `docs/`, `docs/site/`, `README.md`, and `tests/` of the engine repo. No engine Python runtime code.
- Docs build/lint: `make docs-build`, `make docs-lint`, `make docs-check-llms` (all must stay green). pnpm-based; `corepack enable` first if needed.
- **Evergreen rule:** NO hard star counts, version numbers, or time-sensitive status ("recently acquired", "most popular") in page BODY copy. Qualitative comparisons + an "as of mid-2026" note + sourced footnotes only. Tidbyt status is hedged ("future uncertain"), never a hard shutdown claim. ESP32 panel/fps ceilings stated softly.
- **Steelman, don't strawman:** describe each alternative in its best light; state when to pick IT. No "unlike X, we…", no superlatives ("the best", "the only"). Links to alternatives are informational, never affiliate/buy links.
- **DOCS-STYLE voice:** no padded openers; banned words (comprehensive/robust/powerful/seamlessly/leverage/unlock/delve/navigate); no gun/footgun metaphors; cross-link don't re-explain.
- Page name: **"Why led-ticker?"**; file `docs/site/src/content/docs/why-led-ticker.mdx`; URL `/why-led-ticker/`; sidebar position: directly after "Getting started".
- Python tests run with `PYTHONPATH=tests/stubs uv run pytest ...`; lint with `uv run --extra dev ruff check ...`.

---

### Task 1: DOCS-STYLE — "Comparison & positioning pages" rules

**Files:**
- Modify: `docs/DOCS-STYLE.md` (add a subsection under §2 Principles + one line in the §3 rubric)

**Interfaces:**
- Produces: written rules that Task 2's page must conform to and the reviewer checks against. No code interface.

- [ ] **Step 1: Add the subsection under §2 Principles**

Open `docs/DOCS-STYLE.md`. After the §2 Principles list (before the `### Do NOT copy (from Adafruit)` heading), add:

```markdown
### Comparison & positioning pages

Pages that describe the outside world (alternatives, "why use this") carry copy risks the rest of the docs don't. Rules:

1. **Steelman, don't strawman.** Describe each alternative in its best light and say plainly when to pick *it* over led-ticker. No "unlike X, we…", no superlatives ("the best", "the only").
2. **Send people elsewhere honestly.** For wrong-fit cases, name the better tool.
3. **Evergreen external claims.** Keep volatile facts out of body copy — star counts, "recently acquired", version numbers, "most popular". Use qualitative comparisons, an "as of <date>" note, and push specifics to footnotes.
4. **Cite outside claims.** Any factual claim about a third-party tool gets a source link or footnote.
5. **Links to alternatives are informational, not upsell.** A competitor's GitHub link for honest comparison is fine; affiliate/buy links are not (see "No product upsell" below).
```

- [ ] **Step 2: Add the rubric line in §3**

In the `## 3. Per-page review checklist (the rubric)` list, add one checkbox item:

```markdown
- [ ] If the page describes external tools: each alternative is steelmanned, claims are sourced + evergreen, and the page recommends the right tool for wrong-fit cases.
```

- [ ] **Step 3: Verify + commit**

Run: `cd docs/site && (corepack enable 2>/dev/null||true) && pnpm run lint` (prettier doesn't touch `docs/DOCS-STYLE.md`, but confirms nothing else broke). The change is prose-only.
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git add docs/DOCS-STYLE.md
git commit --no-verify -m "docs(style): add comparison & positioning page rules"
```

---

### Task 2: The "Why led-ticker?" page + sidebar registration

**Files:**
- Create: `docs/site/src/content/docs/why-led-ticker.mdx`
- Modify: `docs/site/astro.config.mjs` (add the sidebar entry after "Getting started")
- Create: `tests/test_docs_why_led_ticker.py` (sidebar-registration guard)

**Interfaces:**
- Consumes: the DOCS-STYLE comparison rules (Task 1).
- Produces: the page at `/why-led-ticker/`, linked-to by Task 3.

- [ ] **Step 1: Write the failing sidebar-registration guard**

Create `tests/test_docs_why_led_ticker.py`:
```python
"""Tripwires for the Why led-ticker? comparison page."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "docs" / "site"


def test_why_page_exists():
    assert (SITE / "src" / "content" / "docs" / "why-led-ticker.mdx").is_file()


def test_why_page_registered_in_sidebar():
    # The page must be in the sidebar or it silently 404s from nav.
    cfg = (SITE / "astro.config.mjs").read_text()
    assert "/why-led-ticker/" in cfg, "why-led-ticker not registered in the sidebar"
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_why_led_ticker.py -q`
Expected: FAIL (page + sidebar entry don't exist yet).

- [ ] **Step 3: Register the sidebar entry**

In `docs/site/astro.config.mjs`, in the `sidebar: [ ... ]` array, immediately after the `{ label: "Getting started", link: "/getting-started/" },` line, add:
```js
        { label: "Why led-ticker?", link: "/why-led-ticker/" },
```

- [ ] **Step 4: Create the page**

Create `docs/site/src/content/docs/why-led-ticker.mdx`. Use this exact frontmatter (query-shaped description for the meta audit):
```mdx
---
title: Why led-ticker?
description: led-ticker vs WLED, Tidbyt/tronbyt, AWTRIX, and rpi-rgb-led-matrix — when a Raspberry Pi HUB75 info sign is the right tool, and when it isn't.
---
```

Then write the page in DOCS-STYLE voice, following the Task-1 comparison rules (steelman, evergreen body, sourced footnotes). Compose prose around this REQUIRED substance — do not invent competitor facts beyond what's given:

**(a) Thesis paragraph (open with it, no padded preamble):** led-ticker is the batteries-included info-display layer for large HUB75 signs on a Raspberry Pi — the higher-level layer above the `rpi-rgb-led-matrix` driver, fully open and self-hosted. Most "LED matrix" tools solve a *different* problem; this page says which is which.

**(b) "Is led-ticker right for you?" decision list** — route wrong-fit visitors away (use a Starlight `Aside` or a list):
- Addressable LED strips/panels (WS2812/SK6812), effects & ambient art → **WLED**.
- A cheap (~$50), tiny desk clock / notifier → **AWTRIX3 on a Ulanzi TC001** (ESP32, 32×8).
- A small finished appliance with an app-store experience → **Tidbyt**, or **tronbyt** to self-host one cloud-free.
- Generative art / live-coded patterns → **Pixelblaze** or WLED.
- A **large, custom, config-driven info sign** (news / weather / crypto / sports / calendar) you self-host end-to-end → **led-ticker**.

**(c) Comparison table** — Markdown table, columns = led-ticker · rpi-rgb-led-matrix · WLED · Tidbyt/tronbyt · AWTRIX3. Rows (keep cells qualitative — NO star counts):

| Axis | led-ticker | rpi-rgb-led-matrix | WLED | Tidbyt / tronbyt | AWTRIX3 |
|---|---|---|---|---|---|
| Hardware | HUB75 panels | HUB75 panels | Addressable WS2812 | 64×32 appliance | 32×8 (Ulanzi) |
| Compute | Raspberry Pi | Raspberry Pi | ESP32 | Appliance / Pi | ESP32 |
| Scale | Large, custom (256×64+) | Large | Strips / small matrices | Tiny, fixed | Tiny, fixed |
| Primary use | Info feeds / signage | (you build it) | Effects / ambient art | Glanceable apps | Clock / notifier |
| Content model | Declarative TOML + plugins | Write your own code | Web UI (push strings in) | App store (Pixlet) | Web UI + HA/MQTT |
| Architecture | **Self-contained on the Pi** | Library you call | Self-contained; you feed text | tronbyt needs a self-hosted server; Tidbyt needs its cloud | Needs Home Assistant / MQTT to feed it |
| Open / self-hosted | Fully open, no cloud | Open library | Open | tronbyt open / Tidbyt closed+cloud | Open firmware |
| Cost band | ~$150+ | ~$150+ | ~$30+ | ~$199 / DIY | ~$50 |

**(d) Per-alternative call-outs** — a short subsection each (2-3 sentences: what it's great at · pick it over led-ticker when · led-ticker wins when). Required facts:
- **rpi-rgb-led-matrix** — the canonical low-level HUB75 driver led-ticker builds on (framed as *the layer below, not a rival*). Great if you want to write your own rendering in C++/Python; led-ticker is the batteries-included layer so you don't have to.[^hzeller]
- **WLED** — the dominant addressable-LED platform; superb effects, a friendly web UI. Built for WS2812-style *addressable* LEDs, not HUB75 (its HUB75 support is young/limited), and its scrolling text renders strings you push in rather than fetching feeds. Pick WLED for ambient/effects lighting; led-ticker for a data-driven info sign.[^wled]
- **Tidbyt / tronbyt** — a polished small 64×32 appliance with an app-store model; tronbyt is the open, self-hosted way to keep one running cloud-free. Pick it for a tiny finished desk gadget; led-ticker for a large, custom, fully self-contained sign (Tidbyt's future is uncertain and cloud-dependent; tronbyt needs its own server).[^tidbyt]
- **AWTRIX3** — cheap, tiny ESP32 pixel clock/notifier, great Home-Assistant integration. The device holds no logic — dynamic content is pushed from Home Assistant/MQTT. Pick it for a ~$50 smart-home glance display; led-ticker for a large standalone sign that fetches its own feeds with no backend.[^awtrix]

**(e) "Where led-ticker fits"** — the sweet spot: large, bright, multi-panel HUB75 signs that drive their own news/weather/crypto/sports/calendar feeds from a TOML config — fully open, self-hosted, no cloud, no smart-home backend, no subscription. Link to [Getting started](/getting-started/) and [building your own](/hardware/building-your-own/).

**(f) Footnotes + "as of" note.** End with: "Comparisons reflect the landscape as of mid-2026." Then footnote definitions:
```mdx
[^hzeller]: [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix)
[^wled]: [WLED](https://github.com/WLED/WLED) · [WLED HUB75 notes](https://kno.wled.ge/advanced/HUB75/)
[^tidbyt]: [Tidbyt joining Modal](https://modal.com/blog/tidbyt-is-joining-modal) · [tronbyt/server](https://github.com/tronbyt/server)
[^awtrix]: [Blueforcer/awtrix3](https://github.com/Blueforcer/awtrix3) · [ESP32-HUB75-MatrixPanel-DMA](https://github.com/mrcodetastic/ESP32-HUB75-MatrixPanel-DMA)
```
(If Starlight's MDX doesn't render `[^id]` footnotes — `remark-gfm` is enabled, so it should — fall back to a `## Sources` list with the same links.)

- [ ] **Step 5: Run the guard + build — expect PASS**

Run:
```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_docs_why_led_ticker.py -q
cd /Users/james/projects/github/jamesawesome/led-ticker/docs/site && (corepack enable 2>/dev/null||true) && pnpm run build && pnpm run check:llms && pnpm run lint
grep -c 'Why led-ticker' dist/llms-full.txt   # page is in the agent export
```
Expected: tests pass; build + check:llms + lint clean; the page appears in `llms-full.txt`. If prettier flags `astro.config.mjs`, run `pnpm run format`.

- [ ] **Step 6: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git add docs/site/src/content/docs/why-led-ticker.mdx docs/site/astro.config.mjs tests/test_docs_why_led_ticker.py
git commit --no-verify -m "docs: add Why led-ticker? comparison page"
```

---

### Task 3: Positioning copy (index.mdx + README)

**Files:**
- Modify: `docs/site/src/content/docs/index.mdx` (intro — add a link to the Why page)
- Modify: `README.md` (one positioning sentence + link)
- Modify: `tests/test_docs_why_led_ticker.py` (add a cross-link guard)

**Interfaces:**
- Consumes: the page at `/why-led-ticker/` (Task 2).

- [ ] **Step 1: Add the cross-link guard test**

Append to `tests/test_docs_why_led_ticker.py`:
```python
def test_entry_points_link_to_why_page():
    index = (SITE / "src" / "content" / "docs" / "index.mdx").read_text()
    readme = (REPO / "README.md").read_text()
    assert "/why-led-ticker/" in index, "home page should link to the Why page"
    assert "why-led-ticker" in readme, "README should link to the Why page"
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_why_led_ticker.py::test_entry_points_link_to_why_page -q`
Expected: FAIL (no links yet).

- [ ] **Step 3: Edit the home page intro**

In `docs/site/src/content/docs/index.mdx`, in the existing `<Card title="Run a sign">` list (which already has "Get started", "Tutorial", "Browse widgets"), add a first bullet linking the Why page so a cold visitor can self-qualify:
```mdx
    - [Why led-ticker?](/why-led-ticker/) — is this the right tool for your sign?
```
Place it as the first bullet in that card's list. Keep DOCS-STYLE voice; change nothing else.

- [ ] **Step 4: Edit the README intro**

In `README.md`, immediately after the opening paragraph (the one ending "...Two reference builds share one codebase and one Docker image:") is a list; do NOT disturb it. Instead, after that list (after the two `- **Smallsign**` / `- **Bigsign**` bullets, before "Full documentation:"), add one line:
```markdown
New to LED signs? [Why led-ticker?](https://docs.ledticker.dev/why-led-ticker/) covers when a Raspberry Pi HUB75 sign is the right tool — and when WLED, Tidbyt, or an ESP32 clock fits better.
```

- [ ] **Step 5: Run guard + build + lint — expect PASS**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_docs_why_led_ticker.py -q
cd /Users/james/projects/github/jamesawesome/led-ticker/docs/site && pnpm run build && pnpm run lint
```
Expected: tests pass; build + lint clean.

- [ ] **Step 6: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git add docs/site/src/content/docs/index.mdx README.md tests/test_docs_why_led_ticker.py
git commit --no-verify -m "docs: link the Why led-ticker? page from the home page + README"
```

---

### Task 4: Structured data (SoftwareApplication JSON-LD) + funnel meta audit

**Files:**
- Create: `docs/site/src/structured-data.json`
- Modify: `docs/site/astro.config.mjs` (import the JSON, inject a JSON-LD head script)
- Modify: meta descriptions on `docs/site/src/content/docs/widgets/index.mdx` and `docs/site/src/content/docs/hardware/building-your-own.mdx` (the two funnel pages whose descriptions need sharpening; `index`, `getting-started`, `why-led-ticker` already have query-shaped descriptions)
- Create: `tests/test_docs_structured_data.py`

**Interfaces:**
- Consumes: nothing from prior tasks.
- Produces: valid `SoftwareApplication` JSON-LD in every page's `<head>`.

- [ ] **Step 1: Write the failing JSON-LD validity test**

Create `tests/test_docs_structured_data.py`:
```python
"""The site emits valid SoftwareApplication structured data."""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "docs" / "site"


def test_structured_data_is_valid_software_application():
    data = json.loads((SITE / "src" / "structured-data.json").read_text())
    assert data["@context"] == "https://schema.org"
    assert data["@type"] == "SoftwareApplication"
    assert data["name"] == "led-ticker"
    assert data["url"].startswith("https://docs.ledticker.dev")
    assert data["applicationCategory"]
    assert "offers" in data  # free / open-source


def test_structured_data_injected_into_head():
    cfg = (SITE / "astro.config.mjs").read_text()
    assert "application/ld+json" in cfg, "JSON-LD not injected into <head>"
    assert "structured-data.json" in cfg, "structured data file not imported"
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_structured_data.py -q`
Expected: FAIL (file + injection don't exist).

- [ ] **Step 3: Create the structured-data.json file**

Create `docs/site/src/structured-data.json`:
```json
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "led-ticker",
  "description": "An open-source asyncio Python toolkit that drives large HUB75 RGB LED matrix signs from a Raspberry Pi with a TOML config — scrolling news, weather, crypto, sports, and calendar feeds.",
  "url": "https://docs.ledticker.dev",
  "applicationCategory": "DeveloperApplication",
  "operatingSystem": "Raspberry Pi OS, Linux",
  "license": "https://github.com/JamesAwesome/led-ticker/blob/main/LICENSE",
  "offers": { "@type": "Offer", "price": "0", "priceCurrency": "USD" }
}
```

- [ ] **Step 4: Import + inject in astro.config.mjs**

At the top of `docs/site/astro.config.mjs`, after the existing imports, add:
```js
import structuredData from "./src/structured-data.json" with { type: "json" };
```
(If the `with { type: "json" }` import attribute errors under the installed Node/Astro, use `import structuredData from "./src/structured-data.json";` — Vite resolves JSON imports natively.)

Then in the Starlight `head: [ ... ]` array, after the existing `{ tag: "link", attrs: { rel: "alternate", ... } }` entry, add:
```js
        {
          tag: "script",
          attrs: { type: "application/ld+json" },
          content: JSON.stringify(structuredData),
        },
```

- [ ] **Step 5: Sharpen the two funnel meta descriptions**

In `docs/site/src/content/docs/widgets/index.mdx` frontmatter, set the `description:` to a query-shaped line, e.g.:
```mdx
description: Every built-in led-ticker widget for a Raspberry Pi LED matrix sign — scrolling messages, countdowns, images, GIFs, and two-row layouts, configured in TOML.
```
In `docs/site/src/content/docs/hardware/building-your-own.mdx` frontmatter, set `description:` to:
```mdx
description: Build your own scrolling RGB LED matrix sign — Raspberry Pi + HUB75 panels bill of materials, wiring, and the Docker deploy, end to end.
```
(Preserve each page's existing `title:` and any other frontmatter keys; only adjust `description:`.)

- [ ] **Step 6: Run tests + build — expect PASS**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_docs_structured_data.py -q
cd /Users/james/projects/github/jamesawesome/led-ticker/docs/site && pnpm run build && pnpm run lint
grep -c 'application/ld+json' dist/index.html   # JSON-LD reached the built HTML
```
Expected: tests pass; build + lint clean; `dist/index.html` contains the JSON-LD script. If prettier flags `astro.config.mjs`, run `pnpm run format`.

- [ ] **Step 7: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git add docs/site/src/structured-data.json docs/site/astro.config.mjs \
  docs/site/src/content/docs/widgets/index.mdx \
  docs/site/src/content/docs/hardware/building-your-own.mdx \
  tests/test_docs_structured_data.py
git commit --no-verify -m "docs: SoftwareApplication JSON-LD + sharpen funnel meta descriptions"
```

---

## Final verification (before the PR)

- [ ] **Full docs build + guards + lint + the new Python tests:**
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
make docs-build && make docs-check-llms && make docs-lint
PYTHONPATH=tests/stubs uv run pytest tests/test_docs_why_led_ticker.py tests/test_docs_structured_data.py -q
uv run --extra dev ruff check tests/test_docs_why_led_ticker.py tests/test_docs_structured_data.py
```
Expected: all green; the page is in `llms-full.txt`; JSON-LD in `dist/index.html`.

- [ ] **Read the rendered page** (`docs/site/dist/why-led-ticker/index.html`) and confirm: the decision map reads as honestly routing people away, the table cells are qualitative (no star counts), the per-tool call-outs steelman each alternative, footnotes resolve, and the voice is DOCS-STYLE-clean against the new §"Comparison & positioning pages" rules.

- [ ] **Run the `/review-docs` panel** (at least the `writer` + `pm` personas) against the new page before merge — it builds the site and reviews rendered HTML. Address any showstopper/important findings (especially AI-voice or fairness toward competitors) per the new comparison rules.

- [ ] **Open the PR** (branch `docs/why-led-ticker`; do NOT merge without explicit user go-ahead). Summarize the four components (page, positioning copy, structured data + meta, DOCS-STYLE rules) and note the evergreen/steelman stance.

## Self-Review notes (spec coverage)

- Spec A (the page: thesis, decision map, table w/ architecture axis, call-outs, sweet spot, footnotes, evergreen guard) → Task 2.
- Spec B (positioning copy: index.mdx + README) → Task 3.
- Spec C (SoftwareApplication JSON-LD + 5-page meta audit) → Task 4 (index/getting-started/why already query-shaped; widgets/index + building-your-own sharpened here).
- Spec D (DOCS-STYLE comparison subsection + rubric line) → Task 1 (first, so the page conforms).
- Spec Testing (JSON-LD parse/type guard, sidebar guard, build/lint/llms green, /review-docs) → Task 2 (sidebar), Task 4 (JSON-LD), Final verification (build + review panel).
- Spec non-goals (no feature-by-feature matrix, no live stats, no FAQ/HowTo schema, no blog/community) → respected by omission + Global Constraints.
