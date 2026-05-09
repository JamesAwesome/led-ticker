The sprite family runs a pixel-art character across the panel that erases the outgoing widget and reveals the incoming one. Five families ship in the box — pick by theme.

| Family | Variants | Hires on bigsign? | Best for |
|--------|----------|-------------------|----------|
| `nyancat` | `nyancat`, `nyancat_reverse`, `nyancat_alternating` | yes (animated webp) | General playful |
| `pokeball` | `pokeball`, `pokeball_reverse`, `pokeball_alternating` | yes (Pikachu run sprite + procedural ball) | Pop-culture variety |
| `baseball` | `baseball`, `baseball_reverse`, `baseball_alternating` | yes (procedural ball, 8 rotation frames) | Sports sections |
| `sailor_moon` | `sailor_moon`, `sailor_moon_reverse`, `sailor_moon_alternating` | no (8-bit aesthetic is the design) | Magical / sparkle |
| `pacman` | `pacman`, `pacman_reverse`, `pacman_alternating` | no (8-bit aesthetic is the design) | Retro arcade |

## Variants

- **Forward** (`<name>`): sprite enters from the left, exits right
- **Reverse** (`<name>_reverse`): sprite enters from the right, exits left (sprite flipped horizontally)
- **Alternating** (`<name>_alternating`): cycles forward → reverse → forward each swap

## Pokeball-specific options

| Option | Default | Description |
|--------|---------|-------------|
| `show_pikachu` | `true` | Render the Pikachu run-cycle sprite chasing the ball |
| `show_pokeball` | `true` | Render the pokeball sprite (set `false` for Pikachu-only chase) |

## Tuning

- `transition_duration`: sprite transitions need time to traverse the panel — 1.5–2.5 s feels right
- Shorter durations clip the sprite exit; longer ones work fine
