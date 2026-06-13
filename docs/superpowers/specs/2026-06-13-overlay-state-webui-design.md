# Overlay / busy-light state in the web UI (read-only) — design

**Date:** 2026-06-13
**Status:** approved design, pre-implementation
**Builds on:** the web status UI (PRs #192/#196/#197/#199). All standing invariants
carry forward: the sidecar is a pure reader; the web path never affects the panel;
status is JSON, never-500; rgbmatrix import purity; the overlay system stays
mechanism-only and unaware of the web stack.

## Summary

Surface the display's overlay state on the status page, read-only: the busy-light's
semantic state (configured / active / source / ttl-remaining) plus a roster of every
overlay hook compositing onto the panel (busy-light + plugin overlays). The display
process publishes this into `status.json`; a new Overlays card on the Status tab
renders it from the poll already running. No new endpoint, no new process, nothing on
the render path; `busy_http.py` / `frame.py` are untouched and `busy_light.py` gains
only one read-only accessor — the overlay system still imports nothing from the web
stack (dependency stays web→busy).

## Why this shape

The overlay system (`LedFrame.overlay_hooks`) and the busy light are deliberately
decoupled from the web UI today — their only contact is incidental: the busy dot's
pixels appear in `/api/preview` because hooks paint the canvas before capture, but the
UI has no busy *semantics*. This feature adds semantic read-only visibility through the
one shared channel both processes already use — the tmpfs `status.json` — without
giving the overlay code any knowledge of the web stack. Static roster data is captured
where the names are known (registration in `run()`); dynamic busy state is pulled by
the heartbeat that already runs every beat. A control path (toggling busy from the
page) is explicitly out of scope — it would breach the pure-reader invariant; the
existing `busy_http` `/busy` route remains the control surface.

## Data model

A new top-level `overlays` key in the status snapshot:

```json
"overlays": {
  "roster": [
    {"name": "busy_light", "kind": "core"},
    {"name": "acme.clock", "kind": "plugin"}
  ],
  "busy": {"enabled": true, "active": false, "source": "file", "ttl_remaining": null}
}
```

- **`roster`** — static, written once at startup. Every registered overlay hook as
  `{name, kind}`. `kind` is `"core"` (the busy light) or `"plugin"` (a plugin overlay,
  whose `name` is its namespace, e.g. `acme.clock`). Names come from the registration
  site in `run()`, NOT from introspecting the `Callable` list (a bound method /
  `_guarded_overlay` closure has no clean name). Empty list when nothing is installed.
- **`busy`** — dynamic, refreshed by the heartbeat each beat:
  - `enabled` (bool): is the busy light configured/running at all.
  - `active` (bool): `busy.is_busy` at pull time.
  - `source` (str): `"file"` | `"http"`.
  - `ttl_remaining` (float | null): a RELATIVE remainder — seconds-from-now until an
    armed deadline clears the state — computed at pull time as
    `max(0, _busy_until - monotonic())`; `null` when no deadline is armed (the common
    case). Publish the remainder, never the raw monotonic deadline: the browser renders
    "clears in Ns" directly and never compares it to the wall-clock `published_at`, so
    the monotonic/wall-clock mismatch never bites.
  - When the busy light is disabled, this is `{"enabled": false}` and `busy_light` is
    absent from the roster.

**Schema:** `SCHEMA_VERSION` bumps **2 → 3** (the tripwire guards the top-level key
set, so a new key forces the bump — consistent with the swap_count bump to 2). The
tripwire test pins both the key set AND a literal `== 2` (`test_status_board.py`); BOTH
must change.

**Version-skew behavior — stated honestly.** A schema bump makes the skew all-or-
nothing, NOT a gracefully-degraded card. When the sidecar is v3 and the display still
writes v2 (the brief rolling-restart window), `_read_status` returns
`{"state": "schema_mismatch"}` with no `status` payload, and the page shows its global
"versions out of sync" banner for the WHOLE page — not a populated page with an empty
Overlays card. Both processes ship in one image and compose restarts both, so the
window is seconds. The page's defensive "tolerate a missing `overlays` key" coding is
still correct (cheap, guards against a same-image-new-HTML/old-data transient), but it
does NOT deliver per-card graceful degradation across a version skew — the envelope is
all-or-nothing. (Do not write a test asserting "v2 status renders an empty card": that
path is unreachable — a v2 status never gets past `_read_status` to the renderer.)

## Components

### 1. `status_board.py` — storage + snapshot

- New fields: `overlay_roster: list[dict]` (default `[]`) and `busy: dict`
  (default `{"enabled": False}`).
- `snapshot()` folds them under a single `overlays` key:
  `{"roster": self.overlay_roster, "busy": self.busy}`.
- `SCHEMA_VERSION = 3`; the schema tripwire's expected top-level key set adds
  `overlays`.
- Module-level setters, no-op without an active board:
  - `set_overlay_roster(roster: list[dict]) -> None` — set once at startup.
  - `record_busy(state: dict) -> None` — called by the heartbeat each beat.
- **COST-CRITICAL: both setters are pure setters with NO `publish()`** — mirror the
  shape of `record_swap` (a bare field assignment), NOT `record_section` (which calls
  `publish(force=True)`). The heartbeat already calls `board.publish()` once per beat
  on the next line, so the stored busy dict serializes for free. If `record_busy`
  copies `record_section`'s publish, the heartbeat double-writes tmpfs every beat and
  the "zero extra I/O" property is lost. Heartbeat order is `record_busy(state)` THEN
  the existing `board.publish()`.

### 2. `run.py` — roster capture + heartbeat busy pull

- **Roster capture:** as overlays are registered, accumulate `{name, kind}` dicts.
  `run()` already gates on `config.busy_light.enabled` at the busy-light call site, so
  `run()` synthesizes `{"name": "busy_light", "kind": "core"}` itself when enabled
  (`_start_busy_light` just returns the `BusyLight`, unchanged in shape); and
  `{"name": ns, "kind": "plugin"}` per plugin overlay at the existing
  `for ns, paint in plugins.overlays` loop (the namespace `ns` is the in-scope loop
  variable). After both register, call `set_overlay_roster(pairs)` once. Order: the
  roster call lands AFTER overlay registration (`_setup_status_board` runs before
  registration, so this is a separate later call, not part of board construction).
- **Bind the busy object.** Today `run()` discards `_start_busy_light`'s return
  (`await _start_busy_light(...)` with no assignment). Bind it
  (`busy = await _start_busy_light(...)`, or `None` when disabled) so it can be threaded
  into the heartbeat.
- **Heartbeat spawn ORDER (the main pitfall).** The heartbeat is currently spawned
  BEFORE busy-light setup, so the busy object does not yet exist at the spawn site. The
  heartbeat spawn must MOVE to after busy-light setup, preserving its existing
  preview-tee wiring. (This is a reorder of two adjacent setup lines inside the same
  `try`, not a structural change; re-verify the status-board lifecycle tripwires still
  pass.)
- **Heartbeat busy pull:** `_status_heartbeat` gains a `busy=None` parameter AND a
  `busy_source: str = "file"` parameter (the source string is config-level, NOT on the
  `BusyLight` object — it must be threaded in separately). When `busy` is present, each
  beat it builds the busy dict (`enabled=True`, `active=busy.is_busy`,
  `source=busy_source`, `ttl_remaining=busy.ttl_remaining()`) and calls
  `record_busy(...)` BEFORE the existing `board.publish()`; the build is wrapped so a
  read error logs and stores the dict without `ttl_remaining` rather than killing the
  heartbeat (which also owns preview-watch and the liveness counter). When `busy` is
  None, it records `{"enabled": False}` once and skips thereafter.
- **`busy_light.py` gains ONE read-only accessor; `busy_http.py` and `frame.py` are
  untouched.** Add `BusyLight.ttl_remaining(now=None) -> float | None` returning
  `max(0.0, self._busy_until - monotonic())` when a deadline is armed else `None` —
  symmetric with the existing `tick_ttl(now=None)`, which already reads `_busy_until`.
  This keeps the private deadline encapsulated (the heartbeat never reaches
  `_busy_until` directly, so a future rename can't silently break it) while preserving
  the REAL decoupling invariant: `busy_light.py` still imports nothing from the web
  stack — the dependency direction stays web→busy, never busy→web.

### 3. The page — Overlays card

A new card on the Status tab, after Health and Plugins, rendered from
`lastStatus.overlays` (the existing 3s `/api/status` poll — no new fetch):

- **Busy indicator** (top): when `overlays.busy.enabled`, a dot + label —
  "● busy" when `active`, "○ free" otherwise — with `source` and, if
  `ttl_remaining` is set, "clears in Ns". When `enabled` is false: muted
  "busy light not configured".
- **Overlay roster** (below): one row per entry — `name` + a `core`/`plugin` kind
  tag. Empty roster → muted "no overlays installed".
- Page conventions: dynamic strings (`name`, `source`) through `esc()`;
  `ttl_remaining` number-coerced; a missing `overlays` key (defensive, e.g. a
  same-image new-HTML/old-data transient) renders the card empty / "not configured"
  rather than throwing — but note this is NOT the version-skew path (see Data model:
  a true v2/v3 skew is caught earlier as a global `schema_mismatch` envelope).

## Error handling

- `overlays` is plain snapshot data carried by the existing status envelope. A true
  version skew is caught as a global `schema_mismatch` (whole-page banner, not a
  per-card degrade — see Data model); a defensively-missing key on an otherwise-valid
  status renders the card empty.
- The heartbeat's busy read is wrapped: a raise logs and stores the busy dict
  without `ttl_remaining`, never killing the heartbeat.
- `record_busy` / `set_overlay_roster` are no-ops without an active board.
- No new failure modes on the display side (the heartbeat already runs; this adds one
  read + one setter call per beat).

## Testing

- **`status_board`:** `snapshot()` includes `overlays` with `roster`/`busy`; schema
  tripwire updated to 3 — BOTH the expected key set (add `overlays`) AND the literal
  `== 2` assertion bump to `== 3`; `record_busy` and `set_overlay_roster` round-trip
  and no-op without an active board.
- **no-double-write (cost guard):** assert `record_busy` does NOT itself write the
  status file — e.g. call `record_busy(...)` on an active board and confirm no flush
  happened (no file written / write-count unchanged) until `publish()` is called. This
  pins the `record_swap`-shape (pure setter) contract that the zero-extra-I/O property
  depends on.
- **`busy_light`:** `ttl_remaining()` returns `None` with no deadline armed, a positive
  remainder when armed, and `0.0` (never negative) past the deadline — mirroring the
  existing `tick_ttl` tests' use of an injected `now`.
- **`run.py`:** roster-capture test (busy light + a fake plugin overlay → both in the
  published roster with correct `kind`); heartbeat test that flips `busy.is_busy` and
  asserts the next published snapshot reflects `active` + `ttl_remaining` (with
  `busy_source` threaded through); busy-disabled path records `{"enabled": false}` and
  omits `busy_light` from the roster; a tripwire that the heartbeat is spawned AFTER
  busy-light setup (the busy object must exist at the spawn site).
- **page:** a marker test that the served page references `overlays` and the card id;
  the `/api/status` envelope already tested — `overlays` rides it. (No version-skew
  card test — that path is unreachable; a v2 status is caught as `schema_mismatch`
  before the renderer.)

## Out of scope

- Any control path (toggling busy from the page) — breaches the pure-reader invariant;
  `busy_http` `/busy` stays the control surface.
- Per-overlay enable/disable, z-order, or removal — the overlay system is append-only
  by design (a documented YAGNI).
- Real busy sources (calendar/Slack) — still the busy light's own future work,
  unrelated to surfacing the state that already exists.
- The `[busy_light]` / `[web]` port-collision cleanup — a separate, unrelated fix.
