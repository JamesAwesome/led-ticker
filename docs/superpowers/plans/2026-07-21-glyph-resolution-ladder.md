# Glyph Resolution Ladder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A hi-res glyph resolution ladder — chosen font → bundled DejaVu → 1:1 ASCII look-alike → `?`+WARN — behind the existing `resolve_glyph` seam, so no character silently boxes and none is a `?` without a load-time warning; plus a validate rule that preflights the same ladder.

**Architecture:** `HiresFont.resolve_glyph` is the single seam all four hi-res consumers already route through (draw, per-char draw, `get_text_width`, `hires_text_width`). It gains: notdef-fingerprint miss detection (fixes the silent-box class), lazy rasterization of unseen chars (charset stops being a wall), a DejaVu fallback rung (arrows/symbols the chosen font lacks), a font-aware 1:1 ASCII table, and a once-per-font WARN on the final `?`. A new validate rule walks config text through the same ladder (emoji excluded) and warns on degraded rungs.

**Tech Stack:** Python, Pillow (`ImageFont`/`ImageDraw`, already a dep), pytest. Repo: core (`/Users/james/projects/github/jamesawesome/led-ticker`), branch `glyph-ladder-spec`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-21-glyph-resolution-ladder-design.md`.
- **Scope corrections from the spec (verified against code):** (1) the render ladder is **hi-res only** — BDF draws via `scaled_canvas.draw_bdf_text` + `CharacterWidth`, NOT `resolve_glyph`; every recorded incident is hi-res. BDF keeps today's behavior; the validate rule still covers BDF sections. (2) Rung 3 is **1:1 only** (single char → single substitute char); multi-char expansion (½→"1/2") is DEFERRED — it desyncs the per-char color/token index (the colored-tokens has_emoji-basis hazard) and no recorded incident is multi-char.
- Draw and measure MUST stay in lockstep on resolution (the #393 lesson: a `?`-vs-`-` advance delta skews right-aligned/scrolling text). All four hi-res sites route through the same `resolve_glyph` — do not fork logic per site.
- DejaVu Sans vendored into `src/led_ticker/assets/`; loaded lazily (first rung-2 miss), never at import. License confirmed from the vendored file, recorded in `THIRD_PARTY_NOTICES.md`.
- No `from __future__ import annotations`. Lint gates from repo root: `uv run --extra dev ruff check src/ tests/`, `ruff format --check src/ tests/`, `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/` (CI scope `src/`; 2 pre-existing errors in `app/run.py`+`ticker.py` are known-acceptable).
- Tests: `uv run --no-sync python -m pytest`. Known pre-existing local-only failure `test_no_legacy_mode_names_in_live_tree` (stale worktree) — ignore. Git hooks broken here — `git commit/push --no-verify` after running gates manually.
- Task 5 ends at a HARD STOP: James reviews the historical-incident GIF before the PR (Task 6).

All commands run from the core repo root unless noted.

---

### Task 1: Notdef fingerprint + lazy rasterization (fixes the silent box + the charset wall)

**Files:**
- Modify: `src/led_ticker/fonts/hires_loader.py`
- Test: `tests/test_hires_loader_ladder.py` (new)

**Interfaces:**
- Produces: `HiresFont` gains `pil_font: Any = None` (retained PIL font for lazy rasterize; `compare=False, repr=False`), `threshold: int = THRESHOLD`, `notdef_lit: tuple[tuple[int, int], ...] = ()`. `resolve_glyph(ch)` reworked: dict hit → lazy-rasterize-and-cache on miss → notdef/empty ⇒ treat as MISSING (return None or fall to the ASCII table, which Task 3 fills). A module helper `_is_notdef(glyph, notdef_lit) -> bool`. `_rasterize` prunes eager glyphs whose lit matches notdef and captures `notdef_lit` from a PUA probe.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_hires_loader_ladder.py`:

