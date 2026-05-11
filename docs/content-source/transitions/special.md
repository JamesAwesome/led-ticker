The `special` family is a catch-all for transitions that don't fit the push, wipe, or sprite shapes — instant cuts, full-canvas effects, and continuous-scroll separators. Use them as variety between sections, or as ambient cadence on a single-section playlist.

| Name | What it does | Best for |
|------|--------------|----------|
| `cut` | Instant switch — outgoing replaced by incoming on a single frame | Minimal default; "no transition" feel |
| `color_flash` | Full-canvas white flash between content | Punctuating a major section change |
| `dissolve` | Random pixel scatter (seeded RNG) creates a TV-static effect that resolves to the incoming widget | Dramatic between unrelated sections |
| `split` | Center-outward expanding black band with magenta edge lines | Geometric / theatrical |
| `scroll` | Seamless continuous scroll with a 2×2 bullet-dot separator (6 px symmetric gaps), 1 px / frame for constant speed | Marquee feel — no pause, no flash |

## Tuning

- `transition_duration` (seconds): default 0.5. `cut` ignores it (single frame). `color_flash`, `dissolve`, and `split` look right between 0.4–0.8 s. `scroll` is the exception — duration is implied by content width and the 1 px / frame cadence, not by `transition_duration`.
- `transition_color` ([r, g, b]): used by `color_flash` (overrides the white) and `dissolve` (tints the static). Ignored by `cut`, `split`, `scroll`.

## Tips

- **`scroll` vs `forever_scroll` mode look similar but render differently.** `scroll` is a section-to-section transition that uses `_scroll_between` to bridge two widgets with a `•` separator at 1 px / frame. `forever_scroll` is a section *mode* that scrolls all widgets continuously side-by-side with a separator drawn from the `DEFAULT_BUFFER_MSG` text character. Same visual rhythm, different code paths and different config surfaces.
- **`dissolve` runs at physical resolution on bigsign.** Implementation unwraps the `ScaledCanvas` so the per-pixel scatter has the full 16,384-pixel grain. A logical-grain version (1,024 grain points at scale=4) collapses to fade-through-black at t=0.5 — that's a real bug the implementation avoids. If you ever rewrite `dissolve`, keep it on the unwrapped real canvas; tripwire `test_scatter_uses_physical_resolution_through_scaled_canvas` will catch a regression.
