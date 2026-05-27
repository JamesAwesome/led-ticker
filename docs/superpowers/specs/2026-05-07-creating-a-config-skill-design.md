# Design: `creating-a-config` Local Skill

**Date:** 2026-05-07
**Status:** Approved (brainstorming)

## Overview

A repository-local Claude Code skill that guides users through building, extending, or refining a `led-ticker` TOML config. It encodes the bigsign/smallsign decision matrix, the widget/transition catalogs, and the gotchas already documented in `CLAUDE.md` so users don't have to re-derive them. The skill ships as `.claude/skills/creating-a-config/SKILL.md` plus a `references/` subdirectory.

The skill operates in three modes — **new**, **add**, **refine** — dispatched at invocation based on user intent and current repo state.

## Goals

- Help any user (the repo owner or a fresh cloner) get from "I want a sign that does X" to a working `config/config.toml` without reading every line of `CLAUDE.md` first.
- Encode the small-vs-big sign tradeoffs so the skill picks the right defaults instead of asking the user about every knob.
- Reuse the existing 27+ example configs as a snippet library — never reinvent a working block.
- Surface CLAUDE.md gotchas (content_height ceiling, font_threshold matching, scroll+stretch invalid combinations, etc.) at the right moment, not retroactively after the user runs the sign.
- Stay safe: never silently overwrite `config/config.toml`.

## Non-Goals

- Not a TOML schema validator. The skill consults `references/decision-rules.md` for known gotchas; it does not exhaustively check every field.
- Not a hardware diagnostic. If the sign isn't displaying anything, that's outside this skill's scope.
- Not a replacement for the example configs themselves. Examples remain authoritative; the skill's `snippets.md` indexes them.
- No silent network fetches. If a user references an asset by URL, the skill asks them to download it locally and provide the path.

## Skill Layout

```
.claude/skills/creating-a-config/
  SKILL.md                          # mode dispatch + 3-phase orchestration
  references/
    hardware-guide.md               # smallsign vs bigsign decision matrix
    widgets.md                      # widget catalog (per-widget params + when-to-use)
    transitions.md                  # transition catalog with hardware variants & mood mapping
    snippets.md                     # blessed config snippets indexed by (use_case × widget × sign)
    asset-handling.md               # brand colors / fonts / images / URLs ingest rules
    decision-rules.md               # gotchas & validation rules from CLAUDE.md
```

The skill loads only the references it needs per phase to keep the active context lean:

| Phase / Mode | References loaded |
|--------------|-------------------|
| `new` Phase 1 (outline) | `hardware-guide.md` |
| `new` Phase 2 (per-section) | `snippets.md`, `widgets.md`, `asset-handling.md`, `decision-rules.md` |
| `new` Phase 3 (polish) | `transitions.md`, `decision-rules.md` |
| `add` mode | `widgets.md`, `snippets.md`, `asset-handling.md`, `decision-rules.md` |
| `refine` mode | `decision-rules.md`, `widgets.md`, `transitions.md` |

### `SKILL.md` frontmatter

```yaml
---
name: creating-a-config
description: Use when a user wants to build, extend, or refine a led-ticker config.toml — handles "new config from scratch", "add a widget to my config", or "tune what's already there". Knows the bigsign vs smallsign tradeoffs, widget/transition catalogs, and the CLAUDE.md gotcha list.
---
```

The description advertises all three modes (new / add / refine) so the Skill tool fires for any of them.

## Mode Dispatch

At skill entry, the skill picks one of three modes:

| Mode | Trigger | What it does |
|------|---------|--------------|
| `new` | User says "build a config" / "make a sign" — OR no `config/config.toml` present | Full 3-phase wizard |
| `add` | User says "add a widget" / "add a section" — and `config/config.toml` exists | Reads existing config to inherit sign target/brand, condensed wizard for the new section, inserts it |
| `refine` | User says "looks too small" / "too fast" / "fix the colors" — and `config/config.toml` exists | Reads existing config, asks symptom-style questions, proposes per-issue deltas with edit diffs |

