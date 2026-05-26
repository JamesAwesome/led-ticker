# Panel Color Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `scripts/panel_color_test.py` diagnostic that cycles the panel through full-frame R/G/B/White/Black, plus host + Docker Make targets and a docs page, so hardware-layer issues (FM6126A init, `led_rgb_sequence`, chain wiring, flicker, dead/stuck pixels) can be diagnosed in isolation from config issues.

**Architecture:** A ~50-line standalone Python script that reuses the existing `load_config()` loader and the existing `build_frame_from_config()` helper from `src/led_ticker/app/factories.py:859`, calls `canvas.Fill(r, g, b)` for each color, captures the `SwapOnVSync` return per CLAUDE.md hardware-rendering constraint #1, and exits cleanly on Ctrl-C by painting one final black frame. Two Make targets wrap the script: `panel-test` runs it locally via `uv run`, `panel-test-docker` runs it inside the existing `led-ticker` production image. A new docs page at `tools/panel-test.mdx` is auto-picked-up by the existing `autogenerate: { directory: "tools" }` sidebar block.

**Tech Stack:** Python 3.13, `attrs`, the existing `led_ticker` package, `rgbmatrix` C bindings (real on Pi, stub in tests), `make`, Docker, Astro Starlight (docs).

**Spec reference:** `docs/superpowers/specs/2026-05-26-panel-color-test-design.md` (commit `c8bcd48`).

**Important context discovered during planning:**
- The spec mentions "extract the `DisplayConfig → LedFrame` mapping into a helper" as a refactor item. This is **already done** — `build_frame_from_config(display) -> LedFrame` exists at `src/led_ticker/app/factories.py:859` and is exported via `src/led_ticker/app/__init__.py:43`. The script just imports it. No `factories.py` refactor needed.
- The script does NOT need unit tests (per spec "Out of scope"). Verification is via lint, the existing test suite (regression check on the loader + factory), and manual hardware testing on longboi.
- The script must **not** call `_configure_user_font_dir(config_path)` (which `app/run.py:46` does) — that's only needed for widgets that render text. Panel fills don't touch fonts.
- The script **must** surface coerce warnings the same way `app/run.py:44-45` does:
  ```python
  for w in config._coerce_warnings:
      logging.warning("config coerce: %s", w.message)
  ```
  Mirroring this keeps diagnostic output consistent with the main app.

---

### Task 1: Create the panel color test script

**Files:**
- Create: `scripts/panel_color_test.py`

- [ ] **Step 1: Create the script**

Write `scripts/panel_color_test.py` with the following content exactly:

```python
"""Full-panel color diagnostic.

Cycles the panel through Red → Green → Blue → White → Black, looping
forever until Ctrl-C. Reuses the same config loader and LedFrame
construction the main app uses, so all hardware knobs (panel_type,
led_rgb_sequence, chain, slowdown_gpio, rp1_rio, etc.) come straight
from the config TOML.

Use this to isolate hardware/wiring/driver issues from config issues.
A green Red means led_rgb_sequence is wrong. A garbled bottom half
means panel_type isn't initializing the FM6126A. Etc. See
docs.ledticker.dev/tools/panel-test/ for the full diagnostic matrix.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from led_ticker.app.factories import build_frame_from_config
from led_ticker.config import load_config

COLORS: list[tuple[str, int, int, int]] = [
    ("Red", 255, 0, 0),
    ("Green", 0, 255, 0),
    ("Blue", 0, 0, 255),
    ("White", 255, 255, 255),
    ("Black", 0, 0, 0),
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Cycle the panel through full-frame R/G/B/White/Black to "
            "diagnose hardware/wiring/driver issues independent of config."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/config.longboi.toml"),
        help=(
            "Path to a led-ticker config TOML. Only [display] is used; "
            "widget/section config is ignored. Default: config/config.longboi.toml."
        ),
    )
    parser.add_argument(
        "--hold",
        type=float,
        default=2.0,
        help="Seconds to hold each color before advancing. Default: 2.0.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )
    args = _parse_args()

    config = load_config(args.config)
    # Mirror app/run.py: surface any coercion warnings from load_config so
    # diagnostic output matches what users see when running the main app.
    for w in config._coerce_warnings:
        logging.warning("config coerce: %s", w.message)

    frame = build_frame_from_config(config.display)
    canvas = frame.get_clean_canvas()

    n = len(COLORS)
    try:
        i = 0
        while True:
            name, r, g, b = COLORS[i % n]
            logging.info("[%d/%d] %s (%d, %d, %d)", (i % n) + 1, n, name, r, g, b)
            canvas.Fill(r, g, b)
            # Constraint #1: SwapOnVSync return value MUST be captured.
            canvas = frame.matrix.SwapOnVSync(canvas)
            time.sleep(args.hold)
            i += 1
    except KeyboardInterrupt:
        logging.info("Interrupted — clearing panel.")
        canvas.Fill(0, 0, 0)
        canvas = frame.matrix.SwapOnVSync(canvas)
        return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify `--help` works (parses, no import errors)**

Run:
```bash
uv run python scripts/panel_color_test.py --help
```
Expected: argparse prints usage text covering `--config` and `--hold`. Exit code 0. No traceback.

If you see `ModuleNotFoundError: No module named 'rgbmatrix'`, that's expected only if you try to RUN it (no `--help`); `--help` exits before any rgbmatrix import is forced. The import chain is `led_ticker.app.factories` → `led_ticker.frame` → `led_ticker._compat` which lazily resolves rgbmatrix. As long as `--help` works, the script is structurally sound.

- [ ] **Step 3: Verify the existing test suite still passes**

This is a regression check on `load_config` and `build_frame_from_config` — neither is modified, but the script wires them together for the first time outside the main app.

Run:
```bash
make test
```
Expected: all 1438+ tests pass. No new failures.

- [ ] **Step 4: Lint clean**

Run:
```bash
make lint
```
Expected: ruff reports zero issues in `scripts/panel_color_test.py`. The Makefile's lint target currently checks `src/ tests/ tools/`; if `scripts/` isn't included, that's fine — the script will still be checked by the pre-commit hook when staged.

If lint flags issues (e.g. import order, line length), fix them and re-run.

- [ ] **Step 5: Commit**

```bash
git add scripts/panel_color_test.py
git commit -m "$(cat <<'EOF'
feat: full-panel color test diagnostic script

