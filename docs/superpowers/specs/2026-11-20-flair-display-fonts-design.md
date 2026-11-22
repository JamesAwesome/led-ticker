# Design: styled display fonts shipped in flair, with plugin-declared thresholds

2026-11-20. Closes effects-roadmap item 3 (text styling) by the font route
James chose: no rasterizer feature; ship fonts that already carry the look.
Lives untracked in the main checkout until the core worktree exists; it is
committed with the core PR. The evidence it needs is inlined below.

## Intent

Let anyone with the flair plugin installed write
`font = "flair.BungeeShade"` on a bigsign and get an outlined or 3D-shaded
message that renders correctly with no `font_threshold` in their config.
Today that takes finding an OFL font, copying it to `config/fonts/`, and
knowing that the default threshold of 128 shatters its hairline strokes.

## Goals

- Four fonts ship inside flair: Bungee Shade (3D cast shadow), Bungee
  Outline (double-line outline), Londrina Shadow (rounded, shadowed),
  Londrina Outline (rounded outline). SIL OFL, from google/fonts.
- Each registers with a default threshold of **45**. Leaving
  `font_threshold` unset gives 45; an explicit value still wins.
- Validate rule 2 (threshold mismatch within a family) sees the plugin
  default, so a config on defaults stays quiet.
- Core treats a plugin font as hi-res everywhere it already treats bundled
  and user fonts as hi-res (see "Core" below; today it does not).
- Flair README names each font with its look, working `font_size` range,
  and "bigsign only"; the docs-site fonts page points at them.

## Non-goals

- No `text_style` knob, outline/shadow rasterizer pass, or readable-raster
  unification. The gate found the font route sufficient.
- No scale-1 warning. All four are unreadable on 16 rows, but core has no
  notion of a font being scale-bound; README says bigsign-only.
- No look-based aliases (`flair.shade`). Names are the font file stems
  with the `-Regular` suffix dropped: `flair.BungeeShade`,
  `flair.BungeeOutline`, `flair.LondrinaShadow`, `flair.LondrinaOutline`.
  (My call: matches how bundled and user fonts are addressed, the README
  table maps name to look, and it leaves room for more fonts without a
  taxonomy.)
- Kumar One Outline (renders as a solid face through the thresholder) is
  not shipped.

## Anti-goals

- A user who writes `font = "flair.BungeeShade"` and nothing else, on a
  core at or above flair's floor, must not see dashed outlines. Approaches
  B and C below accept that failure; this design rejects it.
- Fonts must not be renamed or modified (OFL reserved-font-name clause).
  The registered *name* drops `-Regular`; the *file* keeps its full name.

## Constraints

- Plugins import only `led_ticker.plugin`; adding a kwarg to `api.font`
  is an additive API change, so `API_VERSION` goes `(1, 2)` → `(1, 3)`
  and tests pin `>=`.
- Core ships before flair (core-before-plugin). Flair's core floor moves
  to the release that carries the change. The pip floor cannot see a
  rolled-back image, so flair also probes `API_VERSION >= (1, 3)` at
  import; on an older core it registers the fonts with the two-arg form
  and logs ONE warning naming the threshold to set by hand (my call: the
  fonts still work with `font_threshold = 45`, and a stray `threshold=`
  kwarg on an old core would raise `TypeError` and drop the whole plugin).
- Worktree per branch; PRs open as drafts; `gh pr create` and every merge
  need James's go for that PR.
- Plugin load errors must be isolated: a bad threshold at registration
  raises `ValueError` inside `register(api)`, which the loader already
  logs and skips.

## Approaches considered

| | shape | trade-off |
|---|---|---|
| **A (chosen)** | `api.font(name, path, threshold=None)`; core keeps the value and `default_threshold` consults it | small core PR + release before flair; the font declares its own threshold, same reason core has the Inter table |
| B | fonts in flair, thresholds in README only | ships now, but every user hits dashed outlines first |
| C | B plus a flair `validate_config_warnings` nag when the threshold is unset | tells users, but nags forever and the fix stays manual |

