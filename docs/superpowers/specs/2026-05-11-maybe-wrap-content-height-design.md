# `_maybe_wrap` honors content_height at scale=1 — Design Spec

## Goal

Fix `src/led_ticker/ticker.py::_maybe_wrap` so that `content_height` from TOML takes effect at `scale = 1` on panels where `content_height < panel_height`. Currently at scale=1 the canvas is returned unwrapped (raw real canvas), so widgets read the real panel height for layout math and silently produce wrong band splits / placements.

## Background

Discovered in PR #47's tutorial audit. `tutorial-03c-two_row-basic.toml` used `scale = 1, content_height = 16` on a bigsign (64-tall real panel). The two_row widget read `canvas.height = 64`, split into 32+32 bands instead of the intended 16-row content area's 8+8. Result: 8×8 lo-res Instagram sprite at row 0 of the top band; BDF text centered around row 12. 12-row visible gap between sprite and text — looked broken.

Workaround in PR #47: switch the demo to `scale = 2`, which engages the wrapper. The bug remained.

Memory note: `~/.claude/projects/.../memory/project_maybe_wrap_drops_content_height_at_scale1.md` has the full diagnosis + engineer review.

## The fix

Replace the guard in `_maybe_wrap`:

```python
def _maybe_wrap(canvas, scale, content_height=16):
    if scale > 1 or content_height < canvas.height:
        return ScaledCanvas(canvas, scale=scale, content_height=content_height)
    return canvas
```

`ScaledCanvas` at scale=1 is already arithmetically correct: `_y_offset = (real.height - content_height * 1) // 2` centers a `content_height`-tall region on the panel; `SetPixel(x, y)` becomes `real.SetPixel(x*1, y*1 + _y_offset)`, which is a vertical-translate-only operation.

## Side effects flagged by engineer review

Four behaviors change at `scale=1 with content_height < panel_height`. Each is correct (it's what users expect) but worth tracking:

1. **`text_render.draw_text` switches paths.** Today routes through native `_graphics.DrawText` (since canvas is the raw real canvas, no `isinstance(canvas, ScaledCanvas)` match). After fix routes through `draw_bdf_text` (the BDF rasterizer). Pixel-equivalent in normal use, but a non-trivial path switch.

2. **`pixel_emoji.py` hi-res emoji activation.** Four `use_hires = isinstance(canvas, ScaledCanvas)` gates now fire at scale=1 on bigsign. Hi-res sprites paint at native physical resolution into a `content_height`-sized region; potential overflow if `content_height < sprite_logical_height`.

3. **`_swap` switches branches.** Path becomes `canvas.real = frame.matrix.SwapOnVSync(canvas.real)` instead of the unwrapped form. Wrapper identity preserved. Fine.

4. **Existing test `tests/test_ticker.py::test_maybe_wrap_returns_real_canvas_at_scale_1` asserts the buggy behavior.** Must be rewritten — it tests the bug, not the contract.

## Acceptance criteria

- A two_row widget at `scale = 1, content_height = 16` on a 64-tall panel splits into 8+8 logical bands (not 32+32 real bands).
- The render-path switch (`DrawText` → `draw_bdf_text`) for scale=1 wrapped canvases produces visually equivalent output for smallsign + bigsign text. Tested with a fixture asserting pixel parity between BDF rasterizer + native DrawText on representative content.
- Hi-res emoji on `scale=1 + bigsign + content_height < panel_h` configs activates the hi-res sprite path without crashing. A test asserts the sprite renders at the expected physical coords (using `unwrap_to_real`).
- The existing tutorial-03c demo at `scale=1` (after we revert the PR #47 workaround) produces visually equivalent output to the current `scale=2` version.

## Out of scope

- **Always-wrap (option a from engineer review)** — switches text render path for every smallsign user. Wider blast radius; not justified.
- **Make widgets read `content_height` explicitly (option b)** — requires threading `content_height` through every widget's draw signature. Bigger API change.
- **Document the limitation (option c)** — unacceptable; leaves a silent layout bug.
- **Reverting the PR #47 tutorial-03c framing back to scale=1** — judgment call. Defer until after the fix lands and we evaluate which framing reads better.

## Risks

- **Audit example configs/demos before landing.** Search for any `scale = 1` with explicit `content_height < panel_height`. None known in the repo's example configs, but worth confirming.
- **Glyph-rendering edge cases between native `DrawText` and the BDF rasterizer.** The BDF rasterizer is the validated production path on real hardware (Pi 5 + ScaledCanvas), but native `DrawText` is what's used on every smallsign install (no wrapper at scale=1 today). Switching that path is the biggest risk.

If the BDF rasterizer differs from `DrawText` in any glyph rendering, smallsign installs with non-default `content_height` would suddenly look slightly different. Mitigation: keep the rasterizer-vs-DrawText pixel-parity test in the suite as a permanent tripwire.
