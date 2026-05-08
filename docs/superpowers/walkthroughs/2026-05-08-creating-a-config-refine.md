# Walkthrough C: refine mode (broken bigsign config)

## Planted violations

All three violations are in `tests/fixtures/broken-bigsign-config.toml`.

1. **[Rule 1]** content_height ceiling exceeded — section 3 ("Follow Us / Handle"):
   `content_height = 20` with no per-section scale override. At bigsign
   `default_scale = 4`: `20 × 4 = 80 > 64` (physical panel height). Top and bottom rows
   of the logical canvas overflow the visible area; hi-res emoji and large fonts clip
   silently near those edges. Located at lines 100–118.

2. **[Rule 3]** scroll + stretch invalid — section 4 ("Promo GIF"):
   `[[playlist.section.widget]]` gif widget with `fit = "stretch"` AND
   `text_align = "scroll"`. Stretch fills the entire canvas leaving no transparent
   regions; scroll text expects a transparent silhouette to walk behind. Located at
   lines 124–136.

3. **[Rule 2]** Within-family font_threshold mismatch — section 5 ("Brand message"):
   Two message widgets in the same section, both using the Inter family:
   `Inter-Regular` at `font_threshold = 80` and `Inter-Bold` at `font_threshold = 128`
   (the default). At threshold 80, Regular has more lit pixels per glyph than Bold at
   128, inverting the weight contrast on the physical panel (Regular appears fatter than
   Bold). Located at lines 143–167.

---

## User complaint

> "My fonts look too small from across the room. Can you tune my config?"

---

## Refine-mode transcript

### Step 0: Mode detection

Config file exists (`tests/fixtures/broken-bigsign-config.toml`); user said "tune" →
**`refine` mode** selected.

Loaded: `references/decision-rules.md`, `references/widgets.md`, `references/transitions.md`.

---

### Pre-scan validation results

Full 20-rule pass against the broken fixture:

| Rule | Severity | Location | Detail |
|------|----------|----------|--------|
| Rule 1 | HIGH | section[2] (handle) | `content_height=20 × eff_scale=4 = 80 > panel_h_real=64` |
| Rule 3 | HIGH | section[3] (promo gif), widget[0] | `text_align="scroll" + fit="stretch"` |
| Rule 2 | HIGH | section[4] (brand message) | Family "Inter": [('Inter-Regular', 80), ('Inter-Bold', 128)] |

Rules 4–20 all pass (no other violations detected).

---

### Symptom routing

**Skill asked:** "Which of the following describes what you're seeing? (pick all that apply)"
- Too small to read at viewing distance
- Too aggressive / busy
- Too slow / too much dead time
- Too fast / can't read it
- Wrong colors / bad contrast
- Image fit looks bad
- Border / animation feels off
- Other (free text)

**User picked:** "Too small to read at viewing distance"

**Skill inspected:** `font` field on text widgets in sections 1 and 2.
- Section 1: two `message` widgets — no `font` field set → BDF default.
- Section 2: `weather` widget — no `font` field set → BDF default.
- Sign target: bigsign (`default_scale = 4`). Currently BDF. User complaint: too small at far.

**Symptom table row matched:**
> Too small at far + bigsign + currently BDF → Hires Inter at `font_size = 24–32`
> (consult `references/asset-handling.md` distance table)

**Asset-handling distance table (far, 20ft+, bigsign):** Inter-Regular → 28px.

**Proposed DELTA 1:**

```diff
# Section 1 — welcome banner, widget[0]
  type = "message"
  text = "Open daily 10am–8pm :star:"
+ font = "Inter-Regular"
+ font_size = 28
+ font_threshold = 128
  font_color = [255, 200, 100]

# Section 1 — welcome banner, widget[1]
  type = "message"
  text = "Find us on :instagram: @theawesomeshop"
+ font = "Inter-Regular"
+ font_size = 28
+ font_threshold = 128
  font_color = [200, 100, 255]

# Section 2 — weather widget
  type = "weather"
  location = "Brooklyn, NY"
  units = "imperial"
+ font = "Inter-Regular"
+ font_size = 28
+ font_threshold = 128
  font_color = [255, 255, 255]
```

**User response:** "Yes, apply it."

---

### Flag-and-ask for unrelated violations

After addressing the stated symptom, the skill surfaced the 3 pre-scan violations:

---

**Flag 1 (Rule 1 — HIGH):**

> I also noticed: section 3 ("Follow Us") has `content_height = 20` but no
> per-section `scale` override. On bigsign with `default_scale = 4`, the hard
> ceiling is `content_height ≤ 16` (because `16 × 4 = 64 = panel_h_real`).
> Your current value gives `20 × 4 = 80`, which overflows the physical panel
> by 16 pixels. Top and bottom rows of your `two_row` widget clip silently.
> Want me to lower `content_height` to 16?
> *(Per `references/decision-rules.md` Rule 1.)*

**User response:** "Yes, fix it."

**Proposed DELTA 2:**

```diff
  [[playlist.section]]
  mode = "swap"
  hold_time = 6
  loop_count = 2
- content_height = 20
+ content_height = 16
```

---

**Flag 2 (Rule 3 — HIGH):**

> I also noticed: section 4 (promo GIF) combines `text_align = "scroll"` with
> `fit = "stretch"`. Stretch mode fills the entire canvas — there are no
> transparent regions left for the scroll text to walk behind. The footgun
> validation in the codebase will raise at first paint with this combination.
> The simplest fix is changing `fit` to `"pillarbox"` (black bars fill the sides
> of the image, exposing transparent columns the text can scroll through).
> Want me to change `fit` from `"stretch"` to `"pillarbox"`?
> *(Per `references/decision-rules.md` Rule 3.)*

