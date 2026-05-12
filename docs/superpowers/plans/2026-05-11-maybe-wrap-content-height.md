# `_maybe_wrap` content_height fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Fix `src/led_ticker/ticker.py::_maybe_wrap` so `content_height` is honored at `scale=1` on panels where `content_height < panel_height`. Currently the wrapper only engages at `scale > 1`, so widgets reading `canvas.height` get the raw panel height and produce wrong layouts.

**Architecture:** Single-line conditional change to `_maybe_wrap`. Three new tests covering the band-split correctness, the render-path switch side effect, and the hi-res emoji activation side effect. One existing test (`test_maybe_wrap_returns_real_canvas_at_scale_1`) gets rewritten to test the new contract.

**Tech Stack:** Python 3.13, pytest, attrs. No new deps.

**Spec:** `docs/superpowers/specs/2026-05-11-maybe-wrap-content-height-design.md`

---

## File structure

| File | Action | Purpose |
|------|--------|---------|
| `src/led_ticker/ticker.py` | Modify | Change `_maybe_wrap` guard from `scale > 1` to `scale > 1 or content_height < canvas.height` |
| `tests/test_ticker.py` | Modify | Rewrite `test_maybe_wrap_returns_real_canvas_at_scale_1`; add new tests for the wrap-at-scale=1-with-content_height case |
| `tests/test_widgets/test_two_row.py` | Modify | Add integration test: two_row at `scale=1, content_height=16` on 64-tall panel → band split is 8+8, not 32+32 |
| `tests/test_text_render.py` (existing or new) | Modify/Create | Pixel-parity test between `_graphics.DrawText` and `draw_bdf_text` for representative text content |
| `tests/test_pixel_emoji.py` | Modify | Add test: hi-res sprite activation at scale=1 wrapped canvas; assert it renders at native physical coords |
| `docs/site/demos-long/tutorial-03c-two_row-basic.toml` | Modify | Revert to `scale = 1, content_height = 16` (the workaround can be removed) |
| `docs/site/public/demos-long/tutorial-03c-two_row-basic.gif` | Re-render | Confirm visual parity with the current scale=2 workaround |
| `docs/site/src/content/docs/tutorial/03-multi-widget.mdx` | Modify (optional) | Decision after rendering — keep current scale=2 framing OR revert to scale=1 framing |
| `CLAUDE.md` | Modify (optional) | Update if any invariant changes — verify the `_maybe_wrap` description matches |

---

## Task 1: Audit for surprise behavior changes

**Files:** none — read-only sweep.

- [ ] **Step 1: Find any config with `scale = 1` and explicit `content_height < panel_height`**

```bash
grep -rn "scale = 1" --include="*.toml" .
grep -rn "scale = 1" config/ docs/site/demos-pinned/ docs/site/demos-long/
```

Expected output: list of configs. For each, check if it sets `content_height < panel_height`. If found, document the expected behavior change.

- [ ] **Step 2: Search for callers of `_maybe_wrap` that pass non-default `content_height`**

```bash
grep -rn "_maybe_wrap(" src/
```

Confirm all callers thread `content_height` from the section config (they do — `ticker.py` wraps `Ticker.run_*` methods).

- [ ] **Step 3: Document any surprise cases as PR description warnings**

Anything that would visually change should be called out in the PR description so reviewers know to look for visual diffs in those demos.

---

## Task 2: Failing test for band-split correctness

**Files:**
- Modify: `tests/test_widgets/test_two_row.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_widgets/test_two_row.py`:

```python
def test_two_row_band_split_honors_content_height_at_scale_1():
    """Regression: at scale=1, content_height=16 on a 64-tall panel,
    the band split must be 8+8 (16-row content area divided 50/50),
    not 32+32 (the raw panel height divided 50/50). Bug fixed by
    `_maybe_wrap` wrapping at scale=1 when content_height < panel_height.
    """
    from led_ticker.ticker import _maybe_wrap
    from led_ticker.widgets._row_layout import resolve_band_heights
    from types import SimpleNamespace

    real = SimpleNamespace(height=64, width=256)
    wrapped = _maybe_wrap(real, scale=1, content_height=16)

    top_h, bottom_h = resolve_band_heights(wrapped.height, top_row_height=None)
    assert top_h == 8, f"top_h={top_h}; expected 8 (16-row canvas split 50/50)"
    assert bottom_h == 8, f"bottom_h={bottom_h}; expected 8"
```

