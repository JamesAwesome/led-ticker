Sprite transitions run a pixel-art character across the panel that erases the outgoing widget and reveals the incoming one. They ship with the external [`led-ticker-arcade`](https://github.com/JamesAwesome/led-ticker-arcade) plugin — four families, referenced by their namespaced slug. Install the plugin (add `git+https://github.com/JamesAwesome/led-ticker-arcade.git@main` to `config/requirements-plugins.txt` and rebuild) before using these.

| Family | Variants | Hires on bigsign? | Best for |
|--------|----------|-------------------|----------|
| `arcade.nyancat` | `arcade.nyancat`, `arcade.nyancat_reverse`, `arcade.nyancat_alternating` | yes (animated webp) | General playful |
| `arcade.pokeball` | `arcade.pokeball`, `arcade.pokeball_reverse`, `arcade.pokeball_alternating` | yes (Pikachu run sprite + rolling pokeball) | Pop-culture variety |
| `arcade.sailor_moon` | `arcade.sailor_moon`, `arcade.sailor_moon_reverse`, `arcade.sailor_moon_alternating` | no (8-bit aesthetic is the design) | Magical / sparkle |
| `arcade.pacman` | `arcade.pacman`, `arcade.pacman_reverse`, `arcade.pacman_alternating` | no (8-bit aesthetic is the design) | Retro arcade |

A fifth sprite family, **`baseball`** (`baseball.roll`, `baseball.roll_reverse`, `baseball.roll_alternating` — procedural ball, 8 rotation frames, hires on bigsign; best for sports sections), ships with the external [`led-ticker-baseball`](https://github.com/JamesAwesome/led-ticker-baseball) plugin. Install that plugin (add it to `config/requirements-plugins.txt` and rebuild) before using these.

## Variants

- **Forward** (`arcade.<name>`): sprite enters from the left, exits right
- **Reverse** (`arcade.<name>_reverse`): sprite enters from the right, exits left (sprite flipped horizontally)
- **Alternating** (`arcade.<name>_alternating`): cycles forward → reverse → forward each swap

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
