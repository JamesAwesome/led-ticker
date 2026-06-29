# panel-map Pixel-Mapper Helper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `panel-map`, a panel-test-style helper that turns deriving a `pixel_mapper_config` Remap string into a reveal → photograph → transcribe → derive → verify loop, with persona reviews (PM + hobbyist) gating each user-facing task.

**Architecture:** Pure logic (grid parsing, string derivation, calibration-pattern painting) lives in an importable module `src/led_ticker/panel_map.py` so it is unit-tested in the normal suite with no hardware. A thin CLI `scripts/panel_map.py` wires `build_frame_from_config` → canvas → the paint functions and handles Ctrl-C, exactly like `scripts/panel_color_test.py`. `reveal` builds the frame with the mapper forced to identity (raw chain canvas); `verify` builds it with the candidate mapper (final canvas).

**Tech Stack:** Python 3.14, `argparse`, `dataclasses.replace`, the existing `led_ticker.config.load_config` + `led_ticker.app.factories.build_frame_from_config`, the `HeadlessBackend`/`HeadlessCanvas` test stubs. No new dependencies.

## Global Constraints

- **No `from __future__ import annotations` in package source** under `src/led_ticker/` is fine to include (core uses it); plugin source forbids it, but this is core. Match the surrounding file's style — `scripts/panel_color_test.py` uses it, so the new script may too.
- **Hardware-rendering constraints (CLAUDE.md):** #1 every `SwapOnVSync` return value MUST be captured (`canvas = frame.matrix.SwapOnVSync(canvas)`); #3 never `GetPixel` on a real canvas (tests may use the headless `get_pixel`); #4 `SetPixel` works everywhere — all calibration drawing uses `SetPixel`; #5 swap-then-sleep ordering.
- **No LLM anywhere** — every step is deterministic Python (spec non-goal).
- **Personas are the customer.** PM persona = scope/value/discoverability; hobbyist persona = a terminal-comfortable, non-engineer maker with AliExpress HUB75 panels who has never heard of a pixel mapper. Each user-facing task ends with a persona-review gate; blocking concerns are fixed before the task is considered done, non-blocking ones recorded as follow-ups in the plan.
- **`e`/`w` (90°/270°) visual→flag mapping is a hardware-spike output** (Task 5) and a **release blocker for the docs legend** — software tasks must not hardcode a guessed `e`/`w` visual; they treat the flag as opaque pass-through data.
- **Spec:** `docs/superpowers/specs/2026-06-29-panel-map-helper-design.md` is the source of truth.

---

## File Structure

- Create `src/led_ticker/panel_map.py` — pure logic: `LayoutError`, `parse_layout`, `derive_remap_string`, `parse_remap_string`, `DIGITS_3x5` + `draw_digit`/`draw_index`, `draw_up_arrow`, `draw_corner_dot`, `draw_underline`, `draw_border`, `paint_reveal`, `paint_verify`.
- Create `scripts/panel_map.py` — thin CLI (`reveal`/`derive`/`verify` subcommands), mirrors `scripts/panel_color_test.py`.
- Create `tests/test_panel_map.py` — unit tests for all pure logic (golden tripwire, error cases, paint-geometry assertions on `HeadlessCanvas`).
- Create `docs/site/src/content/docs/tools/panel-map.mdx` — user docs.
- Modify `Makefile` — add `panel-map-reveal`, `panel-map-verify`, `panel-map-derive` (+ `-docker` variants).
- Modify `docs/site/src/content/docs/tools/panel-test.mdx` — cross-link + RelatedPages.
- Modify `docs/site/src/content/docs/hardware/building-your-own.mdx` — inline intercept at the `pixel_mapper_config` step.
- Modify `docs/site/src/content/docs/hardware/bigsign.mdx` and `docs/site/src/content/docs/reference/cli.mdx` — cross-links.

---

## Task 1: `derive` — pure string generator + golden tripwire

**Files:**
- Create: `src/led_ticker/panel_map.py`
- Test: `tests/test_panel_map.py`

**Interfaces:**
- Produces:
  - `class LayoutError(ValueError)` — raised with a plain-language message on any invalid grid.
  - `parse_layout(text: str) -> list[list[tuple[int, str]]]` — parse the ASCII grid into rows of `(index, flag)` cells. Raises `LayoutError`.
  - `derive_remap_string(text: str, *, cols: int, rows: int, chain_length: int, parallel: int) -> str` — returns the full `Remap:WIDTH,HEIGHT|x,yORIENT|...` string in chain-index order. Raises `LayoutError`. Emits no warnings itself (the CLI handles the count-mismatch warning).
  - `VALID_FLAGS = ("n", "s", "e", "w", "x")`

- [ ] **Step 1: Write failing tests for `parse_layout` + `derive_remap_string`**

