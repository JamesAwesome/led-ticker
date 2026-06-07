The sprite family runs a pixel-art character across the panel that erases the outgoing widget and reveals the incoming one. Four families ship in the box — pick by theme.

| Family | Variants | Hires on bigsign? | Best for |
|--------|----------|-------------------|----------|
| `nyancat` | `nyancat`, `nyancat_reverse`, `nyancat_alternating` | yes (animated webp) | General playful |
| `pokeball` | `pokeball`, `pokeball_reverse`, `pokeball_alternating` | yes (Pikachu run sprite + procedural ball) | Pop-culture variety |
| `sailor_moon` | `sailor_moon`, `sailor_moon_reverse`, `sailor_moon_alternating` | no (8-bit aesthetic is the design) | Magical / sparkle |
| `pacman` | `pacman`, `pacman_reverse`, `pacman_alternating` | no (8-bit aesthetic is the design) | Retro arcade |

A fifth sprite family, **`baseball`** (`baseball.roll`, `baseball.roll_reverse`, `baseball.roll_alternating` — procedural ball, 8 rotation frames, hires on bigsign; best for sports sections), is NOT core: it ships with the external [`led-ticker-baseball`](https://github.com/JamesAwesome/led-ticker-baseball) plugin. Install the plugin (add it to `config/requirements-plugins.txt` and rebuild) before using these.

## Variants

- **Forward** (`<name>`): sprite enters from the left, exits right
- **Reverse** (`<name>_reverse`): sprite enters from the right, exits left (sprite flipped horizontally)
- **Alternating** (`<name>_alternating`): cycles forward → reverse → forward each swap

## Pokeball-specific options

| Option | Default | Description |
|--------|---------|-------------|
| `show_pikachu` | `true` | Render the Pikachu run-cycle sprite chasing the ball |
| `show_pokeball` | `true` | Render the pokeball sprite (set `false` for Pikachu-only chase) |

## Cross-scale transitions

Sprite transitions work correctly when the outgoing and incoming sections have different `scale` values (e.g. a `scale=2` section swapping to a `scale=4` section). The canvas is switched to the incoming scale before the first frame, so the sprite stays physically consistent throughout — there is no size snap mid-transition.

## Tuning

- `transition_duration`: sprite transitions need time to traverse the panel — 1.5–2.5 s feels right
- Shorter durations clip the sprite exit; longer ones work fine