James picked A on 2026-11-20.

## Evidence for the threshold and size ranges

Moonbunny, 2026-11-20 (preview-tee captures, bigsign 256×64 at scale 4):
at the spike's thresholds (Shade 128, Bungee Outline 60, Londrina Shadow
100) the hairline strokes were dashed; James saw it on the panel. At 60 /
45 / 60 / 45 every outline was continuous ("this looks great"). The local
rasterizer matched the sign's preview pixel for pixel, so the range check
below is local only.

Gap metric: lit pixels with at most one lit 8-neighbour ("dangling
ends"), string "Open 9-5 HELLO 123". Each font has a natural floor (its
own stroke ends); a rise above the floor is dashing.

| font | sizes | floor (t30) | t45 | t60 | t80+ |
|---|---|---|---|---|---|
| Bungee Shade | 40-56 | 23-32 | 23-32 | 23-48 (rises at 40-44) | 27-184 |
| Bungee Outline | 36-52 | 31-35 | 33-34 | 35-78 (rises at 36-44) | 65-375 |
| Londrina Shadow | 44-56 | 0-2 | 0-2 | 6-13 | 46-154 |
| Londrina Outline | 36-52 | 0-3 | 0-7 | 7-92 (rises at 36-44) | 136-325 |

45 holds the floor for all four across the whole range; 60 (the value
the sign passed at 48-52) dashes at the small end. Lit-pixel count grows
under 4% from 60 to 45, and a visual check at each range end at 45 shows
no fused strokes and the Shade face/shadow gap intact. Hence one default,
45, and the ranges above as the README's recommended `font_size`.

## Decided design

### Core (`led-ticker`, one PR)

- `PluginApi.font(self, name, path, threshold=None)`. `threshold` must be
  an `int` in 0-255 and not `bool` (same rule as `resolve_font`); anything
  else raises `ValueError` at registration. Stored in a new buffer
  `font_thresholds`, committed by the loader into
  `hires_loader._PLUGIN_THRESHOLDS: dict[str, int]` beside
  `_PLUGIN_FONTS`, cleared wherever `_PLUGIN_FONTS` is cleared.
- `hires_loader.default_threshold(name)`: plugin value if the name is in
  `_PLUGIN_THRESHOLDS`, else `DEFAULT_THRESHOLDS`, else `THRESHOLD`
  (membership checks, not truthiness; 0 is a legal threshold).
