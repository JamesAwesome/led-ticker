# Demo Gifs Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh the docs site's transition + weather demo gifs based on review feedback — re-render weather against the live API key, slow down + expand the push / wipe / special / sprite family showcases so each gif demonstrates multiple variants of its family at a comfortable read pace, and move the sprite showcase to the long-running pipeline (it'll take longer than auto-render's per-build budget).

**Architecture:** Single PR, six tasks. Each transition family becomes a multi-section TOML — one section per variant — so a single gif shows e.g. push_left → push_right → push_up → push_down → push_random in sequence rather than just one direction. Section-to-section transitions stay invisible (`between_sections = "cut"`) so each variant reads cleanly. Auto-render pipeline (`docs/site/demos/` → committed only as TOML, gif regenerates on every Cloudflare build) handles push / wipe / special at modestly extended `# render-duration:` budgets. Sprite showcase moves to the long-running pipeline (`docs/site/demos-long/` → gif committed) because sprite-trail transitions take 1-3 sec each and stacking 5 families pushes wallclock render time past what's reasonable to redo on every Cloudflare build. Weather refresh is a one-shot re-render with the `.env`-loaded `WEATHERAPI_KEY`.

**Tech stack:** TOML demos under `docs/site/demos/` (auto) and `docs/site/demos-long/` (manual, committed gif). Renderer at `tools/render_demo/render.py`. Make targets `make render-long-demo NAME=<name>` and `make render-long-demos`. Auto pipeline driven by `docs/site/scripts/build-demos.mjs` which honors a `# render-duration: N` comment in each TOML. The `make render-long-demos` target sources `.env` automatically; for `make render-long-demo NAME=…` you may need to `set -a; . ./.env; set +a` first if it doesn't.

**Worktree convention:** Per project memory, lands via worktree + PR. Use `EnterWorktree name="demo-gifs-refresh"`.

---

## File map

| File | Action | Why |
|---|---|---|
| `docs/site/public/demos-long/widget-weather.gif` | Re-render | Current 1.3 KB gif suggests the last render didn't have `WEATHERAPI_KEY` loaded; needs a real-data render |
| `docs/site/demos/push-left.toml` | Delete | Renamed → `transitions-push.toml` for naming consistency with siblings (`transitions-wipe.toml`, `transitions-sprite.toml`, `transitions-special.toml`) |
| `docs/site/demos/transitions-push.toml` | Create | Multi-section showcase: push_left → push_right → push_up → push_down → push_random; `transition_duration = 0.9` (was 0.6, felt rushed); `# render-duration: 22` |
| `docs/site/demos/transitions-wipe.toml` | Replace | Multi-section showcase: wipe_left → wipe_right → wipe_up → wipe_down → wipe_random; `transition_duration = 0.9`; `# render-duration: 22` |
| `docs/site/demos/transitions-special.toml` | Replace | Multi-section showcase: dissolve (slowed to 1.4) → split → color_flash → scroll → cut; `# render-duration: 22` |
| `docs/site/demos-long/transitions-sprite.toml` | Create | Moved from auto. Multi-section showcase: pokeball → baseball → nyancat → pacman → sailor_moon; `# render-duration: 60` |
| `docs/site/demos/transitions-sprite.toml` | Delete | Moved to long-running pipeline |
| `docs/site/public/demos-long/transitions-sprite.gif` | Create (rendered + committed) | Output of the new long-demo |
| `docs/site/src/content/docs/transitions/push.mdx` | Modify | Update `<DemoGif src="/demos/push-left.gif" caption="push_left between two messages" />` → `<DemoGif src="/demos/transitions-push.gif" caption="push family — left, right, up, down, and random" />` |
| `docs/site/src/content/docs/transitions/wipe.mdx` | Modify | Update caption to "wipe family — left, right, up, down, and random with color rotation" |
| `docs/site/src/content/docs/transitions/special.mdx` | Modify | Update caption to "special family — dissolve, split, color_flash, scroll, cut" |
| `docs/site/src/content/docs/transitions/sprite.mdx` | Modify | Update DemoGif src `/demos/transitions-sprite.gif` → `/demos-long/transitions-sprite.gif`; caption to "sprite family — pokeball, baseball, nyancat, pacman, sailor_moon" |

