# Crypto cleanup: remove coinbase/etherscan, extract coingecko → `led-ticker-crypto`

**Date:** 2026-06-10
**Status:** Design — approved, pending spec review

## Goal

Retire the coinbase and etherscan widgets from led-ticker core, and move the coingecko
widget into a new standalone plugin repo `led-ticker-crypto`. Then review the extracted
plugin so it is current against the live CoinGecko API, correct, and well tested.

## Context

Core ships three crypto widgets under `src/led_ticker/widgets/crypto/`:

- `coinbase` (`CoinbasePriceMonitor`, public Coinbase v2 API, no key)
- `coingecko` (`CoinGeckoPriceMonitor`, public CoinGecko v3 API, no key today)
- `etherscan` (`EtherscanGasMonitor`, Etherscan gas oracle, needs `ETHERSCAN_API_KEY`)

They share `crypto/_colors.py` (trend palette: UP/DOWN/NEUTRAL via `colors.lazy_palette`)
and a price-ticker renderer `_draw_price_ticker` that **lives in `coinbase.py`** and is
imported by `coingecko.py`. So coingecko's rendering is coupled to coinbase — the widget we
intend to delete. Any extraction must carry that renderer with coingecko.

This follows the established plugin-extraction precedent (`led-ticker-pool` PR #151,
`led-ticker-baseball`): one repo per plugin, `register(api)` under the `led_ticker.plugins`
entry point, import only the `led_ticker.plugin` public surface, AST import-purity + smoke
tripwires, faithful pixel-identical port validated before core removal.

**Key finding — no core public-surface additions are required.** Everything coingecko
touches is already public:

- Fonts: `FONT_LABEL`/`FONT_DELTA` are just the general `7x13`/`6x10` BDF fonts, reachable via
  `resolve_font("7x13")` / `resolve_font("6x10")`; `FONT_VALUE`/`FONT_VALUE_SMALL` are aliases
  of `FONT_DEFAULT`/`FONT_SMALL`.
- Trend palette: `colors.lazy_palette` (the `colors` module is exported).
- `run_monitor_loop`, `spawn_tracked`, `FrameAwareBase`, `ColorProvider`/`ColorProviderBase`,
  `Canvas`/`Color`/`DrawResult`, and the text-draw helpers (`draw_text`, `get_text_width`,
  `compute_baseline`) are all on the surface.
- The only internal bits coingecko uses (`_ConstantColor`, `DEFAULT_COLOR`, `_draw_price_ticker`)
  are replaced by a tiny constant `ColorProviderBase` subclass / `make_color`, and the copied
  renderer — none of which needs a core change.

## End state

- `src/led_ticker/widgets/crypto/` removed entirely from core (all three widgets + shared code).
- New public repo `led-ticker-crypto`, namespace `crypto`, one widget `crypto.coingecko`.
- Config `type = "coingecko"` → `type = "crypto.coingecko"`.
- Core carries a helpful migration error for the old bare `coingecko` type.

## Plugin shape (`led-ticker-crypto`)

```
src/led_ticker_crypto/
  __init__.py        # register(api) → api.widget("coingecko")(CoinGeckoPriceMonitor)
  coingecko.py       # the widget: monitor (async update) + draw()
  _ticker_render.py  # shared price-ticker renderer (today's coinbase _draw_price_ticker), copied verbatim
  _colors.py         # trend palette via colors.lazy_palette (UP/DOWN/NEUTRAL)
tests/
  test_coingecko.py      # standalone suite (mocked API, draw conformance, helper units)
  test_import_purity.py  # AST tripwire: led_ticker imports == led_ticker.plugin only
  test_smoke.py          # entry-point loads; crypto.coingecko discoverable
README.md
CLAUDE.md
pyproject.toml         # entry point crypto = led_ticker_crypto:register; [tool.uv.sources] led-ticker; 3.14+
.github/workflows/ci.yml  # sibling led-ticker checkout via LED_TICKER_DEPLOY_KEY; ruff + pytest
```

Design rationale: the renderer and colors are `_`-prefixed shared modules rather than folded
into `coingecko.py`, so a future `crypto.coinbase` (or other source) can reuse them without a
new repo — which is the whole point of the general `crypto` namespace over a narrow
`led-ticker-coingecko`.

## Phases

### Phase 1 — faithful extraction (no behavior change)

1. Create `led-ticker-crypto` repo, scaffolded like pool/baseball (pyproject, CI, README, CLAUDE.md).
2. Copy `coingecko.py`, coinbase's `_draw_price_ticker` (→ `_ticker_render.py`), and `_colors.py`
   verbatim; rewire all `led_ticker.*` imports to `led_ticker.plugin`; replace `_ConstantColor`/
   `DEFAULT_COLOR` with a small constant provider / `make_color`; register as `crypto.coingecko`.
