# Hardware Panel Tuning Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated `hardware/panel-tuning.mdx` page that explains every `[display]` performance and wiring knob in depth, with practical tuning guidance, and cross-links it from the existing display concept page and config reference.

**Architecture:** One new MDX page under `docs/site/src/content/docs/hardware/` covering all the non-geometry `[display]` knobs (PWM, dithering, GPIO timing, Pi 5 options, scan mode, wiring quirks) grouped by symptom and purpose. Two small edits to existing pages add cross-links. No Python changes.

**Tech Stack:** MDX (Astro Starlight), `TomlExample` and `RelatedPages` Astro components, `pnpm prettier`.

---

## File Structure

- **Create:** `docs/site/src/content/docs/hardware/panel-tuning.mdx` — new tuning guide
- **Modify:** `docs/site/src/content/docs/concepts/display.mdx` — add link at bottom of `[display] reference` section
- **Modify:** `docs/site/src/content/docs/reference/config-options.mdx` — add "see tuning guide" note below the `[display]` table

---

### Task 1: Create `hardware/panel-tuning.mdx`

**Files:**
- Create: `docs/site/src/content/docs/hardware/panel-tuning.mdx`

- [ ] **Step 1: Create the file with the complete content**

```mdx
---
title: "Hardware: Panel tuning"
description: How to tune pwm_bits, pwm_lsb_nanoseconds, pwm_dither_bits, slowdown_gpio, rp1_rio, limit_refresh_rate_hz, scan_mode, multiplexing, row_addr_type, panel_type, and led_rgb_sequence for your LED panel.
---

import TomlExample from "../../../components/TomlExample.astro";
import RelatedPages from "../../../components/RelatedPages.astro";

The geometry knobs (`rows`, `cols`, `chain`, `default_scale`) are covered
on the [Display concept page](/concepts/display/). This page covers
everything else in `[display]`: the refresh-quality knobs, the Pi 5
extras, and the panel-wiring settings. All of these map straight onto
`rgbmatrix` library options — led-ticker passes them through without
interpretation.

Most builds never need to change anything here beyond `slowdown_gpio`
and `brightness`. Start with the reference configs; only reach for
these knobs when a specific symptom appears.

---

## PWM and color depth

### `pwm_bits` (default `11`)

Controls the bit depth of the PWM signal sent to each color channel.
Higher values give more color gradations (11-bit = 2048 steps per
channel) but slow down the hardware refresh rate because the panel has
to clock out more bit-planes per frame. Lower values speed refresh at
the cost of some color precision.

**When to lower it:** On long chains (5+ panels), the uncapped PWM
refresh rate at `pwm_bits = 11` is fast enough that individual
bit-planes become visible during fast motion — a shimmer or waterfall
artifact. Dropping to `pwm_bits = 8` speeds up the scan cycle roughly
8×, which usually eliminates the shimmer. Color banding at 8-bit is
imperceptible at normal viewing distances on most content.

The bigsign reference build uses `pwm_bits = 8`. The smallsign leaves
it at the default `11`.

<TomlExample
  title="Bigsign — trade color depth for faster refresh"
  code={`[display]
pwm_bits = 8`}
/>

### `pwm_lsb_nanoseconds` (default `130`)

The time duration of the least significant PWM bit. The rgbmatrix
library clocks all higher bit-planes as multiples of this base timing.
Too low → not enough time for each shift register stage to settle →
colors look wrong or washed out. Too high → slower overall refresh.

The default `130` ns works well on Pi 4. Some Pi 5 builds running at
very high clock speeds may benefit from nudging this up to `150`–`200`
if colors look incorrect even with `slowdown_gpio` set appropriately.
Change this only after you've confirmed that `slowdown_gpio` alone
doesn't fix color artifacts.

### `pwm_dither_bits` (default `0`)

Temporal dithering depth. `0` = off. `1` or `2` enables one or two
bits of dithering, spreading the PWM energy across 2 or 4 consecutive
refresh frames rather than applying it all within a single frame.

**What it fixes:** On panels scanned in two halves (top and bottom),
the row at the center seam is refreshed at the boundary between the
two scan halves. At sub-100% brightness, the PWM duty cycle can clip
unevenly on that row, making it appear slightly brighter than its
neighbors. Dithering distributes that energy more evenly and reduces
the brightness differential.

**When to use it:** If a specific row — typically the center row of
a 32-tall panel — appears noticeably brighter than the rows around it
at your working brightness setting, try `pwm_dither_bits = 1` first.
If that's insufficient, try `2`. Values above `2` are not supported by
the underlying library.

<TomlExample
  title="Enable one bit of temporal dithering"
  code={`[display]
