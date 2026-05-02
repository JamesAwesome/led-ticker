# GIF widget — pre-merge review plan

**Goal:** Catch optimization, correctness, test, documentation, and DRY issues
before the gif-widget branch merges into `main`.

**Branch state (gif-widget @ d1573ad, 30 commits ahead of main):**

- ~680 lines new production code
  - `src/led_ticker/widgets/gif.py` (329) — GifPlayer + play loops + text overlay
  - `src/led_ticker/widgets/_gif_decode.py` (132) — Pillow decode + fit modes
  - `src/led_ticker/ticker.py` (+155) — `run_gif`, `_run_gif`, `_play_widget`,
    `_show_one`, `_has_play`
  - `src/led_ticker/app.py` (+38) — gif-relative path resolution, text→message
    rename guard
  - `src/led_ticker/transitions/effects.py` (+27) — Dissolve physical-grain fix
- ~1230 lines tests
- 2 new example configs, 4 GIF assets, 1 design doc, 1 implementation plan

**Headline features delivered (some beyond the original plan):**

1. `GifPlayer` widget with `mode = "gif"` orchestration (`Ticker.run_gif`)
2. Pillow-based decode with 4 fit modes (`pillarbox`, `letterbox`, `stretch`,
   `crop`)
3. Config-relative path resolution
4. Transparent GIF support (alpha-aware decode → composite onto black)
5. `gif_align` (left/center/right) for pillarbox horizontal anchoring
6. Text alongside the GIF: `text_align = "left" | "right" | "scroll" |
   "scroll_over"`
7. Inline `:slug:` emoji in GIF text
8. `text_scale` for chunky glyphs on the bigsign
9. `text_loops` floor: section won't transition until marquee has crossed N
   times
10. `mode = "swap"` merge — GIF works like a normal widget with optional title
11. Dissolve transition fixed to scatter at physical pixel resolution (was
    fade-through-black on bigsign)
12. Several follow-up bug fixes (text-pulsing, text/message rename collision,
    start_pos plumbing, monitor enqueue)

## Review areas

Each area is dispatched to a separate reviewer subagent so they don't pollute
each other's context. Each reviewer must produce a punch list under 500 words
with **severity** (blocker / important / nice-to-have), **file:line**,
**finding**, and **suggested fix**.

### Area 1 — Hot-path performance

**Files:** `src/led_ticker/widgets/gif.py` (focus on `_paint_full`,
`_paint_skip_black`, `_play_with_text`), `src/led_ticker/widgets/_gif_decode.py`,
`src/led_ticker/transitions/effects.py` (Dissolve at physical res).

**Key questions:**

- `_paint_full` and `_paint_skip_black` are pure Python triple-nested loops
  iterating 256×64 = 16,384 pixels per frame. At 20fps that's 327k SetPixel
  calls/sec. Are there safe wins (struct, `memoryview`, batched writes,
  numpy)? Is the inner-loop attribute hoist actually taken?
- The dissolve scatter at physical res is 16× more SetPixel calls than the
  old logical version. Pre-shuffle is cached but the per-frame loop is still
  16,384 iterations at peak. Acceptable? Could the shuffle be precomputed
  once at first run (it already is) and is the hot loop tight enough?
- `_frame_for_elapsed` walks a list every tick — fine for 6-frame GIFs, but
  call frequency is one per text-tick (50 ms). Acceptable?
- Per-tick allocation: `pixels, _ = self._frames[frame_idx]` returns a tuple
  each tick — Python should hoist, but worth a sanity check.

### Area 2 — DRY / refactoring opportunities

**Files:** `src/led_ticker/widgets/gif.py`, `src/led_ticker/widgets/_gif_decode.py`,
`src/led_ticker/ticker.py`.

**Key questions:**

- `_play_no_text` and `_play_with_text` share clearing + frame-pick + swap
  scaffolding. Could collapse into one path with a per-mode "compose tick"
  callback?
- `_apply_fit` has near-identical end-step (paste onto black canvas with
  alpha mask) for pillarbox/letterbox/crop/stretch. The new
  `_flatten_onto_black` helper exists — is every call site using it?
- `_VALID_*` frozensets repeat the validation pattern 3× (text_align,
  gif_align, fit, h_align). Could a tiny `_validate_choice(name, val, allowed)`
  helper de-duplicate?
- Is `_has_play()` in ticker.py the right home, or should it live alongside
  `Widget` protocol definitions?
- Static text positioning in `_play_with_text` re-computes `text_x_left` /
  `text_x_right` once before the loop — but the same logic for
  `text_x_right` clamping (`max(2, …)`) appears once. Any other clamps that
  should match?

