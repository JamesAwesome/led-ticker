# Walkthrough B: add mode (insert weather into existing config)

## Scenario

**Mock setup:** User copies `config/config.example.toml` to a working location and asks to add a weather widget.

**Mock user request:** "I want to add a weather widget for Brooklyn, NY to my config."

**Existing config:** `config/config.example.toml` (small sign baseline — 160×16, `default_scale` absent, `rows = 16`, `cols = 32`, `chain = 5`).

**Mock answers:**
- Widget type: `weather`
- Location: "Brooklyn, NY"
- Units: imperial
- Show icon: yes
- Insertion point: end (after the last existing section)

---

## Mode detection

**Signal:** User said "add a weather widget" — explicit add intent. Additionally, the scenario provides an existing config. Both signals match `add` mode: user says "add a section" AND `config/config.toml` exists.

**Announced:** "Using creating-a-config skill in **add** mode."

**Phase 1 questions skipped:** `add` mode explicitly has no Phase 1 — it skips sign target, brand, tone, and cadence questions. These are inherited from the existing config.

---

## Existing config summary

Extracted from `config/config.example.toml`:

| Property | Value | Source |
|----------|-------|--------|
| Sign target | small sign (160×16) | `rows = 16`, `cols = 32`, `chain = 5`; no `default_scale` → defaults to 1 |
| Default transition | `wipe_alternating` | `[transitions] default` |
| Between-sections transition | `dissolve` | `[transitions] between_sections` |
| Easing | `ease_out` | `[transitions] easing` |
| Transition duration | 0.5s | `[transitions] duration` |
| Existing sections | 2 | `forever_scroll` messages section + `forever_scroll` countdowns section |
| Brand colors | None detected | No `bg_color`, `font_color` patterns with consistent values |
| Default hold_time | Not set globally | Per-section; countdowns section has no hold_time (forever_scroll, count-driven) |

---

## Add-flow transcript

### Step 1: Load reference files

Per SKILL.md `add` mode header:
> Load `references/widgets.md`, `references/snippets.md`, `references/asset-handling.md`, `references/decision-rules.md`.

All four loaded.

### Step 2: Ask widget type

**Q:** "What kind of section do you want to add?"

**A:** `weather`

### Step 3: Snippet lookup

Key: `(use_case=personal_feed, widget=weather, sign=small)` → `weather.personal_feed.smallsign.simple`

Found in `references/snippets.md`:

```toml
[[playlist.section]]
mode = "swap"
transition = "push_alternating"
hold_time = 6
loop_count = 2

[playlist.section.title]
type = "message"
text = "Weather"
color = "random"

[[playlist.section.widget]]
type = "weather"
message = "New York"
location = "New York"
units = "imperial"
```

**"must customize":** `message` (city label), `location` (city/zip), `units` (`"imperial"` or `"metric"`).

### Step 4: Widget-specific questions (from must-customize list)

**Q:** What location string should I use for the API query? (city name, ZIP code, or lat/lon)

**A:** "Brooklyn, NY"

**Q:** What label should appear on the panel for this city?

**A:** (derived from location) → "Brooklyn"

**Q:** Units — imperial (Fahrenheit) or metric (Celsius)?

**A:** imperial

**Q:** Show the weather condition icon?

**A:** yes → `show_icon = true`

No asset collection needed (weather widget has no file assets; API key is in `.env`).

### Step 5: Write section TOML

Applied customizations to the snippet:
- `message`: `"New York"` → `"Brooklyn"`
- `location`: `"New York"` → `"Brooklyn, NY"`
- `units`: already `"imperial"` ✓
- Added `show_icon = true` (user confirmed yes; snippet omits it, defaults true — but explicit is better)

```toml
# --- Weather: Brooklyn, NY ---

[[playlist.section]]
mode = "swap"
transition = "push_alternating"
hold_time = 6
loop_count = 2

[playlist.section.title]
type = "message"
text = "Weather"
color = "random"

[[playlist.section.widget]]
type = "weather"
message = "Brooklyn"
location = "Brooklyn, NY"
units = "imperial"
show_icon = true
```

### Step 6: Per-section lint (decision-rules.md)

Rules checked against the new section:

| Rule | Check | Result |
|------|-------|--------|
| Rule 1: content_height × scale ≤ panel_h_real | No `content_height` set; default + scale=1 → well within 16px | PASS |
| Rule 2: Within-family font_threshold matching | No hires fonts in this section | N/A |
| Rule 3: text_align="scroll" + fit="stretch" | Not a gif/image widget | N/A |
| Rule 5: HiresFont requires font_size | No font override | N/A |
| Rule 11: Section transition precedence | `transition = "push_alternating"` set → this transition fires on entry AND between widgets. Only one widget in section → no inter-widget transition conflict. Noted as informational. | PASS |
| Rule 15: border restricted to specific types | No border field | N/A |
| Rule 17: Hires emoji on small sign falls back | No emoji in weather widget text | N/A |