```python
"""The glyph resolution ladder — notdef detection + lazy rasterization."""

from led_ticker.fonts.hires_loader import load_hires_font

_INTER = "Inter-Bold"  # bundled; lacks ▲ U+25B2 (renders notdef)


class TestNotdefDetection:
    def test_char_font_lacks_resolves_to_missing_not_box(self):
        # ▲ IS in GEOMETRIC_SHAPES (eagerly rasterized) but Inter has no
        # glyph → Pillow draws the notdef box. Pre-ladder this stored a
        # tofu box in `glyphs["▲"]`; now it must be detected as MISSING.
        font = load_hires_font(_INTER, 30)
        assert font is not None
        # After the fix: no eager notdef glyph survives in the dict.
        # resolve_glyph returns None (Task 1) — DejaVu (Task 2) fills it.
        assert font.resolve_glyph("▲") is None

    def test_present_char_still_resolves(self):
        font = load_hires_font(_INTER, 30)
        g = font.resolve_glyph("A")
        assert g is not None and g.lit  # real glyph, lit pixels

    def test_notdef_fingerprint_captured(self):
        font = load_hires_font(_INTER, 30)
        # A private-use codepoint has no assignment → notdef. Its lit set
        # is the captured fingerprint (non-empty for a boxed notdef).
        assert isinstance(font.notdef_lit, tuple)


class TestLazyRasterization:
    def test_char_outside_charset_lazily_rasterizes(self):
        # '∑' N-ARY SUMMATION (U+2211) is NOT in the eager charset. Inter
        # lacks it too → resolves None here (DejaVu has it, Task 2). But a
        # char Inter HAS that's outside the charset must lazily render.
        font = load_hires_font(_INTER, 30)
        # 'ǽ' (U+01FD) — Latin, outside EXTENDED_LATIN, Inter has it.
        g = font.resolve_glyph("ǽ")
        assert g is not None and g.lit

    def test_lazy_result_is_cached(self):
        font = load_hires_font(_INTER, 30)
        a = font.resolve_glyph("ǽ")
        b = font.resolve_glyph("ǽ")
        assert a is b  # same object → cached, not re-rasterized
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --no-sync python -m pytest tests/test_hires_loader_ladder.py -q`
Expected: FAIL — `test_char_font_lacks_resolves_to_missing_not_box` returns a notdef glyph (not None), lazy tests miss (char not in dict → None even though Inter has it).

- [ ] **Step 3: Implement notdef + lazy in `hires_loader.py`**

Add the notdef helper (module level, near `_rasterize_glyph`):

```python
# A private-use codepoint is guaranteed unassigned, so rasterizing it yields
# the font's notdef glyph (a box, or empty if the font has no notdef). We
# fingerprint it once per font and treat any glyph whose lit pixels match as
# MISSING — this is what makes "▲ in a font that lacks it" a detectable miss
# instead of a silently-painted tofu box.
_NOTDEF_PROBE = ""  # PUA U+E000


def _is_notdef(glyph: HiresGlyph, notdef_lit: tuple[tuple[int, int], ...]) -> bool:
    """A glyph is 'missing' if it matches the font's notdef fingerprint, or
    is empty for a non-whitespace request (fonts with no notdef render
    nothing for unknown chars)."""
    return glyph.lit == notdef_lit or (not glyph.lit and notdef_lit == ())
```

Give `HiresFont` the retained font + fingerprint (defaults keep existing
direct constructions working):

```python
@dataclass(frozen=True)
class HiresFont:
    name: str
    size: int
    ascent: int
    descent: int
    line_height: int
    glyphs: dict[str, HiresGlyph] = field(default_factory=dict)
    threshold: int = THRESHOLD
    notdef_lit: tuple[tuple[int, int], ...] = ()
    pil_font: Any = field(default=None, compare=False, repr=False)

    def resolve_glyph(self, ch: str) -> HiresGlyph | None:
        """Glyph for `ch` via the resolution ladder. Rung 1 (this font):
        cached dict → lazily rasterize an unseen char → treat notdef/empty
        as MISSING. Returns None on a miss so the caller (and Tasks 2-3)
        can fall to the next rung; None ultimately draws '?'."""
        glyph = self.glyphs.get(ch)
        if glyph is None and self.pil_font is not None and ch:
            glyph = _rasterize_glyph(
                self.pil_font, ch, self.ascent, self.descent, self.threshold
            )
            if _is_notdef(glyph, self.notdef_lit):
                self.glyphs[ch] = _MISSING  # cache the miss (sentinel)
                return None
            self.glyphs[ch] = glyph  # cache the hit
            return glyph
        if glyph is _MISSING:
            return None
        return glyph
```

Add the miss sentinel near the top (after `HiresGlyph`):

```python
# Sentinel cached in `glyphs` for a char proven missing (notdef) — avoids
# re-rasterizing a known miss on every draw tick.
_MISSING = HiresGlyph(width=0, height=0, advance=0, bearing_x=0, bearing_y=0, lit=())
```

