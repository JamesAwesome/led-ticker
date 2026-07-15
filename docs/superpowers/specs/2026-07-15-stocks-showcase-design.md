# Stock-ticker docs showcase — design spec

**Date:** 2026-07-15
**Status:** approved (brainstorm) — pending user review before planning
**Repo:** `led-ticker` core (the docs site lives at `docs/site/`), worktree `led-ticker--stocks-docs`, branch `docs/stocks-showcase`
**Follows:** `docs/DOCS-STYLE.md` (the site style guide + per-page review rubric).

---

## 1. Summary

There is **no stocks docs page today**. Create a GIF-heavy `widgets/stocks.mdx` that is BOTH
the reference and the showcase — modeled on `widgets/flight.mdx` (a plugin with three
geometry-selected layouts, a demo mode, an animation layer, a Finnhub-style source, and
troubleshooting), but showcase-forward. Add a short **home-page spotlight** (`index.mdx`) that
links into it. The two emphases the showcase must land: **dynamism across modes/sign shapes**
and **embedding a live price into ordinary content** (inline value tokens + mixed colors).

Frame signs by **form factor** (physical shape / dimensions), NOT internal codenames
(smallsign/bigsign/longboi) — so "one ticker, adapts to any sign" reads for a newcomer.

## 2. `widgets/stocks.mdx` structure

Section order (each `##` unless noted); ⭐ = the two lead emphases.

1. **Frontmatter + hero** — lead with the most impressive visual: the **dashboard** layout on a
   long panel (hero SYMBOL + price + sparkline + watch column + LIVE pulse). One `<DemoGif>`
   with a caption that sells "a live, self-updating stock dashboard on your sign." A one-line
   intro + install snippet (like flight.mdx's top).
2. **Try it in demo mode** — a token-free section a reader can paste and run with NO Finnhub
   key (demo feed synthesizes moving prices). Install line: `led-ticker-stocks==0.5.0` +
   `led-ticker-core >= 4.14.0`. Mirrors flight's "Try it without coordinates or a network call."
3. **One ticker, every sign** — the adaptive-layout section, framed BY FORM FACTOR. Three
   `<DemoGif>`s:
   - a **small ~160×16 bar** → the scrolling **crawl** (`ticker` mode);
   - a **wide ~256×64 panel** → the held **card** (`slideshow` mode);
   - a **long ~512×64 panel** → the **dashboard** (`slideshow` mode).
   Copy: one config, the layout auto-selects from the sign's real width — no `layout` field
   needed. (`resolve_layout`.)
4. **⭐ Embed a live price anywhere** — the embed-the-source moment. A `<DemoGif>` of a message
   `text = "DKS :stocks.dks:"` rendered white-label + trend-colored-price, plus a
   `<TomlExample>` showing the `[[source]]` (with `color = {style="stocks.trend", symbol="DKS"}`)
   and the message (`font_color`). Explain: the token renders in the source's `color` while the
   literal text keeps the widget's `font_color` — mixed colors on one line, in your own font.
   Cross-link `concepts/value-tokens` + `concepts/color-providers`. Note the **feeding
   requirement** (the symbol must be fed by a `stocks.quote` source or `stocks.ticker` widget)
   and that this needs core `>= 4.14.0`.
5. **⭐ Live stocks in a real playlist** — the dynamism moment. A `<DemoGif>` of a mixed loop
   built from CORE widgets + stocks (self-contained, no extra plugins): a welcome `message` →
   the stock ticker → an embedded price in a `two_row` header (e.g. top "MARKETS", bottom
   "DKS :stocks.dks:"). Copy: your everyday content and live markets in ONE rotation; shows the
   section modes side by side (scrolling `ticker` vs held `slideshow`).
6. **It's alive** — the animation close-up. A `<DemoGif>` of the card/dashboard animation layer:
   the price-flash on a change, the LIVE-chip pulse, the sparkline endpoint pulse. "Genuinely
   live — it flashes on every tick, not a static image."
7. **Options** — a table: `symbols`, `layout` (override; else auto), `green_up`,
   `update_interval`, `padding`, plus the `stocks.quote` source fields (`symbol`, `format`,
   `placeholder`) and the `stocks.trend` provider (`symbol`, `up`/`down`/`flat`, `green_up`).
8. **Data source (Finnhub)** — env-only token (`FINNHUB_API_TOKEN`), equities-only (FX is
   paid-tier), demo mode when no token, the shared `QuoteCache` (one fetch per symbol across
   widget + tokens), closed-market behavior (holds last close).
9. **If it doesn't work** — troubleshooting: no color on the token (missing feeder / core <
   4.14.0), all-white line (old core ignores `color`), a bad symbol shows em-dash, FX rejected.
