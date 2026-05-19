# Slim gif_plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse `tools/gif_plan/` from ~2,000 lines + 169 tests to one ~120-line module + ~18 tests that emits a recommended `--duration` and a one-line cutoff guard, and slim the `making-a-gif` skill/docs to match.

**Architecture:** A single `plan.py` with a coarse per-widget duration heuristic (dominant magnitude terms only), a `total`/`recommended` aggregation, and a `# render-duration:` cutoff check. CLI prints ≤2 lines, exit codes `0/2/3`. The `widgets.py`/`totals.py`/`flags.py` split, JSON, 6 advisory flags, and the ±20% dogfood are deleted outright. Spec: `docs/superpowers/specs/2026-05-18-gif-plan-reduction-design.md`.

**Tech Stack:** Python 3.13 stdlib (`tomllib`, `re`, `math`, `pathlib`), optional Pillow for gif frame durations, pytest. Branch `slim-gif-plan` (worktree already created off `main`).

---

### Task 1: Replace the estimator + tests

**Files:**
- Modify (full rewrite): `tools/gif_plan/plan.py`
- Delete: `tools/gif_plan/widgets.py`, `tools/gif_plan/totals.py`, `tools/gif_plan/flags.py`, `tools/gif_plan/README.md`, `tools/gif_plan/test_widgets.py`, `tools/gif_plan/test_totals.py`, `tools/gif_plan/test_flags.py`, `tools/gif_plan/test_dogfood.py`
- Keep untouched: `tools/gif_plan/__init__.py`, `tools/gif_plan/conftest.py`
- Test (full rewrite): `tools/gif_plan/test_plan.py`

- [ ] **Step 1: Replace `tools/gif_plan/plan.py` with the coarse estimator**

