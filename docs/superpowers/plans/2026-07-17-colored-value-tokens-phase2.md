# Colored Value Tokens Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend colored value tokens (a `:id:` token renders in its source-declared `color` while literal text keeps the field's color) from `TickerMessage` (Phase 1) to `TwoRowMessage` and the `_BaseImageWidget` image/gif text overlay. Spec: `docs/superpowers/specs/2026-07-17-colored-value-tokens-phase2-design.md`.

**Architecture:** Extract Phase 1's override builder to `sources.py`; add a single shared three-branch "draw a text run with an optional per-char override" helper and route `message.py` (equivalence guard), the two `TwoRowMessage` default draws + its wrap helper, and both image overlay paths through it. Per-field FROZEN segment snapshots (built only when the field has tokens) feed the builder; each draw site passes the `has_emoji` basis that matches its own emoji branch.

**Tech Stack:** Python 3.14, pytest, attrs. Working copy: `/Users/james/projects/github/jamesawesome/led-ticker-colored-tokens-p2`, branch `colored-tokens-phase2` (spec committed there). Run `git branch --show-current` first; abort if not `colored-tokens-phase2`.

## Global Constraints

- **The `has_emoji`-basis rule is THE correctness constraint.** The `has_emoji` arg to `build_token_color_override` MUST equal the predicate the draw site uses to pick its emoji branch (spec §"Phase 1 pattern" table). Getting it wrong reproduces the M1/M2 misalignment bug. Per site: message → `self._has_emoji` (raw); two_row top/bottom/wrap → `has_renderable_emoji(<resolved row text>)`; image single-row `_draw_text` → `self._has_emoji()` (raw); image two-row `_draw_row_text` → `self._has_emoji() and has_renderable_emoji(text)` (compound).
- **Byte-identical when no source declares a color.** A segment snapshot is built ONLY when the field's `TokenizedField.has_tokens` is true; otherwise it stays `None`, the builder returns `None`, and the draw path is unchanged. No per-tick allocation for non-token fields.
- **No fast-path gate change** (spec §4): two_row has no static fast path; image already forces per-tick via `_has_overlay_tokens()`. Do NOT add or narrow a gate.
- Core imports only within core; no new cross-module cycles (`sources.py` must not import a widget). No `from __future__ import annotations`. PEP-758 bare `except` is the project convention.
- Test command: `uv run --extra dev pytest <path> -q` from the working-copy root. Full suite before PR. Lint: `uv run --extra dev ruff check src/ tests/`. Format: `uv run --extra dev ruff format src/ tests/`.

---

### Task 1: Move the override builder to `sources.py`

**Files:**
- Modify: `src/led_ticker/sources.py` (add `build_token_color_override`)
- Modify: `src/led_ticker/widgets/message.py` (import it; delete the private copy)
- Test: `tests/test_sources.py` (add) + the existing message colored-token tests are the equivalence guard.

**Interfaces:**
- Produces: `sources.build_token_color_override(segments, visible_text, frame: int, has_emoji: bool) -> list | None` — identical body/signature to the current `message._build_token_color_override` (message.py:41), only relocated and de-underscored. Tasks 2–5 import it.

- [ ] **Step 1: Write the failing test** in `tests/test_sources.py`:

```python
def test_build_token_color_override_is_public_in_sources():
    from led_ticker.sources import build_token_color_override

    # all-literal segments (no color) -> None
    segs = [("hello", None, False)]
    assert build_token_color_override(segs, "hello", 0, has_emoji=False) is None
```

- [ ] **Step 2: Run to verify failure** — `uv run --extra dev pytest tests/test_sources.py -q -k build_token_color_override` → FAIL (import error).

- [ ] **Step 3: Move the function.** Cut the entire `_build_token_color_override` body from `message.py`, paste into `sources.py` (near `TokenizedField`) renamed `build_token_color_override` (no leading underscore), signature and body UNCHANGED. In `message.py`, add `from led_ticker.sources import build_token_color_override` (or extend the existing sources import) and replace the internal call `_build_token_color_override(...)` with `build_token_color_override(...)`. Confirm no import cycle: `sources.py` must not import `message`/`two_row`/`_image_base`; the builder duck-types `color.color_for`, so no color-provider class import is needed.