If intent is ambiguous, the skill asks a single disambiguation question:
> "Are you starting fresh, adding to an existing config, or tuning what's already there?"

## `new` Mode — 3-Phase Wizard

### Phase 1 — Outline (7 questions)

The skill asks these in order. Each question is multi-choice where possible. Answers feed the section-list proposal.

1. **Sign target:** small (160×16) / bigsign (256×64) / both (parallel configs)
2. **Use case category:** store window / personal feed / event countdown / sports scoreboard / art piece / mixed
3. **Viewing distance:** close (≤6ft) / medium (6–20ft) / far (20ft+) — drives default font sizes
4. **Content sources** (multi-select): rss / weather / custom messages / gifs+images / sports / crypto / countdown
5. **Brand presence:** none / colors only / colors+fonts / colors+fonts+logo
6. **Tone:** minimal / playful / info-dense / branded-pro
7. **Cadence:** always-on continuous loop / scheduled windows (only affects `mode` choices and outer scheduling)

After Q&A, the skill proposes a section list with one widget per section, derived from `references/snippets.md` lookups keyed by (use_case × content_source × sign_target). Example output:

```
Proposed sections:
  [hello]      message       "Welcome to Moon Bunny"
  [weather]    weather       Brooklyn
  [handle]     two_row       @MoonBunnyBakery / hello@…
  [hours]      countdown     to close
```

User confirms or edits the list (add / remove / reorder a section by name).

### Phase 2 — Per-Section Pass

For each confirmed section, the skill:

1. Looks up the matching snippet in `references/snippets.md` keyed by (use_case × widget × sign_target).
2. Asks widget-specific questions only — what the snippet says "must customize". E.g.:
   - `weather`: location, units, icon yes/no
   - `gif`: file path, fit mode, text overlay yes/no
   - `two_row`: top text, bottom text, top color, bottom color
3. For asset-bearing sections, collects assets per `references/asset-handling.md` (see Asset Placement below).
4. Writes the section's TOML to the in-progress config.
5. Runs a per-section lint against `references/decision-rules.md` (font_size missing on hires, scroll+stretch invalid, etc.).
6. Brief "looks good?" before moving to the next section.

### Phase 3 — Polish (5–7 questions)

1. **Default transition + duration + easing** — skill offers 3 picks based on Phase 1 tone. (Minimal → `cut` / `wipe_left`; playful → `nyancat_alternating` / `pokeball_alternating`; info-dense → `push_up` / `wipe_up`; branded-pro → `wipe_alternating` with `transition_color` from brand palette.)
2. **`between_sections` transition** — usually different from per-section.
3. **Default `hold_time`** — defaults derive from cadence (continuous → shorter; scheduled → longer).
4. **Brightness** — defaults: small=60, big=80; ask if user wants different.
5. **Bigsign-only refresh tuning** — only asked if sign target is bigsign and user picked "info-dense" tone (suggests `pwm_bits = 8`, `rp1_rio = 1`).
6. **Save destination** — default `config/config.<descriptive-slug>.toml`; asks before touching `config/config.toml` (see Output Handling).

After Phase 3, the skill assembles the full config, runs final validation (full pass over `references/decision-rules.md`), writes the file, prints a "next steps" summary (test command, deploy command).

## `add` Mode

1. Skill reads existing `config/config.toml`. Extracts: sign target (from `default_scale` and panel dimensions), brand colors (from `bg_color` / common `font_color` values), default transition / hold / easing, existing sections list.
2. Skips Phase 1. Asks one question: **"What kind of section do you want to add?"** — multi-select against `references/widgets.md`.
3. For each chosen widget: same Phase 2 flow as `new` mode (snippet + widget-specific Qs + asset collection + per-section lint).
4. Asks where to insert: end / before [section name] / after [section name].
5. Edits the file in place. Shows the diff before saving. First in-place edit per session creates `config/config.toml.bak`.
6. No Phase 3 — the new section inherits global transitions/holds from existing config.