pwm_dither_bits = 1`}
/>

---

## GPIO timing

### `slowdown_gpio` (default `1`)

Inserts CPU wait cycles between each GPIO write to slow down the
data clock reaching the panel's shift registers. Higher values give
each register stage more time to settle before the next bit arrives.

**Symptoms when too low:** Random pixel noise, scattered wrong-color
pixels, or columns of incorrect color that flicker. These are all
setup-time violations — the next bit arrives before the previous one
has propagated.

**Tuning by hardware:**

| Hardware | Typical value |
|---|---|
| Pi 4, 1–3 panels | `1`–`2` |
| Pi 4, 4–5 panels | `2`–`3` |
| Pi 5, RIO mode | `3`–`4` |
| Pi 5, PIO mode | `2`–`3` |

Start at the low end and raise by `1` each time until pixel noise
disappears. Values above `4` rarely help; if you're still seeing
noise at `4`, the cause is likely a cable or power issue rather than
timing.

<TomlExample
  title="Typical Pi 5 starting point"
  code={`[display]
slowdown_gpio = 3`}
/>

---

## Pi 5 options

These two fields are only available in the
[kingdo9 fork](https://github.com/kingdo9/rpi-rgb-led-matrix)
of the rgbmatrix library, which is what the led-ticker Docker image
ships. They are silently ignored on Pi 4 builds and on older library
versions that don't expose them.

### `rp1_rio` (default `0`)

Pi 5 uses the RP1 peripheral controller instead of the BCM2711 found
in Pi 4. The kingdo9 fork exposes two GPIO backends for RP1:

- `0` — **PIO mode.** Uses the RP1's programmable I/O block. Low CPU
  usage (typically < 5% per core). This is the safe default.
- `1` — **RIO mode.** Uses direct ARM-core register I/O. Higher CPU
  usage (~10–15%), but achieves a meaningfully higher hardware refresh
  rate, which helps reduce motion artifacts on long chains.

Use `rp1_rio = 1` when you need the highest possible refresh rate and
have CPU headroom to spare. The bigsign reference build uses RIO mode.

### `limit_refresh_rate_hz` (default `0`, Pi 5 RIO only)

Caps the hardware refresh rate in Hz. `0` = unlimited.

In RIO mode, the uncapped refresh rate is fast enough that
`SwapOnVSync` can land at different positions within the panel's scan
cycle from frame to frame. On long chains this produces a visible
horizontal seam that drifts across the panel during motion — the top
and bottom halves of the panel appear slightly out of phase with each
other.

Setting `limit_refresh_rate_hz = 100` makes the scan cycle more
predictable relative to the engine's vsync, which eliminates the
seam drift. It also gives the per-row PWM clocking more time between
refreshes, which can reduce the center-row brightness artifact
described under `pwm_dither_bits`.

`100` Hz is a good starting point. Go higher only if you observe
choppiness at 100 (unlikely; the engine runs at 20 fps).

<TomlExample
  title="Pi 5 bigsign — RIO mode with rate cap"
  code={`[display]
