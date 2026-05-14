# Design: `gif_loops = 0` — play through `hold_time`

**Date:** 2026-05-14
**Status:** Approved

## Overview

Repurpose `gif_loops = 0` (currently rejected at post-init) to mean **"play loops that fit in the section's `hold_time`, then stop at a clean frame boundary."** Replaces the `gif_loops = 999` magic-number idiom that appears in `config.bigsign.moonbunny.example.toml` and 10 other example configs.

## Field surface

```toml
[[playlist.section]]
mode = "swap"
hold_time = 8.0

[[playlist.section.widget]]
type = "gif"
path = "sparkles.gif"
gif_loops = 0   # NEW: play through hold_time
```

- **Type:** `gif_loops: int` (unchanged). Default still `1`.
- **Domain change:** previously `gif_loops >= 1`; now `gif_loops >= 0`.
- **Semantics for `gif_loops = 0`:** play as many full gif loops as fit in `section.hold_time`. Stop at the next clean frame boundary after the time budget exhausts. Minimum 1 loop always plays (even if hold_time < loop_ms; the gif always gets one full traversal).
- **Semantics for `gif_loops >= 1`:** unchanged. Plays exactly that many loops; `hold_time` doesn't apply.

## Non-goals

- Not changing `StillImage` semantics. `hold_seconds` stays the still's per-visit timing knob.
- Not changing `gif_loops` for non-zero values. The existing fixed-count behavior is preserved.
- Not deprecating `gif_loops = 999` or similar magic numbers — they continue to work. The docs steer users at `0` going forward.

## Architecture

### Engine wiring

`_play_widget` in `ticker.py` currently has signature:

```python
async def _play_widget(canvas, frame, widget) -> Canvas
```

Extend to accept the section's hold_time:

```python
async def _play_widget(canvas, frame, widget, *, section_hold_time: float = 3.0) -> Canvas
```

