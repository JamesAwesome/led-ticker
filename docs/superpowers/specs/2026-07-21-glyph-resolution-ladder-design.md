# The glyph resolution ladder — systematic tofu fix

**Date:** 2026-07-21
**Status:** approved (brainstorm with James)
**Relation:** workstream A of the two-spec sequence (the standard-emoji pack
was workstream B, shipped core 4.21.0–4.22.0). Emoji now bypass fonts
entirely, so this spec's surface is text glyphs only.

## Problem — the recorded tofu incidents

Every past incident is one of two failure modes against the hi-res font path:

1. **Charset-wall misses (loud `?`):** a formatter/config emits a char outside
   the eagerly-rasterized charset (`string.printable + EXTENDED_LATIN +
   EXTENDED_PUNCTUATION + GEOMETRIC_SHAPES + SYMBOLS`). `resolve_glyph` misses
   → the caller draws the `?` tofu. Fixed reactively each time by growing the
   charset (`SYMBOLS = "°"` for `72°→72?`) or the ASCII table
   (`_ASCII_GLYPH_FALLBACKS = {"−": "-"}` for `−1.98%`, PR #393).
2. **Notdef-box misses (silent):** the char IS attempted but the chosen FONT
   lacks the glyph, so PIL rasterizes the font's notdef box — which looks
   "present" and paints a tofu box (Inter lacks ▲▼ U+25B2/25BC; the em-dash /
   `IÄ` config pre-swaps existed to dodge this class before pasting).

Two consequences the fix must address: piecemeal charset growth never
converges, and config authors have no preflight signal — they discover tofu
on the panel.

## Design — a four-rung resolution ladder behind the existing seam

`HiresFont.resolve_glyph(ch)` is already the single seam all three glyph
consumers route through (`text_render.draw_text` + `draw_text_per_char`, and
`drawing.get_text_width`). Draw and measure MUST stay in lockstep on the
fallback (the #393 lesson: a `?`-vs-`-` advance delta skews right-aligned /
scrolling text). Everything below lives behind that one method so all three
inherit it unchanged.

### 1. Charset becomes an optimization, not a wall (fixes mode 1)

Keep eager rasterization of the common charset as a warm-start, but
`resolve_glyph` **lazily rasterizes an unseen char on first use** and caches
it (per `(font, size, threshold, ch)`, same cache discipline as today). Any
unicode char is now *attempted* — the charset string stops being a hard limit.
No more "add ½ to SYMBOLS" PRs; `GEOMETRIC_SHAPES`/`SYMBOLS`/`EXTENDED_*`
remain only as the warm-start list.

### 2. Notdef detection (fixes mode 2, the silent box)

At font load, rasterize a known-unassigned codepoint (e.g. U+E000 private-use
or U+FFFF) to capture the font's **notdef bitmap fingerprint** (store its
lit-pixel tuple, or a hash). Any rasterization — eager or lazy — whose bitmap
equals the notdef fingerprint is treated as **MISSING**, not present. This is
what makes ▲-in-Inter detectable instead of a silent box. (A font with no
notdef glyph rasterizes empty for missing chars; treat an all-empty bitmap for
a non-whitespace char as missing too.)

### 3. The ladder — per char, at resolve time

`resolve_glyph(ch)` returns the first that produces a real glyph:

1. **Chosen font** rasterizes `ch` to a non-notdef, non-empty bitmap → use it.
2. **Bundled DejaVu Sans** (fallback font, loaded once at the same pixel size)
   rasterizes `ch` to a real glyph → use it, cached. Arrows render as arrows,
   `−` as a real minus, `Ω` as a real omega. Metrics differ slightly from the
   chosen font, acceptable because this rung fires on symbols/punctuation, not
   body text.