**No violations found.** Per-section lint: clean.

### Step 7: Ask insertion point

**Q:** "Where to insert?" — end / before section N / after section N

**A:** end (after the last existing section)

### Step 8: Show diff + get approval (skipped in simulation — approval assumed)

Full diff is in the "Diff" section below. Diff is purely additive — no existing lines removed.

No `.bak` file created (this is a simulation; in real usage, first in-place edit per session creates `config/config.toml.bak`).

---

## Diff

```diff
--- config/config.example.toml
+++ config-with-weather.toml
@@ -177,3 +177,23 @@
 # message = "NYC"
 # location = "New York"
 # units = "imperial"
+
+# --- Weather: Brooklyn, NY ---
+
+[[playlist.section]]
+mode = "swap"
+transition = "push_alternating"
+hold_time = 6
+loop_count = 2
+
+[playlist.section.title]
+type = "message"
+text = "Weather"
+color = "random"
+
+[[playlist.section.widget]]
+type = "weather"
+message = "Brooklyn"
+location = "Brooklyn, NY"
+units = "imperial"
+show_icon = true
```

---

## Smoke-test result

**Command run:**
```bash
PYTHONPATH=tests/stubs uv run python -c "
from led_ticker.config import load_config
c = load_config('/tmp/config-with-weather.toml')
print(f'Loaded OK. Sections: {len(c.sections)}')"
```

**Output:**
```
Loaded OK. Sections: 3
```

Original config: 2 sections. Modified config: 3 sections. N+1 confirmed.

**Note on PYTHONPATH:** The smoke-test command in the scenario used `PYTHONPATH=tests/stubs` (Makefile style). Running plain `python3` without `uv run` requires `PYTHONPATH=tests/stubs:src` because `uv run` is what adds `src/` to `sys.path` in the Makefile flow. Using `uv run python` with `PYTHONPATH=tests/stubs` works correctly.

---

## Acceptance verdict

**PASS** — The modified config loads without errors. The diff is purely additive (zero deletions, 22 lines added).

---

## Issues found

- **NIT — `references/snippets.md` smoke-test command omits `src/` from PYTHONPATH:** The scenario's smoke-test command `PYTHONPATH=tests/stubs python -c "..."` fails with `ModuleNotFoundError: No module named 'led_ticker'` when run outside `uv run`. The Makefile uses `uv run` which adds `src/` automatically. The walkthrough step 7 smoke-test command should either use `uv run python` or include `src/` in the PYTHONPATH: `PYTHONPATH=tests/stubs:src python3 -c "..."`. Since this is in the scenario instructions (not the skill itself), it is low-impact in production — real users would use `make test` — but the scenario spec should be updated.
  **Location:** Walkthrough scenario instructions step 7; not in SKILL.md or any `references/` file.
  **Severity:** NIT

- **NIT — `weather.personal_feed.smallsign.simple` snippet omits `show_icon`:** The snippet does not include `show_icon = true` even though the widget defaults to `show_icon = true`. This is technically redundant (default covers it), but the bigsign sibling snippet (`weather.personal_feed.bigsign.simple`) does include `show_icon = true` explicitly, creating an inconsistency between the two snippets. The skill's "must customize" list for the smallsign snippet does not mention `show_icon` at all, so users who want to disable the icon have no obvious path. Minor inconsistency, no functional impact since the default is `true`.
  **Location:** `references/snippets.md` — snippet `weather.personal_feed.smallsign.simple` vs `weather.personal_feed.bigsign.simple`.
  **Severity:** NIT

- **NIT — `add` mode does not explicitly state "inherit `transition` from existing config" for new sections:** The skill says "No Phase 3 — the new section inherits global transitions and hold settings from the existing config." However, the `weather.personal_feed.smallsign.simple` snippet includes its own `transition = "push_alternating"` — it does NOT inherit the global default. The "inherit" language in the skill is accurate only for sections that omit the `transition` key. The snippet correctly sets an explicit transition (which is a reasonable default for weather), but the skill wording slightly overstates the inheritance guarantee. No functional issue.
  **Location:** SKILL.md `add` mode description, final paragraph.
  **Severity:** NIT

- **NIT — `add` mode step 2 says "multi-select from references/widgets.md":** Weather is a single widget type here, and the snippet lookup key requires a `use_case`. The skill asks "What kind of section do you want to add?" but `add` mode never asks the user for a `use_case` to drive the snippet lookup — it's ambiguous whether to reuse the existing config's inferred use-case or ask freshly. In this walkthrough, `personal_feed` was inferred from the existing config's content (countdown + messages = personal use). The skill SKILL.md does not document this inference step explicitly in `add` mode, leaving a gap if the new section's use-case differs from the existing config's (e.g., adding a `store_window` weather section to a `personal_feed` config).
  **Location:** SKILL.md `add` mode step 2.
  **Severity:** IMPORTANT — the snippet index requires `use_case` as a key but `add` mode never asks for it.
