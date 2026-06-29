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