**User response:** "Yes, fix it."

**Proposed DELTA 3:**

```diff
  [[playlist.section.widget]]
  type = "gif"
  path = "assets/promo-loop.gif"
- fit = "stretch"
+ fit = "pillarbox"
  text = "New arrivals every Friday!"
  text_align = "scroll"
```

---

**Flag 3 (Rule 2 — HIGH):**

> I also noticed: section 5 ("New Collection") has two Inter-family widgets
> with different `font_threshold` values — `Inter-Regular` at 80 but
> `Inter-Bold` at 128. The CLAUDE.md hardware-validated finding is that at
> threshold 80, Regular accumulates more lit pixels per glyph than Bold at 128,
> so **Bold appears lighter than Regular on the panel** — weight contrast inverts.
> Fix: align `Inter-Bold`'s `font_threshold` to 80 (matching Regular).
> Want me to apply that?
> *(Per `references/decision-rules.md` Rule 2.)*

**User response:** "Yes, fix it."

**Proposed DELTA 4:**

```diff
  [[playlist.section.widget]]
  type = "message"
  text = "Shop now — link in bio!"
  font = "Inter-Bold"
  font_size = 22
- font_threshold = 128
+ font_threshold = 80
  font_color = [225, 48, 108]
```

---

### Applied deltas

All four deltas accepted. Written to `/tmp/refined-bigsign-config.toml`.

| Delta | Target section | Change summary |
|-------|---------------|---------------|
| DELTA 1 | Sections 1 (×2 widgets) + 2 (×1 widget) | Added `font = "Inter-Regular"`, `font_size = 28`, `font_threshold = 128` to 3 BDF-default text widgets |
| DELTA 2 | Section 3 | `content_height = 20` → `content_height = 16` |
| DELTA 3 | Section 4, widget[0] | `fit = "stretch"` → `fit = "pillarbox"` |
| DELTA 4 | Section 5, widget[1] | `font_threshold = 128` → `font_threshold = 80` on `Inter-Bold` |

---

## Final config

The changed sections (before → after diffs):

**Section 1 (welcome banner):** Added `font = "Inter-Regular"` / `font_size = 28` /
`font_threshold = 128` to both message widgets.

**Section 2 (weather):** Added `font = "Inter-Regular"` / `font_size = 28` /
`font_threshold = 128` to the weather widget.

**Section 3 (handle):** `content_height = 20` → `content_height = 16`.

**Section 4 (promo GIF):** `fit = "stretch"` → `fit = "pillarbox"`.

**Section 5 (brand message):** `Inter-Bold`'s `font_threshold = 128` → `font_threshold = 80`.

Full result at `/tmp/refined-bigsign-config.toml`.

---

## Re-scan: all violations resolved?

**YES.**

Re-ran the full 20-rule scan against `/tmp/refined-bigsign-config.toml`:

```
Display: default_scale=4, panel_h_real=64

=== RE-SCAN RESULTS ===
All 3 planted violations resolved. Zero violations remaining.
Violations: 0
```

Load verification:

```
Loaded OK. Sections: 5
  [0] mode=forever_scroll scale=4 content_height=16 widgets=2
  [1] mode=swap           scale=4 content_height=16 widgets=1
  [2] mode=swap           scale=4 content_height=16 widgets=1   ← was 20
  [3] mode=swap           scale=4 content_height=16 widgets=1
  [4] mode=swap           scale=4 content_height=16 widgets=2
```

---

## Acceptance verdict

**PASS** — The symptom-driven delta + flag-and-ask cycle worked as designed:

1. Symptom "too small from across the room" correctly routed to the
   "Too small at far + bigsign + currently BDF" row in the symptom table.
   The skill proposed hires Inter at 28px (matching the asset-handling
   far-distance recommendation) and applied it to the 3 BDF-default widgets.

2. Pre-scan detected all 3 planted violations (Rules 1, 2, 3). Each was
   surfaced as an independent flag-and-ask with the rule number cited,
   *after* the symptom-driven delta was addressed. None were auto-fixed.

3. All 4 proposed fix diffs were technically correct. Re-scan confirmed zero
   violations remaining. Config still parses cleanly after all edits.

---

## Issues found

- **[LOW — cosmetic]** The `[transitions] duration = 500` in the fixture uses
  an integer (milliseconds) rather than a float in seconds (`0.5`). The config
  loader accepts it without error (stored as `float` via Python's implicit cast),
  but the value `500` (interpreted as 500 seconds) is nonsensical for a
  transition duration. The refine-mode skill did not flag this because Rule 11
  and the transitions reference only describe the *type* of transition, not
  numeric range validation for `duration`. **Severity: LOW** — config loads and
  the engine would just produce extremely slow transitions, which the user would
  notice at runtime. A future Rule 21 could catch `duration > 10` as a likely
  unit error.

- **[LOW — coverage gap]** None of the 20 rules in `decision-rules.md` check
  the `[transitions] duration` units/range. The broken fixture's `duration = 500`
  passed all 20 rules. The skill's pre-scan would miss this class of misconfiguration.
  Suggest adding a rule: "If `[transitions] duration > 10`, flag as likely
  milliseconds-vs-seconds unit confusion."

- **[INFORMATIONAL]** The `font_threshold` mismatch rule (Rule 2) required
  inferring the font *family* from the raw font name string by stripping weight
  suffixes (e.g., `Inter-Regular` → `Inter`, `Inter-Bold` → `Inter`). The
  skill's regex approach works for standard naming conventions but would miss
  unconventional names (e.g., `BelSans-R` and `BelSans-B` sharing no common
  suffix pattern). The rule as written in `decision-rules.md` states "same font
  family" which implies user discipline on naming — not a skill defect, just a
  documentation boundary to note.