rp1_rio = 1
limit_refresh_rate_hz = 100`}
/>

---

## Scan mode

### `scan_mode` (default `0`)

Controls how the panel scans its rows.

- `0` — **Progressive** (default). Rows are scanned in order from
  top to bottom. Works for all standard HUB75 panels.
- `1` — **Interlaced.** Odd and even rows alternate. Required by a
  small number of unusual panels.

Do not change this unless you observe that every other row is blank
or doubled. If you do see that symptom, try `scan_mode = 1` before
reaching for `multiplexing`.

---

## Panel wiring and driver quirks

The following settings deal with non-standard panel wiring schemes
and driver IC initialization. For a freshly purchased panel from a
reputable source, all four defaults are correct. Reach for these only
when the panel shows the specific symptom described.

### `multiplexing` (default `0`)

Some manufacturers wire the row-select lines in non-standard patterns
to achieve higher pixel density or unusual aspect ratios. The
`multiplexing` value tells the library which pattern to expect.

| Value | Scheme | When to use |
|---|---|---|
| `0` | Direct (standard HUB75) | Default; almost all panels |
| `1` | Stripe | Some high-density P2 panels |
| `2` | Checker | Rare — checkerboard row select |
| `3` | Spiral | Rare — spiral row select |
| `4` | ZStripe | Some P2.5 and P3 panels |
| `5` | ZnMirrorZStripe | Rare |

**Symptom:** The bottom half of the panel displays the top half's
content in reverse, or the lower half is garbled. Start with `1`,
then try `4`.

### `row_addr_type` (default `0`)

How the panel decodes the row address lines.

| Value | Type | When to use |
|---|---|---|
| `0` | Direct | Default; standard 5-bit address |
| `1` | AB-address | Some 64-row panels that only expose 2 address lines |
| `2` | Direct-shifted | Uncommon |
| `3` | ABC-shifted | Uncommon |

**Symptom:** Rows appear in the wrong order or two rows swap.

### `panel_type` (default `""`)

Some driver ICs need a vendor-specific initialization sequence sent
over the data lines before they accept pixel data. Without it, they
power up in an undefined state.

| Value | IC | When to use |
|---|---|---|
| `""` | (none, default) | Standard panels |
| `"FM6126A"` | FM6126A | Common on cheap P2/P3 AliExpress panels |
| `"FM6127"` | FM6127 | Less common variant |

**Symptom:** Panel powers up with the bottom half mirrored or the
display showing random garbage that doesn't clear. This is almost
always an FM6126A panel with no init sequence.

<TomlExample
  title="AliExpress P2/P3 panel with FM6126A driver"
  code={`[display]
panel_type = "FM6126A"`}
/>

### `led_rgb_sequence` (default `"RGB"`)

The physical wire order of the red, green, and blue channels on the
panel's HUB75 connector. Most panels use standard RGB order. Some
manufacturers swap channels.

**Symptom:** Colors look obviously wrong — red renders as blue,
purple objects appear yellow, etc. A useful diagnostic: display a
pure white image; if it looks white, the order is correct. Display
pure red; if it shows as a different color, adjust the sequence to
match.

Common alternatives: `"RBG"`, `"GRB"`, `"GBR"`, `"BRG"`, `"BGR"`.

A specific tell: purple or blue tint with missing vibrancy often
means green and blue are swapped — try `"RBG"`.

---

## Putting it together: tuning checklist

Start with the reference config closest to your hardware and work
through this list in order. Each item addresses a distinct failure
mode.

1. **Pixel noise / wrong colors** → raise `slowdown_gpio` by `1`
   until clean. Stop at `4`.

2. **Color looks washed or incorrect despite clean pixels** →
   raise `pwm_lsb_nanoseconds` to `150`, then `200`. Confirm
   `gpio_mapping` matches your HAT.

3. **Wrong channel order** → adjust `led_rgb_sequence`.

4. **Bottom half garbled or mirrored** → set `panel_type =
   "FM6126A"`, or try `multiplexing = 1`, `4`.

5. **Shimmer / waterfall artifact during motion** (long chains) →
   lower `pwm_bits` to `8`.

6. **Center-row brighter than neighbors** (sub-100% brightness) →
   try `pwm_dither_bits = 1`. Combine with `limit_refresh_rate_hz
   = 100` on Pi 5 RIO builds.

7. **Scan-seam drift during motion** (Pi 5 RIO, long chains) →
   set `limit_refresh_rate_hz = 100`.

8. **Alternating blank rows** → try `scan_mode = 1`.

<RelatedPages slugs={["concepts/display", "hardware/bigsign", "hardware/smallsign", "reference/config-options"]} />
```

