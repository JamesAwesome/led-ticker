# Baseball plugin extraction — design

**Date:** 2026-06-06
**Status:** Approved design, pending implementation plan
**Precedent:** `docs/superpowers/plans/2026-06-03-pool-plugin-extraction.md` (the pool extraction this mirrors)

## Goal

Extract the MLB scores widget, the MLB standings widget, the baseball emoji,
and the baseball transitions out of led-ticker core into a new standalone
**public** GitHub repo `JamesAwesome/led-ticker-baseball`, shipped as a single
plugin under the `baseball` namespace. This is the **second dogfood** of the
plugin system after pool — where pool proved the public surface for a
*data-fetching* widget, baseball proves it for *rich rendering widgets plus a
hi-res sprite transition*.

## Decisions (locked during brainstorming)

| Decision | Choice |
|---|---|
| Repo name | `led-ticker-baseball` (public, under `~/projects/github/jamesawesome/`) |
| Plugin namespace | `baseball` (one repo, one package, one `register(api)`) |
| Scores widget key | `type = "baseball.scores"` (was `type = "mlb"`) |
| Standings widget key | `type = "baseball.standings"` (was `type = "mlb_standings"`) |
| Transition keys | `baseball.roll`, `baseball.roll_reverse`, `baseball.roll_alternating` (were `baseball` / `_reverse` / `_alternating`) |
| Emoji slug | `:baseball.ball:` (slug `ball` under ns `baseball`; plugin emoji slugs are namespaced — `:baseball:` cannot stay bare). Register both lo-res `api.emoji("ball", …)` and hi-res `api.hires_emoji("ball", …)`. |
| Public-surface strategy | **Expand** `led_ticker.plugin` so the plugin imports ONLY from it (AST-verified, same tripwire as pool) |
| Baseball emoji disposition | **Full extraction** — emoji + its private `_generate_baseball_hires` generator leave core; core configs/tests/docs updated |

## Inventory — what moves

| Core today | → Plugin (`baseball` namespace) |
|---|---|
| `src/led_ticker/widgets/mlb.py` (`@register("mlb")`, ~1676 lines; includes `MLB_TEAM_COLORS`, `MLB_TEAM_NAMES`, layouts `ticker`/`scoreboard`/`two_row`, `MLBTwoRowMessage`) | `src/led_ticker_baseball/scores.py` → `baseball.scores` |
| `src/led_ticker/widgets/mlb_standings.py` (`@register("mlb_standings")`) — imports team tables from `widgets.mlb` | `src/led_ticker_baseball/standings.py` → `baseball.standings` |
| baseball emoji in `pixel_emoji.py`: `BASEBALL` (lo-res 8×8), `BASEBALL_HIRES`, generator `_generate_baseball_hires`, registry entries in `EMOJI_REGISTRY` + `HIRES_REGISTRY` | `src/led_ticker_baseball/emoji.py` → `api.emoji("ball", BALL)` + `api.hires_emoji("ball", BALL_HIRES)`; inline slug `:baseball.ball:` (lo-res pairing required for inline use) |
| baseball transitions in `transitions/baseball.py` (`baseball`, `baseball_reverse`, `baseball_alternating`, with hi-res dispatch) | `src/led_ticker_baseball/transition.py` → `api.transition("roll" / "roll_reverse" / "roll_alternating")` |
| baseball hi-res funcs inside the SHARED `transitions/_hires_loader.py`: `render_hires_baseball_frame`, `_baseball_rotation_frames`, `_paint_procedural_baseball` | move into the plugin's `transition.py` (they call `_generate_baseball_hires`, which moves with them — fully self-contained; nyancat/pokeball funcs stay in core's `_hires_loader.py`) |

### Stays in core (deliberately)

- `:flower:` and `:star:` slugs — MLB uses them as Spring-Training / All-Star
  markers, but they are **generic** emoji. They stay in core; the plugin keeps
  rendering them via the public `draw_with_emoji`.
- nyancat / pokeball hi-res machinery in `_hires_loader.py` — only the
  baseball-specific functions move.

## Core public-surface expansion (prerequisite — Core PR A)

The plugin must import ONLY from `led_ticker.plugin` (enforced by an AST
tripwire, identical to the one guarding the pool plugin). The following symbols
are added to `led_ticker.plugin.__all__`. This PR is **pure-additive, no
behavior change**, and mergeable on its own.

**For the widgets:**

- `TickerMessage` (today only `SegmentMessage` / `TwoRowMessage` are public)
- `FrameAwareBase` — public alias/promotion of `widgets._frame_aware._FrameAware`,
  named to match the existing `ColorProviderBase` / `BorderEffectBase` convention
- `safe_scale`, `compute_baseline_for_band` (from `drawing`; `compute_baseline`
  is already public)
- `measure_width` (from `pixel_emoji`; distinct from the already-public
  `measure_emoji_at`)
- `resolve_band_heights` (from `widgets._row_layout`)
- `font_line_height_logical`, `FONT_DEFAULT`, `FONT_SMALL` (from `fonts`;
  `resolve_font` is already public)