- [ ] **Step 4: Run the guard** — `uv run --extra dev pytest tests/test_sources.py -q -k build_token_color_override` (new test passes) AND the full message suite: `uv run --extra dev pytest tests/test_widgets/test_message.py -q` (all pre-existing colored-token tests still green — the equivalence proof). Then `ruff check src/`.

- [ ] **Step 5: Commit** — `git add src/led_ticker/sources.py src/led_ticker/widgets/message.py tests/test_sources.py && git commit -m "refactor(core): move build_token_color_override to sources.py (shared for Phase 2)"`

---

### Task 2: Shared three-branch row-draw helper; adopt in `message.py`

**Files:**
- Modify: `src/led_ticker/pixel_emoji.py` OR a new `src/led_ticker/widgets/_text_run.py` (implementer picks; `_text_run.py` keeps `pixel_emoji` lean — prefer it unless a cycle forces otherwise)
- Modify: `src/led_ticker/widgets/message.py` (route its three branches through the helper)
- Test: `tests/test_widgets/test_text_run.py` (add) + message suite as the equivalence guard.

**Interfaces:**
- Produces:
  ```python
  def draw_text_run(canvas, font, x, baseline_y, provider, visible_text, frame, *,
                    override=None, has_emoji, total_chars=None, y_offset=0,
                    emoji_y=None, max_emoji_height=None) -> int
  ```
  Returns the advance (cursor delta). Implements the exact Phase 1 three-branch dispatch: (a) `has_emoji` → `draw_with_emoji(..., color_override=callable)`; (b) provider `.per_char` and not `has_emoji` → `draw_text_per_char` with an override-aware callback; (c) else → forced per-char via `draw_text_per_char` when `override` is not None, plain `draw_text` otherwise. `emoji_y`/`max_emoji_height` forwarded to `draw_with_emoji` only when provided (two_row/image supply them; message does not). `total_chars` defaults to `count_text_chars(visible_text)` for the emoji branch and `len(visible_text)` for per-char when None.

- [ ] **Step 1: Write failing tests** covering all three branches with and without an override, e.g. a constant provider + override colors only the override chars; a per_char provider + override; an emoji-containing text + override skips the sprite in the char space. (Model assertions on the stub canvas as `test_message.py` does; pull the exact expected-color helper from there.)

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `draw_text_run`** by lifting message.py's three inline branches (message.py:489–598) verbatim into the helper, parameterizing `emoji_y`/`max_emoji_height`/`total_chars`/`y_offset`. Then in `message.draw`, REPLACE the three inline branches with a single `cursor_pos += draw_text_run(draw_canvas, self.font, cursor_pos, baseline_y, provider, visible_text, self.frame_for("font_color"), override=token_override, has_emoji=self._has_emoji, total_chars=count_text_chars(full_text), y_offset=y_offset)`. (message's per-char branch uses `total_chars=len(full_text)`; the emoji branch uses `count_text_chars(full_text)` — preserve the distinction: pass `total_chars` explicitly and let the helper NOT recompute when given.)

- [ ] **Step 4: Run the guard** — new helper tests pass AND `uv run --extra dev pytest tests/test_widgets/test_message.py -q` all green (proves the extraction is behavior-preserving on the shipped widget). `ruff check src/`.

- [ ] **Step 5: Commit** — `git commit -m "refactor(core): shared draw_text_run three-branch helper; message adopts it"`

---

### Task 3: `TwoRowMessage` — snapshots + all three draw sites

**Files:**
- Modify: `src/led_ticker/widgets/two_row.py`
- Test: `tests/test_widgets/test_two_row.py` (add colored-token cases)

**Interfaces:**
- Consumes: `sources.build_token_color_override`, `draw_text_run` (Task 2).

