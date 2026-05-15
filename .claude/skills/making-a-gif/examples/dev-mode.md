# Example: dev mode

**Sub-agent context**: "I'm iterating on the new `border_chase_speed` field for `RainbowChaseBorder`. Render a quick preview so I can spot-check the speed=20 setting."

**Skill response**:

> Using making-a-gif skill in **dev** mode.

Plan:

1. Draft a minimal TOML exercising the change.
2. Save to `/tmp/`.
3. Run the planner.
4. Suggest a SHORTER render-duration (one pass + half-second, not a polished loop).
5. Suggest `make render-demo` with `/tmp/` output.

**Draft config**:

```toml
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1

[[playlist.section]]
mode = "swap"
hold_time = 5.0
scroll_step_ms = 25

[[playlist.section.widget]]
type = "message"
text = "BORDER CHASE PREVIEW"
font = "5x8"
border = { style = "rainbow_chase", speed = 20 }
```

**Planner output**:
- `total_ms`: 5000 (static text + hold).
- `recommended_render_duration_s`: 6 (polished default).

**Dev-mode adjustment**:
- For a static `border` preview, ~3 seconds is enough to see two-three rainbow sweeps.
- Suggest `--duration 3` override.

**Color overlay**: no flags (text uses default white-ish — the engine renders it OK on black; this is a dev preview, not a customer-facing demo).

**Command for the user**:

```bash
make render-demo CONFIG=/tmp/border-chase-preview.toml OUT=/tmp/preview-border-chase-20.gif
# (Or with shorter duration:)
uv run python tools/render_demo/render.py /tmp/border-chase-preview.toml -o /tmp/preview-border-chase-20.gif --duration 3
```

**Skip**:
- No caption draft (dev mode).
- No commit suggestion (throwaway).
- No `# render-duration:` header in the TOML (dev mode treats render-duration as a CLI flag, not a file header).
