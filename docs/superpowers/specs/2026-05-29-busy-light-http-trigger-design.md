# Dynamic Busy-Light Trigger (HTTP) — Design

**Date:** 2026-05-29
**Status:** Approved (brainstorming complete)
**Builds on:** the shipped busy-light overlay system (PR #133, `ef44a5c`)

## Goal

Let the busy light be flipped on/off **remotely from a work Mac** — by a manual
hotkey macro and/or a macOS Focus automation — instead of only by a local file.
Add an HTTP push *source* to the existing busy-light, keeping the file source as
the unchanged default. Must work on **both** reference builds (smallsign and
bigsign/longboi).

## Context

The shipped busy-light cleanly separates two concerns:

- **Sink / state:** `BusyLight` owns an `is_busy` flag and a `paint(canvas)`
  overlay hook registered on `LedFrame.overlay_hooks`. The painter already
  adapts to any panel (`size` knob: ~3–4px on the 16-tall smallsign, ~8–10px on
  the 64-tall bigsign).
- **Source:** whatever flips `is_busy`. Today that is `BusyLight.update()`,
  which reads `file_path.exists()`, polled by `run_monitor_loop`.

The original spec explicitly anticipated "real busy sources … a new poller whose
`update()` sets the flag." This design adds a *push* source (HTTP) alongside the
*poll* source (file).

## Decisions captured during brainstorming

- **Network topology:** work Mac and Pi are on the **same home LAN**. No relay,
  tunnel, or corporate-firewall traversal needed.
- **Trigger:** **manual hotkey** + **macOS Focus/DND**. Both collapse to the same
  thing on the Mac — *an event runs one HTTP call*. Focus needs **no custom
  background detector**: macOS Shortcuts has a native "When [Focus] turns On/Off"
  personal automation. (Camera/mic auto-detect — which *would* need a daemon —
  was considered and rejected.)
- **Transport:** **HTTP endpoint inside led-ticker.** Evaluated against ZeroMQ,
  MQTT, and SSH-file-touch (see Alternatives). HTTP wins on a LAN because it needs
  **nothing installed on the managed work Mac** (curl + Shortcuts "Get Contents of
  URL" are native) and adds **zero new Python dependencies** — `aiohttp>=3.9` is
  already a runtime dep (client-side, used by every data widget); `aiohttp.web` is
  the server half of that same package.
- **TTL:** **optional, off by default** (`ttl_seconds = 0`).
- **Panel scope:** smallsign **and** bigsign/longboi. The transport is
  panel-agnostic; the only per-Pi difference is how the port is exposed.

## Architecture

```
 Work Mac                                   Raspberry Pi (led-ticker)
 ┌──────────────────────┐                   ┌───────────────────────────────────┐
 │ hotkey macro  ──┐     │   HTTP (LAN)      │  busy_http.serve_busy (aiohttp)   │
 │                 ├──── curl/Shortcuts ───► │   GET/POST /busy?state=on|off     │
 │ Focus autom. ───┘     │   :8080           │        │ set_busy(state)          │
 └──────────────────────┘                   │        ▼                          │
                                            │   BusyLight.is_busy  ──► paint()  │
                                            │        (overlay_hooks, unchanged) │
                                            └───────────────────────────────────┘
```

`source = "file"` (default) → existing file poller. `source = "http"` → the
aiohttp listener. The painter and overlay-hook registration are identical in
both modes.

## Components

### `src/led_ticker/busy_light.py` (modify)

Add to `BusyLight`:

- `set_busy(self, state: bool) -> None` — sets `is_busy`. When `ttl_seconds > 0`
  and `state` is `True`, also records `_busy_until = monotonic() + ttl_seconds`;
  `state=False` clears `is_busy` and `_busy_until` immediately.
- `_busy_until: float | None` (init=False, default None) — monotonic deadline.
- `ttl_seconds: float = 0.0` field (0 = disabled).
- `tick_ttl(self, now: float) -> None` — if `_busy_until` is set and
  `now >= _busy_until`, clear `is_busy`/`_busy_until`. Called by a 1 Hz ticker.
  Kept off the paint path so `paint()` stays paint-only and never computes time
  in the hot loop.

`paint()` and `update()` (file source) are unchanged.

### `src/led_ticker/busy_http.py` (new)

`async def serve_busy(busy, *, host, port, token) -> aiohttp.web.AppRunner`

- One `aiohttp.web.Application` with routes:
  - `GET /busy?state=on|off` and `POST /busy` (state from body or `?state=`):
    call `busy.set_busy(...)`, return `200` + `{"busy": <bool>}`.
  - `GET /busy` (no `state`): return `200` + current `{"busy": <bool>}`.
- **Auth:** if `token` is set, require it via `X-Busy-Token:` header **or**
  `?token=` query param. Missing/wrong → `401`. No token configured → open.
- **State parsing:** accept `on/off`, `1/0`, `true/false` (case-insensitive).
  Anything else → `400`.
- Unknown path/method → `404`/`405` (aiohttp default).
- Returns the started `AppRunner` so the caller can supervise/clean it up.

### `src/led_ticker/app/run.py` (modify)

In the `if config.busy_light.enabled:` block:

- Build `BusyLight(..., ttl_seconds=config.busy_light.ttl_seconds)` and register
  `busy.paint` on `led_frame.overlay_hooks` (unchanged).
- If `source == "file"`: `create_task(run_monitor_loop(busy, poll_interval))`
  (current behavior).
- If `source == "http"`: `create_task(serve_busy(busy, host=..., port=...,
  token=...))`, supervised so a bind/crash **logs loudly and the display loop
  keeps running** — a busy port must never take down the sign.
- If `ttl_seconds > 0`: also start a 1 Hz ticker task calling
  `busy.tick_ttl(monotonic())`.

### `src/led_ticker/config.py` (modify)

`BusyLightConfig` gains:

| Field          | Type  | Default      | Notes                                   |
| -------------- | ----- | ------------ | --------------------------------------- |
| `source`       | str   | `"file"`     | `"file"` or `"http"`.                   |
| `http_host`    | str   | `"0.0.0.0"`  | Listen address (http source).           |
| `http_port`    | int   | `8080`       | Listen port (http source).              |
| `token`        | str   | `""`         | Shared secret; empty = open.            |
| `ttl_seconds`  | float | `0.0`        | `0` = explicit on/off only (no expiry). |

Validation at config-load: `source ∈ {"file","http"}`; `1 ≤ http_port ≤ 65535`;
`ttl_seconds ≥ 0`; `token` is a string. (Existing corner/color/size validation
stays.)

## Data flow

1. Mac event (hotkey or Focus on/off) → one HTTP call to `http://<pi>:8080/busy`.
2. `serve_busy` handler authenticates, parses state, calls `busy.set_busy()`.
3. `set_busy` flips `is_busy` (and arms `_busy_until` if TTL on).
4. Next `LedFrame.swap()` runs `busy.paint()` → dot composites over the frame.
5. (TTL on) the 1 Hz ticker clears `is_busy` after `ttl_seconds` unless refreshed.

## Mac-side recipes

Both terminate in one HTTP call; `<pi>` = `longboi.local` / the smallsign's
hostname / a DHCP-reserved IP.

- **Manual hotkey** (Keyboard Maestro / Raycast / Shortcut with a global key):
  `curl -s "http://<pi>:8080/busy?state=on&token=SECRET"` and an `off` twin.
- **Focus automation** (macOS Shortcuts personal automation, no scripting):
  *When [Work] focus turns On → Get Contents of URL (GET)
  `http://<pi>:8080/busy?state=on&token=SECRET`*; a *turns Off* twin with
  `state=off`.

## Deployment (both Pis)

The listener code is identical; only port exposure differs:

- **Docker deploy** (longboi; smallsign if dockerized): add
  `ports: ["8080:8080"]` to that Pi's compose service.
- **Bare-metal / systemd deploy** (`deploy/led-ticker.service`): the process
  binds the host port directly — no mapping; ensure no host firewall blocks it.

Ship HTTP example config snippets for smallsign **and** bigsign/longboi.

## Error handling

- HTTP server is a **supervised task**: bind failure (port in use) or crash logs
  loudly; the display loop continues. The overlay is simply not remotely
  triggerable until restart.
- Handler is total: bad/missing token → `401`, bad `state` → `400`; no exception
  reaches the loop.
- `paint()` stays paint-only (overlay-hooks invariant); TTL expiry lives in the
  ticker.
- **Caveat (documented):** a token in the query string can appear in server logs
  — acceptable on a trusted LAN; the header form is available for cleanliness.

## Testing

- `busy_http` (via `aiohttp.test_utils.TestClient` under pytest-asyncio):
  GET-query and POST both flip the flag; `401` on bad/missing token when one is
  configured; open when none; `400` on bad state; `GET /busy` reports state.
- TTL: injected/monkeypatched clock (no real sleeps) — `is_busy` clears after the
  window via `tick_ttl`; `on` refreshes; `off` clears immediately.
- Config: validation for source enum, port range, `ttl_seconds ≥ 0`, token type;
  parse round-trip.
- Wiring (`app/run.py`): `source="http"` starts the server and registers `paint`;
  `source="file"` byte-for-byte unchanged.
- Panel-agnosticism: existing paint tests already cover smallsign and bigsign
  canvas sizes — regression-locked.

## Docs

- `concepts/busy-light.mdx`: new "Remote / dynamic trigger (HTTP)" section —
  endpoint, auth, TTL, Docker-vs-bare-metal port exposure for both Pis, and the
  two macOS recipes with exact URLs.
- `reference/config-options.mdx`: the 5 new `[busy_light]` fields. The existing
  drift tripwire `test_busy_light_section_field_set_matches_docs` (it derives the
  documented set from `fields(BusyLightConfig)`) will **force** these rows.
- `CLAUDE.md`: extend the busy-light/overlay invariant — `source` modes, "HTTP
  listener is a supervised task that must never crash the display loop," TTL
  expiry lives in the ticker not paint.

## Alternatives considered

| Transport            | LAN verdict | Why not chosen                                                                                   |
| -------------------- | ----------- | ------------------------------------------------------------------------------------------------ |
| **HTTP (chosen)**    | ✅          | Native on the Mac (curl/Shortcuts), zero new deps (`aiohttp.web`), fits the asyncio design.       |
| ZeroMQ (user's idea) | feasible    | Heaviest for a 1-bit/hour signal: needs `pyzmq`/libzmq on the **managed work Mac** AND the ARM Docker image; no built-in auth/TLS; its fan-out/throughput strengths are wasted here. |
| MQTT broker          | feasible    | A whole broker to run for one bit on a LAN. The "right" answer only if this grows to many signals or goes cross-network later. |
| SSH file-touch       | feasible    | Zero led-ticker code (reuses file source), but pays SSH-handshake latency per toggle and needs a key on the Pi. Kept as a no-code fallback, not the build. |

## Out of scope (YAGNI)

- Camera/mic auto-detection (needs a Mac daemon).
- Cross-network / cloud relay (ntfy, hosted MQTT) — revisit if topology changes.
- Multiple simultaneous sources (file AND http at once) — `source` selects one.
- Multi-color / multi-state busy (e.g. "in a meeting" vs "heads down") — single
  boolean for v1.
