# Spleen Pixel Fonts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bundle the Spleen pixel-font family (four OTFs, natives 12/16/24/32 px) so hi-res text is crisp at small sizes where Inter smooshes, with a validate rule warning on off-grid `font_size`.

**Architecture:** The OTFs are ordinary hi-res fonts dropped into `src/led_ticker/fonts/hires/` and resolved by the existing `resolve_font(name, size)` path — no new loader machinery. A module-level `_PIXEL_NATIVE` registry in `hires_loader.py` records each pixel font's native px height; new validate rule 69 warns when a config uses a pixel-native font at a size that isn't `native × k`. The load-bearing property (Spleen OTF at native size renders strictly binary through PIL) is pinned by tests.

**Tech Stack:** Python, Pillow, pytest. Repo: core (`/Users/james/projects/github/jamesawesome/led-ticker`), branch `spleen-pixel-fonts`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-21-spleen-pixel-fonts-design.md`.
- Vendored set is EXACTLY four OTFs from the Spleen **2.2.0** release tarball (`https://github.com/fcambus/spleen/releases/download/2.2.0/spleen-2.2.0.tar.gz`): `spleen-6x12.otf` (native 12), `spleen-8x16.otf` (16), `spleen-12x24.otf` (24), `spleen-16x32.otf` (32). NOT `spleen-32x64` (YAGNI) and NOT `spleen-5x8` (no upstream OTF). License BSD-2-Clause (Frederic Cambus) — vendor upstream `LICENSE` as `src/led_ticker/fonts/hires/SPLEEN-LICENSE.txt` + a `THIRD_PARTY_NOTICES.md` section (same posture as DejaVu).
- Rule number is **69** (68 is the current max). Warning only — NO runtime size-snapping, no loader behavior change for off-grid sizes.
- Exact-advance assertions ARE allowed for Spleen at native sizes (integer grid by construction) — this is a deliberate exception to the "never exact-pin hires advances" project gotcha, which remains in force for OUTLINE fonts (Inter/DejaVu).
- No `from __future__ import annotations`. Lint gates from repo root: `uv run --extra dev ruff check src/ tests/`, `uv run --extra dev ruff format --check src/ tests/`, `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/` (2 pre-existing errors in `app/run.py`+`ticker.py` are known-acceptable).
- Tests: `uv run --no-sync python -m pytest`. Known pre-existing local-only failure `test_no_legacy_mode_names_in_live_tree` (stale worktree) — ignore. Git hooks broken here — `git commit/push --no-verify` after running gates manually.
- Task 3 ends at a HARD STOP: James reviews the Inter-vs-Spleen GIF before the PR (Task 4).

---

### Task 1: Vendor the four Spleen OTFs + license + the binary-grid pin tests

**Files:**
- Create (vendored): `src/led_ticker/fonts/hires/spleen-6x12.otf`, `spleen-8x16.otf`, `spleen-12x24.otf`, `spleen-16x32.otf`, `SPLEEN-LICENSE.txt`
- Modify: `THIRD_PARTY_NOTICES.md`
- Test: `tests/test_spleen_fonts.py` (new)

**Interfaces:**
- Consumes: existing `resolve_font(name, size, threshold)` (`led_ticker.fonts`), `load_hires_font` (`led_ticker.fonts.hires_loader`), `BUNDLED_HIRES_DIR` (`hires_loader.py:29`).
- Produces: the four font names resolvable as `resolve_font("spleen-6x12", 12)` etc. Task 2 relies on these exact lowercase names.

- [ ] **Step 1: Vendor the assets**

```bash
cd /tmp && curl -sL -o spleen.tar.gz \
  "https://github.com/fcambus/spleen/releases/download/2.2.0/spleen-2.2.0.tar.gz"
tar xzf spleen.tar.gz
REPO=/Users/james/projects/github/jamesawesome/led-ticker
for f in spleen-6x12 spleen-8x16 spleen-12x24 spleen-16x32; do
  cp spleen-2.2.0/$f.otf $REPO/src/led_ticker/fonts/hires/$f.otf
done
cp spleen-2.2.0/LICENSE $REPO/src/led_ticker/fonts/hires/SPLEEN-LICENSE.txt
ls -la $REPO/src/led_ticker/fonts/hires/
head -3 $REPO/src/led_ticker/fonts/hires/SPLEEN-LICENSE.txt
# expect: "Copyright (c) 2018-2026, Frederic Cambus" BSD-2 text
```

