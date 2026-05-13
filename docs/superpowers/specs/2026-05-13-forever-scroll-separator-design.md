# Design: Per-Section `forever_scroll` Loop Separator

**Date:** 2026-05-13
**Status:** Approved

## Overview

Replace the hardcoded white bullet (`" • "`) interspersed between widgets in `forever_scroll` mode with a configurable per-section separator. Users can:

- Pick a custom character — e.g., `"*"` for a marquee aesthetic.
- Pick `""` for no character (whitespace gap only, no glyph).
- Pick a custom font for the separator — e.g., a brand font that matches the section's message widget.
- Pick a custom color (constant, `"rainbow"`, `"color_cycle"`, or a gradient — same color-provider surface as `font_color` on regular widgets).

The motivating case: a `forever_scroll` section using a custom display font wants its loop boundary `*` to render in the same font, not in the default 6x12 BDF.

---

## Field surface

Four new fields on `SectionConfig`, all flat (mirrors how `font` / `font_size` / `font_color` are already structured on widgets):

```toml
[[playlist.section]]
mode = "forever_scroll"
separator = " * "                      # the text rendered between loops
separator_font = "hunters_kpop"        # font name (BDF alias or hires font file)
separator_font_size = 48               # required for hires fonts; ignored for BDF
separator_color = [225, 48, 108]       # constant RGB; or "rainbow"; or {style = "gradient", ...}
```

- **Types:**
  - `separator: str | None = None`
  - `separator_font: str | None = None`
  - `separator_font_size: int | None = None`
  - `separator_color: list[int] | str | dict | None = None` (parsed by the existing `font_color` parser into a `ColorProvider`)
- **Defaults:** all `None`. When ALL four are `None`, use the existing `DEFAULT_BUFFER_MSG` (the white `•`) — zero behavior change for existing configs.
- **Mode:** only `mode = "forever_scroll"` honors these. `infini_scroll` widgets fully exit before the next starts, so no separator is needed. `swap` / `gif` don't intersperse at all.

### Literal-text semantics

The string in `separator` is rendered as-is, no auto-padding:

| TOML | Rendered text |
| --- | --- |
| (unset / `None`) | `" • "` (today's default) |
| `separator = "*"` | `"*"` (no surrounding space) |
| `separator = " * "` | `" * "` (user-controlled spacing) |
| `separator = ""` | `"  "` (two spaces — auto minimum gap to avoid widget-touch) |

The empty-string special case ensures widgets don't visually butt up against each other when the user opts out of a glyph. Any non-empty value is rendered exactly as typed.

### Field independence

Each field can be set independently:

- `separator_font` alone (without `separator`) → renders the default `•` in the custom font. Niche but valid (e.g., a section that wants the default bullet but in a thinner BDF).
- `separator_font_size` alone (without `separator_font`) → meaningless (default font is BDF and has a fixed size). The TickerMessage constructor's existing checks will raise; surfaced via the validator's existing rule 5 (`requires font_size`) only in reverse — we DON'T need a new rule for this combination.
- `separator_color` alone → recolor the default bullet.

This matches how widgets already let you mix-and-match `font` / `font_size` / `font_color`.

---

## Validation (new rule 26)

Rule 26 fires when ANY of the four separator fields is set on a section whose `mode != "forever_scroll"`. Same shape as rule 25 (`start_hold` on wrong mode):

| Location | Trigger | Severity |
| --- | --- | --- |
| `section[i]` | any of `separator` / `separator_font` / `separator_font_size` / `separator_color` set on `mode in ("swap", "gif", "infini_scroll")` | error |

Single error per section (not one per field). The fix message lists all four field names.

Color parsing is delegated to the existing `font_color` resolver in `app.py`. If the value is malformed (e.g., a 2-element list, a string that doesn't match any color provider), that resolver already raises with a clear message — those failures surface via `_run_build_checks`, not via a new rule.

---

## Wiring

Per-section custom buffer_msg is built in `app.py` and passed to `Ticker` via the existing `buffer_msg` kwarg. The current Ticker signature already accepts `buffer_msg: Any` (defaults to `DEFAULT_BUFFER_MSG` when `None`); no `Ticker` changes needed.

New helper in `app.py`, near `_resolve_title_delay`:

```python
def _resolve_buffer_msg(section: SectionConfig) -> TickerMessage | None:
    """Build a per-section separator TickerMessage, or None to inherit the
    default white-bullet separator.

    Returns None when all four separator_* fields are unset — Ticker
    will fall back to DEFAULT_BUFFER_MSG.
    """
    if (
        section.separator is None
        and section.separator_font is None
        and section.separator_font_size is None
        and section.separator_color is None
    ):
        return None

    # Empty string -> minimum gap of two spaces (no glyph).
    text = section.separator if section.separator is not None else "•"
    if text == "":
        text = "  "

    kwargs: dict[str, Any] = {"text": text, "center": False}
    if section.separator_font is not None:
        kwargs["font"] = section.separator_font  # name; resolved by TickerMessage
    if section.separator_font_size is not None:
        kwargs["font_size"] = section.separator_font_size
    kwargs["font_color"] = _resolve_color_provider(
        section.separator_color, default=RGB_WHITE
    )
    return TickerMessage(**kwargs)
```

`_resolve_color_provider` is the existing helper used by widget construction; same path that powers `font_color` on `message`. The default kwarg keeps today's white bullet color when the user only changes `separator` text.

Wiring in the existing section build loop (around line 917 in `app.py`):

```python
buffer_msg = _resolve_buffer_msg(section)
if buffer_msg is not None:
    ticker_kwargs["buffer_msg"] = buffer_msg
```

When `buffer_msg` is `None`, the kwarg is omitted and `Ticker.__init__` keeps its default of `DEFAULT_BUFFER_MSG`.

---

## Inheritance and back-compat

- No global default added — these are per-section knobs only. Sections that don't set them inherit `DEFAULT_BUFFER_MSG`.
- Today's `DEFAULT_BUFFER_MSG` constant in `ticker.py` stays. It IS the inherited default; not renaming it.
- All bundled example configs continue to render identically. Regression sweep confirms zero behavior change.

---

## Architecture

### File map

1. **`src/led_ticker/config.py`** — add four fields to `SectionConfig`. Parse them from raw TOML in the section loader.

2. **`src/led_ticker/app.py`**:
   - Add `_resolve_buffer_msg(section)` helper near `_resolve_title_delay`.
   - At the per-section Ticker build site, conditionally inject `buffer_msg` into `ticker_kwargs`.

3. **`src/led_ticker/validate.py`** — new rule 26 in `_check_static`. Same code shape as rule 25.

4. **Tests**:
   - `tests/test_config.py` — parse each new field, verify defaults.
   - `tests/test_app.py` — `_resolve_buffer_msg` returns `None` when all unset, returns a `TickerMessage` with the right text/font/color when set, handles empty-string special case.
   - `tests/test_validate.py` — rule 26 fires on `swap` / `gif` / `infini_scroll`, doesn't fire on `forever_scroll`.

5. **Meta-tripwire** — `tests/test_docs_config_options_drift.py` allow-list for the four new fields. **As confirmed in the start_hold work, this update lands in the docs commit, not the config commit**, because the drift test compares the allow-list against the docs page, not against the dataclass.

6. **Docs**:
   - `docs/site/.../reference/config-options.mdx` — four new rows in per-section table.
   - `docs/site/.../pitfalls.mdx` — rule 26 entry.
   - `docs/site/.../tools/validate.mdx` — rule 26 row.
   - `docs/site/.../concepts/sections-and-modes.mdx` — short prose paragraph explaining the separator, if the page discusses the bullet today. Skip if not.

### What stays the same

- `Ticker.__init__` signature.
- `DEFAULT_BUFFER_MSG` constant.
- `_scroll_side_by_side` internals (the buffer_message is already a generic widget — it doesn't know it's a "separator").
- `SCROLL_GAP` constant and the `scroll` transition's bullet (different code path — that's `_draw_bullet` in transitions, not the forever_scroll separator).

---

## Test plan

### Config parsing (`tests/test_config.py`)

- `test_section_separator_defaults_to_none`
- `test_section_separator_parses_string`
- `test_section_separator_parses_empty_string`
- `test_section_separator_font_parses`
- `test_section_separator_font_size_parses`
- `test_section_separator_color_parses_constant`

### Buffer build (`tests/test_app.py`)

- `test_resolve_buffer_msg_returns_none_when_all_fields_unset` — explicit None means inherit DEFAULT_BUFFER_MSG via Ticker default
- `test_resolve_buffer_msg_with_separator_text_only` — text set, font/color defaults preserved
- `test_resolve_buffer_msg_with_empty_separator_maps_to_two_spaces` — load-bearing
- `test_resolve_buffer_msg_with_custom_font_inherits_default_text` — `separator_font` alone keeps `•` text
- `test_resolve_buffer_msg_with_custom_color` — RGB list parses to ColorProvider

### Validator (`tests/test_validate.py`)

- `test_rule26_separator_on_swap_errors`
- `test_rule26_separator_on_gif_errors`
- `test_rule26_separator_on_infini_scroll_errors`
- `test_rule26_separator_on_forever_scroll_is_allowed`
- `test_rule26_separator_font_alone_on_swap_errors` — confirms the rule catches any of the four fields, not just `separator`

### Regression sweep

- Run `led-ticker validate` against every bundled example config and demo config. Zero rule-26 hits. Zero behavior changes (no example config sets any of the four fields today).

---

## Out of scope

- Renaming `DEFAULT_BUFFER_MSG` to `DEFAULT_SEPARATOR`. The internal naming is consistent with today's "buffer message" framing in `Ticker` and `_scroll_side_by_side`. User-facing naming is `separator_*`; internal can stay.
- Per-widget separator overrides. The separator is between widgets in the forever_scroll queue; making it per-widget would be a different feature (per-widget trailing text, essentially).
- Animated separator (typewriter, etc.). The separator is a TickerMessage; theoretically it accepts `animation` — but exposing that adds surface area beyond the asked-for feature. Skip in this PR.
- Color gradient where the gradient runs ACROSS the separator vs. across the joining widgets together. Out of scope; rainbow/color_cycle work per the existing per-char patterns.

---

## Implementation notes

- The `separator_color` field uses the same parser as widget `font_color`. Reuse `_resolve_color_provider` (or whatever it's named in `app.py`) instead of writing a new path.
- For `_resolve_buffer_msg`, prefer keeping it small and testable as a pure function — pass `RGB_WHITE` as the default color so tests don't import the module's internal default.
- `TickerMessage` already supports `font` / `font_size` / `font_color` keyword args. The construction path here doesn't need new TickerMessage features.
- Rule 26 fires once per section even if multiple separator fields are set on the wrong mode. The fix message names all four fields so the user knows what to remove regardless of which they set.
- Don't add an "unset everything" sentinel value like `separator = "null"`. The `None` default IS the unset state, and `separator = ""` is the documented "no glyph" path.
