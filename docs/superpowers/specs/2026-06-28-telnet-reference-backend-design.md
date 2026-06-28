# Telnet reference backend + `api.backend()` plugin surface — Design

**Date:** 2026-06-28
**Status:** Approved (brainstorm)
**Epic:** #236 (backend abstraction) — the last open item: a concrete additional backend that validates the abstraction.
**Builds on:** PR #293 (`Backend` protocol + `rgbmatrix`/`headless` backends + importable conformance kit + `[display] backend` selection). Prior spec: `docs/superpowers/specs/2026-06-24-backend-abstraction-design.md`.

## Goal

Prove the `Backend` API is **usable by an external plugin author** by building one real, fully self-contained backend against the public protocol — a **telnet backend** that renders the sign as ANSI color in a terminal (`telnet sign.local 2300`, blinkenlights-style). The backend is the *vehicle*; **the validation is the deliverable** — every place the public API falls short of letting a plugin do this cleanly is a finding to fix or document.

## Why telnet (not a web/browser backend)

The brainstorm started at a web/streamed backend reusing the existing webui preview pipe (`PreviewTee` → `preview.bin` → `/api/preview`). We rejected that: **a backend owns its output device.** Production `rgbmatrix` writes to GPIO via its own C library — it does not ask led-ticker to push pixels for it. By symmetry the reference backend must own its transport, not reach into led-ticker's preview format/plumbing (which would *demonstrate the API is not cleanly usable*). A telnet backend reaches for even less than a browser one: no aiohttp, no `preview.bin`, no browser rendering — only the Backend protocol + Canvas contract + stdlib `asyncio` + ANSI codes. It is small enough to review whole, genuinely useful for headless-Pi dev (watch a config render over SSH), and on-brand.

## Validation-first framing

Success is not "telnet works" — it is the set of answers this exercise forces:
1. An **external** plugin registers a backend via `api.backend()` and it is selectable via `[display] backend = "telnet"`.
2. The backend passes `run_backend_conformance(...)` **unmodified**.
3. Frames actually render in a connected terminal.
4. No engine `isinstance`-on-concrete-type leak silently degrades it.
5. Each remaining gap (canvas reuse, async lifecycle, config-passing) is **fixed or explicitly documented**.

## Architecture — two deliverables, two repos

### A. Core (led-ticker) — minimal plugin-backend surface

1. **`api.backend(name)`** — a decorator method on `PluginAPI` (`plugin.py`) mirroring `api.widget`/`api.transition`: it **buffers** the registration under the qualified `namespace.name` (it does NOT call `register_backend` directly). The plugin loader commits it via the generic `_commit` path by adding one entry to `_REGISTRY_MAP` (`"backends": _REGISTRY`, the backend registry dict). This **honors the PluginAPI invariant** (no bare names; atomic commit; collision-check for free) and resolves a real validation finding: backends are selected by a single config string, but the plugin model namespaces everything. **Plugin backends are therefore namespaced** (`backend = "telnet.telnet"`), like `type = "calendar.events"`; built-in backends stay bare (`headless`/`rgbmatrix`). This is safe with reload because `reset_plugins` deletes only *dotted* registry keys — bare built-ins survive, the dotted plugin backend is cleared + re-committed. (`register_backend`, `Backend`, `BackendNotReadyError` are already in `led_ticker.plugin.__all__`.)
2. **Export `HeadlessCanvas`** on the public `led_ticker.plugin` surface. Today only `HeadlessBackend` is exported; a backend author cannot cleanly reuse the software canvas. Exporting it lets the telnet backend *compose* the canvas instead of reinventing the pixel-store + 5-method contract.
3. **Load-order tripwire** — assert `load_plugins` runs before `build_frame_from_config` (verified order in `run.py`: reconcile → `load_plugins` → `build_frame_from_config` → `setup()`/privilege-drop). This is the registration-before-selection guarantee a plugin backend depends on; lock it so a refactor can't reorder it.
4. **`isinstance`-leak audit** — grep `frame.py`/`ticker.py`/`run.py`/`scaled_canvas.py` for `isinstance(_, RgbMatrixBackend)` / concrete-canvas-type gates that a non-rgbmatrix backend would silently miss (hi-res routing, privilege-drop timing, overlay hooks). Fix or document each; the conformance kit tests the canvas, not the engine's trust in it.
5. **Async-lifecycle confirmation** — confirm `backend.setup()` is invoked from within the running asyncio loop (it is: `led_frame.setup()` is called inside the async `run()`), so a backend may `get_running_loop().create_task(...)` to spawn its server. Document this as the supported pattern for backends that do background I/O. (No protocol change in v1; an async lifecycle hook is a possible future finding.)
6. **Failure UX** — a selected backend that is missing/failed-to-import errors loudly at startup (the registry already raises listing known backends); never silently paint nothing.