```python
"""Coarse demo-gif duration estimator for the making-a-gif skill.

Single purpose: tell Claude the `--duration` to render a led-ticker
demo with, and flag when a pinned `# render-duration:` header is too
short (the gif would clip and need re-rendering). Deliberately rough —
it models only the dominant timing terms. Precision is not the goal;
not wasting a render is. See
docs/superpowers/specs/2026-05-18-gif-plan-reduction-design.md.
"""

from __future__ import annotations

import math
import re
import sys
import tomllib
from pathlib import Path

_FONT_CELL_W = 6  # FONT_DEFAULT (6x12) cell width, px
_EMOJI_W = 8  # inline :slug: sprite width, px
_DEFAULT_HOLD_S = 3.0  # SectionConfig.hold_time default
_DEFAULT_HOLD_SECONDS = 5.0  # StillImage.hold_seconds default
_DEFAULT_STEP_MS = 50  # scroll step when a section omits scroll_step_ms
_GIF_FALLBACK_LOOP_MS = 1000  # used when a gif path can't be read

_EMOJI_RE = re.compile(r":[a-z_]+:")
_HEADER_RE = re.compile(r"^\s*#\s*render-duration\s*:\s*(\d+)", re.MULTILINE)

EXIT_OK = 0
EXIT_CUTOFF = 2
EXIT_TOOL_ERROR = 3


class PlanError(Exception):
    """Recoverable tool/usage error (missing or malformed TOML)."""


def _canvas_w(display: dict, section: dict) -> int:
    cols = int(display.get("cols", 64))
    chain = int(display.get("chain", 1))
    scale = int(section.get("scale") or display.get("default_scale") or 1)
    return cols * chain // max(1, scale)


def _content_w(text: str) -> int:
    if not text:
        return 0
    emoji = len(_EMOJI_RE.findall(text))
    stripped = _EMOJI_RE.sub("", text)
    return len(stripped) * _FONT_CELL_W + emoji * _EMOJI_W


def _gif_loop_ms(path: Path) -> int:
    try:
        from PIL import Image
    except ImportError:
        return _GIF_FALLBACK_LOOP_MS
    try:
        with Image.open(path) as im:
            total = 0
            for i in range(getattr(im, "n_frames", 1)):
                im.seek(i)
                total += int(im.info.get("duration", 100))
            return max(1, total)
    except (FileNotFoundError, OSError, ValueError):
        return _GIF_FALLBACK_LOOP_MS


def widget_ms(widget: dict, section: dict, canvas_w: int, config_dir: Path) -> int:
    """Coarse per-widget visit time in ms. Dominant terms only."""
    wtype = widget.get("type", "")
    hold_ms = int(float(section.get("hold_time", _DEFAULT_HOLD_S)) * 1000)
    if wtype in ("message", "countdown", "two_row"):
        text = widget.get("bottom_text") or widget.get("text", "")
        step = int(section.get("scroll_step_ms") or _DEFAULT_STEP_MS)
        overflow = max(0, _content_w(text) - canvas_w)
        return hold_ms + overflow * step
    if wtype in ("image", "still"):
        return int(float(widget.get("hold_seconds", _DEFAULT_HOLD_SECONDS)) * 1000)
    if wtype == "gif":
        if int(widget.get("gif_loops", 1)) == 0:
            return hold_ms
        p = Path(widget.get("path", ""))
        if not p.is_absolute():
            p = (config_dir / p).resolve()
        return _gif_loop_ms(p) * int(widget.get("gif_loops", 1))
    return 0  # data-fetch / unknown — runtime-dependent, contributes 0


def total_ms(config: dict, config_dir: Path) -> int:
    display = config.get("display", {})
    sections = (config.get("playlist") or {}).get("section") or []
    total = 0
    for s in sections:
        if s.get("mode", "swap") != "swap" or s.get("loop_count") == 0:
            continue  # forever/infini/loop-forever — runtime-dependent
        cw = _canvas_w(display, s)
        loop = int(s.get("loop_count") or 1)
        per = sum(widget_ms(w, s, cw, config_dir) for w in s.get("widget", []))
        total += per * loop
    return total


def recommended_s(total: int) -> int:
    return max(1, math.ceil(total / 1000) + 1)


def _read_header(raw: str) -> int | None:
    m = _HEADER_RE.search(raw)
    return int(m.group(1)) if m else None


def plan(config_path: Path) -> tuple[int, int | None, int]:
    """Return (recommended_s, header_s_or_None, total_ms)."""
    try:
        raw = config_path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, PermissionError, OSError) as e:
        raise PlanError(f"cannot read config {config_path}: {e}") from e
    try:
        config = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as e:
        raise PlanError(f"malformed TOML in {config_path}: {e}") from e
    tot = total_ms(config, config_path.parent)
    return recommended_s(tot), _read_header(raw), tot


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: plan.py <config.toml>", file=sys.stderr)
        return EXIT_TOOL_ERROR
    try:
        rec, header, tot = plan(Path(args[0]))
    except PlanError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_TOOL_ERROR
    print(f"duration: {rec}")
    if header is not None and header * 1000 < tot:
        print(f"cutoff: header {header}s < ~{math.ceil(tot / 1000)}s needed")
        return EXIT_CUTOFF
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Delete the obsolete split modules, README, and old test files**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.worktrees/slim-gif-plan
git rm tools/gif_plan/widgets.py tools/gif_plan/totals.py tools/gif_plan/flags.py \
       tools/gif_plan/README.md tools/gif_plan/test_widgets.py \
       tools/gif_plan/test_totals.py tools/gif_plan/test_flags.py \
       tools/gif_plan/test_dogfood.py
```

- [ ] **Step 3: Replace `tools/gif_plan/test_plan.py` with the slim suite**

```python
"""Tests for the slimmed gif_plan estimator."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

