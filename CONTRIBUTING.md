# Contributing to led-ticker

Thanks for your interest! led-ticker is an asyncio Python toolkit that drives RGB
LED matrix panels from a Raspberry Pi. You can contribute without any hardware —
the test suite runs against a stub `rgbmatrix` package on any machine.

## Getting set up

```bash
git clone https://github.com/JamesAwesome/led-ticker.git
cd led-ticker
make dev        # uv sync — installs all deps + the git hooks
make test       # pytest with coverage (no Docker, no hardware)
make lint       # ruff
make format     # ruff format
```

Tests use a stub `rgbmatrix` so they run on any laptop (~2 min). Hardware is only
needed to validate real-panel rendering, which the maintainer does before release.

## Making a change

1. **Branch** — work on a feature branch, never on `main`.
2. **Test-drive it** — add or update tests alongside the change; `make test` must
   stay green. New behavior needs a test; bug fixes need a regression test.
3. **Lint + format** — `make lint` and `make format` (CI runs ruff; the hooks run
   on commit after `make dev`).
4. **Docs** — user-facing behavior is documented on the docs site
   (<https://docs.ledticker.dev>). When you change docs-site pages, follow
   `docs/DOCS-STYLE.md` (the style guide + per-page review rubric).
5. **Open a PR** against `main`. Keep it focused; describe what changed and why.
   CI must be green before review.

## Where things live

- `CLAUDE.md` is the source of truth for the **load-bearing invariants** — the
  hardware-rendering constraints and per-subsystem rules that must hold when you
  touch the render path, widgets, transitions, or the scaling wrapper. Read the
  relevant section before changing that area.
- **Adding a widget / transition** — `CLAUDE.md` has step-by-step recipes
  (`@register` / `@register_transition`, the `draw()` protocol, the `y_offset`
  contract). The test-stub canvas contract (capture the `SwapOnVSync` return,
  `SetPixel` works everywhere, no `GetPixel`) is documented there too.
- **Plugins** — extra widgets / transitions / emoji / fonts ship as plugins that
  import only from the curated `led_ticker.plugin` surface. See the
  [Plugin API reference](https://docs.ledticker.dev/plugins/api-reference/) and
  the authoring tutorial in the docs.

## Questions & discussion

Open a thread in [GitHub Discussions](https://github.com/JamesAwesome/led-ticker/discussions)
for questions, ideas, or show-and-tell. Use [Issues](https://github.com/JamesAwesome/led-ticker/issues)
for bugs and concrete feature requests.

By contributing, you agree your contributions are licensed under the project's
[MIT License](LICENSE), and you are expected to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).
