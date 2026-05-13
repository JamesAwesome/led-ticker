# Design: Per-Section `start_hold`

**Date:** 2026-05-13
**Status:** Approved

## Overview

Add `start_hold` as a per-section field on `forever_scroll` / `infini_scroll` sections. It controls the initial pre-roll (scroll-in + hold of the first widget) that today is governed only by the playlist-wide `[title] delay`. Sections that don't set `start_hold` inherit `[title] delay` — full back-compat.

The motivating case: a playlist with a 5-second title-card hold for one section and a marquee section that should start scrolling immediately. Today both are bound to the same global. After this change, the marquee section sets `start_hold = 0.0` and the title section is unaffected.

---

## Field surface

```toml
[[playlist.section]]
mode = "forever_scroll"
start_hold = 0.0     # new — overrides [title] delay for this section only
```

- **Type:** `float | None`. Default `None` (inherit).
- **Units:** seconds.
- **Domain:** `>= 0`. Negative is a config-time error.
- **Inheritance:** `None` → fall through to `config.title_delay` (the `[title] delay` int, coerced to float at use). Any other value (including `0.0`) overrides.
- **Effect window:** only `mode in ("forever_scroll", "infini_scroll")`. Setting it on `swap` / `gif` is a validation error (rule 25) — see below.

The name pairs with the existing `hold_time` field on the same section, which controls the END hold after all loops finish. `start_hold` is the BEFORE; `hold_time` is the AFTER. Symmetry is the discoverability story for the doc page.

---

## Inheritance and back-compat

- `[title] delay` is unchanged. Default still `5`. Still typed `int` in `AppConfig`.
- Existing configs that don't set `start_hold` see no runtime behavior change.
- The validate rule for `start_hold < 0` is in the same family as today's `hold_seconds < 0.05` check.

No deprecation of `[title] delay` in this change. A future cleanup could rename the global, but that's out of scope here.

---

## Validation (new rule 25)

Rule 25 fires when `start_hold` is set on a section where it has no runtime effect:

- `mode = "swap"` — uses per-widget hold via the engine's `_swap_and_scroll`, not `_scroll_and_delay`. `start_hold` would be ignored.
- `mode = "gif"` — uses `_run_gif`, which doesn't go through `_scroll_and_delay`.

Severity: **error**. The pattern matches existing rules where a field is configured but has no effect (rule 12, 14, 15). Silently ignoring would let users believe they're tuning something that does nothing.

Negative `start_hold` (`< 0`) also rejected. Same rule number, different message — mirrors the style of `hold_seconds < 0.05` (rule 8).

Validation rule entry (for the docs table):

| Check | Severity | Quick fix |
| --- | --- | --- |
| `start_hold` set on a non-scroll mode (`swap` / `gif`) | error | use `hold_time` on `swap`, or change `mode` |
| `start_hold < 0` | error | set to `0` or a positive number of seconds |

---

## Wiring

Two-line plumbing change in `app.py`. Today (paraphrased):

```python
ticker_kwargs["title_delay"] = config.title_delay
```

After:

```python
ticker_kwargs["title_delay"] = (
    section.start_hold
    if section.start_hold is not None
    else float(config.title_delay)
)
```

`Ticker.title_delay` stays typed as `int` for now (its current annotation) — the `float()` coercion is fine because `_scroll_and_delay`'s `delay` parameter is `float`. If `int` typing causes downstream friction, we widen `Ticker.title_delay: int | float` in the same change.

No changes to `ticker.py` — `_scroll_and_delay` already accepts a float `delay` parameter and the `if delay:` gate at the top of `_scroll_side_by_side` already short-circuits when `delay == 0`.

---

## Architecture

### File map

1. **`src/led_ticker/config.py`** — add `start_hold: float | None = None` to `SectionConfig`. Parse from raw TOML in the section loader. No global config changes.

2. **`src/led_ticker/app.py`** — at the per-section Ticker build site (around line 907), compute `title_delay` from `section.start_hold` with fallback to `config.title_delay`. One-line plus a coercion.