(NOTE: `_MISSING` has empty `lit` and `advance=0`; `resolve_glyph` returns
None for it, so it never draws — the `advance=0` is never consumed. Keep it
distinct from a real space glyph by identity check `is _MISSING`.)

Rework `_rasterize` to capture the fingerprint, prune eager notdef glyphs,
and retain the pil_font:

```python
def _rasterize(
    path: Path, size: int, name: str, threshold: int = THRESHOLD
) -> HiresFont:
    pil_font = ImageFont.truetype(str(path), size)
    ascent, descent = pil_font.getmetrics()
    notdef = _rasterize_glyph(pil_font, _NOTDEF_PROBE, ascent, descent, threshold)
    notdef_lit = notdef.lit
    chars = (
        string.printable
        + EXTENDED_LATIN
        + EXTENDED_PUNCTUATION
        + GEOMETRIC_SHAPES
        + SYMBOLS
    )
    glyphs: dict[str, HiresGlyph] = {}
    for ch in chars:
        g = _rasterize_glyph(pil_font, ch, ascent, descent, threshold)
        # Prune eager notdef glyphs: GEOMETRIC_SHAPES (▲▼●○◆◇) rasterize to
        # a box in fonts that lack them — pre-ladder this WAS the tofu.
        if _is_notdef(g, notdef_lit) and ch not in string.printable:
            continue
        glyphs[ch] = g
    return HiresFont(
        name=name, size=size, ascent=ascent, descent=descent,
        line_height=ascent + descent, glyphs=glyphs,
        threshold=threshold, notdef_lit=notdef_lit, pil_font=pil_font,
    )
```

(The `ch not in string.printable` guard keeps ASCII space/control chars —
whose empty rasterization is legitimate, not a miss — in the dict.)

- [ ] **Step 4: Run tests + the font suite**