## `refine` Mode

1. Skill reads existing `config/config.toml`. Runs full validation pass against `references/decision-rules.md` to catalog any pre-existing violations (used in step 4).
2. Asks one symptom-style multi-select question:
   - "Too small to read at viewing distance"
   - "Too aggressive / busy"
   - "Too slow / too much dead time"
   - "Too fast / can't read it"
   - "Wrong colors / bad contrast"
   - "Image fit looks bad"
   - "Border / animation feels off"
   - "Other (free text)"
3. For each selected symptom, the skill consults `references/decision-rules.md` to map symptom → likely cause → specific delta. Examples:
   - "Too small at far viewing distance" + bigsign + currently using BDF → propose hires Inter at `font_size = 24-32`
   - "Too aggressive" → reduce per-char rainbow to `color_cycle`, lengthen `hold_time`, swap `wipe_alternating` → `cut`
   - "Image fit looks bad" + `fit = "stretch"` + non-matching aspect → propose pillarbox/letterbox + `image_align`
4. After addressing stated symptoms, the skill applies **flag-and-ask** for any other violations found in step 1: presents each one as "I also noticed: X (severity) — want me to fix?" The user opts in per item. Hard violations (e.g. content_height ceiling exceeded) get the same flag-and-ask treatment as style issues — no silent auto-fixes.
5. Each proposed delta shown as a unified diff. User approves per delta. Skill applies approved edits; rejects are skipped.
6. First in-place edit per session creates `config/config.toml.bak`.

## Output Handling

| Mode | Default destination | Behavior |
|------|---------------------|----------|
| `new` | `config/config.<slug>.toml` | Slug derived from Phase 1 answers (e.g. `moonbunny-bigsign`, `office-rss-small`, `mets-bigsign`); skill proposes one and lets user override. After write, asks: "Activate this as the live config? (copies to `config/config.toml`, backs existing up to `config/config.toml.bak`)" |
| `add` | edits `config/config.toml` in place | Shows full diff before write. Backup to `config/config.toml.bak` only on first edit per session. |
| `refine` | edits `config/config.toml` in place | Same diff + backup behavior as `add`. Each proposed delta shown separately so user can accept/reject per-issue. |

The skill never silently overwrites `config/config.toml`.

**Backup behavior:** `.bak` is a session-level safety net, not a versioned backup. If `config/config.toml.bak` already exists from a prior session, it is overwritten without prompting. Users who want long-term history should rely on git, not the `.bak` file.

## Asset Placement

