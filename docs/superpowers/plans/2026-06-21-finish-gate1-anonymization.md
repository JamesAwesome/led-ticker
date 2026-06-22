# Finish Gate #1 — Anonymization Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three Moon-Bunny leak classes #256's literal-string guard couldn't catch (brand *voice*, stale GIF *pixels*, unattributed `pride.gif`) plus the `@firebird` handle gap, and harden the guard so each can't recur.

**Architecture:** Fix the render-tool font bug first (keystone — unblocks correct re-renders); sweep the rabbit voice → generic filler; fix the handle; replace `pride.gif` with a CC0-generated rainbow; re-render every affected GIF; extend the completeness guard with phrase-precise voice needles.

**Tech Stack:** Pillow (asset gen), TOML configs, Astro/Starlight docs, pytest, the `render_demo` GIF toolchain.

## Global Constraints

- Worktree `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/finish-gate1`, branch `feat/finish-gate1-anon` (base `origin/main` @ f5266982; spec @ 67178b24). **Run `git branch --show-current` first; abort if `main`.**
- `make dev` once before first commit. Tests: `PYTHONPATH=tests/stubs uv run pytest`. Pillow is in the venv.
- Lint/format: `uv run --extra dev ruff check src/ tests/ tools/` + `ruff format`. Types: `uv run --extra dev pyright src/`. Docs: `make docs-format && make docs-build && make docs-lint` (NEVER pipe `docs-lint` to `tail`).
- **Voice needles must be phrase-precise** (`"May the Rabbit"`, `"bunny best"`, `"be your bunny"`) — NEVER bare `bunny`/`rabbit` (the `:bunny:` emoji slug, `bunny-low/hi.png`, and the "Bunny silhouette" emoji-catalog row legitimately use "bunny").
- **`@firebird` → `@firebird.demo` must NOT corrupt `@firebirdyoga.demo`** — match `@firebird` only when NOT followed by `yoga` (`@firebird(?!yoga)`).
- The render-tool fix is the keystone: it MUST let the custom-font demos re-render (Task 1 before any re-render).
- No release-history framing in rewritten prose (DOCS-STYLE principle 17).
- **NON-GOALS — do NOT touch:** `config/assets/heart-tunnel-opaque.jpg` + `moonscape-opaque.jpg` provenance; the `show_pikachu` pokeball-plugin field; git-history scrub.
- Commit trailer on every commit:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh`

---

### Task 1: Render-tool font-bug fix + tripwire (keystone)

**Files:**
- Modify: `tools/render_demo/render.py` (the suppress/restore block, ~lines 83–115)
- Test: `tools/render_demo/test_render.py` (add a regression test)

**Root cause:** `render.py` patches `app_mod._configure_user_font_dir` to suppress the app's font-dir re-anchor, but `src/led_ticker/app/run.py:32` did `from … import _configure_user_font_dir` (a module-local binding), so `run.py:436`'s call hits the **unpatched** original → re-anchors the user font dir to the temp-dir config copy (no `fonts/`) → the demo's custom font is lost.

- [ ] **Step 1: Reproduce — confirm the local-binding miss**

Read `src/led_ticker/app/run.py` lines 30–34 (the `from … import _configure_user_font_dir`) and line ~436 (the call). Confirm the call uses the bare name (run.py's namespace), not `app_mod._configure_user_font_dir`. This is why patching `app_mod` alone misses it.

- [ ] **Step 2: Apply the fix — also patch run.py's binding**

In `tools/render_demo/render.py`, in the `if original_cfg_path is not None:` suppress block and its `finally:` restore, add the `run` module's binding alongside the existing `app_mod` handling. The block currently reads:

```python
    from led_ticker import app as app_mod
    from led_ticker import frame as frame_mod

    original_rgbmatrix = frame_mod.RGBMatrix
    original_configure = app_mod._configure_user_font_dir
```
Add after `original_configure = …`:
```python
    from led_ticker.app import run as run_mod

    original_run_configure = run_mod._configure_user_font_dir
```
In the suppress block (after `original_configure(original_cfg_path)` / `app_mod._configure_user_font_dir = lambda _path: None`), add:
```python
        run_mod._configure_user_font_dir = lambda _path: None  # type: ignore[assignment]
