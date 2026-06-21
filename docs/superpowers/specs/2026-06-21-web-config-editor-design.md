# Design: Edit the running config from the web UI

**Date:** 2026-06-21
**Status:** Approved for planning
**Depends on:** [Secrets out of config.toml, into env](2026-06-21-secrets-to-env-design.md) (Spec A) — lands first.

## The core insight

Config **hot-reload** (PR #250) is already the apply engine: the display process watches `config.toml` (mtime + content hash via `ConfigWatcher`), runs `load_and_validate` (validation gates the swap — a bad config never reaches the loop), and applies changes at the next render cycle (`_apply_reload`: evicts changed/removed widgets + cancels their tasks, resets the render breaker, respawns the schedule ticker). Restart-required fields are already detected (`nonreloadable_changed`) and recorded (`status_board.record_reload`).

So this feature adds **zero apply code to the display process.** It only needs to *safely produce a valid write to `config.toml`*; the running display adopts it on its own. The work is: a write surface + an editor UI + closing the feedback loop.

## Posture change (explicit)

The webui is today an **unprivileged, read-only sidecar** — its module docstring states it "never writes status.json and never touches the config file." This spec **deliberately changes that** to: *read + **token-gated** config writes.* The docstring/contract and `CLAUDE.md` are updated to match. The webui remains a separate process from the display; it does not import or apply config — it only writes the file the display already watches.

## Architecture / data flow

```
browser editor ──PUT /api/config (TOML + base-hash, token)──▶ webui process
                                                                │ validate_config_text
                                                                │ conflict-check (base-hash vs disk)
                                                                │ backup → atomic write
                                                                ▼
                                       config.toml  (host bind mount, :rw for webui)
                                                                │  (display sees it :ro)
                                                                ▼
                                  display ConfigWatcher → load_and_validate → _apply_reload
                                                                │
                          browser polls GET /api/status ◀───────┘  (applied live / restart-required)
```

## Components

### 1. Save endpoint — `PUT /api/config` (webui, auth-required)
Handler steps, in order:
1. **Auth + write-guard.** Require a configured token (see §4); reject with `403` if the instance is open (no token).
2. **Body limits.** Reuse the existing `MAX_VALIDATE_BODY` cap → `413` on oversize.
3. **Validate** the raw TOML via the existing `validate_config_text`. Invalid → `422` with the `ValidationResult` error list (same `_result_to_json` envelope as `/api/validate`). **No write.**
4. **Conflict check.** The request carries the `base_hash` the edit was loaded from (returned by GET). Compute the current on-disk hash (the same `sha256` `ConfigWatcher` uses). If it differs (a host edit or prior save landed since load) → `409 Conflict` with the current hash; **no clobber**.
5. **Backup + atomic write.** Copy the current `config.toml` → `config.toml.bak` (last-write backup), then write the new bytes to a temp file in the same dir and `os.replace` it onto `config.toml` (atomic; no partial file ever visible to the watcher).
6. Respond `200` with the new hash. The display's hot-reload adopts it within one render cycle.

`GET /api/config` is extended to also return the current `hash` (for the editor's base-hash) and, now that config is secret-free, the **verbatim** TOML. Redaction is retained as a defense-in-depth net (see §4).

### 2. Editor UI (extends the existing single-page `webui/static/index.html`)
- Load `config.toml` into a `<textarea>` (verbatim text + its base-hash).
- **Validate** button → live `POST /api/validate`, errors rendered inline (line/location from the existing validator).
- **Save** button → `PUT /api/config` with the text + base-hash + token. Surfaces `422` errors, `409` ("changed on disk — reload"), `403` ("set a token to enable editing").
- **Feedback loop:** after a `200`, poll `GET /api/status` and show the loop's verdict — **"applied live"** or **"saved — restart required for: `display.rows`, `plugins`"** — read from the reload record `nonreloadable_changed` already produces. This is the payoff: the user sees whether their edit actually took effect on the panel.

### 3. Redaction-as-net (defense in depth)
With Spec A, first-party `config.toml` is secret-free, so GET serves verbatim. To stay safe against a *third-party* plugin that put a secret inline anyway: GET still runs the value-blind redactor, and the **save path restores placeholders** — any value in the submitted body still exactly equal to the `•••` sentinel is replaced, by key path, with the on-disk value before write. So a redacted secret is never exposed *and* never clobbered, regardless of plugin compliance. (For the common secret-free case this is a no-op.)

### 4. Security & deploy
- **Mount:** the webui service's config mount changes `:ro` → `:rw` (one `compose.yaml` line). The display stays `:ro` and sees the webui's write through the shared host bind mount — identical to today's "host edits file → container sees it" model, just with the editor playing the host's role.
- **Writes require a token.** No `LED_TICKER_WEB_TOKEN` set ⇒ the instance is **read-only**: write endpoints return `403`. Reading/preview can stay open; editing cannot. (Open-by-default editing on a LAN appliance is the wrong default.)
- **File ownership (deploy note):** the webui container process must be able to write the host-bind-mounted file — document the `compose.yaml` `user:` / directory-permission requirement on the Pi. (The webui builds no frame, so it does not drop privileges the way the display does — constraint #13 — but it must still match the host file's writable UID/GID.)
- Recoverability: `config.toml.bak` + the conflict-check together mean a bad-but-valid save is recoverable and concurrent edits can't silently clobber.

## Testing

- Endpoint: valid → `200` + atomic write + new hash; invalid → `422`, file unchanged; stale base-hash → `409`, file unchanged; no token → `403`; oversize → `413`; temp-file failure leaves the original intact; `.bak` written with prior contents.
- Redaction-net: a body containing `•••` for a key that holds a real on-disk value restores it on write (round-trip preserves the secret); a non-`•••` value writes through.
- Feedback: a reloadable-only change reports "applied"; a `display.rows` change reports restart-required (drives the UI badge) — assert against `nonreloadable_changed`.
- Posture: write endpoints are absent/`403` without a token; the `:ro` default (no rw mount) surfaces a clear write error rather than a silent failure.

## Risks

- Validation gates *parse/schema* correctness, not *intent* — a valid-but-wrong config applies live. Mitigations: `.bak`, the conflict-check, and the explicit applied/restart-required feedback. Full multi-version undo is out of scope.
- A single shared token guards a write surface. Acceptable for a trusted-LAN appliance; documented as such (token + LAN; TLS is the operator's responsibility). Per-user auth is out of scope.
- The `:rw` mount widens the webui's blast radius to the config directory. Bounded by: token-required writes, path-confined to `config.toml` (no arbitrary path writes — reuse `safe_config_member` confinement), and the atomic-write/backup discipline.

## Scope

- IN: `PUT /api/config` (validate → conflict → backup → atomic write, token-required); `GET /api/config` returns hash + verbatim text; editor textarea + validate + save + applied/restart-required feedback in the existing SPA; `:rw` mount + docs; redaction-as-net with save-time restore; webui posture/docstring/`CLAUDE.md` update.
- OUT: structured/form-based editing (this is the full-TOML editor); editing config files *other than the running one*; multi-version history/undo beyond one `.bak`; per-user auth/TLS; forcing third-party secret hygiene.
