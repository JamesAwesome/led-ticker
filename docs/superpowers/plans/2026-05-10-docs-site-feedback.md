# Docs site feedback implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan PR-by-PR. Steps use checkbox (`- [ ]`) syntax for tracking. Each PR is independently mergeable.

**Goal:** Address seven pieces of docs-site feedback uncovered after PR #34/#36 shipped, organized as four independent PRs that can ship in any order.

**Architecture:** All four PRs touch the docs site at `docs/site/` (Astro Starlight) and adjacent sources. No runtime code changes. Each PR is shaped to be small enough to review independently. The plan duplicates the smallsign / bigsign configs onto the docs pages rather than importing them (intentional — embedded copies stay stable as the runtime configs evolve).

**Tech stack:** Astro Starlight v0.39.x, MDX, Pillow-rasterized hi-res fonts, the existing demo render pipeline (`tools/render_demo/render.py`), and the test stub canvas.

**Source of truth:** Reviews from the UX engineer and technical writer landed before this plan. The convergent calls they made are baked into the task choices below.

---

## PR overview

| PR | Title | Size | Independent? |
|----|-------|------|--------------|
| 1 | README technical refocus + stale API removal | Small | Yes |
| 2 | Pitfalls + rules normalization (H3 template + missing-rule audit + framing) | Medium | Yes |
| 3 | Sections-and-modes gifs + sidebar parenthetical drop + landing-page navbar | Medium | Yes |
| 4 | Embed smallsign + bigsign configs on hardware pages | Small-Medium | Yes |

Sequencing: PR 1 first (cleans up stale info that future PRs link to). PR 2 + PR 3 + PR 4 in parallel afterward.

---

## PR 1: README technical refocus + stale API removal

**Goal:** Strip README.md to ~80 technical lines and point all user-facing prose at `docs.ledticker.dev`. Remove `pulse` / `bounce` / `presentation` API references that were deleted in the color-providers rework but still ship in README.

### File structure

**Modify:**
- `README.md` — strip to ~80 lines; replace user-facing content with docs-site links

**No new files. No deletions.**

### Task 1.1: Audit current README and identify stale + duplicated content

- [ ] **Step 1: Find stale API references**

Run: `grep -n "pulse\|bounce\|presentation" README.md`

Expected output: matches around lines 122, 129, 130, 136. Confirm `pulse` / `bounce` are listed as Text Presentation Effects and `presentation = "typewriter"` appears as a TOML snippet.

- [ ] **Step 2: Identify sections to move to docs site**

Read README.md sections. Tag each section's destination:

| README section | Action |
|---|---|
| `## Quick Start` | Keep, tighten |
| `## Configuration` (line 35-186 — full transition table, emoji table, widget catalog) | **Remove**; link to docs |
| `## Adding a New Widget` (line 187-230) | **Remove**; link to docs (or contributor guide if one exists) |
| `## Validating a Config` | Keep, tighten |
| `## Development` | Keep |
| `## Deployment` | Keep |
| `## Hardware` | Keep, tighten |

### Task 1.2: Replace the README

- [ ] **Step 1: Write the new README**

Replace the entire file with:

```markdown
# led-ticker

An asyncio Python toolkit that drives RGB LED matrix panels from a Raspberry Pi via a TOML config. Two reference builds share one codebase and one Docker image:

- **Smallsign** — Pi 4 + 5× chained 16×32 panels = 160×16 logical canvas
- **Bigsign** — Pi 5 + 8× P3 32×64 panels in a 2×4 vertical-serpentine layout = 256×64 canvas

Full documentation: <https://docs.ledticker.dev>

## Quick start

```bash
git clone https://github.com/JamesAwesome/led-ticker.git
cd led-ticker
make dev
cp config/config.example.toml config/config.toml  # or config.bigsign.example.toml
led-ticker --config config/config.toml
```

For hardware setup, BOM, and wiring diagrams see [docs.ledticker.dev/hardware](https://docs.ledticker.dev/hardware/).

## Configuration

Everything is configured via a TOML file. Three reference configs ship in `config/`:

- `config.example.toml` — smallsign starter (160×16)
- `config.bigsign.example.toml` — bigsign with `pixel_mapper`, scaling, RP1 tuning (256×64)
- `config.moonbunny.example.toml` — real-world bigsign storefront layout

Full config reference: <https://docs.ledticker.dev/reference/config-options/>. Per-widget pages document every knob: <https://docs.ledticker.dev/widgets/>.

Pre-flight a config before deploying:

```bash
make validate CONFIG=config/config.toml
```

`led-ticker validate` checks the config against a registry of decision rules — bad font sizes, scroll-mode + stretch collisions, content-height overflow. Exits non-zero on errors. Useful in CI. Full output format: <https://docs.ledticker.dev/tools/validate/>.

## Development

```bash
make dev        # Install deps (requires uv)
make test       # Run tests (no Docker needed; uses test stubs for rgbmatrix)
make lint       # Run ruff linter
make format     # Auto-format code
make validate CONFIG=config/config.toml  # Pre-flight a config
```

Tests use a stub `rgbmatrix` package so they run on any machine — no Raspberry Pi or Docker required. ~1450 tests, ~2 min on a laptop.

Contributor guide (adding a widget, adding a transition, the test-stub canvas contract): <https://docs.ledticker.dev/reference/contributing/> *(if this URL 404s, see `CLAUDE.md` in this repo for the load-bearing invariants).*

## Deployment

### Docker on Raspberry Pi

```bash
docker compose up -d
```

The compose file mounts `./config` read-only into the container so you edit TOML on the host and the container picks it up on restart.

### Systemd

`deploy/led-ticker.service` and `deploy/install.sh` manage auto-start and auto-restart-on-crash. Full deploy walkthrough: <https://docs.ledticker.dev/hardware/building-your-own/>.

## Hardware

The single Docker image detects the SoC at runtime and selects the BCM2711 GPIO backend (Pi 4) or the RP1 PIO/RIO backend (Pi 5). On the Pi 5 the runtime CLI accepts `--led-rp1-rio=0|1` for the RP1 backend mode; for chain ≥ 2 with flicker raise `slowdown_gpio` from 2 to 3+.

Hardware reference (BOM, wiring, panel-tuning knobs): <https://docs.ledticker.dev/hardware/>.

## License

See [LICENSE](LICENSE).
```