```
In the `finally:`, after `app_mod._configure_user_font_dir = original_configure`, add:
```python
        run_mod._configure_user_font_dir = original_run_configure
```
(Keep the existing `app_mod` patch — both bindings are restored.)

- [ ] **Step 3: Write the tripwire test**

Add to `tools/render_demo/test_render.py` (mirror the existing tests' import style + skip-if-asset-absent pattern). The test renders a config whose widget uses a custom font in `<config_dir>/fonts/` and asserts glyphs actually paint (the font dir was honored). Use the bundled Atkinson font if present, else skip:

```python
import shutil
from pathlib import Path

import pytest


def test_render_honors_user_font_dir(tmp_path):
    """Regression: the render tool must keep the demo's <config_dir>/fonts/ active.

    Before the run_mod._configure_user_font_dir fix, run.py's local binding
    re-anchored the font dir to the temp config copy (no fonts/), so a custom
    font silently fell back / rendered blank. This renders a hires-font widget
    and asserts lit pixels.
    """
    from tools.render_demo import render  # adjust to the module's import path

    font_src = Path("docs/site/demos-long/fonts/AtkinsonHyperlegible-Bold.ttf")
    if not font_src.exists():
        pytest.skip("AtkinsonHyperlegible-Bold.ttf not present (gitignored licensed font)")

    cfgdir = tmp_path / "cfg"
    (cfgdir / "fonts").mkdir(parents=True)
    shutil.copy(font_src, cfgdir / "fonts" / "AtkinsonHyperlegible-Bold.ttf")
    cfg = cfgdir / "c.toml"
    cfg.write_text(
        'default_scale = 1\n'
        '[[playlist.section]]\nmode = "swap"\n'
        '[[playlist.section.widget]]\n'
        'type = "message"\ntext = "AB"\n'
        'font = "AtkinsonHyperlegible-Bold"\nfont_size = 16\n'
    )
    frames = render.render_frames(cfg, duration_s=0.4, original_cfg_path=cfg)  # adjust to the real entrypoint
    lit = any(any(px != (0, 0, 0) for px in frame) for frame in frames)
    assert lit, "custom-font widget rendered blank — user font dir not honored"
```
Inspect `tools/render_demo/render.py` + the existing tests for the EXACT public entrypoint (e.g. `render_frames` / `render` / how `test_renderer_multiframe.py` drives a render) and the frame representation; adapt the call + the `lit` check to match (the goal: assert non-blank output for a custom-font widget). If the harness can't easily return frames, assert against the output GIF's pixels instead.

- [ ] **Step 4: Run the tripwire**

Run: `PYTHONPATH=tests/stubs uv run pytest tools/render_demo/test_render.py::test_render_honors_user_font_dir -v`
Expected: PASS (or SKIP if the font asset is absent). Temporarily revert the Step-2 fix and confirm it FAILS (blank) when the font is present, then restore the fix.

- [ ] **Step 5: ruff + commit**

```bash
uv run --extra dev ruff check tools/ && uv run --extra dev ruff format tools/
git add tools/render_demo/render.py tools/render_demo/test_render.py
git commit -m "fix(render-demo): patch run.py's font-dir binding so custom-font demos render + tripwire

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 2: Brand-voice copy sweep

**Files (configs):** `config/config.example.toml`, `config/config.bigsign.example.toml`, `config/config.forever_scroll.toml`, `config/config.infini_scroll.toml`, `config/config.image_test.example.toml`, `config/config.rainbow_border_test.example.toml`, `config/config.bg_color_test.example.toml`, `config/config.bands_border_test.example.toml`
**Files (docs/skill):** `.claude/skills/creating-a-config/references/snippets.md`, `docs/site/src/content/docs/hardware/bigsign.mdx`, `docs/site/src/content/docs/hardware/smallsign.mdx`, `docs/site/demos/widget-image.toml`

- [ ] **Step 1: Ticker filler — the same pair, all 7 `#DevOps News` spots**

