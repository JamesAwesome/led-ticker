# row_layout hi-res emoji centering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `row_layout` emoji centering so hi-res sprites in two-row widgets sit correctly within their band without requiring a manual `top_emoji_y_offset` workaround.

**Architecture:** Add an optional `sprite_logical_height` parameter to `row_layout` (defaults to `EMOJI_ROW_CAP = 8` for back-compat). Widget callers (`TwoRowMessage`, `_BaseImageWidget` two-row mode) pass the row's `emoji_cap` — which they already compute as `max(EMOJI_ROW_CAP, band_h)` — so the formula `(band_height - sprite_logical_height) // 2 + band_offset` centers the actual sprite size rather than always centering an 8-row sub-band. After the fix, the manual `top_emoji_y_offset = -4` on `docs/site/demos-pinned/two_row-hires-emoji.toml` and the explanatory paragraph on `widgets/two_row.mdx` come out.

**Tech Stack:** Python 3.13, attrs, pytest. No new dependencies.

**Background:** Discovered during PR #42 docs polish. The `:instagram:` sprite (32 real px = 16 logical at scale=2) in a 16-row top band was rendering at logical y=4 (centered for an 8-row sprite), extending to y=20 — bleeding 4 rows into the bottom band. The shipped workaround pulls the sprite up with `top_emoji_y_offset = -4`. The root cause and fix plan are recorded in memory `project_row_layout_hires_emoji_centering.md`.

---

## File structure

| File | Action | Purpose |
|------|--------|---------|
| `src/led_ticker/widgets/_row_layout.py` | Modify | Add `sprite_logical_height` parameter to `row_layout`; update centering formula. |
| `src/led_ticker/widgets/two_row.py` | Modify | Pass `top_emoji_cap` / `bottom_emoji_cap` to the two `_row_layout` calls. |
| `src/led_ticker/widgets/_image_base.py` | Modify | Same change for the two-row text-overlay path on image widgets. |
| `tests/test_widgets/test_row_layout.py` | Create | New test module for `row_layout` directly (focused unit coverage; existing tests in `test_two_row.py` cover the function indirectly). |
| `tests/test_widgets/test_two_row.py` | Modify | Add tripwire test: hi-res emoji in a band-sized for it anchors at the band top (regression for the original bug). |
| `tests/test_widgets/test_image_base.py` | Modify | Mirror tripwire for the image two-row path. |
| `docs/site/demos-pinned/two_row-hires-emoji.toml` | Modify | Remove `top_emoji_y_offset = -4` and the inline math comment. |
| `docs/site/public/demos-pinned/two_row-hires-emoji.gif` | Re-render | Verify visual matches the prior post-workaround gif. |
| `docs/site/src/content/docs/widgets/two_row.mdx` | Modify | Drop the "default placement centers an 8-row low-res sprite" paragraph; replace with one line stating the band fits the sprite. Remove the offset from the TOML example. |
| `CLAUDE.md` | Modify | Update the "Two-row widget" invariants to mention `row_layout`'s `sprite_logical_height` parameter so future contributors don't reintroduce the manual-offset workaround. |

---

## Task 1: Add `sprite_logical_height` parameter to `row_layout`

**Files:**
- Create: `tests/test_widgets/test_row_layout.py`
- Modify: `src/led_ticker/widgets/_row_layout.py:31-63`

- [ ] **Step 1: Write the failing test**

Create `tests/test_widgets/test_row_layout.py`:

```python
"""Unit tests for `row_layout` centering math.

These tests exercise the function directly, bypassing the widget
wrappers. Widget-level integration tests live in test_two_row.py
and test_image_base.py.
"""

from types import SimpleNamespace

import pytest

from led_ticker.fonts import FONT_SMALL
from led_ticker.widgets._row_layout import EMOJI_ROW_CAP, row_layout


class TestRowLayoutSpriteHeight:
    """`sprite_logical_height` parameter centers the actual sprite,
    not the EMOJI_ROW_CAP-tall low-res default."""

    def test_default_sprite_height_preserves_legacy_centering(self):
        """Callers that don't pass `sprite_logical_height` get the
        old EMOJI_ROW_CAP-based centering — back-compat for any
        external caller of row_layout."""
        canvas = SimpleNamespace(height=16, scale=2, width=128)
        # 16-row band, default sprite_logical_height = 8:
        # emoji_y = (16 - 8) // 2 + 0 = 4 (old buggy default)
        _, emoji_y = row_layout(canvas, FONT_SMALL, band_height=16, band_offset=0)
        assert emoji_y == 4

    def test_full_band_sprite_anchors_at_band_top(self):
        """Sprite exactly fills the band — emoji_y should be 0
        (or band_offset for non-zero offsets).

        This is the original `:instagram:` + top_row_height=16 case
        that produced the bleed into the bottom band."""
        canvas = SimpleNamespace(height=16, scale=2, width=128)
        _, emoji_y = row_layout(
            canvas, FONT_SMALL,
            band_height=16, band_offset=0,
            sprite_logical_height=16,
        )
        # (16 - 16) // 2 + 0 = 0
        assert emoji_y == 0

    def test_sprite_smaller_than_band_centers(self):
        """8-row sprite in a 16-row band — centered at row 4."""
        canvas = SimpleNamespace(height=16, scale=2, width=128)
        _, emoji_y = row_layout(
            canvas, FONT_SMALL,
            band_height=16, band_offset=0,
            sprite_logical_height=8,
        )
        # (16 - 8) // 2 + 0 = 4
        assert emoji_y == 4

    def test_sprite_taller_than_band_clamps_to_band_top(self):
        """Sprite logically taller than its band — formula would
        return negative emoji_y; clamp to band_offset so the top
        edge of the sprite anchors at the top of the band (the
        bottom bleeds into the next band, which is the existing
        documented behavior for tiny bands)."""
        canvas = SimpleNamespace(height=16, scale=2, width=128)
        _, emoji_y = row_layout(
            canvas, FONT_SMALL,
            band_height=8, band_offset=0,
            sprite_logical_height=16,
        )
        # (8 - 16) // 2 + 0 = -4 → clamped to 0
        assert emoji_y == 0

    def test_non_zero_band_offset_threads_through(self):
        """Bottom-row band starts at band_offset > 0. The centering
        result is relative to band_offset, not to canvas y=0."""
        canvas = SimpleNamespace(height=24, scale=2, width=128)
        _, emoji_y = row_layout(
            canvas, FONT_SMALL,
            band_height=8, band_offset=16,
            sprite_logical_height=8,
        )
        # (8 - 8) // 2 + 16 = 16
        assert emoji_y == 16
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_widgets/test_row_layout.py -v`

Expected: FAIL — `row_layout` doesn't accept the `sprite_logical_height` kwarg. The first test (legacy default) passes; the other four fail with TypeError.

- [ ] **Step 3: Add the parameter**

Edit `src/led_ticker/widgets/_row_layout.py:31-63`. The function signature and docstring update; the formula swaps `EMOJI_ROW_CAP` for the parameter:

```python
def row_layout(
    canvas: Canvas,
    font: Any,
    band_height: int,
    band_offset: int,
    sprite_logical_height: int = EMOJI_ROW_CAP,
) -> tuple[int, int]:
    """Return (text_baseline_y, emoji_top_y) for one row's band.

    `band_height` is the number of logical rows allocated to this row;
    `band_offset` is the logical y of the band's top edge. With a
    50/50 split on a 16-row canvas these are (8, 0) for top and
    (8, 8) for bottom. With an asymmetric `top_row_height = 4`, top
    is (4, 0) and bottom is (12, 4).

    Delegates baseline math to `compute_baseline_for_band`; centers
    the emoji sprite on a `sprite_logical_height`-tall sub-band so
    sprites of any size coexist with any text size. Defaults to
    `EMOJI_ROW_CAP = 8` (the low-res sprite height) for back-compat
    with callers that don't know their actual sprite size.

    For small bands (`band_height < sprite_logical_height`), the
    centered formula would produce a negative `emoji_y` relative to
    the band — clipping the top of the sprite above the band edge.
    Clamp to `band_offset` so the emoji top is at least the band's
    top edge (the bottom may then bleed into the next band's space,
    which is benign as long as that space isn't occupied — typical
    asymmetric layouts have a small top tag where this bleed lands
    harmlessly before the bottom row's text baseline).
    """
    emoji_y = max(
        band_offset,
        (band_height - sprite_logical_height) // 2 + band_offset,
    )
    baseline = compute_baseline_for_band(
        font, band_height, safe_scale(canvas), valign="center"
    )
    text_baseline = baseline + band_offset
    return text_baseline, emoji_y
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_widgets/test_row_layout.py -v`