scripts/panel_color_test.py cycles R/G/B/W/B to verify the hardware/
driver/wiring layer in isolation from any widget or config logic.
Reuses load_config + build_frame_from_config so all panel knobs come
from the config TOML. Captures SwapOnVSync return per constraint #1.
Ctrl-C paints one final black frame so the panel doesn't stick.

Spec: docs/superpowers/specs/2026-05-26-panel-color-test-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add the `panel-test` Make target (host)

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add `panel-test` to `.PHONY` and the target itself**

The current `.PHONY:` line (line 1) lists several targets. Add `panel-test` and `panel-test-docker` to it.

Edit `Makefile` line 1:

**Before:**
```make
.PHONY: dev hooks test lint typecheck format clean build-docker docs-dev docs-build docs-lint docs-format validate render-demo render-long-demos render-long-demo render-pinned-demos plan-gif render-emoji-previews setup-demo-fonts
```

**After:**
```make
.PHONY: dev hooks test lint typecheck format clean build-docker docs-dev docs-build docs-lint docs-format validate render-demo render-long-demos render-long-demo render-pinned-demos plan-gif render-emoji-previews setup-demo-fonts panel-test panel-test-docker
```

Then add the target itself. The natural insertion point is after the `validate:` target (lines 35-36), so panel-test groups with the other config-aware targets. Insert this block after the `validate:` recipe (after line 36, before the `# --- Docker (production image only) ---` comment at line 38):

```make

# --- Panel diagnostics ---

# Cycle full panel through R/G/B/White/Black for hardware-layer diagnostics.
# Use this when widgets render wrong but you don't know if it's a config or
# wiring/driver issue. Reuses [display] from the given config TOML.
panel-test:  ## Cycle full panel through R/G/B/W/B. Usage: make panel-test [CONFIG=config/config.longboi.toml] [HOLD=2]
	uv run python scripts/panel_color_test.py \
	  --config $(or $(CONFIG),config/config.longboi.toml) \
	  --hold $(or $(HOLD),2)
```

- [ ] **Step 2: Verify the help-target catalogue shows it**

The Makefile uses `## ` comments to auto-generate help text. Verify:

```bash
make help 2>/dev/null | grep panel-test || make 2>&1 | grep panel-test
```

Expected: a line like `panel-test            Cycle full panel through R/G/B/W/B. Usage: make panel-test ...`.

If neither `make help` nor `make` (with no target) prints help — i.e. this repo doesn't have a help target — skip this verification; the comment is still useful inline documentation.

- [ ] **Step 3: Verify dry-run expansion**

