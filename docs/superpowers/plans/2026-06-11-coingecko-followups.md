# CoinGecko Follow-ups Plan — deferred nits + demo gif + docs-site refresh

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development for the code/docs tasks. Steps use `- [ ]`.

**Goal:** Close the four non-blocking review nits left after Phase 3, generate a demo gif for the `crypto.coingecko` widget, and refresh the docs site (which still describes the pre-Phase-3 single-coin widget).

**Architecture:** Two repos, two PRs. (A) led-ticker-crypto: the code nits + the demo gif (rendered locally, committed into the plugin repo's `docs/`, referenced from its README — the baseball/pool convention). (B) led-ticker core: docs-site refresh (`available.mdx` Phase-3 surface + a dedicated widget page + sidebar link).

**Tech Stack:** Python 3.14, attrs, aiohttp, pytest; Astro/Starlight docs site (prettier + astro check). Plugin imports only `led_ticker.plugin`.

**Standing rules:** never work on `main`; the two worktrees are `/Users/james/projects/github/jamesawesome/ltc-followups` (plugin, branch `fix/phase3-followups`) and `/Users/james/projects/github/jamesawesome/lt-cryptodocs` (core, branch `docs/crypto-phase3-site`). Verify `git branch --show-current` per task. Commit `--no-verify`; end messages with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. No "footgun"/"gun" metaphors. Run `uv run pytest -q` + `uv run ruff check src tests` after each plugin task. Don't push/merge without controller instruction.

---

## Phase A — plugin code nits (led-ticker-crypto, `ltc-followups`)

### Task A1: Initial-fetch resilience (the substantive one)
**Files:** `src/led_ticker_crypto/coingecko.py`; `tests/test_coingecko.py`.

Today `start()` awaits the first `update()` directly, so a CoinGecko 429 at boot (the keyless tier 429s after ~4 calls/min) makes the widget **fail to construct** and get skipped for the session. Make the *price* fetch resilient: construct with placeholder data, log, and let `run_monitor_loop` recover. (The `/coins/list` resolution for `symbols` is NOT wrapped — without ids there are no coins to build; that stays a hard startup error.)

- [ ] Step 1: failing test — `start()` whose initial price fetch raises (`_mock_session` returning 429) still returns a constructed widget with `feed_stories` populated (default `price_data` preserved) and does NOT raise. (If symbols resolution is involved, keep that separate — use `symbol_ids`/`symbol` so resolution succeeds and only the price fetch fails.)
```python
async def test_start_tolerates_initial_price_fetch_failure():
    session = _mock_session({"status": {"error_code": 429}}, status=429)
    w = await CoinGeckoMonitor.start(symbol="BTC", symbol_id="bitcoin",
                                     currency="USD", session=session)
    assert w is not None
    assert w.feed_stories[0].price_data["price"] == "0.0000"  # placeholder kept
```
- [ ] Step 2: run → FAIL (currently the 429 propagates out of `start`).
- [ ] Step 3: in `start()`, wrap the initial `await widget.update()` in `try/except Exception as e: logging.warning("crypto.coingecko initial fetch failed (%s); starting with placeholder data, will retry", e)`. Still `spawn_tracked(run_monitor_loop(widget, update_interval))` and return the widget. Do NOT swallow coin-list/resolution errors (those happen before widget construction).
- [ ] Step 4: run → PASS. Full suite + ruff.
- [ ] Step 5: commit `feat: tolerate a failed initial price fetch (start with placeholder, retry via loop)`.

### Task A2: Route `update()` by coin_id instead of `zip`
**Files:** `src/led_ticker_crypto/coingecko.py`; `tests/test_coingecko.py`.

`update()` pairs API results to stories via `zip(self.coins, self.feed_stories)` — correct only because stories are built in `coins` order. Build a `{coin_id: story}` map (once, in `__attrs_post_init__`, or derive in `update`) and look up by `coin_id` so routing can't drift.

- [ ] Step 1: failing test — construct a monitor, then reverse `feed_stories` (simulate an order skew) and assert `update()` still routes each coin's price to the story with the matching symbol. (Or assert an explicit `self._story_by_id` map exists and maps coin_id→story.)
- [ ] Step 2: run → FAIL.
- [ ] Step 3: add `self._story_by_id = {cid: story for (_, cid), story in zip(self.coins, self.feed_stories)}` in `__attrs_post_init__` (a non-attrs/`init=False` attr), and in `update()` resolve each parsed `coin_id` via `self._story_by_id.get(coin_id)` instead of zip. (attrs: declare `_story_by_id: dict = attrs.field(init=False, factory=dict)` and fill it post-init.)
- [ ] Step 4: run → PASS. Full suite + ruff.
- [ ] Step 5: commit `refactor: route update() by coin_id map (was positional zip)`.

### Task A3: Drop the unused `_CoinTicker.currency` field
**Files:** `src/led_ticker_crypto/coingecko.py`; `tests/*` (any `_CoinTicker(... currency=...)` constructions).

The container formats prices (using its own `currency`) before storing them in each story's `price_data`; `_CoinTicker.draw` only uses `symbol` + the pre-formatted `price_data`, never `currency`. Remove the dead field. (Keep `bg_color` — the engine reads it off the story.)

- [ ] Step 1: `grep -rn "currency" src/led_ticker_crypto/coingecko.py tests/` — find every `_CoinTicker` construction passing `currency=` and the field def.
- [ ] Step 2: remove `currency` from `_CoinTicker` (field + any post-init use) and from the places the container builds stories (don't pass `currency=` to `_CoinTicker`). Keep `currency` on `CoinGeckoMonitor`.
- [ ] Step 3: run full suite + ruff → green (fix any test that constructed `_CoinTicker(currency=...)`).
- [ ] Step 4: commit `refactor: drop unused _CoinTicker.currency field`.

### Task A4: Test polish
**Files:** `tests/test_coingecko.py`.

- [ ] Step 1: Replace the low-value `assert pos > 0` smoke checks (in the draw-returns-canvas tests) with stronger assertions: assert the returned object IS the canvas AND `pos == 160` for the centered case (or a specific expected cursor for an uncentered case) — mirror the meaningful `test_centered_fills_canvas`. If a `pos > 0` check is genuinely all that's verifiable for a case, leave it but add a sibling exact-value assertion elsewhere.
- [ ] Step 2: Pin the small-font cutoff boundary: add tests that `_get_price_font` returns the normal font at a 10-char price and the small font at an 11-char price (the boundary is `len > 10`). Use real strings (e.g. `"1234.5678"` len 9 vs `"12345.6789"` len 10 vs `"123456.7890"` len 11 — pick exact-length strings and assert the font identity).
- [ ] Step 3: run → green. ruff.
- [ ] Step 4: commit `test: strengthen draw assertions; pin small-font length boundary`.

---

## Phase B — demo gif (led-ticker-crypto, `ltc-followups`) — CONTROLLER-RUN

The demo renderer (`tools/render_demo` in core) only finds **pip-installed** plugins. This is a local manual render (not CI). The controller runs it after Phase A (the fixes don't change rendering, but render against the final code). The gif lives in the PLUGIN repo's `docs/` and is referenced from its README — matching baseball/pool.

- [ ] Step B1: Create `/Users/james/projects/github/jamesawesome/ltc-followups/docs/demo.toml` — a smallsign-style config (160×16, scale 1) with `type = "crypto.coingecko"` using **explicit `symbol_ids`** for determinism and to showcase the adaptive sub-cent formatting:
```toml
# render-duration: 18
[display]
rows = 16
cols = 32
chain_length = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 3.0

[[playlist.section.widget]]
type = "crypto.coingecko"
symbol_ids = ["bitcoin", "ethereum", "shiba-inu"]
currency = "USD"
```
- [ ] Step B2: Render locally WITH network (so `start()`'s initial fetch populates real prices before frames are captured): in the CORE repo venv, editable-install the plugin and run the renderer:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
uv pip install -e ../led-ticker-crypto
uv run --extra render python -m tools.render_demo.render \
  ../ltc-followups/docs/demo.toml --duration 18 \
  --out ../ltc-followups/docs/crypto-coingecko.gif
# (or `make render-demo CONFIG=../ltc-followups/docs/demo.toml OUT=../ltc-followups/docs/crypto-coingecko.gif` — match the real Make/CLI invocation discovered in tools/render_demo)
```
Confirm the gif shows three cycled coins with real (non-zero) prices, incl. SHIB rendering a sub-cent value (not `0.0000`). If the live API rate-limits and prices come back zero, retry (or set `COINGECKO_API_KEY` if available).
- [ ] Step B3: Reference the gif in `/Users/james/projects/github/jamesawesome/ltc-followups/README.md` (near the overview) — `![crypto.coingecko demo](docs/crypto-coingecko.gif)` — matching how the pool/baseball READMEs embed their `docs/*.gif`.
- [ ] Step B4: Commit `docs: demo config + rendered gif for crypto.coingecko`. (Then controller pushes the branch + opens the plugin PR covering Phase A + B.)

---

## Phase C — docs-site refresh (led-ticker core, `lt-cryptodocs`)

### Task C1: Refresh the `available.mdx` crypto section for the Phase-3 surface
**Files:** `docs/site/src/content/docs/plugins/available.mdx`.
- [ ] Update the `led-ticker-crypto` section (currently single-coin) to describe: multi-coin (cycles one ticker per coin); the three coin-spec styles (`symbol`+`symbol_id`, `symbol_ids`, `symbols` auto-resolved unique-or-error); `api_key`/`COINGECKO_API_KEY` → demo header and the keyless ~5/min rate limit; adaptive sub-cent formatting. Keep the install snippet. Keep it concise (it defers full options to the repo README). Link to the new widget page (Task C2).

### Task C2: Add a dedicated widget page (pool pattern)
**Files:** Create `docs/site/src/content/docs/widgets/crypto-coingecko.mdx` (slug `/widgets/crypto-coingecko/` — hyphen, not a dot, to keep the route clean).
- [ ] Mirror `docs/site/src/content/docs/widgets/pool.mdx`: frontmatter title/description; one-paragraph "provided by the led-ticker-crypto plugin (`type = "crypto.coingecko"`)"; install line (`requirements-plugins.txt` git dep); a short feature list (multi-coin, auto-lookup, demo key, adaptive formatting); and "full options + the demo gif live in the [led-ticker-crypto README](https://github.com/JamesAwesome/led-ticker-crypto#readme)". Optionally embed the gif if the docs site can reference the plugin-repo raw URL; otherwise just link.

### Task C3: Sidebar + cross-links
**Files:** `docs/site/astro.config.mjs`; (optional) `widgets/index.mdx`, `index.mdx`, `tutorial/05-polish.mdx`, `hardware/smallsign.mdx`.
- [ ] Point the sidebar `crypto.coingecko (plugin)` entry at `/widgets/crypto-coingecko/` (was `/plugins/available/`), matching pool/baseball. Update the `widgets/index.mdx` crypto row link to the new page. Leave the other prose links unless trivially improved.

### Task C4: Lint
- [ ] `cd /Users/james/projects/github/jamesawesome/lt-cryptodocs/docs/site && pnpm install --frozen-lockfile && pnpm run lint` (prettier --check + astro check) → clean. Run `pnpm exec prettier --write` on edited files if needed. Then commit `docs: refresh crypto.coingecko docs-site surface (multi-coin/auto-lookup/demo-key) + dedicated widget page`.

---

## Sequencing & verification
1. Phase A (plugin code) → green suite + ruff.
2. Phase B (gif) — controller renders + commits into the plugin worktree.
3. Push plugin branch, open **led-ticker-crypto** PR (A+B); CI green (deploy key is set).
4. Phase C (core docs) → docs-lint green; push, open **led-ticker** docs PR.
5. Hold both for user merge.

## Self-review
- Deferred items: A1 (initial-fetch) ↔ panel finding #1; A2 (zip) ↔ #2; A3 (dead field) ↔ #3 (currency only — bg_color kept, it's engine-read); A4 ↔ #4 test polish. Gif ↔ user ask. Docs-site ↔ user ask (Part A stale-docs finding).
- Gif hosting = plugin repo (user's choice), matching baseball/pool; core docs link to the README.
- No core public-surface changes; no behavior change to the render path (A-fixes don't alter `draw`).