3. Validate **pixel-identical** to core via a render-compare across several frames
   (SHA-256 match), the same technique used to prove the baseball refactor identical.
4. Port the coingecko tests; add `test_import_purity.py` + `test_smoke.py`. CI green.

This phase deliberately keeps the (possibly stale) API behavior unchanged — it proves the
*move* is faithful. Live-API truth-checking is Phase 3.

### Phase 2 — core removal (one coordinated PR, lands after Phase 1 is green)

Because coingecko-in-core imports coinbase's `_draw_price_ticker`, coinbase cannot be deleted
before coingecko leaves core — so all three widgets are removed together:

- Delete `src/led_ticker/widgets/crypto/` and the import in `widgets/__init__.py`.
- Delete `tests/test_widgets/test_crypto.py`, `test_crypto_colors.py`, `test_etherscan.py`.
- Delete docs pages `docs/content-source/widgets/{coinbase,coingecko,etherscan}.md` and demo
  configs `docs/site/demos-long/widget-{coinbase,coingecko,etherscan}.toml`.
- Scrub `.claude/skills/creating-a-config/` fact-packs (`widget-selection.md`, `snippets.md`,
  `asset-handling.md`, `SKILL.md`) of all three.
- `CLAUDE.md`: drop the `crypto/` package-layout line; add `led-ticker-crypto` to the **Plugin
  ecosystem** subsection.
- Remove any crypto blocks from `config/config.example.toml` / `config.bigsign.example.toml`.
- Prune now-orphaned named font constants (`FONT_LABEL`/`FONT_DELTA`/`FONT_VALUE`/
  `FONT_VALUE_SMALL`) **only if** nothing else in core references them; the `7x13`/`6x10`
  registry entries STAY (the plugin resolves them by name).
- **Migration nicety:** a config-load error mapping bare `type = "coingecko"` (and, while we're
  here, `coinbase` / `etherscan`) to a clear "this is now the `crypto.*` plugin — install
  `led-ticker-crypto`" message, so stale configs fail helpfully rather than "unknown widget."

### Phase 3 — review the extracted plugin (verify/fix + optional enhancements)

- **Up to date:** exercise the live CoinGecko v3 free API — confirm the symbol→id lookup, the
  price + 24h-change endpoint, and whether the free tier now requires a demo key
  (`x-cg-demo-api-key`) or imposes new rate limits; fix whatever has drifted.
- **Correct:** fix bugs surfaced by the live check and the test rebuild.
- **Well tested:** the standalone `test_coingecko.py` covers mocked API success/failure, draw
  conformance (canvas + cursor), and helper units (symbol-id lookup, change coloring, price
  font selection), alongside the import-purity and smoke tripwires.
- **Enhancements:** any modest, clearly-useful improvement spotted during review (e.g.
  configurable `vs_currency`, multiple coins, number formatting) is written up and brought back
  for explicit approval **before** it is built. No enhancement is assumed.

## Sequencing & PRs

1. `led-ticker-crypto`: repo creation + Phase-1 faithful port (validated pixel-identical, CI green).
2. Core-removal PR (Phase 2), opened only after #1 is green.
3. Phase-3 review work as its own PR(s) on the plugin, with an enhancements checkpoint.

Each lands via its own worktree + branch + PR; no work on `main`; merges only with explicit
go-ahead.

## Testing & validation

- Phase 1: pixel-identical render-compare (SHA-256 over N frames) between core coingecko and
  the plugin; full plugin `pytest -q` + `ruff check`; import-purity + smoke tripwires green.
- Phase 2: core `make test` green after removal (no dangling imports/tests); a `grep` sweep
  confirms zero remaining `coinbase`/`coingecko`/`etherscan` references outside intentional
  migration text; the migration error is unit-tested.
- Phase 3: live-API check (network); rebuilt suite passes; any enhancement ships with its own tests.

## Risks & mitigations

- **CoinGecko API drift:** the faithful port may not actually fetch live. Mitigated by design —
  Phase 1 proves *rendering* identity with fixtures/mocks; Phase 3 owns live-API correctness.
- **Outward-facing repo creation:** `gh repo create led-ticker-crypto` is hard to undo; confirm
  before running, and mirror pool/baseball visibility (public) + the `LED_TICKER_DEPLOY_KEY` CI setup.
- **Config breakage:** the `coingecko` → `crypto.coingecko` rename breaks existing configs; the
  Phase-2 migration error makes that failure self-explanatory.
- **Orphaned font-constant pruning:** only prune after confirming no non-crypto consumer; when
  in doubt, leave the constant (cheap to keep, like the `lazy_palette`/`GEOMETRIC_SHAPES` retention).

## Out of scope

- Re-homing coinbase or etherscan into the plugin (deleted now; the `crypto` namespace simply
  leaves room to add them later as `crypto.coinbase` etc. if desired).
- Any core public-surface additions (none required).
