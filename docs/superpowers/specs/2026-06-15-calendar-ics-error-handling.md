# Calendar widget — graceful `ics_url` error handling

**Date:** 2026-06-15
**Goal:** Replace the confusing full stack trace + misleading "No upcoming
events" panel that appears when an `ics_url` is invalid/unreachable with a
concise, actionable log line, a distinct on-panel message, and a config-time
preflight that catches the obvious cases — so an end user knows how to fix it.

## Motivating failure

A smoke-config placeholder (`ics_url = "PASTE_YOUR_..._ICS_URL_HERE"`) is treated
by `_fetch_ics` as a bare local path, so the read raises `FileNotFoundError`.
`update()` catches it with `logger.exception(...)`, dumping a ~25-line traceback,
and the panel falls back to `empty_text` ("No upcoming events") — which lies: the
feed is broken, not empty.

## Three fixes

### 1. Runtime — concise, classified log

In `Calendar.update()`'s `except` block, replace `logger.exception(...)` with a
single `logger.warning(...)` carrying an actionable message; demote the full
traceback to `logger.debug("...", exc_info=True)` for debugging.

A module helper `_describe_fetch_error(exc, url) -> str` classifies by exception
type:

| Failure | Trigger | Message |
|---|---|---|
| file not found | `FileNotFoundError` / `IsADirectoryError` | `Calendar feed file not found: '<url>'. Set ics_url to a real .ics URL or an existing file.` |
| HTTP status | `aiohttp.ClientResponseError` | `Calendar feed returned HTTP <status> for <url>. Check the URL is public and correct.` |
| unreachable | other `aiohttp.ClientError` / `OSError` | `Calendar feed unreachable: <url> (<short err>). Check the URL and your network.` |
| parse failure | `ValueError` and anything else | `Calendar feed downloaded but is not valid iCal: <url>.` |

Every message ends with ` See https://docs.ledticker.dev/widgets/calendar/`.
The classifier is pure (exception + url → string), independently testable.

### 2. Panel — distinct `error_text`

New field `error_text: str = "Calendar unavailable"`. When the **first** load
fails (no prior `feed_stories`), the panel shows `error_text` (via a new
`_error_story()`, same construction as `_empty_story()` but with `error_text`)
instead of `empty_text`. A genuinely-empty feed still shows `empty_text`. A
transient refresh failure when data already exists keeps the last-good
`feed_stories` (unchanged resilience) and logs the warning.

`error_text` is a plain string knob like `empty_text` — no provider/validation
beyond a string type.

### 3. Preflight — two tiers (mirrors missing-font behavior)

- **Placeholder → hard error.** In `Calendar.validate_config(cls, cfg)`, an
  `ics_url` whose value contains `PASTE`, `YOUR_`, or `_HERE` (case-insensitive)
  is an unfilled template → append an error:
  `ics_url looks like an unfilled placeholder ('<value>') — paste your real .ics
  URL`. Runs always (per-widget validate hook); travels with the widget.

- **Missing local file → warning, not error.** A new soft check
  `_check_calendar_ics_paths(config, config_dir)` added to `validate.py`'s Phase 2
  warnings block (`if not errors:`). For each `calendar` widget whose `ics_url`
  is a `file://` URL or a bare path (no `http(s)://` / `webcal(s)://` scheme),
  resolve it against `config_dir` (absolute paths used as-is) and, if it does not
  exist, emit a `ValidationIssue(severity="warning", ...)`:
  `calendar ics_url path '<p>' does not exist (resolved to <abs>) — it must be
  present at runtime`. `http(s)`/`webcal` URLs get NO network I/O. Because Phase 2
  warnings only run when there are no hard errors, a placeholder (caught as an
  error in tier 1) never double-reports.

  Rule number: next free rule id in `validate.py`. The check reuses the
  `webcal://`→`https://` normalization already in `_normalize_ics_url` so a
  `webcal` URL is correctly treated as a network URL (no path check).

## Files

- `src/led_ticker/widgets/calendar.py` — `_describe_fetch_error` helper;
  `error_text` field; `_error_story()`; rewritten `update()` except block;
  placeholder check in `validate_config`.
- `src/led_ticker/validate.py` — `_check_calendar_ics_paths` soft check + wire
  into Phase 2 warnings.
- `docs/content-source/widgets/calendar.md` — `error_text` row.
- `docs/site/src/content/docs/widgets/calendar.mdx` — short note on the error
  message + preflight in a "Troubleshooting" aside.

## Tests

- `_describe_fetch_error`: one assertion per class (FileNotFound, ClientResponse
  404, ClientError, ValueError) — message content + docs link.
- `update()` first-load `FileNotFoundError`: panel shows `error_text` (not
  `empty_text`); log is a single WARNING, no traceback (caplog: no
  `logger.exception`/`ERROR` with stack); `_describe_fetch_error` message present.
- `update()` transient failure with prior data: `feed_stories` unchanged (stale
  kept), warning logged.
- genuinely-empty feed still yields `empty_text` (`_empty_story`).
- `error_text` field default + TOML override.
- `validate_config`: placeholder (`PASTE...`) → error; clean `https://` URL → no
  placeholder error.
- `_check_calendar_ics_paths`: missing `file://` path → one **warning** (result
  stays `valid`); existing file → no issue; `https://` URL → no issue (no
  network); placeholder is pre-empted by the tier-1 error (no warning when errors
  present).
- Update existing `test_update_first_load_error_shows_empty_text` → expect
  `error_text`.
- Full suite + ruff + pyright green.

## Out of scope

- Retry/backoff changes (`run_monitor_loop` already backs off).
- Network reachability checks for `http(s)` URLs at validate time (slow,
  network-dependent, false-positive-prone).
- Per-error-class on-panel text (the panel shows one generic `error_text`; the
  specifics live in the log).