Replace EVERY occurrence of these two exact strings:
- `"May the Rabbit always be with you!"` → `"May the uptime be with you!"`
- `"Always be your bunny best!"` → `"Always be shipping!"`
across: `config.example.toml` (87, 91), `config.bigsign.example.toml` (114, 118), `config.forever_scroll.toml` (45, 49), `config.infini_scroll.toml` (37, 41), `snippets.md` (614, 618), `hardware/bigsign.mdx` (256, 260), `hardware/smallsign.mdx` (170, 174). (Line numbers are guides — match the exact strings.)

- [ ] **Step 2: On-panel / comment `bunny` → `phoenix` (accurate to the rendered asset)**

- `config.image_test.example.toml`: `text = "BIG BUNNY"` → `text = "BIG PHOENIX"`; comment `bunny pinned to the right` → `phoenix pinned to the right`; comment `bunny image` → `phoenix image` (lines ~24, 296, 297).
- `config.rainbow_border_test.example.toml`: `text = "TEXT WALKS BEHIND THE BUNNY"` → `"TEXT WALKS BEHIND THE PHOENIX"`; `text = "DOUBLE RAINBOW THROUGH THE BUNNY"` → `"DOUBLE RAINBOW THROUGH THE PHOENIX"`; comments at ~231, ~590 `bunny` → `phoenix` (lines ~165, 231, 246, 590).
- `config.bg_color_test.example.toml`: comments `Bunny image` → `phoenix image`, `Bunny silhouette` → `phoenix silhouette` (lines ~90, 107).
- `config.bands_border_test.example.toml`: comment `the bunny holds` → `the phoenix holds` (line ~333).
- `docs/site/demos/widget-image.toml`: `text = "Bunny says hi"` → `text = "Phoenix says hi"` (line ~26 — still wider than `"Hello!"`, so the line-6 marquee-pass rationale holds); update the line-6 comment to name the new text (`"Phoenix says hi" is wider than "Hello!" …`).

- [ ] **Step 3: Verify the sweep is clean**

Run: `git grep -in "bunny\|rabbit" -- config docs .claude ':!docs/superpowers'`
Expected: ONLY the legitimate `:bunny:` emoji slug + `bunny-low.png`/`bunny-hi.png` rows + the "Bunny silhouette" emoji-catalog description in `docs/content-source/emoji.md` / `docs/site/.../emoji` — NO ticker filler, NO on-panel/comment "bunny" in the config/test files above. (If a stray remains, fix it.)

- [ ] **Step 4: Parse-check + docs build + commit**

```bash
PYTHONPATH=tests/stubs uv run python -c "import tomllib,glob; [tomllib.load(open(f,'rb')) for f in glob.glob('config/*.toml')+glob.glob('docs/site/demos*/**/*.toml',recursive=True)+glob.glob('docs/site/demos/*.toml')]; print('parse ok')"
make docs-format && make docs-build && make docs-lint
git add config docs .claude
git commit -m "docs(anon): sweep retired Moon-Bunny brand voice -> generic filler / phoenix

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 3: `@firebird` → `@firebird.demo`

**Files:** every config/doc with a bare `@firebird` short handle (~25 files: `config/*.toml`, `docs/site/demos-*/*.toml`, `docs/site/demos/*.toml`, `docs/site/src/content/docs/**/*.mdx`) + `docs/DOCS-STYLE.md` (the §6 rule).

- [ ] **Step 1: Find the bare-handle set**

Run: `git grep -nE "@firebird([^y]|$)" -- config docs ':!docs/superpowers'` to list every bare `@firebird` (the `[^y]`/`$` guard excludes `@firebirdyoga`). Record the count of `@firebirdyoga.demo` first: `git grep -oc "@firebirdyoga.demo" -- config docs | wc -l` (to confirm it's unchanged after).

- [ ] **Step 2: Replace bare `@firebird` → `@firebird.demo` (NOT `@firebirdyoga`)**

For each file, replace `@firebird` with `@firebird.demo` ONLY where not followed by `yoga`. Per-file, e.g.:
```bash
perl -i -pe 's/\@firebird(?!yoga)\b/\@firebird.demo/g' <file>
```
(Verify the negative-lookahead leaves `@firebirdyoga.demo` intact. Apply to the files from Step 1.)

- [ ] **Step 3: Update the §6 rule + captions**

In `docs/DOCS-STYLE.md`, the §6 contact table row `| Instagram (short, ≤12 chars for narrow panels) | \`@firebird\` |` → `| Instagram (short, narrow panels) | \`@firebird.demo\` |` (drop the now-wrong "≤12 chars"; 14 chars). Update any other "≤12 chars"/"@firebird" caption (e.g. in `tutorial/03-multi-widget.mdx` the caption explaining the short handle) to `@firebird.demo`.

