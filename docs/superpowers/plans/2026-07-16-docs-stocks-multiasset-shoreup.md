# Docs shore-up: stocks multi-asset (Twelve Data) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. This is a DOCS plan — per-page prose/table edits governed by `docs/DOCS-STYLE.md`, verified by build + lint + drift tests (no TDD code cycle).

**Goal:** Bring the docs site in line with `led-ticker-stocks 0.6.0`. The stocks page and catalog still say *"equities only — crypto/indices/FX aren't supported (a forex symbol is rejected)"*, the exact opposite of what shipped: `provider = "twelvedata"` drives stocks + forex + crypto from one free key.

**Architecture:** Three files. The stocks widget page (`stocks.mdx`) is the substantive rewrite — the intro, the "Data source" section, and the options tables. Two smaller fixes: the plugins index line and the bundled catalog entry (summary + version ref).

**Tech Stack:** Astro/Starlight MDX; `make docs-build` / `make docs-lint`; the catalog is `src/led_ticker/plugins_catalog.json` (drift-guarded by a test).

## Global Constraints

- **Follow `docs/DOCS-STYLE.md`** — run the §3 per-page review checklist against every page you touch (audience/voice, benefit-first, no Adafruit copying, SEO title/description, working links/anchors).
- **Accuracy over enthusiasm:** every claim must match `led-ticker-stocks 0.6.0` behavior. Verify field names/defaults against the plugin (`plugins/stocks/src/led_ticker_stocks/` in the led-ticker-plugins monorepo) — do NOT invent options.
- Finnhub stays the DEFAULT provider and is equities-only; Twelve Data is opt-in (`provider = "twelvedata"`) and multi-asset. Do not imply Finnhub does forex, or that twelvedata is the default.
- Secrets are env-only: `TWELVEDATA_API_KEY` (never in config), same as `FINNHUB_API_TOKEN`.
- **MDX gotcha:** an apostrophe/backslash inside a single-quoted JSX attribute (e.g. `caption='…won\'t…'`) breaks `make docs-build` while `astro check` passes — avoid apostrophes in JSX string attributes.
- **GIFs are OUT of scope** (deferred): demo mode synthesizes ~50–500 prices for every symbol, so it can't show real forex 4-decimals / crypto magnitude / mixed market state — a truthful multi-asset GIF needs a live key the headless renderer doesn't have. The existing layout GIFs (crawl/card/dashboard) stay valid. Note this; don't fake a GIF.
- Verify before done: `make docs-build` (clean) + `make docs-lint` (prettier + astro check) + the catalog drift test (`uv run --extra dev pytest tests/test_plugins/test_catalog.py -q`) + the docs-options drift test if you touched an options table (`tests/test_docs_config_options_drift.py`).
- Commit messages end with exactly:
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_015czjSP4i45aZxX717Zh9yS

## File Structure

- `docs/site/src/content/docs/widgets/stocks.mdx` — **modify** (substantive): intro, a new/rewritten "Data sources" section, options-table rows, the stocks.trend note, the symbols-row fix.
- `docs/site/src/content/docs/plugins/available.mdx` — **modify**: the one stocks summary line.
- `src/led_ticker/plugins_catalog.json` — **modify**: the stocks entry summary + bump the git source `ref` `stocks-v0.5.0` → `stocks-v0.6.0`.

---

## Task 1: `stocks.mdx` — intro + the equities-only limitation

**Files:**
- Modify: `docs/site/src/content/docs/widgets/stocks.mdx` (the intro paragraph + the "v1 tracks US-listed equities only…" paragraph, ~lines 10–12)

**Current (to replace):** the intro says prices are "pulled from Finnhub" and the next paragraph asserts *"v1 tracks US-listed equities only — crypto, indices, and FX aren't supported yet (a forex-looking symbol is rejected at config-load)."*

- [ ] **Step 1: Rewrite the intro** to lead benefit-first and name the multi-asset reality without burying the default. Keep the existing strong "live price on your wall, not a phone app" hook. Add, in the intro's flow: the widget shows live prices via **Finnhub** (the default, US equities) **or Twelve Data** (`provider = "twelvedata"`) for **stocks + forex + crypto from one free key**. Keep the `stocks.quote` token + `stocks.trend` color-provider mention.

