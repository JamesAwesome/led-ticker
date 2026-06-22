# Firebird Shippable-Asset Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every non-shippable sample-media asset (Pikachu / Moon Bunny logo / kpop footage) with one CC0 "Firebird phoenix" asset family derived from a vendored CC0 source, so the public repo carries no encumbered media.

**Architecture:** Vendor the CC0 source + a committed Pillow derive-script that produces 5 phoenix formats; repoint ~40 asset references to them; `git rm` the 7 old files; rewrite the asset prose; fix the stale asset policy; and extend the completeness guard so the old asset names can't return.

**Tech Stack:** Pillow (asset derivation), TOML configs, Astro/Starlight docs, pytest, the `render-demo` GIF toolchain.

## Global Constraints

- Worktree `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/asset-sweep`, branch `feat/firebird-asset-sweep` (base `origin/main` @ b955c259). **Run `git branch --show-current` first; abort if `main`.**
- `make dev` once before first commit. Tests: `PYTHONPATH=tests/stubs uv run pytest`. Pillow 12.1.1 is in the venv.
- Lint/format: `uv run --extra dev ruff check src/ tests/ tools/` + `ruff format`. Types: `uv run --extra dev pyright src/`. Docs: `make docs-build` + `make docs-lint` (NEVER pipe `docs-lint` to `tail` — run `make docs-format` then re-lint).
- **Pixel-art crispness: nearest-neighbor scaling ONLY** (`Image.NEAREST`). Derived assets are **220×220** (the old `pika_wave` footprint; 11× the 20×20 source).
- The CC0 source is staged at `.superpowers/asset-src/phoenix-cc0-no-bg.gif` (20×20, 24-frame, mode P, transparent) + `phoenix-cc0-spritesheet.png`. CC0 / public-domain (OpenGameArt "pixel-phoenix" by *zonked*).
- No release-history framing in rewritten prose (DOCS-STYLE principle 17). No reference to a removed asset file may remain.
- `pride.gif` / `pride_trans.gif` are generic — LEAVE them.
- Commit trailer on every commit:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh`

### Repoint map (used by Task 2)

| old | → new |
|-----|-------|
| `assets/pika_wave.gif` | `assets/phoenix.gif` |
| `assets/pika_wave_transparent.gif` | `assets/phoenix_transparent.gif` |
| `assets/moon-transparent.png` | `assets/phoenix_transparent.png` |
| `assets/bunny-transparent.png` | `assets/phoenix_transparent.png` |
| `assets/bunny-nontransparent.png` | `assets/phoenix.png` |
| `assets/kpop-dance.webp` | `assets/phoenix.webp` |

(`moon_bunny_transparent.gif` is an ORPHAN — referenced by no config; just `git rm` it in Task 3.)

---

### Task 1: Vendor the CC0 source + derive script + 5 phoenix assets + ATTRIBUTION

**Files:**
- Create: `config/assets/_src/phoenix-cc0-no-bg.gif` (vendored source), `config/assets/ATTRIBUTION.md`, `tools/derive_phoenix_assets.py`
- Create (generated, committed): `config/assets/phoenix.gif`, `phoenix_transparent.gif`, `phoenix.png`, `phoenix_transparent.png`, `phoenix.webp`
- Modify: `Makefile` (add `derive-phoenix` target)
- Test: `tests/test_phoenix_assets.py`

- [ ] **Step 1: Vendor the source**

```bash
mkdir -p config/assets/_src
git mv .superpowers/asset-src/phoenix-cc0-no-bg.gif config/assets/_src/phoenix-cc0-no-bg.gif 2>/dev/null || cp .superpowers/asset-src/phoenix-cc0-no-bg.gif config/assets/_src/phoenix-cc0-no-bg.gif
```
(The staged file is in git-ignored scratch; `cp` then `git add` it. Optionally also vendor the spritesheet, but the animated gif is the frame source.)

- [ ] **Step 2: Write `config/assets/ATTRIBUTION.md`**

```markdown
# Sample-media attribution

The repo ships one sample-media asset family (the Firebird phoenix), used by the example
configs and docs demos. All formats are derived from a single CC0 source by
`tools/derive_phoenix_assets.py`.

- **Source:** "pixel-phoenix" by **zonked** — https://opengameart.org/content/pixel-phoenix
- **License:** CC0 1.0 (public domain) — https://creativecommons.org/publicdomain/zero/1.0/
  No attribution is required; this record is kept for provenance.