- [ ] **Step 4: Verify precision + docs**

```bash
git grep -nE "@firebird([^y.]|$)" -- config docs ':!docs/superpowers'   # bare @firebird (no .demo, not yoga) -> expect EMPTY
git grep -c "@firebirdyoga.demo" -- config docs    # unchanged vs Step 1
make docs-format && make docs-build && make docs-lint
```
Expected: no bare `@firebird` without `.demo`; `@firebirdyoga.demo` count unchanged; docs clean.

- [ ] **Step 5: Commit**

```bash
git add config docs
git commit -m "docs(anon): @firebird -> @firebird.demo (carry the .demo fictional marker; §6 rule)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 4: CC0 rainbow `pride.gif`

**Files:**
- Create: `tools/derive_pride_assets.py`
- Modify: `Makefile` (`derive-pride` target), `config/assets/ATTRIBUTION.md`
- Create (generated, committed): `config/assets/pride.gif`, `config/assets/pride_trans.gif` (overwrite the third-party ones)
- Test: `tests/test_phoenix_assets.py` (add pride asserts) or `tests/test_pride_assets.py`

**Note:** the retired `pride_trans.gif` is mode P with NO transparency — both assets are just opaque flags used `fit = "stretch"`. So the replacement is two OPAQUE animated rainbow flags; no alpha needed. Match the retired dims so the demos render identically: `pride.gif` 1000×700, `pride_trans.gif` 498×280.

- [ ] **Step 1: Write `tools/derive_pride_assets.py`**

```python
"""Generate the CC0 6-stripe rainbow sample assets (replaces third-party pride art).

Project-original: six solid horizontal color bands, animated by scrolling the
rainbow vertically (ImageChops.offset wraps) so the gif-widget demo moves and
loops seamlessly. Reproducible. Run: `make derive-pride`.
"""

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "config" / "assets"
# Classic 6-stripe rainbow (generic public-domain arrangement).
BANDS = [
    (228, 3, 3),    # red
    (255, 140, 0),  # orange
    (255, 237, 0),  # yellow
    (0, 128, 38),   # green
    (0, 77, 255),   # blue
    (117, 7, 135),  # violet
]
N_FRAMES = 12


