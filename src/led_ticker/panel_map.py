"""panel-map: derive and verify a pixel_mapper_config Remap string.

Pure logic (grid parsing, string derivation, calibration-pattern painting)
lives here so it can be unit-tested with no hardware. The CLI in
scripts/panel_map.py wires this to a real LedFrame.

See docs.ledticker.dev/tools/panel-map/ for the user-facing workflow and
docs/superpowers/specs/2026-06-29-panel-map-helper-design.md for the design.
"""

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
            if not num and flag in VALID_FLAGS:
                raise LayoutError(
                    f"'{token}' is missing its panel number — write the number "
                    f"then the flag, e.g. '3{flag}', not '{token}'."
                )
            if flag not in VALID_FLAGS or not num.isdigit():
                raise LayoutError(
                    f"'{token}' isn't a valid cell. Each cell is a panel "
                    f"number followed by one of {', '.join(VALID_FLAGS)} "
                    "(e.g. '3s'). Use n=upright, s=upside-down, "
                    "e/w=rotated 90°, x=skip."
                )
            cells.append((int(num), flag))
        rows.append(cells)
    if not rows:
        raise LayoutError("Empty layout — no panels to map.")
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
                    f"You listed panel {idx} twice. Each panel number must "
                    "appear exactly once in your grid."
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


# ---------------------------------------------------------------------------
# Calibration-pattern drawing helpers
# ---------------------------------------------------------------------------

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
                canvas,
                ox + cols - max(4, scale * 2),
                oy + 2,
                rows - 4,
                255,
                255,
                0,
            )
