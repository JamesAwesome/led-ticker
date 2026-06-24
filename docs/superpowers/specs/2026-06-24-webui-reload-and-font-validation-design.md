# WebUI reload confirmation + config-dir-aware text validation

**Date:** 2026-06-24
**Status:** Approved (design), pending implementation

Two independent webui bugs, fixed together because both stem from the webui
running as a separate process from the display and not sharing enough context
with it.

Related prior work: [`2026-06-20-config-hot-reload-design.md`](./2026-06-20-config-hot-reload-design.md)
(the hot-reload watcher this builds on) and
[`2026-06-21-web-config-editor-design.md`](./2026-06-21-web-config-editor-design.md)
(the save → reload → confirm flow).

---

## Problem 1 — "unknown font" warning for a font that IS in the inventory

### Symptom

Validating a config in the webui editor emits a rule-24 "unknown font"
*warning* for a locally-provided font (e.g. `beloved-sans.otf`) that lives in
the config directory's `fonts/` folder and is shown in the webui's font
**inventory**.

### Root cause

The editor's live-validate path is:

1. `POST /api/validate` → `validate_handler` (`webui/__init__.py:566`) calls
   `validate_config_text(body)`.
2. `validate_config_text` (`validate.py:2094`) writes the TOML into a
   `tempfile.TemporaryDirectory` and calls `validate_config(temp_path)`.
3. `validate_config` resolves every relative path against `path.parent` — the
   **temp dir**:
   - `_configure_user_font_dir(path)` → `USER_FONT_DIR = <temp>/fonts` (empty).
   - `_run_build_checks(config.sections, path.parent)` (`validate.py:1957`).
   - `_check_plugin_validation_warnings(config, path.parent)` (`:2054`).
   - `_check_asset_paths(config, path.parent)` (`:2059`).
4. The hires loader can't find `beloved-sans.otf` → `UnknownFontError` →
   downgraded to a rule-24 warning.

Meanwhile the inventory is built from the **real** config dir
(`inventory.py` `_user_fonts(config_dir)`), so the font shows there — the
contradiction the user saw.

This is not fonts-only: `_check_asset_paths` shares the bug, so a config
referencing a local image/gif by relative path would also get a false
"file not found" in the editor-validate path. The sibling handler
`validate_file_handler` (`webui/__init__.py:581`) validates a saved file by
its real path and is unaffected.

### Design

Thread the **real config dir** through as an explicit override so all
relative-path resolution anchors correctly. Backward-compatible by default.

- `validate_config(path, *, strict=False, config_dir: Path | None = None)`
  - When `config_dir is None`: `config_dir = path.parent` (preserves **all**
    existing behavior — CLI `led-ticker validate`, `validate_file_handler`).
  - Use the resolved `config_dir` (not `path.parent`) for:
    `_configure_user_font_dir`, `_run_build_checks`,
    `_check_plugin_validation_warnings`, `_check_asset_paths`.
  - `_configure_user_font_dir` currently takes the config *path* and derives
    `path.parent / "fonts"`. Either (a) pass it the resolved `config_dir` and
    have it append `fonts/`, or (b) keep its signature and call it with a path
    whose `.parent` is `config_dir`. Prefer (a): make it accept the directory
    explicitly to remove the temp-path indirection. Confirm no other caller
    breaks (only `validate.py:1955` and `app.run` call it).
- `validate_config_text(text, *, strict=False, config_dir: Path | None = None)`
  threads `config_dir` straight to `validate_config`.
- `validate_handler` (`webui/__init__.py:566`) passes
  `config_dir=config_path.parent`.

The temp file still exists only to give the TOML parser a real path.
`ValidationResult.path` keeps pointing at the temp file — it is never surfaced
to the user on this path.

---

## Problem 2 — "reload status unknown — check the sign" most of the time

### Symptom

After saving a config from the webui, it shows
`saved (reload status unknown — check the sign)` most of the time, even though
the reload does eventually happen (the user sometimes sees `config reloaded`
in the display logs, sometimes not within the window).

### Root cause

Two compounding defects:

1. **Detection latency (display).** `watcher.changed()` is checked in exactly
   one place: the top of the outer `while True` playlist loop
   (`run.py:690`) — its own comment calls it the *"once per full playlist
   cycle"* check. By contrast, **restart** is checked at the outer loop
   (`:684`), per-section (`:744`), and per-tick via the Ticker's
   `restart_check` (`run.py:929`, `ticker.py:446`). Config reload simply never
   got the finer-grained treatment.

