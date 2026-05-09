# Docs Site Content — Plan B2: Remaining Widgets + Concepts

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Author the second batch of docs site content — four remaining concept pages (sections-and-modes, animations, borders, frame-counters) and six remaining widget pages (rss_feed, mlb, mlb_standings, coinbase, coingecko, etherscan). Plus a precursor task that writes the missing decision-rule fact-pack files (rules 3, 6, 7, 8, 12) so future pages can use the `<DecisionRule>` callout component instead of falling back to plain markdown notes.

**Architecture:** Same patterns established in B1 — every widget MDX page = MDX + fact-pack markdown + (optional) demo TOML. Every concept page = MDX + (optional) demo TOML. C-tier minimum: intro paragraph + options table + ≥1 TOML example + 1 demo gif (where applicable) + Pitfalls callouts + RelatedPages cluster. Use **"Pitfalls"** as the section heading, never "Footguns".

**Demo gifs**: most data-feed widgets (rss_feed, mlb, mlb_standings, coinbase, coingecko) make live HTTP calls and won't render usefully in the 5-second CI capture window. For those: replace `<DemoGif>` with a callout note (Starlight `:::note`) explaining why — same pattern as `widgets/weather.mdx` from B1. Etherscan additionally requires `ETHERSCAN_API_KEY`. Concept pages: animations and borders get demos; sections-and-modes and frame-counters skip demos (the former is hard to demo in 5 sec across multiple sections; the latter is internal plumbing).