---

## Per-task contract

Every task that touches a TOML / mdx ends with:

1. `cd docs/site && pnpm run lint 2>&1 | tail -3` — must pass clean (0 / 0 / 0). Re-stage if prettier reformats.
2. `cd docs/site && pnpm run build 2>&1 | tail -3` — must build 39 pages (no count change).
3. For auto-render TOMLs: trigger a render via `cd docs/site && rm -f public/demos/<NAME>.gif && node scripts/build-demos.mjs 2>&1 | grep -E '<NAME>|done'` — confirm the new TOML renders without error and the resulting gif is non-trivially sized (> 5 KB; tiny gifs usually mean the render captured nothing).
4. `git add` + commit with the message specified in the task.

For long-render gifs, the render step is part of the task (the gif is committed) and uses `make render-long-demo NAME=<name>`.

---

## Task 1: Weather long-demo re-render with `.env` sourced

**File:**
- Re-render: `docs/site/public/demos-long/widget-weather.gif` (TOML at `docs/site/demos-long/widget-weather.toml` is unchanged)

The current gif is only 1.3 KB, suggesting the last render didn't have `WEATHERAPI_KEY` set. Re-render with the env loaded and verify the output looks like a real Brooklyn weather card (icon + temp + label).

- [ ] **Step 1: Confirm `.env` is present and has the key**

```bash
ls -la /Users/james/projects/github/jamesawesome/led-ticker/.env
grep -c '^WEATHERAPI_KEY=' /Users/james/projects/github/jamesawesome/led-ticker/.env
```

Expected: file exists; grep outputs `1`. If the key isn't there, halt and surface to the user — the rest of this task can't run.

- [ ] **Step 2: Source the env and run the render**

The Makefile's `render-long-demo` target sources `.env` automatically via `if [ -f .env ]; then set -a; . ./.env; set +a; fi`. So this should Just Work from the repo root:

```bash
make render-long-demo NAME=widget-weather
```

Expected output: a line like `[render-long-demo] docs/site/demos-long/widget-weather.toml (30s)` followed by the renderer's frame-count log. If the renderer prints `WEATHERAPI_KEY not set` or a 401 from WeatherAPI, the env didn't load — manually source it:

```bash
set -a; . ./.env; set +a
make render-long-demo NAME=widget-weather
```

- [ ] **Step 3: Verify the gif is non-trivial**

```bash
ls -l docs/site/public/demos-long/widget-weather.gif
uv run python -c "from PIL import Image; im = Image.open('docs/site/public/demos-long/widget-weather.gif'); print(f'frames={im.n_frames} size={im.size}')"
```

Expected: file size ≥ 10 KB (usually 20-50 KB), frame count > 30. Tiny file or single frame = render didn't get real data; halt.

- [ ] **Step 4: Commit**

```bash
git add docs/site/public/demos-long/widget-weather.gif
git commit -m "docs: re-render weather long-demo with WEATHERAPI_KEY from .env

Prior render produced a 1.3 KB gif (single frame, no real data) —
WEATHERAPI_KEY wasn't sourced when \`make render-long-demos\` ran.
Re-render with the env loaded so the gif shows the actual Brooklyn
weather card (icon + temp + label) on widgets/weather.mdx."
```

---

## Task 2: Push family showcase (auto-render)

**Files:**
- Delete: `docs/site/demos/push-left.toml`
- Create: `docs/site/demos/transitions-push.toml`
- Modify: `docs/site/src/content/docs/transitions/push.mdx`

Existing demo only shows `push_left`. User feedback: too quick / rapid; want to show other directions. Replace with a multi-section showcase that demonstrates left, right, up, down, and random. Slow `transition_duration` from 0.6 to 0.9 (panel review noted "0.4-0.8 feels right" range — 0.9 is the slow end of comfortable).

