# Renderer Single-Frame Regression Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `tools/render_demo/render.py` reliably produce multi-frame gifs for live-data widget demos (weather, coinbase, coingecko, etherscan, mlb, mlb_standings, rss_feed). The current state ships a 1.2 KB single-frame gif because every captured canvas snapshot is byte-identical and `imageio.mimsave` collapses identical frames into one. Fix the root cause, add a tripwire test that catches single-frame regressions, then re-render the affected long demos so the committed gifs accurately represent the widgets.

**Architecture:** Three phases.

- **Phase 1 — Diagnosis (Task 1).** Confirm whether the captured single frame shows loaded widget data (cosmetic dedupe issue) or pre-load empty state (genuine data-flow bug). The fix differs significantly depending on the answer; we don't guess.
- **Phase 2 — Fix (Task 2 or Task 2-bis).** If frames show real data → add visual variation to live-data demo TOMLs (`border = "rainbow"` is the cheapest source of per-frame change) so frames differ. If frames are empty → bisect for the regression commit and fix the data-flow bug.
- **Phase 3 — Tripwire + re-render (Tasks 3-5).** New renderer smoke test that asserts `n_frames > 1` for a live-data fixture so this regression can't sneak back. Re-render every affected long demo. Final integration.

**Tech stack:** Python renderer (`tools/render_demo/render.py`) using `imageio.v2.mimsave` (v2.37.x). PIL for frame inspection. Pytest for the tripwire. Long-demo TOMLs at `docs/site/demos-long/`. Make targets `make render-long-demo NAME=…` and `make render-long-demos`.

**Worktree convention:** Per project memory, lands via worktree + PR. Use `EnterWorktree name="renderer-static-frame-fix"`.

