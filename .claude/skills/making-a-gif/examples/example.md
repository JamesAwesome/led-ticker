# Example walkthrough (dev + docs)

## Dev mode

**Sub-agent:** "Iterating on `RainbowChaseBorder` speed=20 — render a quick preview."

> Using making-a-gif skill in **dev** mode.

Draft `/tmp/gif-plan-border.toml`:

```toml
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1

[[playlist.section]]
mode = "slideshow"
hold_time = 5.0
scroll_step_ms = 25

[[playlist.section.widget]]
type = "message"
text = "BORDER CHASE PREVIEW"
border = { style = "rainbow", speed = 20 }
```

`make plan-gif CONFIG=/tmp/gif-plan-border.toml` → `duration: 6`.
Dev preview only needs ~3s to see a few sweeps, so suggest:

```bash
make render-demo CONFIG=/tmp/gif-plan-border.toml OUT=/tmp/preview-border.gif
# shorter duration override:
uv run python tools/render_demo/render.py /tmp/gif-plan-border.toml -o /tmp/preview-border.gif --duration 3
```

No caption, no header, no commit (throwaway).

## Docs mode

**User:** "Add a demo gif for `two_row` `scroll_through`."

> Using making-a-gif skill in **docs** mode.

Draft `docs/site/demos-pinned/two_row-scroll_through.toml` (top color
`[225,48,108]` magenta + `[120,230,255]` cyan — both fine, good
contrast on black). `make plan-gif` on it → `duration: 10`. Add
`# render-duration: 10` as the file's top line. Caption, matching the
voice in `widgets/two_row.mdx`: "held magenta `NOW PLAYING` on top,
cyan song title flies fully offscreen-to-offscreen on the bottom".
Then surface:

```bash
uv run python tools/render_demo/render.py docs/site/demos-pinned/two_row-scroll_through.toml -o docs/site/public/demos-pinned/two_row-scroll_through.gif --duration 10
```

Wire `<DemoGif>` into the docs page with the caption; commit the TOML,
the gif, and the docs change.