- [ ] **Step 2: Replace the "equities only / FX rejected" paragraph** with the accurate scope: the default Finnhub path is US-equities-only (a `/` forex symbol is rejected under finnhub); switching `provider = "twelvedata"` adds forex (`EUR/USD`), crypto (`BTC/USD`), and indices — the slash routes the asset class. Keep the `DKS` storefront framing (still the default sample). Point to the new "Data sources" section (Task 3) for the how.

- [ ] **Step 3: Verify** — `make docs-build` clean; re-read against `DOCS-STYLE.md` §3 (benefit-first, accurate, no contradiction left in the intro).

- [ ] **Step 4: Commit**

```bash
git add docs/site/src/content/docs/widgets/stocks.mdx
git commit -m "docs(stocks): intro reflects multi-asset via Twelve Data (not equities-only)"
```

---

## Task 2: `stocks.mdx` — a "Multi-asset via Twelve Data" example section

**Files:**
- Modify: `docs/site/src/content/docs/widgets/stocks.mdx` (add a section — natural home is right after "Embed a live price anywhere" or before "Options")

**Interfaces (consumes):** the 0.6.0 behavior — `provider = "twelvedata"`, mixed `/` symbols, per-symbol market state, auto-format by magnitude, the `stocks.quote` `decimals` override, `stocks.trend` on `/` symbols, env-only `TWELVEDATA_API_KEY`, and the self-tuning rate (auto-detect + no config).

- [ ] **Step 1: Write the section** — a short, copy-pasteable `provider = "twelvedata"` example (a `stocks.ticker` with a stock + forex + crypto mix, and a `stocks.quote` forex token), plus 4 tight bullets:
  - the slash routes the asset class (`AAPL` / `EUR/USD` / `BTC/USD`), no exchange prefix;
  - **per-symbol market state** — crypto reads LIVE while an after-hours stock reads CLSD in the same rotation;
  - **auto-format by magnitude** — forex 4 decimals, crypto thousands-separated, equities 2 — no config (with the `decimals` override on `stocks.quote` for the exception);
  - **the rate just works** — throttles to your key's per-minute cap, **auto-detected** at boot; a paid key runs at full speed with no config.
  - one line: free key at twelvedata.com, in `.env` as `TWELVEDATA_API_KEY` (env-only).

- [ ] **Step 2: Verify** — build clean; example fields checked against the plugin (no invented options); links/anchors resolve.

- [ ] **Step 3: Commit**

```bash
git add docs/site/src/content/docs/widgets/stocks.mdx
git commit -m "docs(stocks): add Multi-asset via Twelve Data section"
```

---

## Task 3: `stocks.mdx` — "Data source (Finnhub)" → "Data sources"

**Files:**
- Modify: `docs/site/src/content/docs/widgets/stocks.mdx` (the `## Data source (Finnhub)` section, ~line 299, and any in-page anchor links to `#data-source-finnhub`)

- [ ] **Step 1: Rewrite the heading + section** to `## Data sources` covering BOTH:
  - **Finnhub (default)** — US equities, free tier; `FINNHUB_API_TOKEN`; a `/` symbol is rejected (equities-only). Preserve the existing accurate content (poll cadence, rate budget, market-hours behavior).
  - **Twelve Data (`provider = "twelvedata"`)** — stocks + forex + crypto from one free key; `TWELVEDATA_API_KEY`; per-symbol market state; the **self-tuning rate** (auto-detect plan via /api_usage, throttle, 429 back-off) — one paragraph, "you don't set a rate; it detects your plan"; delayed data (~1–15 min) on the free tier.
- [ ] **Step 2: Fix anchor references** — any `[Data source](#data-source-finnhub)` links elsewhere in the page now point to the renamed section; update the anchor (e.g. `#data-sources`) at every use (the intro, the symbols-table row, `update_interval` row).
- [ ] **Step 3: Verify** — build clean; grep the page for `#data-source-finnhub` (0 remaining); every in-page link resolves.
- [ ] **Step 4: Commit**