- [ ] **Step 2: Run, confirm it fails**

```bash
uv run pytest tests/test_widgets/test_two_row.py::test_two_row_band_split_honors_content_height_at_scale_1 -v
```

Expected: FAIL with `top_h=32; expected 8`.

- [ ] **Step 3: Don't commit yet — apply the fix in Task 3 first.**

---

## Task 3: Apply the `_maybe_wrap` fix

**Files:**
- Modify: `src/led_ticker/ticker.py` (around line 47)

- [ ] **Step 1: Update the conditional**

Find:

```python
def _maybe_wrap(canvas: Any, scale: int, content_height: int = 16) -> Any:
    """Wrap canvas in a ScaledCanvas when scale > 1; otherwise return as-is.

    `content_height` controls the wrapper's logical height. Default 16 matches
    a single 5x8 / 6x12 row. Sections that need vertical breathing room (e.g.
    the two_row layout) can request a taller logical canvas by passing
    `content_height=20` etc.
    """
    if scale > 1:
        return ScaledCanvas(canvas, scale=scale, content_height=content_height)
    return canvas
```

Replace with:

```python
def _maybe_wrap(canvas: Any, scale: int, content_height: int = 16) -> Any:
    """Wrap canvas in a ScaledCanvas when either:
      - `scale > 1`, OR
      - `content_height < canvas.height` (content area smaller than real panel).

    `content_height` controls the wrapper's logical height. Default 16 matches
    a single 5x8 / 6x12 row. Sections that need vertical breathing room (e.g.
    the two_row layout) can request a taller logical canvas by passing
    `content_height=20` etc.

    The `content_height < canvas.height` guard matters at `scale=1` on panels
    taller than the content area (e.g. bigsign at scale=1 with content_height=16
    on a 64-tall panel). Without this guard, widgets reading `canvas.height`
    would get the raw panel height (64) and compute layouts in real-panel space
    rather than the intended content area, producing visibly wrong placements.
    """
    if scale > 1 or content_height < canvas.height:
        return ScaledCanvas(canvas, scale=scale, content_height=content_height)
    return canvas
```

- [ ] **Step 2: Run the Task 2 test — confirm it passes**

```bash
uv run pytest tests/test_widgets/test_two_row.py::test_two_row_band_split_honors_content_height_at_scale_1 -v
```

Expected: PASS.

---

## Task 4: Rewrite existing tests asserting buggy behavior

**Files:**
- Modify: `tests/test_ticker.py`

- [ ] **Step 1: Find the test that needs rewriting**

```bash
grep -n "test_maybe_wrap_returns_real_canvas_at_scale_1\|_maybe_wrap" tests/test_ticker.py
```

- [ ] **Step 2: Rewrite the test**

If the existing test asserts `not isinstance(result, ScaledCanvas)` at `scale=1`, replace with two tests reflecting the new contract:

```python
def test_maybe_wrap_skips_wrap_when_canvas_fits():
    """At scale=1 with content_height matching panel height, no wrap needed —
    canvas is returned unchanged. This is the smallsign case
    (panel_h=16, content_height=16)."""
    from led_ticker.ticker import _maybe_wrap
    from led_ticker.scaled_canvas import ScaledCanvas
    from types import SimpleNamespace

    real = SimpleNamespace(height=16, width=160)
    result = _maybe_wrap(real, scale=1, content_height=16)
    assert not isinstance(result, ScaledCanvas)
    assert result is real

def test_maybe_wrap_engages_when_content_height_smaller_than_panel():
    """At scale=1 but content_height < panel_h, the wrapper engages so
    widgets compute layout in content-area space, not raw panel space.
    This is the bigsign at scale=1 case (panel_h=64, content_height=16)."""
    from led_ticker.ticker import _maybe_wrap
    from led_ticker.scaled_canvas import ScaledCanvas
    from types import SimpleNamespace

    real = SimpleNamespace(height=64, width=256)
    result = _maybe_wrap(real, scale=1, content_height=16)
    assert isinstance(result, ScaledCanvas)
    assert result.height == 16
    assert result.scale == 1
```

