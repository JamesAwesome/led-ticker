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

**Resolution order** (decided): emoji wins, then source, then literal. The substitution pre-pass runs *before* the emoji parser, so to honor "emoji wins" the pre-pass **skips any token name present in the emoji registry** (it substitutes only names that resolve to a declared source and are not emoji). As defense-in-depth, `validate` also **rejects a source `id` equal to an emoji slug** at config-load, so the skip never actually fires in a valid config — but the skip makes the precedence correct-by-construction rather than relying on validation.

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
  - the `polled: bool` field is part of the contract now, but the v1 background-loop **wiring is NOT shipped** (see "YAGNI" below) — no core source is polled and no `run_monitor_loop` branch is built in v1; v2 adds the loop wiring where it gets a real test.
  - **Write-order contract** (binds future polled sources): a source must write `current` **before** `version`, with no `await` between them, so a reader that samples `version`-then-`current` can never see a new version paired with a stale value. v1 sync sources satisfy this trivially; the contract is documented now for `api.source` implementers.
- Core source classes: `ClockSource`, `DateSource`, `StaticSource` (all `polled=False`).
  - clock/date hold a compiled strftime `format` (+ optional `timezone`); `compute()` formats "now".
  - static's `compute()` returns its fixed `value`.
- `DataRegistry` — maps `id → DataSource`; built once at app startup from `[[source]]`. Reachable from widget `draw()` via a **module-level accessor** (`get_data_registry()` / `set_data_registry()`), set at startup; tests inject a fake via the setter. (Consistent with the existing module-level plugin registry; avoids threading a registry argument through every widget factory.)
- **Refresh:** a single shared **1 Hz ticker** (`spawn_tracked`, `widget.py:32`) calls `compute()` on every synchronous source each second and **bumps `version` only when the string actually changed**. One ticker for all synchronous sources (not one task per source). (1 Hz covers per-second and per-minute formats; finer granularity is out of scope.)
- **Hot-reload** (`_apply_reload`, `reload.py`): reload is awaited between render cycles (not concurrent with a `draw()` in the engine loop), but the 1 Hz ticker IS concurrent — so reload must **(a)** build the new `DataRegistry` fully and **atomic-swap** the module global (never mutate the live dict in place, or the ticker can iterate a half-built registry), and **(b)** cancel the old source ticker and spawn a new one (mirror how schedule is respawned). A surviving cached widget whose text is unchanged keeps its `_referenced_ids`; if a referenced `[[source]]` id was removed/renamed, that token degrades to literal at draw (graceful, reads the live registry) — `[[source]]` is intentionally NOT added to the widget cache key. Document this degradation as intended.
- **`api.source(type)` plugin surface** in `led_ticker.plugin` — mirrors `api.easing` (`plugin.py:334`): registers a source class under `namespace.type` into the source registry, with the same dup-rejection + `_qualify` plumbing. Added to `__all__`. Core registers `clock`/`date`/`static` through the same registry at import. (The registry surface ships in v1; only the polled background-loop *consumer* is deferred to v2.)

## 4. Rendering — "re-measure on change" (decided)

The investigation assumed fixed-width slots would keep `draw_with_emoji` unchanged; verification showed led-ticker's BDF fonts are **proportional**, so a true fixed *pixel* slot would require segment-aware drawing. We chose the simpler strategy that keeps the existing pipeline untouched:

- **At construction**, each text-bearing widget runs a cheap scan of its text field(s) for source tokens (reusing the token regex), recording the referenced source ids and a `_has_tokens` flag. Widgets with no source tokens are entirely unaffected (every step below is gated on `_has_tokens`).
- **At `draw`** (when resolution is *not* frozen — see below), the widget int-compares the referenced sources' `version`s against the last-seen versions it stored:
  - **changed** → re-run the substitution pre-pass to rebuild the display string, store the new versions, and **invalidate the width cache(s)** so the next measure re-decides hold-vs-scroll / centering. The exact caches to invalidate per widget: `message.py` `_content_width` (`message.py:60`); `two_row.py` `_content_width` **and** `_bottom_width` (the bottom-row overflow decision uses a separate cache at `two_row.py:163/488`); the image/gif overlay's width cache in `_image_base.py`.
  - **unchanged** → reuse the cached substituted string and cached width.
- Steady-state per-tick cost (nothing changed) = O(referenced sources) integer comparisons. Substitution/measurement never run on an unchanged tick.

### 4a. Resolution-freeze (the hardware-correctness fix)

Re-measuring at an arbitrary tick is **only safe while the widget is HELD** — `_hold_ticks` redraws every tick and `compute_cursor` re-centers against the current width, so a value change shows a single-tick re-center (acceptable). It is **unsafe during scroll, transition compositing, and typewriter reveal**, where width is captured once and a mid-flight change corrupts rendering. v1 therefore adds a `_resolution_locked` flag (duck-typed, parallel to the existing `pause_frame()`/`resume_frame()` frame-counter freeze):

