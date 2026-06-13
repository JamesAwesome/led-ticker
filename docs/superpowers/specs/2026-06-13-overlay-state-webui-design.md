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
the render path, and `busy_light.py` / `busy_http.py` / `frame.py` are untouched.

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
  - `ttl_remaining` (float | null): seconds until an armed deadline clears the state,
    computed at pull time from the busy object's monotonic deadline; `null` when no
    deadline is armed (the common case).
  - When the busy light is disabled, this is `{"enabled": false}` and `busy_light` is
    absent from the roster.

**Schema:** `SCHEMA_VERSION` bumps **2 → 3** (the tripwire guards the top-level key
set, so a new key forces the bump — consistent with the swap_count bump to 2).
Version skew during a rolling restart shows the existing "versions out of sync"
envelope briefly; both processes ship in one image and compose restarts both.

## Components

### 1. `status_board.py` — storage + snapshot

- New fields: `overlay_roster: list[dict]` (default `[]`) and `busy: dict`
  (default `{"enabled": False}`).
- `snapshot()` folds them under a single `overlays` key:
  `{"roster": self.overlay_roster, "busy": self.busy}`.
- `SCHEMA_VERSION = 3`; the schema tripwire's expected top-level key set adds
  `overlays`.
- Module-level setters, no-op without an active board (mirroring `record_swap` /
  `record_section`):
  - `set_overlay_roster(roster: list[dict]) -> None` — set once at startup.
  - `record_busy(state: dict) -> None` — called by the heartbeat each beat.

### 2. `run.py` — roster capture + heartbeat busy pull

- **Roster capture:** as overlays are registered, accumulate `(name, kind)` pairs —
  `{"name": "busy_light", "kind": "core"}` when `busy.paint` is appended (inside
  `_start_busy_light`, gated on the busy light being enabled), and
  `{"name": ns, "kind": "plugin"}` per plugin overlay at the plugin-overlay append.
  After both register, call `set_overlay_roster(pairs)` once. Order note:
  `_setup_status_board` runs before overlay registration, so the roster is a separate
  call after registration, not part of board construction.
- **Heartbeat busy pull:** `_status_heartbeat` gains a `busy=None` parameter. When
  `busy` is present, each beat it builds the busy dict (`enabled=True`,
  `active=busy.is_busy`, `source` from the busy config, `ttl_remaining` computed from
  the busy object's deadline) and calls `record_busy(...)`; the build is wrapped so a
  read error logs and publishes without `ttl_remaining` rather than killing the
  heartbeat (which also owns preview-watch and the liveness counter). When `busy` is
  None, it publishes `{"enabled": False}` once and skips thereafter. `run()` passes the
  busy light into the heartbeat spawn (or `None` when the busy light is disabled).
- `busy_light.py`, `busy_http.py`, `frame.py` are NOT modified — the heartbeat reads
  `busy.is_busy` and the deadline; the overlay system never imports the web stack.

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
  `ttl_remaining` number-coerced; no `overlays` key (a pre-v3 display) renders the
  card empty / "not configured", never errors.

## Error handling

- `overlays` is plain snapshot data, so a pre-v3 display, a missing key, or a stale
  file degrade through the status envelope the page already handles.
- The heartbeat's busy read is wrapped: a raise logs and publishes the busy dict
  without `ttl_remaining`, never killing the heartbeat.
- `record_busy` / `set_overlay_roster` are no-ops without an active board.
- No new failure modes on the display side (the heartbeat already runs; this adds one
  read + one setter call per beat).

## Testing

- **`status_board`:** `snapshot()` includes `overlays` with `roster`/`busy`; schema
  tripwire updated to 3 with `overlays` in the key set; `record_busy` and
  `set_overlay_roster` round-trip and no-op without an active board.
- **`run.py`:** roster-capture test (busy light + a fake plugin overlay → both in the
  published roster with correct `kind`); heartbeat test that flips `busy.is_busy` and
  asserts the next published snapshot reflects `active` + `ttl_remaining`; busy-disabled
  path publishes `{"enabled": false}` and omits `busy_light` from the roster.
- **page:** a marker test that the served page references `overlays` and the card id;
  the `/api/status` envelope already tested — `overlays` rides it.
- **back-compat:** a v2-shaped status (no `overlays`) renders the card empty without
  error.

## Out of scope

- Any control path (toggling busy from the page) — breaches the pure-reader invariant;
  `busy_http` `/busy` stays the control surface.
- Per-overlay enable/disable, z-order, or removal — the overlay system is append-only
  by design (a documented YAGNI).
- Real busy sources (calendar/Slack) — still the busy light's own future work,
  unrelated to surfacing the state that already exists.
- The `[busy_light]` / `[web]` port-collision cleanup — a separate, unrelated fix.