- [ ] **Step 1: Delete the old single-direction demo**

```bash
rm docs/site/demos/push-left.toml
# Also remove the auto-rendered output if present (it's gitignored but lingers locally):
rm -f docs/site/public/demos/push-left.gif
```

- [ ] **Step 2: Create the new multi-section showcase**

Write `docs/site/demos/transitions-push.toml`:

```toml
# Demo: push family showcase — one section per direction so a single
# captured gif shows left, right, up, down, and random in sequence.
# Section-to-section transitions are `cut` so the inter-direction
# boundaries stay invisible; only the named push transition fires
# between the two messages within each section.
#
# transition_duration = 0.9 (was 0.6 on the old single-direction
# demo). Review feedback flagged the prior speed as rapid; 0.9 is
# the slow end of the docs site's recommended 0.4–0.9 range.
#
# render-duration: 22
# ↑ 5 sections × (1.5 s hold + 0.9 s transition + 1.5 s hold) ≈
#   19 s content; capture 22 s for clean tail.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[transitions]
between_sections = "cut"

[[playlist.section]]
mode = "swap"
transition = "push_left"
transition_duration = 0.9
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "push_left"

[[playlist.section.widget]]
type = "message"
text = "←"

[[playlist.section]]
mode = "swap"
transition = "push_right"
transition_duration = 0.9
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "push_right"

[[playlist.section.widget]]
type = "message"
text = "→"

[[playlist.section]]
mode = "swap"
transition = "push_up"
transition_duration = 0.9
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "push_up"

[[playlist.section.widget]]
type = "message"
text = "↑"

[[playlist.section]]
mode = "swap"
transition = "push_down"
transition_duration = 0.9
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "push_down"

[[playlist.section.widget]]
type = "message"
text = "↓"

[[playlist.section]]
mode = "swap"
transition = "push_random"
transition_duration = 0.9
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "push_random"

[[playlist.section.widget]]
type = "message"
text = "?"
```

- [ ] **Step 3: Update `push.mdx` to point at the new gif**

Edit `docs/site/src/content/docs/transitions/push.mdx`. Find:

```mdx
<DemoGif src="/demos/push-left.gif" caption="push_left between two messages" />
```

Replace with:

```mdx
<DemoGif src="/demos/transitions-push.gif" caption="push family — left, right, up, down, and random" />
```

- [ ] **Step 4: Render the new demo + verify**

```bash
cd docs/site && (corepack enable 2>/dev/null || true) && node scripts/build-demos.mjs 2>&1 | grep -E 'transitions-push|done'
```

Expected: a `[build-demos] rendering ... transitions-push.toml ... (22s)` line, then `[build-demos] done.`

```bash
ls -l docs/site/public/demos/transitions-push.gif
uv run python -c "from PIL import Image; im = Image.open('docs/site/public/demos/transitions-push.gif'); print(f'frames={im.n_frames}')"
```

Expected: file size > 50 KB (multi-section, several seconds of content), frame count > 80. If the file is tiny, the render captured nothing meaningful — halt and check stderr from the renderer.

- [ ] **Step 5: Lint + build**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3
```

Expected: 0 lint, 39 pages built.

- [ ] **Step 6: Commit**

```bash
git add docs/site/demos/transitions-push.toml docs/site/src/content/docs/transitions/push.mdx
git rm docs/site/demos/push-left.toml
git commit -m "docs: push transition showcase — slower, all 5 directions in one gif

User feedback on /transitions/push/: existing demo was too quick
(transition_duration = 0.6 felt rapid) and only showed push_left.

Replace with a multi-section showcase: push_left → push_right →
push_up → push_down → push_random in sequence. Section-to-section
boundaries are invisible cuts so only the named push transition
fires between the two messages within each section. Slow
transition_duration to 0.9 — the slow end of the docs site's
recommended 0.4-0.9 range. \`# render-duration: 22\` extends the
auto-render budget; gif loops cleanly with all 5 directions visible.

Renamed push-left.toml → transitions-push.toml for consistency with
sibling family showcases (transitions-wipe, transitions-sprite,
transitions-special). Updated push.mdx DemoGif src + caption."
```

