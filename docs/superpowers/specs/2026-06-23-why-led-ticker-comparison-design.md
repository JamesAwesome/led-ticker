# Design: "Why led-ticker?" comparison page + positioning + structured data

**Date:** 2026-06-23
**Status:** Approved for planning

## Motivation

This is visibility work item #4-6 from the LLM-discoverability effort. The goal: when a first-time hobbyist asks an LLM "how do I build a scrolling LED matrix sign," led-ticker should be the likely, trustworthy suggestion.

Research (4 parallel web reviews, mid-2026) found the **niche is under-served**: there's a canonical low-level driver (`hzeller/rpi-rgb-led-matrix` — "write your own code") and a single-vertical layer (sports scoreboards), but **no dominant, batteries-included, config-driven, multi-feed info-sign toolkit for Pi + HUB75.** The honest answer to "scrolling news/weather sign on a Pi" is currently "buy the Adafruit HAT + hzeller and write Python" or a one-off script — never a named higher-level tool. That empty slot is led-ticker's.

A comparison page that honestly maps the landscape (and sends wrong-fit visitors elsewhere) is both the answer-shaped content LLMs cite and the positioning that sharpens what led-ticker is. Structured data + tightened entry-point copy make it findable and citeable.

## Decisions (settled at brainstorm)