- **Scroll** (`_swap_and_scroll` scroll branch, `ticker.py`): `stop_pos` is computed **once** from the width at scroll entry (`ticker.py:~669`) and the loop discards the per-tick cursor_pos — so a mid-scroll re-measure would strand the scroll and clip characters (constraints #6/#7). Fix: resolve the widget once *before* `stop_pos` is computed, then set `_resolution_locked = True` for the scroll loop (re-measure suppressed); unlock after. A version that bumped mid-scroll applies on the next held tick / next visit.
- **Transitions** (`run_transition` / `_scroll_between`): these already call `pause_frame()`/`resume_frame()` on the participating widgets. Extend that same seam to **also** set/clear `_resolution_locked`, so a version bump from the 1 Hz ticker cannot change a widget's width while it is being re-rendered for compositing (the C1 hole). No new call sites — it rides the existing pause/resume.
- **Typewriter** (`animation = "typewriter"`): lock resolution for the whole reveal so the sliced string length is stable; additionally, the per-char hue `total_chars` must be counted from the **substituted** string, not the raw `self.text` (today `count_text_chars(self.text)` reads the raw field — with a token that count is wrong). The typewriter path resolves once at reveal start and reads that.
- **Held:** `_resolution_locked = False` — live updates allowed (the live-clock case works during a hold).

- **Reflow** thus happens only at a safe point when a value has changed (per-minute for `%M`, per-day for `%A`, never for `static`). Constant-width formats (zero-padded `%H:%M`) never reflow; variable-width ones reflow once, at the next held tick / visit — a rare, graceful re-center. Overflow-mode flips (two_row bottom row crossing the scroll threshold; a held message growing past the panel) apply at the **next visit**, not mid-visit — the engine reads overflow/width-derived loop bounds once at visit entry.

**Centralization:** the substitution + token-scan + version-tracking logic lives in one shared helper (a small stateful `TokenizedField` in `sources.py`: holds the raw text, the referenced ids, the last-seen `version`s, and the cached substituted string; `resolve(registry) -> (text, changed: bool)` re-substitutes and flips `changed` only when a referenced source's version moved). A field with no source tokens reports `changed=False` forever and returns its literal text. Each widget owns one helper per text field and keeps its own `_content_width` invalidation wiring:

- `widgets/message.py` — `TickerMessage.text` (and `SegmentMessage` if it carries free text).
- `widgets/two_row.py` — `top_text` and `bottom_text` (independent helpers/slots per row).
- `widgets/_image_base.py` — the image/gif text overlay `text` and `bottom_text`.

## 5. Validation

`validate.py` gains source-aware rules (preflight, `make validate`):

- **Errors:** duplicate source `id`; a source `id` equal to an emoji slug (collision); unknown source `type`; a malformed per-type `format` (e.g. clock/date `format` that `strftime` rejects); `static` missing `value`; an invalid `timezone`.
- **No "undeclared token" warning.** An unknown `:slug:` rendering as literal text is existing, intentional behavior, and there is no way to distinguish an intended-but-undeclared source token from literal `:word:` text or a typo'd (possibly plugin) emoji slug — warning on every unknown slug would be noise that trains users to ignore `make validate`. Omitted from v1; literal fallback is documented in the docs page instead.
- A widget plugin's own `validate_config` is unaffected.

## 6. Testing & the hardware tripwire

- **Registry/sources:** `compute()` correctness for clock/date/static; the 1 Hz ticker bumps `version` only on a real change (not every tick); `get/set_data_registry` + reset-on-reload.
- **Substitution:** declared id → value; emoji slug preserved; unknown token → literal; resolution order (emoji wins over a same-named source — and validate forbids that case).
- **Per widget** (message, two_row each row, image/gif overlay): a token resolves and renders; a non-token widget is byte-identical to today (regression guard).
- **The load-bearing tripwires (constraints #6/#7 + the freeze model, §4a):**
  - a HELD `message` with a live token whose value width changes re-measures + re-centers correctly (one per widget surface);
  - **scroll freeze (C2):** a token value bumping mid-scroll does NOT change the in-flight `stop_pos`/clip the tail — the new value applies on the next pass;
  - **transition freeze (C1):** a version bump during a mocked transition leaves the composited width stable (the `pause_frame` seam also locks resolution);
  - **typewriter freeze (I3):** a value change mid-reveal doesn't corrupt the slice, and per-char hue `total_chars` is counted from the substituted string;
  - per-char color (rainbow) flows across a substituted value (its characters get hues like any other text).
- **Hot-reload:** the registry swap is atomic (a fake registry observed by a concurrent ticker is never half-built) and the source ticker is cancelled+respawned; a removed referenced id degrades a surviving widget's token to literal.
- **`api.source`:** a registered source resolves through the full pipeline; dup registration rejected.
- Gates green: pytest (with `PYTHONPATH=tests/stubs`), `ruff check src/ tests/`, `pyright src/`, `make docs-build`/`docs-lint` for the new docs page.

## 7. Docs

A new concept page (`docs/site/.../concepts/value-tokens.mdx` or similar) covering the `[[source]]` block, the three core source types, the `:id:` syntax, and the resolution/literal-fallback rule; cross-link from the relevant widget pages and `reference/config-options.mdx`. DOCS-STYLE compliant. Add `[[source]]` to the config-options drift audit if applicable.

## Scope

**In (v1):**
- `clock` / `date` / `static` synchronous sources + the `[[source]]` config block.
- Token substitution across **all** text-bearing widgets (message, two_row, image/gif overlay).
- The `api.source` plugin surface + the source registry. The `DataSource` contract includes the `polled` field + the write-order rule, but the polled background-loop **wiring** is deferred to v2 (no untested dead code in v1).
- The `_resolution_locked` freeze across scroll / transition / typewriter (§4a).
- `validate` rules + the per-surface width + freeze tripwires + a docs page.

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