```bash
git add docs/site/src/content/docs/widgets/stocks.mdx
git commit -m "docs(stocks): Data sources section covers Finnhub + Twelve Data"
```

---

## Task 4: `stocks.mdx` — options tables

**Files:**
- Modify: `docs/site/src/content/docs/widgets/stocks.mdx` (the `### stocks.ticker widget`, `### stocks.quote source`, `### stocks.trend color provider` option tables, ~lines 262–298)

Verify each row against the plugin source before writing.

- [ ] **Step 1: `stocks.ticker` table** — add a `provider` row (`"finnhub"` default / `"twelvedata"`); fix the `symbols` row (a `/` pair is rejected only under finnhub; valid under twelvedata) and its `#data-source-finnhub` anchor.
- [ ] **Step 2: `stocks.quote` table** — add `provider` and `decimals` rows (decimals = fixed override, else auto by magnitude).
- [ ] **Step 3: `stocks.trend` note** — it now accepts `/` (forex/crypto) symbols; drop any "equities-only / rejected" wording.
- [ ] **Step 4: Verify** — build clean; if a table drift-test covers these, run it (`tests/test_docs_config_options_drift.py` audits `[display]`/config-options, likely NOT the plugin widget table — confirm scope; run it regardless).
- [ ] **Step 5: Commit**

```bash
git add docs/site/src/content/docs/widgets/stocks.mdx
git commit -m "docs(stocks): options tables — provider + decimals rows, /-symbol under twelvedata"
```

---

## Task 5: plugins index + bundled catalog

**Files:**
- Modify: `docs/site/src/content/docs/plugins/available.mdx` (the stocks entry, ~line 62)
- Modify: `src/led_ticker/plugins_catalog.json` (the `stocks` entry)
- Test: `tests/test_plugins/test_catalog.py`

- [ ] **Step 1: `available.mdx`** — rewrite the stocks summary line: multi-asset via Finnhub (equities, default) **or Twelve Data** (`provider = "twelvedata"`, stocks + forex + crypto, one free key). Keep the layouts + token + trend mention and the demo-mode note.
- [ ] **Step 2: `plugins_catalog.json`** — update the stocks `summary` ("Live equity stock ticker…" → a multi-asset one-liner) and bump the git source `ref` from `stocks-v0.5.0` to `stocks-v0.6.0`. Do NOT change `provides` unless a surface changed (widgets/color_providers unchanged; sources already lists the pypi package + the git ref).
- [ ] **Step 3: Verify** — `uv run --extra dev pytest tests/test_plugins/test_catalog.py -q` green; `make docs-build` clean.
- [ ] **Step 4: Commit**

```bash
git add docs/site/src/content/docs/plugins/available.mdx src/led_ticker/plugins_catalog.json
git commit -m "docs(stocks): plugins index + catalog reflect multi-asset (0.6.0)"
```

---

## Task 6: whole-page review + final build

**Files:** none (verification)

- [ ] **Step 1: Full `DOCS-STYLE.md` §3 rubric pass** over the rewritten `stocks.mdx` — one read for voice/benefit-first, one for accuracy (every field/default vs. the plugin), one for links/anchors, one for SEO (title/description still strong).
- [ ] **Step 2: Final build + lint** — `make docs-build` and `make docs-lint` both clean; `git grep -n "equities only\|forex.*reject\|data-source-finnhub\|Data source (Finnhub)"` across `docs/site/src` returns nothing.
- [ ] **Step 3:** confirm the deferred-GIF note is captured (a follow-up: a real multi-asset demo GIF needs a live-key render path).

## Self-Review

**Coverage:** intro (T1) ✓; multi-asset example (T2) ✓; Data sources both providers (T3) ✓; options tables provider/decimals + symbols fix (T4) ✓; index + catalog + version ref (T5) ✓; rubric + build gate (T6) ✓. Deferred: multi-asset GIFs (needs live-key render) — noted, not built.

**Consistency:** Finnhub = default/equities everywhere; Twelve Data = opt-in/multi-asset everywhere; `TWELVEDATA_API_KEY` env-only stated once and referenced; the `#data-source-finnhub` → `#data-sources` anchor rename is applied at every use.
