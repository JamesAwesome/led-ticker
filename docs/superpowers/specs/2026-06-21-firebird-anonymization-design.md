# Moon Bunny → Firebird anonymization (gate #1, step 2)

**Date:** 2026-06-21
**Status:** approved (design)
**Goal:** Remove the real "Moon Bunny Aerial" studio identity from the repo — the leaked
production configs and every Moon Bunny reference in shipped/example/docs surface — and replace
it with the fictional **Firebird Yoga** brand defined in `docs/DOCS-STYLE.md` §6. This is a
prerequisite for open-sourcing and for the getting-started revamp.

**Scope:** anonymization ONLY (leak cleanup + rename + content rewrite). The richer Firebird
**showcase example** (adapting the deleted production config) is a SEPARATE step 3, not this work.

## Decisions (from brainstorming)

1. **One cohesive PR.** §6 (already committed on this branch) + the leak cleanup + the full
   rename land together as one "Moon Bunny → Firebird" anonymization PR. (Pre-open-source there
   is no live public exposure to race, so splitting buys nothing.)
2. **Defer the git-history scrub.** Removing the leaked configs from HEAD + `.gitignore` does NOT
   scrub git history. Rewriting history (`git filter-repo`) mid-development would change every SHA
   and break open PRs/worktrees, for no pre-public benefit. **Do the scrub as a deliberate
   one-time step in open-source prep** — tracked as a gate-1 follow-up. This PR removes from HEAD.
3. **§6 is the single source of truth** for all new copy/colors/handles. Aerial-arts disciplines
   (silks/pole/lyra/ballet/dance/juggling) are **re-authored to yoga**, never find-replaced.
4. **Clean anonymize, don't over-polish `config.firebird.example.toml`.** Step 3 will
   enrich/supersede it with the production-derived rich showcase, so step 2 just makes it correct
   and Moon-Bunny-free.
5. **The `.claude/settings.local.json` WebFetch pin is out of scope** — it is a local, gitignored
   settings file (not in the tracked tree; `git grep` finds nothing). Clean it locally; it is not
   part of this PR.

## Leak cleanup (highest priority)

Two git-tracked, NON-`.example` production configs leak the real studio (live URL, `@handle`,
verbatim disciplines):

- `git rm config/config.moonbunny.production.toml`
- `git rm config/config.pool_bigsign.toml`