Expected: 5 passed.

Run: `uv run pytest tests/test_widgets/test_two_row.py -v`

Expected: all existing tests still pass (back-compat default preserves old behavior for callers that haven't been updated yet).

- [ ] **Step 5: Commit**

```bash
git add tests/test_widgets/test_row_layout.py src/led_ticker/widgets/_row_layout.py
git commit -m "row_layout: add sprite_logical_height parameter

Centers the actual sprite within the band instead of always
centering an 8-row sub-band. Defaults to EMOJI_ROW_CAP = 8 so
existing callers see no behavior change."
```

---

## Task 2: Thread per-row cap through `TwoRowMessage.draw`

**Files:**
- Modify: `src/led_ticker/widgets/two_row.py:208-213`
- Modify: `tests/test_widgets/test_two_row.py` (append tripwire)

- [ ] **Step 1: Write the failing tripwire test**

Add to `tests/test_widgets/test_two_row.py` (at the end of the existing `class TestRowLayout` block, around line 924):

```python
    def test_hires_sprite_anchors_within_full_band(self):
        """Original bug from PR #42: with top_row_height=16 at
        scale=2, the hi-res :instagram: sprite (16 logical tall)
        was placed at emoji_y=4 (centered for an 8-row sprite),
        extending to row 20 — bleeding into the bottom band.

        After the fix: row_layout receives the row's emoji_cap
        as `sprite_logical_height`, so the 16-row sprite anchors
        at emoji_y=0 within the 16-row band. No overlap.
        """
        from types import SimpleNamespace

        from led_ticker.widgets.two_row import _row_layout

        canvas = SimpleNamespace(height=24, scale=2, width=128)
        # Top band = 16 rows, cap = max(8, 16) = 16
        _, top_emoji_y = _row_layout(
            canvas, FONT_SMALL,
            band_height=16, band_offset=0,
            sprite_logical_height=16,
        )
        assert top_emoji_y == 0, (
            f"top_emoji_y={top_emoji_y}; expected 0 — a 16-row sprite "
            "in a 16-row band should anchor at the band's top edge so "
            "it doesn't bleed into the bottom band starting at row 16."
        )
```

- [ ] **Step 2: Run test to verify the new tripwire passes already** (since Task 1 already added the parameter)

Run: `uv run pytest tests/test_widgets/test_two_row.py::TestRowLayout::test_hires_sprite_anchors_within_full_band -v`

Expected: PASS.

- [ ] **Step 3: Update `TwoRowMessage.draw` to pass the cap**

Edit `src/led_ticker/widgets/two_row.py:208-213`. The two `_row_layout` calls need the new kwarg. Note that `top_emoji_cap` / `bottom_emoji_cap` are computed at line 232-233 — that block must move BEFORE the `_row_layout` calls so the caps are available:

```python
        # Cap each row's emoji height so a hi-res sprite doesn't overflow
        # into the other row. When the band is taller than the default
        # `_EMOJI_ROW_CAP`, raise the cap to match — a hi-res sprite that
        # fits the band visually is allowed to render at hi-res. Default
        # 50/50 split with content_height=16 produces band=8 = cap, so
        # existing demos behave identically; bumping content_height or
        # top_row_height enables hi-res emoji on the affected row.
        top_emoji_cap = max(_EMOJI_ROW_CAP, top_h)
        bottom_emoji_cap = max(_EMOJI_ROW_CAP, bottom_h)

        top_text_y, top_emoji_y = _row_layout(
            canvas, top_font,
            band_height=top_h, band_offset=0,
            sprite_logical_height=top_emoji_cap,
        )
        bottom_text_y, bottom_emoji_y = _row_layout(
            canvas, bottom_font,
            band_height=bottom_h, band_offset=top_h,
            sprite_logical_height=bottom_emoji_cap,
        )
```

Delete the duplicated `top_emoji_cap` / `bottom_emoji_cap` block at the original location (formerly line 232-233).

- [ ] **Step 4: Verify the tripwire still passes AND existing tests pass**

Run: `uv run pytest tests/test_widgets/test_two_row.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/two_row.py tests/test_widgets/test_two_row.py
git commit -m "two_row: thread per-row emoji_cap into row_layout

Hi-res sprite in a band sized for it now anchors at the band top
without a manual top_emoji_y_offset. Adds a tripwire that locks
in the 16-row sprite + 16-row band case."
```

---

## Task 3: Thread per-row cap through `_BaseImageWidget` two-row mode

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py` (the two-row text-overlay code path)
- Modify: `tests/test_widgets/test_image_base.py` (append tripwire)

- [ ] **Step 1: Locate the two-row text-overlay path**

Run: `grep -n "_row_layout\|row_layout\|EMOJI_ROW_CAP" src/led_ticker/widgets/_image_base.py`

Expected: lines that call `row_layout` for the two-row branch, plus the `EMOJI_ROW_CAP` import.

- [ ] **Step 2: Identify the per-row caps currently computed in `_image_base.py`**

Look for `top_h` / `bottom_h` and any `*_emoji_cap` assignments — this widget shares `resolve_band_heights` with `TwoRowMessage`. If the per-row cap isn't yet computed (the field surface tripwire in `TestFieldSurfaceMatchesTwoRow` should keep things in sync — verify by running it):

Run: `uv run pytest tests/test_widgets/test_image_base.py::TestFieldSurfaceMatchesTwoRow -v`

Expected: pass.

- [ ] **Step 3: Update the `_row_layout` calls to pass `sprite_logical_height`**

Mirror the two_row.py change: compute `top_emoji_cap` / `bottom_emoji_cap` BEFORE the row_layout calls, pass them as `sprite_logical_height`.

- [ ] **Step 4: Add tripwire to `tests/test_widgets/test_image_base.py`**

Add a test near the existing `TestFieldSurfaceMatchesTwoRow` class (search for `class TestFieldSurfaceMatchesTwoRow` and add immediately after):

```python
class TestImageTwoRowHiresEmojiAnchoring:
    """Hi-res emoji in a band sized to fit it should anchor at the
    band's top edge, not at the 8-row low-res-sprite centering
    position. Mirrors `test_hires_sprite_anchors_within_full_band`
    in test_two_row.py for the image two-row text overlay path."""

    def test_hires_sprite_anchors_within_full_band(self):
        from types import SimpleNamespace

        from led_ticker.fonts import FONT_SMALL
        from led_ticker.widgets._row_layout import row_layout

        canvas = SimpleNamespace(height=24, scale=2, width=128)
        _, top_emoji_y = row_layout(
            canvas, FONT_SMALL,
            band_height=16, band_offset=0,
            sprite_logical_height=16,
        )
        assert top_emoji_y == 0
```

- [ ] **Step 5: Verify tests pass**

Run: `uv run pytest tests/test_widgets/test_image_base.py -v`

Expected: all pass including the new tripwire.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/_image_base.py tests/test_widgets/test_image_base.py
git commit -m "image two-row: thread per-row emoji_cap into row_layout

Mirrors the two_row widget change. Hi-res sprite in a band sized
for it anchors at the band top without a manual offset."
```

---

## Task 4: Remove the workaround from the demo TOML

**Files:**
- Modify: `docs/site/demos-pinned/two_row-hires-emoji.toml`
- Re-render: `docs/site/public/demos-pinned/two_row-hires-emoji.gif`

- [ ] **Step 1: Remove `top_emoji_y_offset = -4` and the inline math comment**

Edit `docs/site/demos-pinned/two_row-hires-emoji.toml`. The lines to remove:

```toml
# row_layout centers an EMOJI_ROW_CAP=8 sub-band within the 16-row top
# band, so the default emoji_y = (16-8)//2 = 4 (logical). The hi-res
# :instagram: sprite is 16 logical tall (32 real / scale=2) and would
# render at rows 4..19 — bleeding 4 rows into the bottom band. Pulling
# the emoji 4 rows up anchors it at row 0..15, exactly within the band.
top_emoji_y_offset = -4
```

The resulting widget block should match its pre-workaround state (just `top_text`, `top_row_height`, fonts, colors, alignment).

- [ ] **Step 2: Re-render the demo gif**

Run:
```bash
dur=$(grep -E '^# render-duration:' docs/site/demos-pinned/two_row-hires-emoji.toml | head -1 | awk '{print $3}')
uv run python tools/render_demo/render.py \
  docs/site/demos-pinned/two_row-hires-emoji.toml \
  -o docs/site/public/demos-pinned/two_row-hires-emoji.gif \
  --duration $dur
```

- [ ] **Step 3: Visually verify the gif**

Extract a frame and inspect:

```bash
uv run python -c "
from PIL import Image
im = Image.open('docs/site/public/demos-pinned/two_row-hires-emoji.gif')
im.seek(5); im.convert('RGB').save('/tmp/hires_fix_5.png')
"
```

Open `/tmp/hires_fix_5.png` (Read tool). Expected: the IG sprite's bottom edge sits ABOVE the bottom-row text — no visible overlap.

- [ ] **Step 4: Commit**

```bash
git add docs/site/demos-pinned/two_row-hires-emoji.toml docs/site/public/demos-pinned/two_row-hires-emoji.gif
git commit -m "demo: drop top_emoji_y_offset workaround from hires-emoji demo

row_layout now centers the actual sprite size within the band, so
the 16-row :instagram: sprite anchors correctly without the manual
offset."
```

---

## Task 5: Update the docs MDX example + prose

**Files:**
- Modify: `docs/site/src/content/docs/widgets/two_row.mdx` (lines around 113)

- [ ] **Step 1: Edit the prose around the Hi-res emoji example**

Replace the workaround paragraph at line ~113 with a simpler version that doesn't mention the offset:

```markdown
The hi-res sprite is 32 real pixels tall. At `scale = 2` it's 16 logical pixels, which exactly matches `top_row_height = 16` — the sprite anchors at the top of the band with no bleed into the bottom row. Smaller bands fall back to the 8×8 lo-res sprite automatically.
```

- [ ] **Step 2: Remove the offset line from the TOML example**

In the same file, the TomlExample block for this section should drop:

```toml
top_emoji_y_offset = -4   # anchor the 16-row hi-res sprite to the top edge of the 16-row band
```

The example should look like:

```toml
[[playlist.section]]
mode = "swap"
scale = 2
content_height = 24

[[playlist.section.widget]]
type = "two_row"
top_text = ":instagram: @moonbunny"
top_row_height = 16
top_font = "Inter-Bold"
top_font_size = 22
top_color = [225, 48, 108]
top_align = "left"
bottom_text = "Aerial • pole • silks • juggling • all levels • now booking"
bottom_color = [255, 240, 200]
bottom_align = "left"
```

- [ ] **Step 3: Build the docs site**

Run: `make docs-build`

Expected: clean build, 39 pages.

- [ ] **Step 4: Commit**

```bash
git add docs/site/src/content/docs/widgets/two_row.mdx
git commit -m "docs: two_row hires emoji example no longer needs an offset

row_layout now centers the actual sprite within the band, so the
example reverts to its natural form. Prose drops the explanation
of the workaround."
```

---

## Task 6: Update CLAUDE.md invariants

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Locate the "Two-row widget" invariants section**

Run: `grep -n "Two-row widget\|row_layout\|EMOJI_ROW_CAP" CLAUDE.md`

Expected: a section discussing per-row emoji cap and the existing tripwire.

- [ ] **Step 2: Add a sentence about the new `sprite_logical_height` parameter**

Find the paragraph describing the per-row emoji cap and append:

```
`row_layout` accepts `sprite_logical_height` (defaults to `EMOJI_ROW_CAP = 8`); widget callers pass their per-row cap so the actual sprite is centered within the band rather than always centering an 8-row sub-band. Tripwire: `test_hires_sprite_anchors_within_full_band` in `tests/test_widgets/test_two_row.py` (and the mirrored test in `test_image_base.py`).
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "CLAUDE.md: document sprite_logical_height parameter on row_layout"
```

---

## Task 7: Full validation + PR

- [ ] **Step 1: Run the full suite**

Run: `make test && make lint && make typecheck && make docs-build`

Expected: all green.

- [ ] **Step 2: Memory cleanup**

After the PR merges, the follow-up memory note at `~/.claude/projects/.../project_row_layout_hires_emoji_centering.md` becomes obsolete. Add a checklist item to the PR description noting the memory entry should be removed after merge. (Don't remove it preemptively — the memory is the spec for this PR.)

- [ ] **Step 3: Open the PR**

```bash
gh pr create --title "fix: row_layout centers actual sprite size, not an 8-row sub-band" --body "$(cat <<'EOF'
## Summary

- Add `sprite_logical_height` parameter to `row_layout` (defaults to `EMOJI_ROW_CAP = 8` for back-compat).
- `TwoRowMessage` and `_BaseImageWidget` two-row mode pass their per-row cap so the actual sprite is centered within the band.
- Drops the `top_emoji_y_offset = -4` workaround from the pinned two_row hi-res emoji demo + corresponding docs paragraph.

## Background

PR #42 shipped a workaround for hi-res emoji overlap on `:instagram: @moonbunny` two-row layouts. The root cause is that `row_layout` always computes `emoji_y` for an 8-row low-res sprite — so a 16-row hi-res sprite in a 16-row band sits at row 4 and bleeds 4 rows into the bottom band.

This PR threads each row's actual emoji cap (`max(EMOJI_ROW_CAP, band_h)` — already computed by the widget) through to `row_layout`, which now centers a sprite of that height. The 16-row IG sprite in the 16-row band anchors at row 0, no bleed.

## Test plan

- [ ] `make test` green (1450+ tests)
- [ ] New unit tests for `row_layout` (`test_row_layout.py`) cover legacy default, full-band sprite, smaller sprite, taller-than-band clamp, and band_offset propagation.
- [ ] Tripwires in `test_two_row.py` and `test_image_base.py` lock in the 16-row sprite + 16-row band case.
- [ ] Re-rendered `two_row-hires-emoji.gif` shows clean separation between the IG sprite and the bottom row text.

After merge: remove the `project_row_layout_hires_emoji_centering.md` memory note (it's now obsolete).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review checklist (for the implementer)

1. **Spec coverage:**
   - row_layout signature change → Task 1 ✅
   - TwoRowMessage call sites updated → Task 2 ✅
   - _BaseImageWidget call sites updated → Task 3 ✅
   - Demo TOML + gif → Task 4 ✅
   - Docs MDX prose + example → Task 5 ✅
   - CLAUDE.md invariants → Task 6 ✅

2. **Placeholder scan:** No TBDs, no "implement appropriate error handling", no "similar to Task N" without the code shown. All steps include the actual code or commands.

3. **Type consistency:** `sprite_logical_height: int = EMOJI_ROW_CAP` is consistent across the row_layout signature, the widget caller sites, and the test fixtures (all pass `int`).

4. **Edge cases:**
   - back-compat default preserves existing call sites (Task 1 covers via `test_default_sprite_height_preserves_legacy_centering`)
   - sprite > band clamping (Task 1 covers via `test_sprite_taller_than_band_clamps_to_band_top`)
   - non-zero band_offset (Task 1 covers via `test_non_zero_band_offset_threads_through`)

5. **Out of scope for this PR:**
   - Per-emoji sizing — `row_layout` accepts ONE height per band. If a row contains a mix of hi-res and lo-res emojis, the cap-based centering may leave one of them visually off-center. The `top_emoji_y_offset` / `bottom_emoji_y_offset` knobs remain available for manual override. A future refactor could scan the text for actual sprite heights and pick the max, but is not addressed here.
   - Validation of `sprite_logical_height` value — no negative check, no upper bound. Callers control the value; widget validation already gates band heights.
