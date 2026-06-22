# Design: Validate the config at startup

**Date:** 2026-06-22
**Status:** Approved for planning

## Motivation

The sign process (`run()`) loads plugins, loads the config, and **builds widgets/transitions directly — it never validates the config first.** Problems surface one at a time at build time: a bad widget type is caught + skipped by `_build_widget_guarded` (logged via `logging.exception`), and a bad transition now degrades to cut via `_build_trans_obj_guarded` (#260). So the sign no longer *crashes* on a bad config, but an operator discovers each problem as a separate crash/skip/log trace as sections cycle — never a single clear picture.

`validate_config` already exists (used by `led-ticker validate` and the hot-reload path) and produces a complete structured `ValidationResult` (all `errors` + `warnings`, each with rule, location, message, fix). This feature runs it once at startup and surfaces the **full report up front** — in the logs and on the web status UI — so the operator sees every problem (e.g. all the stale `feeds.*`/`arcade.*` names) at boot.

This is **purely additive diagnostics.** It does not change whether the sign boots: the existing guards still degrade invalid parts, and the sign always runs.

## Decisions (settled at brainstorm)

- **Log-and-continue, never fatal.** Errors are reported, the sign boots anyway, the guards degrade the bad parts. No blocking, no strict mode, no config knob (always-on; it's cheap).
- **Surface in logs AND the status board / web UI.**
- **`config_validation` is startup-only** — distinct from the existing `last_reload` (hot-reload outcomes). Reloads keep using `last_reload`; they don't touch `config_validation`.
- **Schema bump 5 → 6** to add the field past the top-level-keys tripwire.

## Architecture

### 1. Startup validation step (`src/led_ticker/app/run.py`)

In `run()`, after plugins load + `load_config` (so plugin-provided types resolve — installed plugins validate correctly; only genuinely-unknown names flag) and the existing coerce-warning surfacing, and **before** the render loop, add:

```python
result = await validate_config(config_path)
_log_validation_report(result)            # see below
status_board.record_config_validation(result)
```

Then proceed exactly as today (build sections; the guards degrade any invalid widget/transition).

- **Placement:** alongside the existing coerce-warning drain (~`run.py:451`), after `load_config` and after plugins are loaded (plugins load before `load_config` today, so plugin types are already resolvable at this point).
- **`validate_config` is async** (the reload path already `await`s it) — call it with `await`.
- **Never raises into the loop:** `validate_config` already "never raises" per its contract; wrap defensively only if needed so a validator bug can't stop the sign from booting.

### 2. Log report

A small helper logs the result, reusing the CLI's human formatter as the single source of truth for how a validation result reads:

- **Clean config** (no errors, no warnings): one `INFO` line, e.g. `config validated — no issues`.
- **Issues present:** one `WARNING` summary line —
  `config validation: <N> error(s), <M> warning(s) — the sign will run, degrading invalid widgets/transitions; fix and restart (or run \`led-ticker validate\`)` —
  followed by the per-issue lines exactly as `led-ticker validate` prints them (location · rule · message · fix), via the CLI's existing `_format_human` (or a shared formatter extracted from it; do not duplicate the formatting logic).
- Log under the existing `root`/module logger used at startup. Errors are logged at WARNING level (not ERROR) because the sign continues — the framing makes clear it's running-but-degraded, not failing.

### 3. Status board field (`src/led_ticker/status_board.py`)

- Add a `config_validation` key to `StatusBoard.snapshot()`:
  ```
  "config_validation": {
      "at": <iso8601 ts>,
      "errors":   [ {rule, location, message, fix}, ... ],
      "warnings": [ {rule, location, message, fix}, ... ],
  }
  ```
  Empty (`{}`) until set; set once at boot.
- Add `record_config_validation(result)` mirroring `record_reload`: instrumentation-only, never raises into the engine, calls `publish(force=True)`.
- **Bump `SCHEMA_VERSION` 5 → 6** and update the top-level-keys tripwire test that guards the snapshot key set.
- Reflects **this boot's** config health. A reload only ever swaps in a *valid* config (the reload path rejects invalid ones, recording why in `last_reload`), so `config_validation` is only meaningfully non-empty at startup; it is not updated on reload.

### 4. Web status UI (`src/led_ticker/webui/static/index.html`)

- Add a **"Config validation"** card on the Status tab, mirroring the existing `last-reload-card` (hidden by default, shown when populated).
- Render from `status.config_validation`: a summary (`config: N errors, M warnings`) + the issue list (location · message · fix), all escaped via the page's `esc` helper. Hidden when clean (no errors and no warnings).
- Read-only display; no new endpoint (it rides the existing `/api/status` payload).

## Data flow

```
run(): load plugins → load_config → [validate_config(path)] ──┬─► _log_validation_report (logs)
                                                              └─► record_config_validation → status.json
                                                                            │
                                            web /api/status  ◄──────────────┘  → "Config validation" card
        …then build sections; existing guards degrade invalid widgets/transitions (sign boots regardless)
```

## Testing

- **run() startup:** a config with known-bad types logs the formatted report (caplog asserts the WARNING summary + the per-issue lines) AND `record_config_validation` populates the snapshot field; a clean config takes the "no issues" INFO path and leaves `config_validation` empty. The sign proceeds to build either way (no raise).
- **status_board:** the SCHEMA_VERSION top-level-keys tripwire is updated to include `config_validation`; a snapshot round-trips the field; `record_config_validation` is instrumentation-only (no-op when no active board, never raises).
- **web UI:** a static/handler test that the card renders from a `config_validation` payload and is hidden when clean — matching the existing `last-reload-card` test pattern.
- **No behavior-change tests for the guards:** they already cover "sign still runs with bad types"; this feature only adds reporting.

## Scope / non-goals

- IN: startup `validate_config` call + log report (reusing `_format_human`); `config_validation` status field + `record_config_validation` + schema bump; web "Config validation" card.
- OUT: blocking/strict mode (chosen log-and-continue); any new config knob (always-on); changes to hot-reload (it already validates + gates via `last_reload`); changes to the degrade guards.

## Risks

- **Schema bump** touches the status-snapshot contract — the webui sidecar and any integration reading `status.json` must tolerate schema 6. The webui already classifies schema mismatch (`_read_status` → `schema_mismatch` state); a stale sidecar against a newer display surfaces that cleanly rather than crashing. The card degrades to absent if `config_validation` is missing.
- **Double validation cost at boot** is negligible (validate_config is the same work `led-ticker validate` does once; it runs once at startup, not per tick).