Verify wheel inclusion (the dir ships whole, same as DejaVu): `cd $REPO && uv build --wheel >/dev/null 2>&1 && unzip -l dist/*.whl | grep -c "spleen-" && rm -rf dist` — expect 5 (4 OTFs + license).

- [ ] **Step 2: Add the THIRD_PARTY_NOTICES section**

Append to `THIRD_PARTY_NOTICES.md` (match the DejaVu section's formatting):

```markdown
## Spleen — bundled pixel fonts for small hi-res sizes

Four sizes of the Spleen monospaced pixel-font family ship as hi-res fonts
(`spleen-6x12`, `spleen-8x16`, `spleen-12x24`, `spleen-16x32` — native 12,
16, 24, and 32 px). At their native pixel size (or an integer multiple) they
rasterize to exact 1-bit output — crisp on LED panels at sizes where outline
fonts blur. Vendored at `src/led_ticker/fonts/hires/spleen-*.otf`.

- **Source:** Spleen 2.2.0 — https://github.com/fcambus/spleen
- **License:** BSD 2-Clause (c) 2018-2026 Frederic Cambus — see
  `src/led_ticker/fonts/hires/SPLEEN-LICENSE.txt`.
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_spleen_fonts.py`:

```python
"""Spleen pixel fonts — the binary-grid property the feature rests on.

A Spleen OTF rendered at its native pixel size (or an integer multiple)
produces strictly binary output through PIL: every pixel 0 or 255, exact
integer advances. If a Pillow upgrade ever breaks grid alignment, these
fail loudly. Exact-advance pins are safe HERE (integer grid by
construction) — they remain banned for outline fonts (Inter/DejaVu).
"""

from PIL import Image, ImageDraw, ImageFont

from led_ticker.fonts import resolve_font
from led_ticker.fonts.hires_loader import BUNDLED_HIRES_DIR, load_hires_font

_SPLEEN = {  # name -> (native_px, advance_px at native)
    "spleen-6x12": (12, 6),
    "spleen-8x16": (16, 8),
    "spleen-12x24": (24, 12),
    "spleen-16x32": (32, 16),
}
_SAMPLE = "EV 104.6e MA%?"


def _gray_values(name: str, size: int) -> set[int]:
    """Raw PIL rendering (pre-threshold) of the sample text."""
    pil = ImageFont.truetype(str(BUNDLED_HIRES_DIR / f"{name}.otf"), size)
    asc, desc = pil.getmetrics()
    img = Image.new("L", (len(_SAMPLE) * size, asc + desc), 0)
    ImageDraw.Draw(img).text((0, 0), _SAMPLE, font=pil, fill=255)
    px = img.load()
    return {px[x, y] for x in range(img.width) for y in range(img.height)}


class TestSpleenResolves:
    def test_all_four_names_resolve_at_native(self):
        for name, (native, _adv) in _SPLEEN.items():
            font = resolve_font(name, native)
            g = font.resolve_glyph("M")
            assert g is not None and g.lit, name


class TestBinaryGrid:
    def test_native_size_renders_strictly_binary(self):
        for name, (native, _adv) in _SPLEEN.items():
            vals = _gray_values(name, native)
            assert vals <= {0, 255}, f"{name}@{native}: intermediate grays {sorted(v for v in vals if 0 < v < 255)[:5]}"

    def test_double_size_renders_strictly_binary(self):
        vals = _gray_values("spleen-6x12", 24)
        assert vals <= {0, 255}

    def test_off_grid_renders_antialiased(self):
        # The rule-69 premise: off-grid = intermediate grays = mush.
        vals = _gray_values("spleen-6x12", 11)
        assert any(0 < v < 255 for v in vals)

    def test_threshold_is_a_noop_at_native(self):
        # Through OUR loader: thresholds 1 and 254 must yield identical lit
        # sets (cache keys differ, so these are fresh rasterizations).
        lo = load_hires_font("spleen-6x12", 12, 1)
        hi = load_hires_font("spleen-6x12", 12, 254)
        assert lo is not None and hi is not None
        for ch in "EVLADIST04.62%":
            gl, gh = lo.resolve_glyph(ch), hi.resolve_glyph(ch)
            assert gl is not None and gh is not None, ch
            assert gl.lit == gh.lit, ch

    def test_exact_integer_advance_at_native(self):
        for name, (native, adv) in _SPLEEN.items():
            font = resolve_font(name, native)
            g = font.resolve_glyph("M")
            assert g is not None and g.advance == adv, name
```

- [ ] **Step 4: Run to verify red → green**

Run: `uv run --no-sync python -m pytest tests/test_spleen_fonts.py -q`
Before Step 1's copy the resolve test fails (`UnknownFontError`); after vendoring, ALL should pass with no code change (the loader already handles OTFs). If `test_native_size_renders_strictly_binary` fails on this machine, STOP and report — the feature premise is broken, do not loosen the assertion.

- [ ] **Step 5: Gates + commit**

Run `uv run --no-sync python -m pytest tests/test_spleen_fonts.py tests/test_hires_loader.py tests/test_hires_loader_ladder.py -q` + the three lint gates (scope: the new test file only for ruff; pyright on `src/` unchanged).

```bash
git add src/led_ticker/fonts/hires/spleen-*.otf src/led_ticker/fonts/hires/SPLEEN-LICENSE.txt THIRD_PARTY_NOTICES.md tests/test_spleen_fonts.py
git commit --no-verify -m "feat(fonts): bundle Spleen pixel fonts — crisp 1-bit text at 12/16/24/32 px"
```

---

### Task 2: `_PIXEL_NATIVE` registry + validate rule 69 (off-grid warning)

**Files:**
- Modify: `src/led_ticker/fonts/hires_loader.py` (registry only — no behavior change)
- Modify: `src/led_ticker/validate.py`
- Test: `tests/test_validate.py` (append), `tests/test_spleen_fonts.py` (append registry test)

**Interfaces:**
- Consumes: Task 1's font names; `ValidationIssue` idiom and the `conf` fixture in `tests/test_validate.py`; rule-68 registration at `validate.py:3540` (`warnings.extend(_check_glyph_coverage(config))`).
- Produces: `hires_loader._PIXEL_NATIVE: dict[str, int]`; `validate._check_pixel_font_size(config) -> list[ValidationIssue]` registered as rule 69.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_validate.py` (mirror the `TestGlyphCoverage` idioms — `conf` fixture, async `validate_config`, `_HIRES_CFG`-style template):

```python
_SPLEEN_CFG = """
[display]
rows = 64
cols = 64
chain = 8
default_scale = 4

[[playlist.section]]
mode = "slideshow"

[[playlist.section.widget]]
type = "message"
text = "EV 104.6"
font = "spleen-6x12"
font_size = {size}
"""


class TestPixelFontSize:
    async def test_off_grid_size_warns_with_nearest_sizes(self, conf):
        result = await validate_config(conf(_SPLEEN_CFG.format(size=13)))
        w = [i for i in result.warnings if i.rule == 69]
        assert w and "12" in w[0].fix and "24" in w[0].fix

    async def test_below_native_suggests_native_only(self, conf):
        result = await validate_config(conf(_SPLEEN_CFG.format(size=8)))
        w = [i for i in result.warnings if i.rule == 69]
        assert w and "12" in w[0].fix and "24" not in w[0].fix

    async def test_native_and_multiple_silent(self, conf):
        for size in (12, 24, 36):
            result = await validate_config(conf(_SPLEEN_CFG.format(size=size)))
            assert not [i for i in result.warnings if i.rule == 69], size

    async def test_non_pixel_font_never_warns(self, conf):
        cfg = conf(_SPLEEN_CFG.replace("spleen-6x12", "Inter-Bold").format(size=13))
        result = await validate_config(cfg)
        assert not [i for i in result.warnings if i.rule == 69]

    async def test_default_bdf_widget_unaffected(self, conf):
        cfg = conf(
            _SPLEEN_CFG.replace('font = "spleen-6x12"\n', "").format(size=13)
        )
        result = await validate_config(cfg)
        assert not [i for i in result.warnings if i.rule == 69]
```

Append to `tests/test_spleen_fonts.py`:

```python
class TestPixelNativeRegistry:
    def test_registry_matches_bundled_set(self):
        from led_ticker.fonts.hires_loader import _PIXEL_NATIVE

        assert _PIXEL_NATIVE == {
            "spleen-6x12": 12,
            "spleen-8x16": 16,
            "spleen-12x24": 24,
            "spleen-16x32": 32,
        }
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --no-sync python -m pytest tests/test_validate.py -q -k PixelFontSize`
Expected: FAIL (`_PIXEL_NATIVE` undefined / no rule 69 emitted).

- [ ] **Step 3: Implement**

In `src/led_ticker/fonts/hires_loader.py`, next to the other module constants (after `_ASCII_GLYPH_FALLBACKS`/`_WARNED_MISSING`):

```python
# Pixel-native bundled fonts: name -> native pixel height. A pixel font is
# crisp ONLY at its native size or an integer multiple (rendering lands
# exactly on the LED grid, strictly 1-bit); anything else antialiases into
# mush. Single source of truth for validate rule 69 and the docs. Runtime
# stays permissive — off-grid renders what was asked, only validate warns.
_PIXEL_NATIVE: dict[str, int] = {
    "spleen-6x12": 12,
    "spleen-8x16": 16,
    "spleen-12x24": 24,
    "spleen-16x32": 32,
}
```

In `src/led_ticker/validate.py`, add after `_check_glyph_coverage` (follow its exact idioms — dict `widget_cfg`, function-local imports with `# noqa: PLC0415`):

```python
def _check_pixel_font_size(config: AppConfig) -> list[ValidationIssue]:
    """Rule 69: a pixel-native font (Spleen) at a `font_size` that is not an
    integer multiple of its native pixel height renders blurry — the outline
    lands off the LED grid and antialiases, defeating the point of a pixel
    font. Warning only; the renderer stays permissive (no size snapping —
    a silent snap would change layout underneath an existing config)."""
    from led_ticker.fonts.hires_loader import _PIXEL_NATIVE  # noqa: PLC0415

    issues: list[ValidationIssue] = []
    for i, section in enumerate(config.sections):
        for j, widget_cfg in enumerate(section.widgets):
            name = widget_cfg.get("font")
            native = _PIXEL_NATIVE.get(name) if isinstance(name, str) else None
            if native is None:
                continue
            size = widget_cfg.get("font_size")
            if not isinstance(size, int) or isinstance(size, bool):
                continue  # missing/typed-wrong size → other rules own it
            if size >= native and size % native == 0:
                continue  # on-grid: native or an integer multiple
            lo = (size // native) * native
            hi = lo + native
            suggest = f"Use {hi}." if lo < native else f"Use {lo} or {hi}."
            issues.append(
                ValidationIssue(
                    rule=69,
                    location=f"section[{i}].widget[{j}]",
                    severity="warning",
                    message=(
                        f"{name} at {size}px renders blurry -- pixel fonts "
                        f"are only crisp at their native {native}px or an "
                        f"integer multiple"
                    ),
                    fix=suggest,
                )
            )
    return issues
```

Register it right after rule 68 (`validate.py:3540`):

```python
        warnings.extend(_check_glyph_coverage(config))
        warnings.extend(_check_pixel_font_size(config))
```

- [ ] **Step 4: Run to verify green**

Run: `uv run --no-sync python -m pytest tests/test_validate.py tests/test_spleen_fonts.py -q`
Expected: all pass, including the full existing validate suite (rule 69 only fires on pixel-font names, which no existing test config uses).

- [ ] **Step 5: Gates + commit**

Three lint gates, then:

```bash
git add src/led_ticker/fonts/hires_loader.py src/led_ticker/validate.py tests/test_validate.py tests/test_spleen_fonts.py
git commit --no-verify -m "feat(validate): rule 69 — warn when a pixel font is used off its native grid"
```

---

### Task 3: Docs + the Inter-vs-Spleen visual gate (HARD STOP for James)

**Files:**
- Modify: `docs/site/src/content/docs/concepts/fonts.mdx`
- Scratch: `$CLAUDE_JOB_DIR/tmp/spleen-gate.toml` + rendered GIF/sheet

- [ ] **Step 1: Full suite + gates**

`uv run --no-sync python -m pytest tests/ -q` (only the known stale-worktree failure allowed) + the three lint gates. Record the pass count.

- [ ] **Step 2: Docs — "Pixel fonts" subsection**

In `docs/site/src/content/docs/concepts/fonts.mdx`, insert a `## Pixel fonts` section between `## font_threshold` and `## Character coverage`:

```markdown
## Pixel fonts

Four sizes of [Spleen](https://github.com/fcambus/spleen), a monospaced
pixel font, ship alongside Inter: `spleen-6x12` (12 px), `spleen-8x16`
(16 px), `spleen-12x24` (24 px), and `spleen-16x32` (32 px). Every stroke
is designed on the pixel grid, so at the font's **native size — or any
integer multiple** — glyphs rasterize to exact 1-bit output: no
anti-aliasing, no stroke merging, and `font_threshold` has no effect.

Use them where Inter gets muddy: text below ~14 px, and tabular content
like stats or prices (the fixed-width digits keep columns aligned).

The native-size rule is the one thing to respect: `spleen-6x12` at 12 or
24 px is pixel-perfect; at 13 px it lands off the grid and blurs.
`led-ticker validate` warns when a config does this (rule 69) and names
the nearest crisp sizes.
```

In the `## Decision tree` table add a row after the close-viewing bigsign row:

```markdown
| Bigsign, small/tabular text      | Any              | `spleen-6x12` @ 12 px (or 24) — pixel-crisp |
```

Prettier + build: `cd docs/site && pnpm exec prettier --write src/content/docs/concepts/fonts.mdx && pnpm run build` (expect exit 0, all pages built).

- [ ] **Step 3: The gate GIF**

Write `$CLAUDE_JOB_DIR/tmp/spleen-gate.toml` — bigsign flat render (`rows = 64`, `cols = 256`, `chain_length = 1`, `default_scale = 4`), slideshow, `transition = "cut"`, `hold_time = 2`, four message widgets:

1. `text = "EV 104.6 LA 28 DIST 412FT"`, `font = "Inter-Regular"`, `font_size = 11`, `font_threshold = 80` — the today-status-quo (expect smoosh)
2. same text, `font = "spleen-6x12"`, `font_size = 12` — the fix
3. `text = "W 8-4 ATT 41,022 #1 NL EAST"`, `font = "spleen-6x12"`, `font_size = 12`
4. `text = "SPLEEN 24PX"`, `font = "spleen-12x24"`, `font_size = 24`

Render: `uv run --no-sync python tools/render_demo/render.py $CLAUDE_JOB_DIR/tmp/spleen-gate.toml -o $CLAUDE_JOB_DIR/tmp/spleen-gate.gif --duration 8`. Build a contact sheet (all frames stacked, PIL), READ it yourself first: widget 1 shows Inter's merging, widgets 2–4 crisp with fully open counters. Then STOP.

- [ ] **Step 4: HARD STOP — send James the sheet + GIF**

Send the contact sheet + GIF + pass count. The ask: "does Spleen read clearly better than Inter at the small size?" Do NOT commit docs or open the PR until approved.

- [ ] **Step 5 (post-gate): Commit docs**

```bash
git add docs/site/src/content/docs/concepts/fonts.mdx
git commit --no-verify -m "docs(fonts): pixel-fonts section — Spleen sizes, native-grid rule"
```

---

### Task 4 (post-gate): PR

- [ ] **Step 1:** Push `spleen-pixel-fonts`; `gh pr create`. Body: the smoosh problem + the 9–13 px baseball surface; why a pixel font (binarization at small sizes defeats outline fonts); the verified binary-grid property (with the 12/11/24 gray-values table); what ships (4 OTFs, BSD-2, notices entry); rule 69 (warn-only, no snapping); the pin tests (incl. why exact-advance pins are safe for Spleen only); the gate GIF; follow-up noted: baseball-plugin adoption (9/11 px Inter → `spleen-6x12` @ 12) in the plugins repo. Release = core minor.
- [ ] **Step 2:** `gh pr checks --watch`. STOP — James merges + cuts the release.

---

## Self-review (done at write time)

- **Spec coverage:** assets+license+notices (T1), registry+rule 69 (T2), tests incl. binary pin/threshold-noop/off-grid premise (T1) and all five rule-69 scenarios (T2), docs+decision tree (T3), visual gate (T3), PR/release shape (T4). Non-goals respected — no snapping, no plugin adoption, no 5x8/32x64.
- **Placeholder scan:** none.
- **Type consistency:** `_PIXEL_NATIVE: dict[str, int]` consistent across T2 registry/rule/tests; font names lowercase `spleen-WxH` everywhere; `_check_pixel_font_size` name consistent between implementation and registration.