---

## Task 3: Wipe family showcase (auto-render)

**Files:**
- Replace: `docs/site/demos/transitions-wipe.toml`
- Modify: `docs/site/src/content/docs/transitions/wipe.mdx`

User feedback: existing demo (which used `wipe_alternating` with `loop_count = 2`) cuts too quick after first loop. Want to show other directions.

Same multi-section showcase pattern as Task 2.

- [ ] **Step 1: Replace `transitions-wipe.toml`**

Write `docs/site/demos/transitions-wipe.toml`:

```toml
# Demo: wipe family showcase — one section per direction so a single
# captured gif shows left, right, up, down, and random with full
# color rotation. The previous wipe_alternating demo cut too quick
# after the first loop; this one gives each direction its own
# section so the reader sees each variant clearly before the next.
#
# Each direction inherits its default sweep color (see
# transitions/wipe fact-pack); wipe_random pulls from
# transition_colors.
#
# render-duration: 22
# ↑ 5 sections × (1.5 s hold + 0.9 s transition + 1.5 s hold) ≈
#   19 s content; capture 22 s for clean tail.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[transitions]
between_sections = "cut"

[[playlist.section]]
mode = "swap"
transition = "wipe_left"
transition_duration = 0.9
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "wipe_left"

[[playlist.section.widget]]
type = "message"
text = "← cyan"

[[playlist.section]]
mode = "swap"
transition = "wipe_right"
transition_duration = 0.9
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "wipe_right"

[[playlist.section.widget]]
type = "message"
text = "magenta →"

[[playlist.section]]
mode = "swap"
transition = "wipe_up"
transition_duration = 0.9
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "wipe_up"

[[playlist.section.widget]]
type = "message"
text = "↑ white"

[[playlist.section]]
mode = "swap"
transition = "wipe_down"
transition_duration = 0.9
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "wipe_down"

[[playlist.section.widget]]
type = "message"
text = "↓ green"

[[playlist.section]]
mode = "swap"
transition = "wipe_random"
transition_duration = 0.9
transition_colors = [[0,255,255], [255,0,255], [255,255,255], [0,255,0]]
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "wipe_random"

[[playlist.section.widget]]
type = "message"
text = "?"
```

- [ ] **Step 2: Update `wipe.mdx`**

Find:

```mdx
<DemoGif src="/demos/transitions-wipe.gif" caption="wipe_alternating between two messages" />
```

Replace with:

```mdx
<DemoGif src="/demos/transitions-wipe.gif" caption="wipe family — left, right, up, down, and random" />
```

(URL stays the same; only the caption changes.)

- [ ] **Step 3: Render + verify**

```bash
cd docs/site && rm -f public/demos/transitions-wipe.gif && node scripts/build-demos.mjs 2>&1 | grep -E 'transitions-wipe|done'
ls -l docs/site/public/demos/transitions-wipe.gif
```

Expected: rendering line at (22s), file size > 50 KB.

- [ ] **Step 4: Lint + build + commit**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3

git add docs/site/demos/transitions-wipe.toml docs/site/src/content/docs/transitions/wipe.mdx
git commit -m "docs: wipe transition showcase — slower, all 5 directions in one gif

User feedback on /transitions/wipe/: existing wipe_alternating demo
with loop_count=2 cut too quick after the first loop, and only
demonstrated the alternating variant.

Replace with a multi-section showcase: wipe_left → wipe_right →
wipe_up → wipe_down → wipe_random. Each direction gets its own
named section so the reader sees the sweep color (cyan / magenta /
white / green) and direction clearly before moving on.
transition_duration = 0.9 (was 0.6). \`# render-duration: 22\`
extends the auto-render budget."
```

---

## Task 4: Special family showcase (auto-render, slower dissolve)

**Files:**
- Replace: `docs/site/demos/transitions-special.toml`
- Modify: `docs/site/src/content/docs/transitions/special.mdx`

