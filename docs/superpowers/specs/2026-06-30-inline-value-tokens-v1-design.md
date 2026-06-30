# Inline value tokens — v1 design

**Date:** 2026-06-30
**Status:** Approved (brainstorm complete) — ready for an implementation plan.
**Predecessor:** the feasibility investigation `docs/superpowers/investigations/2026-06-21-inline-value-tokens.md` (PR #255). This spec resolves the open forks that investigation left and refines one of its premises (see §4).

## Goal

Let any text-bearing widget embed inline tokens that resolve to a live string, reusing the existing `:slug:` syntax:

> `font_text = "Welcome! It's :clock.now: on :date.today:"`

v1 ships **synchronous** sources only — `clock`, `date`, `static` — end-to-end across every text-bearing widget, plus the `api.source` plugin surface (the polled/async path exists but is unused; weather etc. is v2).

## Global constraints

- **Mode/name conventions** are not touched; this is additive.
- **PEP 649:** no `from __future__ import annotations` in any new/edited file.
- **Hardware render constraints #6/#7** (cursor/scroll math depends on a correct content width) are the load-bearing risk — see §4 + §6.
- **Plugin public surface:** the `api.source` surface is added to `led_ticker.plugin`; plugins import only from there. `__all__` is the contract.
- **DOCS-STYLE.md** for all docs; no "footgun"/"gun" metaphor anywhere.
- **Core gates:** `PYTHONPATH=tests/stubs uv run --extra dev pytest`, `ruff check src/ tests/`, `pyright src/`.
- Worktree + PR; never commit on `main`.

## 1. Token syntax & resolution

Reuse the existing `:slug:` syntax — `_parse_segments` (`pixel_emoji.py:2506`, regex `:[a-z_][a-z0-9_.]*:` at `pixel_emoji.py:40`) already accepts dotted names and falls through to literal on an unknown slug; the leading `[a-z_]` keeps clock output like `12:34` from tokenizing.

A **substitution pre-pass** runs *before* layout: it replaces any token whose name matches a **declared source id** with that source's `current` value string, and leaves everything else untouched — emoji slugs, unknown tokens, and literal colons all pass through. The result is a plain string that the existing `draw_with_emoji` (`pixel_emoji.py:2590`) + per-char-color pipeline renders with **zero changes** (emoji slugs in the substituted string are still handled downstream as today).

**Resolution order** (decided): emoji registry wins, then source registry, then literal. Because sources are explicitly declared and namespaced (`clock.now`, `weather.nyc`), real collisions are rare; `validate` makes them impossible by **rejecting a source `id` equal to an emoji slug** at config-load.

## 2. Config — top-level `[[source]]`

Sources are global / cross-section, so they are a genuinely top-level array-of-tables (sibling to the `[playlist]` table, **not** nested under it — sections parse from `raw["playlist"]["section"]` at `config.py:613`; sources parse from `raw["source"]`). No collision with the existing nested `[busy_light].source` key.

```toml
[[source]]
id = "clock.now"          # the token name → :clock.now: (must match :[a-z_][a-z0-9_.]*:)
type = "clock"            # selects the source class from the registry
format = "%-I:%M %p"      # type-specific; strftime here → "9:01 AM"

[[source]]
id = "date.today"
type = "date"
format = "%A"             # → "Monday"
# optional: timezone = "America/New_York"   (clock + date; default = system local)

[[source]]
id = "brand.tagline"
type = "static"
value = "Open 9–5"        # fixed string; the simplest source (also the pipeline's smoke test)
```

Parsing mirrors the existing raw-dict→factory pattern (`SectionConfig.widgets` is a `list[dict]` handed to a factory). A new `SourceConfig` dataclass holds `id`, `type`, and the raw kwargs; the source factory (`get_source_class(type)`, mirroring `get_widget_class`) constructs the `DataSource`.

## 3. Components

**New file `src/led_ticker/sources.py`** (≈ `borders.py` in size):

- `DataSource` protocol / base — fields/behavior:
  - `id: str`, `current: str`, `version: int`, `polled: bool`
  - synchronous sources implement `compute() -> str` (pure; no I/O/await)
  - polled sources (v2) own a background `run_monitor_loop` that writes `current`/`version` (the path exists in v1, no core source uses it)
- Core source classes: `ClockSource`, `DateSource`, `StaticSource` (all `polled=False`).
  - clock/date hold a compiled strftime `format` (+ optional `timezone`); `compute()` formats "now".
  - static's `compute()` returns its fixed `value`.
- `DataRegistry` — maps `id → DataSource`; built once at app startup from `[[source]]`. Reachable from widget `draw()` via a **module-level accessor** (`get_data_registry()` / `set_data_registry()`), set at startup and **reset on hot-reload**; tests inject a fake via the setter. (Consistent with the existing module-level plugin registry; avoids threading a registry argument through every widget factory.)
- **Refresh:** a single shared **1 Hz ticker** (`spawn_tracked`, `widget.py:32`) calls `compute()` on every synchronous source each second and **bumps `version` only when the string actually changed**. One ticker for all synchronous sources (not one task per source). Polled sources (v2) self-refresh via their own loop. (1 Hz covers per-second and per-minute formats; finer granularity is out of scope.)
- **`api.source(type)` plugin surface** in `led_ticker.plugin` — mirrors `api.easing` (`plugin.py:334`): registers a source class under `namespace.type` into the source registry, with the same dup-rejection + `_qualify` plumbing. Added to `__all__`. Core registers `clock`/`date`/`static` through the same registry at import.

## 4. Rendering — "re-measure on change" (decided)

The investigation assumed fixed-width slots would keep `draw_with_emoji` unchanged; verification showed led-ticker's BDF fonts are **proportional**, so a true fixed *pixel* slot would require segment-aware drawing. We chose the simpler strategy that keeps the existing pipeline untouched:

- **At construction**, each text-bearing widget runs a cheap scan of its text field(s) for source tokens (reusing the token regex), recording the referenced source ids and a `_has_tokens` flag. Widgets with no source tokens are entirely unaffected (every step below is gated on `_has_tokens`).
- **At `draw`**, the widget int-compares the referenced sources' `version`s against the last-seen versions it stored:
  - **changed** → re-run the substitution pre-pass to rebuild the display string, store the new versions, and **invalidate the width cache** (`self._content_width = -1`) so the next measure re-decides hold-vs-scroll / centering.
  - **unchanged** → reuse the cached substituted string and cached width.
- Steady-state per-tick cost (nothing changed) = O(referenced sources) integer comparisons. Substitution/measurement never run on an unchanged tick.
- **Reflow** happens only when a value changes (per-minute for `%M`, per-day for `%A`, never for `static`). Constant-width formats (zero-padded `%H:%M`) never reflow; variable-width ones reflow once on change — a rare, graceful re-center / re-scroll.

**Centralization:** the substitution + token-scan + version-tracking logic lives in one shared helper (a small stateful `TokenizedField` in `sources.py`: holds the raw text, the referenced ids, the last-seen `version`s, and the cached substituted string; `resolve(registry) -> (text, changed: bool)` re-substitutes and flips `changed` only when a referenced source's version moved). A field with no source tokens reports `changed=False` forever and returns its literal text. Each widget owns one helper per text field and keeps its own `_content_width` invalidation wiring:

- `widgets/message.py` — `TickerMessage.text` (and `SegmentMessage` if it carries free text).
- `widgets/two_row.py` — `top_text` and `bottom_text` (independent helpers/slots per row).
- `widgets/_image_base.py` — the image/gif text overlay `text` and `bottom_text`.

## 5. Validation

`validate.py` gains source-aware rules (preflight, `make validate`):

- Enumerate declared `[[source]]` ids. A token that *looks* like a source token but matches no declared id and no emoji slug → **warning** ("looks like a source token; no `[[source]]` with id `…` is declared — it will render literally"). Not an error: literal fallback is intentional, existing behavior.
- **Errors:** duplicate source `id`; a source `id` equal to an emoji slug (collision); unknown source `type`; a malformed per-type `format` (e.g. clock/date `format` that `strftime` rejects); `static` missing `value`.
- A widget plugin's own `validate_config` is unaffected.

## 6. Testing & the hardware tripwire

- **Registry/sources:** `compute()` correctness for clock/date/static; the 1 Hz ticker bumps `version` only on a real change (not every tick); `get/set_data_registry` + reset-on-reload.
- **Substitution:** declared id → value; emoji slug preserved; unknown token → literal; resolution order (emoji wins over a same-named source — and validate forbids that case).
- **Per widget** (message, two_row each row, image/gif overlay): a token resolves and renders; a non-token widget is byte-identical to today (regression guard).
- **The load-bearing tripwire (constraints #6/#7):** a `message` holding a live token whose value width changes must invalidate `_content_width`, re-measure, and re-decide hold-vs-scroll correctly — one tripwire per widget surface. Plus: per-char color (rainbow) flows across a substituted value (the value's characters get hues like any other text).
- **`api.source`:** a registered source resolves through the full pipeline; dup registration rejected.
- Gates green: pytest (with `PYTHONPATH=tests/stubs`), `ruff check src/ tests/`, `pyright src/`, `make docs-build`/`docs-lint` for the new docs page.

## 7. Docs

A new concept page (`docs/site/.../concepts/value-tokens.mdx` or similar) covering the `[[source]]` block, the three core source types, the `:id:` syntax, and the resolution/literal-fallback rule; cross-link from the relevant widget pages and `reference/config-options.mdx`. DOCS-STYLE compliant. Add `[[source]]` to the config-options drift audit if applicable.

## Scope

**In (v1):**
- `clock` / `date` / `static` synchronous sources + the `[[source]]` config block.
- Token substitution across **all** text-bearing widgets (message, two_row, image/gif overlay).
- The `api.source` plugin surface with the registry + polled path complete (unused by any core source).
- `validate` rules + the per-surface width tripwire + a docs page.

**Out (v2 / later — explicit non-goals):**
- Any **polled / async** source (weather, crypto) — that's v2 (add a poller class via `api.source`; no new subsystem).
- A formatting DSL beyond the single per-type `format` string.
- Sub-field token addressing (one source = one value string).
- Any observer/push machinery beyond the integer `version` counter.
- Fixed-pixel-width slots / segment-aware drawing (rejected for v1 in favor of re-measure-on-change).
- Sub-second refresh granularity.

## Resolved forks (for the record)

1. **Syntax:** reuse `:slug:` (emoji → source → literal; validate forbids id↔emoji collision).
2. **Width strategy:** re-measure on version change (not fixed-pixel slots) — simplest, reuses the draw pipeline, reflow only on real change.
3. **Clock/date:** core sources (core already owns the `clock` widget); plugins add async sources via `api.source`.
4. **Widget scope:** all text-bearing widgets.
5. **Width tooling:** sources need no user `width` config; re-measure-on-change handles proportional fonts correctly.