```python
# tests/test_panel_map.py
import pytest
from led_ticker.panel_map import (
    LayoutError,
    derive_remap_string,
    parse_layout,
)

BIGSIGN_GRID = "8n 6n 4n 2n\n7n 5n 3n 1n"
BIGSIGN_STRING = (
    "Remap:256,64|192,32n|192,0n|128,32n|128,0n|64,32n|64,0n|0,32n|0,0n"
)


def test_parse_layout_basic():
    grid = parse_layout("3n 4n\n1s 2e")
    assert grid == [[(3, "n"), (4, "n")], [(1, "s"), (2, "e")]]


def test_derive_reproduces_bigsign_string_exactly():
    # Golden tripwire: the real config.bigsign.example.toml string.
    out = derive_remap_string(
        BIGSIGN_GRID, cols=64, rows=32, chain_length=8, parallel=1
    )
    assert out == BIGSIGN_STRING


def test_derive_single_row_of_four():
    out = derive_remap_string(
        "1n 2n 3n 4n", cols=64, rows=32, chain_length=4, parallel=1
    )
    assert out == "Remap:256,32|0,0n|64,0n|128,0n|192,0n"


def test_derive_two_by_two_grid():
    # chain enters bottom-left, runs bottom row then top row right-to-left
    out = derive_remap_string(
        "4n 3n\n1n 2n", cols=64, rows=32, chain_length=4, parallel=1
    )
    assert out == "Remap:128,64|0,32n|64,32n|64,0n|0,0n"


def test_derive_preserves_rotation_flags():
    out = derive_remap_string(
        "1s 2e", cols=64, rows=32, chain_length=2, parallel=1
    )
    assert out == "Remap:128,32|0,0s|64,0e"


def test_missing_index_is_plain_language_error():
    with pytest.raises(LayoutError, match="never listed panel 2"):
        derive_remap_string("1n 3n", cols=64, rows=32, chain_length=3, parallel=1)


def test_duplicate_index_is_plain_language_error():
    with pytest.raises(LayoutError, match="listed panel 1 twice"):
        derive_remap_string("1n 1n", cols=64, rows=32, chain_length=2, parallel=1)


def test_ragged_grid_is_plain_language_error():
    with pytest.raises(LayoutError, match="same number of cells"):
        parse_layout("1n 2n 3n\n4n 5n")


def test_bad_flag_is_error():
    with pytest.raises(LayoutError, match="z"):
        parse_layout("1z 2n")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_panel_map.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'led_ticker.panel_map'`

- [ ] **Step 3: Implement `src/led_ticker/panel_map.py` (derive half only)**

```python
"""panel-map: derive and verify a pixel_mapper_config Remap string.

Pure logic (grid parsing, string derivation, calibration-pattern painting)
lives here so it can be unit-tested with no hardware. The CLI in
scripts/panel_map.py wires this to a real LedFrame.

See docs.ledticker.dev/tools/panel-map/ for the user-facing workflow and
docs/superpowers/specs/2026-06-29-panel-map-helper-design.md for the design.
"""

from __future__ import annotations

VALID_FLAGS = ("n", "s", "e", "w", "x")


class LayoutError(ValueError):
    """Invalid transcribed grid. Messages are plain-language on purpose:
    a first-time builder must understand exactly what to fix."""


def parse_layout(text: str) -> list[list[tuple[int, str]]]:
    """Parse the transcribed ASCII grid into rows of (index, flag) cells.

    One text line per physical wall row, top row first; whitespace-separated
    cells, each ``<chain-index><flag>`` e.g. ``3s``. Raises LayoutError.
    """
    rows: list[list[tuple[int, str]]] = []
    for line in (ln for ln in text.splitlines() if ln.strip()):
        cells: list[tuple[int, str]] = []
        for token in line.split():
            flag = token[-1].lower()
            num = token[:-1]
            if flag not in VALID_FLAGS or not num.isdigit():
                raise LayoutError(
                    f"'{token}' isn't a valid cell. Each cell is a panel "
                    f"number followed by one of {', '.join(VALID_FLAGS)} "
                    f"(e.g. '3s'). Got flag '{flag}'."
                )
            cells.append((int(num), flag))
        rows.append(cells)
    if not rows:
        raise LayoutError("Empty layout — nothing to derive.")
    width = len(rows[0])
    for i, r in enumerate(rows):
        if len(r) != width:
            raise LayoutError(
                f"Row {i + 1} has {len(r)} panels but row 1 has {width}. "
                "Every wall row needs the same number of cells."
            )
    return rows


def derive_remap_string(
    text: str,
    *,
    cols: int,
    rows: int,
    chain_length: int,
    parallel: int,
) -> str:
    """Compute the full Remap string from a transcribed grid.

    For each cell at grid (row, col): target x = col*cols, y = row*rows,
    orientation = flag. Entries are emitted in chain-index order 1..N.
    """
    grid = parse_layout(text)
    g_rows = len(grid)
    g_cols = len(grid[0])
    width = g_cols * cols
    height = g_rows * rows

    # index -> (x, y, flag)
    placement: dict[int, tuple[int, int, str]] = {}
    for r, row in enumerate(grid):
        for c, (idx, flag) in enumerate(row):
            if idx in placement:
                raise LayoutError(
                    f"You listed panel {idx} twice. Each cable position "
                    "appears exactly once."
                )
            placement[idx] = (c * cols, r * rows, flag)

    n = g_rows * g_cols
    entries: list[str] = []
    for k in range(1, n + 1):
        if k not in placement:
            raise LayoutError(
                f"You never listed panel {k} (the grid has {n} cells and "
                f"its numbers must be 1..{n}, each once)."
            )
        x, y, flag = placement[k]
        entries.append(f"{x},{y}{flag}")

    return f"Remap:{width},{height}|" + "|".join(entries)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_panel_map.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Run lint**

Run: `uv run --extra dev ruff check src/led_ticker/panel_map.py tests/test_panel_map.py`
Expected: no errors (CI lint gate — the make targets don't run ruff, so run it explicitly).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/panel_map.py tests/test_panel_map.py
git commit -m "feat(panel-map): derive Remap string from transcribed grid"
```

- [ ] **Step 7: Persona review gate (derive UX)**

Dispatch BOTH personas in parallel (Agent tool, `general-purpose`), giving each the full text of `src/led_ticker/panel_map.py` (derive half) and these test cases. Prompts:

- **PM:** "Review this `derive` logic + tests for the panel-map tool (spec at docs/superpowers/specs/2026-06-29-panel-map-helper-design.md). Is the scope right (no gold-plating, nothing core missing)? Are the validation cases the ones that matter? Reply with blocking vs non-blocking concerns."
- **Hobbyist** (use the persona brief from the spec's review): "You're a terminal-comfortable non-engineer with AliExpress panels. Read these `derive` error messages (missing/duplicate/ragged/bad-flag). For each, would you understand exactly what to fix? Rewrite any that would confuse you. Would you trust this tool after seeing them?"

Address blocking concerns inline (re-run Steps 4–5, amend the commit). Record non-blocking items under a "Follow-ups" note at the end of this plan.

---

## Task 2: `reveal` — calibration pattern paint functions

**Files:**
- Modify: `src/led_ticker/panel_map.py`
- Test: `tests/test_panel_map.py`

**Interfaces:**
- Consumes: nothing from Task 1 (independent functions in the same module).
- Produces:
  - `DIGITS_3x5: dict[str, list[str]]` — 3×5 bitmap font for digits `0`–`9`.
  - `draw_index(canvas, value: int, x: int, y: int, *, scale: int, r=255, g=255, b=255) -> None` — draw a (possibly multi-digit) number top-left at `(x, y)`, each digit `3*scale` wide with a 1px gap.
  - `draw_up_arrow(canvas, cx: int, top_y: int, height: int, r, g, b) -> None`
  - `draw_corner_dot(canvas, x: int, y: int, size: int, r, g, b) -> None`
  - `draw_underline(canvas, x: int, y: int, length: int, r, g, b) -> None`
  - `draw_border(canvas, x: int, y: int, w: int, h: int, r, g, b) -> None`
  - `paint_reveal(canvas, *, cols: int, rows: int, chain_length: int, parallel: int) -> None` — paint every raw-chain slot with index + up-arrow + corner dot + underline + border. Slot for chain index `k` (1-based, `k = j*chain_length + i + 1` for parallel row `j`, chain position `i`) sits at `x = i*cols`, `y = j*rows`.

- [ ] **Step 1: Write failing tests (paint geometry on HeadlessCanvas)**

```python
# add to tests/test_panel_map.py
from led_ticker.backends.headless import HeadlessCanvas
from led_ticker.panel_map import (
    DIGITS_3x5,
    draw_index,
    paint_reveal,
)


def test_digit_font_has_all_ten_digits():
    for d in "0123456789":
        assert d in DIGITS_3x5
        assert len(DIGITS_3x5[d]) == 5  # five rows
        assert all(len(row) == 3 for row in DIGITS_3x5[d])  # three cols


def test_draw_index_lights_pixels_in_top_left_region():
    c = HeadlessCanvas(width=64, height=32)
    draw_index(c, 1, 2, 2, scale=1)
    assert c.count_nonzero() > 0
    # nothing painted outside the digit's small bounding box
    assert c.get_pixel(40, 20) == (0, 0, 0)


def test_paint_reveal_lights_every_slot():
    # smallsign geometry: 5 panels of 32x16
    c = HeadlessCanvas(width=160, height=16)
    paint_reveal(c, cols=32, rows=16, chain_length=5, parallel=1)
    # every 32-wide slot has lit pixels (the border alone guarantees this)
    for i in range(5):
        lit = any(
            c.get_pixel(x, y) != (0, 0, 0)
            for x in range(i * 32, (i + 1) * 32)
            for y in range(16)
        )
        assert lit, f"slot {i} is blank"


def test_paint_reveal_index_differs_between_slots():
    # The digit pixels for slot 0 ("1") and slot 1 ("2") must differ,
    # proving each slot draws its own index rather than a constant.
    c = HeadlessCanvas(width=160, height=16)
    paint_reveal(c, cols=32, rows=16, chain_length=5, parallel=1)
    slot0 = [c.get_pixel(x, y) for x in range(0, 32) for y in range(16)]
    slot1 = [c.get_pixel(x, y) for x in range(32, 64) for y in range(16)]
    assert slot0 != slot1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_panel_map.py -k "digit or reveal or draw_index" -v`
Expected: FAIL with `ImportError: cannot import name 'DIGITS_3x5'`

- [ ] **Step 3: Implement the paint functions (append to `src/led_ticker/panel_map.py`)**

```python
# 3x5 bitmap digits. Each entry is 5 rows of 3 chars; '1' = lit.
DIGITS_3x5: dict[str, list[str]] = {
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
}

_DIGIT_W = 3
_DIGIT_H = 5


def draw_digit(canvas, ch, x, y, *, scale, r, g, b):  # noqa: PLR0913
    glyph = DIGITS_3x5[ch]
    for ry, row in enumerate(glyph):
        for rx, bit in enumerate(row):
            if bit == "1":
                for dy in range(scale):
                    for dx in range(scale):
                        canvas.SetPixel(
                            x + rx * scale + dx, y + ry * scale + dy, r, g, b
                        )


def draw_index(canvas, value, x, y, *, scale=1, r=255, g=255, b=255):  # noqa: PLR0913
    cx = x
    for ch in str(value):
        draw_digit(canvas, ch, cx, y, scale=scale, r=r, g=g, b=b)
        cx += _DIGIT_W * scale + scale  # one scaled-pixel gap between digits


def draw_underline(canvas, x, y, length, r, g, b):  # noqa: PLR0913
    for dx in range(length):
        canvas.SetPixel(x + dx, y, r, g, b)


def draw_up_arrow(canvas, cx, top_y, height, r, g, b):  # noqa: PLR0913
    # vertical shaft
    for dy in range(height):
        canvas.SetPixel(cx, top_y + dy, r, g, b)
    # head: two diagonals from the tip
    for d in range(1, height // 2 + 1):
        canvas.SetPixel(cx - d, top_y + d, r, g, b)
        canvas.SetPixel(cx + d, top_y + d, r, g, b)


def draw_corner_dot(canvas, x, y, size, r, g, b):  # noqa: PLR0913
    for dy in range(size):
        for dx in range(size):
            canvas.SetPixel(x + dx, y + dy, r, g, b)


def draw_border(canvas, x, y, w, h, r, g, b):  # noqa: PLR0913
    for dx in range(w):
        canvas.SetPixel(x + dx, y, r, g, b)
        canvas.SetPixel(x + dx, y + h - 1, r, g, b)
    for dy in range(h):
        canvas.SetPixel(x, y + dy, r, g, b)
        canvas.SetPixel(x + w - 1, y + dy, r, g, b)


def paint_reveal(canvas, *, cols, rows, chain_length, parallel):
    """Paint each raw-chain panel slot with its 1-based chain index, an
    up-arrow (logical-up), a top-left corner dot, an underline beneath the
    index (this-way-up cue), and a slot border. Assumes an identity mapper
    so slot k maps 1:1 to the k-th physical panel in the cable chain.
    """
    canvas.Fill(0, 0, 0)
    # integer scale so the 5-tall digit comfortably fits the slot height
    scale = max(1, min(cols // 8, rows // 8))
    for j in range(parallel):
        for i in range(chain_length):
            k = j * chain_length + i + 1
            ox, oy = i * cols, j * rows
            draw_border(canvas, ox, oy, cols, rows, 0, 80, 80)
            draw_corner_dot(canvas, ox + 1, oy + 1, max(2, scale), 255, 0, 0)
            dx, dy = ox + 3, oy + 2
            draw_index(canvas, k, dx, dy, scale=scale)
            draw_underline(
                canvas, dx, dy + _DIGIT_H * scale, _DIGIT_W * scale, 0, 255, 0
            )
            # up-arrow on the right side of the slot
            draw_up_arrow(
                canvas, ox + cols - max(4, scale * 2), oy + 2, rows - 4,
                255, 255, 0,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_panel_map.py -k "digit or reveal or draw_index" -v`
Expected: PASS

- [ ] **Step 5: Generate a software preview PNG for review (no hardware)**

Add a tiny throwaway snippet run via `uv run python -c` that paints a smallsign and a bigsign-raw-chain `HeadlessCanvas` and dumps each to a scaled PNG (Pillow is already a dep) under the scratchpad, so the personas (and later the maintainer) can eyeball legibility before hardware exists:

```bash
uv run python - <<'PY'
from PIL import Image
from led_ticker.backends.headless import HeadlessCanvas
from led_ticker.panel_map import paint_reveal

for name, (cols, rows, chain) in {
    "smallsign": (32, 16, 5),
    "bigsign_rawchain": (64, 32, 8),
}.items():
    c = HeadlessCanvas(width=cols * chain, height=rows)
    paint_reveal(c, cols=cols, rows=rows, chain_length=chain, parallel=1)
    img = Image.new("RGB", (c.width, c.height))
    img.putdata([c.get_pixel(x, y) for y in range(c.height) for x in range(c.width)])
    img.resize((c.width * 8, c.height * 8), Image.NEAREST).save(f"/tmp/reveal_{name}.png")
    print(f"wrote /tmp/reveal_{name}.png")
PY
```

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/panel_map.py tests/test_panel_map.py
git commit -m "feat(panel-map): reveal calibration pattern (index + arrow + dot + underline)"
```

- [ ] **Step 7: Persona review gate (glyph legibility)**

Read the two preview PNGs (`/tmp/reveal_smallsign.png`, `/tmp/reveal_bigsign_rawchain.png`) and attach them to the persona dispatch:

- **Hobbyist:** "This is what `reveal` will paint on each panel (number + arrow + corner dot + underline). On a phone photo of a real wall, could you read each panel's number and tell its rotation? Is a rotated 6/9 safe given the underline? What's hard to read?"
- **PM:** "Is the calibration glyph set minimal-but-sufficient (the spec cut a per-panel hue as gold-plating)? Anything that won't survive a real-room photo and should change before hardware validation?"

If either says the glyphs won't read, change the encoding (bigger digits via a larger `scale` floor, thicker arrow) and re-run Steps 4–5. Record the legibility verdict — it feeds the Task 5 hardware spike.

---

## Task 3: `verify` — coherent + self-diagnosing full-canvas pattern

**Files:**
- Modify: `src/led_ticker/panel_map.py`
- Test: `tests/test_panel_map.py`

**Interfaces:**
- Consumes: `draw_index`, `draw_up_arrow`, `draw_corner_dot`, `draw_border` (Task 2).
- Produces:
  - `parse_remap_string(mapper: str) -> tuple[int, int, list[tuple[int, int, str]]]` — returns `(width, height, [(x, y, flag), ...])` in chain order. Raises `LayoutError` on a malformed string.
  - `paint_verify(canvas, *, mapper: str, cols: int, rows: int) -> None` — paint the coordinate grid + corner labels + a big up-arrow + a per-panel diagnostic overlay (each entry `k` paints index `k` + up-arrow + corner dot into its `(x, y)` cell so a wrong mapper self-identifies which panel is off).

- [ ] **Step 1: Write failing tests**

```python
# add to tests/test_panel_map.py
from led_ticker.panel_map import paint_verify, parse_remap_string


def test_parse_remap_round_trips_bigsign():
    w, h, entries = parse_remap_string(BIGSIGN_STRING)
    assert (w, h) == (256, 64)
    assert len(entries) == 8
    assert entries[0] == (192, 32, "n")
    assert entries[7] == (0, 0, "n")


def test_parse_remap_rejects_garbage():
    with pytest.raises(LayoutError):
        parse_remap_string("not a remap string")


def test_paint_verify_draws_per_panel_indices():
    c = HeadlessCanvas(width=256, height=64)
    paint_verify(c, mapper=BIGSIGN_STRING, cols=64, rows=32)
    # entry 8 sits at canvas (0,0); its index pixels live in that cell
    cell8 = any(
        c.get_pixel(x, y) != (0, 0, 0) for x in range(0, 64) for y in range(0, 32)
    )
    # entry 1 sits at (192,32); its index pixels live in that cell
    cell1 = any(
        c.get_pixel(x, y) != (0, 0, 0)
        for x in range(192, 256)
        for y in range(32, 64)
    )
    assert cell8 and cell1
    # the two cells render different indices (8 vs 1)
    region8 = [c.get_pixel(x, y) for x in range(0, 64) for y in range(0, 32)]
    region1 = [c.get_pixel(x, y) for x in range(192, 256) for y in range(32, 64)]
    assert region8 != region1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_panel_map.py -k "verify or remap" -v`
Expected: FAIL with `ImportError: cannot import name 'paint_verify'`

- [ ] **Step 3: Implement `parse_remap_string` + `paint_verify` (append to `src/led_ticker/panel_map.py`)**

```python
def parse_remap_string(mapper):
    """Parse 'Remap:W,H|x,yORIENT|...' into (width, height, entries)."""
    if not mapper.startswith("Remap:") or "|" not in mapper:
        raise LayoutError(
            f"{mapper!r} is not a Remap string (expected "
            "'Remap:WIDTH,HEIGHT|x,yORIENT|...')."
        )
    header, *cells = mapper[len("Remap:") :].split("|")
    try:
        width, height = (int(v) for v in header.split(","))
    except ValueError as exc:
        raise LayoutError(f"Bad Remap header {header!r}: {exc}") from exc
    entries: list[tuple[int, int, str]] = []
    for cell in cells:
        flag = cell[-1].lower()
        if flag not in VALID_FLAGS:
            raise LayoutError(f"Bad orientation flag in {cell!r}.")
        try:
            x, y = (int(v) for v in cell[:-1].split(","))
        except ValueError as exc:
            raise LayoutError(f"Bad coordinates in {cell!r}: {exc}") from exc
        entries.append((x, y, flag))
    return width, height, entries


def paint_verify(canvas, *, mapper, cols, rows):
    """Paint a coherent, self-diagnosing pattern on the final canvas.

    Global aids: faint panel-seam grid, corner labels, one big up-arrow.
    Per-panel overlay: each chain entry k paints its index + up-arrow + dot
    into its (x, y) cell, so a wrong mapper shows WHICH panel is misplaced.
    """
    width, height, entries = parse_remap_string(mapper)
    canvas.Fill(0, 0, 0)

    # faint seam grid every cols/rows pixels
    for x in range(0, width, cols):
        for y in range(height):
            canvas.SetPixel(x, y, 0, 40, 40)
    for y in range(0, height, rows):
        for x in range(width):
            canvas.SetPixel(x, y, 0, 40, 40)

    # corner labels
    draw_index(canvas, 0, 1, 1, scale=1, r=120, g=120, b=255)  # 0 marks origin
    # big up-arrow spanning the canvas
    draw_up_arrow(canvas, width // 2, 2, height - 4, 60, 60, 60)

    # per-panel diagnostic overlay
    scale = max(1, min(cols // 8, rows // 8))
    for k, (x, y, _flag) in enumerate(entries, start=1):
        draw_border(canvas, x, y, cols, rows, 0, 80, 80)
        draw_corner_dot(canvas, x + 1, y + 1, max(2, scale), 255, 0, 0)
        draw_index(canvas, k, x + 3, y + 2, scale=scale)
        draw_up_arrow(canvas, x + cols - max(4, scale * 2), y + 2, rows - 4,
                      255, 255, 0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_panel_map.py -k "verify or remap" -v`
Expected: PASS

- [ ] **Step 5: Run the full module test + lint**

Run: `uv run pytest tests/test_panel_map.py -v && uv run --extra dev ruff check src/led_ticker/panel_map.py tests/test_panel_map.py`
Expected: all PASS, no lint errors.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/panel_map.py tests/test_panel_map.py
git commit -m "feat(panel-map): self-diagnosing verify pattern (per-panel overlay)"
```

- [ ] **Step 7: Persona review gate (does verify close the loop?)**

- **Hobbyist:** "When my mapper is wrong, `verify` paints the whole wall, and each panel shows the number it *should* be. If panel 5 is rotated wrong, I'd see a tilted arrow on it. Does that tell me which one to fix without re-typing my whole grid? What would still leave me guessing?"
- **PM:** "The spec's #1 review fix was making `verify` diagnostic, not pass/fail, so the guess-loop isn't merely relocated onto the ASCII grid. Does this per-panel overlay deliver that? Anything missing?"

Address blocking concerns; the e/w *visual* correctness is deliberately deferred to Task 5 (hardware).

---

## Task 4: CLI script + Make targets

**Files:**
- Create: `scripts/panel_map.py`
- Modify: `Makefile`
- Test: `tests/test_panel_map.py` (CLI smoke via subprocess for `derive`)

**Interfaces:**
- Consumes: `derive_remap_string`, `paint_reveal`, `paint_verify` (Tasks 1–3); `load_config`, `build_frame_from_config` (existing).
- Produces: a `python scripts/panel_map.py {reveal,derive,verify}` CLI.

- [ ] **Step 1: Write a failing CLI smoke test for `derive` (no hardware)**

```python
# add to tests/test_panel_map.py
import subprocess
import sys


def test_cli_derive_from_stdin_prints_string(tmp_path):
    # derive reads geometry from --config [display]; use the bundled bigsign example
    proc = subprocess.run(
        [
            sys.executable, "scripts/panel_map.py", "derive",
            "--config", "config/config.bigsign.example.toml",
        ],
        input=BIGSIGN_GRID,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert BIGSIGN_STRING in proc.stdout
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_panel_map.py::test_cli_derive_from_stdin_prints_string -v`
Expected: FAIL (script doesn't exist → non-zero return / `No such file`).

- [ ] **Step 3: Implement `scripts/panel_map.py`**

```python
"""panel-map: derive and visually verify a pixel_mapper_config Remap string.

Three subcommands:
  reveal  Paint each panel with its chain index + orientation markers, with
          NO mapper applied, so a photo reveals the physical layout. (hardware)
  derive  Turn the transcribed ASCII grid into a Remap string. (no hardware)
  verify  Apply a candidate mapper and paint a coherent, self-diagnosing
          pattern so a wrong mapper is visibly (and per-panel) obvious. (hardware)

See docs.ledticker.dev/tools/panel-map/ for the full workflow. Run
panel-test FIRST to rule out the hardware layer (RGB sequence / FM6126A).
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
import time
from pathlib import Path

from led_ticker.app.factories import build_frame_from_config
from led_ticker.config import load_config
from led_ticker.panel_map import (
    LayoutError,
    derive_remap_string,
    paint_reveal,
    paint_verify,
)


def _hold_loop(frame, canvas, paint, hold):
    """Repaint + swap at `hold` cadence until Ctrl-C, then clear."""
    try:
        while True:
            paint(canvas)
            canvas = frame.matrix.SwapOnVSync(canvas)  # constraint #1
            time.sleep(hold)
    except KeyboardInterrupt:
        logging.info("Interrupted — clearing panel.")
        canvas.Fill(0, 0, 0)
        canvas = frame.matrix.SwapOnVSync(canvas)
        return 0


def _cmd_reveal(args, display):
    # Force identity mapper so the canvas is the raw data chain.
    d = dataclasses.replace(display, pixel_mapper_config="")
    frame = build_frame_from_config(d)
    canvas = frame.get_clean_canvas()
    logging.info(
        "reveal: %d panels (chain_length=%d parallel=%d), no mapper. "
        "Photograph the wall; transcribe the grid; run `derive`.",
        d.chain_length * d.parallel, d.chain_length, d.parallel,
    )

    def paint(c):
        paint_reveal(
            c, cols=d.cols, rows=d.rows,
            chain_length=d.chain_length, parallel=d.parallel,
        )

    return _hold_loop(frame, canvas, paint, args.hold)


def _cmd_derive(args, display):
    text = args.layout.read_text() if args.layout else sys.stdin.read()
    try:
        out = derive_remap_string(
            text, cols=display.cols, rows=display.rows,
            chain_length=display.chain_length, parallel=display.parallel,
        )
    except LayoutError as exc:
        logging.error("%s", exc)
        return 2
    n_cells = out.count("|")
    expected = display.chain_length * display.parallel
    if n_cells != expected:
        logging.warning(
            "Grid has %d panels but [display] expects %d "
            "(chain_length×parallel). Deriving for the grid as typed.",
            n_cells, expected,
        )
    print(out)  # the string on stdout, pipeable
    return 0


def _cmd_verify(args, display):
    mapper = args.mapper or display.pixel_mapper_config
    if not mapper:
        logging.error(
            "No mapper to verify. Pass --mapper 'Remap:...' or set "
            "pixel_mapper_config in the config."
        )
        return 2
    frame = build_frame_from_config(dataclasses.replace(
        display, pixel_mapper_config=mapper))
    canvas = frame.get_clean_canvas()
    logging.info("verify: applying mapper %r", mapper)

    def paint(c):
        paint_verify(c, mapper=mapper, cols=display.cols, rows=display.rows)

    return _hold_loop(frame, canvas, paint, args.hold)


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path,
                   default=Path("config/config.bigsign.example.toml"),
                   help="Config TOML; only [display] geometry is used.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("reveal", help="Paint chain index + orientation, no mapper.")
    pr.add_argument("--hold", type=float, default=2.0)
    pr.set_defaults(func=_cmd_reveal)

    pd = sub.add_parser("derive", help="ASCII grid (stdin or --layout) -> Remap string.")
    pd.add_argument("--layout", type=Path, default=None,
                    help="File with the transcribed grid. Omit to read stdin.")
    pd.set_defaults(func=_cmd_derive)

    pv = sub.add_parser("verify", help="Apply a candidate mapper, paint a diagnostic pattern.")
    pv.add_argument("--hold", type=float, default=2.0)
    pv.add_argument("--mapper", default=None,
                    help="Remap string to verify. Omit to use the config's.")
    pv.set_defaults(func=_cmd_verify)
    return p.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    args = _parse_args()
    config = load_config(args.config)
    for w in config._coerce_warnings:
        logging.warning("config coerce: %s", w.message)
    return args.func(args, config.display)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the smoke test to verify it passes**

Run: `uv run pytest tests/test_panel_map.py::test_cli_derive_from_stdin_prints_string -v`
Expected: PASS

- [ ] **Step 5: Add Make targets**

In `Makefile`, alongside the `panel-test` targets, add (match the existing `CONFIG`/`HOLD` override + `-docker` style verbatim — open the Makefile, copy the `panel-test` block, and adapt):

```makefile
panel-map-reveal:
	uv run python scripts/panel_map.py reveal --config $(CONFIG) --hold $(HOLD)

panel-map-verify:
	uv run python scripts/panel_map.py verify --config $(CONFIG) --hold $(HOLD)

panel-map-derive:
	uv run python scripts/panel_map.py derive --config $(CONFIG) --layout $(LAYOUT)
```

Reuse the existing `CONFIG`/`HOLD` defaults the `panel-test` targets already define (do NOT redefine them); add a `LAYOUT ?=` default near them. Add `panel-map-reveal-docker` / `panel-map-verify-docker` by copying the `panel-test-docker` recipe and swapping the script invocation. Verify the block: `make -n panel-map-derive CONFIG=config/config.bigsign.example.toml LAYOUT=/tmp/grid.txt`.

- [ ] **Step 6: Manual CLI exercise (headless, no hardware)**

Run reveal/verify against the headless backend to confirm wiring (set backend via a scratch config or the `LED_TICKER` headless path the repo already uses for previews):

```bash
printf '8n 6n 4n 2n\n7n 5n 3n 1n\n' > /tmp/grid.txt
uv run python scripts/panel_map.py derive --config config/config.bigsign.example.toml --layout /tmp/grid.txt
# expect: Remap:256,64|192,32n|192,0n|128,32n|128,0n|64,32n|64,0n|0,32n|0,0n
```

- [ ] **Step 7: Commit**

```bash
git add scripts/panel_map.py Makefile tests/test_panel_map.py
git commit -m "feat(panel-map): CLI subcommands + make targets"
```

- [ ] **Step 8: Persona review gate (end-to-end CLI flow)**

- **Hobbyist:** "Walk the whole flow as you'd run it over SSH: `panel-map reveal` → photograph → write the grid into a file → `panel-map derive --layout` → paste into config → `panel-map verify`. Where do you stumble? Is `--layout FILE` clearly the easy path vs stdin? Is the Ctrl-C behavior reassuring?"
- **PM:** "Does the CLI match `panel-test`'s conventions so existing users have zero new mental model? Is anything under- or over-built?"

Address blocking concerns before docs.

---

## Task 5: Hardware validation spike (maintainer-run) — pins `e`/`w`, confirms legibility

> This task needs real panels and CANNOT be done by an agent. It is the spec's "orientation spike." It gates the docs legend table (Task 6). The maintainer (James) runs it; the agent's job is to capture the results into the spec/plan.

**Files:**
- Modify: `docs/superpowers/specs/2026-06-29-panel-map-helper-design.md` (fill in the pinned `e`/`w` legend + legibility verdict).

- [ ] **Step 1: Run `panel-test` first**, confirm solid colors render cleanly (rules out the hardware layer).
- [ ] **Step 2: Run `make panel-map-reveal CONFIG=<your sign>`**, photograph the wall. Confirm every panel's index, arrow, dot, and underline are legible in the photo at the real cell size. If not, file a glyph-encoding fix against Task 2.
- [ ] **Step 3: Physically rotate one panel 90° one way, re-run reveal**, note what the arrow/dot look like. Derive a string with that panel flagged `e`; `make panel-map-verify --mapper ...`. If it lands wrong, the correct flag is `w`. Record the **observed-rotation → flag** mapping for both 90° directions.
- [ ] **Step 4: Capture a clean reveal photo** for the docs page (or confirm the placeholder plan if hardware/time is short — do not block the tool on the photo).
- [ ] **Step 5: Write the pinned `e`/`w` legend and the legibility verdict into the spec**, then commit:

```bash
git add docs/superpowers/specs/2026-06-29-panel-map-helper-design.md
git commit -m "docs(spec): pin e/w orientation mapping from hardware spike"
```

---

## Task 6: Docs page + cross-links + inline intercept

**Files:**
- Create: `docs/site/src/content/docs/tools/panel-map.mdx`
- Modify: `docs/site/src/content/docs/tools/panel-test.mdx`, `docs/site/src/content/docs/hardware/building-your-own.mdx`, `docs/site/src/content/docs/hardware/bigsign.mdx`, `docs/site/src/content/docs/reference/cli.mdx`

**Constraint:** follow `docs/DOCS-STYLE.md`. The `e`/`w` legend MUST be the **pinned** values from Task 5 — do not ship "e or w, unsure."

- [ ] **Step 1: Write `tools/panel-map.mdx`** mirroring `tools/panel-test.mdx`'s structure, including, in order:
  1. A frontmatter `title`/`description`.
  2. **Prerequisite callout: run `panel-test` first** (link `/tools/panel-test/`).
  3. The **bigsign worked example** end-to-end: the `reveal` photo (or labeled placeholder) → the typed grid `8n 6n 4n 2n` / `7n 5n 3n 1n` → `derive` → the resulting string → `verify`.
  4. Per-subcommand sections (`reveal`/`derive`/`verify`) with the `make` targets and `--config`/`--hold`/`--layout`/`--mapper` flags.
  5. The **orientation legend table** (pinned `e`/`w`) + the **flip-and-retry fallback** for rotated panels.
  6. The **plain-language transcription instruction** ("write it the way it hangs, top row first, left to right"), **photo discipline**, double-digit note.
  7. The **scope-limitation honesty block** (`derive` solves uniform n/s grids; e/w footprint-swaps get best-guess + verify).
  8. `<RelatedPages slugs={["tools/panel-test", "hardware/bigsign", "hardware/building-your-own", "reference/cli"]} />`.

- [ ] **Step 2: Add the inline intercept** in `hardware/building-your-own.mdx` at the exact paragraph that mentions editing `pixel_mapper_config`: a sentence "Don't hand-write this string — run [`panel-map`](/tools/panel-map/) to derive it." Add cross-links + RelatedPages entries in `panel-test.mdx`, `bigsign.mdx`, `reference/cli.mdx`.

- [ ] **Step 3: Lint the docs.** The repo's pre-commit runs `docs-lint (prettier + astro check)` on `.mdx` changes — let it run on commit (Step 4). To run it ahead of the commit: `uv run pre-commit run docs-lint --files docs/site/src/content/docs/tools/panel-map.mdx`. Expected: passes (fix any MDX/prettier errors it reports).

- [ ] **Step 4: Commit**

```bash
git add docs/site/src/content/docs/tools/panel-map.mdx \
        docs/site/src/content/docs/tools/panel-test.mdx \
        docs/site/src/content/docs/hardware/building-your-own.mdx \
        docs/site/src/content/docs/hardware/bigsign.mdx \
        docs/site/src/content/docs/reference/cli.mdx
git commit -m "docs(panel-map): tool page, worked example, inline intercept + cross-links"
```

- [ ] **Step 5: Persona review gate (docs are half the product)** — heaviest review:

- **Hobbyist:** "Read this page cold as the maker with garbled panels. Do you know, step by step, what to DO? Is the panel-test-first pointer there? Could you transcribe your wall from the worked example? Is the e/w table actionable (no 'unsure')? Does anything make you want to give up and go back to guessing?"
- **PM:** "Audit against DOCS-STYLE and the spec. Is the value clear, the discoverability intercept in place (building-your-own), the scope honest? Is this page good enough to be the tool's front door?"

Address all blocking concerns; re-run Step 3; amend the commit.

---

## Self-Review (completed during planning)

- **Spec coverage:** reveal (Task 2) ✓, derive (Task 1) ✓, verify + per-panel diagnostic (Task 3) ✓, CLI + make targets + `-docker` (Task 4) ✓, panel-test-first + photo discipline + transcription instruction + plain-language errors + flip-and-retry (Tasks 2/4/6) ✓, golden tripwire (Task 1) ✓, e/w spike + legibility (Task 5) ✓, docs + worked example + inline intercept + cross-links (Task 6) ✓, per-panel hue cut ✓ (never built). The `DisplayConfig→LedFrame` helper "open detail" is resolved: `build_frame_from_config(dataclasses.replace(display, ...))` IS the single source, so no refactor is needed (YAGNI).
- **Persona reviews:** baked into Tasks 1, 2, 3, 4, 6 as explicit gate steps; Task 5 is itself the hobbyist's real-world hardware test.
- **Type consistency:** `derive_remap_string`, `parse_layout`, `parse_remap_string`, `paint_reveal`, `paint_verify`, `draw_index` signatures are consistent across tasks and the CLI imports.

## Follow-ups (non-blocking, fill in during execution)

- _(record persona non-blocking suggestions here as tasks complete)_
- Parallel chains (`parallel > 1`) slot/ordering is implemented row-major (`k = j*chain_length + i + 1`); the reference builds are `parallel = 1`, so this path is untested on hardware — note in docs and revisit if a `parallel > 1` builder appears.

---

## RESUME STATE (parked 2026-06-29 — credits)

SDD execution is paused mid-Task-3. Ledger: `.superpowers/sdd/progress.md` (gitignored scratch — this committed section is the durable copy). Worktree `/Users/james/projects/github/jamesawesome/led-ticker-panel-map`, branch `feat/panel-map-helper`.

**Done & reviewed clean (PM + hobbyist + code-review gates all addressed):**
- **Task 1** — derive logic. Commits `f4f638eb..7ccd08c5`. (fix: dropped `from __future__`, plainer error messages)
- **Task 2** — reveal calibration paint. Commits `..a14c6cb0`. (fix: solid bounded arrow, 3px corner dot, full-width underline, arrow-bleed regression test; previews `/tmp/reveal_*.png` looked good)

**Task 3 — verify paint: IMPLEMENTED (commit `f13bfae8`), reviews done, FIX PENDING (not yet dispatched).** Resume by dispatching ONE fix subagent (sonnet, worktree-discipline prompt) for, in `src/led_ticker/panel_map.py` + `tests/test_panel_map.py`:
1. **Important — port the bounded arrow.** `paint_verify`'s per-panel `draw_up_arrow` uses the unbounded default `head_half`, re-introducing the slot-bleed fixed for `paint_reveal` in Task 2 (≈6px into the neighbor cell at bigsign). Reuse `paint_reveal`'s bounded placement; extract a shared helper so the two can't drift (also satisfies the DRY-`scale` minor).
2. **Minor — `_panel_scale(cols, rows)` helper** for the `max(1, min(cols//8, rows//8))` formula duplicated in both paint fns.
3. **Minor — `parse_remap_string` empty trailing cell.** `"Remap:256,64|"` → `cells=[""]` → `cell[-1]` raises `IndexError`; should raise `LayoutError`. Add a guard + a test.
4. **Tests — strengthen verify coverage:** a verify no-bleed regression (no arrow color in the next cell's leftmost columns), a pixel-coordinate assertion (a specific index digit lands in its specific cell), and bad-flag / bad-coord `parse_remap_string` cases.
5. Keep `canvas.Fill` (adjudicated NOT a defect — matches `panel_color_test.py`). Do NOT add `from __future__`.

**DESIGN DECISION (locked) — verify rotation cue = "Transform + docs" (NOT a flag label).** Rationale: `verify` paints the logical canvas; on real hardware the rgbmatrix mapper rotates each panel's content per its flag, so a wrong flag makes that panel's digit/arrow/dot appear rotated on the wall — the rotation diagnostic is delivered by the transform (invisible in headless tests). Do NOT draw a flag-rotated arrow (would double-rotate) and do NOT add an n/s/e/w/x letter font. Two downstream requirements:
- **Task 6 docs** must explain how to *read* verify: a panel whose number/arrow/dot looks rotated has the wrong flag → use the flip-and-retry fallback.
- **Task 5 hardware spike** add a check: deliberately set one wrong flag, confirm `verify` shows that one panel rotated.

**Remaining tasks:** Task 3 fix (above) → Task 4 (CLI + Make targets) → Task 5 (hardware spike — **needs James + real panels**; pins `e`/`w`, glyph legibility, reveal photo) → Task 6 (docs page + inline intercept + cross-links). Then final whole-branch review + finishing-a-development-branch.

**Resume procedure:** re-read this section and the ledger; `git log --oneline` to confirm HEAD is `f13bfae8`; dispatch the Task 3 fix; continue the per-task implement → (code + PM + hobbyist) review → fix loop. Base for the Task 3-fix review package is `a14c6cb0` (the Task-3 base), through the new fix HEAD.