User feedback: dissolve in special is too quick. Want to show other specials. Replace with a multi-section showcase that includes dissolve (slowed) + split + color_flash + scroll + cut.

`cut` is instant — including it gives the reader a sense of the no-transition baseline before the dissolve / split / scroll show their effects.

- [ ] **Step 1: Replace `transitions-special.toml`**

Write `docs/site/demos/transitions-special.toml`:

```toml
# Demo: special family showcase — dissolve, split, color_flash,
# scroll, and cut in sequence. The previous demo only showed
# dissolve at duration 0.6 which felt rushed; dissolve gets 1.4 s
# here so the TV-static effect can play out.
#
# `scroll` is the seamless continuous-scroll variant with a bullet
# separator (different rhythm from the others — no pause, no flash).
# `cut` is included last as the no-transition baseline.
#
# render-duration: 22
# ↑ 5 sections × (~3 s avg per section, including scroll's longer
#   traversal + dissolve's 1.4 s) ≈ 18-20 s content; capture 22 s
#   for clean tail.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[transitions]
between_sections = "cut"

[[playlist.section]]
mode = "swap"
transition = "dissolve"
transition_duration = 1.4
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "dissolve"

[[playlist.section.widget]]
type = "message"
text = "TV static"

[[playlist.section]]
mode = "swap"
transition = "split"
transition_duration = 0.9
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "split"

[[playlist.section.widget]]
type = "message"
text = "↔ open"

[[playlist.section]]
mode = "swap"
transition = "color_flash"
transition_duration = 0.6
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "color_flash"

[[playlist.section.widget]]
type = "message"
text = "white pop"

[[playlist.section]]
mode = "swap"
transition = "scroll"
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "scroll"

[[playlist.section.widget]]
type = "message"
text = "• continuous"

[[playlist.section]]
mode = "swap"
transition = "cut"
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "cut"

[[playlist.section.widget]]
type = "message"
text = "instant"
```

- [ ] **Step 2: Update `special.mdx`**

Find:

```mdx
<DemoGif src="/demos/transitions-special.gif" caption="dissolve between two messages" />
```

Replace with:

```mdx
<DemoGif src="/demos/transitions-special.gif" caption="special family — dissolve, split, color_flash, scroll, cut" />
```

- [ ] **Step 3: Render + verify**

```bash
cd docs/site && rm -f public/demos/transitions-special.gif && node scripts/build-demos.mjs 2>&1 | grep -E 'transitions-special|done'
ls -l docs/site/public/demos/transitions-special.gif
```

Expected: rendering line at (22s), file size > 50 KB.

- [ ] **Step 4: Lint + build + commit**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3

git add docs/site/demos/transitions-special.toml docs/site/src/content/docs/transitions/special.mdx
git commit -m "docs: special transition showcase — slower dissolve + 4 more variants

User feedback: dissolve at duration 0.6 was too quick; only one
special variant was demonstrated.

Replace with a multi-section showcase: dissolve (slowed to 1.4) →
split → color_flash → scroll → cut. Each transition gets its own
section + descriptive widget text so the reader can match the
visual to the name. \`cut\` is included as the no-transition
baseline at the end. \`# render-duration: 22\` extends the
auto-render budget."
```

---

## Task 5: Sprite family showcase (move to long-demos)

**Files:**
- Delete: `docs/site/demos/transitions-sprite.toml`
- Delete: `docs/site/public/demos/transitions-sprite.gif` (gitignored, but remove locally to avoid confusion)
- Create: `docs/site/demos-long/transitions-sprite.toml`
- Create: `docs/site/public/demos-long/transitions-sprite.gif` (rendered, committed)
- Modify: `docs/site/src/content/docs/transitions/sprite.mdx`

Sprite-trail transitions are slower per-instance (~1.5-3 s each) and there are 5 families to demonstrate. 5 × ~5 s per section = ~25 s content; the wallclock-to-content ratio for sprite-trail content is moderate (renderer does real work per frame). Move to the long-running pipeline so it renders once and the committed gif serves all subsequent docs builds without redoing the work on every Cloudflare deploy.