- [ ] **Step 1: Write failing tests** — on a DEFAULT-mode widget (`bottom_text_wrap=False`, so sites `:667`/`:702` run): a `:id:` token with a constant `color` in `top_text` renders that color while the literal label keeps `top_color`; same for `bottom_text`/`bottom_color`. Plus: wrap-mode (`bottom_text_wrap=True`) row; a token VALUE that resolves to `":sun: 72"` colors correctly (the has_emoji-basis test); no-color token field is byte-identical (golden pixel compare vs a pre-change render); bottom-row marquee scroll keeps the token colored. Use the test file's existing stub-canvas + registry-stub fixtures.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement.**
  - Add `_top_segments` / `_bottom_segments` attrs (`init=False, default=None`).
  - In `_resolve_tokens`: where `_resolved_top` is set, also set `_top_segments = self._top_token.resolve_segments(reg)` — but ONLY when `self._top_token.has_tokens`; else leave `None`. For the bottom row, set `_bottom_segments` INSIDE the existing `if changed:` block (two_row.py:331) alongside `_resolved_bottom`, so text and segments can't drift. Mirror in `resolve_tokens_now`.
  - Replace the top-row `draw_with_emoji(...)` at `:667` with:
    ```python
    top_override = build_token_color_override(
        self._top_segments, self._resolved_top, self.frame_for("top_color"),
        has_renderable_emoji(self._resolved_top),
    ) if self._top_segments else None
    draw_text_run(
        canvas, top_font, top_x, top_text_y, self.top_color, self._resolved_top,
        self.frame_for("top_color"), override=top_override,
        has_emoji=has_renderable_emoji(self._resolved_top),
        emoji_y=top_emoji_y, max_emoji_height=top_emoji_cap,
    )
    ```
  - Replace the bottom-row `draw_with_emoji(...)` at `:702` with the analogous `draw_text_run` call using `_bottom_segments` / `self._resolved_bottom` / `bottom_color` / `bottom_x` / `bottom_emoji_y` / `bottom_emoji_cap`.
  - Route `_draw_row_text_at`'s existing branches through `draw_text_run` too (or leave it and just add the override — but prefer the helper so all three sites share one dispatch). Its `has_emoji` basis is `has_renderable_emoji(text)` (already what it uses).
  - Confirm `draw_text_run`'s return value is discarded here (two_row's direct draws don't accumulate a cursor — they draw at a computed x); verify the helper's side effects match the old direct `draw_with_emoji` (it must, since branch (a) IS `draw_with_emoji`).

- [ ] **Step 4: Run** the two_row suite to green + `ruff check`.
- [ ] **Step 5: Commit** — `git commit -m "feat(two_row): colored value tokens on both rows (default + wrap)"`

---

### Task 4: Image single-row overlay (`_draw_text`)

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py`
- Test: `tests/test_widgets/test_image_base.py` (add cases)

- [ ] **Step 1: Write failing tests** — a gif/image with `text = "AAPL :id:"` + a constant token color: the token colors, "AAPL" keeps `font_color`. Plus: typewriter mid-reveal colors the token correctly; scroll mode keeps it colored; **fisheye on an image widget** colors the token (the lens shares `_draw_text` — spec I3); a token VALUE `":sun: 72"` aligns (raw has_emoji basis); no-color field byte-identical.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement.**
  - Add `_text_segments` attr; set it (only when `_token_text.has_tokens`) at the same resolve call that sets `_resolved_text_single` (in `_resolve_overlay_text` / its frozen sibling).
  - In `_draw_text` (`:988`): build `override = build_token_color_override(self._text_segments, text, self.frame_for("font_color"), self._has_emoji()) if self._text_segments else None` — **`has_emoji=self._has_emoji()` (RAW cache), matching the branch predicate at `:1028`**. `text` is the actual drawn string (`text_override` prefix or `full_display`). Route the existing branches through `draw_text_run` with `total_chars=count_text_chars(full_display)` (preserve the I3 full-length anchor) and `override=override`.

- [ ] **Step 4: Run** the image suite + `ruff check`.
- [ ] **Step 5: Commit** — `git commit -m "feat(image): colored value tokens on single-row text overlay"`

---

### Task 5: Image two-row overlay (`_draw_row_text` + tuple plumbing)

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py`
- Test: `tests/test_widgets/test_image_base.py` (add two-row cases)