### Area 3 — Test effectiveness

**Files:** `tests/test_widgets/test_gif.py`, `tests/test_widgets/test_gif_decode.py`,
`tests/test_run_gif.py`, `tests/test_gif_path_resolution.py`,
plus additions to `tests/test_ticker_display.py` and `tests/test_transitions.py`.

**Key questions:**

- Adversarial: pick 3 plausible regressions that would NOT be caught by the
  current test suite (e.g., off-by-one in scroll wrap, wrong frame index
  after a partial gif play, missed font_color override). What tests are
  missing?
- Are there over-specified tests (asserting behavior that's not the public
  contract — e.g., exact SetPixel call counts) that would falsely fail on
  benign refactors?
- Mock-vs-integration balance — are tests using mocks where real stubs would
  catch more? (`test_text_loops_extends_section_duration` asserts
  `>= 524 SwapOnVSync` calls; what's the actual minimum?)
- Are there flaky-prone tests (timing-dependent, RNG-dependent)?
- Branch coverage gaps for `_apply_fit` (each fit × each h_align combination)?

### Area 4 — Documentation

**Files:** `src/led_ticker/widgets/gif.py` docstrings, `_gif_decode.py`
docstrings, `CLAUDE.md`, `config/config.gif_test.example.toml`,
`config/config.gif_text.example.toml`,
`docs/superpowers/specs/2026-05-01-gif-widget-design.md`,
`docs/superpowers/plans/2026-05-01-gif-widget.md`.

**Key questions:**

- Module / class / method docstrings — are they accurate after the iteration
  cycles, or do any reference removed behavior?
- Should `CLAUDE.md` get a new "GIF widget" section under
  `## Architecture`? Specifically:
  - The "paint native pixels, bypass ScaledCanvas" pattern
  - The play() dispatch in run_swap
  - Transparent-decode-onto-black design choice
- Are config example comments truthful about what each section demos? Did
  any drift after the fit-mode tweaks?
- Is the spec doc still accurate, or did the implementation drift? (Honest
  review: lots was added beyond spec — are those follow-ups documented
  anywhere durable?)
- Is the original implementation plan worth keeping, or should we drop it
  now that it's complete?

### Area 5 — API surface / naming consistency

**Files:** `src/led_ticker/widgets/gif.py`, `src/led_ticker/widgets/_gif_decode.py`.

**Key questions:**

- Naming: `gif_align` on the widget vs `h_align` on `decode_gif`. Both refer
  to the same thing — should they unify?
- `loops` (gif loops per visit) vs `text_loops` (marquee loops floor). Clear,
  or confusing alongside `loop_count` (section)?
- `text_scale` vs the section-level `scale` — does the user understand which
  to use when?
- Are defaults sensible? (`text_align = "right"` as a default when text is
  empty — does this cause surprise validation errors anywhere?)
- Footguns: e.g., `text_align = "scroll"` with `gif_align = "stretch"` —
  does anything go wrong? Pillarbox + black gif (no transparency) + scroll
  text — is the result sensible or confusing?
- Validation gaps: e.g., is `text_scale = -1` rejected? `loops = -5`?

### Area 6 — Holistic review against the original spec

**Tool:** `superpowers:code-reviewer` agent.

**Inputs:**

- Original design: `docs/superpowers/specs/2026-05-01-gif-widget-design.md`
- Original plan: `docs/superpowers/plans/2026-05-01-gif-widget.md`
- Branch state @ d1573ad

**Key questions:**

- Are the original 7 plan tasks fully met? (Should be yes — that was the
  initial implementation phase.)
- Of the features added beyond the plan, are any fundamentally at odds with
  the original design intent?
- Architectural concerns: is the GIF widget integrated cleanly with the
  rest of the ticker, or does it have weird coupling?
- Is any of the new surface area NOT exercised by tests?

## Process

1. Dispatch all 6 reviewers in parallel (one tool call, six `Agent` blocks).
2. Wait for all to return their punch lists.
3. Aggregate findings into
   `docs/superpowers/plans/2026-05-01-gif-widget-review-findings.md` —
   ordered by severity, deduplicated, with my own commentary on which
   findings to action before merge vs defer.
4. Discuss with the user — they decide which to fix here vs after merge vs
   never.

## Success criteria

- Every reviewer returns a non-empty punch list (six perspectives is a lot;
  someone will find SOMETHING).
- No reviewer's findings overlap by more than ~30% with another's (proves
  the slicing was effective at avoiding redundant work).
- Aggregated findings are short enough to review in one sitting (<2 pages).
