# Creating-a-Config Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repository-local Claude Code skill at `.claude/skills/creating-a-config/` that guides users through new / add / refine flows for the led-ticker `config.toml`.

**Architecture:** Content-only deliverable — one `SKILL.md` orchestrator plus six reference files in `references/`. Reference files are derived from `CLAUDE.md` and the existing `config/*.example.toml` library. The orchestrator does mode dispatch (`new` / `add` / `refine`), runs a 3-phase wizard for `new`, condensed flows for `add` and `refine`, and consults references per phase.

**Tech Stack:** Markdown only. No production code. No tests. Verification is via three explicit walkthrough scenarios at the end.

**Spec:** `docs/superpowers/specs/2026-05-07-creating-a-config-skill-design.md`

---

## File Structure

**New files (all under `.claude/skills/creating-a-config/`):**

| File | Responsibility |
|------|----------------|
| `SKILL.md` | Mode dispatch + 3-phase wizard orchestration. Top-level flow control. |
| `references/hardware-guide.md` | Smallsign vs bigsign decision matrix. Loaded in Phase 1. |
| `references/widgets.md` | Per-widget catalog (purpose, params, gotchas). Loaded in Phase 2 + add + refine. |
| `references/transitions.md` | Transition catalog grouped by family. Loaded in Phase 3 + refine. |
| `references/snippets.md` | Blessed config snippets indexed by (use_case × widget × sign_target). Loaded in Phase 2 + add. |
| `references/asset-handling.md` | Asset ingest playbook (colors, fonts, images, URLs). Loaded in Phase 2 + add. |
| `references/decision-rules.md` | Gotcha checklist distilled from CLAUDE.md. Loaded for validation in every mode. |

**Per-phase loading table (from spec, repeated here for the implementer):**

| Phase / Mode | References loaded |
|--------------|-------------------|
| `new` Phase 1 (outline) | `hardware-guide.md` |
| `new` Phase 2 (per-section) | `snippets.md`, `widgets.md`, `asset-handling.md`, `decision-rules.md` |
| `new` Phase 3 (polish) | `transitions.md`, `decision-rules.md` |
| `add` mode | `widgets.md`, `snippets.md`, `asset-handling.md`, `decision-rules.md` |
| `refine` mode | `decision-rules.md`, `widgets.md`, `transitions.md` |

---

## Conventions for this plan

