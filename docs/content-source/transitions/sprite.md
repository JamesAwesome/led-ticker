Sprite transitions run a pixel-art character across the panel, erasing the outgoing widget and revealing the incoming one. They are provided by four packages in the external [led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins) monorepo — `nyancat`, `pokeball`, `pacman`, and `sailor_moon` — each with forward, reverse, and alternating variants. Reference them by their namespaced slug, e.g. `transition = "pokeball.forward"`. Add the families you want to `config/requirements-plugins.txt` (install only the ones you use) and rebuild:

```text
git+https://github.com/JamesAwesome/led-ticker-plugins.git@nyancat-v0.1.0#subdirectory=plugins/nyancat
git+https://github.com/JamesAwesome/led-ticker-plugins.git@pokeball-v0.1.0#subdirectory=plugins/pokeball
git+https://github.com/JamesAwesome/led-ticker-plugins.git@pacman-v0.1.0#subdirectory=plugins/pacman
git+https://github.com/JamesAwesome/led-ticker-plugins.git@sailor_moon-v0.1.0#subdirectory=plugins/sailor_moon
```

| Family | Variants | Hires on bigsign? | Best for |
|--------|----------|-------------------|----------|
| `nyancat` | `nyancat.forward`, `nyancat.reverse`, `nyancat.alternating` | yes (animated webp) | General playful |
| `pokeball` | `pokeball.forward`, `pokeball.reverse`, `pokeball.alternating` | yes (Pikachu run sprite + rolling pokeball) | Pop-culture variety |
| `sailor_moon` | `sailor_moon.forward`, `sailor_moon.reverse`, `sailor_moon.alternating` | no (8-bit aesthetic is the design) | Magical / sparkle |
| `pacman` | `pacman.forward`, `pacman.reverse`, `pacman.alternating` | no (8-bit aesthetic is the design) | Retro arcade |

A fifth sprite family, **`baseball`** (`baseball.roll`, `baseball.roll_reverse`, `baseball.roll_alternating` — procedural ball, 8 rotation frames, hires on bigsign; best for sports sections), ships with the **[baseball](https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/baseball)** package in the led-ticker-plugins monorepo. Install it via `config/requirements-plugins.txt` (add `git+https://github.com/JamesAwesome/led-ticker-plugins.git@baseball-v0.1.0#subdirectory=plugins/baseball` and rebuild) before using these.

## Variants

- **Forward** (`<fam>.forward`): sprite enters from the left, exits right
- **Reverse** (`<fam>.reverse`): sprite enters from the right, exits left (sprite flipped horizontally)
- **Alternating** (`<fam>.alternating`): cycles forward → reverse → forward each swap

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