`_show_one` (the caller that dispatches to `_play_widget` for play-style widgets) already has `section.hold_time` in scope (it's passed to the regular `_swap_and_scroll` path). Pass it through to `_play_widget`.

### Widget wiring

`GifPlayer.play()` and `StillImage.play()` accept a new `hold_time: float | None = None` kwarg. `_play_widget` passes `section_hold_time` to `widget.play()`.

For `GifPlayer`:

```python
async def play(self, real_canvas, frame, loop_count: int = 1, *, hold_time: float | None = None) -> Canvas:
    # Resolve the effective loop count.
    # gif_loops = 0 + hold_time set → compute loops that fit
    if loop_count == 0 and hold_time is not None:
        loop_ms = self._loop_ms or sum(d for _, d in self._frames)
        if loop_ms > 0:
            loop_count = max(1, int(hold_time * 1000 / loop_ms))
        else:
            loop_count = 1
    elif loop_count == 0:
        # No hold_time available (e.g. forever_scroll context) — fall back to 1.
        loop_count = 1
    # rest of play() uses loop_count as today
```

For `StillImage`: accept the kwarg, ignore it. StillImage already has its own `hold_seconds` field as the per-visit duration knob; section `hold_time` doesn't apply to it. The kwarg exists for protocol uniformity.

### Validation

Update `__attrs_post_init__` on `GifPlayer`:

```python
# Was: if self.gif_loops < 1: raise
# Now:
if self.gif_loops < 0:
    raise ValueError(f"gif_loops must be >= 0, got {self.gif_loops!r}")
```

That's the only change.

No new validator rule. `gif_loops = 0` is now valid; users who set it without setting `hold_time` get the default 3.0s × loops_at_3.0s playback, which is graceful (per the elif branch above, if `hold_time` ever isn't threaded through, fall back to 1 loop).

## Implementation file map

1. **`src/led_ticker/widgets/gif.py`** — `__attrs_post_init__` (allow 0), `play()` (new `hold_time` kwarg, branch for `loop_count == 0`).
2. **`src/led_ticker/widgets/still.py`** — `play()` signature gains the kwarg, ignored.
3. **`src/led_ticker/ticker.py`** — `_play_widget` signature change, `_show_one` passes `section.hold_time`.
4. **Tests:**
   - `tests/test_widgets/test_gif.py` — new tests for `gif_loops = 0` semantics (with/without hold_time, loop-count math).
   - `tests/test_ticker_display.py` (or wherever `_play_widget` is tested) — assert hold_time flows through.
5. **Docs:**
   - `docs/site/src/content/docs/widgets/gif.mdx` — document `gif_loops = 0` as the canonical "play through hold_time" form. The `gif_loops = 999` magic number now reads as the legacy workaround.
   - `docs/site/src/content/docs/content-source/widgets/gif.md` (OptionsTable source) — update `gif_loops` row description.
   - `docs/site/src/content/docs/concepts/sections-and-modes.mdx` — if it discusses gif timing, add a one-liner for the new idiom.
6. **Example configs** — migrate `gif_loops = 999` → `gif_loops = 0` in:
   - `config/config.bigsign.moonbunny.example.toml` (2 occurrences)
   - Other `gif_loops = 999` (and `gif_loops` set to large numbers like 100+) instances in `config/` and `docs/site/demos-*/`. Spot-check each — some may genuinely want a high finite count.

## Test plan

### Widget tests (`test_gif.py`)

- `test_gif_loops_zero_with_hold_time_computes_loops` — `gif_loops = 0`, `hold_time = 8.0`, mock `_loop_ms = 1000` → expect 8 loops.
- `test_gif_loops_zero_with_short_hold_time_minimum_one_loop` — `gif_loops = 0`, `hold_time = 0.5`, `_loop_ms = 1000` → expect 1 loop (minimum).
- `test_gif_loops_zero_without_hold_time_defaults_one_loop` — `gif_loops = 0`, `hold_time = None` → expect 1 loop.
- `test_gif_loops_positive_unchanged_with_hold_time_set` — `gif_loops = 5`, `hold_time = 8.0` → expect 5 loops (no truncation, `hold_time` doesn't apply to fixed counts).
- `test_gif_loops_zero_is_valid_post_init` — direct construction with `gif_loops = 0` no longer raises.
- `test_gif_loops_negative_still_raises` — `gif_loops = -1` raises; boundary preserved.

### Engine tests

- `test_play_widget_passes_hold_time_to_gif` — `_play_widget(section_hold_time=8.0)` reaches `widget.play(hold_time=8.0)`.
- `test_play_widget_passes_hold_time_to_still` — same, even though still ignores it.

### Regression sweep

- Validate every example TOML — confirm none break.
- Update the 2 moonbunny + 11 other configs with `gif_loops = 999` to `gif_loops = 0`. Validate they still produce identical or better behavior on the panel (manual smoke test if possible).

## Out of scope

- StillImage doesn't get a behavior change. Its `hold_seconds` is the right knob; renaming or aligning is a separate discussion (`config-surface-review` flagged this as `hold_time` family inconsistency — leave for a future PR).
- The general unknown-kwarg validator is still deferred.
- `gif_loops = 0` in `forever_scroll` context: `_play_widget` is called from `_run_swap`, not from `forever_scroll` paths. In `forever_scroll`, gif widgets don't go through `_play_widget` (they're rendered by `_scroll_side_by_side` instead). So `gif_loops = 0` in a `forever_scroll` section falls back to the `elif` branch (1 loop) — acceptable; that mode wasn't the target use case.

## Implementation notes

- The kwarg style on `_play_widget` and `widget.play()` is `hold_time` (not `section_hold_time`) inside the widget — the widget doesn't care that the value comes from the section. Use `section_hold_time` only on `_play_widget` to disambiguate from any other `hold_time` in the engine scope.
- For the test of `gif_loops = 0 + hold_time`, mock `widget._loop_ms` directly (don't decode a real gif). The math is `int(hold_time * 1000 / loop_ms)`.
- The `max(1, ...)` floor in the formula matches the existing `loops = max(1, loop_count)` line in the current `play()` — same defensive pattern.
- If a future widget type implements `play()` and doesn't yet accept `hold_time`, `_play_widget` should pass it via a kwarg that the widget can choose to accept. Use `**kwargs`-friendly signatures or explicit ignore.

## Migration notes

After this PR:
- New canonical idiom: `gif_loops = 0` (play through `hold_time`).
- Old idiom: `gif_loops = 999` (or similar magic large number). Still works; just becomes obvious as a workaround now that 0 exists.
- Docs/tutorials get updated; old user configs continue to render identically.

This PR delivers a clean answer to "how do I show this gif for the section's duration?" — the question that previously had no good answer.