2. **Confirmation window (webui).** The save handler captures the prior
   `last_reload.at`, PUTs, waits 1.5s, then polls 3× at 1.5s
   (`index.html:676,708`) — a ~6s budget. On timeout it shows
   "reload status unknown — check the sign" (`index.html:716–721`).

For any playlist whose full cycle exceeds ~6s (essentially every real
multi-section config), the reload lands *after* the webui gave up. The reload
genuinely succeeds at the next cycle boundary — `record_reload(ok=True)` fires
and writes `status.json` — but nobody is polling anymore. Hence
"sometimes I see it in the logs, sometimes I don't (within 6s)".

### Design

**Display side (`run.py`):** detect reloads at each **section boundary**, not
just once per cycle.

- Extract the existing reload detect-and-apply block (`run.py:690–736`) into a
  nested `async def _maybe_reload() -> bool` defined in `run()` so it closes
  over the run-loop locals (`config`, `default_section_trans`, `widget_cache`,
  `widget_tasks`, `render_breaker`, `schedule_task`, …). Use `nonlocal` for the
  variables it rebinds (`config`, `default_section_trans`, `schedule_task`).
  Returns `True` iff a reload was applied (the `else` branch at `:704`), `False`
  for "no change" / "transient mid-write" / "rejected".
- Call `_maybe_reload()`:
  - at the top of the outer `while True` (unchanged placement), and
  - at the **start of each section iteration** (before `record_section`,
    around `run.py:737`).
- On a per-section reload (`_maybe_reload()` returns `True` inside the section
  loop), `break` out of the section `for` loop so the cycle restarts against
  the new `config.sections` rather than continuing to iterate the stale list.
  The outer-loop call at the next pass top will see `watcher.changed() == False`
  (just reloaded) and proceed to play the new sections.

This caps reload latency at one section's duration and applies the swap at a
clean seam (between sections — never mid-scroll). Rejected reloads still keep
the old config and record `ok=False` exactly as today.

Note: a single section with a very long hold can still exceed the webui window;
that is covered by the patient-poll change below.

**Webui side (`index.html`):** make `pollReloadOutcome` patient.

- Poll at a 2s interval up to a **180s** cap (≈90 attempts) until
  `last_reload.at` becomes fresh (differs from the captured `priorAt` and is
  truthy).
- While waiting, show `saved — applying at next section…` (replaces
  `saved — waiting for reload…`).
- Only after the 180s cap is genuinely exceeded, fall back to
  `saved (reload status unknown — check the sign)`.
- The fresh-reload outcome branches (`applied live ✓`, restart-required,
  `reload rejected: …`) are unchanged.
- Rationale for 2s/180s: a 1.5s interval over 180s would be 120 requests;
  2s keeps it ≈90 against a local status endpoint while comfortably covering
  slow playlists.

---

## Testing (TDD — write the failing test first for each)

### Problem 1
- `validate_config_text(text, config_dir=real_dir)` for a config referencing a
  font that exists only in `real_dir/fonts/` → assert **no** rule-24 warning.
- Same for a local image/gif asset in `real_dir` → assert no asset
  "not found" error from `_check_asset_paths`.
- Back-compat: `validate_config_text(text)` (no `config_dir`) and
  `validate_config(path)` still anchor to the temp/`path.parent` dir
  (existing behavior unchanged).
- Likely homes: `tests/test_validate*.py` and/or a webui validate test.

### Problem 2 — display
- Extend the hot-reload run tests: with ≥2 sections, mutate the watched config
  while the loop is mid-cycle and assert the reload is detected/applied at the
  next **section boundary** (within one section), not only at a full-cycle
  boundary. Assert `record_reload(ok=True)` fired and the new section content
  is what plays next.
- Assert a rejected reload still keeps the old config and records `ok=False`
  (no regression).

### Problem 2 — webui frontend
- Check for an existing frontend test harness for `index.html`. If one exists,
  assert the new poll cap/interval constants and the "applying at next
  section…" wait message. If there is no JS test surface, cover what is
  reachable (e.g. any Python-side constant if the value is templated) and note
  the poll-loop behavior as manually verified. Decide during planning.

---

## Out of scope / non-goals
- No change to the status.json schema or `record_reload` shape.
- No change to restart handling (already responsive).
- No mid-section (per-tick) reload — section boundary is the chosen seam.
- No change to `validate_file_handler` (already correct).
