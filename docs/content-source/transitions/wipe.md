The `wipe` family uses a stationary outgoing widget plus a colored sweep line that erases the panel direction-by-direction, then reveals the incoming widget. Snappier than push (no co-motion) and slightly more dramatic.

| Name | Sweep direction | Default color | Best for |
|------|-----------------|---------------|----------|
| `wipe_left` | right→left | cyan | General purpose, professional feel |
| `wipe_right` | left→right | magenta | Variety |
| `wipe_up` | bottom→top | white | Vertical change |
| `wipe_down` | top→bottom | green | Variety |
| `wipe_in` | both edges→center | yellow | Closing-curtain feel |
| `wipe_out` | center→both edges | red | Opening-curtain feel (center-out erase) |
| `wipe_in_vertical` | top and bottom→center row | yellow | Vertical close |
| `wipe_out_vertical` | center row→top and bottom | red | Vertical open |
| `wipe_alternating` | cycles through L→R→U→D | cycles colors | Dynamic variety |
| `wipe_random` | random direction (no immediate repeats) + random color from pool | from `transition_colors` (default: cyan/magenta/white/green) | Unpredictable variety |

`split` is the fixed-magenta twin of `wipe_out`: the same center-outward black band, but with 1-px magenta edges drawn inside the band and no color knob; its band stops one column short of each edge, so its last frame keeps a 1-px sliver of the outgoing at both sides. The center variants are not in the `wipe_alternating` / `wipe_random` pools.

## Tuning

- `transition_duration` (seconds): 0.4–0.8 feels right. Each variant has a `min_frames` floor the runner will not go under: at the default 20 fps that is 2.0 s for `wipe_left` / `wipe_right`, 1.0 s for `wipe_in` / `wipe_out`, 0.8 s for `wipe_up` / `wipe_down` and the vertical center pair. Below the floor, raise `transition_fps` instead
- `transition_color` ([r, g, b]): override the sweep color on any variant except `wipe_alternating` / `wipe_random`
- `transition_colors` (list of [r, g, b]): custom color pool for `wipe_alternating` / `wipe_random`

## Tips

`wipe_alternating` ignores `transition_color` (the singular form) — it cycles through a built-in palette tied to each direction. Use `transition_colors` (the list form) to set the pool for both `wipe_alternating` and `wipe_random`.
