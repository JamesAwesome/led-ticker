# Firebird shippable-asset sweep (gate #1, step 3)

**Date:** 2026-06-21
**Status:** approved (design)
**Goal:** Replace every non-shippable sample-media asset in the repo (third-party copyright + real-brand
logo) with one CC0 "Firebird phoenix" asset family, so the soon-public repo carries no encumbered media.
Completes gate #1 (steps 1-2, the §6 brand + copy anonymization, merged in #256).

## Background

`config/assets/` ships media used as the GENERIC demo sample across ~55 references (configs, demos,
docs): `pika_wave.gif`/`pika_wave_transparent.gif` (Pikachu — Nintendo copyright; the gif-widget sample),
`moon-transparent.png` + `bunny-transparent.png` + `bunny-nontransparent.png` + `moon_bunny_transparent.gif`
(the real Moon Bunny LOGO + the still-image-widget sample + the storefront lockup), and `kpop-dance.webp`
(540×400 real dance footage — the animated-WebP sample). `pride.gif`/`pride_trans.gif` are generic — LEAVE.
7 files to remove. The §6 copy rename (#256) left these asset binaries/paths intentionally untouched
(deferred to this PR).

## Decisions (from brainstorming)

1. **Source: OpenGameArt "pixel-phoenix" by *zonked*, CC0 / public domain**
   (<https://opengameart.org/content/pixel-phoenix>). The source files — `phoenix-cc0-no-bg.gif` (a 20×20
   animated, transparent pixel sprite, ~5KB) + `phoenix-cc0-spritesheet.png` (100×80) — are already
   downloaded and staged in this worktree at `.superpowers/asset-src/` (git-ignored scratch) for the
   implementer to vendor. CC0 verified (no restrictions); pixel-art aesthetic fits the LED panel.
2. **One source → derive all formats** via a small COMMITTED Pillow script (`tools/derive_phoenix_assets.py`).
   Reproducible + coherent. Outputs (committed to `config/assets/`):
   - `phoenix.gif` — animated, composited on black (the gif decoder composites alpha onto black; matches the
     old `pika_wave.gif` opaque path)
   - `phoenix_transparent.gif` — animated, real alpha (for the scroll-behind demos; matches
     `pika_wave_transparent.gif`)
   - `phoenix.png` — a single representative frame, opaque (still-image sample + the opaque-PNG demos)
   - `phoenix_transparent.png` — that frame with alpha (transparent still-image demos + the logo)
   - `phoenix.webp` — animated, transcoded (the animated-WebP demo)
3. **Dimensions:** nearest-neighbor upscale the 20×20 source to **220×220** (11×, crisp pixel edges) so the
   derived assets match `pika_wave`'s 220×220 square footprint and the demos render the same (scale-by-height
   to 64, centered). The webp reuses the square size (the demo proves WebP *support*, not a specific aspect).
   Use nearest-neighbor everywhere to preserve pixel-art crispness.
4. **Phoenix doubles as the Firebird logo mark** — `phoenix.png` / `phoenix_transparent.png` replace the
   moon/bunny logo in the storefront lockup + the `image-static-logo` demo. One coherent symbol.
5. **Provenance:** add `config/assets/ATTRIBUTION.md` recording the CC0 source (OpenGameArt, author *zonked*,
   the URL, "CC0 / public domain — no attribution required; recorded for provenance"). CC0 needs no
   attribution; recording it protects the project.

## Components

### `tools/derive_phoenix_assets.py` (committed, Pillow)