- [ ] **Step 2: Verify no stale API references remain**

Run: `grep -n "pulse\|bounce\|presentation" README.md`

Expected output: zero matches.

- [ ] **Step 3: Verify docs-site links resolve**

The links use the `docs.ledticker.dev` domain which is behind Cloudflare Access (can't curl directly). Sanity-check the PATHS exist on the local build instead:

```bash
make docs-build
for path in hardware reference/config-options widgets tools/validate reference/contributing hardware/building-your-own; do
  out="docs/site/dist/${path}/index.html"
  if [ -f "$out" ]; then echo "OK: $path"; else echo "MISSING: $path"; fi
done
```

Expected output: every path returns OK except `reference/contributing` which legitimately doesn't exist today (the README intentionally points to a future page that may exist; the parenthetical fallback to CLAUDE.md covers it).

If any other path returns MISSING, fix the README link to point at the existing page (e.g. `hardware/` instead of a deeper path that doesn't exist).

### Task 1.3: Commit and open PR

- [ ] **Step 1: Stage and commit**

```bash
git add README.md
git commit -m "docs(readme): technical refocus + stale API removal

Strip README.md to ~80 lines focused on the developer-cloning-the-repo
audience. Move all end-user / config-author content to the docs site at
docs.ledticker.dev with deep links to specific reference pages.

Remove three stale entries from the Text Presentation Effects table:
- 'pulse' (removed in the color-providers/animations rework)
- 'bounce' (removed in the same rework)
- 'presentation = ...' TOML snippet (replaced by 'animation = ...')

Sections removed and replaced with docs-site links:
- Full transition catalogue (30-entry table) -> /transitions/
- Inline emoji sprite table -> /assets/emoji/
- Built-in widget catalogue -> /widgets/
- 'Adding a New Widget' walkthrough -> contributor guide / CLAUDE.md

Sections kept and tightened:
- Quick Start
- Configuration (with deep links per knob)
- Development commands
- Deployment summary
- Hardware short-reference
"
```

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin HEAD
gh pr create --title "docs(readme): technical refocus + stale API removal" --body "$(cat <<'EOF'
## Summary

Strip README.md to ~80 technical lines for the developer-cloning-the-repo audience. Move all end-user / config-author content to docs.ledticker.dev with deep links.

## Stale API removed

The 'Text Presentation Effects' table listed three names that don't exist in the codebase anymore — \`pulse\`, \`bounce\`, and the \`presentation = ...\` TOML key. All three were removed in the color-providers/animations rework. The README was still shipping them as a recommendation for new users.

## What stays

- Quick Start (clone, install, run)
- Configuration intro pointing at the three example configs + docs-site reference
- Development commands (\`make dev\` / \`test\` / \`lint\` / \`validate\`)
- Deployment summary (Docker + systemd)
- Hardware short-reference (Pi 4 vs Pi 5 backend selection)

## What moves

| Removed from README | New home |
|---|---|
| Full transitions table | <https://docs.ledticker.dev/transitions/> |
| Emoji sprite table | <https://docs.ledticker.dev/assets/emoji/> |
| Widget catalog | <https://docs.ledticker.dev/widgets/> |
| 'Adding a New Widget' walkthrough | Contributor guide (or CLAUDE.md fallback) |

## Test plan

- [x] \`grep -n 'pulse\\|bounce\\|presentation' README.md\` returns no matches
- [x] All docs-site paths linked from README resolve on a local \`make docs-build\`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## PR 2: Pitfalls + rules normalization

**Goal:** Standardize every page's Pitfalls section to `### <H3 heading>` followed by prose, audit the decision-rule registry for gaps, and wire rule 22 onto the relevant widget pages. Add a one-line "what these numbered rules mean" sentence on every page that uses `<DecisionRule>` so readers don't get the numbered label as a cold open.

### File structure

**Modify:**
- `docs/site/src/content/docs/pitfalls.mdx` — add rule 22 row
- `docs/site/src/content/docs/widgets/gif.mdx` — add H3 headings to Pitfalls
- `docs/site/src/content/docs/widgets/image.mdx` — add H3 headings to Pitfalls
- `docs/site/src/content/docs/widgets/two_row.mdx` — add H3 headings + DecisionRule for rule 22
- `docs/site/src/content/docs/widgets/message.mdx` — verify Pitfalls already matches the template (it does)
- `docs/site/src/content/docs/widgets/countdown.mdx` — verify (current state: bare paragraph about typewriter; needs H3)
- `docs/site/src/content/docs/concepts/animations.mdx` — H3 already exists; verify framing line is added
- `docs/site/src/content/docs/transitions/special.mdx` — check for Pitfalls (likely none)
- `docs/site/src/content/docs/widgets/{weather,rss_feed,mlb,mlb_standings,coinbase,coingecko,etherscan}.mdx` — audit for Pitfalls sections, normalize each

**No new files.**

### Task 2.1: Audit Pitfalls sections across every widget + concept page

- [ ] **Step 1: Enumerate all Pitfalls sections**

Run: `grep -rln "^## Pitfalls" docs/site/src/content/docs/`

Expected output: ~12 files. Record each one for the normalization passes below.

- [ ] **Step 2: For each file, categorize its current state**

For each file from Step 1, read the Pitfalls section and mark which of these three states it's in:

- **State A — clean**: every pitfall already has an H3 heading. No work needed.
- **State B — listy paragraphs**: pitfalls are bold-lead paragraphs without H3 headings. Needs H3 added to each.
- **State C — bare DecisionRule**: opens with a `<DecisionRule>` and no H3 above it. Needs H3 wrapper.

Sample expected categorization (verify by reading each file):

| File | State |
|---|---|
| `widgets/message.mdx` | A — has `### Typewriter is single-row only` above `<DecisionRule id="14" />` |
| `widgets/gif.mdx` | C + B (DecisionRule at top, then bold paragraphs) |
| `widgets/image.mdx` | C + B (same shape as gif, plus extra paragraphs) |
| `widgets/two_row.mdx` | B (only bold paragraphs, no DecisionRule) |
| `widgets/countdown.mdx` | B (one bold paragraph about typewriter) |
| `concepts/animations.mdx` | A — has `### Typewriter is single-row only` |

### Task 2.2: Standardize Pitfalls structure on widgets/gif.mdx

- [ ] **Step 1: Read the current Pitfalls section**

Open `docs/site/src/content/docs/widgets/gif.mdx`, find the section starting `## Pitfalls`.

- [ ] **Step 2: Rewrite the section with H3 headings**

Replace the entire Pitfalls section (from `## Pitfalls` through the closing `<RelatedPages ...>`) with:

```mdx
## Pitfalls

Numbered rules below are validator rules — `led-ticker validate` checks them automatically. See [Pitfalls (all rules)](/pitfalls/) for the full list.

### Typewriter is single-row only

<DecisionRule id="14" />

### `text_align="scroll"` requires a non-opaque image

The `scroll` mode displays scrolling text through transparent / pillarbox regions of the image. With `fit="stretch"` the image fills every pixel and there are no transparent regions for the text to walk behind — so the text is always hidden. Use `text_align="scroll_over"` for a marquee over a fullscreen image, or use a `.gif` with transparency and `fit="pillarbox"`.

### `text_x_offset` is rejected with scroll modes

`text_x_offset` only applies to static text placement (`text_align = "left"` or `"right"`). With `scroll` or `scroll_over`, the marquee's x position is driven by the scroll logic; adding a constant offset would skew the entry point in a confusing way. Remove the offset, or switch to a static `text_align`.

<RelatedPages slugs={["widgets/image", "widgets/two_row", "assets/emoji"]} />
```

- [ ] **Step 3: Verify build**

```bash
make docs-build
```

Expected output: `[build] Complete!`. If the build fails, check for unclosed MDX tags or stray characters from the replacement.

### Task 2.3: Standardize Pitfalls structure on widgets/image.mdx

- [ ] **Step 1: Replace the Pitfalls section with**

```mdx
## Pitfalls

Numbered rules below are validator rules — `led-ticker validate` checks them automatically. See [Pitfalls (all rules)](/pitfalls/) for the full list.

### Typewriter is single-row only

<DecisionRule id="14" />

### `text_align="scroll"` requires a non-opaque image

The `scroll` mode displays scrolling text through transparent / pillarbox regions of the image. With `fit="stretch"` the image fills every pixel and there are no transparent regions for the text to walk behind. Use `text_align="scroll_over"` for a marquee over a fullscreen image, or use a PNG with transparency and `fit="pillarbox"`.

### `text_x_offset` is rejected with scroll modes

`text_x_offset` only applies to static text placement (`text_align = "left"` or `"right"`). With `scroll` or `scroll_over`, the marquee's x position is driven by the scroll logic; adding a constant offset would skew the entry point in a confusing way. Remove the offset, or switch to a static `text_align`.

### `hold_seconds` must be at least 0.05

Values below 0.05 (50 ms) are rejected at config-load. The minimum exists because anything shorter than one engine tick would skip rendering entirely.

### Animated source files only show frame 0

If you pass an animated `.gif` or `.webp` to the `image` widget, only the first frame is decoded and displayed. Use the [`gif`](/widgets/gif/) widget for animation — it shares the entire `image` text-overlay surface plus per-frame mechanics.

<RelatedPages slugs={["widgets/gif", "widgets/two_row", "assets/emoji"]} />
```

- [ ] **Step 2: Verify build**

```bash
make docs-build
```

### Task 2.4: Standardize Pitfalls structure on widgets/two_row.mdx + wire rule 22

- [ ] **Step 1: Replace the Pitfalls section**

Rule 22 (font line-height exceeds per-row band) was added to the registry in PR #34 but never wired to a page that surfaces it. It belongs on `two_row.mdx` — the widget where the constraint bites first.

Replace the Pitfalls section with:

```mdx
## Pitfalls

Numbered rules below are validator rules — `led-ticker validate` checks them automatically. See [Pitfalls (all rules)](/pitfalls/) for the full list.

### Per-row font line-height must fit the row band

<DecisionRule id="22" />

### `scale=4` is too narrow for handles

At section `scale = 4` the bigsign's logical canvas is only 64 pixels wide (256 real px ÷ 4 = 64 logical px), which clips most @handles mid-word. The `two_row` widget is designed for `scale = 2` (128 logical px) on the bigsign. Override the section's scale with `scale = 2` — you can mix scales across sections in the same config.

### `content_height` hard ceiling

On the bigsign at `scale = 4` the maximum `content_height` is 16 (`16 × 4 = 64` real rows). For `scale = 2` the ceiling is 32. Values above the ceiling push the logical canvas taller than the real panel; rows near the edges clip silently. For per-row breathing room use `top_text_y_offset` / `bottom_text_y_offset` rather than over-specifying `content_height`.

<RelatedPages slugs={["widgets/message", "widgets/gif", "concepts/display"]} />
```

- [ ] **Step 2: Verify build**

```bash
make docs-build
```

### Task 2.5: Standardize Pitfalls structure on widgets/countdown.mdx

- [ ] **Step 1: Open the file and find the Pitfalls section**

Open `docs/site/src/content/docs/widgets/countdown.mdx`. The Pitfalls section is currently a single bold-lead paragraph about typewriter not being supported.

- [ ] **Step 2: Replace with H3-styled version**

```mdx
## Pitfalls

Numbered rules below are validator rules — `led-ticker validate` checks them automatically.

### Typewriter is not available on `countdown`

`animation = "typewriter"` is only supported on `message`, `gif`, and `image` widgets. Adding it to a `countdown` widget raises at config load. For dynamic color on a countdown use [`font_color = "rainbow"`](/concepts/color-providers/) or a gradient instead.
```

- [ ] **Step 3: Verify build**

```bash
make docs-build
```

### Task 2.6: Add rule 22 to /pitfalls/ page

- [ ] **Step 1: Update pitfalls.mdx**

Open `docs/site/src/content/docs/pitfalls.mdx`. Add rule 22 to the **Hard rules (errors)** section, between rule 14 and the `## Soft rules` heading:

```mdx
<DecisionRule id="14" />

<DecisionRule id="22" />

## Soft rules (warnings)
```

- [ ] **Step 2: Verify build**

```bash
make docs-build
```

- [ ] **Step 3: Open /pitfalls/ in a browser (optional sanity check)**

```bash
make docs-dev
# Open http://localhost:4321/pitfalls/ and confirm rule 22 renders inline with the others.
# Ctrl-C when done.
```

### Task 2.7: Audit remaining widget pages and normalize any Pitfalls present

- [ ] **Step 1: Check the rest of the widget pages**

```bash
for f in docs/site/src/content/docs/widgets/{weather,rss_feed,mlb,mlb_standings,coinbase,coingecko,etherscan}.mdx; do
  if grep -q "^## Pitfalls" "$f"; then
    echo "=== $f ==="
    awk '/^## Pitfalls/,/^## [^P]|^<Related/' "$f"
    echo
  fi
done
```

For each file in the output, apply the same template: every distinct pitfall gets an H3 heading.

If a file has no Pitfalls section in the output, no change needed there.

- [ ] **Step 2: Final build verification**

```bash
make docs-build
```

### Task 2.8: Run docs lint and commit

- [ ] **Step 1: Run lint**

```bash
cd docs/site && pnpm run lint && cd ../..
```

Expected output: `0 errors, 0 warnings, 0 hints`.

- [ ] **Step 2: Commit**

```bash
git add docs/site/src/content/docs/pitfalls.mdx \
        docs/site/src/content/docs/widgets/message.mdx \
        docs/site/src/content/docs/widgets/countdown.mdx \
        docs/site/src/content/docs/widgets/two_row.mdx \
        docs/site/src/content/docs/widgets/gif.mdx \
        docs/site/src/content/docs/widgets/image.mdx \
        docs/site/src/content/docs/concepts/animations.mdx
# Add any other widget pages touched in Task 2.7

git commit -m "docs: normalize Pitfalls sections + wire missing rule 22

Every Pitfalls section across the widget and concept pages now follows
a single template: H3 heading naming the failure mode, one or two
prose paragraphs explaining cause + fix, optional <DecisionRule>
callout below the prose when a validator rule covers it.

Adds an opening sentence to each Pitfalls section that frames the
numbered rules as validator rules — readers no longer hit 'Rule 14'
as a cold label.

Wires rule 22 (font line-height exceeds per-row band) onto the
two_row widget page (where the constraint bites first) and onto the
master /pitfalls/ page. Rule 22 was added to the registry in PR #34
but had no <DecisionRule id='22'> anywhere — closes that gap.

Before: gif/image opened Pitfalls with a bare <DecisionRule> card
(no heading), then bold-lead paragraphs. The card read as orphaned
prose with no scannable entry point.

After: every pitfall is an H3 + one paragraph. The card sits under
its own H3 like any other pitfall.
"
```

- [ ] **Step 3: Push and open PR**

```bash
git push -u origin HEAD
gh pr create --title "docs: normalize Pitfalls sections + wire missing rule 22" --body "$(cat <<'EOF'
## Summary

Two related fixes for the docs site's Pitfalls sections:

1. **Consistent shape across pages**: every pitfall is now \`### <heading>\` + one paragraph, with optional \`<DecisionRule>\` callout below the prose.
2. **Numbered rule framing**: a one-sentence intro to each Pitfalls section explains that numbered rules are validator rules checked by \`led-ticker validate\`. Readers no longer hit 'Rule 14' as an unexplained label.

## Why

Before: gif/image opened Pitfalls with a bare \`<DecisionRule>\` card (no heading), then bold-lead paragraphs without H3s. The card read as orphaned prose with no scannable entry point. two_row had only bold paragraphs with no DecisionRule at all, despite rule 22 covering one of its most common config errors.

After: every pitfall has an H3 heading, the prose is consistent, and rule 22 is now actually wired onto the two_row page.

## Files touched

- \`pitfalls.mdx\` — adds rule 22 to the master list
- \`widgets/gif.mdx\`, \`widgets/image.mdx\` — H3 wrapper around DecisionRule + H3s for the bold-paragraph pitfalls
- \`widgets/two_row.mdx\` — H3s + new DecisionRule for rule 22
- \`widgets/countdown.mdx\` — H3 wrapping the typewriter-not-supported pitfall
- Any other widget pages with Pitfalls sections caught by the audit

## Test plan

- [x] \`make docs-build\` clean (39 pages)
- [x] \`pnpm run lint\` clean
- [x] /pitfalls/ renders rule 22 inline
- [x] /widgets/two_row/ shows DecisionRule for rule 22

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## PR 3: Sections-and-modes gifs + sidebar drop + landing-page navbar

**Goal:** Add three pinned-pipeline gifs to `/concepts/sections-and-modes/` (one per mode), drop the `(overview)` parenthetical from the Widgets sidebar entry, and switch the landing page off `template: splash` so the sidebar appears.

### File structure

**Create:**
- `docs/site/demos-pinned/sections-forever_scroll.toml`
- `docs/site/demos-pinned/sections-infini_scroll.toml`
- `docs/site/demos-pinned/sections-swap.toml`
- `docs/site/public/demos-pinned/sections-forever_scroll.gif` (committed output)
- `docs/site/public/demos-pinned/sections-infini_scroll.gif`
- `docs/site/public/demos-pinned/sections-swap.gif`

**Modify:**
- `docs/site/src/content/docs/concepts/sections-and-modes.mdx` — embed three `<DemoGif>` entries
- `docs/site/astro.config.mjs` — change Widgets sidebar entry from "All widgets (overview)" to "All widgets"
- `docs/site/src/content/docs/index.mdx` — remove `template: splash` from frontmatter

### Task 3.1: Author three sections-and-modes demo TOMLs

- [ ] **Step 1: Create `sections-forever_scroll.toml`**

Write to `docs/site/demos-pinned/sections-forever_scroll.toml`:

```toml
# render-duration: 8
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[transitions]
default = "cut"

[[playlist.section]]
mode = "forever_scroll"
loop_count = 1
scroll_step_ms = 35

[[playlist.section.widget]]
type = "message"
text = "Open 9-5"
font_color = [225, 48, 108]

[[playlist.section.widget]]
type = "message"
text = "Free coffee Friday"
font_color = [255, 220, 0]

[[playlist.section.widget]]
type = "message"
text = "All ages welcome"
font_color = [120, 220, 255]
```

- [ ] **Step 2: Create `sections-infini_scroll.toml`**

Write to `docs/site/demos-pinned/sections-infini_scroll.toml`:

```toml
# render-duration: 10
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[transitions]
default = "cut"

[[playlist.section]]
mode = "infini_scroll"
loop_count = 1
scroll_step_ms = 35

[[playlist.section.widget]]
type = "message"
text = "Now Enrolling"
font_color = [225, 48, 108]

[[playlist.section.widget]]
type = "message"
text = "Spring Classes Open"
font_color = [255, 220, 0]
```

- [ ] **Step 3: Create `sections-swap.toml`**

Write to `docs/site/demos-pinned/sections-swap.toml`:

```toml
# render-duration: 10
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[transitions]
default = "push_left"
duration = 0.5

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 2.5

[[playlist.section.widget]]
type = "message"
text = "Hello"
font_color = [120, 220, 255]

[[playlist.section.widget]]
type = "message"
text = "World"
font_color = [225, 48, 108]
```

### Task 3.2: Render the three demos

- [ ] **Step 1: Render via `make render-pinned-demos`**

```bash
make render-pinned-demos 2>&1 | grep -E "sections-|FAILED"
```

Expected output: three lines like `[render-pinned-demos] docs/site/demos-pinned/sections-forever_scroll.toml -> docs/site/public/demos-pinned/sections-forever_scroll.gif (8s)`.

If FAILED appears for any demo, read the rendered output for the error and fix the TOML.

- [ ] **Step 2: Verify gif playback durations are sensible**

```bash
uv run python -c "
from PIL import Image
import os
for name in ['sections-forever_scroll', 'sections-infini_scroll', 'sections-swap']:
    im = Image.open(f'docs/site/public/demos-pinned/{name}.gif')
    total = 0
    for i in range(im.n_frames):
        im.seek(i); total += im.info.get('duration', 0)
    print(f'{name}: {im.n_frames} frames, {total/1000:.1f}s')
"
```

Expected output: each gif plays for ~6-10 seconds.

### Task 3.3: Embed gifs on the sections-and-modes page

- [ ] **Step 1: Open the page**

`docs/site/src/content/docs/concepts/sections-and-modes.mdx`

- [ ] **Step 2: Add `import DemoGif` near the top**

The file already imports `TomlExample` and `RelatedPages`. Add a `DemoGif` import alongside them so the file's import block reads:

```mdx
import DemoGif from "../../../components/DemoGif.astro";
import TomlExample from "../../../components/TomlExample.astro";
import RelatedPages from "../../../components/RelatedPages.astro";
```

- [ ] **Step 3: Insert a `<DemoGif>` above each mode's TomlExample**

For `## \`forever_scroll\` — side-by-side ticker`: between its opening prose paragraph and its `<TomlExample>`, insert:

```mdx
<DemoGif
  src="/demos-pinned/sections-forever_scroll.gif"
  caption="`forever_scroll` — three short messages flow together separated by a bullet; the panel never clears"
/>
```

For `## \`infini_scroll\` — one-at-a-time scroll`: insert:

```mdx
<DemoGif
  src="/demos-pinned/sections-infini_scroll.gif"
  caption="`infini_scroll` — each widget scrolls fully off before the next enters; a clean gap between messages"
/>
```

For `## \`swap\` — held with transitions`: insert:

```mdx
<DemoGif
  src="/demos-pinned/sections-swap.gif"
  caption="`swap` — each widget holds for `hold_time`, then a transition (`push_left` here) reveals the next"
/>
```

- [ ] **Step 4: Verify build**

```bash
make docs-build
```

Confirm `dist/concepts/sections-and-modes/index.html` exists and contains the three new image references:

```bash
grep -c "sections-forever_scroll\|sections-infini_scroll\|sections-swap" docs/site/dist/concepts/sections-and-modes/index.html
```

Expected output: `3`.

### Task 3.4: Drop the (overview) parenthetical from the Widgets sidebar

- [ ] **Step 1: Open `docs/site/astro.config.mjs`**

Find the Widgets sidebar group. The first item is currently:

```js
{ label: "All widgets (overview)", link: "/widgets/" },
```

- [ ] **Step 2: Change the label**

Replace that line with:

```js
{ label: "All widgets", link: "/widgets/" },
```

- [ ] **Step 3: Verify build**

```bash
make docs-build
```

Confirm the sidebar in any built page now reads "All widgets" instead of "All widgets (overview)":

```bash
grep "All widgets" docs/site/dist/widgets/message/index.html | head -3
```

Expected output: the link text now matches what the sidebar config says.

### Task 3.5: Bring the navbar back on the landing page

- [ ] **Step 1: Open `docs/site/src/content/docs/index.mdx`**

The frontmatter currently has `template: splash`. The splash template intentionally suppresses the sidebar to give the hero full visual weight.

- [ ] **Step 2: Remove the `template: splash` line**

Delete it from the frontmatter. The frontmatter should now be:

```yaml
---
title: led-ticker
description: An asyncio Python toolkit for displaying scrolling feeds on RGB LED matrix panels.
hero:
  tagline: Scrolling feeds on RGB LED matrix panels.
  actions:
    - text: Get started
      link: /getting-started/
      icon: right-arrow
    - text: GitHub
      link: https://github.com/JamesAwesome/led-ticker
      icon: external
      variant: minimal
---
```

- [ ] **Step 3: Verify the sidebar now renders**

```bash
make docs-build
grep -c "sidebar-pane\|sl-sidebar\|All widgets" docs/site/dist/index.html
```

Expected output: at least 3 (previously was 1 or 0 — sidebar elements absent).

- [ ] **Step 4: Sanity-check the hero block still renders**

```bash
grep -c "tagline\|hero" docs/site/dist/index.html
```

Expected output: > 0. The hero block renders in the default doc template too, just without the full-width centering.

### Task 3.6: Run docs lint and commit

- [ ] **Step 1: Run lint**

```bash
cd docs/site && pnpm run lint && cd ../..
```

- [ ] **Step 2: Commit**

```bash
git add docs/site/demos-pinned/sections-forever_scroll.toml \
        docs/site/demos-pinned/sections-infini_scroll.toml \
        docs/site/demos-pinned/sections-swap.toml \
        docs/site/public/demos-pinned/sections-forever_scroll.gif \
        docs/site/public/demos-pinned/sections-infini_scroll.gif \
        docs/site/public/demos-pinned/sections-swap.gif \
        docs/site/src/content/docs/concepts/sections-and-modes.mdx \
        docs/site/astro.config.mjs \
        docs/site/src/content/docs/index.mdx

git commit -m "docs: sections-and-modes gifs + sidebar consistency + landing-page navbar

Three small UX fixes bundled:

1. Three pinned-pipeline gifs for /concepts/sections-and-modes — one
   per mode (forever_scroll, infini_scroll, swap). Each gif goes
   above its mode's TomlExample with a caption that describes the
   distinguishing visual behavior, not just the mode name.

   forever_scroll: messages flow together with bullet separators.
   infini_scroll: messages have a clean gap between them.
   swap: each message holds, then a transition reveals the next.

   Captured at the new section-level scroll_step_ms = 35 so the
   marquee reads briskly on the docs preview.

2. Drop the '(overview)' parenthetical from the Widgets sidebar
   entry. The Widgets group label already signals 'this group is
   about widgets'; the entry-page label just needs to distinguish
   itself from the per-widget rows ('All widgets' suffices). Other
   sidebar sections (Transitions, Concepts, Hardware, etc.) don't
   have the parenthetical, so dropping it brings Widgets into
   alignment instead of spreading the parenthetical to every group.

3. Remove 'template: splash' from index.mdx so the landing page
   gets the sidebar back. The splash template suppresses the
   sidebar by design to give the hero full visual weight — but
   visitors couldn't start browsing without using search or
   clicking one of the two CTA buttons. The default 'doc' template
   keeps the hero block (tagline + action buttons) but adds the
   sidebar.
"
```

- [ ] **Step 3: Push and open PR**

```bash
git push -u origin HEAD
gh pr create --title "docs: sections-and-modes gifs + sidebar + landing-page navbar" --body "$(cat <<'EOF'
## Summary

Three small UX fixes bundled into one PR:

1. **Sections-and-modes page gets three gifs** — one per mode (\`forever_scroll\`, \`infini_scroll\`, \`swap\`). Each visualizes the distinguishing behavior the prose can only describe.
2. **Drop the '(overview)' parenthetical** from the Widgets sidebar so it stops being the only group that calls itself out that way.
3. **Bring the sidebar back on the landing page** by removing \`template: splash\`. Visitors couldn't navigate without using search or clicking a CTA — annoying for anyone who lands on the page expecting standard docs nav.

## Demos

| Mode | Caption |
|---|---|
| \`forever_scroll\` | three messages flow together with bullet separators |
| \`infini_scroll\` | each message has a clean gap before the next enters |
| \`swap\` | each message holds, transition (push_left) reveals the next |

Captured at \`scroll_step_ms = 35\` so the marquee reads briskly.

## Sidebar before/after

| Before | After |
|---|---|
| All widgets (overview) | All widgets |
| Transitions | Transitions |
| Concepts | Concepts |

## Landing page before/after

Before: \`template: splash\` → centered hero, no sidebar, search + CTA only.
After: default doc template → sidebar visible, hero still renders but as a doc-page hero rather than a centered marketing splash.

## Test plan

- [x] \`make render-pinned-demos\` produces three new gifs end-to-end
- [x] Gifs play 6-10 sec each
- [x] \`make docs-build\` clean
- [x] \`pnpm run lint\` clean
- [x] Sidebar renders on the homepage (\`grep sidebar-pane dist/index.html\` non-zero)
- [x] Widgets sidebar entry now reads "All widgets" (no parenthetical)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## PR 4: Embed smallsign + bigsign configs on hardware pages

**Goal:** Bring the example configs into the docs site as embedded reference configs on the corresponding hardware pages. Editorial pass on `config.example.toml` and `config.bigsign.example.toml` to bring their section comments up to `config.moonbunny.example.toml`'s quality first; then duplicate (not import) the cleaned versions onto the hardware pages.

### File structure

**Modify:**
- `config/config.example.toml` — editorial pass on section comments
- `config/config.bigsign.example.toml` — editorial pass on section comments
- `docs/site/src/content/docs/hardware/smallsign.mdx` — embed the smallsign config inside `<details>`
- `docs/site/src/content/docs/hardware/bigsign.mdx` — embed the bigsign config inside `<details>`

**No new files. No deletions.**

### Task 4.1: Editorial pass on config.example.toml

- [ ] **Step 1: Read the current file**

```bash
cat config/config.example.toml
```

- [ ] **Step 2: Identify comment categories**

The file currently has:
- A 30-entry transition catalogue comment block at the top (overlaps with /transitions/ docs)
- Inline knob-value explanations (good — keep)
- Section dividers (good — keep)
- A "Display Modes" comment block (overlaps with /concepts/sections-and-modes/)
- An RSS feed example block with "Uncomment and add your favorite feeds" guidance (developer-terse)

The moonbunny config (`config.moonbunny.example.toml`) is the template. Read it for tone:

```bash
head -60 config/config.moonbunny.example.toml
```

Notice that moonbunny's section comments explain the **design choice**, not just the knob values. e.g. `# text_align='scroll' — image painted on top with skip-black, so text shows through`.

- [ ] **Step 3: Rewrite the transitions comment block**

Replace the 30-entry transition catalogue with a single editorial sentence:

```toml
# --- Transitions ---
# Global transition defaults. Full transition catalogue and per-family
# tuning lives at https://docs.ledticker.dev/transitions/. The defaults
# below give a 0.5-sec wipe between widgets within a section, and a
# dissolve between sections — readable on a 160x16 smallsign without
# being distracting.

[transitions]
default = "wipe_alternating"
duration = 0.5
easing = "ease_out"
between_sections = "dissolve"
```

- [ ] **Step 4: Rewrite or remove the "Display Modes" comment block**

Replace it with:

```toml
# --- Sections ---
# Each section is a group of widgets that share a display mode
# (forever_scroll | infini_scroll | swap), hold time, and scroll
# cadence. See https://docs.ledticker.dev/concepts/sections-and-modes/
# for the full mode reference.
```

- [ ] **Step 5: Tighten any other developer-terse comments**

Apply the same rule: every block comment should answer "what is this section doing and why", with knob values explained inline. Don't list all values for a knob — link to docs instead.

- [ ] **Step 6: Verify the config still validates**

```bash
make validate CONFIG=config/config.example.toml
```

Expected output: zero errors. (Comments don't affect validation, but this catches accidental edits to the TOML.)

### Task 4.2: Editorial pass on config.bigsign.example.toml

- [ ] **Step 1: Apply the same pattern as Task 4.1**

The bigsign config is denser and references specific hardware tuning (`pixel_mapper`, `slowdown_gpio`, `rp1_rio`, `pwm_bits`). The comment voice should explain WHY each value is set, not just WHAT it does.

Sample target voice for the display block:

```toml
[display]
# Bigsign canvas: 8 P3 32x64 panels arranged as a 2x4 vertical
# serpentine = 256x64 logical. The pixel_mapper string is what
# tells the rgbmatrix library how to remap pixels onto the physical
# chain — see https://docs.ledticker.dev/hardware/bigsign/ for the
# diagram and how to derive your own mapper string.
rows = 32
cols = 64
chain = 8
parallel = 1
pixel_mapper = "Remap:256,64|192,32n|192,0n|128,32n|128,0n|64,32n|64,0n|0,32n|0,0n"

# default_scale = 4 means: every widget draws at the standard 16-tall
# logical canvas, and the ScaledCanvas wrapper expands every pixel to
# a 4x4 real block. The widget code never sees the 256x64 panel
# directly — everything is logical-pixel-relative until paint.
default_scale = 4

brightness = 60

# Pi 5 RP1 GPIO tuning. slowdown_gpio paired with rp1_rio mode = 1
# (PIO mode) gives stable refresh on an 8-panel chain. Drop pwm_bits
# from default 11 to 8 to keep refresh rate above the perceptual
# flicker floor at this chain length.
slowdown_gpio = 3
rp1_rio = 1
pwm_bits = 8
```

- [ ] **Step 2: Verify**

```bash
make validate CONFIG=config/config.bigsign.example.toml
```

### Task 4.3: Embed the smallsign config on the hardware page

- [ ] **Step 1: Open `docs/site/src/content/docs/hardware/smallsign.mdx`**

Confirm the page exists. If not, the embed task lives on the closest hardware-build page.

- [ ] **Step 2: Add an embedded config section**

At an appropriate point in the page (typically after the BOM + wiring sections, before the "deploy" content), add:

```mdx
## Reference config

A complete working config for this build. Drop this into `config/config.toml` and adjust the per-widget content for your sign.

<details>
<summary>Complete <code>config.example.toml</code> (160×16 smallsign)</summary>

```toml
# Paste the entire contents of config/config.example.toml here.
# (Duplicated, not imported — keeps the embedded copy stable as the
# repo's example evolves.)
```

</details>
```

For the `<details>` body, paste the **entire current content** of `config/config.example.toml` inside the fenced code block. This is the editorial-cleaned version from Task 4.1.

- [ ] **Step 3: Verify build**

```bash
make docs-build
grep -c "config.example.toml\|details" docs/site/dist/hardware/smallsign/index.html
```

Expected output: > 0.

### Task 4.4: Embed the bigsign config on the hardware page

- [ ] **Step 1: Open `docs/site/src/content/docs/hardware/bigsign.mdx`**

- [ ] **Step 2: Add an embedded config section, same pattern as Task 4.3**

```mdx
## Reference config

A complete working config for this build, including the `pixel_mapper` string and the Pi 5 RP1 tuning that this hardware needs. Drop this into `config/config.toml` and adjust the per-widget content.

<details>
<summary>Complete <code>config.bigsign.example.toml</code> (256×64 bigsign)</summary>

```toml
# Paste the entire contents of config/config.bigsign.example.toml here.
```

</details>
```

For the `<details>` body, paste the **entire current content** of `config/config.bigsign.example.toml`. This is the editorial-cleaned version from Task 4.2.

- [ ] **Step 3: Verify build**

```bash
make docs-build
```

### Task 4.5: Run docs lint and commit

- [ ] **Step 1: Run lint**

```bash
cd docs/site && pnpm run lint && cd ../..
```

- [ ] **Step 2: Commit**

```bash
git add config/config.example.toml \
        config/config.bigsign.example.toml \
        docs/site/src/content/docs/hardware/smallsign.mdx \
        docs/site/src/content/docs/hardware/bigsign.mdx

git commit -m "docs: embed smallsign + bigsign example configs on hardware pages

Editorial pass on config.example.toml and config.bigsign.example.toml
to bring their section-comment voice up to config.moonbunny.example.toml
quality (explain WHY, not just WHAT; link to docs for value
catalogues). Then embed the cleaned configs on the corresponding
hardware pages inside <details>/<summary> blocks so readers can
expand them when wanted but they don't dominate the page.

Embedded as duplicates (paste, not import) so the docs-site copy is
stable as the runtime configs evolve. Both copies remain valid
configs — verified via 'make validate'.

Removed from the configs:
- 30-entry transition catalogue comment (now linked to /transitions/)
- 'Display Modes' comment block (now linked to /concepts/sections-and-modes/)

Promoted in the configs:
- Section-level comments now explain the design choice
- Inline comments now answer 'why this value' for tunable knobs
"
```

- [ ] **Step 3: Push and open PR**

```bash
git push -u origin HEAD
gh pr create --title "docs: embed example configs on hardware pages + editorial pass" --body "$(cat <<'EOF'
## Summary

Bring the smallsign + bigsign example configs into the docs site as embedded reference configs on the corresponding hardware pages. Editorial pass on the configs first to bring their comment voice up to the moonbunny config's quality.

## Why

A reader on \`/hardware/bigsign/\` currently has no path from the build instructions to a complete annotated working config — they're told to copy \`config.bigsign.example.toml\` but not shown what's in it. Embedding the config inline (inside \`<details>\`) means the reader can see the config without leaving the page, and the config's section comments narrate the design choices they'd otherwise have to reverse-engineer.

## Editorial pass

Both configs follow the moonbunny pattern now: section comments explain WHY a value was chosen, knob lists move to the docs site as deep links. Sample:

\`\`\`toml
# Before:
# pwm_bits — refresh quality knob, 1-11
pwm_bits = 8

# After:
# Drop pwm_bits from default 11 to 8 to keep refresh rate above the
# perceptual flicker floor at this chain length. See
# https://docs.ledticker.dev/hardware/bigsign/ for the
# refresh/pwm_bits tradeoff curve.
pwm_bits = 8
\`\`\`

## Duplication is intentional

The embedded copies are pasted, not imported. The trade-off: when the runtime config evolves, the embedded copy needs a manual sync. The win: the docs copy is stable and can carry editorial commentary the runtime config doesn't need.

## Test plan

- [x] \`make validate CONFIG=config/config.example.toml\` clean
- [x] \`make validate CONFIG=config/config.bigsign.example.toml\` clean
- [x] \`make docs-build\` clean
- [x] \`pnpm run lint\` clean
- [x] /hardware/smallsign/ and /hardware/bigsign/ each render the embedded config inside an expandable \`<details>\`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Cross-PR verification

After all four PRs merge, do a final pass:

- [ ] **Run the full docs build and confirm 39+ pages**

```bash
git checkout main && git pull
make docs-build
```

Expected: `[build] 39 page(s) built`.

- [ ] **Visual spot-check the most-touched pages**

```bash
make docs-dev
```

Open the dev server and walk:
- `/` — sidebar visible, hero renders
- `/concepts/sections-and-modes/` — three gifs in place
- `/widgets/gif/`, `/widgets/image/`, `/widgets/two_row/` — Pitfalls H3s consistent, rule 22 wired
- `/pitfalls/` — rule 22 in the hard-rules section
- `/hardware/smallsign/`, `/hardware/bigsign/` — embedded configs render in `<details>`
- Sidebar reads "All widgets" not "All widgets (overview)"

- [ ] **Confirm no stale links from README**

```bash
grep -oE 'docs\.ledticker\.dev/[^)]*' README.md | sort -u
```

For each link, run the dist path check:

```bash
make docs-build
for url in $(grep -oE 'docs\.ledticker\.dev/[^)]*' README.md | sed 's|docs.ledticker.dev||' | sort -u); do
  path="docs/site/dist${url}index.html"
  [ -f "$path" ] && echo "OK: $url" || echo "MISS: $url"
done
```

Expected: all OK (excluding `/reference/contributing/` if that page isn't created).

---

## What this plan deliberately does not do

- **Does not add a tooltip or interactive component for the Rule N badges.** The cost (custom component code, hover state in Starlight's styling) exceeds the benefit; the one-line framing sentence on each Pitfalls section is sufficient.
- **Does not change the moonbunny config.** Its comment quality is already the target the others are aiming for.
- **Does not refactor the runtime configs' structure** — only the comments. Knobs, sections, and values stay identical so the runtime keeps loading them.
- **Does not create a new "Decision rules" concept page.** The existing `/pitfalls/` page already serves that role; duplicating it would create two sources of truth.
- **Does not extend the hires-font glyph set further.** PR #36 added bullet, em-dash, ellipsis, curly quotes — sufficient for current docs needs.
- **Does not bundle the four PRs into one branch.** Each PR is independently mergeable to keep review surface tight.