**Tech stack:** No new infrastructure. Same components, same renderer, same lint pipeline (which now includes `prettier --check` + `astro check` from PR #22). Subagents must run `pnpm run lint` before each commit; the pre-commit hook will catch drift but it's faster to clean up before commit.

---

## File map

### Decision-rule fact-pack files (5 — precursor for `<DecisionRule>` to work)

| File | Action | Rule subject |
|------|--------|--------------|
| `docs/content-source/rules/03-scroll-plus-stretch.md` | Create | Rule 3: text_align="scroll" + fit="stretch" rejected |
| `docs/content-source/rules/06-two-row-at-scale-4.md` | Create | Rule 6: two_row at scale=4 too narrow (warning) |
| `docs/content-source/rules/07-text-x-offset-with-scroll.md` | Create | Rule 7: text_x_offset + scroll text_align rejected |
| `docs/content-source/rules/08-hold-seconds-too-short.md` | Create | Rule 8: hold_seconds < 0.05 rejected |
| `docs/content-source/rules/12-animation-on-wrong-widget.md` | Create | Rule 12: animation only on message/countdown/gif/image |

### Concept pages (4)

| File | Action | Demo? |
|------|--------|-------|
| `docs/site/src/content/docs/concepts/sections-and-modes.mdx` | Create | no |
| `docs/site/src/content/docs/concepts/animations.mdx` | Create | yes (typewriter) |
| `docs/site/src/content/docs/concepts/borders.mdx` | Create | yes (rainbow chase) |
| `docs/site/src/content/docs/concepts/frame-counters.mdx` | Create | no |

### Widget pages (6)

| File | Action | Fact-pack? | Demo gif? |
|------|--------|------------|-----------|
| `docs/site/src/content/docs/widgets/rss_feed.mdx` | Create | yes | no (live fetch) |
| `docs/site/src/content/docs/widgets/mlb.mdx` | Create | yes | no (live fetch) |
| `docs/site/src/content/docs/widgets/mlb_standings.mdx` | Create | yes | no (live fetch) |
| `docs/site/src/content/docs/widgets/coinbase.mdx` | Create | yes | no (live fetch) |
| `docs/site/src/content/docs/widgets/coingecko.mdx` | Create | yes | no (live fetch) |
| `docs/site/src/content/docs/widgets/etherscan.mdx` | Create | yes | no (live fetch + API key) |

### Demo TOMLs (2 — only the two concept pages with demos)

| File | Action |
|------|--------|
| `docs/site/demos/concepts-animations.toml` | Create — typewriter on a message |
| `docs/site/demos/concepts-borders.toml` | Create — rainbow chase border |

### Fact-pack widget files (6)

| File | Action |
|------|--------|
| `docs/content-source/widgets/rss_feed.md` | Create |
| `docs/content-source/widgets/mlb.md` | Create |
| `docs/content-source/widgets/mlb_standings.md` | Create |
| `docs/content-source/widgets/coinbase.md` | Create |
| `docs/content-source/widgets/coingecko.md` | Create |
| `docs/content-source/widgets/etherscan.md` | Create |

---

## Per-page contract (refresher from B1)

Every widget MDX page is structurally a clone of `widgets/message.mdx` (which Plan A wrote). Every concept page mirrors the narrative tone of `concepts/display.mdx` / `concepts/fonts.mdx` / `concepts/color-providers.mdx` from B1. Subagents must read at least one of these as a style reference before drafting the new page.

Use `:::note` Starlight admonitions (NOT raw blockquotes) where a callout improves readability — same as `widgets/weather.mdx` does for "no demo gif".

---

## Task 1: Decision-rule fact-pack files (precursor)

**Files:**
- Create: `docs/content-source/rules/03-scroll-plus-stretch.md`
- Create: `docs/content-source/rules/06-two-row-at-scale-4.md`
- Create: `docs/content-source/rules/07-text-x-offset-with-scroll.md`
- Create: `docs/content-source/rules/08-hold-seconds-too-short.md`
- Create: `docs/content-source/rules/12-animation-on-wrong-widget.md`

After this task, future pages can use `<DecisionRule id="3" />` etc. instead of plain markdown notes. Each rule file follows the exact format established by `docs/content-source/rules/14-typewriter-on-image.md` (read it as a template).

- [ ] **Step 1: Read the rule-14 template**

```bash
cat docs/content-source/rules/14-typewriter-on-image.md
```

- [ ] **Step 2: Read the source for each rule**

The validator's static-check logic in `src/led_ticker/validate.py:_check_static` is the canonical statement of each rule. Read that function — every `ValidationIssue(rule=N, ...)` corresponds to one of these files. Also read CLAUDE.md "Pitfall validation" section for design rationale on each.

Rules to create:
- **Rule 3** — `text_align ∈ ("scroll", "scroll_over")` with `fit = "stretch"`. The validator rejects this because stretch fills the whole panel with no transparent regions for text to walk behind/over.
- **Rule 6** — `two_row` widget at section `scale = 4`. Logical canvas is only 64 px wide at that scale, which clips most handles. Recommend `scale = 2` override on the section.
- **Rule 7** — `text_x_offset != 0` with `text_align ∈ ("scroll", "scroll_over")`. text_x_offset is a static-text knob; for scrolling text the position is computed by the scroll loop and the offset is meaningless.
- **Rule 8** — `hold_seconds < 0.05` (50 ms). At sub-50 ms holds the engine starves; values that small are typically a unit-conversion typo (someone meant 50 instead of 0.05). Validator raises with a fix hint.
- **Rule 12** — `animation = "typewriter"` on a widget type other than `message`, `countdown`, `gif`, or `image`. Each rejected widget type produces a clearer error message at config-load.

- [ ] **Step 3: Create each file**

File template (copy from rule 14):

```markdown
## Rule N: <one-line title>

**SOURCE:** CLAUDE.md — "Pitfall validation" subsection.

**DETECT:** <when this fires; reference the validator's check>.

**SYMPTOM:** Config load raises with a message like `"<actual error string>"`.

**FIX:** <how to resolve — bullet list if multiple ways>.

<optional 1-paragraph design rationale>.
```

The actual error strings come from `validate.py:_check_static`. Quote them verbatim so the user can grep their console for matches.

- [ ] **Step 4: Verify formatting matches rule 14**

Each new file should pass `pnpm run lint` (prettier --check). The full build verification happens implicitly in Task 3 (which references `<DecisionRule id="12" />`) — if any of the new files are malformed, that build will fail with a clear error from the `<DecisionRule>` component's glob lookup.

```bash
cd docs/site && pnpm exec prettier --check ../content-source/rules/
```

- [ ] **Step 5: Commit**

```bash
git add docs/content-source/rules/
git commit -m "feat(docs): add fact-pack files for decision rules 3, 6, 7, 8, 12"
```

---

## Task 2: `concepts/sections-and-modes.mdx`

**Files:**
- Create: `docs/site/src/content/docs/concepts/sections-and-modes.mdx`

Concept page; no demo gif (multi-section configs are hard to capture in 5 sec).

- [ ] **Step 1: Read sources**

- `src/led_ticker/config.py` — `SectionConfig` fields, especially `mode`
- `src/led_ticker/ticker.py` — `run_forever_scroll()`, `run_infini_scroll()`, `run_swap()` methods
- `CLAUDE.md` "Display Flow" section

Key facts:
- Three modes: `forever_scroll`, `infini_scroll`, `swap`
- `forever_scroll` — all widgets in the section scroll side-by-side as a continuous stream with bullet-dot separators
- `infini_scroll` — each widget fully scrolls off before the next appears (one at a time)
- `swap` — held-and-scroll style (when text overflows it scrolls; otherwise it holds for `hold_time`); transitions fire between widgets
- `loop_count` — how many times the section repeats before moving to the next
- `hold_time` — dwell time per widget in `swap` mode after scroll completes
- Sections vs widgets: sections group widgets and define the run mode; widgets are the actual content

- [ ] **Step 2: Read the existing concepts pages for style**

Match the tone of `concepts/display.mdx` and `concepts/color-providers.mdx`.

- [ ] **Step 3: Write the page**

Structure: intro → 3 mode subsections (one per mode) with one TomlExample each → loop_count + hold_time sub-section → RelatedPages.

Suggested TomlExample for each mode:
- `forever_scroll`: 3 messages with bullet separators
- `infini_scroll`: 2 messages, each scrolls fully before the next appears
- `swap`: 2 messages with a `transition = "wipe_left"` between them

RelatedPages: `concepts/display`, `transitions/index`, `widgets/index`.

- [ ] **Step 4: Lint + build verify**

```bash
cd docs/site && pnpm run lint && pnpm run build 2>&1 | tail -3
```

- [ ] **Step 5: Commit**

```bash
git add docs/site/src/content/docs/concepts/sections-and-modes.mdx
git commit -m "feat(docs): concepts/sections-and-modes.mdx — forever_scroll vs infini_scroll vs swap"
```

---

## Task 3: `concepts/animations.mdx` + demo

**Files:**
- Create: `docs/site/src/content/docs/concepts/animations.mdx`
- Create: `docs/site/demos/concepts-animations.toml`

- [ ] **Step 1: Read sources**

- `src/led_ticker/animations.py` — `Typewriter` class. Fields: `frames_per_char` (default 3).
- CLAUDE.md "Color providers and animations" section — animations are independent from font_color; `frames_per_char` × ENGINE_TICK_MS (50 ms) = real ms-per-char.
- CLAUDE.md "Typewriter on image widgets" section — typewriter on gif/image is single-row only (rule 14).

Key facts:
- Currently one animation: `typewriter`
- Sets `animation = "typewriter"` on a widget; chars appear one at a time at `frames_per_char × 50 ms` per char
- Composes with any `font_color` (rainbow, gradient, etc.) — independent counters
- Valid on: `message`, `countdown`, `gif`, `image`. NOT on data widgets (rule 12).
- Per-effect counter: typewriter has `restart_on_visit = True` — reveals from scratch each time the section visits the widget

- [ ] **Step 2: Demo TOML**

```toml
# Demo: typewriter on a message with rainbow per-char color.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 5.0

[[playlist.section.widget]]
type = "message"
text = "Hello!"
animation = "typewriter"
frames_per_char = 6
font_color = "rainbow"
```

`frames_per_char = 6` (~300 ms/char) makes the type effect visible at the 5-sec capture window — at default 3 frames the reveal completes in <200 ms.

- [ ] **Step 3: Page structure**

Intro → "What `animation` does" → "Where it works" (rule 12 reference) → "Composing with font_color" → "Tuning frames_per_char" → RelatedPages.

Use `<DecisionRule id="12" />` (Task 1 just added that file).

- [ ] **Step 4: Lint + build + commit**

```bash
cd docs/site && pnpm run lint && pnpm run build 2>&1 | tail -3
git add docs/site/src/content/docs/concepts/animations.mdx docs/site/demos/concepts-animations.toml
git commit -m "feat(docs): concepts/animations.mdx — typewriter + demo"
```

---

## Task 4: `concepts/borders.mdx` + demo

**Files:**
- Create: `docs/site/src/content/docs/concepts/borders.mdx`
- Create: `docs/site/demos/concepts-borders.toml`

- [ ] **Step 1: Read sources**

- `src/led_ticker/borders.py` — `RainbowChaseBorder`, `ConstantBorder`. Fields per type.
- CLAUDE.md "Rainbow border" section — full design rationale.

Key facts:
- Border styles: `"rainbow"` (animated chase), constant `[r, g, b]`
- TOML accepts: string `"rainbow"`, RGB list `[r, g, b]`, or table `{style="rainbow", thickness=N, speed=N, char_offset=N}`
- Paints at PHYSICAL resolution (bypasses ScaledCanvas — `unwrap_to_real`). On bigsign at scale=4, the border traces the actual 256×64 panel edge, not the 64×16 logical canvas.
- Default speed = 4 (≈12 sec per perimeter revolution), char_offset = 6 (≈60 distinct hue cycles around 640-px perimeter)
- Restricted widget types: `message`, `countdown`, `two_row`, `gif`, `image`. Other widget types raise at config-load (rule 15 — but we haven't documented rule 15 yet, so use a plain markdown note).

- [ ] **Step 2: Demo TOML**

```toml
# Demo: rainbow chase border on a message.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 5.0

[[playlist.section.widget]]
type = "message"
text = "Hello"
border = {style = "rainbow", thickness = 1, speed = 4, char_offset = 6}
font_color = [255, 240, 200]
```

- [ ] **Step 3: Page structure**

Intro → DemoGif → "Border styles" (rainbow + constant) → "Tuning the chase" (speed, char_offset, thickness) → "Where it works" (note about supported widget types) → RelatedPages.

- [ ] **Step 4: Lint + build + commit**

```bash
cd docs/site && pnpm run lint && pnpm run build 2>&1 | tail -3
git add docs/site/src/content/docs/concepts/borders.mdx docs/site/demos/concepts-borders.toml
git commit -m "feat(docs): concepts/borders.mdx — rainbow chase + demo"
```

---

## Task 5: `concepts/frame-counters.mdx`

**Files:**
- Create: `docs/site/src/content/docs/concepts/frame-counters.mdx`

Advanced concept page; no demo gif (this is internal engine plumbing — visible only in subtle interactions like "rainbow chase phase keeps going across loop_count > 1 iterations").

- [ ] **Step 1: Read sources**

- `src/led_ticker/widgets/_frame_aware.py` — the `_FrameAware` mixin
- CLAUDE.md "Per-effect counters" subsection inside "Rainbow border" (search for "Per-effect counters")

Key facts:
- Frame-aware widgets track `_frame_count`, incremented per engine tick
- Each EFFECT on a widget gets its own counter via `_effect_frames` (e.g., font_color rainbow + border rainbow + typewriter all tick on independent counters)
- `restart_on_visit` is a class-level flag per effect: `True` means counter resets when the widget is shown (typewriter does this); `False` means counter advances continuously (rainbow / color_cycle / rainbow border do this)
- Section transitions reset effect state via `run_transition`'s `_reset_presenter` — entry-to-section is always fresh
- During transitions, frame counters are paused (`pause_frame()`) so the widget's effects don't drift mid-composit

This is an "advanced reference" page — most users won't read it, but the few who do (debugging "why did my rainbow text restart") need it.

- [ ] **Step 2: Page structure**

Intro → "Why frame counters exist" → "Restart-on-visit vs continuous" (table of which effects do which) → "Section transitions reset" → RelatedPages.

- [ ] **Step 3: Lint + build + commit**

```bash
cd docs/site && pnpm run lint && pnpm run build 2>&1 | tail -3
git add docs/site/src/content/docs/concepts/frame-counters.mdx
git commit -m "feat(docs): concepts/frame-counters.mdx — per-effect counters + visit reset"
```

---

## Task 6: `widgets/rss_feed.mdx` + fact-pack

**Files:**
- Create: `docs/content-source/widgets/rss_feed.md`
- Create: `docs/site/src/content/docs/widgets/rss_feed.mdx`

No demo gif — RSS fetches live data and the widget expands stories into TickerMessage instances asynchronously, which doesn't render usefully in a 5-sec capture.

- [ ] **Step 1: Read source**

`src/led_ticker/widgets/rss_feed.py`. Note `RSSFeedMonitor` has no `draw()` — stories expand into in-section TickerMessages. Record fields: `feed_url`, font/color knobs (inherited), `update_interval`, max stories.

- [ ] **Step 2: Write fact-pack file**

Standard markdown options table (same shape as `docs/content-source/widgets/message.md`).

- [ ] **Step 3: Write MDX page**

Clone `widgets/weather.mdx` as the structural template (since both have the "no demo gif, live fetch" framing). Replace DemoGif with a `:::note` admonition explaining no demo. Include a "Common patterns" section (e.g., a single feed, a feed with custom font_color, max-N stories). RelatedPages: `widgets/message`, `widgets/mlb`, `concepts/sections-and-modes`.

- [ ] **Step 4: Lint + build + commit**

```bash
cd docs/site && pnpm run lint && pnpm run build 2>&1 | tail -3
git add docs/content-source/widgets/rss_feed.md docs/site/src/content/docs/widgets/rss_feed.mdx
git commit -m "feat(docs): widgets/rss_feed.mdx + fact-pack (no demo, live fetch)"
```

---

## Task 7: `widgets/mlb.mdx` + fact-pack

**Files:**
- Create: `docs/content-source/widgets/mlb.md`
- Create: `docs/site/src/content/docs/widgets/mlb.mdx`

- [ ] **Step 1: Read source**

`src/led_ticker/widgets/mlb.py` — `MLBScoreMonitor`. Note its behavior: shows scores during games, "Final" after games end, postponements, series state. Free MLB API; no key required.

- [ ] **Step 2: Write fact-pack + MDX**

Same pattern as rss_feed. Common patterns: tracking a single team, tracking multiple teams, hide-when-no-game options. RelatedPages: `widgets/mlb_standings`, `widgets/rss_feed`.

- [ ] **Step 3: Lint + build + commit**

```bash
cd docs/site && pnpm run lint && pnpm run build 2>&1 | tail -3
git add docs/content-source/widgets/mlb.md docs/site/src/content/docs/widgets/mlb.mdx
git commit -m "feat(docs): widgets/mlb.mdx + fact-pack (no demo, live fetch)"
```

---

## Task 8: `widgets/mlb_standings.mdx` + fact-pack

**Files:**
- Create: `docs/content-source/widgets/mlb_standings.md`
- Create: `docs/site/src/content/docs/widgets/mlb_standings.mdx`

- [ ] **Step 1: Read source**

`src/led_ticker/widgets/mlb_standings.py` — `MLBStandingsMonitor`. Shows top-N teams + tracked teams. Detects offseason (returns last-completed-season standings).

- [ ] **Step 2-3: Same pattern as Task 7**

```bash
git add docs/content-source/widgets/mlb_standings.md docs/site/src/content/docs/widgets/mlb_standings.mdx
git commit -m "feat(docs): widgets/mlb_standings.mdx + fact-pack (no demo, live fetch)"
```

---

## Task 9: `widgets/coinbase.mdx` + fact-pack

**Files:**
- Create: `docs/content-source/widgets/coinbase.md`
- Create: `docs/site/src/content/docs/widgets/coinbase.mdx`

- [ ] **Step 1: Read source**

`src/led_ticker/widgets/crypto/coinbase.py` — `CoinbasePriceMonitor`. Public Coinbase API; no key needed. Shows current price + delta with up/down/neutral colors.

- [ ] **Step 2: Note shared color constants**

Coinbase / coingecko / etherscan all use `UP_TREND_COLOR` / `DOWN_TREND_COLOR` / `NEUTRAL_TREND_COLOR` from `colors.py`. Document these in each fact-pack so users know the convention.

- [ ] **Step 3: Same pattern as Task 7**

```bash
git add docs/content-source/widgets/coinbase.md docs/site/src/content/docs/widgets/coinbase.mdx
git commit -m "feat(docs): widgets/coinbase.mdx + fact-pack (no demo, live fetch)"
```

---

## Task 10: `widgets/coingecko.mdx` + fact-pack

**Files:**
- Create: `docs/content-source/widgets/coingecko.md`
- Create: `docs/site/src/content/docs/widgets/coingecko.mdx`

- [ ] **Step 1: Read source**

`src/led_ticker/widgets/crypto/coingecko.py`. Same shape as Coinbase but different API. Public, no key. Often a fallback when Coinbase data is unavailable.

- [ ] **Step 2-3: Same pattern**

The page should explicitly call out the relationship — "essentially `coinbase` but pointed at CoinGecko's API". Cross-link to `coinbase` in RelatedPages.

```bash
git add docs/content-source/widgets/coingecko.md docs/site/src/content/docs/widgets/coingecko.mdx
git commit -m "feat(docs): widgets/coingecko.mdx + fact-pack (no demo, live fetch)"
```

---

## Task 11: `widgets/etherscan.mdx` + fact-pack

**Files:**
- Create: `docs/content-source/widgets/etherscan.md`
- Create: `docs/site/src/content/docs/widgets/etherscan.mdx`

- [ ] **Step 1: Read source**

`src/led_ticker/widgets/crypto/etherscan.py` — `EtherscanGasMonitor`. Shows ETH gas prices (low/avg/high). **Requires `ETHERSCAN_API_KEY`** env var — surface this prominently in the page intro and fact-pack.

- [ ] **Step 2-3: Same pattern**

The MDX page's `:::note` admonition should explain BOTH: (1) no demo because live fetch, and (2) needs API key in your `.env` for any deployment to work.

```bash
git add docs/content-source/widgets/etherscan.md docs/site/src/content/docs/widgets/etherscan.mdx
git commit -m "feat(docs): widgets/etherscan.mdx + fact-pack (no demo, needs ETHERSCAN_API_KEY)"
```

---

## Task 12: Final verify

- [ ] **Step 1: Full lint pass**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -5
```
Expected: 0 errors, 0 warnings.

- [ ] **Step 2: Full build**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
```
Expected: 29 pages built (19 from end of B1 + 10 new).

- [ ] **Step 3: Verify all expected files exist**

```bash
test -f docs/site/dist/concepts/sections-and-modes/index.html && echo OK sections
test -f docs/site/dist/concepts/animations/index.html && echo OK animations
test -f docs/site/dist/concepts/borders/index.html && echo OK borders
test -f docs/site/dist/concepts/frame-counters/index.html && echo OK frame-counters
test -f docs/site/dist/widgets/rss_feed/index.html && echo OK rss_feed
test -f docs/site/dist/widgets/mlb/index.html && echo OK mlb
test -f docs/site/dist/widgets/mlb_standings/index.html && echo OK mlb_standings
test -f docs/site/dist/widgets/coinbase/index.html && echo OK coinbase
test -f docs/site/dist/widgets/coingecko/index.html && echo OK coingecko
test -f docs/site/dist/widgets/etherscan/index.html && echo OK etherscan
test -f docs/site/dist/demos/concepts-animations.gif && echo OK demo-animations
test -f docs/site/dist/demos/concepts-borders.gif && echo OK demo-borders
```
Expected: 12 OK lines.

- [ ] **Step 4: Run the Python test suite**

```bash
make test 2>&1 | tail -3
```
Expected: 1432 passed (no Python touched in this batch).

- [ ] **Step 5: Sidebar shows all the new sections**

Run `pnpm run dev` and visit `http://localhost:4321/`. Confirm sidebar groups:
- Concepts (now 7: display, sections-and-modes, fonts, color-providers, animations, borders, frame-counters)
- Widgets (now 13: index + 12 widgets)
- Transitions (4: index + push, wipe, sprite)
- Assets (1: emoji)
- Pitfalls

- [ ] **Step 6: No commit** — push and open the PR.