3. **Expanded ASCII look-alike table** (`_ASCII_GLYPH_FALLBACKS`, grown from
   today's single `−→-`): dash family (—–‒→-), quote families (’‘→', ""→"),
   ellipsis (…→...), primes (′→', ″→"), math (×→x, ÷→/, −→-), NBSP→space, and
   MULTI-CHAR expansions where a single glyph has a clean ASCII spelling
   (½→"1/2", ¼→"1/4", ¾→"3/4"). The draw/measure paths already handle a
   fallback that is a STRING (per-char), so multi-char entries compose. The
   table is the rung for chars DejaVu also lacks OR where an ASCII form is
   preferable (a real `-` vs DejaVu's `−` is a wash; keep the table entry so
   BDF gets it too — see scope).
4. **`?` + once-per-font WARN** naming the char + codepoint. Tofu is still
   possible for a genuinely unrenderable char with no look-alike, but it is
   never SILENT — the log flags it, and validate (below) catches config-time
   cases.

Resolution result is cached per char so the ladder walk is paid once.

### 4. Validate rule — preflight the same ladder (fixes the trust gap)

A new `validate.py` rule loads each section's ACTUAL resolved font (it already
knows the font per widget) and runs every char of every config text field
(`text`/`top_text`/`bottom_text`/title text) through the SAME ladder,
**emoji excluded** (they bypass fonts — skip `:slug:` tokens and unicode-emoji
runs via the existing `pixel_emoji` scanners). It reports only DEGRADED rungs:

- Rung 3 (ASCII look-alike) → **warning**: "section N widget M: `—` will
  render as `-` in Inter-Bold (font lacks the glyph)".
- Rung 4 (`?`) → **warning**: "section N widget M: `Ω` will render as `?`
  (no glyph in Inter-Bold, DejaVu, or the fallback table)".
- Rungs 1–2 (chosen font or DejaVu has a real glyph) → **silent**: a DejaVu
  arrow is a good render, not a problem.

The em-dash / `IÄ` pre-swap era ends: authors see it at `led-ticker validate`.

### 5. Scope fences

- **BDF (smallsign)** keeps its pixel-font behavior. It gets rungs 3–4 through
  the shared seam (ASCII table, then `?` + WARN) but NOT rung 2 — a 5,800-glyph
  TTF can't sensibly mix into 8px pixel fonts. BDF misses that have no table
  entry stay `?`, and the validate rule reports them (it runs against whatever
  font the section resolves).
- **Runtime-formatted values** (stocks `−`, live token text) are fixed by the
  ladder at RENDER time, which validate cannot see — this is precisely why
  both layers (render ladder + validate) exist, not just one.
- **DejaVu Sans** bundles into the wheel (~700 KB). License to be confirmed
  at implementation from the vendored file's own LICENSE (DejaVu is under a
  permissive Bitstream-Vera-derived license, attribution-only, no
  copyleft) — record the exact text in `THIRD_PARTY_NOTICES.md`, same posture
  as the Noto entry. Loaded lazily on first rung-2 miss (not at import) so
  signs that never hit a gap don't pay for it. If DejaVu's license turns out
  awkward, the fallback candidate is GNU Unifont or Noto Sans (both
  broad-coverage, permissively licensed) — the rung is font-agnostic.

## Architecture / units

- `hires_loader.py` — `HiresFont` gains: notdef fingerprint captured at load;
  `resolve_glyph` reworked into the ladder (lazy chosen-font rasterize →
  DejaVu → table → None-signals-`?`); a module-level lazily-loaded DejaVu
  `PIL.ImageFont` at the requested size; the expanded `_ASCII_GLYPH_FALLBACKS`.
- `text_render.py` / `drawing.py` — UNCHANGED call sites; they already call
  `resolve_glyph` and already handle a string/multi-char fallback. The
  `or fallback` (`?`) at each site becomes the rung-4 sentinel path — verify
  the multi-char-fallback advance is summed correctly in both draw and measure
  (existing behavior for the current `−→-`; extend tests to multi-char).
- `validate.py` — new rule + its `_check_*` function, registered like rule 67;
  next free rule number.
- `assets/` — DejaVuSans.ttf (or a subsetted-but-broad copy) vendored.
- `THIRD_PARTY_NOTICES.md` — DejaVu entry.

## Tests & gates

- Notdef fingerprint: a font known to lack ▲ (Inter-Bold) rasterizes ▲ to the
  notdef bitmap → detected as missing (unit).
- Ladder order per rung: a char only DejaVu has (▲) → rung 2; a char nobody
  has but the table does (½) → rung 3 multi-char; a char nobody has (a rare
  CJK ideograph, or a PUA codepoint) → rung 4 `?` + one WARN.
- Draw/measure PARITY per rung, incl. multi-char (½→"1/2" must advance 3 glyph
  widths on BOTH sides — the F6 guard extended).
- Lazy rasterize + cache: an unseen char resolves once, second call cached;
  DejaVu font loads at most once per size.
- Validate rule scenarios: rung-3 warning, rung-4 warning, rung-1/2 silent,
  emoji skipped, BDF section reported.
- **Render-path GIF gate (the historical-incident battery):** one config in a
  font that lacks the glyphs, rendering `72°`, `−1.98%`, `▲ up ▼ down`, an
  em-dash line, `½ cup`, `Ω` — every one must render legibly (real glyph or
  clean look-alike), ZERO visible `?` except the deliberately-unrenderable
  control char. Bigsign; James's visual gate before merge.

## Non-goals

- No per-widget font-fallback config knob (the ladder is automatic; YAGNI).
- No BDF second-font rung.
- No emoji involvement (they bypass fonts; the validate rule skips them).
- No change to the public font-resolution API surface plugins use.
- Not touching the color/border/animation systems — glyph resolution only.

## Release shape

Core minor (new capability + bundled asset + validate rule). No plugin
changes required — plugins that draw text inherit the ladder through core's
`resolve_glyph`.