10. **Related pages** (`<RelatedPages>`) — value-tokens, color-providers, two_row, the plugins
    catalog.

## 3. Home-page spotlight (`index.mdx`)

A compact spotlight (a card / short section, matching the home page's existing component
vocabulary — audit `index.mdx` first): ONE hero GIF (either the mixed-color embedded-price line
or the dashboard — pick whichever reads best at card size), a punchy line — *"Live stock
tickers — any symbol, any sign, embedded anywhere"* — and a link to `widgets/stocks.mdx`.
Keep it small; it's a pull-in, not a second showcase.

## 4. Demo GIFs (production)

Six pinned demos, committed source TOML under `docs/site/demos-pinned/` + rendered GIF under
`docs/site/public/demos-pinned/`, via the making-a-gif pipeline:

| GIF | Shows | Geometry (render-safe) |
|---|---|---|
| `stocks-dashboard-hero` | dashboard (hero) | long, scale 4, NO pixel_mapper |
| `stocks-crawl` | crawl | small, scale 1 |
| `stocks-card` | card | wide, scale 4, NO mapper |
| `stocks-embed-price` | mixed-color token in a message | wide, scale 4 |
| `stocks-playlist` | mixed core+stocks loop | wide, scale 4 |
| `stocks-animation` | flash + pulses close-up | wide/long, scale 4 |

Rules:
- **Demo mode** (no `FINNHUB_API_TOKEN`) so prices move deterministically and no key is needed
  to re-render. An `<Aside>` on the page states the GIFs are demo-mode renders; live mode pulls
  real quotes with a free Finnhub token.
- **Render-safe geometry**: NO `pixel_mapper_config` (it trips the headless content-height
  ceiling) — use `rows=64, cols=64, chain_length=4` (≈256 wide) / `rows=64, cols=128, chain=4`
  (≈512 wide) at `default_scale = 4`, and `rows=16, cols=32, chain=5` at scale 1. Real signs
  keep their Remap block; the DEMO configs don't need it. Note this in each demo header.
- Rendering requires `led-ticker-stocks` installed in the render venv (`pip install
  led-ticker-stocks==0.5.0`) — the render tool boots the real `run()` and loads the plugin via
  its entry point.
- Use **DKS** as the demo symbol (matches the session's smoke configs).
- Each GIF gets a `# render-duration:` header; captions match the site's matter-of-fact voice.

## 5. Navigation / catalog

- Add `widgets/stocks.mdx` to the widgets sidebar group (astro config / sidebar) so it appears
  in nav next to flight/weather/crypto.
- Add a `provides`/catalog entry so the Plugin Store + `plugins/available.mdx` list the stocks
  widget/source/provider (audit how flight/crypto are listed; keep drift-guards green —
  `tests/test_docs_*` if any apply).

## 6. Non-goals

- No new plugin CODE — this is docs + demo configs only (the features already shipped:
  stocks 0.5.0, core 4.14.0).
- Not a rewrite of `showcase.mdx` (the real-sign gallery) — a stocks entry there is optional
  future, not part of this.
- No live-data embeds (the site renders static GIFs; live is described, not embedded).

## 7. Phasing (for the plan)

1. **Pinned demo configs + renders** — author the six render-safe demo TOMLs, render the GIFs,
   eyeball each (colors, no clipping, motion). This is the long pole.
2. **`widgets/stocks.mdx`** — write the page (all sections), wire the `<DemoGif>`s, `<TomlExample>`s,
   cross-links, `<RelatedPages>`; add to the sidebar + catalog.
3. **Home spotlight** — the `index.mdx` card + link.
4. **Docs QA** — `make docs-lint` / `make docs-build` clean; per-page review against
   `docs/DOCS-STYLE.md`; drift-guard tests green.