- **Page:** a new top-level **"Why led-ticker?"** sidebar item, high in the IA (near `getting-started`).
- **Staleness:** **evergreen** — qualitative comparisons + an "as of mid-2026" note + sourced footnotes; **no hard star counts or time-sensitive status claims in body copy.**
- **Stance:** **full send-elsewhere decision map** — actively recommend the right alternative for wrong-fit cases.
- **Scope:** four components — the page (#4), positioning copy (#5), structured data + meta (#6), and a DOCS-STYLE.md update (D).

## Components

### A. The "Why led-ticker?" page

New page at `docs/site/src/content/docs/why-led-ticker.mdx`, registered as a top-level sidebar entry in `astro.config.mjs` near `getting-started`.

**Structure (top to bottom):**
1. **Thesis paragraph** — "led-ticker is the batteries-included info-display layer for large HUB75 signs on a Pi — the missing higher-level layer above hzeller's driver, fully open and self-hosted."
2. **"Is led-ticker right for you?" decision map** — an honest tree that routes wrong-fit visitors away: addressable LEDs → WLED; cheap + tiny clock/notifier → AWTRIX/Ulanzi; finished small appliance → Tidbyt/tronbyt; generative art/effects → Pixelblaze/WLED; **large custom info sign, config-driven, self-hosted → led-ticker.**
3. **Comparison table** — evergreen cells, axes below.
4. **Per-alternative honest call-outs** — 2-3 sentences each: what it's great at · when to pick it over led-ticker · when led-ticker wins. (The verbatim-citeable bits.)
5. **"Where led-ticker fits"** — the sweet-spot paragraph → links to `getting-started` + hardware.
6. **Sourced footnotes** + "as of mid-2026" note.

**Comparison axes** (columns = the tools; rows below):

| Axis | What it captures |
|---|---|
| Hardware domain | HUB75 vs addressable (WS2812) vs fixed appliance |
| Compute | Raspberry Pi vs ESP32 vs appliance |
| Scale / canvas | large custom (256×64+) vs tiny fixed |
| Primary use | info feeds vs effects/art vs clock/notifier |
| Content model | declarative TOML + plugins vs web UI vs app-store vs push-in |
| **Architecture** | **self-contained on the Pi (led-ticker) vs separate self-hosted server (tronbyt) vs vendor cloud (Tidbyt) vs needs Home-Assistant/MQTT to feed it (AWTRIX) vs push-your-own-strings (WLED)** |
| Open / self-hosted | fully open + no cloud vs closed/cloud |
| Cost band | ~$150+ vs ~$30-60 vs ~$199 |
| Setup effort | qualitative |

The **Architecture** row is the sharpest differentiator and the one the user explicitly asked to surface: led-ticker is the only option that is a *self-contained sign* — it fetches its own feeds on-device with no separate server, no cloud, and no smart-home backend. tronbyt requires its own self-hosted server (`tronbyt/server`) to render and push frames; Tidbyt depends on its vendor cloud; AWTRIX is dark until Home Assistant/MQTT feeds it; WLED renders only strings you push in.

**Tools covered:** `hzeller/rpi-rgb-led-matrix` (framed as *the layer below, not a rival*), WLED, Tidbyt/tronbyt, AWTRIX3 / ESP32-HUB75; brief mentions of Pixelblaze (art) and the sports-scoreboard projects (single-vertical neighbors).

**Evergreen guard (consequence of the staleness decision):** no star counts in the body; Tidbyt's ownership/operational status is hedged ("future uncertain", not a hard shutdown claim — research found no official EOL); ESP32 panel-count/fps ceilings stated softly (research sourced them from a single vendor article). Specifics + sources live in footnotes.

### B. Positioning copy (#5)

Surgical edits to the two highest-traffic entry points, in the existing voice (DOCS-STYLE):
- **`docs/site/src/content/docs/index.mdx`** — ensure the hero/intro answers the first-timer's literal question ("I want a scrolling LED sign — is this for me, where do I start?") with the one-line sweet-spot and a clear link to **Why led-ticker?** + `getting-started`. Tighten, don't rewrite.
- **`README.md`** — one sharpened positioning sentence in the intro + a link to the page. Minimal.

### C. Structured data + meta (#6)

- **schema.org JSON-LD** `SoftwareApplication` injected site-wide via the `head:` array in `astro.config.mjs` (the same array that already holds the llms.txt `<link rel>`): `name`, `description`, `applicationCategory`, `operatingSystem` (Raspberry Pi OS / Linux), `offers` (free / open-source), `url`, `license`. **v1 is `SoftwareApplication` only** — no FAQ/HowTo schema (YAGNI).
- **Meta-description audit** of the **top-funnel pages only** (home, the new Why page, `getting-started`, hardware overview, widgets index): Starlight renders each page's `description:` frontmatter into `<meta name="description">` + OpenGraph; sharpen those ~5 so they match the queries a first-timer types. Most pages already have descriptions; this only touches the funnel-critical ones.

### D. DOCS-STYLE.md update

Add a short **"Comparison & positioning pages"** subsection (under §2 Principles) + one line in the §3 per-page rubric:

1. **Steelman, don't strawman** — describe each alternative in its best light; state when to pick *it*. No "unlike X, we…", no superlatives ("the best", "the only").
2. **Send people elsewhere honestly** — name the better tool for wrong-fit cases.
3. **Evergreen external claims** — no volatile facts in body (star counts, "recently acquired", versions, "most popular"); qualitative + "as of <date>" + footnotes.
4. **Cite outside claims** — any factual claim about a third-party tool gets a source link/footnote.
5. **Links to alternatives are informational, not upsell** — reinforces the existing "no buy-now links" rule; a competitor's GitHub link for honest comparison is fine, affiliate/buy links are not.

Rubric line (§3): *"If the page describes external tools: each alternative is steelmanned, claims are sourced + evergreen, and the page recommends the right tool for wrong-fit cases."*

Rules 3-4 generalize beyond this page (any future content referencing the outside world). Writing them down lets the `/review-docs` writer persona check against a standard, not vibes.

## Data flow / integration

```
astro.config.mjs:
  sidebar:  + "Why led-ticker?" top-level entry (near getting-started)
  head:     + <script type="application/ld+json"> SoftwareApplication
docs/site/src/content/docs/why-led-ticker.mdx  ← the page (Starlight Aside/table/footnotes)
docs/site/src/content/docs/index.mdx           ← tightened intro + link
README.md                                       ← one positioning sentence + link
docs/DOCS-STYLE.md                              ← comparison-pages subsection + rubric line
```

## Scope / non-goals

- **IN:** the Why page (A), the two positioning-copy edits (B), `SoftwareApplication` JSON-LD + the 5-page meta audit (C), the DOCS-STYLE subsection + rubric line (D).
- **OUT:** exhaustive feature-by-feature matrix; live/auto-updated competitor stats (evergreen by design); FAQ/HowTo schema; blog posts and community seeding (visibility items #7-#8 — separate efforts); any change to competitor projects.

## Testing

- **Build/lint:** `make docs-build`, `make docs-check-llms`, and `make docs-lint` stay green; the new page is included in `llms-full.txt` automatically.
- **JSON-LD guard:** a test that the injected structured data parses as valid JSON and is a `SoftwareApplication` (so a future `head:` edit can't silently emit broken/empty schema). Mirrors the existing `astro.config`-reading content tests.
- **Sidebar registration guard:** a content-presence test that `why-led-ticker` is registered in the sidebar config (so the page can't silently 404 / drop out of nav).
- **Human-ish review:** run `/review-docs` (at minimum the technical-writer + PM personas) against the new page before merge, checking it against the new DOCS-STYLE comparison rules.

## Risks

- **Competitor facts drift** — mitigated by the evergreen rule (no hard numbers in body; dated + sourced footnotes) codified in DOCS-STYLE so it's enforced on future edits.
- **Tone risk (reads as marketing / unfair)** — mitigated by the steelman rule + the `/review-docs` writer persona pass against the written rubric.
- **schema.org invalidity** — mitigated by the JSON-LD parse/type test.