- Every reference file starts with a header HTML comment naming its CLAUDE.md source sections and a `Last synced:` date (per the spec's Maintenance Note). Format:
  ```markdown
  <!-- Derived from CLAUDE.md sections: <comma-separated section titles>.
       Last synced: 2026-05-07. -->
  ```
- Use Markdown tables wherever data is comparative (sign target × widget, viewing distance × font size, etc.). Tables are easier to scan than prose.
- Snippet entries follow the format shown in the spec's `references/snippets.md` section. Always cite source file + line range.
- Frontmatter uses YAML. The skill name is `creating-a-config` (no namespace prefix needed for repo-local skills).
- Cross-references between reference files use relative paths: `[snippets.md](snippets.md)`.
- Every commit on this branch starts with `skill:` per the existing `docs:`, `feat:`, `fix:` prefix convention.
- Each task ends with a commit. The branch is `feat/creating-a-config-skill` (already created).

---

### Task 1: Scaffold the skill directory + add to gitignore-allowlist

**Files:**
- Create: `.claude/skills/creating-a-config/.gitkeep` (empty placeholder)
- Modify: `.gitignore` if `.claude/skills/` is currently ignored

The repo's `.claude/` directory currently contains `settings.local.json` and `worktrees/`. Verify `.claude/skills/` is **not** in `.gitignore` so committed skills track in the repo. If `.claude/` is broadly ignored, add an explicit `!.claude/skills/` allowlist entry.

- [ ] **Step 1: Inspect current ignore state**

Run:
```bash
git check-ignore -v .claude/skills/creating-a-config/SKILL.md
```

Expected: command exits with code 1 and produces no output (path is NOT ignored). If it prints a matching ignore rule, proceed to step 2; otherwise skip to step 3.

- [ ] **Step 2: Add allowlist entry to .gitignore (only if step 1 showed ignored)**

Add this block at the end of `.gitignore`:

```gitignore
# Track repo-local Claude skills (commit them in source)
!.claude/skills/
!.claude/skills/**
```

- [ ] **Step 3: Create scaffold**

```bash
mkdir -p .claude/skills/creating-a-config/references
touch .claude/skills/creating-a-config/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/creating-a-config/.gitkeep .gitignore
git commit -m "skill: scaffold creating-a-config directory"
```

---

### Task 2: `references/hardware-guide.md`

**Files:**
- Create: `.claude/skills/creating-a-config/references/hardware-guide.md`

**Source materials:**
- `CLAUDE.md` sections: "Project Overview" (sign descriptions), "Hardware" (concrete hardware specs), "CRITICAL: Hardware Rendering Constraints", "Per-section `content_height`".
- Example configs: `config/config.example.toml` (small sign), `config/config.bigsign.example.toml` (bigsign).

**Structure (skeleton — implementer fills the data):**

```markdown
<!-- header comment -->

# Hardware Guide: Smallsign vs Bigsign

## At-a-glance comparison

| Dimension | Small sign | Bigsign |
|-----------|------------|---------|
| Pi model | ... | ... |
| Logical canvas | 160×16 | 256×64 |
| `default_scale` | 1 | 4 |
| BDF fonts | ✓ | ✓ |
| Hires TTF/OTF fonts | (overflows; user beware) | ✓ |
| Hires emoji (`:moon:`, `:instagram:`) | (falls back to lowres) | ✓ |
| Hires sprite transitions (nyancat/pokeball/baseball) | (uses lowres) | ✓ |
| `content_height` ceiling | 16 | 16 (hard: `content_height × 4 ≤ 64`) |
| Realistic viewing distance | ≤ 10 ft | up to 50 ft |
| Brightness default | 60 | 80 |

## Choosing scale (bigsign only)

- `default_scale = 4` — headline content (banners, weather, countdown). Logical 16-row content fills the panel.
- `scale = 2` per-section — handle layouts (TwoRow @MoonBunnyBakery + email). 128 logical px is wide enough for typical handles; rows are 32 real px tall.
- Never `scale = 4` for a TwoRow with a typical handle — text wraps or gets cut.

## Viewing-distance heuristics

| Distance | Sign | Recommended font |
|----------|------|------------------|
| Close (≤6 ft) | small | BDF FONT_DEFAULT (6×12) |
| Close (≤6 ft) | bigsign | BDF FONT_DEFAULT (6×12) at scale=4, OR hires Inter @ 16 |
| Medium (6–20 ft) | small | BDF FONT_DEFAULT |
| Medium (6–20 ft) | bigsign | hires Inter @ 18–22 |
| Far (20 ft+) | small | (not realistic) |
| Far (20 ft+) | bigsign | hires Inter / Inter-Bold @ 24–32 |

## Refresh tuning (bigsign / Pi 5 only)

- `pwm_bits = 8` (down from default 11) — ~8× faster refresh, minor color hit
- `rp1_rio = 1` — RIO mode, faster + more CPU. `0` for PIO mode (lower CPU).
- `slowdown_gpio = 3` — raise to 4–5 if flicker.
- Only suggest these for "info-dense" tone with many sections.

## What does NOT work where

- Hires emoji / hires fonts / hires sprite transitions are no-ops on small sign — they fall back to lowres or BDF without warning. Don't promise them on small sign.
- `content_height = 20` on bigsign at scale=4 silently clips top + bottom rows.
```

- [ ] **Step 1: Read source materials**

Read CLAUDE.md sections listed above and skim `config.example.toml` + `config.bigsign.example.toml`.

- [ ] **Step 2: Write the file using the structure above**

Fill in concrete numbers from CLAUDE.md (Pi 4 / Pi 5 model names, `slowdown_gpio` defaults, exact panel layout). Include the HTML comment header naming source sections.

- [ ] **Step 3: Validate cross-references**

Open `CLAUDE.md` and confirm every fact in the file is grounded in a CLAUDE.md statement (no inventing numbers). Spot-check 5 facts.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/creating-a-config/references/hardware-guide.md
git commit -m "skill: add hardware-guide reference"
```

---

### Task 3: `references/widgets.md`

**Files:**
- Create: `.claude/skills/creating-a-config/references/widgets.md`

**Source materials:**
- `CLAUDE.md` sections: "Package Layout" (widget list), "Inline Emoji", "Two-row widget", "GIF widget and Still-image widget", and any per-widget callouts.
- `src/led_ticker/widgets/*.py` — read each widget's docstring + attrs fields for params.
- `config/config.*.example.toml` — see real usage.

**Structure (one section per widget):**

```markdown
<!-- header comment -->

# Widget Catalog

## `message` (TickerMessage)

**Purpose:** One-line scrolling text message. The bread-and-butter widget.

**When to use:**
- Welcome banners, announcements
- Anywhere you need plain text with optional inline `:slug:` emoji
- Use with `border = "rainbow"` for attention-grabbing

**Key TOML params:**
- `text` (required): the message string. Supports `:emoji:` slugs.
- `font_color`: constant `[r,g,b]`, `"rainbow"`, `"color_cycle"`, or table `{style="gradient", from=..., to=...}`. Per-char providers sweep across emoji.
- `font` / `font_size` / `font_threshold`: optional. Required together for hires.
- `animation`: `"typewriter"` to type out characters one-by-one.
- `border`: `"rainbow"`, table `{style="rainbow", speed=N, char_offset=N, thickness=N}`, or `[r,g,b]`.
- `bg_color`: `[r,g,b]` background fill.

**Gotchas:**
- Hires fonts MUST specify `font_size` (loader raises otherwise).
- `animation = "typewriter"` is only supported on `message` — config-load raises on other widgets.
- BDF `font_size` < cell_h is invalid.

**Snippets:** see `snippets.md` for `message.<use_case>.<sign>` entries.

---

## `countdown` (TickerCountdown)

(continue same shape per widget...)
```

**Widgets to cover** (one section each, in this order):

1. `message` — TickerMessage
2. `countdown` — TickerCountdown
3. `two_row` — TwoRowMessage
4. `weather` — WeatherWidget (note: two color knobs `font_color` and `font_color_temp`)
5. `rss` — RSSFeedMonitor (note: stories expand into TickerMessages, no native draw)
6. `mlb` — MLBMonitor
7. `mlb_standings` — MLBStandingsMonitor
8. `gif` — GifPlayer
9. `image` — StillImage
10. `crypto.coinbase` — CoinbasePriceMonitor
11. `crypto.coingecko` — CoinGeckoPriceMonitor
12. `crypto.etherscan` — EtherscanGasMonitor

For each: 1-line purpose, "when to use" bullets, key TOML params, gotchas, pointer to snippet section name.

- [ ] **Step 1: Read source materials**

For each widget, read the corresponding `src/led_ticker/widgets/*.py` for the field list, plus search `CLAUDE.md` for any mention of that widget.

- [ ] **Step 2: Write the file using the structure above**

Cover all 12 widget types listed. Keep each section short — 5–10 lines.

- [ ] **Step 3: Validate widget coverage**

Run:
```bash
ls src/led_ticker/widgets/*.py | grep -v "^_" | grep -v "__init__"
ls src/led_ticker/widgets/crypto/*.py | grep -v "__init__"
```

Confirm every concrete widget file (excluding the `_` prefixed helpers) has a section in `widgets.md`.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/creating-a-config/references/widgets.md
git commit -m "skill: add widgets reference"
```

---

### Task 4: `references/transitions.md`

**Files:**
- Create: `.claude/skills/creating-a-config/references/transitions.md`

**Source materials:**
- `CLAUDE.md` section: "Transition System" (lists every transition with descriptions).
- `src/led_ticker/transitions/*.py` — read each module's `@register_transition` calls.
- Spec section `references/transitions.md`.

**Structure:**

```markdown
<!-- header comment -->

# Transition Catalog

## Selecting a transition

| Tone | Suggested transitions |
|------|----------------------|
| Minimal | `cut`, `wipe_left`, `wipe_right` |
| Playful | `nyancat_alternating`, `pokeball_alternating`, `pacman_alternating` |
| Info-dense | `push_up`, `wipe_up`, `dissolve` |
| Branded-pro | `wipe_alternating` with brand `transition_color`, `cut`, `color_flash` |

## Family: Push (rapid scroll, both sides move)

| Name | Direction | Hires variant on bigsign |
|------|-----------|--------------------------|
| `push_left` | outgoing → left, incoming ← right | (no hires variant) |
| `push_right` | ... | ... |
| `push_up` | ... | ... |
| `push_down` | ... | ... |
| `push_alternating` | cycles through above | ... |
| `push_random` | random pick, never repeat last | ... |

(continue for: Wipe, Instant, Sprite, Special)

## Sprite family — sign-specific notes

- `nyancat` / `pokeball` / `baseball` have hires variants that auto-fire on bigsign (animated webp / Pikachu sprite / procedural rotation). On small sign they use the existing 8×8 sprite paths.
- `pacman` and `sailor_moon` are 8-bit-aesthetic and have NO hires variant — they look right on both signs.

## Recommended `transition_duration` ranges

| Family | Range (ms) | Notes |
|--------|-----------|-------|
| Push | 400–800 | Faster feels snappier |
| Wipe | 600–1200 | Sweep line wants enough time to scan |
| Instant | (n/a — `cut` is 0; `color_flash` ~200) | |
| Sprite | 1500–2500 | Sprite needs time to traverse |

## `transition_specified` precedence rule

When a section's TOML writes `transition = "..."`, that transition fires for BOTH:
1. The inter-section ENTRY when this section appears (overrides `between_sections`)
2. The inter-widget transitions (between widgets in the section)

Sections that omit `transition` fall back to `[transitions] between_sections` for entry.

## `transition_colors` for `wipe_random`

`wipe_random` accepts `transition_colors = [[r,g,b], [r,g,b], ...]` to pick the sweep-line color from a custom pool. Single `transition_color = [r,g,b]` works as a one-element pool.
```

- [ ] **Step 1: Read source materials**

Read CLAUDE.md "Transition System" section in full. Read `src/led_ticker/transitions/__init__.py` to get the canonical registered names.

- [ ] **Step 2: Write the file**

Cover every registered transition. Group by family.

- [ ] **Step 3: Validate**

Run:
```bash
grep -h "register_transition" src/led_ticker/transitions/*.py | grep -oE '"[a-z_]+"' | sort -u
```

Confirm every name appearing in the grep output appears in the file.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/creating-a-config/references/transitions.md
git commit -m "skill: add transitions reference"
```

---

### Task 5: `references/decision-rules.md`

**Files:**
- Create: `.claude/skills/creating-a-config/references/decision-rules.md`

**Source materials:**
- `CLAUDE.md` — the **single richest source**. Scan top-to-bottom for every rule of the form "X is invalid" / "X must Y" / "raises if Z" / "warns when Q".

**Rules to include** (from spec's "references/decision-rules.md" section, plus anything the implementer finds while scanning):

1. `content_height × scale ≤ panel_h_real` (hard ceiling — bigsign means `content_height ≤ 16`)
2. Mixing `font_threshold` within a font family inverts weight contrast (Bold weights pair to same threshold as Regular)
3. `text_align="scroll"` + `fit="stretch"` is invalid (no transparent regions for text)
4. Hires emoji is a no-op on small sign / scale=1
5. HiresFont configs MUST specify `font_size`
6. TwoRow at scale=4 is usually wrong for handle layouts (suggest scale=2)
7. `text_x_offset != 0` invalid with scroll modes
8. `hold_seconds < 0.05` invalid on image widgets
9. BDF `font_size < cell_h` invalid
10. Per-widget `font_threshold` must be int 0-255 (not float, not bool)
11. Section transitions: explicit `transition = "..."` overrides `between_sections` for inter-section entry
12. `animation = "typewriter"` is only supported on `message` widget
13. `bottom_text != ""` on gif/image switches to two-row mode and refuses single-row params (`text_align`, `text_valign`, `text_x_offset`, `font_size`)

**Structure (one block per rule):**

```markdown
<!-- header comment -->

# Decision Rules

These rules are the validation checklist. The skill consults this file at every validation checkpoint (per-section lint, Phase 3 final, refine-mode flag-and-ask).

---

## Rule 1: content_height × scale ≤ panel_h_real

**SOURCE:** `CLAUDE.md` — "Per-section `content_height`" section.

**DETECT:** `section.content_height × default_scale > panel_height`. For bigsign (default_scale=4, panel_height=64) this means `content_height > 16`.

**SYMPTOM:** Top + bottom rows of logical canvas overflow visible area; content placed near those edges silently clips. BDF text may look fine; hires emoji and large hires fonts surface the clip immediately.

**FIX:** Lower `content_height` to `panel_height // default_scale` (16 for bigsign at scale=4). For per-row breathing room use widget-level `text_y_offset` instead.

---

## Rule 2: Within-family font_threshold matching

(continue same shape per rule...)
```

- [ ] **Step 1: Scan CLAUDE.md exhaustively**

Read CLAUDE.md top-to-bottom, marking any "must / raises / invalid / warns / refuses / silently clips" assertions. The 13 rules above are a starting set, NOT exhaustive — add any others found during the scan.

- [ ] **Step 2: Write the file**

One block per rule. The format is fixed: `**SOURCE:**`, `**DETECT:**`, `**SYMPTOM:**`, `**FIX:**`. The DETECT phrase must be specific enough that the skill can mechanically check it against a config.

- [ ] **Step 3: Validate rule count**

Confirm the file has at least 13 rules. Note: the implementer should expect to find a few more during the scan.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/creating-a-config/references/decision-rules.md
git commit -m "skill: add decision-rules reference"
```

---

### Task 6: `references/asset-handling.md`

**Files:**
- Create: `.claude/skills/creating-a-config/references/asset-handling.md`

**Source materials:**
- `CLAUDE.md` sections: "Hi-res fonts on the bigsign", "Per-widget `font_threshold`", "Match thresholds within a font family", "Inline Emoji", "GIF widget and Still-image widget".
- `config/fonts/` — actual layout (flat directory, no family subdir).
- `config/assets/` — actual layout.

**Structure:**

```markdown
<!-- header comment -->

# Asset Handling Playbook

## Brand colors (hex → RGB)

The skill solicits hex codes (e.g. `#E5306C`) and converts to `[r,g,b]` lists.

**Application sites table:**

| Brand role | TOML field |
|-----------|------------|
| Background tone (per-section bg) | `bg_color` |
| Background tone (per-row band on TwoRow / image) | `top_bg_color` / `bottom_bg_color` |
| Primary text | `font_color` |
| Per-row text (TwoRow / image two-row mode) | `top_color` / `bottom_color` |
| Accent / highlight | per-char `gradient` `from`/`to`, or constant on a single section |
| Transition flash | `transition_color` |
| Border | `border = [r,g,b]` (constant) or `border = {style="constant", color=[r,g,b]}` |

## Custom fonts

**Placement:** `config/fonts/<file>` (flat directory; no family subdir). Files are gitignored — they don't go in the repo.

**Font size by viewing distance** (bigsign):

| Distance | Inter-Regular | Inter-Bold | Beloved Sans Regular | Beloved Sans Bold |
|----------|---------------|------------|----------------------|-------------------|
| Close (≤6 ft) | 16 | 16 | 18 | 18 |
| Medium (6–20 ft) | 22 | 22 | 24 | 24 |
| Far (20 ft+) | 28 | 28 | 32 | 32 |

**Threshold rule (CRITICAL):** Within a font family, Bold weights MUST use the same `font_threshold` as Regular so weight contrast survives. E.g.:

```toml
# CORRECT — weight contrast survives
[hello]
font = "Beloved-Sans-Regular"
font_size = 24
font_threshold = 80
[hello_bold]
font = "Beloved-Sans-Bold"
font_size = 24
font_threshold = 80   # same as Regular

# WRONG — Bold appears thinner than Regular!
[hello]
font_threshold = 80
[hello_bold]
font_threshold = 128  # default — inverts weight contrast
```

**Threshold defaults:**
- Inter family at any size: 128 (default)
- Beloved Sans Regular at 24-32: 80 (thin strokes need lower threshold)
- Beloved Sans Bold paired with above: 80 (match Regular)

**Type:** must be `int` 0-255. Floats and bools are rejected.

## Images / GIFs

**Placement:** `config/assets/<file>`. Files are gitignored.

**Fit-mode decision tree:**

1. Image aspect matches panel aspect (ratio within ±10%) → `fit = "stretch"` is fine; `fit = "pillarbox"` works too.
2. Image is taller than panel aspect → `fit = "letterbox"` (black bars top/bottom).
3. Image is wider than panel aspect → `fit = "pillarbox"` (black bars left/right). Use `image_align = "left" | "center" | "right"` to anchor.
4. Image needs to fill the panel and aspect doesn't matter → `fit = "crop"`.
5. Image has transparent regions and you want text to walk "behind" the silhouette → any fit EXCEPT stretch (stretch leaves no transparent regions).

**Two-row text overlay decision:**
- One line of text → use single-row knobs (`text`, `text_align`, `text_valign`, `font_size`).
- Two lines (top held + bottom scrolling) → set `bottom_text` to switch to two-row mode. Single-row knobs are then refused.

**Hold time / loops:**
- Still image: `hold_seconds` (default 5).
- GIF: `gif_loops` (default 1) × native frame durations.
- With `text_loops > 0` on either: `hold_seconds` becomes a duration FLOOR; the source extends to fit the marquee.

## URLs and handles

| User says | Lands as |
|-----------|----------|
| "Instagram @handle" | `:instagram: @handle` in `two_row.bottom_text` |
| "Email me@example.com" | `:email: me@example.com` in `two_row.bottom_text` |
| "Weather in Brooklyn" | `[weather]` widget with `location = "Brooklyn, NY"` |
| "RSS feed at <url>" | `[rss]` widget with `url = "<url>"` |
| "Mets fan" | `[mlb]` widget with `team = "NYM"` |
| "BTC price" | `[crypto]` widget with `pair = "BTC-USD"` |
| "Countdown to <date>" | `[countdown]` widget with `target_date = "<ISO>"` |

**No silent network fetches.** If user gives an asset URL, the skill asks them to download and provide the local path.
```

- [ ] **Step 1: Read source materials**

Read the CLAUDE.md sections listed. Verify `config/fonts/` and `config/assets/` are flat directories (`ls`).

- [ ] **Step 2: Write the file**

Cover all four asset types. Include the threshold rule prominently — it's a high-impact gotcha.

- [ ] **Step 3: Validate**

Spot-check three facts against CLAUDE.md (the exact threshold value 80 for Beloved Sans Regular, the rejection of float/bool, the placement at `config/fonts/<file>` flat).

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/creating-a-config/references/asset-handling.md
git commit -m "skill: add asset-handling reference"
```

---

### Task 7: `references/snippets.md`

**Files:**
- Create: `.claude/skills/creating-a-config/references/snippets.md`

**Source materials:**
- All `config/config.*.example.toml` files. Especially:
  - `config.moonbunny.example.toml` — store window template
  - `config.showroom-bigsign.example.toml` — broad bigsign feature demo
  - `config.example.toml` — small sign baseline
  - `config.bigsign.example.toml` — bigsign baseline
  - `config.presentation_test.example.toml` — color/animation effects
  - `config.image_test.example.toml`, `config.gif_test.example.toml`, `config.gif_text.example.toml` — image widgets
  - `config.hires_*` configs — bigsign hires features

**Structure:**

```markdown
<!-- header comment -->

# Snippet Catalog

Each snippet cites its source file + line range. The skill copies the snippet verbatim, then customizes the fields listed under "must customize".

## Index by (use_case, widget, sign)

| Use case | Widget | Sign | Snippet ID |
|----------|--------|------|-----------|
| store_window | message | big | `message.store_window.bigsign.welcome` |
| store_window | two_row | big | `two_row.store_window.bigsign.handle` |
| store_window | gif | big | `gif.store_window.bigsign.logo` |
| ... | ... | ... | ... |

## Snippets

### snippet: message.store_window.bigsign.welcome

**source:** `config/config.moonbunny.example.toml` lines 25-35 *(adjust during implementation to actual line range)*

**use when:** bigsign + brand presence + welcoming banner needed.

**must customize:** `text`, `font_color` (brand), `font_size`, `font_threshold`.

**copy verbatim:**

```toml
[hello]
type = "message"
text = "Welcome to Moon Bunny"
font = "BelovedSans-Bold"
font_size = 32
font_threshold = 80
font_color = [225, 48, 108]
```

(continue same shape per snippet...)
```

**Required snippets to author** (~22 total — add or refine the ID list as you discover better source material; the IDs below are the minimum coverage):

Store window (5):
1. `message.store_window.bigsign.welcome`
2. `two_row.store_window.bigsign.handle`
3. `gif.store_window.bigsign.logo`
4. `weather.store_window.bigsign.brand`
5. `countdown.store_window.bigsign.hours`

Personal feed (6):
6. `rss.personal_feed.smallsign.headlines`
7. `rss.personal_feed.bigsign.headlines`
8. `weather.personal_feed.smallsign.simple`
9. `weather.personal_feed.bigsign.simple`
10. `crypto.personal_feed.smallsign.btc`
11. `crypto.personal_feed.bigsign.btc`

Event countdown (2):
12. `countdown.event.smallsign`
13. `countdown.event.bigsign`

Sports (3):
14. `mlb.sports.smallsign`
15. `mlb.sports.bigsign`
16. `mlb_standings.sports.bigsign`

Art (3):
17. `gif.art.bigsign.full_panel`
18. `image.art.bigsign.full_panel`
19. `message.art.bigsign.rainbow_border`

Mixed (3):
20. `message.mixed.smallsign`
21. `message.mixed.bigsign`
22. `two_row.mixed.bigsign.dual_message`

- [ ] **Step 1: Map source files to snippet IDs**

For each snippet ID, identify the source `.example.toml` file and approximate line range. Read each source file to confirm the snippet exists and is correct.

- [ ] **Step 2: Write the file**

Author the index table at the top, then 22 snippet blocks following the format.

- [ ] **Step 3: Validate every snippet's source**

For each snippet, run:
```bash
sed -n '<start>,<end>p' <source_file>
```

Confirm the lines extracted match what the snippet claims. If lines drifted, update the line range.

- [ ] **Step 4: Validate index completeness**

Confirm every snippet ID in the catalog appears in the index table, and vice versa.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/creating-a-config/references/snippets.md
git commit -m "skill: add snippets reference catalog"
```

---

### Task 8: `SKILL.md` — orchestration + mode dispatch

**Files:**
- Create: `.claude/skills/creating-a-config/SKILL.md`

**Source materials:**
- The committed spec (`docs/superpowers/specs/2026-05-07-creating-a-config-skill-design.md`).
- The 6 reference files written in Tasks 2-7 (the SKILL.md cross-references them).

**Structure:**

```markdown
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

Announce: "Using creating-a-config skill in <mode> mode."

---

## `new` mode (3-phase wizard)

### Phase 1: Outline

Load `references/hardware-guide.md`.

Ask these 7 questions, one at a time, using AskUserQuestion. Multi-choice format where listed.

1. **Sign target:** small (160×16) / bigsign (256×64) / both (parallel configs)
2. **Use case category:** store window / personal feed / event countdown / sports scoreboard / art piece / mixed
3. **Viewing distance:** close (≤6ft) / medium (6–20ft) / far (20ft+)
4. **Content sources** (multi-select): rss / weather / custom messages / gifs+images / sports / crypto / countdown
5. **Brand presence:** none / colors only / colors+fonts / colors+fonts+logo
6. **Tone:** minimal / playful / info-dense / branded-pro
7. **Cadence:** always-on continuous loop / scheduled windows

After answers, propose a section list: load `references/snippets.md`, look up snippets keyed by (use_case × content_source × sign_target), produce one section per content source. Present to user with proposed widget per section. User confirms or edits the list.

### Phase 2: Per-section pass

Load `references/snippets.md`, `references/widgets.md`, `references/asset-handling.md`, `references/decision-rules.md`.

For each confirmed section in the outline:

1. Look up the snippet matching (use_case × widget × sign_target) in `snippets.md`.
2. Ask widget-specific questions per the snippet's "must customize" list. Use AskUserQuestion.
3. For asset-bearing sections: collect assets per `asset-handling.md`. Place in `config/fonts/<file>` or `config/assets/<file>`. Verify the path exists; never fetch URLs silently.
4. Write the section's TOML to the in-progress config buffer.
5. Run per-section lint: for each rule in `decision-rules.md` whose DETECT clause matches this section, surface as flag-and-ask.
6. Brief "looks good?" before next section.

### Phase 3: Polish

Load `references/transitions.md`, `references/decision-rules.md`.

Ask these (5–7 questions, condensed via AskUserQuestion when possible):

1. **Default transition + duration + easing** — offer 3 picks based on Phase 1 tone (see `transitions.md` "Selecting a transition" table).
2. **`between_sections` transition** — usually different.
3. **Default `hold_time`** — defaults: continuous=5, scheduled=10.
4. **Brightness** — defaults: small=60, big=80; ask if different.
5. **Bigsign refresh tuning** — only ask if sign=bigsign AND tone=info-dense.
6. **Save destination** — propose `config/config.<descriptive-slug>.toml` based on Phase 1 answers; ask if user wants to override or activate as `config/config.toml` (with `.bak` of existing).

Run final validation: full pass over `decision-rules.md` against the assembled config. Surface flags as flag-and-ask.

Write the file. Print: path written, test command (`make test`), run command (read from `Makefile` / `compose.yaml`), unfixed flags.

---

## `add` mode

Load `references/widgets.md`, `references/snippets.md`, `references/asset-handling.md`, `references/decision-rules.md`.

1. Read `config/config.toml`. Extract: sign target (from `default_scale` + panel dims), brand colors, default transition / hold / easing, sections list.
2. Ask: "What kind of section do you want to add?" — multi-select from `widgets.md`.
3. For each chosen widget: same flow as `new` Phase 2 (snippet lookup, widget Qs, asset collection, write, lint).
4. Ask: "Where to insert?" — end / before [section] / after [section].
5. Show full diff. First in-place edit per session creates `config/config.toml.bak` (overwrites prior `.bak` if present).
6. Apply edit on user approval.

---

## `refine` mode

Load `references/decision-rules.md`, `references/widgets.md`, `references/transitions.md`.

1. Read `config/config.toml`. Run full validation pass against `decision-rules.md`. Cache the violation list.
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
   | Too small at far + bigsign + currently BDF | `font` field on text widgets | Hires Inter at `font_size=24-32` (consult `asset-handling.md` distance table). Migrate from BDF default. |
   | Too small + already hires | `font_size` value | Bump font_size up one tier (16→22, 22→28, 28→32). |
   | Too aggressive / busy | `font_color`, `border`, transitions | Swap per-char `rainbow` → `color_cycle`. Replace `wipe_alternating` / `nyancat_alternating` → `cut` or `wipe_left`. Lengthen `hold_time` by 50%. Drop animated `border` to constant or remove. |
   | Too slow / too much dead time | `hold_time`, `transition_duration` | Reduce `hold_time` by 30-50%. If `transition_duration > 1000`, drop to 600. Consider `cut` for inter-widget transitions. |
   | Too fast / can't read it | `hold_time`, `transition_duration` | Raise `hold_time` by 50%. If using fast transitions (`cut`, `push_left` at 400ms), bump duration to 800ms or swap to a wipe. |
   | Wrong colors / bad contrast | `bg_color` vs `font_color` luminance | If both are light or both dark, propose adjusting one for contrast (luminance heuristic: rough sum of RGB channels for each — push them apart). For brand-locked colors, propose adding a `border` for separation. |
   | Image fit looks bad + `fit="stretch"` + non-matching aspect | `fit`, image dimensions | Propose `fit="pillarbox"` (wider than panel) or `fit="letterbox"` (taller than panel) per `asset-handling.md` decision tree. Add `image_align` if pillarbox. |
   | Border / animation feels off | `border.speed`, `border.char_offset`, `border.thickness`, `animation` | If border feels too fast: lower `speed` (default 4 on bigsign; try 2). Too uniform: raise `char_offset`. Too thin from far: thickness 1→2. Typewriter feels off-pace: tune `frames_per_char` (default 3; raise for slower). |
4. After stated symptoms, surface step-1 violation list as flag-and-ask. Each item: "I also noticed: <rule violation> (severity) — want me to fix? Per `decision-rules.md` rule N."
5. Show each delta as unified diff. User approves per-delta.
6. Apply approved edits. First in-place edit per session backs up to `config/config.toml.bak`.

---

## Validation: flag-and-ask philosophy

The skill never silently auto-fixes a violation. Every flag is presented to the user with the rule cited (`per decision-rules.md rule N`). The user decides. This applies in all three modes.
```

- [ ] **Step 1: Read the spec**

Re-read `docs/superpowers/specs/2026-05-07-creating-a-config-skill-design.md` to ground the SKILL.md in the agreed design.

- [ ] **Step 2: Write the SKILL.md**

Use the structure above. Cross-reference each `references/*.md` file by relative path. Don't repeat content from references — direct the skill to load them.

- [ ] **Step 3: Validate cross-references**

For every `references/<name>.md` mentioned in SKILL.md, confirm the file exists. Run:
```bash
grep -oE 'references/[a-z-]+\.md' .claude/skills/creating-a-config/SKILL.md | sort -u
ls .claude/skills/creating-a-config/references/
```

The two lists must match (every reference in SKILL.md exists; every existing reference is mentioned at least once in the loading table).

- [ ] **Step 4: Validate the description triggers all three modes**

Read the `description:` frontmatter line. Confirm it contains words/phrases that would match user intents for **new**, **add**, and **refine** (e.g. "build", "add a widget", "tune"). The Skill tool fires when the description matches the user's request.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/creating-a-config/SKILL.md
git commit -m "skill: add creating-a-config orchestrator"
```

---

### Task 9: Walkthrough A — `new` mode store-window scenario

**Files:**
- Create: `docs/superpowers/walkthroughs/2026-05-07-creating-a-config-new-store-window.md` (verification artifact)

**Goal:** Confirm the skill, when invoked in `new` mode for a "store window on bigsign" scenario, produces a config sensibly close to `config/config.moonbunny.example.toml`.

**Scenario inputs:**
- Sign target: bigsign
- Use case: store window
- Viewing distance: medium (storefront window seen from sidewalk)
- Content sources: custom messages, weather, two_row (handle)
- Brand presence: colors+fonts (assume Beloved Sans family available — fake the path for the walkthrough)
- Tone: branded-pro
- Cadence: always-on continuous

- [ ] **Step 1: Start a fresh Claude Code session in this repo**

This is critical — the walkthrough must run with no context from the planning session. The skill must work cold.

- [ ] **Step 2: Invoke the skill**

In the fresh session, type: `/creating-a-config` (or "help me make a new config"). The skill should detect `new` mode (config.toml doesn't exist OR the user clearly stated "new").

- [ ] **Step 3: Walk through Phase 1 with the scenario inputs above**

Answer each of the 7 questions per the scenario.

- [ ] **Step 4: Confirm the proposed section list**

Expected: at least sections for hello-banner (message), weather, handle (two_row). Reasonable additions: hours-countdown, brand-message.

- [ ] **Step 5: Walk through Phase 2 per section**

For each, confirm the skill asks only widget-specific questions and applies the brand colors / fonts.

- [ ] **Step 6: Walk through Phase 3 polish**

Pick `wipe_alternating` with brand `transition_color`, `hold_time=8`, `between_sections=cut`, save to `config/config.store-window-bigsign.toml`.

- [ ] **Step 7: Diff the produced config against `config/config.moonbunny.example.toml`**

```bash
diff -u config/config.moonbunny.example.toml config/config.store-window-bigsign.toml
```

The two should be **structurally similar** (same widget types, similar fields, similar transitions). They will not be identical — the moonbunny config is a real-world template, not the wizard's deterministic output. Acceptance: a human reading both can say "yep, the wizard's output is a reasonable variant of moonbunny."

- [ ] **Step 8: Document results**

Write the walkthrough log to `docs/superpowers/walkthroughs/2026-05-07-creating-a-config-new-store-window.md`. Include: scenario inputs, transcript of skill questions + answers, final config diff against moonbunny, "issues found" list.

- [ ] **Step 9: Iterate on the skill if walkthrough exposed issues**

If Phase 1 questions weren't clear, if a snippet was missing, if a validation rule didn't fire — fix in the relevant file. Re-run the walkthrough from a fresh session. Loop until clean.

- [ ] **Step 10: Commit walkthrough log + any skill fixes**

```bash
git add docs/superpowers/walkthroughs/2026-05-07-creating-a-config-new-store-window.md
git add .claude/skills/creating-a-config/  # only if fixes applied
git commit -m "skill: walkthrough A (new mode store window) verification"
```

---

### Task 10: Walkthrough B — `add` mode insert into example config

**Files:**
- Create: `docs/superpowers/walkthroughs/2026-05-07-creating-a-config-add-section.md`

**Goal:** Confirm `add` mode can insert a new widget section into an existing `config.toml` cleanly, inheriting global settings.

**Scenario inputs:**
- Pre-existing `config/config.toml` = copy of `config/config.example.toml` (small sign baseline)
- User request: "add a weather widget for Brooklyn"

- [ ] **Step 1: Set up the scenario**

```bash
cp config/config.example.toml config/config.toml
```

- [ ] **Step 2: Start fresh session, invoke the skill**

In a fresh session, type: "I want to add a weather widget to my config" (or `/creating-a-config` and describe intent).

- [ ] **Step 3: Confirm `add` mode dispatch**

Skill should detect `add` mode (config.toml exists + "add a widget" intent). It should NOT ask Phase 1 questions about sign target / brand / tone — those are inherited.

- [ ] **Step 4: Walk through the per-section flow**

Skill asks weather-specific questions only: location (answer: Brooklyn, NY), units, icon yes/no.

- [ ] **Step 5: Confirm insertion question**

Skill asks where to insert. Pick "end".

- [ ] **Step 6: Confirm diff and apply**

Skill shows unified diff. User approves. File saves with `.bak` of original.

- [ ] **Step 7: Validate the result**

```bash
diff config/config.toml.bak config/config.toml
ls config/config.toml.bak  # should exist
```

The diff should show only an additive new `[weather]` section. No other sections touched.

- [ ] **Step 8: Smoke-test the config**

```bash
PYTHONPATH=tests/stubs python -c "from led_ticker.config import load_config; load_config('config/config.toml')"
```

Expected: no exception (config still parses).

- [ ] **Step 9: Restore the example baseline**

```bash
mv config/config.toml.bak config/config.toml
# OR delete both — config.toml is gitignored
rm config/config.toml config/config.toml.bak
```

- [ ] **Step 10: Document results**

Write walkthrough log. Same format as Walkthrough A.

- [ ] **Step 11: Iterate if issues, commit**

Same iteration loop. Then:

```bash
git add docs/superpowers/walkthroughs/2026-05-07-creating-a-config-add-section.md
git add .claude/skills/creating-a-config/  # only if fixes applied
git commit -m "skill: walkthrough B (add mode) verification"
```

---

### Task 11: Walkthrough C — `refine` mode against an intentionally broken config

**Files:**
- Create: `docs/superpowers/walkthroughs/2026-05-07-creating-a-config-refine.md`
- Create: `tests/fixtures/broken-bigsign-config.toml` (intentionally violation-laden test fixture)

**Goal:** Confirm `refine` mode catches multiple gotchas via flag-and-ask and addresses user-stated symptoms with sensible deltas.

**Test fixture content** — `tests/fixtures/broken-bigsign-config.toml` should violate at least 3 rules from `decision-rules.md`. Suggested violations:

1. `content_height = 20` on a bigsign section at scale=4 (Rule 1 violation: 20×4=80 > 64)
2. A TwoRow section using Beloved Sans Regular at `font_threshold=80` AND Beloved Sans Bold at `font_threshold=128` in the same section (Rule 2 violation: weight contrast inverted)
3. A gif section with `text_align = "scroll"` AND `fit = "stretch"` (Rule 3 violation)
4. A bigsign hires-emoji section using `:moon:` on what's actually a small sign (Rule 4 — only fires if you change the panel dims; alternative: use a HiresFont without `font_size` for Rule 5)

**Scenario user complaints:**
- "The fonts on my display look too small from across the room."

This complaint should match a "too small at far viewing distance" symptom. The skill should propose increasing `font_size` AND surface the unrelated violations as flag-and-ask.

- [ ] **Step 1: Author the broken fixture**

Write `tests/fixtures/broken-bigsign-config.toml` with the 3+ violations listed. Each violation should be obvious to a careful reader of `decision-rules.md`. Add a top-of-file comment listing the violations so future maintainers know it's intentional.

- [ ] **Step 2: Set up the scenario**

```bash
cp tests/fixtures/broken-bigsign-config.toml config/config.toml
```

- [ ] **Step 3: Fresh session, invoke skill with the complaint**

"My fonts look too small from across the room. Can you tune my config?"

- [ ] **Step 4: Confirm `refine` mode dispatch**

Skill detects refine mode + symptom "too small at far".

- [ ] **Step 5: Confirm symptom-driven delta**

Skill should propose increasing `font_size` (or switching BDF to hires if the broken config used BDF) on the affected sections.

- [ ] **Step 6: Confirm flag-and-ask for the unrelated violations**

After addressing the stated symptom, skill should surface ALL the planted violations as separate "I also noticed: X — want me to fix?" prompts. Each citing the relevant rule from `decision-rules.md`.

- [ ] **Step 7: Accept all proposals, apply diffs**

Verify each diff is minimal and targeted. The skill should NOT make unrelated edits beyond what was approved.

- [ ] **Step 8: Verify result config is clean**

Re-run validation manually: do any rules from `decision-rules.md` still match the resulting config? They should not.

- [ ] **Step 9: Restore baseline**

```bash
rm config/config.toml config/config.toml.bak
```

- [ ] **Step 10: Document results**

Write walkthrough log. Include: planted violations, the user complaint, every flag-and-ask the skill raised, final clean config, "issues found" list.

- [ ] **Step 11: Iterate if issues, commit**

Same iteration loop.

```bash
git add docs/superpowers/walkthroughs/2026-05-07-creating-a-config-refine.md
git add tests/fixtures/broken-bigsign-config.toml
git add .claude/skills/creating-a-config/  # only if fixes applied
git commit -m "skill: walkthrough C (refine mode) verification + broken fixture"
```

---

## Deferred / out-of-scope

- **`both` sign target (parallel small + big configs):** The Phase 1 question lists it as an option but actual implementation is deferred. The skill should reply "parallel configs not yet supported — pick one for now" if user picks `both`. A future enhancement adds dual-output support. (Tracked as a comment in SKILL.md Phase 1.)
- **Visual mood reference parsing:** Phase 1's "moodboard URL/photo" idea was scoped down. The skill accepts the URL as text-only context; no image parsing or visual analysis. Tone selection drives stylistic register instead.
- **Snippet learning:** No mechanism for the skill to add new snippets to `snippets.md` based on user-created configs. Manual update only.