- [ ] **Step 1: Delete the auto-render version**

```bash
git rm docs/site/demos/transitions-sprite.toml
rm -f docs/site/public/demos/transitions-sprite.gif
```

- [ ] **Step 2: Create the long-demo TOML**

Write `docs/site/demos-long/transitions-sprite.toml`:

```toml
# Long demo: sprite transition showcase — pokeball, baseball,
# nyancat, pacman, sailor_moon in sequence. Moved from auto-render
# to long-running because sprite-trail transitions take 1.5-3 s
# each and stacking 5 families pushes wallclock render time past
# what's reasonable to redo on every Cloudflare build.
#
# The smallsign-flavored canvas (160x16) means low-res sprite
# variants render — not the bigsign hi-res Nyan Cat / animated
# Pikachu. That's intentional: this gif is the at-a-glance
# reference, not a hardware showcase. Hi-res variants are described
# in transitions/sprite.mdx Pitfalls.
#
# render-duration: 60
# ↑ 5 sections × (~6 s avg per section, including the slower
#   sprite-trail transitions) ≈ 25-30 s content; capture 60 s
#   wallclock allows for the renderer's realistic capture rate
#   on sprite content.
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[transitions]
between_sections = "cut"

[[playlist.section]]
mode = "swap"
transition = "pokeball"
transition_duration = 2.0
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "pokeball"

[[playlist.section.widget]]
type = "message"
text = "+ pikachu"

[[playlist.section]]
mode = "swap"
transition = "baseball"
transition_duration = 1.8
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "baseball"

[[playlist.section.widget]]
type = "message"
text = "stitched roll"

[[playlist.section]]
mode = "swap"
transition = "nyancat"
transition_duration = 2.0
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "nyancat"

[[playlist.section.widget]]
type = "message"
text = "rainbow trail"

[[playlist.section]]
mode = "swap"
transition = "pacman"
transition_duration = 2.0
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "pacman"

[[playlist.section.widget]]
type = "message"
text = "+ ghosts"

[[playlist.section]]
mode = "swap"
transition = "sailor_moon"
transition_duration = 2.0
loop_count = 1
hold_time = 1.5

[[playlist.section.widget]]
type = "message"
text = "sailor_moon"

[[playlist.section.widget]]
type = "message"
text = "wand sweep"
```

- [ ] **Step 3: Render the long-demo locally**

```bash
make render-long-demo NAME=transitions-sprite
```

Expected output: `[render-long-demo] docs/site/demos-long/transitions-sprite.toml (60s)` followed by a few minutes of renderer output, then a `Wrote ...` line. The render takes wallclock minutes (sprite content is slow to capture).

- [ ] **Step 4: Verify the gif**

```bash
ls -l docs/site/public/demos-long/transitions-sprite.gif
uv run python -c "from PIL import Image; im = Image.open('docs/site/public/demos-long/transitions-sprite.gif'); print(f'frames={im.n_frames} content_s={im.n_frames * 0.05:.1f}')"
```

Expected: file size > 100 KB (5 sprite families with motion = lots of distinct frames), frame count > 200, content_s > 10. If the file is tiny or has < 50 frames, the render bailed early — check stderr from `make render-long-demo` and re-run with a longer `# render-duration:` if needed.

If the rendered gif visually skips one of the sprites or the content_s is much shorter than the 60 s `render-duration`, that's the render-rate ceiling — bump `render-duration` to 90 in the TOML and re-render.

- [ ] **Step 5: Update `sprite.mdx`**

Find:

```mdx
<DemoGif src="/demos/transitions-sprite.gif" caption="pokeball_alternating between two messages" />
```

Replace with:

```mdx
<DemoGif src="/demos-long/transitions-sprite.gif" caption="sprite family — pokeball, baseball, nyancat, pacman, sailor_moon (smallsign-flavored; hi-res variants render automatically on bigsign)" />
```