Run: `uv run --no-sync python -m pytest tests/test_hires_loader_ladder.py tests/test_hires_loader.py tests/test_pixel_emoji.py -q`
Expected: new tests pass; existing hires-font tests still green (the retained pil_font + defaults don't change any existing assertion). If a pre-existing test constructed `HiresFont(...)` positionally and the new fields shifted it — they're keyword/defaulted, so positional construction up to `glyphs` is unchanged. Run the three lint gates.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/fonts/hires_loader.py tests/test_hires_loader_ladder.py
git commit --no-verify -m "feat(fonts): notdef detection + lazy glyph rasterization (ladder rung 1)"
```

---

### Task 2: DejaVu fallback rung

**Files:**
- Modify: `src/led_ticker/fonts/hires_loader.py`
- Create (vendored): `src/led_ticker/assets/DejaVuSans.ttf`, and its license file `src/led_ticker/assets/DejaVuSans-LICENSE.txt`
- Modify: `THIRD_PARTY_NOTICES.md`
- Test: `tests/test_hires_loader_ladder.py` (append)

**Interfaces:**
- Consumes: Task 1's `resolve_glyph`, `_is_notdef`, `_rasterize_glyph`.
- Produces: `_dejavu_glyph(ch, size, ascent, descent, threshold) -> HiresGlyph | None` (module, `@functools.lru_cache` on the DejaVu `ImageFont` per size); `resolve_glyph` rung 2 consults it before returning None.

- [ ] **Step 1: Vendor DejaVu + record the license**

```bash
mkdir -p src/led_ticker/assets
curl -sL -o src/led_ticker/assets/DejaVuSans.ttf \
  "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf"
curl -sL -o src/led_ticker/assets/DejaVuSans-LICENSE.txt \
  "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/LICENSE"
ls -la src/led_ticker/assets/DejaVuSans.ttf   # expect ~700KB
head -5 src/led_ticker/assets/DejaVuSans-LICENSE.txt   # confirm Bitstream Vera / DejaVu terms
```

Verify it ships in the wheel: `uv build --wheel >/dev/null 2>&1 && unzip -l dist/*.whl | grep -c "DejaVuSans.ttf" && rm -rf dist` (expect 1; if 0, the .ttf is committed so hatchling should include it — verify the packaging config as the emoji-pack task did).

Add to `THIRD_PARTY_NOTICES.md` a section:

```markdown
## DejaVu Sans — the hi-res glyph fallback font

The hi-res glyph resolution ladder (`fonts/hires_loader.py`) falls back to
DejaVu Sans for characters a config's chosen font lacks (arrows, math and
currency symbols, extended punctuation), rasterized at the same pixel size.
Vendored at `src/led_ticker/assets/DejaVuSans.ttf`.

- **Source:** DejaVu Fonts — https://dejavu-fonts.github.io/
- **License:** DejaVu Fonts License (Bitstream Vera-derived; permissive,
  attribution-only) — see `src/led_ticker/assets/DejaVuSans-LICENSE.txt`.
```

- [ ] **Step 2: Write the failing test** (append)

```python
class TestDejaVuRung:
    def test_arrow_font_lacks_resolves_via_dejavu(self):
        # ▲ U+25B2: Inter lacks it (Task 1 → None at rung 1); DejaVu HAS it.
        font = load_hires_font(_INTER, 30)
        g = font.resolve_glyph("▲")
        assert g is not None and g.lit  # real arrow from DejaVu, not a box

    def test_dejavu_glyph_is_not_notdef(self):
        from led_ticker.fonts.hires_loader import _dejavu_glyph

        g = _dejavu_glyph("▲", 30, 24, 6, 128)
        assert g is not None and g.lit

    def test_dejavu_also_lacking_returns_none(self):
        # A rare CJK ideograph DejaVu doesn't cover → still None (→ ? later).
        font = load_hires_font(_INTER, 30)
        assert font.resolve_glyph("鿿") is None
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run --no-sync python -m pytest tests/test_hires_loader_ladder.py -q -k DejaVu`
Expected: FAIL — `_dejavu_glyph` undefined; ▲ still None.

- [ ] **Step 4: Implement the DejaVu rung**

```python
_DEJAVU_PATH = Path(__file__).parent.parent / "assets" / "DejaVuSans.ttf"


@functools.lru_cache(maxsize=_FONT_CACHE_MAXSIZE)
def _dejavu_pil(size: int) -> Any:
    """DejaVu Sans PIL font at `size`, or None if the asset is missing
    (degrade gracefully — a stripped install just can't use rung 2)."""
    try:
        return ImageFont.truetype(str(_DEJAVU_PATH), size)
    except OSError:
        logging.getLogger(__name__).warning(
            "DejaVu fallback font unavailable at %s — glyph ladder rung 2 "
            "disabled",
            _DEJAVU_PATH,
        )
        return None


@functools.lru_cache(maxsize=2048)
def _dejavu_glyph(
    ch: str, size: int, ascent: int, descent: int, threshold: int
) -> HiresGlyph | None:
    """Rasterize `ch` from DejaVu at the chosen font's metrics, or None if
    DejaVu also lacks it. Cached per (ch, size, ...) across all fonts."""
    pil = _dejavu_pil(size)
    if pil is None:
        return None
    d_ascent, d_descent = pil.getmetrics()
    notdef = _rasterize_glyph(pil, _NOTDEF_PROBE, d_ascent, d_descent, threshold)
    g = _rasterize_glyph(pil, ch, d_ascent, d_descent, threshold)
    if _is_notdef(g, notdef.lit):
        return None
    return g
```

In `resolve_glyph`, replace the two `return None` misses with a DejaVu
consult:

```python
            if _is_notdef(glyph, self.notdef_lit):
                self.glyphs[ch] = _MISSING
                # fall through to rung 2 below
                glyph = None
            else:
                self.glyphs[ch] = glyph
                return glyph
        if glyph is _MISSING:
            glyph = None
        if glyph is not None:
            return glyph
        # Rung 2: DejaVu fallback (real arrows/symbols the chosen font lacks).
        dj = _dejavu_glyph(ch, self.size, self.ascent, self.descent, self.threshold)
        if dj is not None:
            return dj
        return None
```

(Rewrite `resolve_glyph` cleanly rather than patching — the final shape:
dict hit-or-lazy → rung-1 result or None → rung-2 DejaVu → None. Keep the
`_MISSING` caching so a repeat miss doesn't re-rasterize the chosen font,
though DejaVu is re-consulted each call — its own `lru_cache` makes that a
dict hit.)

- [ ] **Step 5: Run + gates + commit**

Run the ladder tests + `tests/test_hires_loader.py` + lint gates → green.

```bash
git add src/led_ticker/fonts/hires_loader.py src/led_ticker/assets/DejaVuSans.ttf src/led_ticker/assets/DejaVuSans-LICENSE.txt THIRD_PARTY_NOTICES.md tests/test_hires_loader_ladder.py
git commit --no-verify -m "feat(fonts): DejaVu Sans fallback rung — real glyphs for chars the font lacks"
```

---

### Task 3: Font-aware 1:1 ASCII table (rung 3) + once-per-font WARN (rung 4)

**Files:**
- Modify: `src/led_ticker/fonts/hires_loader.py`
- Test: `tests/test_hires_loader_ladder.py` (append)

**Interfaces:**
- Consumes: Task 1–2 `resolve_glyph`.
- Produces: expanded `_ASCII_GLYPH_FALLBACKS` (all 1:1); `resolve_glyph` rung 3 (substitute char, resolved via rungs 1–2) then rung 4 (None + a once-per-font WARN via a module `set` guard).

- [ ] **Step 1: Write the failing tests** (append)

```python
class TestAsciiRungAndWarn:
    def test_emdash_font_lacks_falls_to_hyphen(self, monkeypatch, caplog):
        # Force a font that lacks '—' by stubbing DejaVu off, so the ASCII
        # table is the only rung that can save it.
        import led_ticker.fonts.hires_loader as m

        monkeypatch.setattr(m, "_dejavu_glyph", lambda *a, **k: None)
        font = load_hires_font(_INTER, 30)
        # Inter HAS the em-dash (EXTENDED_PUNCTUATION) — so this asserts the
        # table does NOT fire when the font has the real glyph.
        real = font.resolve_glyph("—")
        hyph = font.resolve_glyph("-")
        assert real is not None and real is not hyph  # kept the real em-dash

    def test_ascii_table_fires_only_on_miss(self, monkeypatch):
        import led_ticker.fonts.hires_loader as m

        # A char in the table whose real glyph the font lacks resolves to
        # the substitute. U+2212 MINUS: Inter lacks it, table maps → '-'.
        monkeypatch.setattr(m, "_dejavu_glyph", lambda *a, **k: None)
        font = load_hires_font(_INTER, 30)
        sub = font.resolve_glyph("−")
        hyph = font.resolve_glyph("-")
        assert sub is not None and sub is hyph  # rendered as the hyphen glyph

    def test_unrenderable_returns_none_and_warns_once(self, monkeypatch, caplog):
        import logging

        import led_ticker.fonts.hires_loader as m

        monkeypatch.setattr(m, "_dejavu_glyph", lambda *a, **k: None)
        m._WARNED_MISSING.clear()
        font = load_hires_font(_INTER, 30)
        with caplog.at_level(logging.WARNING):
            assert font.resolve_glyph("鿿") is None
            font.resolve_glyph("鿿")  # second call
        warns = [r for r in caplog.records if "9fff" in r.getMessage().lower()
                 or "鿿" in r.getMessage()]
        assert len(warns) == 1  # warned exactly once per (font, char)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --no-sync python -m pytest tests/test_hires_loader_ladder.py -q -k "Ascii"`
Expected: FAIL — `_WARNED_MISSING` undefined; U+2212 currently maps via the OLD in-resolve table but the new font-aware ordering + warn don't exist.

- [ ] **Step 3: Expand the table + add rungs 3-4**

Grow `_ASCII_GLYPH_FALLBACKS` (all single-char; multi-char deferred per the plan's scope note):

```python
# 1:1 ASCII look-alikes for typographic codepoints, applied ONLY when the
# chosen font AND DejaVu both lack the real glyph (rung 3). Single-char only:
# multi-char expansions (½→"1/2") are deferred — they'd desync the per-char
# colour/token index. Extend as new formatter glyphs surface.
_ASCII_GLYPH_FALLBACKS: dict[str, str] = {
    "−": "-",  # MINUS SIGN → HYPHEN-MINUS
    "—": "-",  # EM DASH
    "–": "-",  # EN DASH
    "‐": "-",  # HYPHEN
    "‘": "'",  # LEFT SINGLE QUOTE
    "’": "'",  # RIGHT SINGLE QUOTE
    "“": '"',  # LEFT DOUBLE QUOTE
    "”": '"',  # RIGHT DOUBLE QUOTE
    "′": "'",  # PRIME
    "″": '"',  # DOUBLE PRIME
    "×": "x",  # MULTIPLICATION SIGN
    "÷": "/",  # DIVISION SIGN
    " ": " ",  # NO-BREAK SPACE
    "•": ".",  # BULLET
}

# Once-per-(font, char) WARN guard for rung 4 — tofu is never SILENT.
_WARNED_MISSING: set[tuple[str, str]] = set()
```

Finalize `resolve_glyph` (full clean shape, replacing the Task-2 patch):

```python
    def resolve_glyph(self, ch: str) -> HiresGlyph | None:
        """Resolution ladder for `ch`:
        1. this font (cached dict → lazily rasterize; notdef/empty ⇒ miss),
        2. bundled DejaVu Sans (real arrows/symbols the font lacks),
        3. a 1:1 ASCII look-alike (only when 1-2 miss),
        4. None (caller draws '?') + a once-per-font WARN.
        Draw and measure both call this, so a miss advances identically."""
        g = self.glyphs.get(ch)
        if g is None and self.pil_font is not None and ch:
            g = _rasterize_glyph(
                self.pil_font, ch, self.ascent, self.descent, self.threshold
            )
            g = None if _is_notdef(g, self.notdef_lit) else g
            self.glyphs[ch] = g if g is not None else _MISSING
        elif g is _MISSING:
            g = None
        if g is not None:
            return g
        # Rung 2: DejaVu.
        dj = _dejavu_glyph(ch, self.size, self.ascent, self.descent, self.threshold)
        if dj is not None:
            return dj
        # Rung 3: 1:1 ASCII look-alike (resolve the substitute via 1-2).
        alt = _ASCII_GLYPH_FALLBACKS.get(ch)
        if alt is not None and alt != ch:
            sub = self.resolve_glyph(alt)
            if sub is not None:
                return sub
        # Rung 4: nothing — warn once, let the caller draw '?'.
        key = (self.name, ch)
        if key not in _WARNED_MISSING:
            _WARNED_MISSING.add(key)
            logging.getLogger(__name__).warning(
                "font %r has no glyph for %r (U+%04X) and no fallback — "
                "it will render as '?'",
                self.name, ch, ord(ch) if len(ch) == 1 else 0,
            )
        return None
```

Ensure `import logging` is present at the top of the module.

- [ ] **Step 4: Run the FULL emoji/text battery**

Run: `uv run --no-sync python -m pytest tests/ -q -k "hires or font or text or width or token or two_row or message or stock"`
Expected: all green — the existing `test_hires_minus` (U+2212→-) still passes (now via rung 3), token-alignment and width tests unaffected (resolution unchanged for present chars; misses now resolve BETTER, never worse). Lint gates.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/fonts/hires_loader.py tests/test_hires_loader_ladder.py
git commit --no-verify -m "feat(fonts): 1:1 ASCII fallback rung + once-per-font miss warning (ladder rungs 3-4)"
```

---

### Task 4: Validate rule — preflight the ladder

**Files:**
- Modify: `src/led_ticker/validate.py`
- Test: `tests/test_validate.py` (append)

**Interfaces:**
- Consumes: `resolve_font` (per-section font), `HiresFont.resolve_glyph`, the `pixel_emoji` emoji scanners to EXCLUDE emoji.
- Produces: `_check_glyph_coverage(config) -> list[ValidationIssue]`, registered like rule 67; next free rule number. Reports rung-3 (substituted) and rung-4 (`?`) chars; silent on rungs 1-2.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_validate.py`, using that file's config-building + `_run_validate` helpers — read a neighboring rule's tests first for the exact idioms)

```python
class TestGlyphCoverage:
    def test_unrenderable_char_warns(self, tmp_path):
        # U+9FFF (no glyph anywhere) in a hires message → warning it will '?'.
        cfg = _write_config(tmp_path, '''
            [display]
            rows = 32
            cols = 64
            chain_length = 8
            default_scale = 4
            [[playlist.section]]
            mode = "slideshow"
            [[playlist.section.widget]]
            type = "message"
            text = "price 鿿 up"
            font = "Inter-Bold"
            font_size = 30
        ''')
        issues = _run_validate(cfg)
        assert any("9FFF" in i.message.upper() or "?" in i.message
                   for i in issues if i.severity == "warning")

    def test_ascii_substituted_char_warns(self, tmp_path):
        # U+2212 minus in Inter → substituted to '-' → informational warning.
        cfg = _write_config(tmp_path, '''
            [display]
            rows = 32
            cols = 64
            chain_length = 8
            default_scale = 4
            [[playlist.section]]
            mode = "slideshow"
            [[playlist.section.widget]]
            type = "message"
            text = "down −2%"
            font = "Inter-Bold"
            font_size = 30
        ''')
        issues = _run_validate(cfg)
        assert any("−" in i.message or "minus" in i.message.lower()
                   or "-" in i.message for i in issues if i.severity == "warning")

    def test_dejavu_covered_char_silent(self, tmp_path):
        # ▲ resolves via DejaVu → NO warning (good render, not a problem).
        cfg = _write_config(tmp_path, '''
            [display]
            rows = 32
            cols = 64
            chain_length = 8
            default_scale = 4
            [[playlist.section]]
            mode = "slideshow"
            [[playlist.section.widget]]
            type = "message"
            text = "▲ up"
            font = "Inter-Bold"
            font_size = 30
        ''')
        issues = _run_validate(cfg)
        assert not [i for i in issues if "▲" in i.message]

    def test_emoji_not_flagged(self, tmp_path):
        # 🚀 and :rocket: are font-bypassing — the rule must skip them.
        cfg = _write_config(tmp_path, '''
            [display]
            rows = 32
            cols = 64
            chain_length = 8
            default_scale = 4
            [[playlist.section]]
            mode = "slideshow"
            [[playlist.section.widget]]
            type = "message"
            text = "go \U0001F680 :rocket:"
            font = "Inter-Bold"
            font_size = 30
        ''')
        issues = _run_validate(cfg)
        assert not [i for i in issues if "rocket" in i.message.lower()
                    or "F680" in i.message.upper()]
```

- [ ] **Step 2: Run to verify failure** — the rule doesn't exist; no warnings emitted.

- [ ] **Step 3: Implement the rule** (model: `_check_hires_only_emoji_scale1`, rule 67; register in the same runner list; next free number)

```python
def _check_glyph_coverage(config: AppConfig) -> list[ValidationIssue]:
    """Rule N: warn when a config text char won't render in its font.

    Runs every text char through the SAME resolution ladder the renderer
    uses (`resolve_glyph`), EXCLUDING emoji (they bypass fonts). Reports
    only degraded rungs: a 1:1 ASCII substitution (informational) or an
    unrenderable '?' (the tofu the ladder couldn't save). Rungs 1-2 (the
    chosen font or DejaVu has a real glyph) are silent."""
    from led_ticker.fonts import resolve_font
    from led_ticker.fonts.hires_loader import _ASCII_GLYPH_FALLBACKS, HiresFont
    from led_ticker.pixel_emoji import EMOJI_PATTERN, _uemoji_runs

    issues: list[ValidationIssue] = []
    for s_idx, section in enumerate(config.sections):
        for w_idx, widget in enumerate(section.widgets):
            font_name = widget.font or _DEFAULT_HIRES_FONT  # per file's helper
            size = getattr(widget, "font_size", None) or _DEFAULT_SIZE
            try:
                font = resolve_font(font_name, size)
            except Exception:
                continue  # unknown font surfaced by another rule
            if not isinstance(font, HiresFont):
                pass  # BDF: resolve_glyph absent; fall through to CharacterWidth check below
            for field in ("text", "top_text", "bottom_text"):
                val = _widget_text(widget, field)  # per file's accessor idiom
                if not isinstance(val, str) or not val:
                    continue
                # Strip emoji spans (slug tokens + unicode-emoji runs).
                stripped = _strip_emoji_spans(val, EMOJI_PATTERN, _uemoji_runs)
                for ch in stripped:
                    if ch in " \t":
                        continue
                    verdict = _classify_glyph(font, ch)  # helper below
                    if verdict == "substituted":
                        issues.append(ValidationIssue(
                            severity="warning",
                            message=(f"section {s_idx+1} widget {w_idx+1}: "
                                     f"{ch!r} (U+{ord(ch):04X}) will render as "
                                     f"{_ASCII_GLYPH_FALLBACKS[ch]!r} — "
                                     f"{font_name} lacks the glyph"),
                            fix="Use the ASCII form directly, or a font with the glyph.",
                        ))
                    elif verdict == "tofu":
                        issues.append(ValidationIssue(
                            severity="warning",
                            message=(f"section {s_idx+1} widget {w_idx+1}: "
                                     f"{ch!r} (U+{ord(ch):04X}) will render as "
                                     f"'?' — no glyph in {font_name}, DejaVu, "
                                     f"or the fallback table"),
                            fix="Remove the character or use a font that covers it.",
                        ))
    return issues
```

Add the two helpers (adapt to the file's `HiresFont` import + BDF font
shape). `_classify_glyph` distinguishes the four rungs using `resolve_glyph`
plus a peek at whether rung-1/2 produced the result vs the ASCII table:

```python
def _classify_glyph(font, ch: str) -> str:
    """Return 'ok' (rung 1-2), 'substituted' (rung 3), or 'tofu' (rung 4)."""
    from led_ticker.fonts.hires_loader import _ASCII_GLYPH_FALLBACKS, HiresFont

    if not isinstance(font, HiresFont):
        # BDF: a char is 'tofu' if the BDF font has no width/glyph for it.
        return "ok" if font.CharacterWidth(ord(ch)) > 0 else "tofu"
    # Temporarily bypass the ASCII table to see if rung 1-2 alone renders.
    saved = _ASCII_GLYPH_FALLBACKS.pop(ch, _SENTINEL)
    try:
        rung12 = font.resolve_glyph(ch)
    finally:
        if saved is not _SENTINEL:
            _ASCII_GLYPH_FALLBACKS[ch] = saved
    if rung12 is not None:
        return "ok"
    return "substituted" if saved is not _SENTINEL and saved != ch else "tofu"
```

(NOTE: mutating the module dict under validate is single-threaded and
restored in `finally`; if the reviewer prefers, refactor `resolve_glyph`
to take an optional `use_ascii_table=True` param instead — cleaner but
touches the hot path. Implementer's call; the param approach is
preferable if it doesn't complicate the render path.)

- [ ] **Step 4: Run** `uv run --no-sync python -m pytest tests/test_validate.py -q` + `-k validate` + lint gates → green.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit --no-verify -m "feat(validate): warn on non-rendering config text chars (glyph coverage)"
```

---

### Task 5: Historical-incident visual gate + docs (HARD STOP for James)

**Files:**
- Modify: `docs/site/src/content/docs/concepts/fonts.mdx` (glyph-coverage note)
- Scratch: `$CLAUDE_JOB_DIR/tmp/` gate config

- [ ] **Step 1: Full suite + gates**

Run: `uv run --no-sync python -m pytest tests/ -q` (only the known stale-worktree failure allowed) and the three lint gates. Record the pass count.

- [ ] **Step 2: The historical-incident battery GIF**

Write `$CLAUDE_JOB_DIR/tmp/tofu-gate.toml` — bigsign flat render shape (rows 64/cols 256/chain_length 1/default_scale 4), a `one_at_a_time` section (or several slideshow sections) with `font = "Inter-Bold"`, `font_size = 30`, each message a past incident: `"72° today"`, `"DOWN −1.98%"`, `"▲ UP ▼ DOWN"`, `"buy — now"`, `"cost × 3"`, `"Ω resistance"` (Ω, DejaVu-covered), and a control `"rare 鿿 char"` (should `?`). Render via `uv run --no-sync python tools/render_demo/render.py ... --duration 12`, extract a contact sheet, CHECK IT YOURSELF: every line legible (real glyph or clean look-alike), the ONLY `?` is the U+9FFF control.

- [ ] **Step 3: Docs note**

In `docs/site/src/content/docs/concepts/fonts.mdx`, add a short "Glyph coverage" subsection: any character renders if the chosen font has it; otherwise the sign falls back to a bundled font (DejaVu Sans) for symbols/arrows the font lacks, then to a look-alike ASCII character (a `−` shows as `-`), and only shows `?` for a truly unrenderable character — which `led-ticker validate` warns about ahead of deploy. Note emoji use their own sprite path (link to the emoji page). Prettier + `pnpm run build` (72 pages, exit 0).

- [ ] **Step 4: HARD STOP — send the GIF to James**

Send the contact sheet + GIF with the pass count. Confirm every historical incident renders legibly. Do NOT open the PR until approved.

- [ ] **Step 5 (post-gate): Commit docs**

```bash
git add docs/site/src/content/docs/concepts/fonts.mdx
git commit --no-verify -m "docs(fonts): glyph-coverage ladder note"
```

---

### Task 6 (post-gate): PR

- [ ] **Step 1:** Push `glyph-ladder-spec`; `gh pr create`. Body: the two failure modes fixed, the four-rung ladder, the scope corrections (hires-only render ladder + BDF-inclusive validate; 1:1-only rung 3 with multi-char deferred and WHY), DejaVu vendoring + license, the historical-incident GIF, and the perf note (lazy rasterize + `_MISSING`/DejaVu caches mean steady-state is dict lookups). Note: no plugin changes needed (plugins inherit the ladder through core's `resolve_glyph`); release = core minor.
- [ ] **Step 2:** Watch `gh pr checks --watch`. STOP — James merges + cuts the release.
