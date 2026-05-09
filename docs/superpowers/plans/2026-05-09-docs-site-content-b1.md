# Docs Site Content — Plan B1: Foundations + Most-Used

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Author the first batch of docs site content — three foundation concept pages, the most-used widget pages (countdown, two_row, weather, gif, image), the wipe + sprite transition family pages, the emoji asset page, and the widget/transition index pages. Every page hits the C-tier minimum: intro paragraph + options table (where applicable) + ≥1 TOML example + 1 demo gif (where applicable) + RelatedPages cluster. Pages use the established components (`<DemoGif>`, `<TomlExample>`, `<OptionsTable>`, `<DecisionRule>`, `<RelatedPages>`).

**Architecture:** Per page, three artifacts: an `MDX` page in `docs/site/src/content/docs/<area>/<name>.mdx`, a fact-pack file in `docs/content-source/<area>/<name>.md` (skipped for concepts and index pages), and a demo TOML in `docs/site/demos/<name>.toml` (skipped for index pages, weather, and concepts). Demo gifs auto-generate from the TOMLs via the `build-demos.mjs` prebuild script. Patterns and components established in Plan A — every page in this plan is structurally a clone of `widgets/message.mdx` (for widgets) or `transitions/push.mdx` (for transitions) or stylistically narrative (for concepts).

**Tech stack:** No new infrastructure — Astro Starlight v0.39.x + the components already in place + the renderer + dorny/paths-filter + dependabot all unchanged.

**Style note (from the brainstorm):** Content tone is **mix matching page type** — concepts pages are narrative-heavy, widget/transition pages are reference-heavy. Page priority is **most-used-first** (foundations + popular widgets in this batch; less-used widgets / data feeds in B2; tools and showcase in B3). Use **"Pitfalls"** as the section heading throughout — never "Footguns".

---

## File map

### Concept pages (3) — narrative, no fact-pack

| File | Action | Notes |
|------|--------|-------|
| `docs/site/src/content/docs/concepts/display.mdx` | Create | Explains rows / cols / chain / parallel / pixel_mapper / default_scale |
| `docs/site/src/content/docs/concepts/fonts.mdx` | Create | BDF vs hires, font_size, font_threshold, when to use which |
| `docs/site/src/content/docs/concepts/color-providers.mdx` | Create | constant / rainbow / gradient / color_cycle / random + per-char vs whole-string |

### Widget pages (6: index + 5 widgets — message done in Plan A)

| File | Action | Notes |
|------|--------|-------|
| `docs/site/src/content/docs/widgets/index.mdx` | Create | Decision tree: which widget to pick |
| `docs/site/src/content/docs/widgets/countdown.mdx` | Create | TickerCountdown — message variant with date arithmetic |
| `docs/site/src/content/docs/widgets/two_row.mdx` | Create | TwoRowMessage — held top + scrolling bottom |
| `docs/site/src/content/docs/widgets/weather.mdx` | Create | WeatherWidget — needs WEATHERAPI_KEY (no demo gif; static example) |
| `docs/site/src/content/docs/widgets/gif.mdx` | Create | GifPlayer — animated frames at native res |
| `docs/site/src/content/docs/widgets/image.mdx` | Create | StillImage — single PNG/JPG; mirrors gif feature surface |

### Transition pages (3: index + 2 families — push done in Plan A)

| File | Action | Notes |
|------|--------|-------|
| `docs/site/src/content/docs/transitions/index.mdx` | Create | Grid + selection table |
| `docs/site/src/content/docs/transitions/wipe.mdx` | Create | wipe_left/right/up/down + alternating + random |
| `docs/site/src/content/docs/transitions/sprite.mdx` | Create | nyancat / pokeball / baseball / sailor_moon / pacman families |

### Asset pages (1)

| File | Action | Notes |
|------|--------|-------|
| `docs/site/src/content/docs/assets/emoji.mdx` | Create | All 17 lowres slugs + 13 hires variants |

### Fact-pack files (8 — one per widget/transition with an options table)

| File | Action |
|------|--------|
| `docs/content-source/widgets/countdown.md` | Create |
| `docs/content-source/widgets/two_row.md` | Create |
| `docs/content-source/widgets/weather.md` | Create |
| `docs/content-source/widgets/gif.md` | Create |
| `docs/content-source/widgets/image.md` | Create |
| `docs/content-source/transitions/wipe.md` | Create |
| `docs/content-source/transitions/sprite.md` | Create |
| `docs/content-source/emoji.md` | Create |

### Demo TOMLs (8 — one per page that has a demo gif)

| File | Action |
|------|--------|
| `docs/site/demos/concepts-fonts.toml` | Create — BDF vs hires comparison |
| `docs/site/demos/concepts-color-providers.toml` | Create — rainbow vs gradient vs color_cycle |
| `docs/site/demos/widget-countdown.toml` | Create |
| `docs/site/demos/widget-two_row.toml` | Create |
| `docs/site/demos/widget-gif.toml` | Create |
| `docs/site/demos/widget-image.toml` | Create |
| `docs/site/demos/transitions-wipe.toml` | Create |
| `docs/site/demos/transitions-sprite.toml` | Create |
| `docs/site/demos/assets-emoji.toml` | Create |

(`concepts/display.mdx`, the index pages, and `widgets/weather.mdx` deliberately skip the demo gif — display is conceptual, indexes are listings, weather requires an API key not available in CI.)

### Sidebar update

| File | Action |
|------|--------|
| `docs/site/astro.config.mjs` | Modify — add `Concepts` and `Assets` sidebar groups |

---

## Per-page content contract

Every widget MDX page follows this template (clone `widgets/message.mdx` and adapt):

```mdx
---
title: <widget> widget
description: <one-sentence summary>
---

import DemoGif from '../../../components/DemoGif.astro';
import TomlExample from '../../../components/TomlExample.astro';
import OptionsTable from '../../../components/OptionsTable.astro';
import DecisionRule from '../../../components/DecisionRule.astro';
import RelatedPages from '../../../components/RelatedPages.astro';

<one-paragraph intro: what the widget does, when you'd reach for it>

<DemoGif src="/demos/<slug>.gif" caption="<one-line caption>" />

<TomlExample title="Minimal example" code={`<minimal toml snippet>`} />

## Options

<OptionsTable source="widgets/<name>" />

## Common patterns

<2-3 short patterns, each with a TomlExample and one sentence of context>

## Pitfalls

<1-2 DecisionRule references with id matching the relevant rule>

<RelatedPages slugs={["widgets/<related>", "concepts/<related>"]} />
```