| Asset type | Lands at | Skill's responsibility |
|------------|----------|------------------------|
| Brand colors | (not a file) inlined as `[r,g,b]` in TOML | Convert hex → RGB; suggest application sites (font_color / bg_color / transition_color / border / top_color / bottom_color) |
| Custom font (`.ttf` / `.otf`) | `config/fonts/<file>` (flat directory, no family subdir) | Move/copy file into place; pick `font_size` by viewing distance; apply within-family `font_threshold` matching rule from CLAUDE.md (e.g. Beloved Sans Regular needs threshold=80; match Bold to Regular's threshold) |
| Image / GIF | `config/assets/<file>` | Move/copy file; if needed, run a quick Pillow probe for native dimensions to recommend `fit`; validate aspect against panel ratio; warn on `text_align="scroll"` + `fit="stretch"` |
| URLs / handles | (not a file) inlined as TOML fields | Map handle → widget field. `:instagram:` / `:email:` slug recognition for `two_row`. Weather location → weather widget. MLB team → mlb widget. Crypto pair → crypto widget. RSS URL → rss widget. |

If user provides an asset path: skill verifies the file exists, then copies/moves it into the canonical location.

If user provides a URL: skill asks them to download manually and provide the path. No silent network fetches.

## Validation Strategy — Three Checkpoints

Validation is **flag-and-ask** at every checkpoint. The skill never silently auto-fixes a violation; it surfaces the rule and the user decides.

1. **Per-section lint (Phase 2)**: After writing each section, quick lint against `references/decision-rules.md` for per-widget gotchas (font_size missing on hires, scroll+stretch invalid, scale=4 + content_height>16, font_threshold mismatch within family).
2. **Phase 3 final validation (`new` mode)**: Full pass over the assembled config; surface anything found before write.
3. **`refine` mode flag-and-ask**: When reading existing config, run the same validation and surface unrelated issues alongside the symptoms the user mentioned.

## `references/` Contents

### `references/hardware-guide.md`

Short table-driven document. Sections:
- **Small sign (160×16, scale=1)**: BDF only, no hires anything (fonts / transitions / emoji are no-ops or invalid), 1px border max, viewing distance ≤10ft realistic.
- **Bigsign (256×64, scale=4)**: hires fonts/transitions/emoji available, **content_height ≤ 16** (hard ceiling: `content_height × scale ≤ panel_h_real`), scale=2 for handle layouts (TwoRow), scale=4 for headlines.
- **Viewing distance heuristics**: close → BDF FONT_DEFAULT (6×12) OK on either sign; medium → bigsign + hires Inter @ 16-22; far → bigsign + hires Inter @ 24-32.
- **Refresh tuning notes (Pi 5 / bigsign only)**: `pwm_bits = 8` for ~8× faster refresh, `rp1_rio = 1` for RIO mode, `gpio_slowdown` raise to 3+ if flicker.

### `references/widgets.md`

One section per widget. For each widget: 1-line purpose, when-to-use bullet, key TOML params, gotchas, pointer to relevant snippet IDs. Covers:

`message`, `countdown`, `weather`, `rss`, `two_row`, `mlb`, `mlb_standings`, `gif`, `image`, crypto family (`coinbase`, `coingecko`, `etherscan`).

### `references/transitions.md`

Grouped by family:
- **Push** (rapid scroll): push_left / push_right / push_up / push_down / push_alternating / push_random
- **Wipe** (sweep line): wipe_left / wipe_right / wipe_up / wipe_down / wipe_alternating / wipe_random / dissolve / split
- **Instant**: cut / color_flash
- **Sprite**: nyancat / pokeball / baseball / pacman / sailor_moon (and *_reverse / *_alternating variants)
- **Special**: scroll (seamless continuous)

For each: which sign (small / big / both), hires variant on bigsign (yes/no), mood/tone fit, recommended `transition_duration` range. Plus the `transition_specified` precedence note (TOML `transition = "..."` is used for both inter-section ENTRY and inter-widget transitions).

### `references/snippets.md`

The snippet catalog. Each entry:

```
### snippet: weather.bigsign.brand
  source: config/config.showroom-bigsign.example.toml lines 45-62
  use when: bigsign + brand presence + weather requested
  must customize: location, font_color (brand), font_color_temp
  copy verbatim:
  [weather]
  type = "weather"
  ...
```

~20-30 snippets covering combinations of (use_case × widget × sign_target). Indexed at the top of the file by `(use_case, widget, sign_target)` triples for fast lookup.

### `references/asset-handling.md`

Per-asset-type ingest playbook. Sections:
- **Brand colors**: hex-to-RGB conversion, decision tree for "where does this color go" (background tone vs accent color vs transition flash).
- **Custom fonts**: placement at `config/fonts/<file>` (flat directory), `font_size` by viewing distance table, **within-family threshold matching** rule (Bold weights pair to the same `font_threshold` as Regular so weight contrast survives).
- **Images / GIFs**: placement at `config/assets/<file>`, **fit-mode decision tree** (matching aspect → stretch OR pillarbox; tall image on wide sign → pillarbox; image with text overlay → never stretch), two-row text overlay decision branch.
- **URLs / handles**: per-widget mapping table.

### `references/decision-rules.md`

The gotcha list distilled from CLAUDE.md as a quick-scan checklist. Rules in this format:

```
RULE: content_height × scale ≤ panel_h_real
SOURCE: CLAUDE.md (Per-section content_height section)
DETECT: section.content_height × default_scale > panel_height
FIX: lower content_height to (panel_height // default_scale) — 16 for bigsign at scale=4
```

Initial rule set:

- `content_height × scale ≤ panel_h_real` (hard ceiling)
- Mixing `font_threshold` within a font family inverts weight contrast (warn if Regular and Bold on same family use different thresholds)
- `text_align="scroll"` + `fit="stretch"` is invalid (no transparent regions to expose text)
- Hires emoji is a no-op on small sign / scale=1 (bigsign-only feature)
- HiresFont configs MUST specify `font_size` (loader raises otherwise)
- TwoRow at scale=4 is usually wrong for handle layouts (suggest scale=2)
- `text_x_offset != 0` invalid with scroll modes
- `hold_seconds < 0.05` invalid on image widgets
- BDF `font_size < cell_h` invalid
- Per-widget `font_threshold` must be int 0-255 (not float, not bool)
- Section transitions: explicit `transition = "..."` overrides `between_sections` for inter-section entry (precedence rule)

Used by all three validation checkpoints AND by `refine` mode for symptom-to-cause mapping.

## Smoke-Test Handoff

After writing the config, the skill prints:
- The exact path written
- Whether it's the live config or a named alternate
- Local test command (`make test`)
- Hardware run command — read from `Makefile` / `compose.yaml` / `CLAUDE.md` (probably `docker compose up`)
- Any flagged-but-unfixed violations from validation

## Files Changed

| File | Change |
|------|--------|
| `.claude/skills/creating-a-config/SKILL.md` | New — mode dispatch + 3-phase orchestration |
| `.claude/skills/creating-a-config/references/hardware-guide.md` | New |
| `.claude/skills/creating-a-config/references/widgets.md` | New |
| `.claude/skills/creating-a-config/references/transitions.md` | New |
| `.claude/skills/creating-a-config/references/snippets.md` | New |
| `.claude/skills/creating-a-config/references/asset-handling.md` | New |
| `.claude/skills/creating-a-config/references/decision-rules.md` | New |

No production code changes. No tests changed. The skill is content-only.

## Tests / Validation

The skill itself is markdown content, not code, so there's no unit test surface. Verification is:

1. **Self-walkthrough**: After writing, manually walk through `new` mode for a hypothetical "store window on bigsign" scenario and confirm the produced config is sensible (compare against `config.moonbunny.example.toml` as a known-good reference).
2. **Self-walkthrough**: Walk through `refine` mode against an intentionally-broken config (e.g. content_height=20 on bigsign + threshold-mismatched fonts) and confirm violations are surfaced.
3. **Self-walkthrough**: Walk through `add` mode against `config.example.toml` and confirm the new section is inserted cleanly.

The implementation plan should specify each walkthrough as a concrete deliverable.

## Maintenance Note

The `references/` files are **derived from CLAUDE.md** at the time the skill is written. Updates to CLAUDE.md (new widgets, new transitions, new gotchas) do not auto-propagate. When CLAUDE.md grows a new constraint, the corresponding reference file (usually `decision-rules.md`) needs a manual update.

Each reference file should include a short header comment naming its CLAUDE.md source sections so a future maintainer can spot drift quickly. Example:

```markdown
<!-- Derived from CLAUDE.md sections: "CRITICAL: Hardware Rendering Constraints",
     "Per-section content_height", "Per-widget font_threshold". Last synced: 2026-05-07. -->
```

## Open Questions / Future Work

- Whether to support `both` (parallel small + big configs) at v1 or defer. Implementation plan should call this out.
- Whether the skill should learn over time (e.g. add new snippets when user creates a particularly nice config). Out of scope for v1.
- Localization / non-English content widgets. Out of scope; widgets handle UTF-8 transparently anyway.
