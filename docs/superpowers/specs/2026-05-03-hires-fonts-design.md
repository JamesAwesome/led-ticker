# Hi-res Fonts — Design

**Date:** 2026-05-03
**Status:** Approved, ready for implementation plan

## Goal

Add hi-res font support so widgets can render text at native physical pixels (~24-40px on the bigsign) instead of the current path where BDF bitmap fonts (6×12 or 5×8) get expanded 4× by `ScaledCanvas` into chunky 4×4 blocks. Two concrete fonts in scope:

1. **Beloved Sans** — Adobe Fonts (Typekit). MoonBunny brand font. License-incompatible with public-repo bundling, so the user drops the `.otf` into a config dir.
2. **Inter** — open-source (OFL). Bundled in the package as the universal hi-res default.

## Why now

The bigsign has 256×64 native pixels. Today, text glyphs are 12 logical rows tall, expanded to 48 real rows via 4×4 block expansion. Letters are readable but blocky — fine for ticker info, wrong for brand text. A 32-pixel-tall TTF rendered at native resolution gives ~10× more curve approximation per glyph and reads as proper typography on the panel.

## Scope (decided in brainstorming)

**In scope:**
- Hi-res font infrastructure: loader, glyph cache, render dispatch, widget integration.
- Two concrete fonts: Inter (bundled) + Beloved Sans (user-supplied).
- Per-widget TOML knobs: `font` (string name) + `font_size` (int pixel height).
- Emoji integration: `:slug:` patterns continue to render correctly when text uses a hi-res font.
- Backwards compat: any widget without `font`/`font_size` keeps existing BDF behavior on both signs.

**Out of scope:**
- Section-level `font` defaults that propagate to widgets (mirror of bg_color pattern). YAGNI for v1.
- Anti-aliased rendering. Binarize at 50% intensity for a clean pixel-art look. AA is a follow-up if needed.
- Auto-sizing based on widget context. User picks `font_size` explicitly.
- Hi-res rendering on the small sign (16-row panel). User can configure it but text will overflow vertically; user's responsibility.
- Font weight/style switching (regular vs bold). Treat each weight as a separate registry entry (`"inter-bold"`, `"inter-regular"`).
- Caching font glyph data to disk. In-memory `@functools.cache` only.

## Resolution model

User opt-in per widget via TOML. The `font` field is a string name resolved through this priority chain:

1. `config/fonts/{name}.{otf,ttf}` (user-supplied, gitignored).
2. `src/led_ticker/fonts/hires/{name}.{otf,ttf}` (bundled).
3. BDF registry: `{ "6x12": FONT_DEFAULT, "5x8": FONT_SMALL }`.
4. Raise `UnknownFontError` listing all available names.

Examples:
- `font = "beloved-sans"` → looks up Beloved Sans in `config/fonts/`. User must have downloaded the .otf there.
- `font = "inter"` → bundled hi-res Inter Regular.
- `font = "inter-bold"` → bundled hi-res Inter Bold.
- `font = "6x12"` → existing BDF default. Same as not setting `font`.
- (no `font` key) → widget's class default (`FONT_DEFAULT` for most widgets).

## Architecture

### File layout

```
src/led_ticker/fonts/
  hires/
    inter-regular.otf      # NEW — bundled OFL font
    inter-bold.otf         # NEW — bundled OFL font
  hires_loader.py          # NEW — loader, glyph rasterization, cache
  __init__.py              # extends with resolve_font(name, size)
  bdf_parser.py            # existing — unchanged
  5x8.bdf, 6x10.bdf, ...   # existing BDFs — unchanged

config/
  fonts/                   # NEW — gitignored, user-supplied
    beloved-sans.otf       # user drops their licensed file
```

### `HiresFont` dataclass and glyph cache

```python
@dataclass(frozen=True)
class HiresGlyph:
    width: int               # bbox width
    height: int              # bbox height
    advance: int             # x-advance to next char
    bearing_x: int           # left-side bearing
    bearing_y: int           # top to baseline
    lit: tuple[tuple[int, int], ...]   # (dx, dy) lit pixels post-threshold

@dataclass(frozen=True)
class HiresFont:
    name: str
    size: int                # configured pixel height
    ascent: int
    descent: int
    line_height: int
    glyphs: dict[str, HiresGlyph]
```