**Interfaces:**
- The row tuple built by `_render_two_row_tick` (`:1428`), `_render_two_row_wrap_tick` (`:1474`), and the two-row fast-path builders (`:1983`, `:2057`) gains a per-row override (or a per-row segment snapshot the composer converts). `_draw_row_text` (`:1090`) gains an `override=None` param.

- [ ] **Step 1: Write failing tests** — a two-row image overlay (`bottom_text != ""`) with a colored token in `top_text` and in `bottom_text`; each colors while its row's `top_color`/`bottom_color` holds for literals. Plus: token VALUE `":sun: 72"` aligns under the COMPOUND has_emoji basis; no-color byte-identical; the two-row FAST path (static image) still renders the token colored AND still bypasses paint-once (I2 — `_has_overlay_tokens()` unchanged).

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement.**
  - Add `_top_segments` / `_bottom_segments` (distinct from the single-row `_text_segments`); resolve them (gated on the row token's `has_tokens`) in `_play_with_two_row_text`'s per-row resolve alongside `_resolved_top_text` / `_resolved_bottom_text`.
  - Widen `_draw_row_text`'s signature with `override=None`; inside, route through `draw_text_run` with `has_emoji = self._has_emoji() and has_renderable_emoji(text)` (the COMPOUND predicate at `:1118`) and `override=override`.
  - In each composer (`_render_two_row_tick`, `_render_two_row_wrap_tick`) and BOTH fast-path tuple builders (`:1983`, `:2057`): build the per-row override from that row's segment snapshot + resolved text + row provider + the compound has_emoji, and pass it to `_draw_row_text`. Widen the row tuple if the composer stores tuples before drawing (implementer: inspect whether the override can be computed at draw time from `self._<row>_segments` instead of threading through the tuple — computing it in `_draw_row_text` from a row-id arg is simpler than widening 4 build sites; choose the lower-churn option and note the choice in the report).

- [ ] **Step 4: Run** the image suite to green + `ruff check` + `uv run --extra dev pyright src/led_ticker/widgets/_image_base.py`.
- [ ] **Step 5: Commit** — `git commit -m "feat(image): colored value tokens on two-row text overlay"`

---

### Task 6: Full suite, GIF gate, docs, PR

- [ ] **Step 1: Full suite** — `uv run --extra dev pytest -q` from root. Expected: all pass (Phase 1 message tests + new Phase 2 tests). Then `ruff check src/ tests/` + `ruff format --check src/ tests/`.
- [ ] **Step 2: GIF gate** (render-path change — mandatory). Render throwaway bigsign-flat TOMLs via `tools/render_demo/render.py`: (a) a `two_row` with a colored `:clock.now:`-style token on the bottom row + a differently-colored label; (b) an `image`/`gif` with a colored-token caption (single-row); (c) a two-row image overlay with a colored token. Use a `[[source]]` with a constant `color` (or a `clock`/`static` source) so no network is needed. Confirm mixed colors read; attach GIFs to the session.
- [ ] **Step 3: Docs** — if `two_row` / image docs pages or `CLAUDE.md` state a colored-token limitation ("message only"), update to "message, two_row, image overlay." Check `docs/DOCS-STYLE.md` compliance if touching docs-site pages.
- [ ] **Step 4: Push + PR** — `git push -u origin colored-tokens-phase2`; `gh pr create` (body via file): what (Phase 2 surfaces), spec path, the antagonist-review-hardened design notes (all five draw sites + per-site has_emoji basis), GIF-gate results, and that no config surface is added. Watch CI green. Do NOT merge without user go-ahead.

---

## After merge (separate, not tasks here)

- Core release vNext (minor) via `cut_release.py`.
- Small **led-ticker-plugins** PR: add a `two_row` + image colored-token line to the stocks smoke configs (mirrors Phase 1 PR #49) for hardware validation; floor those configs to the core release.
- Board: mark Phase 2 shipped in [[project_colored_value_tokens]] + [[project_task_board]].