- [ ] **Step 3: Run the full test_ticker.py module**

```bash
uv run pytest tests/test_ticker.py -v
```

Expected: all pass.

---

## Task 5: Pixel-parity test for DrawText / draw_bdf_text render-path switch

**Files:**
- Modify or Create: `tests/test_text_render.py`

- [ ] **Step 1: Identify the rendering branches**

Read `src/led_ticker/text_render.py::draw_text`. Confirm the `isinstance(canvas, ScaledCanvas)` branch routes to `draw_bdf_text` (BDF rasterizer); the else branch routes to `_graphics.DrawText` (native).

- [ ] **Step 2: Write a pixel-parity test**

For representative text content + standard BDF fonts (`5x8`, `6x12`, `7x13`), assert that the BDF rasterizer and the native `DrawText` produce identical output. This is a permanent tripwire — if the two paths ever diverge, smallsign installs that get newly-wrapped via Task 3's fix would show subtle text differences.

```python
def test_bdf_rasterizer_matches_native_drawtext_on_5x8():
    """BDF rasterizer (via draw_bdf_text) and native _graphics.DrawText
    must produce identical pixel output for the standard BDF fonts.
    Permanent tripwire: if these diverge, smallsign installs that newly
    use the wrapper at scale=1 (after the _maybe_wrap fix) would show
    subtle text rendering differences."""
    # Implementation: render "Hello world" with both paths into matched
    # canvases, then assert pixel-for-pixel equality. Reuse existing
    # canvas test stubs from tests/conftest.py.
    pass  # full implementation when writing the test
```

The agent implementing this task should look at existing rendering tests in `tests/` for canvas stub patterns; mirror those.

- [ ] **Step 3: Run the test**

```bash
uv run pytest tests/test_text_render.py -v
```

Expected: PASS. If FAILS, the BDF rasterizer and `DrawText` diverge in some way — STOP and report. That's a load-bearing finding that blocks the `_maybe_wrap` fix.

---

## Task 6: Hi-res emoji activation test at scale=1

**Files:**
- Modify: `tests/test_pixel_emoji.py`

- [ ] **Step 1: Write the test**

```python
def test_hires_emoji_activates_at_scale_1_with_wrapper():
    """When _maybe_wrap engages at scale=1 (bigsign with content_height < panel_h),
    `use_hires = isinstance(canvas, ScaledCanvas)` fires and hi-res sprites
    render at native physical resolution into the content area."""
    from led_ticker.ticker import _maybe_wrap
    from led_ticker.pixel_emoji import draw_emoji_at
    from types import SimpleNamespace

    # Build a bigsign-ish recording canvas at scale=1 with content_height=16
    real = build_recording_canvas(height=64, width=256)
    wrapped = _maybe_wrap(real, scale=1, content_height=16)

    # Draw the IG sprite at logical (0, 0); should hit hi-res because:
    #   - canvas is ScaledCanvas (use_hires=True)
    #   - candidate exists in HIRES_REGISTRY
    #   - logical_h = 32//1 = 32, which OVERFLOWS the 16-row content area.
    # Expectation: depends on the row_layout cap. Document the behavior
    # explicitly so we know what should happen.
    advance = draw_emoji_at(wrapped, "instagram", 0, 0)

    # Assert pixels were written and document where they landed.
    # Specifically: at scale=1 + content_height=16, _y_offset = 24, so
    # painting hi-res at logical (0, 0) places real pixels at (0, 24..55)
    # — but the sprite is 32 tall and the content area is only 16,
    # so the sprite overflows below the content area.
    # This is a real behavior to document, not necessarily a separate bug.
```

The implementing agent should figure out the precise expected behavior by running the renderer; this test documents what actually happens so future contributors know.

- [ ] **Step 2: Run the test**

```bash
uv run pytest tests/test_pixel_emoji.py -v
```

If the test reveals an overflow issue, document it in the spec's "Risks" section and decide whether to fix in this PR or follow-up.

---

## Task 7: Validate by re-rendering tutorial-03c at scale=1

**Files:**
- Modify: `docs/site/demos-long/tutorial-03c-two_row-basic.toml`
- Re-render: `docs/site/public/demos-long/tutorial-03c-two_row-basic.gif`

