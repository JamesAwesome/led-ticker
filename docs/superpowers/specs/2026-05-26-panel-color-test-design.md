# Design: full-panel color test script

**Date:** 2026-05-26
**Status:** Approved (brainstorm), pending spec review → implementation plan

## Problem

When a new panel build (or a freshly-flashed Pi) doesn't render correctly, the failure mode is often in the **hardware/driver layer**, not the config layer: FM6126A init didn't run, `led_rgb_sequence` is wired wrong (Red shows green), chain length is off, `slowdown_gpio` is too low and the image flickers, dead/stuck pixels are masquerading as missing glyphs. Today the only way to diagnose those is to write a config and watch a widget render — which conflates "config bug" with "hardware bug" and makes triage slow.

The existing tooling covers the **config layer** (`led-ticker validate`, `make render-demo`) but nothing covers the **hardware layer** in isolation.

## Goal / non-goals

**Goal:** a small diagnostic that paints the whole panel in flat colors (R, G, B, White, Black) so the hardware/wiring/init/sequence layer can be verified independently of any widget or config logic.

**Non-goals:** widget rendering, scrolling, timing accuracy, ScaledCanvas paths, any kind of "test pattern" beyond solid fills.

## Design

### Script — `scripts/panel_color_test.py` (~50 lines)

**CLI**

```
uv run python scripts/panel_color_test.py [--config PATH] [--hold SECONDS]
```

- `--config` defaults to `config/config.longboi.toml`.
- `--hold` defaults to `2.0` seconds per color.
- Loops forever until Ctrl-C.
- Ctrl-C handler paints one final black frame, swaps, exits `0` — so the panel doesn't stick on a color.
- Logs `[1/5] Red (255, 0, 0)` etc. to stderr each tick.

**Implementation outline**

1. `argparse` for `--config` and `--hold`.
2. `config = load_config(Path(args.config))` — reuses the existing loader; surfaces any coercion warnings via the same mechanism `app/run.py` uses.
3. Build `LedFrame` by copying the exact kwargs list from `src/led_ticker/app/factories.py:892-910`. Single source of truth — if `DisplayConfig` ever gains a field, the script picks it up without drift. (Implementation note: factor the `DisplayConfig → LedFrame` mapping into a small helper that both `factories.py` and this script call, so the kwargs list lives in exactly one place.)
4. Color cycle:
   ```python
   COLORS = [
       ("Red",   255,   0,   0),
       ("Green",   0, 255,   0),
       ("Blue",    0,   0, 255),
       ("White", 255, 255, 255),
       ("Black",   0,   0,   0),
   ]
   ```