def _base(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    band_h = h / len(BANDS)
    for i, color in enumerate(BANDS):
        draw.rectangle([0, round(i * band_h), w, round((i + 1) * band_h)], fill=color)
    return img


def _frames(w: int, h: int) -> list[Image.Image]:
    base = _base(w, h)
    # Scroll the whole flag vertically by a full height over N frames (wraps to
    # the start at frame N -> seamless loop).
    return [ImageChops.offset(base, 0, round(i * h / N_FRAMES)) for i in range(N_FRAMES)]


def main() -> None:
    for name, (w, h) in {"pride.gif": (1000, 700), "pride_trans.gif": (498, 280)}.items():
        frames = _frames(w, h)
        frames[0].save(
            OUT / name, save_all=True, append_images=frames[1:], duration=80, loop=0
        )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add the Make target**

In `Makefile`, add `derive-pride` to `.PHONY` and (mirroring `derive-phoenix`):
```makefile
derive-pride:  ## Re-generate config/assets/pride.* (CC0 rainbow flag)
	$(UVRUN) python tools/derive_pride_assets.py
```

- [ ] **Step 3: Generate the assets**

Run: `make derive-pride` (or `PYTHONPATH=tests/stubs uv run python tools/derive_pride_assets.py`). Confirm `config/assets/pride.gif` (1000×700) + `pride_trans.gif` (498×280) regenerate.

- [ ] **Step 4: ATTRIBUTION + reconcile the policy wording**

In `config/assets/ATTRIBUTION.md`, add an entry: the pride assets are **project-generated CC0** by `tools/derive_pride_assets.py` (a 6-stripe rainbow, band RGBs as above) — no third-party source. Ensure the file's "real-brand / customer media is not committed" wording is consistent (this resolves the prior provenance gap — pride is now generated CC0, fully covered).

- [ ] **Step 5: Test the generated assets**

Add to `tests/test_phoenix_assets.py` (or a new `tests/test_pride_assets.py`):
```python
def test_pride_assets_exist_and_animated():
    from pathlib import Path

    from PIL import Image

    assets = Path(__file__).resolve().parent.parent / "config" / "assets"
    for name, size in {"pride.gif": (1000, 700), "pride_trans.gif": (498, 280)}.items():
        im = Image.open(assets / name)
        assert im.format == "GIF", f"{name}: {im.format}"
        assert im.size == size, f"{name}: {im.size} != {size}"
        assert getattr(im, "n_frames", 1) > 1, f"{name}: expected animation"
```

- [ ] **Step 6: Run test + commit**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_phoenix_assets.py -q   # (or test_pride_assets.py)
uv run --extra dev ruff check tools/ tests/ && uv run --extra dev ruff format tools/ tests/
git add tools/derive_pride_assets.py Makefile config/assets/ATTRIBUTION.md config/assets/pride.gif config/assets/pride_trans.gif tests/
git commit -m "feat(assets): replace third-party pride GIFs with a CC0-generated rainbow + derive script

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 5: Re-render every affected GIF

**Files:** `docs/site/public/demos-long/*.gif`, `docs/site/public/demos-pinned/*.gif`, `docs/site/public/demos/*.gif` (only the affected ones).

With Task 1's font fix in place, the stale font GIFs can now render correctly.

- [ ] **Step 1: Identify the set**

The GIFs to re-render are those whose source config changed (voice/handle/pride) OR that were stale-moonbunny:
- Stale moonbunny (font-blocked): `tutorial-04a-font`, `tutorial-04c-image-with-text`, `tutorial-05a-transitions`. Confirm with `git log -1 --format=%h -- docs/site/public/demos-long/<name>.gif` (a pre-firebird hash = stale).
- Voice/handle/pride demos: `docs/site/demos/widget-image.toml` → `widget-image.gif`; the handle demos `tutorial-03c-two_row-basic`, `tutorial-03d-two_row-hires` (+ any other showing `@firebird`); the pride demos (the `gif_test`/`gif_text` pride sections aren't committed demo GIFs — skip if no committed GIF references them). Run `git grep -l "@firebird\b\|phoenix\|pride" docs/site/demos-*/*.toml docs/site/demos/*.toml` to find configs and map to their committed GIFs (`grep -rl "<name>.gif" docs/site/src/content/docs`).

- [ ] **Step 2: Re-render each**

For each: `make render-demo CONFIG=docs/site/demos-long/<name>.toml OUT=docs/site/public/demos-long/<name>.gif` (adjust dir). Then VERIFY each:
```python
from PIL import Image
im = Image.open("docs/site/public/demos-long/<name>.gif")
frames = []
for i in range(getattr(im, "n_frames", 1)):
    im.seek(i); frames.append(im.convert("RGB").tobytes())
assert len(set(frames)) > 2, "not animated"
```
AND spot-check (open a frame, or trust the now-firebird config) that NO moonbunny/bunny/rabbit text appears. If a GIF still can't render correctly, DIAGNOSE + flag in the report (do NOT commit a known-broken/leaky GIF silently).

- [ ] **Step 3: Commit**

```bash
git add docs/site/public
git commit -m "docs(demos): re-render the stale moonbunny + voice/handle/pride demos (font fix in place)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 6: Guard — brand-voice needles

**Files:** `tests/test_no_real_brand.py`

- [ ] **Step 1: Add the voice-phrase guard**

Add a test mirroring the existing guards (git grep + `assert res.returncode in (0, 1)` + allow-list `docs/superpowers/` and this file):
```python
def test_no_retired_brand_voice_outside_archival():
    """Guard the retired studio's rabbit brand VOICE (phrases, not bare words).

    Needles are PHRASES, never bare 'bunny'/'rabbit', because the ':bunny:'
    emoji slug, bunny-low/hi.png, and the 'Bunny silhouette' emoji-catalog row
    legitimately contain 'bunny'. These phrases are the retired tagline voice.
    """
    import subprocess
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    needles = ["May the Rabbit", "bunny best", "be your bunny"]
    offenders = []
    for needle in needles:
        res = subprocess.run(
            ["git", "grep", "-il", needle, "--",
             ":!docs/superpowers", ":!tests/test_no_real_brand.py"],
            cwd=repo, capture_output=True, text=True,
        )
        assert res.returncode in (0, 1), f"git grep failed (rc={res.returncode}): {res.stderr}"
        offenders += [f"{needle}: {p}" for p in res.stdout.splitlines() if p]
    assert not offenders, "retired brand voice still present:\n" + "\n".join(sorted(set(offenders)))
```

- [ ] **Step 2: Run — expect GREEN (Task 2 removed the voice)**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_no_real_brand.py -q`
Expected: PASS (all guards: name, content, filename, palette, asset, voice). If the voice guard FAILS, it lists the offenders — fix them (a Task-2 miss), re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/test_no_real_brand.py
git commit -m "test: guard the retired Moon-Bunny brand voice (phrase-precise needles)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 7: Final verification

**Files:** none (verification only; fix-and-note if a gate fails).

- [ ] **Step 1: Guards + voice grep**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_no_real_brand.py tests/test_phoenix_assets.py -q
git grep -in "bunny\|rabbit" -- config docs .claude ':!docs/superpowers'   # only :bunny: emoji / bunny-low,hi.png / "Bunny silhouette" rows
git grep -nE "@firebird([^y.]|$)" -- config docs ':!docs/superpowers'        # empty (no bare @firebird)
```

- [ ] **Step 2: Asset paths resolve + pride animated**

```bash
PYTHONPATH=tests/stubs uv run python - <<'PY'
import re, pathlib, glob
existing={p.name for p in pathlib.Path("config/assets").iterdir()}
pat=re.compile(r'assets/([A-Za-z0-9_.\-]+\.(?:gif|png|webp|jpg|jpeg))')
bad=[(m.group(1),f) for f in glob.glob("config/*.toml")+glob.glob("docs/site/demos*/**/*.toml",recursive=True)+glob.glob("docs/site/demos/*.toml") for m in pat.finditer(pathlib.Path(f).read_text()) if m.group(1) not in existing]
print("BROKEN:",bad or "none ✓")
PY
```

- [ ] **Step 3: Full suite + lint + types + docs**

```bash
PYTHONPATH=tests/stubs uv run pytest -q
uv run --extra dev ruff check src/ tests/ tools/ && uv run --extra dev ruff format --check src/ tests/ tools/
uv run --extra dev pyright src/
make docs-format && make docs-build && make docs-lint
```
Expected: all green; the render tripwire passes; the re-rendered stale font GIFs show no moonbunny.

- [ ] **Step 4: Push + open PR (do NOT merge — pause for go-ahead)**

```bash
git push -u origin feat/finish-gate1-anon
```
Open the PR against `main`; ensure CI is green before requesting merge.

## Self-review notes / gotchas

- Task 1 is the keystone — without the font fix, Task 5's stale font GIFs re-render blank/wrong. Do it first.
- Voice needles are phrases (`"May the Rabbit"` / `"bunny best"` / `"be your bunny"`) — bare `bunny`/`rabbit` would false-positive on the `:bunny:` emoji + `bunny-low/hi.png` + "Bunny silhouette". The Task-7 grep tolerates exactly those legitimate rows.
- The handle replace MUST use the `(?!yoga)` lookahead — verify `@firebirdyoga.demo`'s count is unchanged.
- `pride_trans.gif` has NO transparency (opaque flag, `fit="stretch"`); the CC0 replacement is two opaque rainbow flags at the retired dims (1000×700, 498×280) — demos render identically, no repoint.
- Adapt Task 1's tripwire to `render_demo`'s actual entrypoint/frame representation (read the existing `test_renderer_multiframe.py`) — the binding fix is the load-bearing part; the test asserts non-blank custom-font output.
- NON-GOALS: do not touch `heart-tunnel/moonscape.jpg`, `show_pikachu`, or git history.