- [ ] **Step 1: Revert tutorial-03c to `scale = 1`**

Change `scale = 2` back to `scale = 1` in the TOML. Keep `content_height = 16` and all other fields.

- [ ] **Step 2: Re-render**

```bash
make render-long-demo NAME=tutorial-03c-two_row-basic
```

- [ ] **Step 3: Visually compare to the current scale=2 version**

Extract midpoint frames from both versions (you'll need to keep a copy of the current scale=2 gif before re-rendering) and confirm:
- 8×8 lo-res IG sprite at top, properly aligned with @moonbunny text in the same band
- Bottom row scrolling
- No visible difference in band positions / sizes

If the scale=1 version looks broken, the `_maybe_wrap` fix has a subtle issue and we should NOT ship until investigated.

- [ ] **Step 4: Decision — keep or revert chapter prose**

Currently `tutorial/03-multi-widget.mdx` introduces `scale = 2` as the bigsign baseline. After the fix, you could revert the prose to introduce `scale = 1` as the simpler baseline (since the wrapper now engages correctly). This is a judgment call:
- Revert if the scale=1 framing reads as a cleaner pedagogical entry point.
- Keep if the scale=2 framing teaches more concepts up-front.

Either way, update the chapter prose to be consistent with the demo TOML.

---

## Task 8: Run full test suite + commit + open PR

- [ ] **Step 1: `make test`**

Expected: all tests pass.

- [ ] **Step 2: `make lint && make typecheck && make docs-build`**

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "fix: _maybe_wrap honors content_height at scale=1

Per memory note project_maybe_wrap_drops_content_height_at_scale1.md:
at scale=1 the canvas was returned unwrapped, silently dropping
content_height from TOML. Widgets reading canvas.height got the raw
panel height. The two_row widget's band split misbehaved on bigsign
configs that set scale=1 + content_height<panel_h.

Fix: wrap whenever (scale > 1 OR content_height < canvas.height).
ScaledCanvas at scale=1 is arithmetically correct — _y_offset
centers the content_height region on the panel, SetPixel is a
vertical-translate-only operation.

Tests:
- Band-split correctness at scale=1, content_height=16 on 64-tall panel
- Rewritten existing test_maybe_wrap_returns_real_canvas_at_scale_1
  (it was testing the bug; now tests the new contract)
- Pixel-parity tripwire between BDF rasterizer and native DrawText
  (permanent: any divergence would silently affect smallsign installs)
- Hi-res emoji activation behavior at the newly-wrapped path

Side effects (documented):
- text_render path switches from native DrawText to BDF rasterizer for
  scale=1 + content_height < panel_h configs. Pixel-equivalent per the
  tripwire test.
- Hi-res emoji can activate at scale=1 with the wrapper; sprite size vs
  content_height overflow is documented but unchanged from prior behavior.

Validated by re-rendering tutorial-03c at scale=1 (was workaround'd
to scale=2 in PR #47); produces visually equivalent output.
"
```

- [ ] **Step 4: Push + open PR**

```bash
git push -u origin worktree-maybe-wrap-fix
gh pr create --title "fix: _maybe_wrap honors content_height at scale=1" --body "..."
```

PR body should include the diagnosis from the memory note + the four side effects + the test evidence.

---

## Self-review

**Spec coverage:**
- Fix the conditional ✅ (Task 3)
- New behavior test ✅ (Task 2)
- Existing bug-asserting test rewritten ✅ (Task 4)
- Pixel-parity tripwire for render-path switch ✅ (Task 5)
- Hi-res emoji activation ✅ (Task 6)
- Validation on a real demo ✅ (Task 7)
- Repo-wide audit for affected configs ✅ (Task 1)

**Placeholder scan:** Task 5 and Task 6 have explicit "implementing agent: figure out the precise expected behavior" notes — those aren't placeholders but acknowledged places where the test author has to do additional research. Acceptable.

**Type consistency:** New tests use `SimpleNamespace` for canvas stubs (matches existing test style). The `_maybe_wrap` signature is unchanged; only the body changes.

**Edge case coverage:** The fix only adds a wrap when one specific condition fires; existing code paths at `scale > 1` are unchanged. Smallsign with `panel_h=16, content_height=16` (the default) doesn't wrap (`16 < 16` is false), preserving today's behavior.
