# gif-plan

Deterministic CLI that computes playtime + flags common timing bugs for led-ticker demo gifs. Sibling to `tools/render_demo/`.

## Usage

```bash
uv run python tools/gif_plan/plan.py <config.toml>
uv run python tools/gif_plan/plan.py <config.toml> --json
make plan-gif CONFIG=path/to.toml
```

## Output

**Human (default)**:
```
config: docs/site/demos-pinned/two_row-wrap.toml
playlist_total: 7000ms
recommended_render_duration: 8s
header `# render-duration:` found: 8s

section[0] mode=swap loop_count=1 → 7000ms
  widget[0] type=two_row visit=7000ms

flags:
  [ERROR] playlist :: mid_pass_cutoff
    render-duration: 8 cuts ~125ms of playlist content mid-pass.
    fix: Bump to 9 (matches the deterministic playlist total + 1s buffer).
```

**JSON (`--json`)**: same data, machine-parseable. Consumed by the `making-a-gif` skill.

## Exit codes

- `0` — clean.
- `1` — warnings only.
- `2` — errors (impossible math or mid-pass cutoff with header set).

## What it covers

Modes: `swap`.
Widgets: `message`, `countdown`, `two_row`, `image`, `still`, `gif`.

## What it does NOT cover (v1)

- `forever_scroll` / `infini_scroll` modes — timing is runtime-dependent.
- Data-fetch widgets (`weather`, `coinbase`, `mlb`, `rss_feed`, `etherscan`, `coingecko`) — visit time depends on fetched data.
- Bigsign pixel_mapper transformations — canvas-width math is approximate.

## Tests

```bash
PYTHONPATH=. uv run pytest tools/gif_plan/ -v
```

Includes:
- Per-formula unit tests (widgets + totals + flags).
- CLI integration tests.
- Dogfood against the 35 existing pinned demos with a ±20% drift tripwire.

## When NOT to invoke

If you need to render a gif, use `tools/render_demo/` directly (or `make render-demo`). This tool only plans; it doesn't render. The companion `.claude/skills/making-a-gif/` skill ties the two together.
