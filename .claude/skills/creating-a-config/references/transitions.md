<!-- Derived from CLAUDE.md section: Transition System. Last synced: 2026-05-07. -->

# Transition Catalog

## Selecting a transition

| Tone | Suggested transitions |
|------|----------------------|
| Minimal | `cut`, `wipe_left`, `wipe_right` |
| Playful | `nyancat_alternating`, `pokeball_alternating`, `pacman_alternating` |
| Info-dense | `push_up`, `wipe_up`, `dissolve` |
| Branded-pro | `wipe_alternating` with brand `transition_color`, `cut`, `color_flash` |

## How transitions work

All transitions implement `frame_at(t, canvas, outgoing, incoming, **kwargs) where t` ranges from 0.0 (show only outgoing) to 1.0 (show only incoming).

The **important constraints:**

- **Push** transitions use draw-blackout-draw: draw outgoing at its scroll position, SetPixel-blackout the zone where incoming will appear, then draw incoming. This prevents overlap since DrawText cannot be clipped.
- **Wipe** transitions draw a stationary outgoing widget, then use SetPixel to black out regions and draw colored sweep lines. At t=1.0, they snap to incoming.
- **Sprite** transitions draw animated sprites overlaid on the canvas using SetPixel (never call `widget.draw()` on anything other than the real canvas).
- **Instant** transitions have no animation (`cut` is 0 duration; `color_flash` is ~200ms).
- **Special** (`scroll`) uses a continuous 1px/frame scroll with a bullet separator for seamless feel.

## Family: Push (rapid scroll, both contents move together)

Rapid horizontal or vertical scroll where both outgoing and incoming move simultaneously.

| Name | Direction | Hires variant |
|------|-----------|---------------|
| `push_left` | outgoing exits left, incoming enters from right | No |
| `push_right` | incoming enters from left, outgoing exits right | No |
| `push_up` | outgoing exits top, incoming enters from bottom | No |
| `push_down` | outgoing exits bottom, incoming enters from top | No |
| `push_alternating` | Cycles through left → right → up → down each swap | No |
| `push_random` | Random push direction each swap; never repeats last | No |

## Family: Wipe (sweep line + stationary outgoing)

A sweep line moves across the canvas, erasing outgoing content and revealing incoming. Outgoing stays stationary during the wipe.

| Name | Direction | Sweep line motion | Hires variant | Color customization |
|------|-----------|-------------------|---------------|---------------------|
| `wipe_left` | Right-to-left | moves left toward screen edge | No | `transition_color` or default cyan |
| `wipe_right` | Left-to-right | moves right toward screen edge | No | `transition_color` or default magenta |
| `wipe_up` | Bottom-to-top | moves up toward top edge | No | `transition_color` or default white |
| `wipe_down` | Top-to-bottom | moves down toward bottom edge | No | `transition_color` or default green |
| `dissolve` | Random scatter | Random pixel scatter (TV static effect); operates at physical resolution | No | Not customizable (black scatter is fixed) |
| `wipe_alternating` | All four directions | Cycles left → right → up → down each swap | No | Per-direction default colors, or set `transition_color` for all, or `transition_colors = [[r,g,b], ...]` to pick custom colors per sweep |
| `wipe_random` | Random direction | Random wipe direction each swap; never repeats last | No | Default color pool per wipe direction, or customize via `transition_color` (single color for all random wipes) or `transition_colors = [[r,g,b], ...]` (pool of colors to randomly sample) |
| `split` | Center-outward | Center-outward expanding black band with magenta edge lines | No | Not customizable (magenta is fixed) |

## Family: Instant / Flash

Quick, no-animation transitions that change content instantly or with a brief flash.

| Name | Effect | Duration |
|------|--------|----------|
| `cut` | Instant switch from outgoing to incoming, no transition | 0 (immediate) |
| `color_flash` | White flash frames content change | ~200ms (at standard frame duration) |

## Family: Sprite (animated sprites with character personality)

Sprite-based transitions where characters or objects traverse the screen and reveal incoming content. On **bigsign** at scale=4, certain sprites have hi-res animated variants that auto-activate (animated webp, Pikachu sprite, or procedural rotation).

### Nyan Cat family

Nyan Cat flies across the screen with a rainbow trail.

| Name | Direction | Trail color | Hires variant (bigsign only) | Notes |
|------|-----------|-------------|------------------------------|-------|
| `nyancat` | Left-to-right | Rainbow fills screen | Yes — animated webp sprite at 256×64 | |
| `nyancat_reverse` | Right-to-left (flipped) | Rainbow fills screen | Yes — animated webp sprite at 256×64 | |
| `nyancat_alternating` | Alternates nyancat ↔ nyancat_reverse each swap | Rainbow | Yes | |

### Pokeball family

Pokeball rolls with Pikachu chasing/running alongside. On bigsign, the ball is procedural (reuses internal emoji geometry) and Pikachu is animated.

| Name | Direction | Pikachu | Ball | Hires variant (bigsign only) | Config toggles |
|------|-----------|---------|------|------------------------------|----------------|
| `pokeball` | Left-to-right | Running right | Rolling left-to-right | Yes — procedural ball + animated Pikachu | `show_pikachu=true/false`, `show_pokeball=true/false` |
| `pokeball_reverse` | Right-to-left (flipped) | Running left | Rolling right-to-left | Yes — procedural ball + animated Pikachu | `show_pikachu=true/false`, `show_pokeball=true/false` |
| `pokeball_alternating` | Alternates pokeball ↔ pokeball_reverse each swap | Alternates | Alternates | Yes | `show_pikachu=true/false`, `show_pokeball=true/false` |