- [ ] **Step 6: Lint + build**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -3
```

Expected: 0 lint, 39 pages built.

- [ ] **Step 7: Verify the new image lands in dist**

```bash
test -f docs/site/dist/demos-long/transitions-sprite.gif && echo OK gif-in-dist
```

- [ ] **Step 8: Commit**

```bash
git add docs/site/demos-long/transitions-sprite.toml \
        docs/site/public/demos-long/transitions-sprite.gif \
        docs/site/src/content/docs/transitions/sprite.mdx
git rm docs/site/demos/transitions-sprite.toml
git commit -m "docs: sprite transition showcase — 5 families, moved to long pipeline

User feedback: want gifs of nearly every transition for reference.
The sprite family had only one demo (pokeball_alternating). Add a
showcase covering pokeball, baseball, nyancat, pacman, sailor_moon
in sequence so a reader sees each family's character + trail style
without having to render configs themselves.

Move to docs/site/demos-long/ because sprite-trail transitions take
1.5-3 s each; stacking 5 families pushes the wallclock render time
past what's reasonable to redo on every Cloudflare build. Same
pattern as widget-two_row, widget-mlb, etc. — render once locally,
commit the gif, served as-is by Cloudflare.

The captured gif is smallsign-flavored (160x16, low-res sprites);
hi-res Nyan Cat / Pikachu variants render automatically on bigsign
at scale=4. Caption notes this so a bigsign user knows what to
expect."
```

---

## Task 6: Final integration

- [ ] **Step 1: Full lint + build pass**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
cd docs/site && pnpm run build 2>&1 | tail -5
```

Expected: 0 lint, 39 pages built.

- [ ] **Step 2: Verify all expected outputs**

```bash
# Refreshed weather
test -f docs/site/public/demos-long/widget-weather.gif && \
  [ "$(stat -f%z docs/site/public/demos-long/widget-weather.gif 2>/dev/null || stat -c%s docs/site/public/demos-long/widget-weather.gif)" -gt 10000 ] && \
  echo OK weather-refreshed

# New sprite long-demo
test -f docs/site/public/demos-long/transitions-sprite.gif && echo OK sprite-long-demo
test -f docs/site/dist/demos-long/transitions-sprite.gif && echo OK sprite-in-dist

# Auto-render TOMLs
test -f docs/site/demos/transitions-push.toml && echo OK push-toml
test -f docs/site/demos/transitions-wipe.toml && echo OK wipe-toml
test -f docs/site/demos/transitions-special.toml && echo OK special-toml
[ ! -f docs/site/demos/push-left.toml ] && echo OK old-push-removed
[ ! -f docs/site/demos/transitions-sprite.toml ] && echo OK old-sprite-removed

# mdx caption updates
grep -q 'push family — left, right, up, down' docs/site/dist/transitions/push/index.html && echo OK push-caption
grep -q 'wipe family — left, right, up, down' docs/site/dist/transitions/wipe/index.html && echo OK wipe-caption
grep -q 'special family — dissolve, split' docs/site/dist/transitions/special/index.html && echo OK special-caption
grep -q 'sprite family — pokeball, baseball, nyancat' docs/site/dist/transitions/sprite/index.html && echo OK sprite-caption

# DemoGif src points at the right path
grep -q '/demos/transitions-push.gif' docs/site/dist/transitions/push/index.html && echo OK push-src
grep -q '/demos-long/transitions-sprite.gif' docs/site/dist/transitions/sprite/index.html && echo OK sprite-src-long
```

Expected: 13 OK lines.

- [ ] **Step 3: Run Python suite as sanity check**

```bash
PYTHONPATH=tests/stubs uv run pytest -q 2>&1 | tail -3
```

Expected: 1439 passed, 2 skipped (or current baseline; no Python touched in this PR).

- [ ] **Step 4: Push and open PR**