**For the hi-res transition (net-new surface pool never exercised):**

- `ScaledCanvas` (for the `isinstance(canvas, ScaledCanvas)` dispatch)
- `unwrap_to_real` (and `paint_hires` if the hi-res paint path needs it)
- `SNAP_THRESHOLD` — optional; the plugin may instead define its own snap
  constant locally with a comment

**Already reachable — no work:** `make_color`, `lazy_palette`, `RGB_WHITE`
(via the re-exported `colors` module), `SegmentMessage`, `TwoRowMessage`,
`run_monitor_loop`, `spawn_tracked`, `compute_baseline`, `Transition`,
`ColorProvider`, `draw_with_emoji`.

## Plugin repo structure (mirrors `led-ticker-pool`)

```
led-ticker-baseball/
  pyproject.toml          # entry-point group "led_ticker.plugins"; baseball = "led_ticker_baseball:register"
                          # [tool.uv.sources] led-ticker = { path = "../led-ticker", editable = true }
                          # requires-python = ">=3.14"; deps: led-ticker, aiohttp (+ whatever mlb.py needs)
  README.md               # canonical baseball-widget docs (config keys, layouts, options, screenshots)
  uv.lock
  .github/workflows/ci.yml
  src/led_ticker_baseball/
    __init__.py           # register(api): api.widget("scores")/("standings"); api.emoji("baseball"); api.transition("roll"/...)
    scores.py             # ex-mlb.py — imports ONLY led_ticker.plugin
    standings.py          # ex-mlb_standings.py — team tables imported from scores.py (same-package, fine)
    emoji.py              # baseball lo/hi-res sprites + _generate_baseball_hires generator
    transition.py         # baseball roll transition family + moved hi-res render funcs
    validate_config.py    # team-abbr / layout-value / two-row-field guardrails (validate_config convention)
  tests/                  # ported test_mlb, test_mlb_scoreboard, test_mlb_lazy_palette, test_mlb_standings, test_baseball
                          # + the baseball slices of test_pixel_emoji / test_hires_loader / test_transitions
```

No `from __future__ import annotations` anywhere in plugin source (PEP 649 rule,
same as core).

## Phases

### Phase 0 — Core public-surface expansion (Core PR A)

Add the §"Core public-surface expansion" symbols to `led_ticker.plugin`.
Pure-additive, no behavior change. Update the plugin-system docs/reference for
the new surface. Mergeable independently — unblocks Phase 2.

### Phase 1 — Git repository setup

1. Create the local project folder and `git init` (or `gh repo create`) at
   `~/projects/github/jamesawesome/led-ticker-baseball`.
2. Create the **public** GitHub repo `JamesAwesome/led-ticker-baseball`
   (`gh repo create JamesAwesome/led-ticker-baseball --public`).
3. **CI auth (security-sensitive, mirrors pool):** led-ticker is a **private**
   repo, so CI checks it out as a sibling via a **read-only deploy key**:
   - Generate an SSH keypair scoped to this CI use.
   - Add the **public** key as a read-only deploy key named
     `led-ticker-baseball CI (read-only)` on the `JamesAwesome/led-ticker`
     repo.
   - Add the **private** key as the secret `LED_TICKER_DEPLOY_KEY` on
     `JamesAwesome/led-ticker-baseball`.
   - The workflow uses `ssh-key:` (NOT `token:`).
4. Seed the repo: `pyproject.toml`, `.gitignore`, `README.md` stub, `LICENSE`
   (match pool's), the `.github/workflows/ci.yml` from Phase 1a below.
5. Push `main` and confirm the first CI run goes **green** before porting code.

#### Phase 1a — CI / GitHub Actions (explicit, must be current)

The workflow mirrors pool's `ci.yml`: checkout self, checkout private core as a
sibling via the deploy key, install uv, `uv sync --extra dev`, `ruff check`,
`pytest`. Triggers: `push` to `main` and all `pull_request`.

**Action versions MUST be verified current at repo-creation time** — do NOT
copy stale pins blindly. As of 2026-06-06 pool uses `actions/checkout@v6.0.3`
and `astral-sh/setup-uv@v8.2.0` (both Node-24 majors). Before committing the
workflow:

1. Check each action's latest release (`gh release view` / the GitHub releases
   page) and pin to the newest stable major-locked SHA/tag.
