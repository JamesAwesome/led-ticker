# Task 5 report — `message` (TickerMessage) integration + the resolution-freeze model

## Status: COMPLETE

## The freeze mechanism, as built

Two freeze surfaces, both keyed off a new `_resolution_locked` flag on
`FrameAwareBase`, plus a widget-local typewriter lock:

1. **`FrameAwareBase._resolution_locked`** (`widgets/_frame_aware.py`) — new
   `init=False, default=False` field, parallel to `_frame_paused`. `pause_frame()`
   now sets BOTH `_frame_paused = True` and `_resolution_locked = True`;
   `resume_frame()` clears both. Rides the existing `run_transition` /
   `_scroll_between` pause/resume seam with **no new call sites** — closes the C1
   (transition compositing) hole.

2. **Engine scroll lock** (`ticker.py`, `_swap_and_scroll`) — the scroll-overflow
   branch sets `_resolution_locked = True` for the scroll loop and clears it in a
   `finally`. Two new duck-typed static helpers next to
   `_advance_frame_if_supported`:
   - `_resolve_now_if_supported(widget)` → `widget.resolve_tokens_now()`. Called
     ONCE before the initial draw so the `cursor_pos` that decides hold-vs-scroll
     and feeds `stop_pos` measures the CURRENT value.
   - `_lock_resolution_if_supported(widget, locked)` → sets the flag if present.
     Wraps ONLY the scroll loop; the pre/post holds stay unlocked so a held
     redraw still re-resolves + re-centers (live-clock-during-hold).

3. **TickerMessage typewriter lock** (`message.py`, `_anim_resolution_lock`) —
   when `animation` is set and the field has tokens, the widget resolves once at
   reveal start and locks for the whole reveal (stable slice length + stable
   per-char hue anchor). Cleared on visit reset via a `reset_frame` override.

### TickerMessage wiring
- `__attrs_post_init__` builds `self._token = TokenizedField(self.text)`, seeds
  `_resolved_text = self.text`. `_has_emoji` stays on RAW text.
- `_resolve_into_full_text()` returns `self.text` verbatim for a non-token field
  (byte-identical to today); otherwise resolves against `get_data_registry()`
  unless frozen (`_resolution_locked` OR `_anim_resolution_lock`); on `changed`
  sets `_content_width = -1`.
- `draw` uses `full_text` everywhere `self.text` fed measurement/rendering,
  INCLUDING both hue anchors — `count_text_chars(full_text)` (emoji path) and
  `len(full_text)` (per-char path) = the I3 fix.
- `resolve_tokens_now()` forces resolve + `_content_width = -1`.

## Tripwires + results (all TDD)

`tests/test_widgets/test_message.py::TestTickerMessageInlineTokens`:
- non_token_byte_identical, substitutes_token_on_draw, unknown→literal,
  rewidths_when_held, unchanged_keeps_cached_width,
  **pause_frame_locks_resolution (C1)**, per_char_color_flows,
  **typewriter_token_slice_stable_mid_reveal (I3)**, resolve_tokens_now — all PASS.

`tests/test_ticker_display.py::TestSwapAndScrollTokenFreeze`:
- **scroll_freeze_value_change_does_not_change_stop_pos (C2)** — value ballooned
  10× on the first scroll swap does NOT move `stop_pos` (stays at entry width) —
  PASS.
- scroll_branch_locks_and_releases_resolution — lock set during loop, released
  in finally — PASS.

## Gate results
- Full suite: `PYTHONPATH=tests/stubs uv run --extra dev pytest` →
  **3126 passed, 2 skipped** (~62s). Pre-existing ticker/message/redraw-contract
  (AST scan, constraint #12) tests stay green — the new scroll-loop try/finally
  didn't break the per-tick advance_frame contract.
- ruff `check src/ tests/` → All checks passed.
- pyright `src/` → 0 errors, 0 warnings.

## Deviations
- The brief's C2 example `expected = -(cursor_pos - width)` omits widget padding;
  the real engine formula (constraint #7) adds `padding`. Test asserts against
  `+ widget.padding`. The freeze proof (entry width, not the ballooned value) is
  unchanged.
- C1 is the unit test on `pause_frame()` (brief: "A unit test on TickerMessage
  suffices"). `run_transition` reaches the same lock through the existing
  pause/resume seam (no new code) — no separate run_transition test added.

## Concerns / notes for Tasks 6/7
- `_resolution_locked` + the pause/resume extension live on `FrameAwareBase`, so
  two_row / image inherit the transition freeze for free; they still need their
  own scroll-branch handling (different scroll paths), `resolve_tokens_now()`,
  per-field `TokenizedField` wiring, and width-cache invalidation (`_bottom_width`
  for two_row, the overlay cache for image).
- The engine helpers are duck-typed and reusable as-is by two_row / image.
- Typewriter lock clears on `reset_frame` (visit entry), not on a completion
  hook — correct because a reveal is contained within one visit.
