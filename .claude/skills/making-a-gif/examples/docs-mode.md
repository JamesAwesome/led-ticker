# Example: docs mode

**User**: "I want to add a demo gif for the new `scroll_through` mode on `two_row`."

**Skill response**:

> Using making-a-gif skill in **docs** mode.

Plan:

1. Create a new pinned-demo TOML: `docs/site/demos-pinned/two_row-scroll_through.toml`.
2. Add a `# render-duration:` header based on planner math.
3. Render via `make render-demo`.
4. Wire `<DemoGif>` into `docs/site/src/content/docs/widgets/two_row.mdx`.

**Initial config draft**:

```toml
# render-duration: <to be filled by planner>
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1

[[playlist.section]]
mode = "swap"
hold_time = 7.0
scroll_step_ms = 25

[[playlist.section.widget]]
type = "two_row"
top_text = "NOW PLAYING"
top_font = "5x8"
top_color = [225, 48, 108]
bottom_text = "Some Long Song Title — Album Name (2026)"
bottom_font = "5x8"
bottom_color = [120, 230, 255]
bottom_text_scroll = "scroll_through"
```

**Run planner**:

```bash
uv run python tools/gif_plan/plan.py /tmp/two_row-scroll_through.toml --json
```

**Output (abbrev)**:
- `total_ms`: 9000
- `recommended_render_duration_s`: 10
- Flags: only `render_duration_suggestion` (info) — no header yet.

**Color overlay**:
- Top color `[225, 48, 108]` — IG brand magenta, fine.
- Bottom color `[120, 230, 255]` — cyan, fine.
- No contrast issues against the default black background.

**Caption (matching voice from `widgets/two_row.mdx`)**:
> held magenta `NOW PLAYING` on top, cyan song title flies fully offscreen-to-offscreen on the bottom — one pass per visit

**Next steps for the user**:
1. Save to `docs/site/demos-pinned/two_row-scroll_through.toml` with `# render-duration: 10` header.
2. Run: `make render-demo CONFIG=docs/site/demos-pinned/two_row-scroll_through.toml OUT=docs/site/public/demos-pinned/two_row-scroll_through.gif`.
3. Wire into the docs page with the drafted caption.
4. Commit all three new files.