- **`list_available_hires_fonts()` includes `_PLUGIN_FONTS` keys.** Found
  today with a throwaway local plugin on current core: `_is_hires_font_name`
  (`app/coercion.py`) is `name in list_available_hires_fonts()`, which
  scans only the user and bundled dirs, so `demo.BungeeShade` was
  classified as *not* hi-res. The widget still built (`resolve_font`
  finds plugin fonts first) and validate still caught a missing size, but
  three gates silently skip plugin fonts: the friendly "requires
  font_size" hints (`factories.py` ~810 / ~855), the two-row image hi-res
  refusal (`factories.py` ~1227, validate rule 71's runtime mirror), and
  rules 63/64 (rotation / lens on scale 1). Fixing the listing fixes all
  of them and the "available:" list in `UnknownFontError`. Check
  `tests/test_validate_rotation_rules.py`, which reads the listing.
- `API_VERSION = (1, 3)`; the comment block above it gains "(1, 3)
  `api.font` accepts `threshold`; `default_threshold` honours it; plugin
  fonts appear in the hi-res listing".
- Docs: api-reference row for `api.font`; `docs/plugin-system.md`; fonts
  page sentence "Every other hi-res font — user-supplied or
  plugin-contributed — defaults to 128" becomes "user-supplied fonts
  default to 128; a plugin font defaults to what its plugin declared";
  CLAUDE.md `font_threshold` paragraph gets the same one-line amendment.
- Tests: registered threshold is returned by `default_threshold`;
  `resolve_font(name)` with no threshold loads at it; explicit threshold
  wins; reset clears it; bool / out-of-range / non-int rejected; a font
  registered without a threshold still defaults to 128; plugin font name
  appears in `list_available_hires_fonts()` and `_is_hires_font_name`;
  two-row image with a plugin font is refused like a bundled hi-res font;
  validate rule 2 is quiet for two widgets on the plugin default and warns
  when one overrides; `API_VERSION >= (1, 3)`.
- Byte-identical for every existing config: nothing registers a plugin
  font today.

### Flair (`led-ticker-plugins`, one PR after the core release)

- **Plugin root.** Flair's entry point is `led_ticker_flair.flair:register`,
  and `_resolve_root` uses that module's directory, so the root is
  `led_ticker_flair/flair/`. Files go in `led_ticker_flair/flair/fonts/`
  and register as `api.font("BungeeShade", "fonts/BungeeShade-Regular.ttf", threshold=45)`
  (not `flair/fonts/...`, which would double the segment). `api.font`
  never checks existence, so a flair test asserts each registered path
  exists and `resolve_font("flair.<name>", 48)` returns a `HiresFont`.
- Files: the four TTFs unmodified plus one `OFL.txt` per family copied
  from its own google/fonts dir (`ofl/bungeeshade`, `ofl/bungeeoutline`,
  `ofl/londrinashadow`, `ofl/londrinaoutline`). Record the google/fonts
  commit the files came from in a `SOURCES.md` beside them. Hashes of the
  files verified on moonbunny today (sha256):
  `665c6260…7df482` BungeeShade, `9232000f…721f1f` BungeeOutline,
  `bdc4a662…e01a21` LondrinaShadow, `773c655b…f05f4d` LondrinaOutline
  (full hashes in the gate assets; the builder re-hashes on fetch).
- Hatch's `packages = ["src/led_ticker_flair"]` already ships non-Python
  files (sprites prove it); add a packaging test that the built wheel
  contains the four TTFs and the licence files.
- `register(api)`: if `API_VERSION >= (1, 3)` call the three-arg form
  with `threshold=45`; else the two-arg form plus one `logger.warning`
  ("flair display fonts need `font_threshold = 45` on this core").
  Tests cover both branches.
- Core floor in `pyproject.toml`: the core release that carries the
  change (check the latest tag first; dev versions lag tags).
- README section "Display fonts": table of name, look, recommended
  `font_size` (Bungee Shade 40-56, Bungee Outline 36-52, Londrina Shadow
  44-56, Londrina Outline 36-52), default threshold 45, "bigsign only
  (scale 4; unreadable on 16-row signs)". Note the old-core caveat.
- Demo config `plugins/flair/examples/display-fonts.bigsign.toml` (one
  `message` per font), rendered to a GIF for the README with the render
  demo via the plugins venv (rows=64/cols=256/chain=1 copy; snippet and
  demo TOML must match verbatim per the docs-parity rule). My call; drop
  if James would rather not carry a GIF.
- Flair `CLAUDE.md`: one invariant bullet: fonts are unmodified OFL files,
  threshold 45 comes from the moonbunny measurement plus the local
  size-range grid, re-measure on the sign before changing it.
- Flair version bump per its tag convention; the release needs James's
  go.

## Calls I made (check these while reading)

1. Names drop `-Regular`; no look-based aliases.
2. One threshold, 45, for all four (sign passed at 60/45 at one size; the
   range grid says 45 everywhere).
3. Old-core fallback registers without a threshold and warns once.
4. No scale-1 warning for these fonts.
5. Demo config + GIF in the flair README.
6. Core PR also fixes the hi-res listing for plugin fonts (found during
   recon; small, same seam).

## Left to the builder

- Exact test file placement for the rule 2 and listing tests.
- Whether the api-reference drift test needs its table regenerated or
  hand-edited.
- GIF duration and frame sampling (making-a-gif skill; sample by
  playback time).

## Background

Gate doc `docs/superpowers/specs/2026-11-19-text-styling-gate.md` §12
(local-only) and its `assets/.../hw/` folder hold the moonbunny captures,
the threshold sweep, the size-range grid output and the deploy configs.