- [ ] **Step 2: Verify the file was created**

```bash
ls -la docs/site/src/content/docs/hardware/panel-tuning.mdx
```

Expected: file exists.

- [ ] **Step 3: Commit**

```bash
git add docs/site/src/content/docs/hardware/panel-tuning.mdx
git commit -m "docs: add hardware/panel-tuning guide for all display perf and wiring knobs"
```

---

### Task 2: Add cross-links from existing pages

**Files:**
- Modify: `docs/site/src/content/docs/concepts/display.mdx`
- Modify: `docs/site/src/content/docs/reference/config-options.mdx`

- [ ] **Step 1: Update `concepts/display.mdx` — replace the closing paragraph of `[display] reference`**

Find the existing paragraph that starts with "The most-touched fields are above" (around line 65–67):

```mdx
The most-touched fields are above (`rows`, `cols`, `chain`,
`default_scale`, `pixel_mapper`, `slowdown_gpio`); see the
reference page when you need `pwm_bits`, `pwm_lsb_nanoseconds`,
`rp1_rio`, or the other Pi-tuning options.
```

Replace it with:

```mdx
The most-touched fields are above (`rows`, `cols`, `chain`,
`default_scale`, `pixel_mapper`, `slowdown_gpio`). For the
refresh-quality and panel-wiring knobs (`pwm_bits`, `pwm_dither_bits`,
`rp1_rio`, `scan_mode`, `multiplexing`, etc.) see the
[Panel tuning guide](/hardware/panel-tuning/).
```

- [ ] **Step 2: Update `reference/config-options.mdx` — add a "see also" line below the `[display]` table**

Find the paragraph that immediately follows the `[display]` table (around line 65):

```mdx
These are the common knobs. The full set of `rgbmatrix` library
options is broader — see `CLAUDE.md` for the additional Pi-5 tuning
notes and what each setting interacts with.
```

Replace it with:

```mdx
For in-depth explanations of the refresh-quality and wiring fields —
including tuning steps and symptom-based guidance — see the
[Panel tuning guide](/hardware/panel-tuning/).
```

- [ ] **Step 3: Run prettier to format both files**

```bash
cd docs/site && pnpm prettier --write src/content/docs/concepts/display.mdx src/content/docs/reference/config-options.mdx
```

Expected: files reformatted with no errors.

- [ ] **Step 4: Commit**

```bash
git add docs/site/src/content/docs/concepts/display.mdx docs/site/src/content/docs/reference/config-options.mdx
git commit -m "docs: cross-link to panel-tuning guide from display concept and config reference"
```

---

### Task 3: Prettier pass on the new page + final check

**Files:**
- Modify: `docs/site/src/content/docs/hardware/panel-tuning.mdx`

- [ ] **Step 1: Run prettier on the new page**

```bash
cd docs/site && pnpm prettier --write src/content/docs/hardware/panel-tuning.mdx
```

Expected: no errors. File may be reformatted (long table cells get wrapped differently).

- [ ] **Step 2: Run the Python test suite to confirm no regressions**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.worktrees/pwm-dither-bits && python -m pytest tests/ -q 2>&1 | tail -10
```

Expected: all tests pass (currently 2146 passed, 2 skipped).

- [ ] **Step 3: Commit if prettier made changes**

```bash
git add docs/site/src/content/docs/hardware/panel-tuning.mdx
git commit -m "docs: prettier formatting pass on panel-tuning guide"
```

If prettier made no changes, skip the commit.
