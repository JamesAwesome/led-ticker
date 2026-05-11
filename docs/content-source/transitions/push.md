# Push Transition Family

The `push` family scrolls the outgoing and incoming widgets together — the old slides off one edge while the new enters from the opposite edge. Both are visible simultaneously during the transition.

| Name | Direction | Best for |
|------|-----------|----------|
| `push_left` | Old exits left, new enters from right | General purpose, news-ticker feel |
| `push_right` | Old exits right, new enters from left | "Going back" in a sequence |
| `push_up` | Old exits top, new enters from bottom | Countdowns, score updates |
| `push_down` | Old exits bottom, new enters from top | Variety, vertical change |
| `push_alternating` | Cycles through left → right → up → down each swap | Dynamic variety |
| `push_random` | Random direction each swap, never repeats back-to-back | Unpredictable variety |

## Tuning

- `transition_duration` (seconds): default 0.5. Push transitions feel right at 0.4–0.8 s. Below 0.3 the motion blurs; above 1.2 it drags.
- `easing`: `linear`, `ease_in_out` (default for pushes), `ease_out`. Linear is sharper; ease_in_out feels softer.

## Tips

- Push transitions ignore `transition_color` (no sweep line, no flash).
- Push reads from the engine's "outgoing scroll position" so a widget mid-scroll continues seamlessly into the push. This is why push transitions feel snappier than wipes.
