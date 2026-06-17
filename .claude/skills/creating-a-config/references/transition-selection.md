# Transition Selection & Configuration Guide

Use this guide to **choose** a transition (by tone) and **wire** it into the config (global default, per-section override, fine-grained entry/widget control).

**For each transition family's catalog and tuning** — the full list of names, directions, `transition_duration` ranges, `easing`, and sweep colors — **read the family fact-pack:** `docs/content-source/transitions/push.md`, `wipe.md`, `sprite.md`, `special.md`. Those are the source of truth for per-family options.

`transition_duration` (and `duration`) are in **seconds** (float). The example configs use 0.4–4.0. A value of `800` is a milliseconds-era mistake — the validator (Rule 21) warns when a duration "looks like milliseconds." Author durations in seconds.

---

## Selecting a transition

| Tone | Suggested transitions |
|------|----------------------|
| Minimal | `cut`, `wipe_left`, `wipe_right` |
| Playful | `arcade.nyancat_alternating`, `arcade.pokeball_alternating`, `arcade.pacman_alternating` (requires `led-ticker-arcade` plugin) |
| Info-dense | `push_up`, `wipe_up`, `dissolve` |
| Branded-pro | `wipe_alternating` with brand `transition_color`, `cut`, `color_flash` |

---

## Configuring transitions

**Global fallback:** Set `[transitions] between_sections = "wipe_left"` to use `wipe_left` when a section doesn't specify a transition.

**Per-section override:** Set `transition = "arcade.pokeball"` in a section's TOML to use `arcade.pokeball` for BOTH:
1. The inter-section ENTRY when this section appears (overrides `between_sections`).
2. The inter-widget transitions (between multiple widgets within the section).

**Section transition precedence rule:** When a section's TOML writes `transition = "..."`, that transition fires for BOTH entry and inter-widget. Sections that omit `transition` fall back to `[transitions] between_sections` for entry.

### Fine-grained control: `entry_transition` and `widget_transition`

For independent control over entry and within-section transitions, use the dedicated fields:

- `entry_transition` — controls how THIS section appears (overrides both `transition` and `between_sections` for this section's entry only).
- `widget_transition` — controls inter-widget swaps within this section (overrides `transition` for within-section only).

```toml
[[playlist.section]]
mode = "swap"
entry_transition = "arcade.pokeball"     # this section pops in with pokeball (requires led-ticker-arcade)
widget_transition = "wipe_left"          # widgets within the section wipe left between swaps
```

Both fields accept the same string or dict form as `transition`:

```toml
[[playlist.section]]
mode = "swap"
entry_transition = {type = "dissolve", duration = 0.8}
widget_transition = "push_left"
```

**Precedence (entry):** `entry_transition` > `transition` (when set) > `[transitions] between_sections`
**Precedence (widget):** `widget_transition` > `transition` (when set) > none (cut)

### Sweep line color customization (wipe transitions)

Wipe transitions accept `transition_color` or `transition_colors` to customize the sweep-line color. **Both keys are valid at two levels:**

1. **Global** (`[transitions]` block) — applies to every section that uses a wipe.
2. **Per-section** (`[[playlist.section]]` block) — overrides the global value for that section only.

Per-section override:

```toml
[[playlist.section]]
mode = "swap"
transition = "wipe_left"
transition_color = [255, 100, 150]   # pink sweep line for this section only
transition_duration = 0.8
```

Global default (every wipe in the config uses this unless overridden):

```toml
[transitions]
default = "wipe_left"
between_sections = "dissolve"
duration = 0.6
transition_color = [255, 200, 130]   # cream — applies to all wipes globally
```

For `wipe_random` with a custom color pool (per-section):

```toml
[[playlist.section]]
mode = "swap"
transition = "wipe_random"
transition_colors = [
    [255, 0, 0],      # red
    [0, 255, 0],      # green
    [0, 0, 255],      # blue
]
transition_duration = 0.8
```

A single `transition_color` with `wipe_random` works as a one-element pool — every random wipe picks that color. See `docs/content-source/transitions/wipe.md` for which variants honor the singular vs. list form.