```bash
git push -u origin worktree-demo-gifs-refresh
gh pr create --title "docs: demo gifs refresh — weather (.env), expanded transition showcases" --body "$(cat <<'EOF'
## Summary

Six gif fixes from review feedback. Single PR, six commits.

- **Weather long-demo refreshed** — prior render produced a 1.3 KB gif because `WEATHERAPI_KEY` wasn't sourced. Re-rendered with `.env` loaded.
- **Push family showcase** — replaced `push-left.toml` (single direction at duration 0.6, felt rapid) with `transitions-push.toml`: multi-section showcase covering push_left, push_right, push_up, push_down, push_random at duration 0.9. `# render-duration: 22`.
- **Wipe family showcase** — replaced `wipe_alternating` demo (cut too quick after first loop) with multi-section showcase covering wipe_left/right/up/down/random with each direction's default sweep color. `# render-duration: 22`.
- **Special family showcase** — slowed dissolve from 0.6 → 1.4 (TV-static effect plays out cleanly) and added split, color_flash, scroll, cut variants. Multi-section showcase. `# render-duration: 22`.
- **Sprite family showcase** — moved from auto-render to `demos-long/`. Five sections covering pokeball, baseball, nyancat, pacman, sailor_moon. Long-pipeline because sprite-trail transitions take 1.5-3 s each; 5 families stacked pushes wallclock render past auto-render's per-build budget. Renders once locally, commits the gif.
- **MDX caption updates** — push.mdx, wipe.mdx, special.mdx, sprite.mdx updated to describe the new multi-variant content. sprite.mdx DemoGif src moves from `/demos/` to `/demos-long/`.

## Test plan

- [x] `pnpm run lint` clean (0/0/0)
- [x] `pnpm run build` builds 39 pages
- [x] All 13 verification grep checks pass (refreshed weather, new sprite long-demo, all TOMLs, all caption updates, src paths)
- [x] Python test suite passes unchanged

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review checklist

**Spec coverage** — every feedback item maps to a task:

- ✅ Weather widget — API key from main repo's .env → Task 1
- ✅ Push transition too quick + show other directions → Task 2
- ✅ Slow down dissolve in special transitions → Task 4
- ✅ Wipe transitions cut too quick + show other directions → Task 3
- ✅ Want gifs of nearly every transition for reference → covered across Tasks 2-5 (push family × 5, wipe family × 5, special family × 5, sprite family × 5 = 20 of 33 transitions get explicit demos; the remaining `_alternating` and `_reverse` variants are documented behavior derivable from the showcased forward variants)
- ✅ Move any to long-running gifs → Task 5 (sprite moves; rest stay auto)

**Placeholder scan** — no TBDs / TODOs / "fill in later". Every TOML is given verbatim. Every commit message is given verbatim. Every verification command is given exactly.

**Type consistency** —
- TOML schema (`[display]`, `[[playlist.section]]`, `[[playlist.section.widget]]`) is consistent across all task TOMLs.
- File paths used in Task 5's sprite `git rm` (`docs/site/demos/transitions-sprite.toml`) match Task 6's verification check (`! -f` should be true after Task 5 deletes it).
- `# render-duration:` comment format (`# render-duration: N`) matches what `Makefile`'s `render-long-demo` and `docs/site/scripts/build-demos.mjs` already parse — verified earlier in the codebase.
- `between_sections = "cut"` is set on all four showcase TOMLs (push, wipe, special, sprite) so inter-section boundaries don't compete with the named-direction transitions being demonstrated.

**Out of scope (intentional):**
- Rendering ALL 33 transitions individually — that would be 33 separate gifs, low marginal value over the family showcases. The 5 family showcases × ~5 variants each cover the visually distinct cases; `_alternating` and `_reverse` variants are documented behavior derivable from the showcased forward forms.
- Hi-res sprite variants on bigsign — the smallsign-flavored renderer can't capture these; the sprite.mdx caption notes hi-res variants render automatically on bigsign.
- Showcase gif tuning past first render — if a captured gif looks visually wrong (e.g. content clipped, transition not visible), the implementer adjusts `transition_duration` / `hold_time` / `# render-duration:` and re-renders within the same task. Not a separate task.
