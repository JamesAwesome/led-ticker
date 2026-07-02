# Monitor-registration hardening — design

**Date:** 2026-07-01
**Status:** Approved (extends the shipped monitor-health feature, v4.2.0 / #340; see `2026-07-01-monitor-health-webui-design.md`).

## Goal

Remove the structural conditions that made the Container-exclusion bug (caught by the antagonistic review of #340) possible, so that class of bug — a `run_monitor_loop` rider silently missing from the Monitors panel because a shape allow-list didn't anticipate it — cannot recur.

## The trap being disarmed

Three layers compounded in #340's original gate:
1. **Intuitive-but-wrong model** — "widgets have `.draw`"; real data widgets ride the loop as Containers (`feed_stories` + `update()`, no `.draw`).
2. **Silent failure** — an unmatched shape was skipped with no log; absence reads as "working."
3. **Tests that confirmed instead of caught** — the fake was given a synthetic `.draw` to match the wrong model.

The shipped fix (`draw OR feed_stories`) corrects the *instance*; this hardening removes the *mechanism* (the allow-list itself).

## Design

### 1. Invert the default: register everything, opt out explicitly

`run_monitor_loop` gains a keyword-only param:

```python
async def run_monitor_loop(
    widget: Updatable,
    interval: float,
    splay: bool = True,
    immediate: bool = False,
    register_monitor: bool = True,
) -> None:
```

- `register_monitor=True` (default): the rider is ALWAYS registered in the status board's monitor roster. No shape detection decides registration.
- `register_monitor=False`: explicit opt-out for riders that are not data monitors. The ONLY current opt-out is busy_light — `app/run.py`'s `_start_busy_light` spawn passes `register_monitor=False`.
- Keyword-only with a default → zero plugin changes; the docs API-reference call shape `run_monitor_loop(widget, interval)` remains valid.

**Effect on the failure mode:** an unanticipated future shape goes from *invisible monitor* (silent absence) to *visible row with a possibly-generic tag* (cosmetic, self-announcing). Audit note: every current rider (polled sources; the 10 plugin data widgets — baseball×5, calendar, crypto, pool, rss, weather) already matched the old allow-list, so this changes zero current registrations.

### 2. The gate shrinks to an explicit marker

With registration unconditional, kind detection is no longer a gate — just a tag:

```python
kind = "source" if getattr(widget, "polled", False) else "widget"
```

- `.polled` is an explicit, intentional marker (`DataSource` sets it deliberately) — not inferred structure.
- The `hasattr(draw) or hasattr(feed_stories)` shape checks are DELETED from `run_monitor_loop`. There is no allow-list left to be wrong.
- The kind set stays closed: `{"source", "widget"}`. No schema change (SCHEMA_VERSION stays 9), no webui change (it already renders `esc(m.kind || "")` safely), no docs-state change ("covers sources and data widgets automatically" remains true).
- The existing registration block's structure is otherwise preserved: `_mon_name` default `None`, the whole block inside `contextlib.suppress(Exception)`, `_monitor_type`/`_monitor_value` unchanged.

### 3. Make registration (and the opt-out) audible

- On registration, one INFO log at loop start: `monitor loop started: <name> (<kind>, every <interval>s)` — a boot-time roster in the log stream. Precedent: the repo already logs per-update at INFO ("RSS BBC updated: 5 stories"); one line per monitor per boot is strictly quieter.
- On opt-out (`register_monitor=False`), one DEBUG log: `monitor loop started (unregistered): <classname>` — intentional exclusions are auditable but not noisy.
- Logs sit inside the existing suppressed registration block where they use `_mon_name` (never raise into the loop); the opt-out DEBUG can log the classname directly.

### 4. Anchor tests to reality (no-circular-golden-tests)

- **`test_unknown_shape_registers_by_default`** — an object with ONLY `update()` (no `polled`/`draw`/`feed_stories`) registers with `kind == "widget"`. This is the tripwire that kills the bug class: any future allow-list regression fails it.
- **`test_register_monitor_false_excludes`** — `register_monitor=False` → the rider never appears in `board.monitors` (replaces/extends the current busy-light-like exclusion test, which now tests the kwarg rather than shape-fallthrough).
- **AST/grep tripwire** — assert `app/run.py`'s busy_light `run_monitor_loop(...)` call passes `register_monitor=False` (pins the opt-out against accidental removal; repo precedent: `tests/test_engine_redraw_contract.py`, the container-refresh AST test).
- **Protocol-anchored fakes** — the container-shaped fakes in `tests/test_status_instrumentation.py` gain `assert isinstance(fake, Container)` (the `@runtime_checkable` Protocol; verified to work for both class-level and instance-set `feed_stories`). A fake that drifts from the real Container shape now fails loudly instead of enshrining a wrong model.
- Existing tests (container registers, source kind, never-raise, retry_in, self-heal) must keep passing unchanged in intent; the busy-light test updates from shape-based to kwarg-based exclusion.

### 5. Paper for the next reader

- **CLAUDE.md** — add to the load-bearing invariants (near the Container-widget bullet): monitors register by DEFAULT; `register_monitor=False` is the explicit opt-out (busy_light only); kind = `.polled` → source, else widget — never reintroduce a shape allow-list for registration; name the tripwires.
- **Docs site** — optional single-line touch to the Plugin API reference `run_monitor_loop` row noting the `register_monitor=True` default; no other docs change (the feature docs' claims are unchanged).

## Constraints (inherited from #340)

- Never raise into the poll loop (the registration block stays fully suppressed; logging included).
- Core-only; zero plugin changes; the public surface only grows (keyword-only + default).
- No schema bump; kinds stay `{"source","widget"}`.
- PEP 649; worktree + PR; gates: `uv run --extra dev pytest`, `ruff check`, `ruff format --check`, `pyright`; STOP at the open green PR (explicit merge approval per PR).

## Out of scope

Plugin self-declared kinds (`monitor_kind: str` param) — YAGNI until a plugin actually needs a kind the marker can't infer; the bool leaves room to add it later. Any webui change. Any new kind string.

## Sizing

~15 lines in `src/led_ticker/widget.py`, 1 line in `src/led_ticker/app/run.py`, ~4 test additions/updates across `tests/test_status_instrumentation.py` (+ the AST tripwire file), 1 CLAUDE.md bullet, optional 1-line docs touch. Single-task execution (one implementer + one reviewer), not a multi-task SDD.