from tools.gif_plan.plan import (
    EXIT_CUTOFF,
    EXIT_OK,
    EXIT_TOOL_ERROR,
    _canvas_w,
    _content_w,
    main,
    plan,
    recommended_s,
    total_ms,
    widget_ms,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO_ROOT / "docs" / "site" / "demos-pinned"


def _gif(path: Path, *, frames: int, dur_ms: int) -> None:
    imgs = [Image.new("RGB", (8, 8), (i, i, i)) for i in range(frames)]
    imgs[0].save(
        path, save_all=True, append_images=imgs[1:], duration=dur_ms, loop=0
    )


class TestContentWidth:
    def test_plain_text(self):
        assert _content_w("HELLO") == 5 * 6

    def test_emoji_counts_as_8(self):
        # ":star:" stripped → "hi  yo" (6 chars) ×6 + 1 emoji ×8 = 44
        assert _content_w("hi :star: yo") == 6 * 6 + 8

    def test_empty(self):
        assert _content_w("") == 0


class TestCanvasWidth:
    def test_default_scale(self):
        assert _canvas_w({"cols": 32, "chain": 5}, {}) == 160

    def test_section_scale_override(self):
        assert _canvas_w({"cols": 32, "chain": 5}, {"scale": 2}) == 80


class TestWidgetMs:
    def test_message_fits_is_hold_only(self):
        w = {"type": "message", "text": "HI"}
        s = {"hold_time": 4.0, "scroll_step_ms": 25}
        assert widget_ms(w, s, 160, Path(".")) == 4000

    def test_message_overflow_adds_scroll(self):
        w = {"type": "message", "text": "x" * 40}  # 240px
        s = {"hold_time": 4.0, "scroll_step_ms": 25}
        # hold 4000 + (240-160)*25 = 4000 + 2000 = 6000
        assert widget_ms(w, s, 160, Path(".")) == 6000

    def test_two_row_uses_bottom_text(self):
        w = {"type": "two_row", "top_text": "T", "bottom_text": "y" * 40}
        s = {"hold_time": 0.0, "scroll_step_ms": 25}
        assert widget_ms(w, s, 160, Path(".")) == (240 - 160) * 25

    def test_image_default_hold_seconds(self):
        assert widget_ms({"type": "image"}, {}, 160, Path(".")) == 5000

    def test_gif_loops_times_frame_sum(self, tmp_path):
        g = tmp_path / "g.gif"
        _gif(g, frames=2, dur_ms=100)
        w = {"type": "gif", "path": str(g), "gif_loops": 3}
        assert widget_ms(w, {}, 160, tmp_path) == 600

    def test_gif_loops_zero_is_section_hold(self, tmp_path):
        w = {"type": "gif", "path": "x.gif", "gif_loops": 0}
        assert widget_ms(w, {"hold_time": 4.0}, 160, tmp_path) == 4000

    def test_gif_relative_path_resolves_against_config_dir(self, tmp_path):
        (tmp_path / "assets").mkdir()
        (tmp_path / "cfg").mkdir()
        _gif(tmp_path / "assets" / "x.gif", frames=5, dur_ms=80)
        w = {"type": "gif", "path": "../assets/x.gif", "gif_loops": 2}
        prev = os.getcwd()
        os.chdir(REPO_ROOT)  # prove cwd-independence
        try:
            assert widget_ms(w, {}, 160, tmp_path / "cfg") == 400 * 2
        finally:
            os.chdir(prev)

    def test_unknown_widget_contributes_zero(self):
        assert widget_ms({"type": "weather"}, {}, 160, Path(".")) == 0


class TestTotals:
    def test_skips_non_swap_and_loop_count_zero(self):
        cfg = {
            "display": {"cols": 32, "chain": 5},
            "playlist": {
                "section": [
                    {
                        "mode": "swap",
                        "hold_time": 4.0,
                        "widget": [{"type": "message", "text": "HI"}],
                    },
                    {
                        "mode": "forever_scroll",
                        "widget": [{"type": "message", "text": "HI"}],
                    },
                    {
                        "mode": "swap",
                        "loop_count": 0,
                        "widget": [{"type": "message", "text": "HI"}],
                    },
                ]
            },
        }
        assert total_ms(cfg, Path(".")) == 4000

    def test_loop_count_multiplies(self):
        cfg = {
            "display": {"cols": 32, "chain": 5},
            "playlist": {
                "section": [
                    {
                        "mode": "swap",
                        "loop_count": 3,
                        "hold_time": 2.0,
                        "widget": [{"type": "message", "text": "HI"}],
                    }
                ]
            },
        }
        assert total_ms(cfg, Path(".")) == 6000

    def test_recommended_s(self):
        assert recommended_s(7000) == 8
        assert recommended_s(7001) == 9
        assert recommended_s(0) == 1


class TestCli:
    def _write(self, tmp_path: Path, body: str, header: str = "") -> Path:
        p = tmp_path / "demo.toml"
        p.write_text((header + "\n" + body).strip() + "\n")
        return p

    _BODY = """
[display]
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 4.0

[[playlist.section.widget]]
type = "message"
text = "HI"
"""

    def test_clean_exits_zero(self, tmp_path, capsys):
        cfg = self._write(tmp_path, self._BODY, "# render-duration: 5")
        assert main([str(cfg)]) == EXIT_OK
        assert capsys.readouterr().out.strip() == "duration: 5"

    def test_cutoff_exits_two(self, tmp_path, capsys):
        cfg = self._write(tmp_path, self._BODY, "# render-duration: 2")
        assert main([str(cfg)]) == EXIT_CUTOFF
        out = capsys.readouterr().out
        assert "duration: 5" in out and "cutoff: header 2s" in out

    def test_no_header_clean(self, tmp_path, capsys):
        cfg = self._write(tmp_path, self._BODY)
        assert main([str(cfg)]) == EXIT_OK
        assert "cutoff" not in capsys.readouterr().out

    def test_missing_file_exits_three(self, tmp_path, capsys):
        assert main([str(tmp_path / "nope.toml")]) == EXIT_TOOL_ERROR
        assert "cannot read config" in capsys.readouterr().err

    def test_malformed_toml_exits_three(self, tmp_path, capsys):
        bad = tmp_path / "bad.toml"
        bad.write_text("[display\ncols = 32\n")
        assert main([str(bad)]) == EXIT_TOOL_ERROR
        assert "malformed TOML" in capsys.readouterr().err

    def test_bad_args_exits_three(self, capsys):
        assert main([]) == EXIT_TOOL_ERROR
        assert "usage:" in capsys.readouterr().err


class TestPinnedDemoSanity:
    """Every shipped demo must produce a usable number without crashing.
    NO accuracy assertion — the precise ±20% pin is intentionally
    deleted, not relaxed."""

    def test_all_pinned_demos(self, capsys):
        tomls = sorted(DEMO_DIR.glob("*.toml"))
        assert tomls, "no pinned demos found"
        for cfg in tomls:
            code = main([str(cfg)])
            capsys.readouterr()
            assert code in (EXIT_OK, EXIT_CUTOFF), f"{cfg.name} → exit {code}"
            rec, _, _ = plan(cfg)
            assert isinstance(rec, int) and rec > 0, cfg.name
```

- [ ] **Step 4: Run the suite — expect FAIL before the rewrite is in place, PASS after**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker/.worktrees/slim-gif-plan && PYTHONPATH=tests/stubs uv run --extra dev pytest tools/gif_plan/ -q`
Expected: PASS — all ~18 tests green, no collection errors (the deleted `test_widgets.py`/etc. are gone; only `test_plan.py` runs).

- [ ] **Step 5: Lint + format the new module/tests**

Run: `uv run --with ruff ruff check --fix tools/gif_plan/ && uv run --with ruff ruff format tools/gif_plan/`
Expected: "All checks passed!" and files formatted.

- [ ] **Step 6: Commit**

```bash
git add -A tools/gif_plan/
git commit -m "gif_plan: collapse to a coarse duration + cutoff estimator

~2000 lines + 169 tests → one ~120-line plan.py + ~18 tests. Deletes
widgets/totals/flags split, JSON, the 6 advisory flags, the ±20%
dogfood + xfail list. CLI emits <=2 lines (duration + cutoff), exit
0/2/3. Per spec 2026-05-18-gif-plan-reduction-design.md.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Slim the docs page + Makefile help

**Files:**
- Modify (full rewrite): `docs/site/src/content/docs/tools/gif-plan.mdx`
- Modify: `Makefile:67`

- [ ] **Step 1: Replace `docs/site/src/content/docs/tools/gif-plan.mdx`**

````mdx
---
title: "Tool: gif-plan"
description: Get the recommended render --duration for a led-ticker demo TOML, and a guard against shipping a clipped gif.
---

import RelatedPages from "../../../components/RelatedPages.astro";

`gif-plan` reads a led-ticker demo `config.toml` and prints the
recommended `--duration` to render it with. It exists so the question
"how long should I render this?" has a one-shot answer instead of a
guess-render-recheck loop. It is deliberately a **coarse** estimate —
it models only the dominant timing terms (hold time, overflow scroll,
gif loops); precision is not the goal, not wasting a render is. The
script lives at [`tools/gif_plan/plan.py`](https://github.com/jamesawesome/led-ticker/blob/main/tools/gif_plan/plan.py)
and ships as `make plan-gif`. The math layer is the planner;
[`render-demo`](/tools/render-demo/) is the pixels layer.

## Usage

```bash
make plan-gif CONFIG=docs/site/demos-pinned/two_row-wrap.toml
```

Output is at most two lines:

```text
duration: 8
```

If the file carries a `# render-duration: N` header on its top line
and `N` is shorter than the estimated playtime, it adds a cutoff line
and exits non-zero — that is the one check that stops you shipping a
gif that clips mid-content and having to re-render:

```text
duration: 8
cutoff: header 5s < ~8s needed
```

`# render-duration:` is the header `make render-pinned-demos` reads to
pick each pinned demo's `--duration`.

## Exit codes

| Code | Meaning                                                            |
| ---- | ------------------------------------------------------------------ |
| `0`  | Clean — recommended duration printed.                              |
| `2`  | The `# render-duration:` header is shorter than the estimate.      |
| `3`  | Tool error — config not found or malformed TOML (message on stderr). |

## Out of scope

The estimate is coarse and intentionally ignores some cases:
`forever_scroll` / `infini_scroll` / `loop_count = 0` sections
(runtime-dependent → contribute 0); data-fetch widgets (`weather`,
`mlb`, crypto, `rss_feed` — depend on fetched data → contribute 0);
bigsign `pixel_mapper` (naive canvas-width); wrap floors, two-row
overlay marquee, hires width, and inter-widget transition time (not
modelled — treat the number as a lower bound for transition-heavy
playlists). The companion skill at
[`.claude/skills/making-a-gif/`](https://github.com/jamesawesome/led-ticker/tree/main/.claude/skills/making-a-gif)
wraps this plus `render-demo` and adds LED-panel colour/contrast
judgement.

<RelatedPages slugs={["tools/render-demo", "reference/cli"]} />
````

- [ ] **Step 2: Update the Makefile help text (line 67)**

Change line 67 from:

```
plan-gif:  ## Plan a demo gif (math + flags). Usage: make plan-gif CONFIG=path/to.toml
```

to:

```
plan-gif:  ## Recommended render --duration for a demo (+ cutoff guard). Usage: make plan-gif CONFIG=path/to.toml
```

(Leave line 68, `uv run python tools/gif_plan/plan.py $(CONFIG)`, unchanged — the new CLI takes exactly the config arg.)

- [ ] **Step 3: Run docs-lint**

Run: `cd docs/site && pnpm install --frozen-lockfile >/dev/null 2>&1; pnpm run format >/dev/null 2>&1; pnpm run lint 2>&1 | tail -4`
Expected: `0 errors, 0 warnings, 0 hints`.

- [ ] **Step 4: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.worktrees/slim-gif-plan
git add docs/site/src/content/docs/tools/gif-plan.mdx Makefile
git commit -m "docs: slim gif-plan page + Makefile help to match the coarse tool

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: Slim SKILL.md and collapse the examples

**Files:**
- Modify (full rewrite): `.claude/skills/making-a-gif/SKILL.md`
- Create: `.claude/skills/making-a-gif/examples/example.md`
- Delete: `.claude/skills/making-a-gif/examples/dev-mode.md`, `.claude/skills/making-a-gif/examples/docs-mode.md`

- [ ] **Step 1: Replace `.claude/skills/making-a-gif/SKILL.md`**

```markdown
---
name: making-a-gif
description: Use when a user or sub-agent wants to plan or make a demo gif of a led-ticker config. Triggers on "make a gif of...", "demo gif for X", "what render-duration should I use", "preview this widget". Gets the render --duration from tools/gif_plan, adds LED-panel colour/contrast judgement, and proposes the exact make render-demo command.
---

# Making a led-ticker Demo Gif

Two modes: **docs** (polished — source TOML committed under `docs/site/demos-pinned/`, rendered gif under `docs/site/public/demos-pinned/`) and **dev** (throwaway preview to `/tmp/`). Docs signals: "for docs", "add to demos-pinned", a `docs/site/` path, captions/commit. Dev signals: "preview", "spot check", sub-agent iterating on a feature, `/tmp/` output. If ambiguous, ask which. Announce: "Using making-a-gif skill in **<mode>** mode."

## Steps

1. **Get a TOML.** Pasted config → save to `/tmp/gif-plan-<topic>.toml`. A path → use as-is. Only an intent described → draft a minimal config, save to `/tmp/`.

2. **Get the duration:** `make plan-gif CONFIG=<path>` (from repo root). It prints `duration: <N>` and, if a `# render-duration:` header is too short, a `cutoff:` line + non-zero exit. Use `<N>` as the render `--duration`. Exit `3` = bad path/TOML (fix and re-run, not a result).

3. **Colour/contrast judgement** (the tool does NOT do this — you do). Scan colour fields (`font_color`, `top_color`, `bottom_color`, `bg_color`, `border`, separators):
   - Pure black `[0,0,0]` → renders INVISIBLE on the panel. Warn unless used intentionally as "transparent"; suggest `[10,10,10]` or a brand colour.
   - Pure white `[255,255,255]` → washes blue-white. Suggest cream `[254,255,204]`.
   - Dark-on-dark (luminance Δ < 30) → low-contrast risk; suggest previewing at `brightness = 60`.
   - Brand fallbacks: magenta `[225,48,108]`, cream `[254,255,204]`, cyan `[120,230,255]`, soft pink `[255,176,240]`, lavender `[189,169,234]`.

4. **Caption (docs mode only).** Read 2-3 existing `<DemoGif caption="...">` lines from `docs/site/src/content/docs/widgets/<widget>.mdx` and match their matter-of-fact, visual voice.

5. **Surface the recommendation:** the `--duration`, any cutoff/colour notes, and the exact command:
   - Docs: `make render-demo CONFIG=docs/site/demos-pinned/<name>.toml OUT=docs/site/public/demos-pinned/<name>.gif`; add/update the `# render-duration:` header in the source TOML.
   - Dev: `make render-demo CONFIG=/tmp/gif-plan-<topic>.toml OUT=/tmp/preview-<topic>.gif`. For a dev preview, a shorter `--duration` (one pass + a beat) is fine — verification, not a polished loop.

## Don'ts

- Don't run `make render-demo` yourself — rendering takes ~10s and the user usually iterates the config first. Suggest the command.
- Don't modify the user's config unless asked.
- Don't hand-compute durations — that's what `make plan-gif` is for; re-invoke it instead.

See `examples/example.md` for an end-to-end walkthrough.
```

- [ ] **Step 2: Create `.claude/skills/making-a-gif/examples/example.md`**

```markdown
# Example walkthrough (dev + docs)

## Dev mode

**Sub-agent:** "Iterating on `RainbowChaseBorder` speed=20 — render a quick preview."

> Using making-a-gif skill in **dev** mode.

Draft `/tmp/gif-plan-border.toml`:

```toml
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1

[[playlist.section]]
mode = "swap"
hold_time = 5.0
scroll_step_ms = 25

[[playlist.section.widget]]
type = "message"
text = "BORDER CHASE PREVIEW"
border = { style = "rainbow", speed = 20 }
```

`make plan-gif CONFIG=/tmp/gif-plan-border.toml` → `duration: 6`.
Dev preview only needs ~3s to see a few sweeps, so suggest:

```bash
make render-demo CONFIG=/tmp/gif-plan-border.toml OUT=/tmp/preview-border.gif
# shorter duration override:
uv run python tools/render_demo/render.py /tmp/gif-plan-border.toml -o /tmp/preview-border.gif --duration 3
```

No caption, no header, no commit (throwaway).

## Docs mode

**User:** "Add a demo gif for `two_row` `scroll_through`."

> Using making-a-gif skill in **docs** mode.

Draft `docs/site/demos-pinned/two_row-scroll_through.toml` (top color
`[225,48,108]` magenta + `[120,230,255]` cyan — both fine, good
contrast on black). `make plan-gif` on it → `duration: 10`. Add
`# render-duration: 10` as the file's top line. Caption, matching the
voice in `widgets/two_row.mdx`: "held magenta `NOW PLAYING` on top,
cyan song title flies fully offscreen-to-offscreen on the bottom".
Then surface:

```bash
make render-demo CONFIG=docs/site/demos-pinned/two_row-scroll_through.toml OUT=docs/site/public/demos-pinned/two_row-scroll_through.gif
```

Wire `<DemoGif>` into the docs page with the caption; commit the TOML,
the gif, and the docs change.
```

- [ ] **Step 3: Delete the two old example files**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.worktrees/slim-gif-plan
git rm .claude/skills/making-a-gif/examples/dev-mode.md \
       .claude/skills/making-a-gif/examples/docs-mode.md
```

- [ ] **Step 4: Sanity-check the skill grep-clean of dropped concepts**

Run: `grep -nE 'json|--json|flags|render_duration_suggestion|severity|footgun|\bgun\b' .claude/skills/making-a-gif/SKILL.md .claude/skills/making-a-gif/examples/example.md || echo CLEAN`
Expected: `CLEAN` (no stale JSON/flag/severity references, no gun metaphor).

- [ ] **Step 5: Commit**

```bash
git add -A .claude/skills/making-a-gif/
git commit -m "skill: slim making-a-gif SKILL.md + collapse examples

~105-line SKILL + two ~60-line examples → ~45-line SKILL + one short
example. Drops the JSON-schema block, exit-code table, flag relay.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Full repo test suite**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker/.worktrees/slim-gif-plan && PYTHONPATH=tests/stubs uv run --extra dev pytest -q 2>&1 | tail -4`
Expected: all pass, 0 failures. The gif_plan portion is now ~18 tests (no `test_widgets/totals/flags/dogfood`); the engine suite is unaffected (this work touches only `tools/gif_plan/`, docs, and the skill).

- [ ] **Step 2: `make plan-gif` smoke on representative pinned demos**

Run:
```bash
for f in two_row-wrap gif-silent message-brand-color two_row-scroll_through gif-two_row-scroll_through; do
  echo -n "$f: "; make plan-gif CONFIG=docs/site/demos-pinned/$f.toml 2>&1 | tr '\n' ' '; echo
done
```
Expected: each prints `duration: <int>` (some also a `cutoff:` line). No tracebacks, no `error:`.

- [ ] **Step 3: Lint clean**

Run: `uv run --with ruff ruff check tools/gif_plan/ && uv run --with ruff ruff format --check tools/gif_plan/`
Expected: "All checks passed!" + "files already formatted".

- [ ] **Step 4: Push the branch and open the PR**

```bash
git push -u origin slim-gif-plan
gh pr create --base main --head slim-gif-plan \
  --title "slim gif_plan to the token-saving kernel" \
  --body "Implements docs/superpowers/specs/2026-05-18-gif-plan-reduction-design.md. tools/gif_plan ~2000 lines+169 tests → ~120-line plan.py + ~18 tests; CLI emits <=2 lines (duration + cutoff), exit 0/2/3; SKILL.md/examples + gif-plan.mdx slimmed; 6 advisory flags + JSON + dogfood pin removed. Full suite green.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```
Expected: PR URL printed. Do NOT merge — wait for user review.

---

### Task 5: In-flight cleanup (CONFIRM with the user before running)

**Files:** none (operational — closes a PR, removes branches/worktrees)

This is destructive and outward-facing. Present it and get an explicit go-ahead in the same turn before running anything.

- [ ] **Step 1: Confirm with the user**

Ask: "Slim PR is open. OK to close PR #73 (the leaf spike — its premise is now deleted) and remove the two spike worktrees/branches (`spike/gif-plan-engine-coupling`, `spike/measured-plan-harness`)?"

- [ ] **Step 2: On explicit yes, close #73 and clean up**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
gh pr close 73 --comment "Superseded: gif_plan is being reduced to a coarse duration+cutoff kernel (spec 2026-05-18-gif-plan-reduction-design.md), so the shared-mirror premise of this spike no longer applies."
git worktree remove .worktrees/spike-gif-plan-coupling --force
git worktree remove .worktrees/spike-measured-plan --force
git branch -D spike/gif-plan-engine-coupling spike/measured-plan-harness
git push origin --delete spike/gif-plan-engine-coupling
git fetch --prune origin
```
(The `spike/measured-plan-harness` branch is local-only — no remote delete needed. `main` is clean; nothing to revert.)

- [ ] **Step 3: Confirm clean**

Run: `git worktree list && gh pr view 73 --json state --jq .state`
Expected: only the primary worktree + `.worktrees/slim-gif-plan` remain; PR #73 state `CLOSED`.

---

## Self-Review

**Spec coverage:** estimator/CLI contract (Task 1 plan.py + tests) ✓; delete/keep/new file list (Task 1 Steps 1-3) ✓; docs slim (Task 2) ✓; SKILL.md + examples collapse (Task 3) ✓; CI/packaging unchanged — no task needed (verified: `pyproject` testpaths still `tools/gif_plan`, PR #71 job still gated, conftest kept) ✓; in-flight cleanup (Task 5, gated) ✓; success criteria checked in Task 4 ✓.

**Placeholder scan:** no TBD/TODO; every code/content step contains the full file body or the exact line change; commands have expected output.

**Type/name consistency:** `widget_ms`, `total_ms`, `recommended_s`, `plan`, `main`, `_canvas_w`, `_content_w`, `_gif_loop_ms`, `PlanError`, `EXIT_OK/CUTOFF/TOOL_ERROR` are used identically in `plan.py` and `test_plan.py`. `conftest.py` (kept) provides the `tools.gif_plan` import path the tests rely on. `make plan-gif` passes exactly one arg, matching `main()`'s `len(args) != 1` contract.
