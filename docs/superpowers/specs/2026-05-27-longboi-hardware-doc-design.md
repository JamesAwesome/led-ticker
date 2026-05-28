# Longboi Hardware Reference Doc Design

## Goal

Add a standalone hardware reference page for the "longboi" display build —
a Pi 5 + four-panel P2 widescreen used as a permanent meeting backdrop.
This is the reference infrastructure that the MLB scoreboard layout and hires
font configs are designed for.

---

## Output File

`docs/content-source/hardware-longboi.md`

New standalone page. Does not modify the existing `hardware-guide-legacy.md`.

---

## Hardware Specs

| Item | Detail |
|---|---|
| **Panels** | 4× Muen P2 indoor, 128×64 dots, 256×128mm each |
| **Panel link** | https://www.aliexpress.us/item/3256808899822704.html |
| **Chaining** | 4 panels horizontal → 512×64 physical, ~100cm × 12.8cm overall |
| **Logical resolution** | 128×16 at scale=4 |
| **Pi** | Raspberry Pi 5 |
| **HAT** | Adafruit RGB Matrix Bonnet |
| **Power supply** | Mean Well LRS-200-5, 200W 5V 40A |
| **PSU link** | https://www.amazon.com/dp/B0B6HSLSQQ |

---

## Sections

### 1. Overview

Short intro: widescreen 4-panel display (~1m wide, 13cm tall), Pi 5, sits on
top of a bookcase and appears on camera during meetings. Frame as reference
infrastructure — the MLB scoreboard layout and the hires font pipeline were
designed for this exact form factor.

### 2. Bill of Materials

Table or list:
- 4× Muen P2 128×64 LED panels (link)
- Raspberry Pi 5
- Adafruit RGB Matrix Bonnet (link to Adafruit guide)
- Mean Well LRS-200-5 5V 40A power supply (link)
- Standard IDC data cables (panel-to-panel and Pi-to-first-panel)

### 3. Assembly Notes — E-Pin (critical callout)

64-row panels require the **E address line**, which is not wired by default on
the Adafruit bonnet (it was designed for 32-row panels).

**Required step:** solder a jumper from GPIO 8 to the E pad on the bonnet.
Follow the Adafruit matrix setup guide:
https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/matrix-setup

Skipping this step produces a mirrored/garbled bottom half of the display.

This section is the primary reason the page exists — it is the one step that
is not obvious from the panel datasheet or the rpi-rgb-led-matrix README.

### 4. Physical Specs

| Property | Value |
|---|---|
| Panel resolution | 128×64 dots each |
| Panel pitch | P2 (2mm) |
| Panel size | 256mm × 128mm |
| Chain | 4 panels wide |
| Physical canvas | 512×64 px (~100cm × 12.8cm) |
| Logical canvas | 128×16 px at `default_scale = 4` |

### 5. Configuration

Reference config: `config/config.mlb_scoreboard_test.toml`

Include a brief `[display]` block snippet and a table explaining each
non-obvious setting:

| Setting | Value | Why |
|---|---|---|
| `rows` | 64 | Physical row count per panel |
| `cols` | 128 | Physical column count per panel |
| `chain_length` | 4 | Number of panels chained |
| `default_scale` | 4 | Logical→physical multiplier |
| `hardware_mapping` | `"adafruit-hat"` | Adafruit bonnet GPIO mapping |
| `panel_type` | `"FM6126A"` | Required for Muen P2 init sequence |
| `led_rgb_sequence` | `"BRG"` | Muen P2 color channel order |
| `gpio_slowdown` | 5 | Pi 5 needs higher slowdown than Pi 4 |
| `rp1_rio` | 1 | Pi 5 RP1 I/O controller fast-path |
| `pwm_bits` | 7 | Reduces flicker on camera |
| `limit_refresh_rate_hz` | 100 | Keeps display stable on camera |

`pwm_bits` and `limit_refresh_rate_hz` are worth highlighting: they were tuned
specifically for this "on camera" use case to eliminate flicker visible in
video.

### 6. Photos

Placeholder — photos to be added. Targets:
- Full display on bookcase (shows form factor)
- E-pin solder joint on the bonnet (shows the critical assembly step)
- Back of panels showing IDC cable routing

---

## Out of Scope

- Wiring diagrams (Adafruit guide covers this)
- Power injection details for brightness-limited use
- Any software config beyond the reference TOML snippet
