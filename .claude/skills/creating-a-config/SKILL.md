---
name: creating-a-config
description: Use when a user wants to build, extend, or refine a led-ticker config.toml — handles "new config from scratch", "add a widget to my config", or "tune what's already there". Knows the bigsign vs smallsign tradeoffs, widget/transition catalogs, and the CLAUDE.md gotcha list.
---

# Creating a led-ticker Config

You are guiding the user through building or modifying a `config/config.toml` for the led-ticker. There are three modes: **new**, **add**, **refine**.

## Step 0: Detect mode

Determine the user's intent:

- `new` — user said "build a config" / "make a sign" / similar. OR no `config/config.toml` exists.
- `add` — user said "add a widget" / "add a section". `config/config.toml` exists.
- `refine` — user said "looks too small" / "too fast" / "fix the colors". `config/config.toml` exists.

If ambiguous, ask:
> "Are you starting fresh, adding to an existing config, or tuning what's already there?"

Announce: "Using creating-a-config skill in **\<mode\>** mode."

## TOML structure reminder (all modes)

Every config has this skeleton:

```toml
[display]
rows = 32
cols = 64
chain = 8
default_scale = 4
# ... hardware knobs

[title]
delay = 5

[transitions]
default = "push_left"
duration = 0.5
easing = "ease_in_out"
between_sections = "dissolve"

# Each section is an array entry:
[[playlist.section]]
mode = "slideshow"     # or "ticker" or "one_at_a_time"
hold_time = 6
loop_count = 1

[playlist.section.title]   # optional title card
type = "message"
text = "Weather"
color = [255, 150, 190]

[[playlist.section.widget]]   # one or more widgets per section
type = "weather.current"
location = "Brooklyn"
units = "imperial"

[[playlist.section.widget]]   # additional widgets allowed
type = "message"
text = "More info"
```

The skill produces configs in THIS structure. Never use top-level `[section_name]` headers in place of `[[playlist.section]]`.

---

## `new` mode (3-phase wizard)

### Phase 1: Outline

Load `references/hardware-guide.md`.

Ask these 7 questions, one at a time. Use multi-choice format where listed.