- **Vendored source:** `config/assets/_src/phoenix-cc0-no-bg.gif` (20×20, animated, transparent).
- **Derived:** `phoenix.gif`, `phoenix_transparent.gif`, `phoenix.png`, `phoenix_transparent.png`,
  `phoenix.webp` (220×220, nearest-neighbor upscale).

Real-brand or third-party media is never committed — it is gitignored per-deployment.
```

- [ ] **Step 3: Write `tools/derive_phoenix_assets.py`**

```python
"""Derive the Firebird phoenix sample assets from the vendored CC0 source.

Source: OpenGameArt "pixel-phoenix" by zonked (CC0). One 20x20 animated transparent
GIF -> the 5 formats the demos need, nearest-neighbor upscaled to 220x220 (crisp pixel
art, matching the retired pika_wave.gif footprint). Reproducible from a clean checkout.
Run: `make derive-phoenix` (or `python tools/derive_phoenix_assets.py`).
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "config" / "assets" / "_src" / "phoenix-cc0-no-bg.gif"
OUT = ROOT / "config" / "assets"
SIZE = (220, 220)  # 11x the 20x20 source, nearest-neighbor


def _rgba_frames(im: Image.Image) -> list[Image.Image]:
    frames = []
    for i in range(getattr(im, "n_frames", 1)):
        im.seek(i)
        frames.append(im.convert("RGBA").resize(SIZE, Image.NEAREST))
    return frames


def _durations(im: Image.Image, n: int) -> list[int]:
    out = []
    for i in range(n):
        im.seek(i)
        out.append(int(im.info.get("duration", 80)))
    return out


def main() -> None:
    src = Image.open(SRC)
    frames = _rgba_frames(src)
    durs = _durations(Image.open(SRC), len(frames))

    # transparent animated GIF (real 1-bit alpha): paste each RGBA frame onto a
    # transparent P canvas; transparency index 0.
    def to_p_transparent(rgba: Image.Image) -> Image.Image:
        p = rgba.convert("RGBA")
        # quantize visible pixels; reserve index 0 for transparency
        alpha = p.getchannel("A")
        pal = p.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
        pal.paste(255, mask=alpha.point(lambda a: 255 if a < 128 else 0))
        pal.info["transparency"] = 255
        return pal

    tframes = [to_p_transparent(f) for f in frames]
    tframes[0].save(
        OUT / "phoenix_transparent.gif", save_all=True, append_images=tframes[1:],
        duration=durs, loop=0, transparency=255, disposal=2, optimize=False,
    )

    # opaque animated GIF (composited on black) — matches the old pika_wave.gif path
    black = [Image.new("RGBA", SIZE, (0, 0, 0, 255)) for _ in frames]
    oframes = [Image.alpha_composite(b, f).convert("RGB") for b, f in zip(black, frames)]
    oframes[0].save(
        OUT / "phoenix.gif", save_all=True, append_images=oframes[1:],
        duration=durs, loop=0, optimize=False,
    )

    # animated WebP (RGBA)
    frames[0].save(
        OUT / "phoenix.webp", save_all=True, append_images=frames[1:],
        duration=durs, loop=0, lossless=True,
    )

    # still PNGs from a representative frame (mid-animation reads best)
    mid = frames[len(frames) // 2]
    mid.save(OUT / "phoenix_transparent.png")
    Image.alpha_composite(Image.new("RGBA", SIZE, (0, 0, 0, 255)), mid).convert("RGB").save(
        OUT / "phoenix.png"
    )


if __name__ == "__main__":
    main()
```

> The animated-GIF-with-transparency path is the fiddly bit. After running, OPEN each output and verify: `phoenix_transparent.gif` has `n_frames == 24`, `(220,220)`, mode `P`, `info["transparency"]` set, and visible transparent regions; `phoenix.gif` opaque RGB 24 frames; `phoenix.webp` 24 frames RGBA; the two PNGs `(220,220)` (one RGBA, one RGB). If Pillow's transparency handling produces artifacts, iterate on `to_p_transparent` (the goal: transparent where source alpha<128, crisp pixels elsewhere). The visual proof is Task 7's re-rendered demos.

- [ ] **Step 4: Add the Make target**

In `Makefile`, add `derive-phoenix` to `.PHONY` and a target:
```makefile
derive-phoenix:  ## Re-derive config/assets/phoenix.* from the vendored CC0 source
	$(UVRUN) python tools/derive_phoenix_assets.py
```
(Match the file's existing `$(UVRUN)`/venv-invocation convention — check how `render-emoji-previews` invokes Python and mirror it.)

- [ ] **Step 5: Generate the assets**

Run: `make derive-phoenix` (or `PYTHONPATH=tests/stubs uv run python tools/derive_phoenix_assets.py`). Confirm the 5 files appear in `config/assets/`.

- [ ] **Step 6: Write the asset test (verifies the 5 outputs)**

`tests/test_phoenix_assets.py`:
```python
from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "config" / "assets"


def test_five_phoenix_assets_exist_and_are_correct():
    expected = {
        "phoenix.gif": ("GIF", "RGB_or_P", True),
        "phoenix_transparent.gif": ("GIF", "P", True),
        "phoenix.png": ("PNG", "RGB", False),
        "phoenix_transparent.png": ("PNG", "RGBA", False),
        "phoenix.webp": ("WEBP", "RGBA", True),
    }
    for name, (fmt, _mode, animated) in expected.items():
        p = ASSETS / name
        assert p.exists(), f"missing derived asset {name}"
        im = Image.open(p)
        assert im.format == fmt, f"{name}: format {im.format} != {fmt}"
        assert im.size == (220, 220), f"{name}: size {im.size} != (220, 220)"
        if animated:
            assert getattr(im, "n_frames", 1) > 1, f"{name}: expected animation"


def test_transparent_png_has_alpha():
    im = Image.open(ASSETS / "phoenix_transparent.png")
    assert im.mode == "RGBA"
    assert im.getchannel("A").getextrema()[0] == 0  # has fully-transparent pixels
```
(Loosen the `_mode` checks to what your derive actually produces; the load-bearing asserts are existence + 220×220 + animated-where-expected + the PNG alpha.)

- [ ] **Step 7: Run the test + lint + commit**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_phoenix_assets.py -q
uv run --extra dev ruff check tools/ tests/ && uv run --extra dev ruff format tools/ tests/
git add config/assets/_src config/assets/phoenix.* config/assets/ATTRIBUTION.md tools/derive_phoenix_assets.py Makefile tests/test_phoenix_assets.py
git commit -m "feat(assets): vendor CC0 phoenix + derive script + 5 derived sample assets

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 2: Repoint all asset references → phoenix

**Files:** `config/*.example.toml`, `docs/site/demos-pinned/*.toml`, `docs/site/demos-long/*.toml`, `docs/site/demos/*.toml` (the `path = "assets/…"` lines).

- [ ] **Step 1: Apply the repoint map to every `path =` reference**

For each old→new in the Global Constraints repoint map, replace the `path = "assets/<old>"` (and `path = "../../../config/assets/<old>"`-style relative forms in demos) with the phoenix equivalent. Get the exact files:
`git grep -l "pika_wave\|moon-transparent\|bunny-transparent\|bunny-nontransparent\|kpop-dance" -- config docs/site/demos-pinned docs/site/demos-long docs/site/demos`
Apply ONLY to `path =` lines in this task (prose/comments are Task 4). Keep `pride.gif` references untouched.

- [ ] **Step 2: Verify configs still parse + nothing points at a soon-removed file**

```bash
PYTHONPATH=tests/stubs uv run python -c "import tomllib,glob; [tomllib.load(open(f,'rb')) for f in glob.glob('config/*.toml')+glob.glob('docs/site/demos*/**/*.toml',recursive=True)]; print('parse ok')"
git grep -n "assets/pika_wave\|assets/moon-transparent\|assets/bunny-\|assets/kpop-dance" -- config docs/site/demos-pinned docs/site/demos-long docs/site/demos
```
Expected: parse ok; the second grep prints NOTHING (all `path =` refs repointed).

- [ ] **Step 3: Commit**

```bash
git add config docs/site/demos-pinned docs/site/demos-long docs/site/demos
git commit -m "refactor(assets): repoint demo/config asset paths to the phoenix

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 3: Remove the 7 old asset files

**Files:** delete `config/assets/{pika_wave.gif, pika_wave_transparent.gif, moon-transparent.png, bunny-transparent.png, bunny-nontransparent.png, moon_bunny_transparent.gif, kpop-dance.webp}`.

- [ ] **Step 1: git rm**

```bash
git rm config/assets/pika_wave.gif config/assets/pika_wave_transparent.gif \
  config/assets/moon-transparent.png config/assets/bunny-transparent.png \
  config/assets/bunny-nontransparent.png config/assets/moon_bunny_transparent.gif \
  config/assets/kpop-dance.webp
```

- [ ] **Step 2: Broken-path check (no `path =` reference to a removed file)**

```bash
git grep -n "pika_wave\|moon-transparent\|bunny-transparent\|bunny-nontransparent\|moon_bunny\|kpop-dance" -- . ':!docs/superpowers' ':!tests/test_no_real_brand.py' ':!config/assets/ATTRIBUTION.md'
```
Expected: only PROSE/comment hits remain (handled in Tasks 4-5) — NO `path =` line. (If a `path =` line still references a removed file, fix it — a Task 2 miss.)

- [ ] **Step 3: Commit**

```bash
git commit -m "chore(assets): remove the non-shippable Pikachu/Moon-Bunny/kpop assets

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 4: Asset prose rewrites (+ snippet/GIF parity, tech-writer)

**Files:** `docs/site/src/content/docs/widgets/gif.mdx`, `widgets/image.mdx`, `concepts/sections-and-modes.mdx`, the transitions docs that mention pika (`transitions/*.mdx`, `docs/content-source/transitions/sprite.md`, `docs/content-source/emoji.md`), and config comments (`config/config.gif_test.example.toml`, `config.firebird.example.toml`, `config.gif_text.example.toml`, others from the grep).

- [ ] **Step 1: Rewrite the asset-description prose → phoenix**

`Pikachu`/`pika`/`pika_wave` → `phoenix`; `kpop-dance`/`dance footage`/`K-POP` (as an asset descriptor) → `phoenix` (animated WebP); `moon`/`bunny` logo/asset descriptions → `phoenix`. Examples: `config.gif_test.example.toml`'s header "Uses `pika_wave.gif` (220×220 square)" → "Uses `phoenix.gif` (220×220 square)"; gif.mdx "Transparent Pikachu…" → "Transparent phoenix…". **Snippet/GIF parity (DOCS-STYLE §4):** any snippet quoting a repointed demo TOML must match it (it now says `phoenix`). Keep `pride.gif` mentions.

- [ ] **Step 2: docs build + lint + grep**

```bash
make docs-format && make docs-build && make docs-lint
git grep -in "pikachu\|pika_wave\|pika\b\|kpop\|moon-transparent\|bunny-" -- docs/site/src/content/docs config docs/content-source
```
Expected: docs clean; grep prints NOTHING (all asset prose rewritten). Each touched page passes the DOCS-STYLE §3 rubric (technical-writer review, §5).

- [ ] **Step 3: Commit**

```bash
git add docs/site/src/content/docs docs/content-source config
git commit -m "docs(assets): rewrite Pikachu/kpop/moon-bunny asset prose to the phoenix

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 5: Fix the stale asset-handling policy

**Files:** `.claude/skills/creating-a-config/references/asset-handling.md` (+ `snippets.md` if it names a removed asset).

- [ ] **Step 1: Rewrite the policy**

The doc currently states `bunny-transparent.png` / `kpop-dance.webp` "ship with the public repo." Rewrite: the repo ships ONE CC0 sample-media family — the Firebird **phoenix** (`config/assets/phoenix.*`, derived from a vendored CC0 source via `tools/derive_phoenix_assets.py`, see `config/assets/ATTRIBUTION.md`); real-brand / third-party / customer media is **gitignored and never committed**. Update any example that referenced `bunny-`/`pika_wave` to use `phoenix.*`.

- [ ] **Step 2: Grep + commit**

```bash
git grep -in "pika_wave\|pikachu\|moon_bunny\|moon-transparent\|bunny-\|kpop" -- .claude/skills/creating-a-config
git add .claude/skills/creating-a-config
git commit -m "docs(skill): correct the asset-handling policy to the single CC0 phoenix family

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```
Expected grep: empty (or only `phoenix` now).

---

### Task 6: Extend the completeness guard with asset needles

**Files:** `tests/test_no_real_brand.py`

- [ ] **Step 1: Add an asset-needle test**

Add a test (alongside the existing name + palette guards) that asserts ZERO references to the retired copyrighted/real-brand assets outside the allow-list (`docs/superpowers/` + this test file). Use PRECISE needles to avoid false hits:

```python
def test_no_retired_assets_outside_archival():
    import subprocess
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    needles = [
        "pika_wave", "pikachu", "moon_bunny", "moon-transparent",
        "bunny-transparent", "bunny-nontransparent", "kpop-dance", "kpop",
    ]
    offenders = []
    for needle in needles:
        res = subprocess.run(
            ["git", "grep", "-il", needle, "--",
             ":!docs/superpowers", ":!tests/test_no_real_brand.py"],
            cwd=repo, capture_output=True, text=True,
        )
        assert res.returncode in (0, 1), f"git grep failed (rc={res.returncode}): {res.stderr}"
        offenders += [f"{needle}: {p}" for p in res.stdout.splitlines() if p]
    assert not offenders, "retired assets still referenced:\n" + "\n".join(sorted(set(offenders)))
```
(Keep `pride` OUT of the needles. Note: `pikachu`/`kpop` are precise enough; `pika_wave`/`bunny-transparent` are exact filenames.)

- [ ] **Step 2: Run — expect GREEN (Tasks 2-5 removed the names)**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_no_real_brand.py -q`
Expected: PASS (all three guards: name, palette, assets). **If the asset guard FAILS**, it lists the files still naming a retired asset — fix those (a Task 2/4/5 miss), re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/test_no_real_brand.py
git commit -m "test: guard against retired copyrighted/real-brand asset names

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 7: Re-render affected demo GIFs + full verification

**Files:** `docs/site/public/demos-pinned/*.gif`, `docs/site/public/demos-long/*.gif` (the gif/image demos whose source asset changed).

- [ ] **Step 1: Identify + re-render**

The demos that now use `phoenix.*` (the `gif-*` and `image-*` pinned demos + the affected tutorials) need re-rendering so the GIF matches the new asset. For each, find its config + render:
```bash
make render-demo CONFIG=docs/site/demos-pinned/<name>.toml OUT=docs/site/public/demos-pinned/<name>.gif
```
(Use `make render-pinned-demos` for the batch if it's reliable.) **If a re-render is BLOCKED** (gitignored licensed font / toolchain), FLAG it in the report (the config/snippet is consistent; the GIF is the stale artifact) — do NOT fake. Record re-rendered vs blocked.

- [ ] **Step 2: Full verification**

```bash
PYTHONPATH=tests/stubs uv run pytest -q
uv run --extra dev ruff check src/ tests/ tools/ && uv run --extra dev ruff format --check src/ tests/ tools/
uv run --extra dev pyright src/
make docs-format && make docs-build && make docs-lint
```
Expected: full suite green (incl. the gif/image widget tests + `test_firebird_bigsign_config_widgets_build` + the three guards + `test_phoenix_assets`); lint/types/docs clean.

- [ ] **Step 3: Commit**

```bash
git add docs/site/public
git commit -m "docs(demos): re-render demos onto the phoenix asset

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

## Final verification (after all tasks)

- [ ] `tests/test_no_real_brand.py` passes (name + palette + asset guards) and `tests/test_phoenix_assets.py` passes.
- [ ] `PYTHONPATH=tests/stubs uv run pytest -q` full suite green.
- [ ] `git grep -in "pika_wave\|pikachu\|moon_bunny\|moon-transparent\|bunny-\|kpop" -- . ':!docs/superpowers' ':!tests/test_no_real_brand.py' ':!config/assets/ATTRIBUTION.md'` → empty.
- [ ] No `path =` reference to a removed asset; the 7 files gone; `pride.*` kept.
- [ ] `make docs-build` + `make docs-lint` clean; re-rendered GIFs committed; blocked ones flagged.
- [ ] `git status` no untracked (`??`); `.superpowers/asset-src/` scratch consumed (source now committed under `config/assets/_src/`).
- [ ] Push, open PR against `main`, CI green before requesting merge.

## Notes / gotchas

- **Animated-GIF transparency in Pillow is the trickiest bit** (Task 1) — GIF is 1-bit alpha; verify the transparent gif renders correctly (the scroll-behind demo is the real test in Task 7). Iterate on `to_p_transparent` if needed.
- **`moon_bunny_transparent.gif` is an orphan** — no config references it; just `git rm` (Task 3).
- The derive script must be reproducible from the COMMITTED source (`config/assets/_src/`), not the scratch staging dir.
- Some demo GIFs can't re-render without the gitignored licensed fonts (same as #256) — flag, don't fake.
- The asset guard's needles must exclude `pride`; keep them precise (`pika_wave`/`pikachu`/`kpop-dance`/`kpop`/`moon_bunny`/`moon-transparent`/`bunny-transparent`/`bunny-nontransparent`).
- After merge (controller): the deferred git-history scrub (open-source prep) now also covers the removed binary assets; note it.
