# Web status UI — design

**Date:** 2026-06-10
**Status:** approved design, pre-implementation
**Origin:** #1 on the LEDMatrix-comparison adoption list — a web surface is the single
biggest adoption blocker for external users.

## Summary

A read-only web status UI for led-ticker, delivered as a **sidecar process**
(`led-ticker webui`) that shares the existing Docker image with the display process.
The display process publishes state to a versioned `status.json` file; the sidecar
serves a single tabbed HTML page (Status / Config / Validate) plus a small JSON API.
No write path to the running display in v1: the sidecar shows what's happening,
renders the live config (secrets redacted), and validates candidate TOML in the
browser. Changes are still applied by hand — the config file remains the sole
source of truth.

## Decisions (with rationale)

| Decision | Choice | Why |
|---|---|---|
| Audience | Future external users | Adoption play; pairs with going public. Polish bar is "a stranger's first sign," not "the author's ops tool." |
| v1 scope | Status + validate, read-only | No second writer to the config (the LEDMatrix comparison's do-not-copy lesson); no conflict with the `:ro` config mount. |
| Architecture | Sidecar process, same image | Privilege separation (display runs privileged for GPIO; web runs unprivileged), render loop physically isolated from web traffic and validation CPU (GIL contention), independent restart/upgrade, and the right shape for future write-path features (apply-config, scheduling, preview). The deployment cost mostly evaporates because the example `compose.yaml` ships the second service. |
| Auth | Optional shared token, default open | Matches the `busy_http` precedent. Secrets are redacted from the config view regardless of auth. LAN-appliance assumption; reverse-proxy for anything else (documented). |
| Page layout | Tabbed: Status / Config / Validate | The validate tool wants editor + results space; the glance view stays uncluttered for the "is my sign okay" check. |
| Frontend | One static HTML file, vanilla JS, no build step | The repo has no frontend toolchain and this keeps it that way. The page polls `/api/status` every ~3 s. |

## Component 1: status publishing (display process)

New module `src/led_ticker/status_board.py`.

- `StatusBoard` (attrs class) collects state; `publish()` atomically writes JSON
  (write temp file + `os.replace`, same pattern as the busy file). Top-level
  `"schema": 1` field versions the contract.
- **Single writer:** the display process. The sidecar never writes.
- Published content:
  - **Startup, once:** `started_at`, hostname (the page's header identity),
    config path, display geometry (panel size, scale), loaded plugins
    (namespace, version, registered widgets/transitions/emoji), failed plugins.
  - **Section start** (hook in `app/run.py`'s section loop): section name/index,
    mode, widget count. Triggers an immediate publish.
  - **Widget visit** (hook at the ticker's per-widget dispatch): short summary of
    the current widget (type + text/source preview).
  - **Monitor liveness:** one hook in `run_monitor_loop()` records
    `last_update[name] = timestamp` — covers every async data widget and container
    with a single call site.
  - **Log tail:** a bounded `logging.Handler` keeping the last ~50 records at
    WARNING and above, serialized into the file.
- **Throttling:** dirty flag + minimum write interval (~2 s); section changes
  publish immediately. Boundary-driven only — never per-tick.
- **Gating:** publishing happens only when a `[web]` block is present in the
  config. Absent block = zero new behavior for existing installs.
- **Failure rule (inherited from overlay hooks):** an exception inside `publish()`
  (disk full, permissions, serialization bug) logs once at WARNING and disables
  publishing for the session. The render loop never sees it; the panel keeps
  running. The sidecar then reports the stale/missing file honestly.

## Component 2: the `webui` sidecar

New CLI subcommand `led-ticker webui --config config.toml` (sibling of
`validate`), plus a module (e.g. `src/led_ticker/webui.py`) following the
`busy_http` shape: `build_webui_app()` is pure for testing; `serve_webui()` is
the production runner.

- Runs **unprivileged**. Importing the module must not import `rgbmatrix`
  (explicit invariant with a tripwire test; the `_compat` shim already makes
  this achievable).
- Reads the same `[web]` config block as the display process:

  ```toml
  [web]
  host = "0.0.0.0"     # default
  port = 8080           # default
  token = ""            # default: open; non-empty enables auth
  status_path = "/run/led-ticker/status.json"  # default; the Docker compose
                        # example overrides this to the shared volume path
  ```

- Routes:

  | Route | Behavior |
  |---|---|
  | `GET /` | The status page (single static HTML file shipped as package data) |
  | `GET /api/status` | Reads + parses `status.json`, adds the staleness verdict, returns JSON |
  | `GET /api/config` | Live `config.toml` as text, redacted, plus resolved geometry |
  | `POST /api/validate` | Body = candidate TOML (1 MB cap) → validate engine → issues as JSON |

- **Auth:** `X-Web-Token` header or `?token=` query, checked on every route
  including `/`. Empty configured token = open.
- **Redaction:** key-name pattern match (`token`, `*key*`, `secret`, `password`,
  `webhook`) replaces values with `•••` in `/api/config` output. Pure function,
  exhaustively tested — a redaction miss is the worst failure in a read-only
  design. Applies regardless of auth state.
- **Validation:** the same code path as the CLI. `validate.py` gains a
  **from-string entry point** (chosen over temp-file plumbing; benefits the CLI
  too). MigrationErrors and coerce warnings return as structured issues with the
  same rule numbers the CLI prints.
- **Staleness:** the sidecar compares the file's embedded timestamp to now; older
  than ~3× the publish interval flips the UI's live indicator to
  "● stale since HH:MM". This catches a dead display process with no extra
  mechanism.

## Page design

Tabbed layout (wireframe C from the brainstorm):

- **Status tab:** header strip (hostname, uptime, live/stale dot) · now-playing
  hero (section name/index, mode, current widget preview) · health panel
  (monitor last-update table, failed plugins, log tail) · plugins panel
  (namespace, version, what each registered).
- **Config tab:** full-height read-only view of the redacted live TOML, plus
  resolved display geometry.
- **Validate tab:** editor pane (paste/upload TOML) on the left, issues table
  (rule number, severity, message — CLI parity) on the right.

## Error handling

Governing rules: **nothing on the web path may ever affect the panel**, and
**the sidecar degrades gracefully when the display side is absent.**

- `status.json` missing → friendly first-run/empty state ("display process
  hasn't published yet — is led-ticker running? is `[web]` configured?"), not an
  error page.
- Malformed or wrong-schema JSON → degraded state naming the mismatch
  ("status schema 2, this UI understands 1 — versions out of sync").
- Stale timestamp → live dot flips to stale, page keeps rendering last-known data.
- `POST /api/validate` failures are *results*, not errors: parse explosions and
  MigrationErrors return 200 with a structured issue list. Only oversize body
  (413) and bad auth (401) are HTTP errors.
- Config file unreadable from the sidecar → the Config tab shows the failure
  reason; Status and Validate tabs keep working. Tabs fail independently.
- **Startup order is irrelevant:** either process may start first; each side's
  degraded states cover the other's absence. No compose health-check dependency.

## Testing

- **Status contract:** round-trip (`StatusBoard` → publish → parse); a schema
  tripwire that fails when the published field set changes without bumping
  `"schema"`; atomicity via the temp + `os.replace` pattern (no partial reads).
- **Publisher discipline:** `publish()` raising never propagates (mirror of the
  overlay-hook rule); throttle behavior (N dirty-marks within the interval → 1
  write; section change → immediate write).
- **Engine instrumentation:** `run_monitor_loop` hook records a timestamp on
  every monitor update; section/widget boundary hooks get behavioral tests
  against the existing mock-frame fixtures.
- **Sidecar app:** `build_webui_app()` route tests via `aiohttp.test_utils` —
  auth (token/open), redaction (exhaustive key cases: `api_key`, `token`, nested
  tables, arrays), staleness verdicts, missing/malformed/wrong-schema status
  files, 413 on oversize validate bodies.
- **Validate-from-string:** parity tests against the file-path entry point (same
  config → same issues both ways).
- **Import purity tripwire:** importing the webui module must not import
  `rgbmatrix` — in the spirit of the existing AST meta-tripwires.
- No browser-automation tests: the page is one static file polling JSON; the API
  tests carry the weight. Manual check on real hardware, as usual.

## Deployment

- **Docker:** the example `compose.yaml` gains a `webui` service — same image,
  `command: led-ticker webui --config /code/config/config.toml`, config mounted
  `:ro`, a small shared volume (or tmpfs mount) for `status.json`, port 8080.
  The display service is unchanged except the shared status mount.
- **Bare metal:** new `deploy/led-ticker-webui.service` unit running as a
  non-root `User=`; `status_path` defaults under `/run/led-ticker/` (tmpfs — no
  SD-card wear).
- **Docs:** one new docs-site page following `docs/DOCS-STYLE.md`;
  `config.example.toml` gains a commented-out `[web]` block. The existing
  config-options drift test keeps the reference page honest.

## Explicitly out of scope for v1 (future shape)

- Any write path to the running display: config apply/restart, busy-light
  toggle, brightness/scheduling. When these arrive, the sidecar is the right
  host: it validates and writes the config *file* (still the sole source of
  truth) and bounces the display service — never reaching into the running
  process. The busy toggle composes for free via the existing `.busy` file the
  file-poller already reads.
- Live panel preview (LEDMatrix-comparison steal #2): would be file-published
  PNG frames from a shadow recorder, served by this same sidecar — no
  architectural change needed.