2. If a newer version exists than pool's pins, use it here AND open a follow-up
   to bump pool to match (keep the two plugins' CI in lockstep).
3. Confirm the runner image (`ubuntu-latest`) and `python-version: "3.14"`
   still match core's `requires-python`.

Reference workflow (update versions per step 1 above):

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout led-ticker-baseball
        uses: actions/checkout@v6.0.3        # verify latest at setup
        with:
          path: led-ticker-baseball
      - name: Checkout led-ticker (sibling dependency)
        uses: actions/checkout@v6.0.3        # verify latest at setup
        with:
          repository: JamesAwesome/led-ticker
          path: led-ticker
          ssh-key: ${{ secrets.LED_TICKER_DEPLOY_KEY }}
      - name: Install uv
        uses: astral-sh/setup-uv@v8.2.0      # verify latest at setup
        with:
          python-version: "3.14"
      - name: Sync
        working-directory: led-ticker-baseball
        run: uv sync --extra dev
      - name: Lint
        working-directory: led-ticker-baseball
        run: uv run ruff check src tests
      - name: Test
        working-directory: led-ticker-baseball
        run: uv run pytest -q
```

### Phase 2 — Build the plugin

Port `mlb.py`/`mlb_standings.py` → `scores.py`/`standings.py`, the emoji, and
the transition (with its hi-res funcs) against the Phase 0 surface. Rewrite all
`from led_ticker.<internal>` imports to `from led_ticker.plugin import …`. Wire
`register(api)`. Port `validate_config` guardrails. Port the tests. CI green.

**AST tripwire:** a test asserts every module under `src/led_ticker_baseball/`
imports led-ticker symbols ONLY from `led_ticker.plugin` (copy pool's test).

### Phase 3 — Remove from core + migrate (Core PR B)

1. Delete `widgets/mlb.py`, `widgets/mlb_standings.py`, `transitions/baseball.py`,
   the baseball emoji from `pixel_emoji.py`, and the baseball funcs from
   `_hires_loader.py`. Remove their registry entries and `widgets/__init__.py`
   imports.
2. Migrate the ~14 `config.*` files that use `mlb` / `mlb_standings` to
   `type = "baseball.scores"` / `"baseball.standings"` and the baseball
   transition keys to `baseball.roll*`.
3. Handle `:baseball:` in the ~6 generic configs that showcase it
   (`config.toml`, `config.longboi.toml`, `config.small_sign.toml`,
   `config.scale_smoketest.toml`, `config.hires_emoji_test.example.toml`, and
   the `widgets-legacy.md` doc line): for configs that install the baseball
   plugin, migrate `:baseball:` → `:baseball.ball:`; for purely-decorative core
   demo/test configs that should stay plugin-free, replace with another core
   hi-res emoji (e.g. `:moon:` / `:star:`) or drop it. Note that
   `:baseball.ball:` only renders where the plugin is installed.
4. Update core tests: remove the baseball slices from `test_pixel_emoji.py`,
   `test_hires_loader.py`, `test_transitions.py`, `test_widgets/test_message.py`;
   delete `test_mlb*.py` / `test_baseball.py`.
5. Add the plugin to `config/requirements-plugins.example.txt` (git URL) and the
   Dockerfile / `deploy/install.sh` install path — same declarative,
   constraint-based install as pool.
6. Confirm the plugin's `validate_config` restored every guardrail core was
   enforcing (the pool extraction lost some on the first pass — check `layout`
   value validation and any two-row-field gating).

### Phase 4 — Hardware validation

Validate on a real sign before declaring done:

- **Bigsign / longboi (scale > 1):** hi-res baseball emoji + hi-res `baseball.roll`
  transition + scaled `baseball.scores`/`standings` rendering.
- **Smallsign (scale = 1):** lo-res 8×8 baseball emoji + non-hires transition.

Each sign needs `cp config/requirements-plugins.example.txt
config/requirements-plugins.txt` (if not already present) + `docker compose up
--build` to pick up the plugin before its migrated config works.

### Phase 5 — Docs

- docs-site `plugins/available/` directory entry for baseball.
- Slim the core MLB widget docs pages to pointers at the plugin README.
- Plugin `README.md` becomes the canonical baseball-widget docs (config keys,
  layouts, all options, screenshots/GIFs) — like pool's README.
- Update `CLAUDE.md`: remove the MLB/baseball-emoji/baseball-transition file-map
  entries and invariants from core; note baseball as an external plugin in the
  Plugin invariants section.

## Risks / watch-items

- **Production signs (longboi, small_sign)** run MLB today and carry the
  `:baseball:` showcase line; after Phase 3 they need the plugin installed
  before their migrated configs work — the one-time
  `cp requirements-plugins.example → .txt` + `docker compose up --build` deploy
  caveat that pool established. Surface this in the deploy notes.
- **Lost guardrails on extraction** — pool silently dropped some of core's
  validation; the spec review caught it. Pre-empt by porting MLB's validation
  into the plugin's `validate_config` and diffing against what core enforced.
- **Hi-res transition is new plugin territory** — if the
  `ScaledCanvas` / `unwrap_to_real` public surface proves awkward to consume,
  that's a signal to refine the public API (a feature of the dogfood, not a
  blocker). Capture any friction for the plugin-system docs.
- **CI action drift** — Phase 1a's "verify latest" step is mandatory; do not
  ship stale pins. Keep baseball and pool CI versions in lockstep.
- **PEP 649** — no `from __future__ import annotations` in plugin source.

## Out of scope

- Per-team logo sprites — there are none; teams render as text + the
  `MLB_TEAM_COLORS` table. Nothing to move.
- Publishing led-ticker to PyPI — still path-pinned via `[tool.uv.sources]`,
  same as pool.
- Splitting into two namespaces — rejected during brainstorming in favor of one
  `baseball` namespace.