### Loader

```python
# src/led_ticker/fonts/hires_loader.py

THRESHOLD: int = 128  # 50% of 0-255

@functools.cache
def load_hires_font(name: str, size: int) -> HiresFont | None:
    """Returns None if name not found in any hi-res dir."""
    path = _find_font_path(name)
    if path is None:
        return None
    return _rasterize(path, size, name)

def _find_font_path(name: str) -> Path | None:
    """Scan config/fonts/ first, then bundled hires/, return first match."""
    for ext in (".otf", ".ttf"):
        for base in (USER_FONT_DIR, BUNDLED_HIRES_DIR):
            candidate = base / f"{name}{ext}"
            if candidate.exists():
                return candidate
    return None

def _rasterize(path: Path, size: int, name: str) -> HiresFont:
    pil_font = ImageFont.truetype(str(path), size)
    ascent, descent = pil_font.getmetrics()
    glyphs: dict[str, HiresGlyph] = {}
    chars = string.printable + EXTENDED_LATIN  # see below
    for ch in chars:
        glyphs[ch] = _rasterize_glyph(pil_font, ch)
    return HiresFont(
        name=name,
        size=size,
        ascent=ascent,
        descent=descent,
        line_height=ascent + descent,
        glyphs=glyphs,
    )

def _rasterize_glyph(pil_font, ch: str) -> HiresGlyph:
    bbox = pil_font.getbbox(ch)  # (x0, y0, x1, y1)
    width = max(1, bbox[2] - bbox[0])
    height = max(1, bbox[3] - bbox[1])
    img = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(img)
    draw.text((-bbox[0], -bbox[1]), ch, font=pil_font, fill=255)
    pixels = img.load()
    lit = tuple(
        (dx, dy)
        for dy in range(height)
        for dx in range(width)
        if pixels[dx, dy] >= THRESHOLD
    )
    advance = int(pil_font.getlength(ch))
    return HiresGlyph(
        width=width,
        height=height,
        advance=advance,
        bearing_x=bbox[0],
        bearing_y=-bbox[1],
        lit=lit,
    )
```

`@functools.cache` keyed on `(name, size)` — the same font at different sizes gets separate cache entries. Glyphs are immutable tuples for cache safety.

`EXTENDED_LATIN` is a module-level constant with the most common Latin-1 accented characters (`"àáâãäåæçèéêëìíîïñòóôõöøùúûüýÿÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝŸ"`). Adequate for English + most European feeds. Other characters fall back to the `'?'` glyph at render time.

`list_available_fonts()` walks both `config/fonts/` and `src/led_ticker/fonts/hires/`, plus the BDF aliases, returning a sorted list of names — used in the `UnknownFontError` message.

### Resolver in `fonts/__init__.py`

```python
class UnknownFontError(ValueError):
    pass

def resolve_font(name: str, size: int = 24) -> Font | HiresFont:
    """TOML name → font object. Tries hi-res first, falls back to BDF."""
    hires = load_hires_font(name, size)
    if hires is not None:
        return hires
    bdf_alias = {"6x12": FONT_DEFAULT, "5x8": FONT_SMALL}
    if name in bdf_alias:
        return bdf_alias[name]
    available = list_available_fonts()  # walks both dirs + bdf aliases
    raise UnknownFontError(
        f"unknown font {name!r}; available: {available}"
    )
```

### Render dispatch

Extend `text_render.draw_text`:

```python
def draw_text(canvas, font, x, y, color, text):
    if isinstance(font, HiresFont):
        return _draw_hires_text(canvas, font, x, y, color, text)
    if isinstance(canvas, ScaledCanvas):
        bdf = get_bdf_for(font)
        return canvas.draw_bdf_text(bdf, x, y, color, text)
    return _graphics.DrawText(canvas, font, x, y, color, text)


def _draw_hires_text(canvas, font, x, y, color, text):
    """Paint hi-res glyphs at native physical resolution.

    `(x, y)` are LOGICAL coords (matching BDF behavior). The renderer
    multiplies by the canvas's scale to get real coords, then paints
    glyph pixels directly to the unwrapped real canvas — bypasses the
    wrapper's 4×4 block expansion.
    """
    real = unwrap_to_real(canvas)
    scale = getattr(canvas, "scale", 1)
    real_baseline_y = y * scale + getattr(canvas, "_y_offset", 0)
    real_x = x * scale
    set_px = real.SetPixel
    r, g, b = color.red, color.green, color.blue
    cursor_x = real_x
    fallback = font.glyphs.get("?")
    for ch in text:
        glyph = font.glyphs.get(ch, fallback)
        if glyph is None:
            continue
        gx0 = cursor_x + glyph.bearing_x
        gy0 = real_baseline_y - glyph.bearing_y
        for dx, dy in glyph.lit:
            px, py = gx0 + dx, gy0 + dy
            if 0 <= px < real.width and 0 <= py < real.height:
                set_px(px, py, r, g, b)
        cursor_x += glyph.advance
    return cursor_x - real_x
```

### Coordinate-system contract

- Widgets pass `(x, y)` in **logical** coords as today. Logical baseline_y is typically 12 (10 ascent + 2 descent for FONT_DEFAULT).
- BDF path: ScaledCanvas's `draw_bdf_text` multiplies by scale internally, painting block-expanded.
- Hi-res path: `_draw_hires_text` multiplies by scale internally, painting at native pixels.
- The hi-res font's pixel size (`HiresFont.size`) is in **real** pixels. User sets `font_size` to fit the panel: ~32-40 for headlines on the bigsign, ~24 for body. Picking too tall a font_size will overflow the panel vertically — user's responsibility.

### Widget integration

Widget code is **unchanged**. The `Font` type alias in `_types.py` widens conceptually:

```python
# _types.py
Font = Any  # was: just C font; now polymorphic — BDF Font OR HiresFont
```

Widgets store `font: Font` (or `Font | HiresFont` if a stricter annotation is desired). All call sites that consume `font` go through helpers that dispatch on type:

- `text_render.draw_text(canvas, font, ...)` — covered above.
- `drawing.get_text_width(font, text)` — extend with `isinstance(font, HiresFont)` branch summing glyph advances.
- `pixel_emoji.draw_with_emoji(canvas, font, ...)` — already accepts arbitrary `font`. Internally uses `draw_text` for plain segments; that becomes polymorphic for free. The `emoji_y` parameter (vertical anchor for the 8x8 sprite) is currently computed by callers from BDF glyph height (12). For hi-res fonts, callers must compute `emoji_y` from `font.line_height` instead. Add a small helper `font_line_height(font: Font | HiresFont) -> int`.
- `pixel_emoji.measure_width(font, text, ...)` — same pattern; sum hi-res advances + emoji widths.

### App.py integration

`_build_widget` resolves the `font` field:

```python
font_name = widget_cfg.pop("font", None)
font_size = widget_cfg.pop("font_size", DEFAULT_HIRES_SIZE)  # e.g. 24
if font_name:
    widget_cfg["font"] = resolve_font(font_name, font_size)
# else: widget keeps its class default
```

`DEFAULT_HIRES_SIZE = 24` constant. Widgets with no `font` keyword in TOML get the class default (`FONT_DEFAULT` BDF).

## Validation and footguns

- `font_size` validation: `font_size >= 8`. Smaller risks unreadable glyphs.
- Hi-res font on a 16-row small sign panel — text will overflow vertically. Logged warning at config load if `font_size > panel_h - 2` and current display is the small sign.
- A widget with a hi-res font passing `(x, y)` logical coords assumes the text fits in the panel. If the user picks `font_size = 64` on a 64-tall panel, descenders will clip below. Documented; not validated.
- Unknown font name raises at config load time, not first paint. The error message lists all available font names from both dirs + BDF aliases.

