# Discoverability Pass — Design

**Date:** 2026-06-23
**Status:** Approved (design phase)
**Branch:** `docs/discoverability-pass`

## Problem

The `led-ticker` repo went public for the open-source launch but its discovery
surface is unconfigured:

- GitHub repo **description** is the placeholder `"My LED Ticker code"` — invisible
  to anyone searching for what the project actually is.
- **Zero GitHub topics** are set — topics are GitHub's primary discovery/browse
  surface and the single biggest miss.
- **No homepage URL** — `docs.ledticker.dev` is not wired into the repo sidebar.
- The **README** carries Raspberry Pi model keywords but none of the hardware /
  library brand names a maker would actually search for (Adafruit RGB Matrix
  HAT/Bonnet, HUB75, `hzeller/rpi-rgb-led-matrix`, panel pitches).
- The PyPI package `led-ticker-core` has **no `keywords` field** in
  `pyproject.toml` and a minimal `classifiers` set, weakening PyPI search.

## Positioning

**DIY / hardware-first.** Keywords used are genuine hardware and library names
people search for. No competitor name-drops (no "Tidbyt/Vestaboard alternative"
framing) and no keyword-stuffing — every added term must read as natural,
useful prose or legitimate metadata.

## Scope

Full discoverability surface, in four parts. Parts 1–3 are executed in this
effort; Part 4 is a documented manual follow-up.

### Part 1 — GitHub repo metadata (via `gh repo edit`)

Highest ROI, lowest risk. No file changes; pure repo settings.

- **Description** (replaces `"My LED Ticker code"`):
  > Drive Adafruit RGB Matrix HAT / HUB75 LED panels from a Raspberry Pi with a
  > TOML config — scrolling news, weather, crypto, and more. Asyncio Python.
- **Homepage:** `https://docs.ledticker.dev`
- **Topics** (lowercase, hyphenated — GitHub allows up to 20):
  `raspberry-pi`, `raspberry-pi-5`, `raspberry-pi-4`, `led-matrix`,
  `rgb-led-matrix`, `hub75`, `adafruit`, `led-sign`, `led-ticker`,
  `led-display`, `rpi-rgb-led-matrix`, `hzeller`, `python`, `asyncio`,
  `docker`, `pixel-art`, `scrolling-text`, `bdf-fonts`

### Part 2 — README keyword integration

Two surgical, non-bloating additions:

1. **Tagline sentence** directly under the H1, carrying high-value search terms
   in natural prose (e.g. naming Adafruit RGB Matrix HAT / HUB75 panels and the
   `hzeller/rpi-rgb-led-matrix` foundation).
2. **New "Hardware compatibility" subsection** under `## Hardware` that answers
   "will my hardware work?" while being keyword-dense:
   - Adafruit RGB Matrix HAT + RGB Matrix Bonnet (`hardware_mapping = "adafruit-hat"`)
   - HUB75 panels; pitches P3 / P4; sizes 32×64 and 16×32
   - `hzeller/rpi-rgb-led-matrix` library (and the project's fork)
   - Pi 4 (BCM2711 GPIO backend) / Pi 5 (RP1 PIO/RIO backend)

   This subsection must stay factually aligned with the existing `## Hardware`
   prose and CLAUDE.md hardware invariants (no new claims).

### Part 3 — PyPI metadata (`pyproject.toml`)

- Add a `keywords = [...]` array (PyPI indexes these). Mirror the GitHub topic
  vocabulary where it makes sense: raspberry-pi, led-matrix, rgb-led-matrix,
  hub75, adafruit, led-sign, asyncio, etc.
- Add 2–3 richer trove `classifiers`, drawn only from the official PyPI
  classifier list, e.g.:
  - `Topic :: System :: Hardware`
  - `Framework :: AsyncIO`
  - `Intended Audience :: Developers`

  (Each must be verified against the canonical classifier list before adding —
  an invalid classifier breaks the PyPI upload.)

### Part 4 — Social preview image (manual follow-up, NOT automated)

The og:image shown when the repo is linked in Slack / Discord / social is a
1280×640 PNG uploaded through repo **Settings → Social preview** in the GitHub
web UI. It cannot be set via `gh`/CLI and should not be fabricated. Documented
as a recommended manual step (a real LED-panel photo is the natural asset).

## Out of scope (YAGNI)

- `CITATION.cff` — academic-citation metadata; not this audience.
- Competitor-comparison content / "alternative to X" framing.
- Community-profile badges / shields beyond the existing CI + License badges.
- Any change to the docs site itself (this is repo-surface only).

## Success criteria

- `gh repo view` shows the new description, homepage, and topic set.
- README renders with the tagline + Hardware compatibility subsection, no broken
  links, prose reads naturally (not stuffed).
- `pyproject.toml` parses, `keywords` present, all classifiers valid; `make dev`
  / build still succeed.
- Part 4 captured as a checklist item for the maintainer.

## Verification

- `make dev` in the worktree (per project convention) and a build/parse check of
  `pyproject.toml`.
- `make lint` is not strictly required (no Python source change) but run if the
  pyproject edit is non-trivial.
- Visual README review (Markdown lint / link check) before PR.
- Confirm `gh repo edit` succeeded via `gh repo view --json description,homepageUrl,repositoryTopics`.