**Pre-PR debug evidence already gathered (don't re-walk these):**
- WeatherAPI key in `/Users/james/projects/github/jamesawesome/led-ticker/.env` is valid: `curl "https://api.weatherapi.com/v1/current.json?key=$WEATHERAPI_KEY&q=Brooklyn,NY"` returns real Brooklyn weather data.
- `WeatherWidget.start(...)` standalone (driven by aiohttp + the same env-loaded key) populates `current_temp` and `weather` correctly within < 1 sec.
- `tools/render_demo/render.py` driven against `docs/site/demos-long/widget-coinbase.toml` for 8 sec captures **154 frames into RecordingMatrix.frames** — the engine IS calling `SwapOnVSync` and the wrap is intercepting them.
- All 154 captured frames have an **identical MD5 hash** (confirmed by `for f in frames: hashlib.md5(f.tobytes()).hexdigest()`). imageio.mimsave collapses identical frames to one in the encoded gif.
- imageio multi-frame encoding works correctly with distinct frames (verified with minimal repro: `[Image.new('RGB',(10,10),(i*40,100,200)) for i in range(5)]` → 5-frame gif).
- The previous successful weather render (32 KB, multi-frame) was committed earlier in this codebase's history — so multi-frame live-data renders ARE achievable; something diverged.

---

## File map

### Phase 1 — Diagnosis

| File | Action | Why |
|---|---|---|
| (none — output is a markdown report in chat) | Read-only | Determine which fix branch to execute |

### Phase 2A — Cosmetic dedupe fix (if frames show real data)

| File | Action | Why |
|---|---|---|
| `docs/site/demos-long/widget-weather.toml` | Modify | Add `border = "rainbow"` to weather widget so border chase produces frame-to-frame variation |
| `docs/site/demos-long/widget-coinbase.toml` | Modify | Same — `border = "rainbow"` |
| `docs/site/demos-long/widget-coingecko.toml` | Modify | Same |
| `docs/site/demos-long/widget-mlb.toml` | Modify | Same |
| `docs/site/demos-long/widget-mlb_standings.toml` | Modify | Same |
| `docs/site/demos-long/widget-rss_feed.toml` | Modify | Same |
| `docs/site/demos-long/widget-etherscan.toml` | Modify | Same — even though render is skipped (no API key in CI), keep consistent |

### Phase 2B — Data-flow regression fix (if frames are empty)

| File | Action | Why |
|---|---|---|
| `tools/render_demo/render.py` (or wherever the bisect identifies) | Modify | Fix whatever commit broke widget data flow within `app_run` |

### Phase 3 — Tripwire + re-render

| File | Action | Why |
|---|---|---|
| `tools/render_demo/test_renderer_multiframe.py` | Create | Pytest tripwire — render fixture demo, assert `n_frames > 1` and last frame ≠ first frame |
| `docs/site/public/demos-long/widget-weather.gif` | Re-render | Multi-frame output |
| `docs/site/public/demos-long/widget-coinbase.gif` | Re-render | Same |
| `docs/site/public/demos-long/widget-coingecko.gif` | Re-render | Same |
| `docs/site/public/demos-long/widget-mlb.gif` | Re-render | Same |
| `docs/site/public/demos-long/widget-mlb_standings.gif` | Re-render | Same |
| `docs/site/public/demos-long/widget-rss_feed.gif` | Re-render | Same |
| `docs/site/public/demos-long/widget-etherscan.gif` | Skip | Requires API key not in `.env` — render-long-demos auto-skips it via `# requires-env: ETHERSCAN_API_KEY` |

---

## Per-task contract

Every task ends with:

1. Lint clean if it touched MDX / Astro: `cd docs/site && pnpm run lint 2>&1 | tail -3` (0 errors / 0 warnings / 0 hints).
2. Python tests pass if Python touched: `PYTHONPATH=tests/stubs uv run pytest -q 2>&1 | tail -3`.
3. Commit with the exact message specified.

The renderer is NOT exercised by `make test` — the renderer's own tests (`tools/render_demo/test_*.py`) are picked up via `pyproject.toml`'s `testpaths` per a prior PR.

---

## Task 1: Diagnose — does the captured single frame show real data or empty pre-load state?

**Files:**
- Read-only: `docs/site/public/demos-long/widget-weather.gif` (or render fresh)
- Read-only: `docs/site/demos-long/widget-weather.toml`

This is purely investigative — no commits. Output is a report that determines which Phase 2 task to execute.

- [ ] **Step 1: Source env and render weather**

```bash
set -a; . /Users/james/projects/github/jamesawesome/led-ticker/.env; set +a
echo "key length: ${#WEATHERAPI_KEY}"  # should be 30
make render-long-demo NAME=widget-weather 2>&1 | tail -5
```

If `WEATHERAPI_KEY` is empty or the render exits non-zero, halt and surface — that's a different problem than this plan addresses.

- [ ] **Step 2: Extract the single frame as a PNG**

```bash
uv run python -c "
from PIL import Image
im = Image.open('docs/site/public/demos-long/widget-weather.gif')
print(f'frames={im.n_frames} size={im.size}')
im.seek(0)
im.convert('RGB').save('/tmp/weather-frame-0.png')
print('Wrote /tmp/weather-frame-0.png')
"
open /tmp/weather-frame-0.png
```

- [ ] **Step 3: Classify the frame visually**

Look at the rendered PNG. There are three possible states:

**State A — Real data on canvas.** You see "Brooklyn:" label + a temperature value (e.g. "54F") + a small weather condition icon. The widget loaded successfully; the gif is single-frame because every tick after data load showed the same content and imageio deduped them.

**State B — Empty / pre-load state.** Black canvas, or just the "Brooklyn:" label with no temp / icon, or a placeholder. The widget didn't get its data into the canvas before the renderer captured frames.

**State C — Garbage / corrupted.** Something else entirely. Halt and escalate.

- [ ] **Step 4: Cross-check by hashing all captured frames at the engine level (sanity check)**

Even if the gif is 1 frame, the captured-but-deduped frames may have variation that imageio collapsed. Verify:

```bash
set -a; . /Users/james/projects/github/jamesawesome/led-ticker/.env; set +a
uv run python -c "
import sys, asyncio, contextlib, hashlib
sys.path.insert(0, 'tests/stubs')
sys.path.insert(0, '.')
from pathlib import Path
from led_ticker import frame as frame_mod
from led_ticker.app import run
from tools.render_demo.recording import RecordingMatrix

holder = []
orig = frame_mod.RGBMatrix
def patched(*a, **k):
    real = orig(*a, **k); rec = RecordingMatrix(real); holder.append(rec); return rec
frame_mod.RGBMatrix = patched

async def go():
    task = asyncio.create_task(run(Path('docs/site/demos-long/widget-weather.toml')))
    with contextlib.suppress(Exception):
        await asyncio.wait_for(asyncio.shield(task), timeout=8)
    task.cancel()
    with contextlib.suppress(BaseException):
        await task

asyncio.run(go())
frames = holder[0].frames if holder else []
print(f'captured: {len(frames)}')
hashes = set()
for f in frames:
    hashes.add(hashlib.md5(f.tobytes()).hexdigest()[:8])
print(f'distinct frame hashes: {len(hashes)}')
"
```

If `distinct frame hashes` reports `1`: every captured frame is byte-identical → confirms cosmetic dedupe. → **Phase 2A**.

If `distinct frame hashes` > 1 but the encoded gif is still 1 frame: imageio is mis-encoding and we have a separate encoder bug. → escalate.

If `captured: 0` or `< 5`: the engine is barely running → data-flow / event-loop bug. → **Phase 2B**.

- [ ] **Step 5: Report**

Surface to the chat one of:

- "**State A confirmed** — frames show real Brooklyn weather data; identical frames are correct; encoder dedupes them. Proceeding to Task 2A (cosmetic fix via demo-TOML border chase)."
- "**State B confirmed** — frames are empty/pre-load; widget data isn't reaching the canvas. Proceeding to Task 2B (bisect for regression)."
- "**Unexpected state** — escalate."

---

## Task 2A: Add `border = "rainbow"` to live-data demo TOMLs

**Run only if Task 1 reports State A.**

**Files:**
- Modify: `docs/site/demos-long/widget-weather.toml`
- Modify: `docs/site/demos-long/widget-coinbase.toml`
- Modify: `docs/site/demos-long/widget-coingecko.toml`
- Modify: `docs/site/demos-long/widget-mlb.toml`
- Modify: `docs/site/demos-long/widget-mlb_standings.toml`
- Modify: `docs/site/demos-long/widget-rss_feed.toml`
- Modify: `docs/site/demos-long/widget-etherscan.toml`

`border = "rainbow"` adds an animated 1-pixel perimeter chase that paints to physical pixel resolution via `unwrap_to_real`. The chase advances a hue per engine tick (50 ms cadence), so every captured frame differs from the next — imageio sees N distinct frames and writes a multi-frame gif. Bonus: looks better visually, since a static weather card looks like a screenshot while a static card with a chasing rainbow border looks alive.

Per `CLAUDE.md`, `border` is accepted on `message`, `countdown`, `two_row`, `gif`, and `image` widgets. Live-data widgets that wrap text (weather, coinbase, coingecko, mlb, mlb_standings, etherscan) use the message-widget render path internally and accept border via the same wiring. `rss_feed` doesn't have its own draw — it expands stories into TickerMessages — so border on `rss_feed` may not work; verify in step 1 before adding.

- [ ] **Step 1: Verify which live-data widgets accept `border`**

```bash
grep -nE 'border:|self\.border' src/led_ticker/widgets/weather.py src/led_ticker/widgets/crypto/*.py src/led_ticker/widgets/mlb*.py src/led_ticker/widgets/rss_feed.py 2>&1 | head -20
```

Expected: weather, coinbase, coingecko, mlb, mlb_standings, etherscan all reference `border`. `rss_feed` may not (it has no `draw()`). If any widget doesn't accept border, exclude it from the bulk edit and note in the commit message.

- [ ] **Step 2: Add `border = "rainbow"` to each accepting widget's TOML**

For each TOML in the file map, edit the `[[playlist.section.widget]]` block to add `border = "rainbow"` as a new field. Example for `widget-weather.toml` — add the line shown:

```toml
[[playlist.section.widget]]
type = "weather"
message = "Brooklyn"
location = "Brooklyn, NY"
units = "imperial"
update_interval = 5
border = "rainbow"
```

Apply the equivalent to coinbase, coingecko, mlb, mlb_standings, etherscan. Skip rss_feed if step 1 confirmed it doesn't support border.

- [ ] **Step 3: Render one TOML to verify the fix works**

```bash
set -a; . /Users/james/projects/github/jamesawesome/led-ticker/.env; set +a
make render-long-demo NAME=widget-weather 2>&1 | tail -3
ls -l docs/site/public/demos-long/widget-weather.gif
uv run python -c "from PIL import Image; im = Image.open('docs/site/public/demos-long/widget-weather.gif'); print(f'frames={im.n_frames}')"
```

Expected: file size > 30 KB (border chase produces lots of distinct frames), `n_frames > 30`. If still 1 frame, halt — the border isn't varying as expected; escalate.

- [ ] **Step 4: Commit the TOML changes (gifs re-rendered in Task 5)**

```bash
git add docs/site/demos-long/widget-*.toml
git commit -m "demos: rainbow-border live-data widgets so renderer captures frame variation

Live-data widget demos (weather, coinbase, coingecko, mlb,
mlb_standings, etherscan) render as completely-static cards once
their async data load completes. Every captured engine tick produces
a byte-identical canvas, and imageio.mimsave correctly collapses
identical frames into one — yielding a 1.2 KB single-frame gif that
looks like a render error.

Add \`border = \"rainbow\"\` to each accepting widget's section.
RainbowChaseBorder advances one hue per 50 ms engine tick, so each
captured frame differs from the next; imageio writes a multi-frame
gif. Side benefit: visually the cards look alive instead of static,
which fits the docs-site demo intent better than a screenshot would.

(rss_feed excluded — no \`draw()\` of its own; stories expand into
TickerMessages that get the section's transition / color settings,
not a \`border\` field.)
"
```

---

## Task 2B: Bisect for the data-flow regression and fix it

**Run only if Task 1 reports State B.**

**Files:**
- Modify: whatever commit the bisect identifies as introducing the regression

This task is harder to scope in advance because the fix depends on what the bisect surfaces. Plan: identify the offending commit, then either revert it (if narrow) or fix the underlying issue (if it landed alongside related work that shouldn't revert).

- [ ] **Step 1: Find a known-working commit**

The earlier successful weather render produced a 32 KB multi-frame gif and was committed. Find that commit:

```bash
git log --all --oneline --diff-filter=M -- docs/site/public/demos-long/widget-weather.gif | head -5
```

Identify the most recent commit where the committed gif was visibly multi-frame (file size > 10 KB). That's the "good" commit for the bisect.

- [ ] **Step 2: Write the bisect test predicate**

Save as `/tmp/bisect-renderer.sh`:

```bash
#!/usr/bin/env bash
set -e
cd /Users/james/projects/github/jamesawesome/led-ticker
set -a; . ./.env; set +a
uv sync --extra dev 2>&1 > /dev/null
uv run python tools/render_demo/render.py docs/site/demos-long/widget-coinbase.toml -o /tmp/bisect.gif --duration 8 2>&1 > /dev/null
N=$(uv run python -c "from PIL import Image; print(Image.open('/tmp/bisect.gif').n_frames)")
echo "frames=$N"
[ "$N" -gt 1 ] && exit 0 || exit 1
```

`chmod +x /tmp/bisect-renderer.sh`. Predicate: `coinbase render produces > 1 frame` → exit 0 (good); else exit 1 (bad).

- [ ] **Step 3: Run the bisect**

```bash
git bisect start
git bisect bad HEAD
git bisect good <good-commit-from-step-1>
git bisect run /tmp/bisect-renderer.sh
git bisect log
git bisect reset
```

The `bisect run` command will check out commits, run the predicate, and converge on the first bad commit. Note the SHA + the change it introduced.

- [ ] **Step 4: Decide fix shape**

Read the offending commit (`git show <sha>`). Possible categories:
- **Engine tick loop change** (`ticker.py`) — likely fix is to restore a missing draw / advance_frame call in the changed loop branch
- **Async startup change** (`app.py`) — likely fix is to ensure widget background tasks run before the engine starts capturing
- **Widget regression** (`widgets/<name>.py`) — likely fix is to restore the data-population path that was removed
- **Import / module ordering** (`tools/render_demo/render.py`) — likely fix is to ensure `tests/stubs` is on `sys.path` before any led_ticker import

For any of these: write a focused fix that makes coinbase + weather render multi-frame against the existing TOMLs (no `border = "rainbow"` workaround needed).

- [ ] **Step 5: Verify the fix and commit**

```bash
set -a; . /Users/james/projects/github/jamesawesome/led-ticker/.env; set +a
uv run python tools/render_demo/render.py docs/site/demos-long/widget-coinbase.toml -o /tmp/coinbase-fixed.gif --duration 8
uv run python -c "from PIL import Image; print('frames=', Image.open('/tmp/coinbase-fixed.gif').n_frames)"
```

Expected: `frames= > 1`. If still 1, the fix is incomplete — iterate.

```bash
git add <fixed files>
git commit -m "fix(renderer): restore widget data flow for live-data demos

Bisect identified <SHA> as the regression commit. <One-paragraph
explanation of what broke and what the fix restores.>

Verified: coinbase + weather long demos now render multi-frame gifs
when run against the same TOMLs that previously produced 1-frame
output."
```

---

## Task 3: Add a renderer multi-frame tripwire test

**Files:**
- Create: `tools/render_demo/test_renderer_multiframe.py`

Catch this regression class proactively. Test renders a small fixture config that should produce a multi-frame gif, asserts both frame count > 1 AND first-frame ≠ last-frame (catches dedupe-collapse AND empty-data cases).

Use a synthetic fixture config — not a real long-demo — so the test doesn't depend on `WEATHERAPI_KEY` or network. A `message` widget with `font_color = "rainbow"` produces per-tick hue variation that exercises the same render path as live-data widgets with rainbow borders.

- [ ] **Step 1: Write the test file**

Create `tools/render_demo/test_renderer_multiframe.py`:

```python
"""Tripwire: render output for an animated widget must produce a
multi-frame gif with visually distinct first and last frames.

Catches two regression classes:
  - Engine produces 1 frame total (would mean the engine isn't
    swapping the canvas, e.g. a tick-loop regression)
  - Engine swaps but every frame is identical (would mean the widget
    isn't advancing its animated state, OR imageio mis-encodes).

Fixture is a minimal synthetic message widget with
`font_color = "rainbow"` — per-character hue advances every 50 ms
engine tick, which produces visually distinct canvases without
needing network / API keys / live data. If this test ever fails,
something between RecordingMatrix.SwapOnVSync and
imageio.mimsave's frame ordering broke.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image
import pytest

from tools.render_demo.render import render

FIXTURE_TOML = """
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
text = "Hello"
font_color = "rainbow"
"""


def test_render_animated_widget_produces_multiframe_gif(tmp_path: Path) -> None:
    """A rainbow-text message rendered for 4 sec must produce a
    multi-frame gif (rainbow hue cycles every 50 ms tick → 80 distinct
    frames in 4 sec; some get deduped if identical, but at least
    several distinct frames remain)."""
    cfg = tmp_path / "fixture.toml"
    cfg.write_text(FIXTURE_TOML)
    out = tmp_path / "out.gif"

    render(cfg, out, duration=4.0, upscale=1, fps=20)

    assert out.exists(), "Renderer produced no output file"
    im = Image.open(out)
    assert im.n_frames > 1, (
        f"Renderer produced single-frame gif ({out.stat().st_size} bytes). "
        f"Either the engine isn't swapping (RecordingMatrix.frames empty) "
        f"or every captured frame is byte-identical (widget isn't varying "
        f"its canvas, OR imageio dedupe collapsed them). See "
        f"tools/render_demo/test_renderer_multiframe.py docstring for the "
        f"two regression classes this test guards against."
    )


def test_render_first_and_last_frames_differ(tmp_path: Path) -> None:
    """Stronger assertion: first-frame and last-frame of the rendered
    gif must differ. Catches the case where n_frames > 1 but the
    encoder writes a sequence like [A, A, A, A] that PIL still reports
    as multi-frame because of how the gif structure is stored."""
    cfg = tmp_path / "fixture.toml"
    cfg.write_text(FIXTURE_TOML)
    out = tmp_path / "out.gif"

    render(cfg, out, duration=4.0, upscale=1, fps=20)

    im = Image.open(out)
    im.seek(0)
    first = hashlib.md5(im.convert("RGB").tobytes()).hexdigest()
    im.seek(im.n_frames - 1)
    last = hashlib.md5(im.convert("RGB").tobytes()).hexdigest()

    assert first != last, (
        f"First and last frames of rendered gif have identical content "
        f"(both hash to {first[:8]}). The widget isn't varying its canvas "
        f"across the {im.n_frames}-frame capture. Confirm the rainbow "
        f"text animation is working: drop into a Python REPL and call "
        f"`message.draw()` at successive frame counts on a TickerMessage "
        f"with font_color='rainbow' — colors should cycle."
    )
```

- [ ] **Step 2: Run the new tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tools/render_demo/test_renderer_multiframe.py -v 2>&1 | tail -10
```

Expected (post-fix from Task 2A or 2B): both tests PASS.

If the tests FAIL after Task 2A/2B, the fix is incomplete — iterate on the underlying issue before continuing. Don't paper over with `pytest.mark.skip`.

- [ ] **Step 3: Commit**

```bash
git add tools/render_demo/test_renderer_multiframe.py
git commit -m "test(renderer): tripwire — gif output must be multi-frame + first ≠ last

Catches two regression classes that surfaced in this PR:
  - Engine swaps the canvas but every captured frame is byte-identical
    (widget isn't advancing its animated state OR imageio dedupes)
  - Engine produces 1 frame total (tick-loop regression)

Fixture is a minimal synthetic message widget with
font_color = \"rainbow\" — produces per-tick hue variation that
exercises the same render path as live-data widgets without needing
network or API keys.

Two assertions: (1) gif is multi-frame, (2) first and last frame
hashes differ. The two together cover the dedupe-collapse case and
the inserted-but-identical-frames case."
```

---

## Task 4: Re-render all affected live-data long demos

**Files:**
- Re-render: `docs/site/public/demos-long/widget-weather.gif`
- Re-render: `docs/site/public/demos-long/widget-coinbase.gif`
- Re-render: `docs/site/public/demos-long/widget-coingecko.gif`
- Re-render: `docs/site/public/demos-long/widget-mlb.gif`
- Re-render: `docs/site/public/demos-long/widget-mlb_standings.gif`
- Re-render: `docs/site/public/demos-long/widget-rss_feed.gif`
- Skip: `docs/site/public/demos-long/widget-etherscan.gif` (no `ETHERSCAN_API_KEY` in `.env`; render-long-demos auto-skips)

- [ ] **Step 1: Source env and run the bulk render**

The `make render-long-demos` target sources `.env` automatically when run from a directory that has it. The worktree DOESN'T have `.env`, so source explicitly:

```bash
set -a; . /Users/james/projects/github/jamesawesome/led-ticker/.env; set +a
make render-long-demos 2>&1 | tail -20
```

Expected: a `[render-long-demos]` line per TOML, with `[render-long-demos] SKIP widget-etherscan` for the etherscan one (no key). All others should print `rendering ... (Ns)`.

- [ ] **Step 2: Verify each gif is multi-frame**

```bash
for name in widget-weather widget-coinbase widget-coingecko widget-mlb widget-mlb_standings widget-rss_feed widget-two_row; do
  if [ -f "docs/site/public/demos-long/$name.gif" ]; then
    n=$(uv run python -c "from PIL import Image; print(Image.open('docs/site/public/demos-long/$name.gif').n_frames)")
    bytes=$(stat -f%z "docs/site/public/demos-long/$name.gif" 2>/dev/null || stat -c%s "docs/site/public/demos-long/$name.gif")
    if [ "$n" -gt 1 ]; then echo "OK $name n_frames=$n size=$bytes"; else echo "FAIL $name n_frames=$n (single-frame)"; fi
  else
    echo "MISSING $name (skipped or render failed)"
  fi
done
```

Expected: all listed (except etherscan, which is missing/skipped) report `OK ... n_frames > 1`. If anything reports `FAIL`, either the fix from Task 2A/2B doesn't fully cover that widget OR that widget needs its own border-add (re-check Task 2A coverage).

- [ ] **Step 3: Commit the re-rendered gifs**

```bash
git add docs/site/public/demos-long/widget-*.gif
git commit -m "demos: re-render all live-data long demos (multi-frame after renderer fix)

After Task 2 (rainbow-border live-data widgets / data-flow fix),
all live-data long demos render as multi-frame gifs showing the
animated content (chasing rainbow border around the loaded widget
data) rather than the prior 1.2 KB single-frame collapse.

Verified: every committed gif is multi-frame; etherscan stays
skipped (no API key in .env)."
```

---

## Task 5: Final integration

- [ ] **Step 1: Full lint pass**

```bash
cd docs/site && pnpm run lint 2>&1 | tail -3
```

Expected: 0 / 0 / 0.

- [ ] **Step 2: Full Python suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -q 2>&1 | tail -3
```

Expected: previous baseline + 2 new tests from Task 3 passing.

- [ ] **Step 3: Verify the dist build picks up the new gifs**

```bash
cd docs/site && pnpm run build 2>&1 | tail -3
test -f docs/site/dist/demos-long/widget-weather.gif && echo OK weather-in-dist
```

- [ ] **Step 4: Push and open PR**

```bash
git push -u origin worktree-renderer-static-frame-fix
gh pr create --title "fix(renderer): live-data widget gifs collapse to single frame" --body "$(cat <<'EOF'
## Summary

Fixes a regression where `tools/render_demo/render.py` produced 1.2 KB single-frame gifs for every live-data widget long-demo (weather, coinbase, coingecko, mlb, mlb_standings, rss_feed). The captured canvas snapshots were byte-identical across the entire render window, and imageio.mimsave correctly deduped them to one frame.

## Diagnosis

Ran the diagnosis flow in `docs/superpowers/plans/2026-05-09-renderer-static-frame-fix.md` Task 1: confirmed the captured single frame showed [REAL DATA / EMPTY STATE — fill in once Task 1 runs]. Root cause: [from Task 1 report].

## Fix

- [If Task 2A path] Added `border = "rainbow"` to live-data widget demo TOMLs so the perimeter chase produces per-tick frame variation. Bonus: visually the demos feel alive instead of looking like screenshots.
- [If Task 2B path] [Bisect-identified commit + revert/fix description]

Plus a new pytest tripwire (`tools/render_demo/test_renderer_multiframe.py`) with two assertions — `n_frames > 1` AND `first-frame ≠ last-frame` — so this regression class is caught by CI in the future.

## Test plan

- [x] New renderer tripwire tests pass
- [x] All live-data long demos re-rendered as multi-frame gifs (etherscan skipped; no key in .env)
- [x] Existing test suite unchanged baseline
- [x] Docs site build + lint clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review checklist

**Spec coverage:**
- ✅ Diagnose: Task 1 (decision branch on real-data vs empty-state)
- ✅ Fix: Task 2A (cosmetic via demo TOMLs) OR Task 2B (data-flow bisect)
- ✅ Tripwire: Task 3 (new pytest)
- ✅ Re-render affected demos: Task 4
- ✅ Final integration: Task 5

**Placeholder scan:** Two intentional `[fill in once Task 1 runs]` / `[from Task 1 report]` markers in the PR body — these are filled in at PR-open time after Task 1's diagnostic report determines the actual root cause. Not a placeholder failure; a downstream-fill point. Acceptable because the PR body explicitly references the diagnostic report that Task 1 produces.

**Type consistency:** File paths in Task 4's verification loop match the file map. The bisect script's `> /dev/null` redirects stderr — make sure that doesn't hide real errors during the bisect (intentional: the bisect predicate only cares about the final n_frames count, but verify the bisect's first run shows something sensible).

**What's intentionally out of scope:**
- Re-rendering transition / auto-render demos. Those produce visually distinct frames (transitions are animated by definition) so they're unaffected by the dedupe issue.
- The original `2026-05-09-demo-gifs-refresh.md` plan. After this PR lands, that plan's Task 1 (weather refresh) is largely done by Task 4 here, but the transition-family showcases (T2-T5 there) are still pending.
- `widget-two_row` long demo — already multi-frame because the bottom row scrolls (frame variation from scroll position). Re-render in Task 4 only as a sanity check; expect no change.