```bash
make -n panel-test
```
Expected (one line, possibly wrapped):
```
uv run python scripts/panel_color_test.py --config config/config.longboi.toml --hold 2
```

```bash
make -n panel-test CONFIG=config/config.small_sign.toml HOLD=0.5
```
Expected:
```
uv run python scripts/panel_color_test.py --config config/config.small_sign.toml --hold 0.5
```

If the dry-run output doesn't show the override taking effect, check the `$(or $(VAR),default)` syntax — `$(or)` returns the first non-empty arg.

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "$(cat <<'EOF'
feat: make panel-test target

Wraps scripts/panel_color_test.py for local (uv run) use. Same
CONFIG=/HOLD= override convention as `make validate`. Default config
is config/config.longboi.toml to match the named target on the spec.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Add the `panel-test-docker` Make target

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add the target**

Insert immediately after the `panel-test:` recipe added in Task 2, inside the same `# --- Panel diagnostics ---` block:

```make

# Run the panel-test inside the production Docker image — this is what you'll
# run on longboi/bigsign/smallsign over SSH. Requires `make build-docker` to
# have run at least once.
#
# IMPORTANT: stop the running ticker first or the diagnostic will fight it for
# the matrix:
#   docker compose stop       # or: sudo systemctl stop led-ticker
#   make panel-test-docker
#   docker compose start      # or: sudo systemctl start led-ticker
#
# --privileged + --network host match compose.yaml so behavior is identical to
# prod. -it gives the script a TTY so Ctrl-C reaches Python and the black-
# frame cleanup runs. -v scripts:ro means script edits don't require rebuilding
# the image.
panel-test-docker:  ## Cycle R/G/B/W/B inside Docker. Stop the running ticker first.
	docker run --rm -it --privileged --network host \
	  -v $(PWD)/config:/code/config:ro \
	  -v $(PWD)/scripts:/code/scripts:ro \
	  led-ticker \
	  python /code/scripts/panel_color_test.py \
	    --config /code/$(or $(CONFIG),config/config.longboi.toml) \
	    --hold $(or $(HOLD),2)
```

- [ ] **Step 2: Verify dry-run expansion**

```bash
make -n panel-test-docker
```
Expected (multi-line continuation, but all on one logical command):
```
docker run --rm -it --privileged --network host -v <repo-root>/config:/code/config:ro -v <repo-root>/scripts:/code/scripts:ro led-ticker python /code/scripts/panel_color_test.py --config /code/config/config.longboi.toml --hold 2
```

With overrides:
```bash
make -n panel-test-docker CONFIG=config/config.testing.toml HOLD=1
```
Expected: `--config /code/config/config.testing.toml --hold 1` substituted.

