# draw_text_run consolidation + message fisheye colorization — Implementation Plan

**Goal:** Add `hires_downscale` to `draw_text_run`, route the three inline three-branch copies (image single-row, image two-row, message fisheye lens) through it, and colorize message-fisheye tokens (closes follow-up #2). Spec: `docs/superpowers/specs/2026-07-17-textrun-dedup-fisheye-design.md`.

**Branch:** `textrun-dedup-fisheye` (worktree `/Users/james/projects/github/jamesawesome/led-ticker-textrun-dedup`). No `from __future__ import annotations`. Test: `uv run --extra dev pytest <path> -q`; lint `ruff check src/ tests/`; `pyright src/led_ticker/widgets/`.

## Task 1: `draw_text_run` gains `hires_downscale`

- Add `hires_downscale: float = 1.0` (keyword-only) to `draw_text_run` (`widgets/_text_run.py`); forward it to `draw_with_emoji` in the EMOJI branch only (plain branches unchanged).
- Test (`tests/test_widgets/test_text_run.py`): emoji-branch call forwards `hires_downscale=0.5` to `draw_with_emoji` (spy/patch `_text_run.draw_with_emoji`, assert kwarg); a plain-text branch call with `hires_downscale=0.5` still renders (ignored, no crash). TDD: write failing first.
- Run `test_text_run.py` + `test_message.py` (message still green — default 1.0 no-op). Commit.

## Task 2: Route image single-row `_draw_text` through the helper

- Replace `_image_base._draw_text`'s ~3-branch body with one `draw_text_run(...)` call: `override` (its existing `self._text_segments` build, RAW `self._has_emoji()` basis), `has_emoji=self._has_emoji()`, `total_chars=count_text_chars(full_display)`, `hires_downscale=hires_downscale`, plus `x, baseline_y, provider=color, visible_text=text, frame`. Keep the override list→callable wrap OR pass the list — match `draw_text_run`'s `override` param type (it takes a `list | None`, wrapping internally; verify and pass the list, not a pre-wrapped callable).
- Equivalence guard: `test_image_base.py` stays fully green (byte-identical). Commit.

## Task 3: Route image two-row `_draw_row_text` through the helper

- Replace `_draw_row_text`'s branch body with `draw_text_run(...)`: per-row `override`, `has_emoji = self._has_emoji() and has_renderable_emoji(text)` (COMPOUND), `emoji_y=emoji_y`, `max_emoji_height=max_emoji_height`, `total_chars=per_char_total`, `frame=frame_count`, `provider=color`, `visible_text=text` (NO hires_downscale — two-row rows don't downscale, default 1.0).
- Equivalence guard: `test_image_base.py` green. Commit.

## Task 4: Route message `_paint_strip` lens through the helper + CLOSE #2

- Replace `message._paint_strip`'s 3 branches with `draw_text_run(...)`: build a token override from `self._resolved_segments` (mirror `message.draw`'s `build_token_color_override(segments, visible_text, self.frame_for("font_color"), self._has_emoji)` then wrap/pass), `has_emoji=self._has_emoji`, `total_chars=count_text_chars(full_text)`, `hires_downscale=hires_downscale`, `y_offset=y_offset`, `provider`, `visible_text`, `frame=self.frame_for("font_color")`, `x=x_logical`, `baseline_y=baseline`.
- **New mutation-grade test** (`tests/test_message_lens.py` or `test_message.py`): a `message` widget with a colored `:id:` token (constant source color, plain value "99") drawn under `flair.fisheye` (drive the lens path — see existing `test_message_lens.py` for how it invokes the lens). Assert PER-POSITION: every lit pixel in the token's x-span is the source color, every lit pixel in the literal's x-span is the host color. Mutation-check in the report: setting the lens override to `None` (or flipping the basis) makes it FAIL; restore → PASS.
- Run `test_message.py` + `test_message_lens.py`. Commit.

## Task 5: Docs, full suite, GIF gate, PR

- CLAUDE.md colored-tokens invariant: DELETE the two "Follow-ups (deferred)" bullets (hires_downscale passthrough + message lens); ADD one line: "two_row threads `color_override` into `draw_with_emoji` directly via `_row_override` (NOT through `draw_text_run`) — routing its `:667`/`:702` sites through the helper's `draw_text` fast path would break the ~20 tests patching `two_row.draw_with_emoji`; intentional exception." Also update "message fisheye ... does NOT" → now DOES colorize.
- Full suite `uv run --extra dev pytest -q` (all green); `ruff check src/ tests/` + `ruff format --check`; `pyright src/led_ticker/widgets/`.
- GIF gate: a message widget + colored `:id:` (static source, constant color) + `animation`/section under `flair.fisheye` on bigsign-flat geometry via `tools/render_demo`. Confirm the token colorizes through the lens. Attach.
- Push, `gh pr create` (body: de-dup + #2 closure, spec path, two_row exception noted, GIF result, byte-identical-image claim). CI green. Do NOT merge without go-ahead.
