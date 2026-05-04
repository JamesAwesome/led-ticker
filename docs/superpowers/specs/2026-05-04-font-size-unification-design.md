# Font-size unification — design

**Status:** Draft for review
**Date:** 2026-05-04
**Scope:** Image widgets (`gif`, `image`) — single-row text-overlay path

## Background

led-ticker has two font systems with two different size knobs:

- **BDF** (legacy bitmap fonts): `text_scale: int = 1` — multiplier on the cell height (e.g. 6×12 + `text_scale=4` → 48 real px tall on bigsign via `ScaledCanvas` block-expansion).
- **HiresFont** (TTF/OTF, recent): `font_size: int` — absolute real-pixel target passed to the Pillow rasterizer.

Two knobs for one user concept ("how tall is my text") creates persistent
TOML friction. The recent `bd61140` ("single-row wrap fires on
`_logical_scale` too") introduced an additional subtle rule: BDF text on
bigsign at default `text_scale=1` now auto-block-expands to panel scale,
which broke a working pillarbox layout (PIKACHU section in
`config.gif_text.example.toml`).

The user's framing: *"the config is feeling too confusing."*

## Goals

1. **One TOML knob** for text size across font types: `font_size: int`, real pixels.
2. **Smart default on bigsign for BDF** preserved (no regression vs. current behavior; just renamed).
3. **HiresFont path unchanged** in user-visible behavior (`font_size` already its native vocabulary).
4. **Loud migration error** for stale configs that still use `text_scale` — caught at config-load, not at first paint.

## Non-goals

- **Title widgets, TickerMessage, TwoRowMessage**: not affected. `text_scale`
  exists only on `_BaseImageWidget` per a grep audit. Other widgets already
  use `font` + `font_size` uniformly.
- **Internal font-type Protocol unification**: nine `isinstance(font, HiresFont)`
  branches in helpers stay as-is. The Protocol refactor was assessed in the
  preceding thread and deferred until a third font type appears.
- **Panel-relative size syntax** (e.g. `font_size = "half"` or `0.5`): considered
  and dropped. `font_size: int` real px is the only accepted form.
- **HiresFont smart default**: HiresFont still requires explicit `font_size`
  at `_build_widget` time (the rasterizer needs a real-px target at
  construction). Smart default applies to BDF only.

## Architecture

### One knob, real pixels, smart default for BDF

- `_BaseImageWidget` exposes a single user-facing size knob: `font_size: int | None = None` (real pixels).
- Internally, the widget computes a `_block_scale: int` from `(font, font_size, _logical_scale)` at first paint. For BDF that drives the `ScaledCanvas` wrap; for HiresFont it's always 1 (the rasterizer handled size at construction).
- The `_block_scale` mechanism replaces the old `effective_scale = max(text_scale, _logical_scale)` formula.

### Smart default

- `font_size = None` (omitted in TOML) and font is BDF → resolved at first paint to `cell_h × _logical_scale`. On bigsign that gives 48 real px for FONT_DEFAULT (preserves bd61140 behavior); on small sign 12 real px (native).
- `font_size = None` and font is HiresFont → rejected at `_build_widget` time. Error message names the panel sizes ("e.g. 24 for bigsign, 12 for small sign").

### BDF size snapping

- BDF cells are bitmaps; arbitrary `font_size` values must snap to integer multiples of the cell height.
- Snap rule: round down to the largest multiple ≤ requested. `font_size = 25` with BDF 6×12 → renders at 24 real px (`_block_scale = 2`).
- Snap is silent (no warning logged). Documented in CLAUDE.md so users know.
- Floor: `font_size < cell_h` is rejected at paint time with a hint pointing to a smaller bundled BDF (5×8 if the user wants something smaller than 12).

## Components

### 1. Field rename — `_BaseImageWidget`

```python
# Before:
text_scale: int = attrs.field(default=1, kw_only=True)

# After:
font_size: int | None = attrs.field(default=None, kw_only=True)
```

The internal `text_scale` mechanism (block-expansion via `ScaledCanvas`)
doesn't disappear — it's how BDF block-scaling physically works. It's
demoted to an internal-only `_block_scale: int` computed at first paint.

### 2. New helper — `block_scale_for_font_size`

```python
# In src/led_ticker/fonts/__init__.py
def block_scale_for_font_size(font: Font, font_size: int) -> int:
    """For BDF: round-down font_size to nearest integer multiple of
    cell_h. For HiresFont: returns 1 (rasterizer handled size at
    construction). Floor of 1; raises if font_size < cell_h for BDF."""
```

Lives next to `font_line_height_logical` — same kind of polymorphic
dispatch on font type.

### 3. Default-derivation method — `_resolved_font_size`

```python
# In _BaseImageWidget
def _resolved_font_size(self) -> int:
    """Return the effective font_size. If user-set, returns as-is.
    If None, BDF gets cell_h × _logical_scale; HiresFont errors
    (must be explicit at construction)."""
```

Called from `_play_with_text` once per visit (cached in a local;
lifecycle-stable across ticks).

### 4. `_play_with_text` rewrite

The single-row playback method's wrap-scale resolution changes:

```python
# Before (post-bd61140):
effective_scale = self.text_scale if self.text_scale > 1 else self._logical_scale
text_canvas = self._wrap_for_text(canvas, effective_scale)

# After:
font_size = self._resolved_font_size()
block_scale = block_scale_for_font_size(self.font, font_size)
text_canvas = self._wrap_for_text(canvas, block_scale)
```

`_wrap_for_text` is unchanged (already extracted from the punch-list pass).

### 5. Validation updates

In `_validate_common`:

- Drop `text_scale >= 1` check.
- Drop `text_scale > 1 with HiresFont` rejection (no longer makes sense — HiresFont's natural unit is `font_size`).
- Add: `font_size > 0` if set.
- Add: `font_size` rejected when `bottom_text` is set (use `top_font_size` / `bottom_font_size` instead).
- Two-row already validates `text_scale > 1` separately; that branch is dropped (the per-row knobs were never in `text_scale` semantics anyway).

In `_play_with_text` after default resolution:

- BDF + `font_size < cell_h` → `ValueError("font_size=N below cell height M; for smaller text use BDF '5x8' or HiresFont with font_size=N")`.
- `font_size > panel_h_real` → existing rows-fit check, reworded to reference resolved font_size.

In `_build_widget` (`app.py`):

- TOML `text_scale = N` → raise migration error verbatim.
- HiresFont without `font_size` → raise with the "(e.g. 24 for bigsign, 12 for small)" hint.

### 6. Error messages — verbatim

```
text_scale = N (legacy):
  "text_scale removed in favor of font_size (real pixels). Migrate:
   font_size = N × cell_h_of_your_font. For BDF 6×12: font_size = N × 12.
   For BDF 5×8: font_size = N × 8."

font_size = 0 or negative:
  "font_size must be > 0; got {value!r}."

BDF font_size below cell_h:
  "font_size={value} below cell height {cell_h} for {font_name}. For
   smaller text use BDF '5x8' (cell_h=8) or a HiresFont."

HiresFont missing font_size at _build_widget:
  "HiresFont '{name}' requires font_size (real pixels). e.g.
   font_size = 24 for bigsign, font_size = 12 for small sign."

font_size in two-row mode:
  "font_size is the single-row knob; in two-row mode use top_font_size
   and bottom_font_size."
```

## Data flow

```
TOML  →  app._build_widget  →  widget construction  →  first paint
─────────────────────────────────────────────────────────────────────
font = "Inter-Bold"     resolve_font("Inter-Bold", 24)   HiresFont stored
font_size = 24          → HiresFont(size=24)             font_size=24 stored
                                                         _block_scale = 1 at paint

font = "6x12"           resolve_font("6x12", None)       BDF stored
(no font_size)          → BDF cell                       font_size=None stored
                                                         At first paint:
                                                         _resolved_font_size = 12 × _logical_scale
                                                         _block_scale = font_size // 12

font = "6x12"           resolve_font("6x12", None)       BDF stored
font_size = 24          → BDF cell                       font_size=24 stored
                                                         At first paint:
                                                         _block_scale = 24 // 12 = 2

font = "Inter-Bold"     ERROR: HiresFont requires        (refused before widget)
(no font_size)          font_size

text_scale = 4 (any)    ERROR: text_scale removed,       (refused at config load)
                        migration formula given
```

## Migration

Single PR contains all migration steps:

1. **Code changes** — `_image_base.py`, `app.py`, `fonts/__init__.py`, `gif.py` + `still.py` docstrings.
2. **In-tree configs** — mechanical migration of `text_scale = N` to `font_size = N × cell_h`. Affected files (audited via grep):
   - `config/config.gif_text.example.toml` (7 occurrences)
   - `config/config.gif_test.example.toml` (5 occurrences)
   - `config/config.image_test.example.toml` (5 occurrences)
3. **CLAUDE.md** — drop the bd61140 paragraph's `effective_scale` formula, replace with `font_size` rule. Add migration formula. Update tripwire references.
4. **User's bigsign Pi `config.toml`** — out of repo. User does `git pull` and runs the same search/replace before next deploy. Migration error catches anything missed.

The cell heights for migration:

- BDF FONT_DEFAULT (6×12): cell_h = 12
- BDF FONT_SMALL (5×8): cell_h = 8

Audit script for the migration:

```bash
grep -B5 'text_scale' config/*.toml
# For each match, check what `font` is set to nearby; multiply by cell_h.
```

## Error handling

Three classes, summarized:

1. **Migration errors** (loud, at config load) — stale `text_scale` raises with migration formula. Catches at startup.
2. **Construction-time validation** (in `__attrs_post_init__`) — `font_size > 0`, two-row rejection, HiresFont-requires-explicit.
3. **Paint-time validation** (in `_play_with_text`) — BDF below cell_h, font exceeds panel_h_real.

## Testing

### Unit — `block_scale_for_font_size`

- BDF exact multiples: `12 → 1`, `24 → 2`, `48 → 4`.
- BDF round-down: `25 → 2`, `47 → 3`.
- BDF below floor: `11` raises with the "smaller font" hint.
- HiresFont: any positive `font_size` returns `1`.

### Construction validation

- `_DummyImage(font_size=0)` raises with "must be > 0".
- `_DummyImage(font_size=-5)` raises (same).
- `_DummyImage(font_size=24, top_text="x", bottom_text="y")` raises with "two-row" hint.
- `_DummyImage(font_size=None)` constructs (None is the smart-default sentinel).

### Migration

- `_build_widget({"type": "gif", "text_scale": 4, ...})` raises with the verbatim migration message including the formula.
- `_build_widget({"type": "gif", "font": "Inter-Bold"})` (no `font_size`) raises with the HiresFont hint.

### Behavioral

- Smart-default tripwire: `_DummyImage(font=FONT_DEFAULT)`, set `_logical_scale=4`; assert `_resolved_font_size() == 48`.
- Smart-default small sign: same widget, `_logical_scale=1`; assert `_resolved_font_size() == 12`.
- Existing `TestSingleRowLogicalScaleWrap` becomes `TestSingleRowFontSize` — same three assertions, new vocabulary:
  - bigsign with `font_size=None` → text_canvas IS a `ScaledCanvas` wrapper.
  - small sign with `font_size=None` → no wrap.
  - explicit `font_size=24` BDF on bigsign → wrapper at scale=2 (not 4).

### Visual / integration

No panel-rendering test harness. Proof points:

- The migrated `config.gif_text.example.toml` PIKACHU section already renders correctly on hardware (shipped in 68e2360 with `font = "Inter-Bold", font_size = 24`).
- The other migrated example configs (`gif_test`, `image_test`) get a manual hardware sanity check before declaring done.

## Open questions

None. The HiresFont smart-default decision (require explicit) is the only place we deviated from the simplest user model, and the alternative (re-rasterize at first paint) is materially more work for a marginal user-experience gain.

## Appendix — files touched

```
src/led_ticker/widgets/_image_base.py
src/led_ticker/widgets/gif.py            (docstring schema only)
src/led_ticker/widgets/still.py          (docstring schema only)
src/led_ticker/app.py                    (_build_widget plumbing)
src/led_ticker/fonts/__init__.py         (block_scale_for_font_size helper)
config/config.gif_text.example.toml
config/config.gif_test.example.toml
config/config.image_test.example.toml
tests/test_widgets/test_image_base.py    (renamed test class, new tests)
tests/test_fonts.py                      (new TestBlockScaleForFontSize class)
tests/test_app.py                        (new TestFontSizeMigration class)
CLAUDE.md
```