### Baseball family

White baseball with red stitching rolls across the screen. On small sign, uses 4 rotation frames; on bigsign (hi-res), 8 rotation frames of procedurally-rendered ball.

| Name | Direction | Stitching rotation frames | Hires variant (bigsign only) | Notes |
|------|-----------|--------------------------|------------------------------|-------|
| `baseball` | Left-to-right | 4-frame stitch rotation | Yes — 8 rotation frames, procedural | |
| `baseball_reverse` | Right-to-left (flipped) | 4-frame stitch rotation (flipped) | Yes — 8 rotation frames, procedural | |
| `baseball_alternating` | Alternates baseball ↔ baseball_reverse each swap | Alternates | Yes | |

### Pac-Man family

Pac-Man chases 3 scared ghosts (Blinky/Pinky/Inky) with dots trailing. Includes mouth-chomping animation and ghost-wave animation.

| Name | Direction | Ghosts | Hires variant |
|------|-----------|--------|---------------|
| `pacman` | Left-to-right | Fleeing right | No (8-bit aesthetic by design) |
| `pacman_reverse` | Right-to-left (flipped) | Fleeing left | No |
| `pacman_alternating` | Alternates pacman ↔ pacman_reverse each swap | Alternates | No |

### Sailor Moon family

Moon Stick wand sweeps across the screen with a sparkle trail erasing outgoing content.

| Name | Direction | Trail effect | Hires variant |
|------|-----------|--------------|---------------|
| `sailor_moon` | Left-to-right | Sparkle trail | No (8-bit aesthetic by design) |
| `sailor_moon_reverse` | Right-to-left (flipped) | Sparkle trail | No |
| `sailor_moon_alternating` | Alternates sailor_moon ↔ sailor_moon_reverse each swap | Sparkle trail | No |

## Family: Special

Unique or multi-purpose transitions.

| Name | Effect | Use case |
|------|--------|----------|
| `scroll` | Seamless continuous scroll with bullet separator (2×2 SetPixel dots, 6px symmetric gaps). Moves at 1px/frame for constant speed. | When you want a smooth, content-aware scroll between widgets without disorienting direction changes. Unlike `forever_scroll` mode (which uses a `•` text character), `scroll` is a pure-graphics separator. |

## Recommended `transition_duration` ranges

`duration` and `transition_duration` are in **seconds** (float). The example configs use 0.5–4.0. Values above ~5s are likely a milliseconds-vs-seconds unit error.

Choose durations to match the transition's visual pace:

| Family | Range (seconds) | Notes |
|--------|-----------------|-------|
| Push | 0.4–0.8 | Faster feels snappier; 0.4s for tight pacing, 0.8s for dramatic effect |
| Wipe | 0.6–1.2 | Sweep line wants enough time to traverse; faster = more energetic, slower = more elegant |
| Instant | (n/a) | `cut` is 0; `color_flash` is 0.2–0.3 |
| Sprite (Nyan Cat, Pokeball, Baseball) | 1.5–2.5 | Sprite needs time to traverse screen; 1.5s = fast, 2.5s = leisurely |
| Pac-Man | 1.5–2.5 | Same as other sprite families |
| Sailor Moon | 1.5–2.5 | Same as other sprite families |
| Scroll | 0.8–4.0 | The longer the duration, the more relaxed the bullet separator feels. The example configs cite `4.0` for `scroll` |

## Configuring transitions

**Global fallback:** Set `[transitions] between_sections = "wipe_left"` to use `wipe_left` when a section doesn't specify a transition.

**Per-section override:** Set `transition = "pokeball"` in a section's TOML to use `pokeball` for BOTH:
1. The inter-section ENTRY when this section appears (overrides `between_sections`)
2. The inter-widget transitions (between multiple widgets within the section)

**Section transition precedence rule:** When a section's TOML writes `transition = "..."`, that transition fires for BOTH entry and inter-widget. Sections that omit `transition` fall back to `[transitions] between_sections` for entry.

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
transition_duration = 800
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
transition_duration = 800
```

Single `transition_color` with `wipe_random` works as a one-element pool — every random wipe picks that color.

## Per-widget font and colors

Transitions respect the `font_color` (and `top_color` / `bottom_color` on multi-row widgets) settings. A widget with `font_color = "rainbow"` will continue to animate during the transition (unless paused via `pause_frame()`). Frame-aware widgets pause automatically during transitions to avoid mid-animation state changes.

## Cross-scale transitions on bigsign

When a section specifies `scale` (override for that section), the transition re-wraps the canvas mid-transition at t ≥ 0.5 so the incoming widget scales in at its native size. Always capture the return value: `canvas = await run_transition(...)`.

## Register your own transition

To create a custom transition, add it to `src/led_ticker/transitions/`:

```python
from led_ticker.transitions import register_transition

@register_transition("my_transition")
class MyTransition:
    def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
        # t ranges from 0.0 (outgoing only) to 1.0 (incoming only)
        # Use canvas.SetPixel(x, y, r, g, b) for effects
        # At t=0: show outgoing. At t=1.0: show incoming.
        # NEVER call widget.draw() on anything except the real canvas.
        return canvas
```

Then import and re-export it in `src/led_ticker/transitions/__init__.py`.
