The `wipe` family uses a stationary outgoing widget plus a colored sweep line that erases the panel direction-by-direction, then reveals the incoming widget. Snappier than push (no co-motion) and slightly more dramatic.

| Name | Sweep direction | Default color | Best for |
|------|-----------------|---------------|----------|
| `wipe_left` | right→left | cyan | General purpose, professional feel |
| `wipe_right` | left→right | magenta | Variety |
| `wipe_up` | bottom→top | white | Vertical change |
| `wipe_down` | top→bottom | green | Variety |
| `wipe_alternating` | cycles through L→R→U→D | cycles colors | Dynamic variety |
| `wipe_random` | random direction (no immediate repeats) + random color from pool | from `transition_colors` (default: cyan/magenta/white/green) | Unpredictable variety |

## Tuning

- `transition_duration` (seconds): 0.4–0.8 feels right
- `transition_color` ([r, g, b]): override the sweep color on a single direction variant
- `transition_colors` (list of [r, g, b]): custom color pool for `wipe_alternating` / `wipe_random`

## Pitfalls

`wipe_alternating` ignores `transition_color` (the singular form) — it cycles through a built-in palette tied to each direction. Use `transition_colors` (the list form) to set the pool for both `wipe_alternating` and `wipe_random`.