1. **Sign target:** small (160×16) / bigsign (256×64)
   *(Note: "both" is reserved for future parallel-config support; if the user picks both, explain that's not yet supported and ask them to pick one.)*
2. **Use case category:** store window / personal feed / event countdown / sports scoreboard / art piece / mixed
3. **Viewing distance:** close (≤6ft) / medium (6–20ft) / far (20ft+)
   *(Drives default font sizes — consult `references/hardware-guide.md` distance table.)*
4. **Content sources** (multi-select): rss / weather / custom messages / gifs+images / sports / crypto / countdown
5. **Brand presence:** none / colors only / colors+fonts / colors+fonts+logo
6. **Tone:** minimal / playful / info-dense / branded-pro
7. **Cadence:** always-on continuous loop / scheduled windows

After all 7 answers, propose a section list. Load `references/snippets.md`; look up snippets keyed by (use_case × content_source × sign_target); produce one section per content source. Present to the user as section names with widgets, e.g.:

```
Proposed sections:
  Section 1 (mode=ticker):      welcome banner — message widget
  Section 2 (mode=slideshow):   weather — weather widget
  Section 3 (mode=slideshow):   handle — two_row widget
  Section 4 (mode=slideshow):   hours countdown — countdown widget
```

User confirms or edits the list (add / remove / reorder).

### Phase 2: Per-section pass

Load `references/snippets.md`, `references/widget-selection.md`, `references/asset-handling.md`, `references/decision-rules.md`. For each chosen widget's options (field names, types, defaults), read its fact-pack `docs/content-source/widgets/<type>.md` — that is the source of truth for params; author TOML from it.

**Brand font defaults (carried across all sections):**

If Phase 1 brand presence was `colors+fonts` or `colors+fonts+logo`, the user has already named one or more font files (collected per `references/asset-handling.md`). Pick a per-tier default font_size from the asset-handling viewing-distance table BEFORE entering the per-section loop, e.g. medium-distance bigsign + Inter-Bold → 22. Use this as the default for every text-bearing widget (message, countdown, two_row, weather, image/gif overlay text, plus `[playlist.section.title]` blocks). Don't re-ask per section.

Sections-pass loop — for each confirmed section in the outline:

1. Look up the snippet matching (use_case × widget × sign_target) in `references/snippets.md`.
2. Ask only the widget-specific questions the snippet's "must customize" list requires. Use AskUserQuestion. **If the user picked a custom brand font in Phase 1, also append `font` / `font_size` / `font_threshold` to every text-bearing widget in this section even if the snippet's must-customize list omits them** — the snippets are pre-fonts and need the brand applied.
3. For asset-bearing sections (gif, image, custom font): collect assets per `references/asset-handling.md`. Place fonts in `config/fonts/<file>` and images in `config/assets/<file>`. Verify the path exists before referencing it in TOML. Never fetch URLs silently.
4. Write the section's TOML to the in-progress config buffer using the `[[playlist.section]]` / `[[playlist.section.widget]]` structure. If the section has a `[playlist.section.title]` and brand fonts are in play, apply the brand font to the title too.
5. Run per-section lint: run `led-ticker validate config/config.toml --json` and surface any `errors` or `warnings` from the output as flag-and-ask items, citing each `rule` and `fix` field. Then check font-size vs viewing distance (see step 5a below) and any remaining issues from `references/decision-rules.md` not caught by the validator.

   **Additionally** check font-size vs viewing distance: if Phase 1 distance was `medium` and the user picked a `font_size ≥ 24`, OR distance was `far` and `font_size < 22`, flag with: "Phase 1 distance was <X>; recommended `font_size` is <range>; you picked <N>. Want me to align with the recommendation?" Cite `references/asset-handling.md` viewing-distance table.

6. Brief "looks good?" before moving to the next section.

### Phase 3: Polish

Load `references/transition-selection.md`, `references/decision-rules.md`. For each transition family's catalog and tuning (durations, easing, sweep colors), read its fact-pack `docs/content-source/transitions/<family>.md` (`push`, `wipe`, `sprite`, `special`).

Ask these questions (5–7 total, condensed where possible):

1. **Default transition + duration + easing** — offer 3 picks based on Phase 1 tone. Consult the "Selecting a transition" table in `references/transition-selection.md`:
   - Minimal → `cut` or `wipe_left`
   - Playful → `nyancat.alternating` or `pokeball.alternating`
   - Info-dense → `push_up` or `wipe_up`
   - Branded-pro → `wipe_alternating` with `transition_color` from the brand palette
2. **`between_sections` transition** — usually different from the default; suggest `dissolve` for branded-pro, `cut` for minimal.
3. **Default `hold_time`** — defaults: continuous loop → 5s, scheduled windows → 10s.
4. **Brightness** — defaults: small=60, bigsign=60; ask if user wants different.
5. **Bigsign refresh tuning** — only ask if sign=bigsign AND tone=info-dense. Suggest `pwm_bits = 8` — the RIO backend is the library default, no knob needed (consult `references/hardware-guide.md` refresh tuning notes).
6. **Save destination** — propose `config/config.<descriptive-slug>.toml` based on Phase 1 answers (e.g. `firebird-bigsign`, `office-rss-small`); ask if user wants to override. After write, ask: "Activate this as the live config? (copies to `config/config.toml`, backs up any existing to `config/config.toml.bak`)"

Run final validation: run `led-ticker validate config/config.toml --json`. Surface all `errors` as mandatory fixes and `warnings` as flag-and-ask before writing. Also do a full pass over `references/decision-rules.md` for any issues not caught by the validator.

Write the file with all three top-level blocks (`[display]`, `[title]`, `[transitions]`) plus all the `[[playlist.section]]` entries.

Print:
- Path written (and whether it is the live config or a named alternate)
- Test command: `make test`
- Hardware run command: `docker compose up` (verify against `Makefile` / `compose.yaml`)
- Any flagged-but-unfixed violations from validation

---

## `add` mode

Load `references/widget-selection.md`, `references/snippets.md`, `references/asset-handling.md`, `references/decision-rules.md`. For each chosen widget's options, read its fact-pack `docs/content-source/widgets/<type>.md` — the source of truth for params.

1. Read `config/config.toml`. Extract: sign target (from `default_scale` + display dims), brand colors (from `bg_color` / common `font_color` values), default transition / hold / easing, existing sections list. Also **infer use_case** from existing widgets — e.g., presence of the `baseball.scores` / `baseball.standings` plugin widgets (`led-ticker-baseball`) → `sports`; multiple `rss.feed` + `weather.current` → `personal_feed`; a single `gif`/`image` filling the panel → `art`; mixed content with brand colors + handle → `store_window`. The inferred use_case drives snippet lookup in step 3. If you're not confident, ask the user: "I'm reading this as a <X> config — does that match?"
2. Ask: "What kind of section do you want to add?" — multi-select from `references/widget-selection.md`.
3. For each chosen widget: same flow as `new` Phase 2 — look up the snippet by (inferred-use_case × widget × sign) in `references/snippets.md`, ask the snippet's "must customize" questions, collect any assets, write the section TOML, run per-section lint.
4. Ask: "Where to insert?" — end / before \<section N\> / after \<section N\>.
5. Show full diff. First in-place edit per session creates `config/config.toml.bak` (overwrites any prior `.bak` without prompting).
6. Apply edit only on user approval.

No Phase 3 — global `[transitions]` and `hold_time` are not re-asked. The new section gets its own `transition` / `transition_color` from the chosen snippet (snippets often pin a per-section transition); for everything not set on the new section, the existing global `[transitions]` config applies.

---

## `refine` mode

Load `references/decision-rules.md`, `references/widget-selection.md`, `references/transition-selection.md`.

1. Read `config/config.toml`. Run `led-ticker validate config/config.toml --json` and cache the output as the base violation list (`errors` and `warnings` from the JSON). Also run a full pass over `references/decision-rules.md` for any issues not yet caught by the validator.
2. Ask one symptom-style multi-select question:
   - "Too small to read at viewing distance"
   - "Too aggressive / busy"
   - "Too slow / too much dead time"
   - "Too fast / can't read it"
   - "Wrong colors / bad contrast"
   - "Image fit looks bad"
   - "Border / animation feels off"
   - "Other (free text)"
3. For each selected symptom, map to specific deltas using this table:

   | Symptom | Inspect | Propose |
   |---------|---------|---------|
   | Too small at far + bigsign + currently BDF | `font` field on text widgets | Hires Inter at `font_size = 24–32` (consult `references/asset-handling.md` distance table). Migrate from BDF default. |
   | Too small + already hires | `font_size` value | Bump `font_size` up one tier (16→22, 22→28, 28→32). |
   | Too aggressive / busy | `font_color`, `border`, transitions | Swap per-char `rainbow` → `color_cycle`. Replace `wipe_alternating` / `nyancat.alternating` → `cut` or `wipe_left`. Lengthen `hold_time` by 50%. Drop animated `border` to constant or remove. |
   | Too slow / too much dead time | `hold_time`, `transition_duration` | Reduce `hold_time` by 30–50%. If `transition_duration > 1000`, drop to 600. Consider `cut` for inter-widget transitions. |
   | Too fast / can't read it | `hold_time`, `transition_duration` | Raise `hold_time` by 50%. If using fast transitions (`cut`, `push_left` at 400ms), bump duration to 800ms or swap to a wipe. |
   | Wrong colors / bad contrast | `bg_color` vs `font_color` luminance | If both colors are light or both are dark, adjust one for contrast (rough luminance heuristic: sum of RGB channels; push them apart). For brand-locked colors, propose adding a `border` for separation. |
   | Image fit looks bad + `fit="stretch"` + non-matching aspect | `fit`, image dimensions | Propose `fit="pillarbox"` (image wider than panel) or `fit="letterbox"` (image taller than panel) per `references/asset-handling.md` decision tree. Add `image_align` if pillarboxing. |
   | Border / animation feels off | `border.speed`, `border.char_offset`, `border.thickness`, `animation` | If border feels too fast: lower `speed` (default 4 on bigsign; try 2). Too uniform: raise `char_offset`. Too thin from far: increase `thickness` from 1 to 2. Typewriter feels off-pace: tune `frames_per_char` (default 3; raise for slower reveal). |

4. After addressing stated symptoms, surface the step-1 violation list as flag-and-ask. Each item: "I also noticed: \<rule violation\> (severity) — want me to fix? Per `references/decision-rules.md` rule N."
5. Show each proposed delta as a unified diff. User approves per delta.
6. Apply approved edits. First in-place edit per session backs up to `config/config.toml.bak` (overwrites any prior `.bak` without prompting).

---

## Validation: flag-and-ask philosophy

The skill **never silently auto-fixes a violation.** Every flag is presented to the user with the rule cited (`per references/decision-rules.md rule N`). The user decides whether to apply the fix. This applies in all three modes at all three checkpoints:

1. Per-section lint (Phase 2 of `new`, or per-section in `add`)
2. Phase 3 final validation (assembled config, `new` mode only)
3. Symptom + catch-all flag-and-ask (`refine` mode)