- [ ] **Step 3: Lint Makefile (best-effort — there's no lint target for Makefiles, but check by parsing)**

```bash
make -n panel-test-docker > /dev/null && echo OK
```
Expected: `OK`. If you see `*** missing separator` or a tab/space error, fix the indentation (Makefile recipes require literal tabs).

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "$(cat <<'EOF'
feat: make panel-test-docker target

Runs scripts/panel_color_test.py inside the production led-ticker
image — the path you'll actually use on the Pi. --privileged +
--network host match compose.yaml so behavior matches prod. -it for
Ctrl-C signal forwarding; -v scripts:ro so script edits don't require
rebuilding the image. User must stop the running ticker first.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Add the docs page

**Files:**
- Create: `docs/site/src/content/docs/tools/panel-test.mdx`

- [ ] **Step 1: Create the docs page**

Auto-picked-up by the `autogenerate: { directory: "tools" }` sidebar block at `docs/site/astro.config.mjs:80-81` — no astro.config edit needed.

Write `docs/site/src/content/docs/tools/panel-test.mdx`:

````mdx
---
title: "Tool: panel-test"
description: Cycle the panel through full-frame R, G, B, White, Black so hardware/wiring/driver issues can be diagnosed independently of any widget or config.
---

import RelatedPages from "../../../components/RelatedPages.astro";

`panel-test` paints the panel solid Red → Green → Blue → White → Black on repeat. It exists to **isolate the hardware layer from the config layer**: when widgets render wrong, this tells you whether your `led_rgb_sequence`, `panel_type`, `chain`, or `slowdown_gpio` is at fault before you start tearing apart your TOML. The implementation is a single `~50`-line script at [`scripts/panel_color_test.py`](https://github.com/jamesawesome/led-ticker/blob/main/scripts/panel_color_test.py).

It reads the `[display]` section of any led-ticker config TOML and reuses the same `LedFrame` construction the main app uses — so every panel knob (FM6126A init, BRG-vs-RGB remapping, chain length, `rp1_rio`, slowdown) is exactly as the running ticker would see it. Widget config is ignored entirely.

## Quick start — host

For a dev laptop or any non-Docker host with the `rgbmatrix` Python bindings installed:

```bash
make panel-test                                        # uses config/config.longboi.toml, 2s holds
make panel-test CONFIG=config/config.small_sign.toml  # different sign
make panel-test HOLD=4                                 # slower cycle for a long stare
```

The make target wraps `uv run python scripts/panel_color_test.py --config $(CONFIG) --hold $(HOLD)` — same `CONFIG=` override convention as [`make validate`](/tools/validate/).

Ctrl-C exits cleanly: the script paints one final black frame and swaps it on, so the panel never sticks on the last color of the cycle.

## Quick start — Docker (on the Pi)

This is what you'll actually run on a deployed sign. The diagnostic and the main ticker cannot share the matrix, so stop the ticker first:

```bash
docker compose stop          # or: sudo systemctl stop led-ticker
make panel-test-docker
# ...observe the panel, Ctrl-C when done...
docker compose start         # or: sudo systemctl start led-ticker
```

The `panel-test-docker` target runs `docker run --rm -it --privileged --network host` against the existing `led-ticker` image — same privilege flags as `compose.yaml`. The script is bind-mounted from the repo, so iteration on the script itself doesn't require `make build-docker`. The first run does require the image to exist (`make build-docker` once).

## What it does

The script cycles indefinitely through this sequence:

| # | Color | RGB         | What you should see                                   |
| - | ----- | ----------- | ----------------------------------------------------- |
| 1 | Red   | (255, 0, 0) | Every LED on the chain glows pure red.                |
| 2 | Green | (0, 255, 0) | Every LED on the chain glows pure green.              |
| 3 | Blue  | (0, 0, 255) | Every LED on the chain glows pure blue.               |
| 4 | White | (255, 255, 255) | Every LED on the chain is fully lit on all three channels. |
| 5 | Black | (0, 0, 0)   | All LEDs off.                                         |

Each color holds for `--hold` seconds (default 2.0). Per cycle it logs `[N/5] <Name> (r, g, b)` to stderr.

## What it lets you diagnose

| Symptom on panel | Likely cause | Where to fix |
| ---------------- | ------------ | ------------ |
| Red shows green, or Green shows blue, etc. | `led_rgb_sequence` is wrong | `[display] led_rgb_sequence` in your config — see [config-options](/reference/config-options/). Common values: `"RGB"` (default), `"BRG"` (panels wired G→R, R→B, B→G — typical Muen P2). |
| Bottom half of each panel garbled, mirrored, or stuck-on | `panel_type = "FM6126A"` missing or driver init not running | Set `[display] panel_type = "FM6126A"` (or `"FM6127"`). Without it FM6126A driver chips power up in a bad state. |
| Only the first panel of the chain lights up | `chain` set wrong, or HUB75 IDC cables crossed | Verify `[display] chain` matches your physical chain length. Then verify each panel's OUT goes to the next panel's IN — easy to flip an IDC cable. |
| Visible flicker during the solid-color holds | `slowdown_gpio` too low for your wiring | Bump `[display] slowdown_gpio` — Pi 4 typically wants `2`, longer chains and Pi 5 often want `3` or higher. |
| Dim or visibly-off pixels during the White frame | Hardware fault on those pixels | Physical inspection — replace the panel if widespread. |
| Pixels still glowing during the Black frame | Stuck-on pixels (hardware fault) | Physical inspection. Note position so you can rule it out in normal operation. |

## CLI flags

| Flag       | Type    | Default                         | Meaning                                              |
| ---------- | ------- | ------------------------------- | ---------------------------------------------------- |
| `--config` | path    | `config/config.longboi.toml`    | Config TOML to read `[display]` from. Widget/section config is ignored. |
| `--hold`   | float   | `2.0`                           | Seconds to hold each color before advancing.         |

The script has no other arguments. It always cycles R → G → B → W → B and always loops forever.

## Notes

- **`sudo` on the host path:** the rgbmatrix C library needs `/dev/mem` access. On a Pi you'll need `sudo uv run python scripts/panel_color_test.py …` (or just `sudo make panel-test`). The Docker path handles this via `--privileged`.
- **No GIF demo:** test patterns don't render meaningfully as GIFs — the value of this tool is on physical LEDs. The docs page intentionally has no demo image.
- **Not a substitute for `validate`:** `panel-test` cannot tell you anything about your widgets, transitions, or playlist. Use [`validate`](/tools/validate/) for config-layer checks and [`render-demo`](/tools/render-demo/) for widget-layer previews.

<RelatedPages slugs={["hardware/bigsign", "hardware/smallsign", "reference/cli", "tools/validate"]} />
````

- [ ] **Step 2: Verify docs build**

```bash
make docs-build
```
Expected: build succeeds, no Astro errors. The new `tools/panel-test/` page is generated in `docs/site/dist/tools/panel-test/`.

If you see an error about `RelatedPages` import, check the relative path matches the other tools pages (it's `../../../components/RelatedPages.astro` — three `..` for a tools page).

- [ ] **Step 3: Verify docs lint**

```bash
make docs-lint
```
Expected: prettier + astro check both clean. Fix any reported issues — usually trailing whitespace or table alignment.

- [ ] **Step 4: Spot-check the rendered page**

```bash
make docs-dev
```
Open `http://localhost:4321/tools/panel-test/` in a browser. Verify:
- Page renders with the correct title.
- "Tools" sidebar contains a `panel-test` entry (autogenerated).
- Both code blocks (host + Docker) render correctly.
- Both tables (cycle table + diagnostic table) render correctly.
- The `<RelatedPages>` block at the bottom links to all four target pages.

Stop the dev server (Ctrl-C).

- [ ] **Step 5: Commit**

```bash
git add docs/site/src/content/docs/tools/panel-test.mdx
git commit -m "$(cat <<'EOF'
docs: tools/panel-test page

Documents the panel-test diagnostic script and Make targets. Auto-
picked-up by the tools/ autogenerate sidebar block — no astro.config
change needed. Style mirrors tools/validate.mdx (lead paragraph,
quick-start blocks, what-it-does/diagnoses/flags tables, RelatedPages
footer).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Add the `panel-test` rows to the reference/cli Make-targets table

**Files:**
- Modify: `docs/site/src/content/docs/reference/cli.mdx`

The cli.mdx page has a Make-targets table at line 56+ (`## Make targets`). Two new rows go in for our new targets.

- [ ] **Step 1: Add the rows**

Open `docs/site/src/content/docs/reference/cli.mdx` and find the Make-targets table (starts around line 60 with the header row).

The existing table follows the same alphabetical-ish grouping seen in the Makefile: `make validate`, then `make plan-gif`, then `make render-demo`, etc. Insert the `panel-test` rows AFTER `make validate` (line 73 in the current file) and BEFORE `make plan-gif`. Two rows, in this order:

```
| `make panel-test`          | Cycle the panel through full-frame R/G/B/White/Black to diagnose hardware/wiring/driver issues. Usage: `make panel-test [CONFIG=config/config.longboi.toml] [HOLD=2]`. See [panel-test](/tools/panel-test/). |
| `make panel-test-docker`   | Same as `make panel-test`, but runs inside the production Docker image. Stop the running ticker first (`docker compose stop`). Usage: `make panel-test-docker [CONFIG=…] [HOLD=…]`.                          |
```

Match the column alignment of the existing rows (the table uses padded spaces for readability — copy the spacing of the row above when inserting).

- [ ] **Step 2: Verify docs build still clean**

```bash
make docs-build
```
Expected: clean.

- [ ] **Step 3: Verify docs lint still clean**

```bash
make docs-lint
```
Expected: clean. If prettier reformats your row to a different column alignment, accept the reformat — that's prettier's call.

- [ ] **Step 4: Commit**

```bash
git add docs/site/src/content/docs/reference/cli.mdx
git commit -m "$(cat <<'EOF'
docs: list panel-test targets in reference/cli Make table

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Cross-link from the hardware pages

**Files:**
- Modify: `docs/site/src/content/docs/hardware/bigsign.mdx`
- Modify: `docs/site/src/content/docs/hardware/smallsign.mdx`

Both pages have a `## Tips` section. Add a short cross-link tip at the END of each Tips section.

- [ ] **Step 1: Append a tip to bigsign.mdx**

Open `docs/site/src/content/docs/hardware/bigsign.mdx`. The `## Tips` section starts at line 135. Append a new subsection AT THE END of the `## Tips` section (before `## Reference config` at line 158):

```mdx
### Wiring or driver problem? Run `panel-test` first

If your widgets render with the wrong colors, a garbled bottom half, only one panel lit, or visible flicker, the issue is most likely in the hardware layer (`led_rgb_sequence`, `panel_type`, `chain`, `slowdown_gpio`) — not in your config. The [`panel-test`](/tools/panel-test/) diagnostic isolates the hardware layer by painting flat R/G/B/W/B colors, so you can verify wiring and driver init before debugging widgets.
```

- [ ] **Step 2: Append the same tip (lightly adapted) to smallsign.mdx**

Open `docs/site/src/content/docs/hardware/smallsign.mdx`. The `## Tips` section starts at line 96. Append a new subsection AT THE END of the `## Tips` section (before `## Reference config` at line 110):

```mdx
### Wiring or driver problem? Run `panel-test` first

If your widgets render with the wrong colors, only one panel lit, or visible flicker during scrolling, the issue is most likely in the hardware layer (`led_rgb_sequence`, `chain`, `slowdown_gpio`) — not in your config. The [`panel-test`](/tools/panel-test/) diagnostic isolates the hardware layer by painting flat R/G/B/W/B colors, so you can verify wiring before debugging widgets.
```

(Smallsign panels don't typically use FM6126A, so the `panel_type` mention is dropped from this version.)

- [ ] **Step 3: Verify both pages still build and lint**

```bash
make docs-build && make docs-lint
```
Expected: both clean.

- [ ] **Step 4: Commit**

```bash
git add docs/site/src/content/docs/hardware/bigsign.mdx docs/site/src/content/docs/hardware/smallsign.mdx
git commit -m "$(cat <<'EOF'
docs: cross-link panel-test from hardware Tips sections

Adds a "Wiring or driver problem? Run panel-test first" tip at the end
of the Tips section on both bigsign and smallsign pages. Sends users
to the hardware-layer diagnostic before they start debugging config.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Final verification pass

**Files:**
- None (verification only)

- [ ] **Step 1: Full pre-commit-style check**

```bash
make lint && make test && make docs-build && make docs-lint
```
Expected: all four clean. This is the same suite the pre-push hook would run.

- [ ] **Step 2: Help text spot-check**

```bash
uv run python scripts/panel_color_test.py --help
make -n panel-test
make -n panel-test-docker
```
Expected: all three print sensible output and exit 0.

- [ ] **Step 3: Verify git log is clean**

```bash
git log --oneline -10
```
Expected: 6 new commits from this plan (Tasks 1, 2, 3, 4, 5, 6), each with a focused subject line.

- [ ] **Step 4: Hardware-loop verification (USER step, requires physical longboi access)**

This step requires running on the Pi and observing the panel. Not automatable. Flag this to the user and present these commands for them to run:

```bash
# On the Pi (after pulling/syncing the new code):
make build-docker        # rebuild image with the new script baked in
docker compose stop      # release the matrix
make panel-test-docker   # observe panel
# ...verify R/G/B/W/B cycle, no flicker, Ctrl-C clears panel...
docker compose start     # restore normal operation
```

Confirm with the user that the panel cycled cleanly through R/G/B/W/B before considering this plan fully complete.

---

## Self-review (running before handoff)

**Spec coverage:**
- Script (`scripts/panel_color_test.py`) → Task 1 ✓
- `panel-test` Make target → Task 2 ✓
- `panel-test-docker` Make target → Task 3 ✓
- Docs page (`tools/panel-test.mdx`) → Task 4 ✓
- Cross-link from `reference/cli.mdx` → Task 5 ✓ (the spec said "if a table exists" — verified during planning, the table exists at line 56+)
- Cross-link from `hardware/bigsign.mdx` + `hardware/smallsign.mdx` → Task 6 ✓
- `DisplayConfig → LedFrame` helper extraction → already done before this work began (`build_frame_from_config` at `factories.py:859`); called out in the header section so the implementer doesn't redo it.
- Verification plan → Task 7 ✓

**Placeholder scan:** No TBDs, no "implement later", no vague-error-handling stubs. The script code block in Task 1 is complete and runnable. The Makefile diffs are exact. The docs MDX is complete prose.

**Type consistency:**
- `build_frame_from_config(display)` — same signature used in Task 1 (script) and in the existing `app/run.py:48` call site. No drift.
- `load_config(path)` — same signature, same `_coerce_warnings` attribute access as `app/run.py:44-45`.
- `frame.matrix.SwapOnVSync(canvas)` — same call shape used everywhere in the existing codebase.
- `frame.get_clean_canvas()` — same method called by the engine in `ticker.py`.

All consistent. Plan ready for handoff.