3. **`src/led_ticker/validate.py`** — new rule 25 in `_check_soft` (or its own helper, mirroring `_check_held_top_text_overflow`). Two conditions:
   - `start_hold is not None and section.mode in ("swap", "gif")` → error
   - `start_hold is not None and start_hold < 0` → error

4. **Tests** (see Test plan below).

5. **Docs** (see Docs section below).

### What stays the same

- The `Ticker` class signature and dispatch.
- `_scroll_and_delay` and `_scroll_side_by_side` internals.
- `[title] delay` semantics, type, and default.
- All existing example configs (they don't set `start_hold`).

---

## Test plan

### Config parsing (`tests/test_config.py`)

- A section with `start_hold = 0.0` parses with `section.start_hold == 0.0`.
- A section without `start_hold` parses with `section.start_hold is None` (NOT `0` — that would conflate "unset" with "explicitly zero").
- A section with `start_hold = 2.5` parses with `section.start_hold == 2.5`.

### App wiring (`tests/test_app.py` or `tests/test_ticker_display.py`)

- Section with `start_hold = 0.0` → `Ticker` constructed with `title_delay == 0.0` (or 0 — exact equality after coercion).
- Section with `start_hold = None` and `[title] delay = 5` → `Ticker` constructed with `title_delay == 5`.
- Section with `start_hold = 1.5` and `[title] delay = 5` → `Ticker` constructed with `title_delay == 1.5` (section wins).

### Validator (`tests/test_validate.py`)

- `test_rule25_start_hold_on_swap_section_errors` — error fires.
- `test_rule25_start_hold_on_gif_section_errors` — error fires.
- `test_rule25_start_hold_on_forever_scroll_is_allowed` — no rule-25 error.
- `test_rule25_start_hold_on_infini_scroll_is_allowed` — no rule-25 error.
- `test_rule25_negative_start_hold_errors` — error fires.
- `test_rule25_zero_start_hold_is_allowed` — `start_hold = 0.0` on a `forever_scroll` section validates clean.

### Regression sweep

- Re-run the existing example configs in `config/` and `docs/site/demos-*/` through the validator. Zero unexpected errors (none of them set `start_hold`).

---

## Docs

1. **`docs/site/src/content/docs/reference/config-options.mdx`** — add a `start_hold` row to the per-section table.

2. **`docs/site/src/content/docs/concepts/playback.mdx`** (or equivalent concepts page for the modes) — short paragraph: "By default every `forever_scroll` / `infini_scroll` section starts with a pre-roll set by `[title] delay`. Override per section with `start_hold`. Setting `start_hold = 0` makes the section's first widget walk in from the right edge without pausing."

3. **`docs/site/src/content/docs/pitfalls.mdx`** — rule 25 entry under the Errors section.

4. **`docs/site/src/content/docs/tools/validate.mdx`** — rule 25 row in the reference table.

---

## Out of scope

- Renaming `[title] delay` to something like `[playlist] start_hold_default`. Separate cleanup; the current change is intentionally surgical.
- Per-widget `start_hold`. The pre-roll fundamentally operates on the section's FIRST widget; adding it per-widget would change semantics.
- Negative `start_hold` to mean "skip the first N seconds of scroll-in". Not requested; would be a different feature.
- Splitting the existing scroll-in + hold into two separate knobs. Today's bundled behavior is preserved.
- Migration path for `mode = "swap"`. `hold_time` is the correct field there; cross-mode aliasing would create confusion.

---

## Implementation notes

- `start_hold = 0` must reliably bypass the pre-roll. The existing `if delay:` guard at the top of `_scroll_side_by_side` (line 452) already short-circuits when `delay == 0` (`0` is falsy in Python). No changes needed there.
- The validator's new rule should be in `_check_static` (it's a section-shape check, not a widget-shape check). Position next to rule 6 (`two_row` at `scale = 4`) which is the same shape of check.
- `SectionConfig` is a frozen attrs dataclass (per existing patterns); the new field follows the same conventions.
