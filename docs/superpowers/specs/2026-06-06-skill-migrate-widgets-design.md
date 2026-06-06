# Config-skill migration 4/5 — widgets — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorm)

## Context

Fourth of five sub-pieces in the config-skill fact-pack migration (memory `project_config_skill_factpack_migration`). The agreed architecture is a **split**: shared reference data → `content-source/` fact-packs (also consumed by the docs site); skill-procedural knowledge → the skill's own `references/`. Sub-pieces 1–3 (decision-rules #170, hardware-guide #171, asset-handling #172) were clean verbatim moves of pure-procedural content.

Widgets is **the first true reconciliation piece**, and the shape is the opposite of what the migration originally assumed.

## Finding from exploration

`docs/content-source/widgets-legacy.md` (319 lines, 12 core widgets + a trailing emoji reference) is **not richer than the per-page fact-packs** — it has **drifted and is partly wrong**. The per-page fact-packs (`docs/content-source/widgets/*.md`, 13 files incl. `pool`) are now both **richer** (full two-row / wrap / separator option coverage) and **more correct**:

- **`gif` widget:** legacy documents `gif_loops`; the field was renamed to `play_count` and `gif_loops` is **rejected at config-load** (`src/led_ticker/app/factories.py:640`). The fact-pack `gif.md` correctly documents `play_count`.
- **`image` widget:** legacy documents `hold_seconds`; the real field is `hold_time` (`src/led_ticker/widgets/still.py:139`, floor `>= 0.05`). This is the same bug the docs-site sweep fixed everywhere else — it was never fixed in `widgets-legacy.md`. The fact-pack `image.md` correctly documents `hold_time`.

So if the skill keeps sourcing widget params from the legacy guide, it can emit configs that fail to load. The fix is to stop using the legacy param lists and read the fact-packs instead.

What the legacy guide has that the fact-packs do **not** is **skill-procedural selection knowledge** — each widget's **Purpose**, **When to use**, and selection-relevant **Gotchas**. The wizard needs this for the `add`-mode "what kind of section?" multi-select and for picking widgets in `new` Phase 2. The OptionsTable fact-packs carry only option/type/default/description rows, not selection framing.

## The split for widgets

- **Option/param details (shared, docs-site-consumed):** already live correctly in `docs/content-source/widgets/<type>.md`. The skill reads those for params. The two bugs vanish because the skill stops sourcing params from the stale legacy lists.
- **Skill-procedural selection knowledge:** move each legacy widget's Purpose / When to use / selection Gotchas into a **new single file `.claude/skills/creating-a-config/references/widget-selection.md`** — a compact per-widget selection guide (one entry per widget; no param tables). One consolidated file, because the wizard reads it once for the multi-select.
- **Delete `widgets-legacy.md`:** its param lists are stale/buggy (dropped, not migrated). Its trailing "Inline Emoji Reference" already lives in `docs/content-source/emoji.md` (SKILL.md does not reference that section).

## Deliverable

1. **Create `references/widget-selection.md`** — a "Widget Selection Guide" with one entry per core widget (the 12 in the legacy catalog: `message`, `countdown`, `two_row`, `weather`, `rss_feed`, `mlb`, `mlb_standings`, `gif`, `image`, `crypto.coinbase`, `crypto.coingecko`, `crypto.etherscan`). Each entry = **Purpose** (one line), **When to use** (the legacy bullets), and **Selection notes** (only the legacy Gotchas that bear on *whether/when to pick the widget* — e.g. countdown is day-resolution only; two_row needs a tall canvas; weather needs `WEATHERAPI_KEY`; mlb has no key but mlb cadence; etherscan needs an API key). Drop param-mechanics gotchas (those are option-table / decision-rules / validate.py territory). A short header states: **for option/parameter details, read `docs/content-source/widgets/<type>.md`**. Add a one-line pointer to `pool` (plugin) directing to its fact-pack, so the catalog matches the 13 fact-packs.
2. **Repoint SKILL.md (4 refs):**
   - Phase 2 load (line ~101) and `add` load (line ~150): replace `docs/content-source/widgets-legacy.md` with `references/widget-selection.md` (for selection) **and** add an instruction to read the specific `docs/content-source/widgets/<type>.md` fact-pack for each chosen widget's options.
   - `add` multi-select (line ~153): "multi-select from `references/widget-selection.md`".
   - `refine` load (line ~165): replace `widgets-legacy.md` with `references/widget-selection.md`.
3. **`git rm docs/content-source/widgets-legacy.md`.**
4. **No docs-site change** — the site consumes the per-page fact-packs, not the legacy file.

## Out of scope

- Sub-piece 5/5 (transitions) — its own spec→plan→PR.
- Rewriting or re-verifying the fact-packs (they were correctness-swept during the docs effort). This piece only *adds* the selection guide and *deletes* the legacy file.
- Changing `snippets.md` (the "must customize" lists stay there).

## Verification

- New `references/widget-selection.md` has an entry for all 12 core widgets + the header pointing at `content-source/widgets/<type>.md` + a `pool` pointer.
- **The selection guide contains no `gif_loops` and no `hold_seconds`** (the drift bugs are not carried forward) — grep clean.
- No `widgets-legacy` references remain outside `docs/superpowers/`.
- SKILL.md references `references/widget-selection.md` and `docs/content-source/widgets/` (fact-pack dir); `widgets-legacy` 0×.
- Legacy file deleted; no change under `docs/site/src/`.
- Skill content has no automated test and skips CI's Python jobs — verify by grep + read-through. `make docs-lint` still clean (legacy file deletion + spec/plan under docs/ trigger it).