**Vendor the source first:** move the staged CC0 file from `.superpowers/asset-src/phoenix-cc0-no-bg.gif`
(git-ignored scratch where it's currently parked) to a COMMITTED location, `config/assets/_src/phoenix-cc0-no-bg.gif`
(5KB), so the derive is reproducible from a clean checkout. (Commit the spritesheet too if the script uses it.)

The script reads `config/assets/_src/phoenix-cc0-no-bg.gif` and writes the 5 derived assets to
`config/assets/`. Pure-derivation, idempotent, runnable via `make` (add a `derive-phoenix` target) or
directly. Documents the source + the nearest-neighbor 10× upscale. The animated gif is the frame source
(the spritesheet is a fallback only if frame extraction from the gif is messy).

### Repoint map (apply to every `path = "assets/…"` reference)

| old asset | → new |
|-----------|-------|
| `assets/pika_wave.gif` | `assets/phoenix.gif` |
| `assets/pika_wave_transparent.gif` | `assets/phoenix_transparent.gif` |
| `assets/moon-transparent.png` | `assets/phoenix_transparent.png` |
| `assets/bunny-transparent.png` | `assets/phoenix_transparent.png` |
| `assets/bunny-nontransparent.png` | `assets/phoenix.png` |
| `assets/moon_bunny_transparent.gif` | `assets/phoenix_transparent.gif` |
| `assets/kpop-dance.webp` | `assets/phoenix.webp` |

Reference footprint (current `main`): `pika_wave` ×19 files, `moon-transparent` ×22, `bunny-` ×10,
`kpop-dance` ×3, `moon_bunny` ×1 — across `config/*.example.toml`, `docs/site/demos-*`, `docs/site/demos/`,
and `.mdx` (`widgets/gif.mdx`, `widgets/image.mdx`, `concepts/sections-and-modes.mdx`, transitions docs).
Re-derive the exact set with `git grep -il "pika_wave\|moon_bunny\|moon-transparent\|bunny-\|kpop"`.

### Prose

Rewrite the asset-description prose that named the old media: "Pikachu"/"pika" → "phoenix";
"kpop-dance"/"dance footage" → "phoenix" (animated WebP); "moon"/"bunny" logo descriptions → "phoenix".
Files incl. `widgets/gif.mdx`, `widgets/image.mdx`, transitions docs, and the config comments
(e.g. `config.gif_test.example.toml`'s "Uses pika_wave.gif (220×220 square)" → "Uses phoenix.gif").

### `asset-handling.md` policy fix

`.claude/skills/creating-a-config/references/asset-handling.md` currently states `bunny-transparent.png` /
`kpop-dance.webp` "ship with the public repo" — that was the false premise this sweep corrects. Rewrite the
policy: the repo ships ONE CC0 sample asset family (the phoenix); customer/real-brand or third-party media is
gitignored and never committed.

### Guard extension

Extend `tests/test_no_real_brand.py` with an ASSET-needle check: assert ZERO references to
`pika_wave` / `pikachu` / `pika` / `moon_bunny` / `moon-transparent` / `bunny-` / `kpop` outside the
allow-list (`docs/superpowers/` + the test file). This makes the copyrighted-asset names a permanent
tripwire alongside the existing name + palette guards. (Scope the `pika`/`bunny-` patterns precisely to avoid
false hits.)

## Removals

`git rm` the 7 non-shippable files: `pika_wave.gif`, `pika_wave_transparent.gif`, `moon-transparent.png`,
`bunny-transparent.png`, `bunny-nontransparent.png`, `moon_bunny_transparent.gif`, `kpop-dance.webp`. Keep
`pride.gif` / `pride_trans.gif` (generic). Confirm nothing references a removed file after the repoint.

## Re-render

Re-render the ~15-20 demo GIFs whose source asset changed (the gif/image demos). Per #256, some are blocked
by the gitignored licensed fonts (AtkinsonHyperlegible-Bold etc.) — re-render what's possible, FLAG the
blocked ones (snippet/TOML still consistent; the GIF is the stale artifact), don't fake. The 3 GIFs already
flagged stale in #256 may re-render here if their asset changed — note overlap.

## Testing / verification

- `tools/derive_phoenix_assets.py` runs clean from the committed source and produces all 5 assets at 220×220
  (a test asserting the 5 files exist + are the right format/size, e.g. `tests/test_phoenix_assets.py`, OR a
  smoke check — keep it light).
- `tests/test_no_real_brand.py` (name + palette + NEW asset needles) all green.
- The configs/demos still load + the widgets build: `PYTHONPATH=tests/stubs uv run pytest` full suite green
  (esp. the gif/image widget tests + `test_firebird_bigsign_config_widgets_build`).
- `git grep -il "pika_wave\|moon_bunny\|moon-transparent\|bunny-\|kpop" -- . ':!docs/superpowers' ':!tests/test_no_real_brand.py'`
  → empty.
- No reference to a removed asset file remains (broken-path check).
- `make docs-build` + `make docs-lint` clean; re-rendered GIFs committed; blocked ones flagged.
- `uv run --extra dev ruff check` + `pyright src/` clean (the derive script lives in tools/ — ensure it
  passes lint; it's not in src/).

## Non-goals

- `pride.gif`/`pride_trans.gif` — generic, kept.
- The fonts/render limitation (some demo GIFs un-renderable without the licensed font) — same deferral as
  #256; flag, don't fake.
- A separate text wordmark — the phoenix IS the logo (decision 4).
- Restyling demos beyond the asset swap (keep layout/colors/§6 palette as-is).

## Constraints

- Repo is pre-open-source; the committed CC0 source + derived assets must be genuinely unencumbered.
- Docs: never pipe `docs-lint` to `tail`; run `docs-format` then re-lint.
- No release-history framing in rewritten prose (DOCS-STYLE principle 17).
- Pixel-art crispness: nearest-neighbor scaling only.
- The derive script must be reproducible from a clean checkout (commit the source).