5. Per color:
   - `canvas = frame.get_clean_canvas()`
   - `canvas.Fill(r, g, b)` — standard `rgbmatrix` binding; also implemented in the test stub (`tests/stubs/rgbmatrix/__init__.py:71`).
   - `canvas = frame.matrix.SwapOnVSync(canvas)` — capture return (CLAUDE.md hardware constraint #1).
   - `time.sleep(args.hold)`.
6. `try / except KeyboardInterrupt`: paint one black frame, swap, return.

**Compliance with hardware-rendering constraints (CLAUDE.md "CRITICAL: Hardware Rendering Constraints"):**

- **#1 SwapOnVSync return value captured** — every swap site reassigns `canvas`.
- **#2 No DrawText on non-Canvas objects** — script doesn't call `DrawText` at all.
- **#3 No GetPixel** — not used.
- **#4 SetPixel works everywhere** — not needed; `Fill` is more efficient for uniform colors.
- **#5 Swap-then-sleep ordering** — `SwapOnVSync` before `time.sleep`.
- **#9 ScaledCanvas wrapping** — explicitly bypassed. `Fill` on the raw canvas paints every physical LED on the chain regardless of `default_scale`, which is exactly what we want: a hardware diagnostic should not be affected by logical-canvas scaling. No `ScaledCanvas` wrapper is constructed.
- **#12 advance_frame per tick** — not applicable (no widgets, no frame-aware effects).

### Make target — `panel-test` (host)

```make
panel-test:  ## Cycle full panel through R/G/B/White/Black. Usage: make panel-test [CONFIG=config/config.longboi.toml] [HOLD=2]
	uv run python scripts/panel_color_test.py \
	  --config $(or $(CONFIG),config/config.longboi.toml) \
	  --hold $(or $(HOLD),2)
```

Same `CONFIG=` / `HOLD=` override convention as `make validate`. Used on the dev laptop with a panel attached via USB-serial console, or any non-Docker host that has the rgbmatrix Python bindings installed.

### Make target — `panel-test-docker` (prod path)

```make
panel-test-docker:  ## Cycle R/G/B/W/B inside Docker. Stop the running ticker first (docker compose stop).
	docker run --rm -it --privileged --network host \
	  -v $(PWD)/config:/code/config:ro \
	  -v $(PWD)/scripts:/code/scripts:ro \
	  led-ticker \
	  python /code/scripts/panel_color_test.py \
	    --config /code/$(or $(CONFIG),config/config.longboi.toml) \
	    --hold $(or $(HOLD),2)
```

Flag-by-flag rationale:

- `--privileged` — GPIO/`/dev/mem` access (matches `compose.yaml:22`).
- `--network host` — parity with `compose.yaml:23` (not strictly needed by this script, but keeps behavior identical to prod).
- `--rm` — clean up the one-shot container on exit.
- `-it` — interactive TTY so Ctrl-C reaches Python and the black-frame cleanup runs.
- `-v $(PWD)/config:/code/config:ro` — same mount as compose.
- `-v $(PWD)/scripts:/code/scripts:ro` — script changes don't require rebuilding the image.

**Pre-flight constraint:** the user must stop the running ticker first; the diagnostic and the main app cannot share the matrix. The Make target comment and docs page both state this explicitly. Expected sequence:

```bash
docker compose stop          # or: sudo systemctl stop led-ticker
make panel-test-docker
docker compose start         # or: sudo systemctl start led-ticker
```

Both Make targets get added to the `.PHONY:` list at the top of the Makefile.

### Docs page — `docs/site/src/content/docs/tools/panel-test.mdx`

Auto-picked-up by the `autogenerate: { directory: "tools" }` block in `astro.config.mjs:80-81` — no sidebar edit needed.

Sections (matching the style of `tools/validate.mdx`):

1. **Lead paragraph** — what the script is, why it exists separately from `validate` / `render-demo` (hardware layer vs. config layer).
2. **Quick start (host)** — `make panel-test`, `make panel-test CONFIG=… HOLD=…`.
3. **Quick start (Docker on the Pi)** — `make panel-test-docker` with the stop/start dance around it.
4. **What it does** — R/G/B/W/B cycle, hold time, Ctrl-C → black-frame cleanup.
5. **What it lets you diagnose** — table:

   | Symptom on panel | Likely cause | Where to fix |
   | --- | --- | --- |
   | Red shows green / Green shows blue | `led_rgb_sequence` wrong | `[display] led_rgb_sequence` ([config-options](/reference/config-options/)) |
   | Bottom half of panel garbled or mirrored | `panel_type = "FM6126A"` missing or driver init not running | `[display] panel_type` |
   | Only first panel of the chain lights up | `chain` setting wrong or HUB75 cable order off | `[display] chain` + wiring |
   | Flicker during solid colors | `slowdown_gpio` too low for the chain | bump `slowdown_gpio` |
   | Dim or dead pixels during white frame | hardware fault on those pixels | physical inspection |
   | Stuck-on pixels during black frame | hardware fault on those pixels | physical inspection |

6. **CLI flags** — `--config`, `--hold` with defaults.
7. **Notes** — `sudo` required on the Pi for the host path; the Docker path handles privilege via `--privileged`; no GIF demo (test patterns don't render meaningfully as GIFs).
8. **`<RelatedPages slugs={["hardware/bigsign", "hardware/smallsign", "reference/cli", "tools/validate"]} />`**

### Cross-links from existing pages

- `hardware/bigsign.mdx`: one-line mention near where `panel_type` / `led_rgb_sequence` are discussed — "If you suspect a wiring or driver-init issue, the [`panel-test`](/tools/panel-test) tool isolates the hardware layer from the config layer."
- `hardware/smallsign.mdx`: same.
- `reference/cli.mdx`: add a row for `panel-test` and `panel-test-docker` to the Make-targets table (if present — verify during implementation; skip the section if no such table exists).

## Out of scope (deliberately)

- Any kind of moving/animated test pattern (gradients, ramps, line sweeps). Solid fills cover the diagnostic need; anything richer is `make render-demo` territory.
- A unit test that drives the script through the rgbmatrix stub. The script's logic is ~50 lines of `argparse` + a loop; the value-add of a test is low and the maintenance cost (mocking `time.sleep`, asserting on the SwapOnVSync return-capture pattern) is non-trivial. Skip.
- Auto-detection of "is the ticker already running?" with a friendly error. Out of scope; the docs page covers the manual stop/start dance.

## Files touched

**New:**

- `scripts/panel_color_test.py`
- `docs/site/src/content/docs/tools/panel-test.mdx`

**Modified:**

- `Makefile` — add `panel-test` + `panel-test-docker` targets, add both to `.PHONY:`.
- `src/led_ticker/app/factories.py` — extract the `DisplayConfig → LedFrame` mapping into a helper for reuse by the script (single source of truth).
- `docs/site/src/content/docs/hardware/bigsign.mdx` — one-line cross-link.
- `docs/site/src/content/docs/hardware/smallsign.mdx` — one-line cross-link.
- `docs/site/src/content/docs/reference/cli.mdx` — Make-targets table row (if a table exists).

## Verification plan

**On the dev laptop (no panel hardware):**

- `make lint` clean.
- `make test` clean — no new tests added (per "Out of scope"), but no regressions in the existing 1438+ suite. In particular the existing `factories.py` tests must still pass after the `DisplayConfig → LedFrame` mapping is extracted into a helper.
- `python scripts/panel_color_test.py --help` parses and prints usage cleanly.
- `make docs-build` clean; `make docs-lint` clean.

**On longboi (physical hardware):**

- `make build-docker` succeeds.
- `make panel-test-docker` after `docker compose stop` shows the full R/G/B/W/B cycle on the physical panel. Specifically:
  - Red is red (not green or blue) — confirms `led_rgb_sequence = "BRG"` is correctly remapping.
  - All 4 panels in the chain light up uniformly — confirms `chain = 4` and HUB75 cable order.
  - Bottom half of each panel renders cleanly during the white frame — confirms `panel_type = "FM6126A"` is sending init.
  - No flicker during the 2s holds — confirms `slowdown_gpio = 3` is adequate.
  - Ctrl-C exits and the panel goes black (not stuck on the last color).
- `docker compose start` restores normal ticker operation.