Add to `.gitignore` next to the existing `config/config.toml` rule (so a real deployed config
can't be re-committed):

```
config/config.*.production.toml
config/config.pool_bigsign.toml
```

(CLAUDE.md already states the real deployed config is supposed to be gitignored — these two
slipped through. Their CONTENT is captured for step 3 via git history / the prior read.)

## Rename — Group A: business-identity copy → Firebird

Rewrite every Moon Bunny identity reference to Firebird Yoga using §6. **Re-author** disciplines
to yoga; map handles `@moonbunnyaerial`→`@firebirdyoga.demo`, `@MoonBunny`→`@firebird`,
`moonbunnyaerial.com`→`firebirdyoga.demo`, `info@…`→`hello@firebirdyoga.demo`.

Files (the live footprint, ~55 total across A+B):

- **Tracked example configs:** `config/config.moonbunny.example.toml`,
  `config/config.bigsign.moonbunny.example.toml`, `config/config.gif_test.example.toml`,
  `config/config.hires_fonts_test.example.toml`.
- **Config-skill:** `.claude/skills/creating-a-config/SKILL.md` + `references/{snippets,
  decision-rules,hardware-guide,asset-handling}.md` (note: hardware-guide already has a
  `@MoonBunnyBakery` variant — align to Firebird).
- **Repo surface:** `README.md`, `.github/ISSUE_TEMPLATE/submit-sign.yml`, the moonbunny mention
  in `CLAUDE.md`.
- **docs/site demo TOMLs** (~22): `demos-pinned/{border-color_cycle-range, gif-two_row,
  image-two_row-scroll_through, image-two_row, image-typewriter-border, image-typewriter,
  message-brand-color, message-gradient, two_row-asymmetric, two_row-brand-handle,
  two_row-font-hierarchy, two_row-hires-emoji}.toml`; `demos-long/{tutorial-01-setup,
  tutorial-02-first-config, tutorial-03a-sections, tutorial-03b-multi-widget,
  tutorial-03c-two_row-basic, tutorial-03d-two_row-hires, tutorial-04a-font,
  tutorial-04c-image-with-text, tutorial-05a-transitions, tutorial-05b-final,
  widget-pool-two-row}.toml`.
- **docs/site .mdx** (~13): `concepts/{display,fonts}.mdx`; `widgets/{gif,image,message,
  two_row}.mdx`; `tutorial/{01-setup,02-first-config,03-multi-widget,04-custom-branding,
  05-polish}.mdx`; `showcase.mdx`.
- **Test fixtures:** `tests/test_app.py` (`@MoonBunny`), `tests/test_gif_path_resolution.py`
  (`@MoonBunny`), `tests/test_pixel_emoji.py` (`@moonbunnyaerial`, `info@moonbunnyaerial.com`),
  `tests/test_widgets/test_gif.py`, `tests/test_widgets/test_two_row.py`.

## Rename — Group B: filenames / asset dir / referrers

- `config/config.moonbunny.example.toml` → `config/config.firebird.example.toml`
- `config/config.bigsign.moonbunny.example.toml` → `config/config.bigsign.firebird.example.toml`
- `docs/site/public/showcase/moonbunny/` → `docs/site/public/showcase/firebird/` (incl.
  `placeholder.svg`); update `showcase.mdx` `img src` + the `## moonbunny` heading + alt text.
- Update referrers: `.dockerignore`, `README.md` (config-name mentions), and
  `tests/test_app.py::test_moonbunny_bigsign_config_widgets_build` — rename the test +
  the `config.moonbunny.example.toml` path it loads to `config.firebird.example.toml` (this test
  loads the config and builds every widget; keep that behavior, keep the licensed-font skip note).

## Group C — LEAVE (historical record)

Do NOT rewrite dated `docs/superpowers/plans/**`, `docs/superpowers/specs/**`,
`docs/superpowers/walkthroughs/**`. They reference the brand as written at the time; rewriting
falsifies the record. (Optionally a one-line note in CONTRIBUTING/showcase that historical plans
predate the anonymization — nice-to-have, not required.)

## Traps & cross-cutting rules

- **"pole" false-positive.** `barber-pole` / `candy-cane` are BORDER styles
  (`src/led_ticker/borders.py`, `borders.mdx`). Several demos contain BOTH Moon Bunny copy AND a
  barber-pole border (`two_row-asymmetric`, `two_row-brand-handle`, `two_row-hires-emoji`, the
  tutorials). In those files rewrite the brand copy but **leave `"pole"` in the border config
  untouched.** Never blanket-replace "pole".
- **Snippet/GIF parity (DOCS-STYLE §4, hard rule).** A `demos-pinned`/`demos-long` TOML and the
  `.mdx` snippet that quotes it must change **together, character-for-character**. Any pinned demo
  whose visible copy changes must have its GIF **re-rendered** (`make render-demo`) and the new
  asset committed; otherwise the picture and the snippet diverge. Flag any demo that needs a
  re-render (esp. the `two_row` brand/handle ones + `message-brand-color`/`message-gradient`).
  If a GIF can't be re-rendered (missing fonts/assets), say so rather than letting it drift.
- **No `___ for Every(body)` / "Find Your ___" slogans** (§6) — those echo Moon Bunny; use the
  §6 copy.

## Completeness guard (new tripwire)

Add a test (e.g. `tests/test_no_real_brand.py`) that greps the tracked tree and asserts **zero**
occurrences of `moonbunny`, `moon bunny`, `moonbunnyaerial`, or `aerial` (case-insensitive)
**outside** `docs/superpowers/` (archival) and outside this spec file — so the rename is provably
complete and a future edit can't reintroduce the real brand. (Scope the allow-list to
`docs/superpowers/**` + this design doc.) This is the rename's correctness anchor.

## Testing / verification

- `tests/test_no_real_brand.py` passes (the completeness guard).
- Full suite green: `PYTHONPATH=tests/stubs uv run pytest` — esp. the renamed
  `test_firebird_bigsign_config_widgets_build` (loads `config.firebird.example.toml`), and the
  updated `@firebird*` fixtures in `test_pixel_emoji`/`test_gif_path_resolution`/`test_gif`/
  `test_two_row`.
- `ruff check` + `ruff format` clean (the test files).
- Docs: `make docs-build` + `make docs-lint` clean; every touched `.mdx` re-reviewed against the
  DOCS-STYLE §3 rubric (the technical-writer review loop, §5).
- Any re-rendered demo GIF committed; snippet/GIF parity holds.

## Non-goals / deferred

- **The richer Firebird showcase example** (from the deleted production config) — step 3.
- **Git-history scrub** — open-source-prep follow-up (decision 2). Track it.
- **The local `.claude/settings.local.json` WebFetch pin** — local cleanup, not this PR.

## Constraints

- No `from __future__ import annotations` in `src/` (n/a here — tests only).
- `asyncio_mode = "auto"`.
- Docs: never pipe `docs-lint` to `tail` (DOCS-STYLE §4 gotcha); run `docs-format` then re-lint.
- Repo is pre-open-source — no "legacy/deprecated/backward-compat" framing in any rewritten copy
  (DOCS-STYLE principle 17).