Every transition family MDX page follows the `transitions/push.mdx` pattern — opening sentence, demo gif of one variant, OptionsTable from the fact-pack file (lists all variants in the family), behavior notes, RelatedPages cluster.

Every concept MDX page is narrative-heavy: opens with what the concept is, why it exists, and the vocabulary; weaves in TomlExample snippets to illustrate; ends with RelatedPages.

Every fact-pack widget file (`docs/content-source/widgets/<name>.md`) is JUST a markdown options table — same shape as `docs/content-source/widgets/message.md`. Source the option list by reading the widget's Python source: look at the `@attrs.define` class fields and the constructor (`__init__` for Python attrs classes). Each row: `| option | type | default | description |`.

Every fact-pack transition family file (`docs/content-source/transitions/<family>.md`) starts with the family description, then a markdown table of variants with columns `| name | direction | best for |`. Source the variants list by grepping `src/led_ticker/transitions/<family>.py` for `@register_transition`.

---

## Task 1: Set up new directories and update sidebar

**Files:**
- Modify: `docs/site/astro.config.mjs`
- Create empty dirs: `docs/site/src/content/docs/concepts/`, `docs/site/src/content/docs/assets/`, `docs/content-source/widgets/` (already exists from Plan A), `docs/content-source/transitions/` (exists)

- [ ] **Step 1: Create the new content directories**

```bash
mkdir -p docs/site/src/content/docs/concepts docs/site/src/content/docs/assets
```

- [ ] **Step 2: Update sidebar in `docs/site/astro.config.mjs`**

Edit the sidebar array. Find the existing array and change it to:

```js
      sidebar: [
        { label: "Home", link: "/" },
        { label: "Getting started", link: "/getting-started/" },
        {
          label: "Concepts",
          items: [{ autogenerate: { directory: "concepts" } }],
        },
        {
          label: "Widgets",
          items: [{ autogenerate: { directory: "widgets" } }],
        },
        {
          label: "Transitions",
          items: [{ autogenerate: { directory: "transitions" } }],
        },
        {
          label: "Assets",
          items: [{ autogenerate: { directory: "assets" } }],
        },
        {
          label: "Pitfalls",
          link: "/pitfalls/",
        },
      ],
```

- [ ] **Step 3: Smoke-test the build (with no new pages yet, sidebar autogenerate of empty dirs should still build)**

```bash
cd docs/site && pnpm install --frozen-lockfile && pnpm run build 2>&1 | tail -10
```

If empty `concepts/` and `assets/` dirs cause a Starlight error, add temporary placeholder index pages and remove them in later tasks. Otherwise commit and proceed.

- [ ] **Step 4: Commit**

```bash
git add docs/site/astro.config.mjs docs/site/src/content/docs/concepts/ docs/site/src/content/docs/assets/
git commit -m "feat(docs): scaffold concepts/ and assets/ directories + sidebar"
```

---

## Task 2: `concepts/display.mdx`

**Files:**
- Create: `docs/site/src/content/docs/concepts/display.mdx`

Concept page — narrative, no fact-pack, no demo gif.

- [ ] **Step 1: Read the source for accurate facts**

Read `src/led_ticker/config.py` lines 14–32 (the `DisplayConfig` dataclass). Note every field, type, and default. Also read CLAUDE.md "Per-section `content_height`" section (around line 100) for the scale-vs-content_height relationship.

- [ ] **Step 2: Create `docs/site/src/content/docs/concepts/display.mdx`**

Page structure:

```mdx
---
title: Display
description: How rows, cols, chain, parallel, scale, and pixel_mapper combine into a logical canvas.
---

import TomlExample from '../../../components/TomlExample.astro';
import RelatedPages from '../../../components/RelatedPages.astro';

<intro paragraph: led-ticker drives a panel of LEDs. The [display] block in your TOML
tells the engine the panel's physical geometry — how many pixels, how the panels chain
together, and what scaling to apply. Get this right and everything else "just works";
get it wrong and content prints to a 3-pixel slice or runs off the edge.>

## The two reference signs

<two-paragraph block: small sign (Pi 4 + 5×32×16 = 160×16) and bigsign
(Pi 5 + 8× P3 32×64 vertical-serpentine 2×4 = 256×64). Show both [display]
blocks side-by-side via TomlExample.>

<TomlExample title="Small sign" code={`[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60
slowdown_gpio = 2`} />

<TomlExample title="Bigsign" code={`[display]
rows = 32
cols = 64
chain = 8
parallel = 1
pixel_mapper = "Remap:256,64|192,32n|192,0n|128,32n|128,0n|64,32n|64,0n|0,32n|0,0n"
default_scale = 4
brightness = 60
slowdown_gpio = 3
pwm_bits = 8
rp1_rio = 1`} />

## Logical canvas vs real panel

<one paragraph: when default_scale > 1, the engine creates a ScaledCanvas wrapper.
Drawing logic stays at "16-tall logical content"; the wrapper expands every SetPixel
to a scale×scale block on the real canvas. Hard ceiling: content_height × scale ≤
panel_h_real. For bigsign at scale=4, content_height ≤ 16.>

## Per-section overrides

<one short paragraph: scale and content_height can be overridden per-section.
TwoRow widgets typically use scale=2 to widen the logical canvas to 128 px.>

<TomlExample code={`[[playlist.section]]
mode = "swap"
scale = 2
content_height = 24
hold_time = 4.0`} />

<RelatedPages slugs={["concepts/fonts", "widgets/two_row", "hardware/bigsign"]} />
```

- [ ] **Step 3: Build verify**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
```
Expected: 7 pages built (was 6, +1 for display).

- [ ] **Step 4: Commit**

```bash
git add docs/site/src/content/docs/concepts/display.mdx
git commit -m "feat(docs): concepts/display.mdx — rows/cols/scale/pixel_mapper concept"
```

---

## Task 3: `concepts/fonts.mdx`

**Files:**
- Create: `docs/site/src/content/docs/concepts/fonts.mdx`
- Create: `docs/site/demos/concepts-fonts.toml`

Concept page with one demo gif comparing BDF and Inter.

- [ ] **Step 1: Read sources for accurate facts**

- `src/led_ticker/fonts/__init__.py` — bundled BDF aliases and dimensions
- `src/led_ticker/fonts/hires_loader.py` — hires font resolution and `font_threshold` semantics
- CLAUDE.md "Hi-res fonts on the bigsign" and "Per-widget `font_threshold`" sections

Key facts to surface:
- Bundled BDF: `5x8`, `6x10`, `6x12`, `7x13`. Cell heights: 8, 10, 12, 13 px.
- Bundled hires: `Inter-Regular`, `Inter-Bold`. Specify `font_size` (real px) explicitly.
- `font_threshold` (0–255, default 128) — rasterization cutoff. Lower = thicker glyphs.
- Match thresholds within a family (Bold + Regular at same threshold) to preserve weight contrast.
- BDF ignores threshold (pre-rasterized).

- [ ] **Step 2: Create the demo config `docs/site/demos/concepts-fonts.toml`**

```toml
# Demo: BDF vs hires-Inter side-by-side via swap transition.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 2.5

[[playlist.section.widget]]
type = "message"
text = "BDF 6x12"
font = "6x12"

[[playlist.section.widget]]
type = "message"
text = "Inter-Bold"
font = "Inter-Bold"
font_size = 14
font_threshold = 128
```

- [ ] **Step 3: Create `docs/site/src/content/docs/concepts/fonts.mdx`**

```mdx
---
title: Fonts
description: BDF bitmap fonts vs hi-res TTF/OTF — what to pick and why.
---

import DemoGif from '../../../components/DemoGif.astro';
import TomlExample from '../../../components/TomlExample.astro';
import RelatedPages from '../../../components/RelatedPages.astro';

<intro: every text-bearing widget — message, countdown, two_row, weather, the text
overlay on gif/image — picks a font. led-ticker ships two flavors, and the right
choice depends on panel scale and viewing distance.>

<DemoGif src="/demos/concepts-fonts.gif" caption="BDF 6x12 (left) vs Inter-Bold @ 14px (right)" />

## BDF: the bundled bitmap fonts

<one paragraph: pre-rasterized, designed pixel-by-pixel. Crisp at small sizes, no
threshold tuning, instant load. Bundled aliases: 5x8, 6x10, 6x12, 7x13. The numbers
are pixel cell width × height. Default font is 6x12.>

<TomlExample code={`[[playlist.section.widget]]
type = "message"
text = "Hello"
font = "6x12"   # ← font default; can omit`} />

## Hires (TTF / OTF) for the bigsign

<one paragraph: at scale=4, BDF text is 12 real pixels tall — small on a 64-tall
panel. Hires fonts (Inter-Regular and Inter-Bold are bundled) render at any
real-pixel size. Specify `font_size` in pixels explicitly. For brand fonts (e.g.,
Adobe Beloved Sans), drop the .otf into config/fonts/ and reference by name.>

<TomlExample code={`[[playlist.section.widget]]
type = "message"
text = "Hello"
font = "Inter-Bold"
font_size = 28
font_threshold = 80`} />

## font_threshold

<one short paragraph: hires fonts get rasterized to 1-bit at draw time. 0–255,
default 128. Lower threshold = thicker (more pixels exceed cutoff). Thin-stroked
fonts (Beloved Sans Regular at 24-32 px) need ~80 to read; the default 128 leaves
glyphs visibly broken. **Pair Bold + Regular at the same threshold** within a family,
or weight contrast inverts.>

## Decision tree

| Panel | Distance | Recommended |
|-------|----------|-------------|
| Small sign (160×16) | any | BDF 6x12 (default) — perfect at 1× |
| Bigsign, close (≤6 ft) | ≤ 6 ft | BDF or Inter @ 16-22 |
| Bigsign, medium (6–20 ft) | ≤ 20 ft | Inter @ 22-28 |
| Bigsign, far (across street) | > 20 ft | Inter @ 28-32 |

<RelatedPages slugs={["concepts/display", "concepts/color-providers", "widgets/message"]} />
```

- [ ] **Step 4: Build verify**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
```
Expected: 8 pages built (was 7).

- [ ] **Step 5: Commit**

```bash
git add docs/site/src/content/docs/concepts/fonts.mdx docs/site/demos/concepts-fonts.toml
git commit -m "feat(docs): concepts/fonts.mdx — BDF vs hires + threshold tuning"
```

---

## Task 4: `concepts/color-providers.mdx`

**Files:**
- Create: `docs/site/src/content/docs/concepts/color-providers.mdx`
- Create: `docs/site/demos/concepts-color-providers.toml`

- [ ] **Step 1: Read source for accurate facts**

- `src/led_ticker/color_providers.py` — defines `_ConstantColor`, `Rainbow`, `ColorCycle`, `Gradient`, `Random`. Each has a `per_char` flag.
- CLAUDE.md "Color providers and animations" section.

Key facts:
- Constant: `font_color = [r, g, b]` — single color
- Rainbow: `font_color = "rainbow"` — per-char hue sweep
- ColorCycle: `font_color = "color_cycle"` — whole-string hue rotation
- Gradient: `font_color = {style="gradient", from=[...], to=[...]}` — per-char interpolation
- Random: `font_color = "random"` — picks once on visit (whole-string)
- Per-char (`rainbow`, `gradient`) iterate characters; whole-string (the rest) get one color per draw

- [ ] **Step 2: Create `docs/site/demos/concepts-color-providers.toml`**

```toml
# Demo: rotates through 3 color providers on the same text.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 3.0

[[playlist.section.widget]]
type = "message"
text = "rainbow"
font_color = "rainbow"

[[playlist.section.widget]]
type = "message"
text = "color_cycle"
font_color = "color_cycle"

[[playlist.section.widget]]
type = "message"
text = "gradient"
font_color = {style = "gradient", from = [255, 100, 100], to = [100, 100, 255]}
```

- [ ] **Step 3: Create `docs/site/src/content/docs/concepts/color-providers.mdx`**

```mdx
---
title: Color providers
description: Constant / rainbow / gradient / color_cycle / random — how `font_color` accepts more than just RGB.
---

import DemoGif from '../../../components/DemoGif.astro';
import TomlExample from '../../../components/TomlExample.astro';
import RelatedPages from '../../../components/RelatedPages.astro';

<intro: every text-bearing widget's `font_color` (and `top_color`/`bottom_color` on
two_row + image widgets) accepts five flavors — a constant RGB, three named
providers, and an inline-table gradient. Some animate over time, some pick once
per visit.>

<DemoGif src="/demos/concepts-color-providers.gif" caption="rainbow → color_cycle → gradient" />

## The five providers

| Provider | Syntax | Per-char? | Animates? |
|----------|--------|-----------|-----------|
| Constant | `[r, g, b]` | no | no |
| Rainbow | `"rainbow"` | **yes** | yes (hue sweep) |
| Gradient | `{style="gradient", from=[...], to=[...]}` | **yes** | no (frozen interpolation) |
| ColorCycle | `"color_cycle"` | no | yes (whole-string hue rotation) |
| Random | `"random"` | no | no (picks once on visit) |

Per-char providers iterate characters and assign a unique color to each — that's
how `rainbow` produces a stripe across letters. Whole-string providers compute
one color per draw and apply it to the whole message.

## Picking the right one

<short prose: When you want a static color (or are matching brand), use a constant
RGB list. When you want subtle motion, color_cycle. When you want maximum visual
impact — kid-section flair, attention grabbers — rainbow. When you want polish
that respects palette constraints, gradient between two brand colors. Random is
useful for variety in long-running displays.>

## Inline emoji + per-char providers

Per-char rainbow / gradient sweeps continuously **across** `:slug:` emoji
boundaries — the sprite still renders in its native colors, and the text
between/around emoji gets per-character colors with the index advancing across
emoji segments.

<TomlExample code={`[[playlist.section.widget]]
type = "message"
text = ":star: Now Enrolling :star:"
font_color = "rainbow"`} />

## Animations vs colors

`font_color` and `animation` are independent axes — a `message` widget can have
`font_color = "rainbow"` AND `animation = "typewriter"` and the chars type out
in rainbow with independent counters. See **animations** (B2).

<RelatedPages slugs={["concepts/fonts", "widgets/message", "assets/emoji"]} />
```

- [ ] **Step 4: Build + commit**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
git add docs/site/src/content/docs/concepts/color-providers.mdx docs/site/demos/concepts-color-providers.toml
git commit -m "feat(docs): concepts/color-providers.mdx — provider vocabulary + demo"
```
Expected: 9 pages built.

---

## Task 5: `widgets/index.mdx` (decision tree)

**Files:**
- Create: `docs/site/src/content/docs/widgets/index.mdx`

Index page — listing + decision tree. No fact-pack, no demo.

- [ ] **Step 1: Create the page**

```mdx
---
title: Widgets
description: The 12 built-in widgets — what each one does and how to pick.
---

import RelatedPages from '../../../components/RelatedPages.astro';

led-ticker ships **12 built-in widget types**. Each is configured by a
\`[[playlist.section.widget]]\` block in your TOML. This page is the menu — pick the
one that fits your data, then read its page for the full options list.

## By data source

| Widget | Source | Use when |
|--------|--------|----------|
| [`message`](/widgets/message/) | static text | most lines on most signs |
| [`countdown`](/widgets/countdown/) | local clock + a target date | "X days until …" |
| [`two_row`](/widgets/two_row/) | two static lines | held-handle + scrolling promo (storefront) |
| [`weather`](/widgets/weather/) | WeatherAPI.com | forecast / current conditions |
| [`rss_feed`](/widgets/rss_feed/) | any RSS URL | news / blog headlines |
| [`mlb`](/widgets/mlb/) | MLB free API | game scores / series state |
| [`mlb_standings`](/widgets/mlb_standings/) | MLB free API | standings (top N + tracked teams) |
| [`coinbase`](/widgets/coinbase/) | Coinbase | crypto price |
| [`coingecko`](/widgets/coingecko/) | CoinGecko | crypto price (alternative source) |
| [`etherscan`](/widgets/etherscan/) | Etherscan | Ethereum gas |
| [`gif`](/widgets/gif/) | local file | animated gifs / webp / multi-frame images |
| [`image`](/widgets/image/) | local file | static PNG / JPG |

## By complexity

- **Just text:** \`message\`, \`countdown\`. No external dependencies.
- **Two text rows (storefront layout):** \`two_row\` at section \`scale=2\`.
- **Live data (background fetch):** \`weather\`, \`rss_feed\`, \`mlb\`, \`mlb_standings\`, the three crypto widgets. Each has retry + exponential backoff.
- **Visual:** \`gif\`, \`image\`. Both support text overlay, fit modes (pillarbox / letterbox / stretch / crop), and per-row two-row layouts.

## Common knobs

Most widgets share these — see the [message widget](/widgets/message/) for the
canonical surface:

- \`font\`, \`font_size\`, \`font_threshold\` — see [Fonts](/concepts/fonts/)
- \`font_color\` — see [Color providers](/concepts/color-providers/)
- \`bg_color\` — RGB list, painted across the panel before content
- \`border\` — animated rainbow chase or constant ring
- \`animation\` — typewriter (where supported)

<RelatedPages slugs={["widgets/message", "widgets/gif", "transitions/index"]} />
```

- [ ] **Step 2: Build + commit**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
git add docs/site/src/content/docs/widgets/index.mdx
git commit -m "feat(docs): widgets/index.mdx — decision tree"
```
Expected: 10 pages built.

---

## Task 6: `widgets/countdown.mdx` + fact-pack + demo

**Files:**
- Create: `docs/content-source/widgets/countdown.md`
- Create: `docs/site/demos/widget-countdown.toml`
- Create: `docs/site/src/content/docs/widgets/countdown.mdx`

- [ ] **Step 1: Read source to extract options**

Read `src/led_ticker/widgets/message.py` — `TickerCountdown` class. Note its
unique fields beyond TickerMessage: `countdown_date` (date), `prefix` (string,
default `"Days "`), `suffix` (string, default `""`).

It otherwise inherits the entire TickerMessage option surface: `text`, `font`,
`font_size`, `font_threshold`, `font_color`, `bg_color`, `border`, `animation`,
`frames_per_char`, `padding`, `text_y_offset`.

- [ ] **Step 2: Write `docs/content-source/widgets/countdown.md`**

```markdown
The `countdown` widget extends `message` with date arithmetic — every draw,
it renders `<prefix><N><suffix>` where N is the number of days from today
to `countdown_date`.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `text` | string | required | Trailing message after the day count (e.g. `"Until Spring"`). Inline emoji supported. |
| `countdown_date` | date | required | Target date in TOML date syntax: `2026-12-25`. |
| `prefix` | string | `"Days "` | Text before the day count. Set to `""` for just the number + text. |
| `suffix` | string | `""` | Text immediately after the day count, before the message. |
| `font` | string | `"6x12"` | BDF or hires font name. |
| `font_size` | int | (BDF cell height) | Real-pixel font size for hires fonts. Required if `font` is hires. |
| `font_threshold` | int 0–255 | `128` | Rasterization threshold for hires fonts. |
| `font_color` | RGB / string / table | `[255, 255, 0]` | Constant, `"rainbow"`, `"color_cycle"`, `"random"`, or `{style="gradient", from=..., to=...}`. |
| `bg_color` | RGB list | none | Background fill before text. |
| `border` | string / table | none | `"rainbow"`, `[r,g,b]`, or `{style="rainbow", thickness=N, speed=N, char_offset=N}`. |
| `animation` | string | none | `"typewriter"` for character-by-character reveal. |
| `padding` | int | `6` | Horizontal padding (logical px) when scrolling. |
```

- [ ] **Step 3: Write `docs/site/demos/widget-countdown.toml`**

```toml
# Demo: a countdown widget targeting a fixed near-future date.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 4.0

[[playlist.section.widget]]
type = "countdown"
text = "Until Summer"
countdown_date = 2026-06-21
font_color = "rainbow"
```

- [ ] **Step 4: Write `docs/site/src/content/docs/widgets/countdown.mdx`**

Use `widgets/message.mdx` as the structural template. The intro should be one
sentence saying the widget shows "X Days Until Y" by computing the day delta
from today. Include the demo gif, a minimal TOML example with `countdown_date`,
a "Common patterns" section (custom prefix/suffix, branded color), and 1
DecisionRule callout for rule 12 (animation only on supported types — countdown
is supported).

- [ ] **Step 5: Build verify + commit**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
git add docs/content-source/widgets/countdown.md docs/site/demos/widget-countdown.toml docs/site/src/content/docs/widgets/countdown.mdx
git commit -m "feat(docs): widgets/countdown.mdx + fact-pack + demo"
```
Expected: 11 pages built.

---

## Task 7: `widgets/two_row.mdx` + fact-pack + demo

**Files:**
- Create: `docs/content-source/widgets/two_row.md`
- Create: `docs/site/demos/widget-two_row.toml`
- Create: `docs/site/src/content/docs/widgets/two_row.mdx`

- [ ] **Step 1: Read source**

Read `src/led_ticker/widgets/two_row.py`. The widget is heavy — record every
field from the `@attrs.define` class. Pay attention to the per-row prefix
convention: `top_*` and `bottom_*` for everything dual-row.

Also read CLAUDE.md "Two-row widget" section for design rationale (scale=2 for
storefront layouts, content_height = 24 for breathing room).

- [ ] **Step 2: Write `docs/content-source/widgets/two_row.md`**

Markdown table covering the surface. Group fields logically (top row, bottom
row, layout, shared). Same shape as countdown.md but more rows.

- [ ] **Step 3: Write `docs/site/demos/widget-two_row.toml`**

```toml
# Demo: two_row at scale=2 (storefront-window typical).
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
scale = 1
content_height = 16
loop_count = 1
hold_time = 4.0

[[playlist.section.widget]]
type = "two_row"
top_text = "@example"
top_color = [225, 48, 108]
top_align = "center"
bottom_text = "Now booking — all levels welcome!"
bottom_color = [255, 240, 200]
bottom_align = "left"
```

(Note: this demo runs on the small-sign-flavored renderer (160×16 panel), so
scale=1. Real bigsign deployments use scale=2 + content_height=24.)

- [ ] **Step 4: Write `docs/site/src/content/docs/widgets/two_row.mdx`**

Follow the message.mdx template. The intro should explain: held top + scrolling
bottom, ideal for storefront-window @handle + promo line, designed for `scale=2`
on the bigsign. Include 2-3 patterns: brand-handle layout, asymmetric row split
(`top_row_height`), per-row fonts (`top_font` + `bottom_font` for typographic
hierarchy). DecisionRule for rule 6 (two_row at scale=4 warning).

- [ ] **Step 5: Build + commit**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
git add docs/content-source/widgets/two_row.md docs/site/demos/widget-two_row.toml docs/site/src/content/docs/widgets/two_row.mdx
git commit -m "feat(docs): widgets/two_row.mdx + fact-pack + demo"
```
Expected: 12 pages built.

---

## Task 8: `widgets/weather.mdx` + fact-pack (no demo gif)

**Files:**
- Create: `docs/content-source/widgets/weather.md`
- Create: `docs/site/src/content/docs/widgets/weather.mdx`

Weather widget needs `WEATHERAPI_KEY` to fetch live data — not available in CI.
Skip the demo gif. Use a static photo or a TomlExample-only intro instead.

- [ ] **Step 1: Read source**

`src/led_ticker/widgets/weather.py`. List all fields and defaults.

- [ ] **Step 2: Write `docs/content-source/widgets/weather.md`**

Same shape as the others. Note `WEATHERAPI_KEY` env var requirement.

- [ ] **Step 3: Write `docs/site/src/content/docs/widgets/weather.mdx`**

Follow the message.mdx template, but replace the `<DemoGif>` with a callout box
(a Starlight `<Aside type="note">` if the project uses one — otherwise a plain
markdown blockquote) explaining that live demos require the API key. Show 1-2
TomlExample patterns (basic, with custom location + units, with two-color
font_color + font_color_temp).

- [ ] **Step 4: Build + commit**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
git add docs/content-source/widgets/weather.md docs/site/src/content/docs/widgets/weather.mdx
git commit -m "feat(docs): widgets/weather.mdx + fact-pack (no demo, needs API key)"
```
Expected: 13 pages built.

---

## Task 9: `widgets/gif.mdx` + fact-pack + demo

**Files:**
- Create: `docs/content-source/widgets/gif.md`
- Create: `docs/site/demos/widget-gif.toml`
- Create: `docs/site/src/content/docs/widgets/gif.mdx`

- [ ] **Step 1: Read source**

`src/led_ticker/widgets/gif.py` and `src/led_ticker/widgets/_image_base.py` (the
shared text-overlay surface). Note: the `gif` widget shares **most** of its
surface with `image` — text overlay options, fit modes, scroll layering. Only
`gif`-specific options are `gif_loops` and the gif decoder behaviors.

Also CLAUDE.md "GIF widget and Still-image widget" section for the shared surface.

- [ ] **Step 2: Write `docs/content-source/widgets/gif.md`**

Comprehensive options table. Group fields: image (path, fit, image_align),
single-row text overlay (text, text_align, text_valign, scroll_speed_ms, font,
etc.), two-row text overlay (top_text, bottom_text, top_*, bottom_*),
gif-specific (gif_loops). Reuses many surfaces from `_image_base.py`.

- [ ] **Step 3: Write `docs/site/demos/widget-gif.toml`**

Use a bundled gif from `config/assets/`:

```toml
# Demo: gif widget with pikachu wave + scrolling text overlay.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 4.0

[[playlist.section.widget]]
type = "gif"
path = "../../../config/assets/pika_wave_transparent.gif"
fit = "pillarbox"
image_align = "left"
text = "Hello!"
text_align = "scroll_over"
gif_loops = 999
font_color = [255, 200, 100]
```

(Path is relative to the demo TOML file's location at docs/site/demos/. Adjust
if the renderer resolves paths from elsewhere — verify by running locally.)

- [ ] **Step 4: Write `docs/site/src/content/docs/widgets/gif.mdx`**

Follow the message.mdx template. Intro: plays animated gifs/webp at native
panel resolution, with an optional text overlay. Patterns: silent gif, gif
with overlay text scrolling in front (scroll_over), gif with text walking
behind a transparent silhouette (scroll). DecisionRule for rule 3
(scroll+stretch invalid) and rule 14 (typewriter on gif/image single-row only).

- [ ] **Step 5: Build + commit**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
git add docs/content-source/widgets/gif.md docs/site/demos/widget-gif.toml docs/site/src/content/docs/widgets/gif.mdx
git commit -m "feat(docs): widgets/gif.mdx + fact-pack + demo"
```
Expected: 14 pages built.

---

## Task 10: `widgets/image.mdx` + fact-pack + demo

**Files:**
- Create: `docs/content-source/widgets/image.md`
- Create: `docs/site/demos/widget-image.toml`
- Create: `docs/site/src/content/docs/widgets/image.mdx`

`image` (StillImage) shares almost everything with `gif`. The `image.md`
fact-pack file should reuse the same surface as `gif.md` minus `gif_loops` (use
`hold_seconds` instead). The MDX page can reference gif.mdx as "the same widget,
but for static images".

- [ ] **Step 1: Read source**

`src/led_ticker/widgets/still.py`. Confirm shared surface with gif via
`_image_base.py`.

- [ ] **Step 2-4: Write the three files**

Demo TOML:
```toml
# Demo: still image widget with scrolling text overlay.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 4.0

[[playlist.section.widget]]
type = "image"
path = "../../../config/assets/bunny-transparent.png"
fit = "pillarbox"
image_align = "left"
text = "Bunny says hi"
text_align = "scroll_over"
hold_seconds = 4.0
font_color = [200, 100, 255]
```

- [ ] **Step 5: Build + commit**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
git add docs/content-source/widgets/image.md docs/site/demos/widget-image.toml docs/site/src/content/docs/widgets/image.mdx
git commit -m "feat(docs): widgets/image.mdx + fact-pack + demo"
```
Expected: 15 pages built.

---

## Task 11: `transitions/index.mdx`

**Files:**
- Create: `docs/site/src/content/docs/transitions/index.mdx`

- [ ] **Step 1: Write the page**

```mdx
---
title: Transitions
description: How content swaps between widgets — push, wipe, sprite, and special effects.
---

import RelatedPages from '../../../components/RelatedPages.astro';

A transition runs between widgets in \`swap\` mode (and between sections
regardless of mode). The pick is set in your \`[transitions]\` block — \`default\`
applies between widgets, \`between_sections\` applies at section boundaries.
Each section can override with \`transition = "..."\`.

## The four families

| Family | What it looks like | Best for |
|--------|---------|----------|
| [Push](/transitions/push/) | Old slides off, new slides in from the opposite side | General purpose, news-ticker feel |
| [Wipe](/transitions/wipe/) | Sweep line erases content, leaves new in its wake | Clean / professional |
| [Sprite](/transitions/sprite/) | Pixel-art character (Pikachu, Pac-Man, baseball, …) crosses the panel | Fun / themed |
| [Special](/transitions/special/) (B3) | Cut, dissolve, color flash, split, scroll | Variety, ambient |

## Picking a transition

| Tone | Default | Between sections |
|------|---------|------------------|
| Minimal | \`cut\` or \`wipe_left\` | \`cut\` |
| Playful | \`pokeball_alternating\` or \`nyancat_alternating\` | \`pokeball_alternating\` |
| Info-dense | \`push_up\` | \`dissolve\` |
| Branded-pro | \`wipe_alternating\` (with \`transition_color\` from the brand palette) | \`dissolve\` |

## Tuning

- \`transition_duration\` (seconds): default 0.5; range 0.3–1.5 is typical
- \`easing\`: \`linear\` (sharp) / \`ease_out\` / \`ease_in_out\` (default for pushes)
- \`transition_color\`: RGB list — used by wipe sweep lines and color_flash
- \`transition_colors\`: list of RGB lists — used by \`wipe_alternating\` / \`wipe_random\` for a custom color pool

<RelatedPages slugs={["transitions/push", "transitions/wipe", "transitions/sprite"]} />
```

- [ ] **Step 2: Build + commit**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
git add docs/site/src/content/docs/transitions/index.mdx
git commit -m "feat(docs): transitions/index.mdx — family menu + selection table"
```
Expected: 16 pages built.

---

## Task 12: `transitions/wipe.mdx` + fact-pack + demo

**Files:**
- Create: `docs/content-source/transitions/wipe.md`
- Create: `docs/site/demos/transitions-wipe.toml`
- Create: `docs/site/src/content/docs/transitions/wipe.mdx`

- [ ] **Step 1: Read source**

`src/led_ticker/transitions/wipe.py`. Note variants: `wipe_left`, `wipe_right`,
`wipe_up`, `wipe_down`, `wipe_alternating`, `wipe_random`. Each has a default
sweep color (cyan for left, magenta for right, white for up, green for down).
`wipe_alternating` cycles through directions; `wipe_random` randomizes both
direction and (from a default or custom) color pool.

- [ ] **Step 2: Write `docs/content-source/transitions/wipe.md`**

```markdown
The `wipe` family uses a stationary outgoing widget plus a colored sweep line that erases the panel direction-by-direction, then reveals the incoming widget. Snappier than push (no co-motion) and slightly more dramatic.

| Name | Sweep direction | Default color | Best for |
|------|------|---------|----------|
| `wipe_left` | right→left | cyan | General purpose, professional feel |
| `wipe_right` | left→right | magenta | Variety |
| `wipe_up` | bottom→top | white | Vertical change |
| `wipe_down` | top→bottom | green | Variety |
| `wipe_alternating` | cycles through L→R→U→D | cycles colors | Dynamic variety |
| `wipe_random` | random direction (no immediate repeats) + random color from pool | from `transition_colors` (default: cyan/magenta/white/green) | Unpredictable variety |

## Tuning

- `transition_duration` (seconds): 0.4-0.8 feels right
- `transition_color` ([r, g, b]): override the sweep color on a single direction
- `transition_colors` (list of [r, g, b]): custom color pool for `wipe_alternating` / `wipe_random`

## Pitfalls

Wipe transitions ignore `transition_color` on `wipe_alternating` / `wipe_random` UNLESS you also provide `transition_colors` — alternating uses a built-in palette by default, random reads the pool field.
```

- [ ] **Step 3: Write `docs/site/demos/transitions-wipe.toml`**

```toml
# Demo: wipe_alternating between two messages.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[transitions]
default = "wipe_alternating"
duration = 0.6
transition_colors = [[0,255,255], [255,0,255], [255,255,255], [0,255,0]]

[[playlist.section]]
mode = "swap"
loop_count = 2
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "First"

[[playlist.section.widget]]
type = "message"
text = "Second"
```

- [ ] **Step 4: Write `docs/site/src/content/docs/transitions/wipe.mdx`**

Use `transitions/push.mdx` as the structural template — opening sentence,
DemoGif, OptionsTable from fact-pack, behavior notes, RelatedPages.

- [ ] **Step 5: Build + commit**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
git add docs/content-source/transitions/wipe.md docs/site/demos/transitions-wipe.toml docs/site/src/content/docs/transitions/wipe.mdx
git commit -m "feat(docs): transitions/wipe.mdx + fact-pack + demo"
```
Expected: 17 pages built.

---

## Task 13: `transitions/sprite.mdx` + fact-pack + demo

**Files:**
- Create: `docs/content-source/transitions/sprite.md`
- Create: `docs/site/demos/transitions-sprite.toml`
- Create: `docs/site/src/content/docs/transitions/sprite.mdx`

- [ ] **Step 1: Read source**

Each sprite family is its own file:
- `src/led_ticker/transitions/nyancat.py`
- `src/led_ticker/transitions/pokeball.py`
- `src/led_ticker/transitions/baseball.py`
- `src/led_ticker/transitions/sailor_moon.py`
- `src/led_ticker/transitions/pacman.py`

Each defines `<name>` + `<name>_reverse` + `<name>_alternating`. Some have hires
variants (nyancat, pokeball, baseball — see CLAUDE.md "Hi-res transitions").

- [ ] **Step 2: Write `docs/content-source/transitions/sprite.md`**

```markdown
The sprite family runs a pixel-art character across the panel that erases the outgoing widget and reveals the incoming one. Themed and fun — best for retail / kid-facing displays where personality matters more than minimalism.

| Family | Variants | Hires? | Best for |
|--------|----------|--------|----------|
| `nyancat` | `nyancat`, `nyancat_reverse`, `nyancat_alternating` | yes | General playful |
| `pokeball` | `pokeball`, `pokeball_reverse`, `pokeball_alternating` | yes | Pop-culture variety |
| `baseball` | `baseball`, `baseball_reverse`, `baseball_alternating` | yes | Sports sections |
| `sailor_moon` | `sailor_moon`, `sailor_moon_reverse`, `sailor_moon_alternating` | no | Magical / sparkle aesthetic |
| `pacman` | `pacman`, `pacman_reverse`, `pacman_alternating` | no | Retro arcade |

## Variants

- **Forward** (`<name>`): sprite enters from the left, exits right
- **Reverse** (`<name>_reverse`): sprite enters from the right, exits left (sprite is flipped)
- **Alternating** (`<name>_alternating`): cycles forward → reverse → forward each swap

## Hires on the bigsign

`nyancat`, `pokeball`, and `baseball` auto-activate hi-res sprites when the canvas is at scale > 1 (i.e., on the bigsign). The hi-res variants are noticeably more detailed and read better at distance.

## Tuning

- `transition_duration`: sprite transitions feel right at 1.5–2.5 seconds — the sprite needs time to traverse
- `show_pikachu` / `show_pokeball`: pokeball variants only — toggle whether each sprite renders
```

- [ ] **Step 3: Write `docs/site/demos/transitions-sprite.toml`**

```toml
# Demo: pokeball_alternating between two messages.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[transitions]
default = "pokeball_alternating"
duration = 1.8

[[playlist.section]]
mode = "swap"
loop_count = 2
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "First"

[[playlist.section.widget]]
type = "message"
text = "Second"
```

- [ ] **Step 4: Write `docs/site/src/content/docs/transitions/sprite.mdx`**

Follow `transitions/push.mdx` template.

- [ ] **Step 5: Build + commit**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
git add docs/content-source/transitions/sprite.md docs/site/demos/transitions-sprite.toml docs/site/src/content/docs/transitions/sprite.mdx
git commit -m "feat(docs): transitions/sprite.mdx + fact-pack + demo"
```
Expected: 18 pages built.

---

## Task 14: `assets/emoji.mdx` + fact-pack + demo

**Files:**
- Create: `docs/content-source/emoji.md`
- Create: `docs/site/demos/assets-emoji.toml`
- Create: `docs/site/src/content/docs/assets/emoji.mdx`

- [ ] **Step 1: Read source**

`src/led_ticker/pixel_emoji.py` — extract `EMOJI_REGISTRY` (lowres) and
`HIRES_REGISTRY` (hires). 17 lowres + 13 hires-only-shaped via the same
slug names; `pokeball` and `pride` are hires-only.

- [ ] **Step 2: Write `docs/content-source/emoji.md`**

```markdown
Use `:slug:` inside any text-bearing widget to render a pixel-art icon inline. Each is an 8×8 sprite in its native colors; the surrounding text uses your `font_color`.

The slug list rots fast as new icons are added. The source of truth is `src/led_ticker/pixel_emoji.py` — `grep -E '^\s+"[a-z_]+":' src/led_ticker/pixel_emoji.py` lists every slug. As of 2026-05-08:

| Slug | Description | Hires variant |
|------|-------------|---------------|
| `:baseball:` | White ball with red stitching | yes |
| `:bunny:` | Bunny silhouette | yes |
| `:cat:` | Cat | yes |
| `:cloud:` | Cloud icon | yes |
| `:email:` | Envelope (white) | yes |
| `:flower:` | Pink flower | yes |
| `:fog:` | Fog icon | yes |
| `:heart:` | Heart | yes |
| `:instagram:` | Instagram glyph (magenta) | yes |
| `:moon:` | Crescent moon | yes |
| `:partly_cloudy:` | Sun + cloud | yes |
| `:pokeball:` | Pokeball | hires only — won't render at scale=1 |
| `:pride:` | Pride flag stripes | hires only |
| `:rain:` | Rain icon | yes |
| `:snow:` | Snow icon | yes |
| `:star:` | Yellow star | yes |
| `:sun:` | Sun icon | yes |
| `:taco:` | Taco | yes |
| `:thunder:` | Thunder icon | yes |

## Hires on the bigsign

When the panel is at `default_scale > 1`, slugs with a hires variant auto-render the higher-detail sprite — same horizontal footprint (8 logical columns), 16× more detail per cell. On `scale=1` (small sign), the lowres 8×8 sprite is used.

`:moon:` is the canonical hires example: 32×32 sprite with circle-subtraction shading. Hires-only slugs (`pokeball`, `pride`) render nothing on a small sign.

## Adding a new emoji

Edit `src/led_ticker/pixel_emoji.py`. Define an 8×8 pixel-data tuple (`(x, y, r, g, b)`), add it to `EMOJI_REGISTRY`. For hires, draw a 32×32 variant and add it to `HIRES_REGISTRY`. The renderer auto-handles the scale dispatch.
```

- [ ] **Step 3: Write `docs/site/demos/assets-emoji.toml`**

```toml
# Demo: a row of inline emoji on a single message.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 4.0

[[playlist.section.widget]]
type = "message"
text = ":taco: :star: :flower: :sun:"
font_color = [255, 240, 200]
```

- [ ] **Step 4: Write `docs/site/src/content/docs/assets/emoji.mdx`**

```mdx
---
title: Inline emoji
description: 17+ pixel-art glyphs you can drop into any message text via `:slug:`.
---

import DemoGif from '../../../components/DemoGif.astro';
import TomlExample from '../../../components/TomlExample.astro';
import OptionsTable from '../../../components/OptionsTable.astro';
import RelatedPages from '../../../components/RelatedPages.astro';

Drop \`:slug:\` into any message text to render a pixel-art icon inline:

<DemoGif src="/demos/assets-emoji.gif" caption=":taco: :star: :flower: :sun:" />

<TomlExample title="Example" code={`[[playlist.section.widget]]
type = "message"
text = ":taco: Taco Tuesday!"`} />

## Available slugs

<OptionsTable source="emoji" />

<RelatedPages slugs={["widgets/message", "concepts/color-providers"]} />
```

- [ ] **Step 5: Build + commit**

```bash
cd docs/site && pnpm run build 2>&1 | tail -5
git add docs/content-source/emoji.md docs/site/demos/assets-emoji.toml docs/site/src/content/docs/assets/emoji.mdx
git commit -m "feat(docs): assets/emoji.mdx + fact-pack + demo"
```
Expected: 19 pages built.

---

## Final verify

- [ ] **Run the full docs build**

```bash
cd docs/site && pnpm run build 2>&1 | tail -10
```
Expected: 19 pages built (5 from Plan A + 14 from Plan B1).

- [ ] **Verify all demo gifs render**

```bash
ls -lh docs/site/public/demos/
```
Expected: at least 9 .gif files (the 2 from Plan A plus 7 new ones — concept-fonts, concept-color-providers, widget-countdown, widget-two_row, widget-gif, widget-image, transitions-wipe, transitions-sprite, assets-emoji; weather has no demo).

- [ ] **Run the Python test suite**

```bash
make test 2>&1 | tail -3
```
Expected: 1432 passed, 0 regressions (Plan B1 doesn't touch Python).

- [ ] **Sidebar shows all the new sections**

Open `docs/site/dist/index.html` (or run `pnpm run dev` and visit
`http://localhost:4321/`); confirm sidebar groups: Home, Getting started,
Concepts (3), Widgets (7 — index + 6 widgets), Transitions (4 — index + 3
families), Assets (1), Pitfalls.

- [ ] **No commit needed if final verify is green** — push the branch and open the PR.
