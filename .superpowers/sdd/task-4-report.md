# Task 4 Report: Frontend — "Restart to apply" button

## What was added

### `src/led_ticker/webui/static/index.html`

**CSS** (after `.store-action-area`):
- `.restart-btn` — green-tinted button matching the store-btn style family
- `.restart-btn:disabled` — 45% opacity, not-allowed cursor
- `.restart-btn-wrap` — top-margin wrapper rendered into by `renderRestartBtn()`
- `.restart-status` — muted text below the button showing elapsed / error messages
- `.restart-notice` — hidden-by-default blue-tinted card in the config tab for restart-required notices

**HTML additions**:
1. **Config tab** — `#config-restart-notice` div (hidden by default) containing:
   - `<strong>Restart required</strong>` heading
   - `#config-restart-fields` span (field names that need a restart)
   - `#config-restart-btn-wrap` (rendered into by `renderRestartBtn`)
2. **Store pending banner** — appended `#store-restart-btn-wrap` and `#store-restart-status` div

**JavaScript additions**:
- `lastAllowRestart` — module-level bool tracking `allow_restart` across `poll()` and `renderStore()` calls
- `renderRestartBtn(wrapId, statusId, allowRestart, onDone)` — reusable button factory:
  - `allow_restart` false → disabled button with tooltip "Browser restart is off — set [web] allow_restart = true (and ensure your service auto-restarts: Docker, or systemd Restart=)"
  - `allow_restart` true + no token → focuses the token field + status message
  - `allow_restart` true + token → enabled button, wires `doRestart()`
- `_setRestartStatus(statusId, text)` — null-safe status writer
- `doRestart(btn, statusId, onDone)` — click handler:
  1. Prompts with `confirm("The sign will go dark for a few seconds while the display restarts. Continue?")`
  2. `POST /api/restart` with `X-Web-Token` header
  3. `setInterval` live elapsed counter "restarting… Ns"
  4. Polls `GET /api/status` every 1.5s; tracks `wentOffline` flag; on recovery calls `onDone()`
  5. 60s timeout: "The display hasn't come back. Refresh this page; if the sign is still dark, check the container is running (docker compose ps) and view the logs."
- `showConfigRestartNotice(fields)` / `hideConfigRestartNotice()` — show/hide the config tab notice
- `poll()` — updated to read `allow_restart` from `/api/status` into `lastAllowRestart`
- `renderStore()` — updated to read `allow_restart` from `/api/store` and call `renderRestartBtn()`
- `pollReloadOutcome()` — updated: `lr.restart_required.length > 0` calls `showConfigRestartNotice()`; clear outcomes call `hideConfigRestartNotice()`

## Manual / maintainer interactive flow checklist

These flows require a browser + a running sign with `[web] allow_restart = true` and a token configured:

1. **Enabled + token set → happy path**: Open Store tab with a plugin pending install (badge "Restart to activate"). Button appears green "Restart to apply". Click → confirm dialog shows "The sign will go dark for a few seconds while the display restarts. Continue?" → POST fires → elapsed counter increments → sign goes dark → sign recovers → "Display back online ✔" → store refreshes, pending banner hides.

2. **Enabled + no token**: Open Store tab with a pending plugin but no token in the field. Button appears enabled. Click → no confirm → token field gains focus → status reads "Enter your token in the field above first."

3. **Disabled (`allow_restart = false`)**: Button appears greyed-out. Hover shows tooltip "Browser restart is off — set [web] allow_restart = true (and ensure your service auto-restarts: Docker, or systemd Restart=)". Click has no effect.

4. **60s timeout**: Block the sign from recovering (e.g. stop Docker but don't restart). Counter climbs to ~60s, then shows "The display hasn't come back. Refresh this page; if the sign is still dark, check the container is running (docker compose ps) and view the logs."

5. **POST failure** (e.g. wrong token mid-session, or 403 from `allow_restart = false` race): Button re-enables and status shows the error from the response body.

6. **Config-editor restart-required path**: Edit a config field that requires restart (e.g. `[display].chain_length`). Save → `pollReloadOutcome` detects `lr.restart_required`. Config tab shows the `#config-restart-notice` card with the field list and the "Restart to apply" button. On recovery the notice hides and `config-status` reads "display restarted ✔".

## Tests added

`tests/test_webui_app.py` — 9 new static-marker tests (97 total, was 88):

| Test | What it checks |
|---|---|
| `test_index_html_has_restart_button_hooks` | All wrapper/status/notice element IDs present; `renderRestartBtn`/`doRestart` defined; `allow_restart`/`lastAllowRestart` in HTML |
| `test_index_html_restart_confirm_text` | Exact `confirm()` dark-panel message |
| `test_index_html_restart_disabled_tooltip` | Disabled tooltip text (allow_restart, systemd Restart=) |
| `test_index_html_restart_timeout_message` | Timeout message + `docker compose ps` |
| `test_index_html_restart_uses_header_not_url` | Token via header only; POST method |
| `test_index_html_restart_reads_display_online_for_poll` | Recovery poller uses `body2.state`; `wentOffline` tracking |
| `test_index_html_restart_button_in_store_pending_banner` | `renderRestartBtn("store-restart-btn-wrap")` call in `renderStore` |
| `test_index_html_restart_button_in_config_editor_notice` | `showConfigRestartNotice` / `hideConfigRestartNotice` defined; `renderRestartBtn("config-restart-btn-wrap")` present |

## Fix note (post-task-4 follow-up — commit fd2c6b56)

Two UX bugs found after the initial task-4 work and fixed in a single follow-up commit:

**Fix 1 — config-tab restart had no status feedback.**
`showConfigRestartNotice` was calling `renderRestartBtn("config-restart-btn-wrap", null, ...)`.
`statusId=null` made every `_setRestartStatus` call a no-op, so "restarting…", elapsed counter,
failure messages, and "Display back online ✔" were all silently discarded in the config tab.
Fixed by:
- Adding `<div id="config-restart-status" class="restart-status"></div>` to the
  `#config-restart-notice` card (after `#config-restart-btn-wrap`, same `.restart-status` class the Store uses).
- Changing the `showConfigRestartNotice` call to pass `"config-restart-status"` as `statusId`.

**Fix 2 — Store "Display back online ✔" cleared instantly.**
The Store `onDone` callback ran `loadStore(); $("store-restart-status").textContent = "";`
synchronously. Because `loadStore()` is async and not awaited, the `.textContent = ""`
executed immediately — before the user could read the success message.
Fixed by wrapping the clear in `setTimeout(() => { $("store-restart-status").textContent = ""; }, 3000)`,
giving the confirmation ~3 seconds of visibility. `loadStore()` call order is unchanged.

**Tests added (2 new, now 99 total in test_webui_app.py + test_webui_purity.py):**
- `test_index_html_has_restart_button_hooks` — extended: asserts `id="config-restart-status"` present in HTML.
- `test_index_html_restart_button_in_config_editor_notice` — extended: asserts `renderRestartBtn("config-restart-btn-wrap", "config-restart-status"` in HTML so the statusId wiring cannot regress.
- `test_index_html_store_restart_ondone_clears_status_after_delay` — new: asserts the store onDone uses `setTimeout` to clear the status (not a synchronous bare assignment).

Interactive check note: no JS runner in CI — the elapsed-counter, polling, and "back online" visibility improvements are manual-verify items (same flows as the task-4 interactive checklist above, items 1 and 6).