These are the only core changes. No preview-format export, no config-plumbing system (see Config decision).

### B. led-ticker-plugins monorepo — the `telnet` backend plugin

- New workspace package `plugins/telnet/` (dist **`led-ticker-telnet`**); `register(api)` calls `api.backend("telnet")(TelnetBackend)` → registers as `telnet.telnet` (entry-point namespace `telnet` + name `telnet`).
- **`create_canvas()`** → returns a `HeadlessCanvas` (reused from core's public surface). The canvas stores its own pixels (no `GetPixel`, constraint #3) so `swap()` can serialize them.
- **`setup()`** → start an `asyncio` TCP server bound to the configured host/port; accept multiple clients; log `telnet backend — connect: telnet <host> <port>`. A bind failure logs and degrades (the panel must still boot — constraint #1 mirrored).
- **`swap(canvas)`** → render the canvas's stored pixels to an ANSI frame and broadcast to connected clients, then return the *other* buffer (double-buffer contract, constraint #8). Rendering: 24-bit-color half-block `▀` (top pixel = foreground, bottom pixel = background → two LED rows per character cell), cursor-home (`ESC[H`) each frame so the terminal repaints in place. Disconnected clients are pruned.
- **Self-contained dependencies:** only the public Backend protocol + Canvas contract + `HeadlessCanvas` + stdlib `asyncio`. No led-ticker internals.
- **Tests:** `from led_ticker.backends.conformance import run_backend_conformance` run against `TelnetBackend` (the first real external consumer of the importable kit), plus a unit test that a swapped frame is serialized + broadcast to a fake client and that `swap()` returns a different buffer.

## Config decision (a finding, handled pragmatically)

Backends are `attrs` classes whose fields `build_frame_from_config` populates from `[display]` (rgbmatrix carries its options; headless takes `width/height`). A plugin backend's *custom* field (the telnet port) is not in `[display]`'s schema, so there is **no clean way to configure a plugin backend via TOML today.**

**v1 resolution:** the telnet backend reads its port/host from **env vars with sane defaults** (`LED_TICKER_TELNET_PORT`, default `2300`; `LED_TICKER_TELNET_HOST`, default `0.0.0.0`) — keeping the plugin self-contained with zero core config-plumbing. **The gap "plugin backends cannot take TOML `[display]` config" is documented as the headline usability finding,** with a possible follow-up (a backend-options passing mechanism, e.g. a `[display.<backend>]` sub-table forwarded to a `Backend.from_config(...)` hook). We name the gap rather than bolt a config system onto this spec.

## Usage

```toml
[display]
backend = "telnet.telnet"   # namespaced: <entry-point namespace>.<backend name>
```
Install `led-ticker-telnet`, start led-ticker, then from any terminal: `telnet sign.local 2300` (or `nc sign.local 2300`). The display runs with no hardware; frames stream as ANSI color.

## Out of scope

- Browser/web backend; reusing the webui preview pipe.
- Full telnet IAC option negotiation — raw TCP streaming ANSI (telnet/nc clients render it), blinkenlights-style.
- A TOML config-passing mechanism for plugin backends (documented finding / possible follow-up).
- Production `rgbmatrix` behavior — unchanged, byte-identical.

## Testing strategy

- **Core:** unit tests for `api.backend()` (a plugin-registered backend is selectable); the load-order tripwire; the `isinstance`-audit outcome encoded as tests/comments. Full suite green; webui rgbmatrix-purity preserved.
- **Plugin:** `run_backend_conformance(TelnetBackend)` passes unmodified; frame-serialize/broadcast + double-buffer unit tests. Import-purity (no `led_ticker.<internal>` imports — only `led_ticker.plugin`).
- **Maintainer smoke (not unit-testable):** `[display] backend = "telnet"` on a machine, `telnet localhost 2300`, confirm the sign renders + animates + a second client can connect + disconnect doesn't crash.

## Risks

- **Abstraction leak** (top risk): an engine `isinstance` gate degrades the telnet backend silently — addressed by the audit (A.4); the conformance kit cannot catch engine-side trust.
- **Async server from a sync protocol** — addressed by A.5 (spawn on the running loop from `setup()`); if that proves awkward, the finding is "the Backend protocol needs an async lifecycle hook."
- **Frame rate / bandwidth** — full ANSI repaint per tick is tiny (e.g. 160×16 ≈ a few KB/frame at ~20fps); prune dead clients; never block the render loop on a slow socket (drop frames to a slow client rather than stall `swap()`).

## Process

brainstorm (this) → writing-plans → subagent-driven execution. Two repos: core changes + spec land in led-ticker; the plugin lands in led-ticker-plugins (separate worktree/PR). The maintainer telnet smoke is the only non-unit-testable gate.
