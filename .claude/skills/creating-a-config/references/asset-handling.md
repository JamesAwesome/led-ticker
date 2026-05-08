<!-- Derived from CLAUDE.md sections: "Hi-res fonts on the bigsign", "Per-widget font_threshold", "Match thresholds within a font family", "Inline Emoji", "GIF widget and Still-image widget". Last synced: 2026-05-07. -->

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
| "RSS feed at <url>" | `[rss_feed]` widget with `feed_url = "<url>"` |
| "Mets fan" | `[mlb]` widget with `teams = ["NYM"]` |
| "BTC price" | `[coinbase]` widget with `symbol = "BTC"`, `currency = "USD"` |
| "Countdown to <date>" | `[countdown]` widget with `date = "<YYYY-MM-DD>"` |

**No silent network fetches.** If user gives an asset URL, the skill asks them to download and provide the local path.
