# Stock-ticker docs showcase — Implementation Plan

> Executed INLINE (render-heavy + visual). REQUIRED SUB-SKILL context: superpowers:writing-plans (this doc), making-a-gif (dev/docs mode for every render), and `docs/DOCS-STYLE.md` for the page.

**Goal:** A GIF-heavy `widgets/stocks.mdx` (reference + showcase) + a home-page spotlight that show off the stock ticker's dynamism across sign shapes and the ability to embed a live price into ordinary content.

**Design:** see `docs/superpowers/specs/2026-07-15-stocks-showcase-design.md`.

## Global constraints
- Worktree `led-ticker--stocks-docs`, branch `docs/stocks-showcase` (verify `git branch --show-current`).
- Demos render in **demo mode** (no `FINNHUB_API_TOKEN`), **render-safe geometry** (NO `pixel_mapper_config`), symbol **DKS**. `led-ticker-stocks==0.5.0` installed in the venv.
- Follow `docs/DOCS-STYLE.md`. Frame signs by **form factor** (dimensions), not codenames.
- `make docs-lint` + `make docs-build` clean; keep docs drift-guard tests green.

---

### Task 1: Six pinned demo configs + rendered GIFs (the long pole)

Author each source TOML under `docs/site/demos-pinned/<name>.toml` (with a `# render-duration:` header), render to `docs/site/public/demos-pinned/<name>.gif`, and EYEBALL each (right colors, no clipping, real motion). Render command:
`uv run python tools/render_demo/render.py <src>.toml -o <out>.gif --duration <N>` (drop `pixel_mapper`; strip any `backend=` line — render.py injects its own).

Geometry cheat-sheet (real width = cols×chain):
- small ~160×16: `rows=16, cols=32, chain_length=5`, `default_scale` unset (1).
- wide ~256×64: `rows=64, cols=64, chain_length=4`, `default_scale=4`.
- long ~512×64: `rows=64, cols=128, chain_length=4`, `default_scale=4`.

The six (all `[[source]] id="stocks.dks" type="stocks.quote" symbol="DKS"` where a token/color is used; `stocks.ticker` widgets use `demo = true`):

1. **`stocks-dashboard-hero`** (long) — `stocks.ticker` `symbols=["DKS","MSFT","NVDA","TSLA","AMZN","GOOGL","META","AMD"]`, `demo=true`, `mode="slideshow"`, `hold_time≈5`. Auto-selects dashboard at 512 width. Duration long enough for 1-2 symbol holds.
2. **`stocks-crawl`** (small) — `stocks.ticker` `symbols=["DKS","MSFT","NVDA","TSLA"]`, `demo=true`, `mode="ticker"`. Auto-selects crawl. Duration = one full scroll pass.
3. **`stocks-card`** (wide) — `stocks.ticker` `symbols=["DKS","MSFT","NVDA","TSLA"]`, `demo=true`, `mode="slideshow"`, `hold_time≈5`. Auto-selects card.
4. **`stocks-embed-price`** (wide) — `[[source]]` with `format="{price} {pct}"` + `color={style="stocks.trend",symbol="DKS"}`; a `message` `text="DKS :stocks.dks:"`, `font="Inter-Bold"`, `font_size=44`, `font_threshold=80`, `font_color=[255,255,255]`. Verify white label + trend-colored price.
5. **`stocks-playlist`** (wide) — a mixed loop, core widgets + stocks, self-contained: section A `message` welcome ("MARKETS TODAY", a brand color); section B `stocks.ticker` card (`demo=true`); section C `two_row` header (top "DKS", bottom `":stocks.dks:"`) with `bottom_color={style="stocks.trend",symbol="DKS"}` and a white `top_color` — reuses the source from section... note: a `[[source]]` is process-global, declare once. Shows scroll (ticker) vs held (slideshow) modes in one GIF. Keep total duration modest (a couple of sections).
6. **`stocks-animation`** (wide) — `stocks.ticker` card, `demo=true`, a LONGER duration so a demo price change triggers a visible flash; the LIVE chip + sparkline pulse show throughout. (If a flash is hard to catch deterministically, a longer hold raises the odds.)

- [ ] Author + render + eyeball each of the six. Re-render on any color/clip/motion issue.
- [ ] Commit the six `.toml` + `.gif` pairs.

### Task 2: `widgets/stocks.mdx`

Write the page per the spec's section order (hero → try-demo → one-ticker-every-sign → embed-price ⭐ → playlist ⭐ → it's-alive → options → data source → troubleshooting → related). Model on `widgets/flight.mdx` (imports: `DemoGif`, `RelatedPages`, `Aside`). Wire each `<DemoGif>` to its rendered GIF; add `<TomlExample>` (or the site's inline-code component — audit flight/weather) for the embed-price + install snippets. Cross-link `concepts/value-tokens`, `concepts/color-providers`. An `<Aside>` notes the GIFs are demo-mode renders (live needs a free Finnhub token). Frame signs by form factor.

- [ ] Draft the page; verify every DemoGif path resolves to a real file.
- [ ] Add to the sidebar (astro/starlight config sidebar) in the widgets group; add a catalog/`available.mdx` entry (audit how flight/crypto are listed).

### Task 3: Home-page spotlight (`index.mdx`)

Audit `index.mdx`'s existing component vocabulary; add ONE compact spotlight (hero GIF — the embed-price line or dashboard, whichever reads at card size — + the punchy line + link to `widgets/stocks.mdx`). Small; a pull-in, not a second showcase.

- [ ] Add the spotlight; keep the home page balanced (don't bury existing content).

### Task 4: Docs QA

- [ ] `make docs-lint` (prettier + astro check) clean.
- [ ] `make docs-build` clean (page builds, links resolve).
- [ ] Run any docs drift-guard tests (`uv run --extra dev pytest tests/ -k "docs" -q`) — green.
- [ ] Per-page review against `docs/DOCS-STYLE.md` (voice, headings, alt text/captions, no jargon-first).
- [ ] Commit.

## Post
- Final read-through; open the PR. (No release — docs-only.)
