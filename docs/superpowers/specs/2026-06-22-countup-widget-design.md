# Design: `countup` widget (+ shared `count` base, both core)

**Date:** 2026-06-22
**Status:** Approved for planning

## Motivation

led-ticker ships a core `countdown` widget that renders days **until** a future date (`"Launch: 42"`). Users also want the mirror — days **since** a past date: "Days since launch", "100 days sober", "Days without an incident", "Open for 5 days". This adds a `countup` widget for that, sharing the countdown render implementation, and unifies their out-of-range behavior.

Both widgets are pure date math against the system clock — no network, no dependency, no secret — so both stay in **core** (the project's extraction line is "needs an external service", not "is a specific widget"; everything that moved to plugins carried a network/dep/key surface).

## Decisions (settled at brainstorm)

An engineer and a product manager debated the two open questions; the outcomes:

- **Two widgets sharing one implementation.** Separate `countdown` + `countup` types (the PM's discoverability + structural misconfiguration-proofing) over a shared base class (the engineer's no-duplication). Not a single widget with a `direction` param; not two fully-independent widgets.
- **Both stay in core.** Unanimous — pure date math is the most core-eligible widget possible; countdown is already core, and moving it would be a breaking change with zero dependency/image benefit.
- **Out-of-range → skip from rotation** (the widget disappears that pass), not a negative number and not a held blank slot. Plus a non-blocking config-load **warning** for a wrong-side date.
- **Unify the rule across both widgets.** This is a **behavior change to the shipped countdown widget**: today it renders `-N` past its date; now it disappears. The user explicitly chose this (consistency; `"Launch: -3"` was never useful). Existing configs remain valid (no migration); it is a documented behavior change.
- **Days only**, no migration of the existing `countdown_date` field.

## Architecture

### 1. Widget structure — `src/led_ticker/widgets/count.py` (new)

A shared base + two thin registered widgets:

- **`_CountWidget(FrameAwareBase)`** — owns the entire shared surface that `TickerCountdown` has today: `text`, `font`, `font_color` (ColorProvider, coerced), `border`, `center`, `padding`, `bg_color`, the `_baseline_y` cache, and the full `draw()` (border-before-text, the per-char vs whole-string ColorProvider branch, `y_offset`/`font_color` override handling). It renders `f"{self.text}: {days}"` where `days` comes from a subclass hook `_days() -> int`. It also implements the visibility hook `should_display() -> bool` returning `self._days() >= 0` (see §2).
- **`TickerCountdown`** (`@register("countdown")`) — field `countdown_date: date`; `_days()` returns `(self.countdown_date - date.today()).days` (positive while the date is in the future).
- **`TickerCountup`** (`@register("countup")`) — field `countup_date: date`; `_days()` returns `(date.today() - self.countup_date).days` (positive while the date is in the past).

`TickerCountdown` moves out of `widgets/message.py` into `widgets/count.py`. `message.py` keeps a back-compat re-export (`from led_ticker.widgets.count import TickerCountdown  # noqa: F401`) so existing importers (e.g. `tests/test_app.py`, any registry/factory import) keep working unchanged. `widgets/__init__.py` imports `count` so both `@register` decorators run at startup (mirroring how `message` is imported today).

Boundary semantics (both widgets): `_days() == 0` on the day itself → shown as `"<text>: 0"`. `_days() < 0` → out of range → skipped (§2).

### 2. Visibility hook — skip out-of-range widgets per pass

A duck-typed, optional protocol method consulted on every section pass:

- **`should_display(self) -> bool`** — a new optional Widget capability. Widgets that don't define it are always displayed (the default for every existing widget). `_CountWidget.should_display()` returns `self._days() >= 0`.
- **`_expand_sources(...)` in `src/led_ticker/ticker.py`** — which already runs every pass via `_build_ticker_iter` and already filters breaker-disabled widgets — additionally drops any widget whose `should_display()` returns `False`. The check is duck-typed: `not hasattr(w, "should_display") or w.should_display()`. Container-expanded widgets (feed stories) are checked the same way after expansion.
- An out-of-range count widget therefore vanishes from the rotation that pass, re-evaluated next pass (for date math it stays gone once past, but the mechanism is per-pass and general). If a section's widgets are **all** filtered out, the section yields nothing that pass; the engine already handles an empty section cleanly (the `None`-sentinel path in `_run_swap`/`_build_then_enqueue`, ticker.py ~707) — it ends the section and moves on, no crash, no blank held slot.

This hook is intentionally **general** (not countdown-special-cased) so a future visibility-gated widget (e.g. "only during business hours") reuses the same seam.

### 3. Config + wrong-side warning

- TOML for the new widget:
  ```toml
  [[section.widgets]]
  type = "countup"
  text = "Days since launch"
  countup_date = 2026-01-01
  # plus the same optional styling as countdown: font, font_color, border,
  # center, padding, bg_color
  ```
  `countdown` config is unchanged.
- **Config-load warning** (added to `validate_widget_cfg` in `src/led_ticker/app/factories.py`, severity `warning` — non-blocking): a `countup` with a **future** `countup_date`, or a `countdown` with a **past** `countdown_date`, emits a gentle hint (e.g. `"countup_date 2027-01-01 is in the future — this widget won't display until then (did you mean a countdown?)"`). Because it is a warning, it surfaces through the startup-validation report + web "Config validation" card (shipped 2026-06-22) and never blocks the sign. A future `countup_date` can be legitimate (configured in advance), so this is deliberately a warning, not an error.

### 4. Scope / non-goals

- **IN:** the `countup` widget; the shared `_CountWidget` base; `TickerCountdown` moved to `count.py` with back-compat re-export; the `should_display()` visibility hook + `_expand_sources` filter; the unified skip-when-out-of-range behavior (applies to both); the wrong-side validation warning; docs + example-config + drift updates.
- **OUT (YAGNI):** a `direction` param; hours/minutes granularity; a live-ticking variant; configurable `expired_text`/placeholder; auto-detecting direction from past/future (rejected — a silent semantic flip). Richer inline live values are the eventual job of the deferred inline-value-tokens feature.

## Data flow

```
config → TickerCountup(countup_date=…) built like any core widget
section pass → _build_ticker_iter → _expand_sources:
                 filters breaker-disabled  AND  not should_display()
   in range (days ≥ 0)  → enqueued, renders "<text>: <days>"
   out of range (days<0)→ dropped this pass (disappears; all-dropped section → empty, handled)
config load → validate_widget_cfg: wrong-side date → severity="warning"
                → startup-validation report + web "Config validation" card
```

## Testing

- **`_days()` math:** countup → past date positive, today 0, future negative; countdown → future positive, today 0, past negative.
- **`should_display()`:** True at `days ≥ 0`, False at `days < 0`, for both widgets.
- **`_expand_sources` filter:** a widget whose `should_display()` is False is dropped from the pass; a widget without the method is kept; a section whose widgets are all filtered yields nothing and does not crash the run mode (covered by the existing empty-section handling, asserted via a focused test).
- **Behavior-change tripwire:** a `countdown` to a **past** date is now skipped (previously rendered `-N`) — a test that pins the new behavior so a regression is visible.
- **Shared render:** `countup` renders `"<text>: <days>"` and honors `font_color`/border/center exactly like `countdown` (one shared-surface assertion, not a duplicated countdown test suite).
- **Validation warning:** a future `countup_date` and a past `countdown_date` each produce one `severity="warning"` issue from `validate_widget_cfg` (and no error).
- **Back-compat import:** `from led_ticker.widgets.message import TickerCountdown` still resolves after the move.

## Docs

- New `countup` widget page on the docs site (mirrors the `countdown` page; "days since" / "100 days sober" examples). Follow `docs/DOCS-STYLE.md`.
- Update the `countdown` page to document the new disappear-when-past behavior (was: showed a negative).
- Add a `countup` block to an example config; update `tests/test_docs_config_options_drift.py` expectations if the new widget's fields are audited there.
- Changelog note for the countdown behavior change (no config migration required).

## Risks

- **Behavior change to a shipped widget** (countdown disappears past its date). Mitigated: configs stay valid (no migration), the change is documented, and the new validation warning surfaces a wrong-side date. A user who relied on seeing `-N` loses that — judged acceptable (it was never a useful display).
- **New visibility seam in the hot path.** `should_display()` is called once per widget per section pass (not per render tick), duck-typed and cheap; it must never raise (a count widget's `_days()` is pure date math). Existing widgets are unaffected (no method → always shown).
- **All-widgets-skipped section.** Relies on the existing empty-section handling (`None` sentinel) — covered by a test so a future engine change can't silently reintroduce a crash/blank-hold.