## Testing strategy

**Per-component:**

1. **`tests/test_hires_font_loader.py` (new):**
   - User dir overrides bundled (drop fake `inter-regular.otf` in `tmp_path/config/fonts/`, monkeypatch the dir, assert it wins over bundled).
   - Unknown font name → `UnknownFontError` listing available names.
   - BDF fallback: `resolve_font("6x12")` returns `FONT_DEFAULT`.
   - `@functools.cache` identity: two `load_hires_font("inter", 32)` calls return same object.
   - `HiresFont` glyphs: `'A'` exists, `glyph.lit` non-empty, `glyph.advance > 0`.
   - Threshold sanity: 32px `'M'` has more lit pixels than 32px `'i'`.

2. **`tests/test_text_render.py` extension:**
   - `draw_text(canvas=Mock, font=HiresFont, ...)` → `_draw_hires_text` called, NOT BDF path.
   - `_draw_hires_text` paints to UNWRAPPED real canvas: wrap a `_StubCanvas` in `ScaledCanvas(scale=4)`, paint, assert lit pixels at real coords (not 4×4 block-expanded).
   - Out-of-bounds clipping: glyph spanning past `panel_w` doesn't crash.
   - Coord math: logical baseline_y=12 with scale=4 + 32-pixel tall font puts glyph top at real `y = 12*4 + offset - bearing_y`.

3. **`tests/test_drawing.py` extension:**
   - `get_text_width(HiresFont, "abc")` returns sum of glyph advances.
   - Empty string returns 0.
   - Unknown char falls back to `'?'` glyph advance.

4. **`tests/test_pixel_emoji.py` extension:**
   - `draw_with_emoji(font=HiresFont, text=":taco: hi")` paints both the sprite AND "hi" via hi-res renderer.
   - `measure_width(HiresFont, ":taco: hi")` = taco_width + advance("hi").
   - `emoji_y` derived from `font_line_height(font)` for hi-res, NOT hardcoded 12.

5. **`tests/test_app.py` extension:**
   - TOML `font = "inter"`, `font_size = 32` → `_build_widget` returns `TickerMessage` whose `.font` is a `HiresFont` instance.
   - TOML `font = "6x12"` → returns the existing BDF `FONT_DEFAULT`.
   - TOML `font = "totally-not-a-font"` → raises `UnknownFontError` at config load (not at paint time).

**Test fixtures:**
- Bundled `inter-regular.otf` is the test asset for real hi-res cases.
- Mocked user-dir tests use empty-file fixtures created at test setup with `tmp_path`.

**Estimated: ~20-25 new tests.**

**Not testing:**
- Visual fidelity on real hardware — manual bigsign smoke test.
- Beloved Sans rendering (asset isn't in repo, can't be CI-tested).

## Touch list (rough)

- `src/led_ticker/fonts/hires_loader.py` — new (loader, rasterizer, cache).
- `src/led_ticker/fonts/__init__.py` — add `resolve_font`, `list_available_fonts`, `UnknownFontError`.
- `src/led_ticker/fonts/hires/` — new dir with `inter-regular.otf` and `inter-bold.otf`.
- `config/fonts/` — new dir, gitignored. Empty initially; user drops Beloved Sans.
- `.gitignore` — add `config/fonts/`.
- `src/led_ticker/text_render.py` — `_draw_hires_text` + dispatch in `draw_text`.
- `src/led_ticker/drawing.py` — `get_text_width` dispatch on font type.
- `src/led_ticker/pixel_emoji.py` — `font_line_height` helper, `emoji_y` derivation update.
- `src/led_ticker/app.py` — `_build_widget` resolves `font` + `font_size` keys.
- `src/led_ticker/_types.py` — comment update on `Font` type alias.
- `pyproject.toml` — verify hatchling includes the new `fonts/hires/` dir in the wheel (default behavior should pick it up; verification step).
- Tests across 5 files (1 new, 4 extended).
- `CLAUDE.md` — document the hi-res font system + resolution chain.

Estimated 12-15 small commits + tests.
