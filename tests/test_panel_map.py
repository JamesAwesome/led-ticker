import subprocess
import sys

import pytest

from led_ticker.backends.headless import HeadlessCanvas
from led_ticker.panel_map import (
    DIGITS_3x5,
    LayoutError,
    derive_remap_string,
    draw_index,
    paint_reveal,
    paint_verify,
    parse_layout,
    parse_remap_string,
)

BIGSIGN_GRID = "8n 6n 4n 2n\n7n 5n 3n 1n"
BIGSIGN_STRING = "Remap:256,64|192,32n|192,0n|128,32n|128,0n|64,32n|64,0n|0,32n|0,0n"


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
    out = derive_remap_string("1s 2e", cols=64, rows=32, chain_length=2, parallel=1)
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


def test_flag_only_token_missing_panel_number():
    with pytest.raises(LayoutError, match="missing its panel number"):
        parse_layout("s 2n")


# ---------------------------------------------------------------------------
# Task 2: reveal calibration pattern
# ---------------------------------------------------------------------------


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


def test_arrow_does_not_bleed_across_slot_boundary():
    """Arrow must be bounded within its slot and must have a shaft ≥ 2 px wide.

    Regression for the original 1-px-diagonal arrowhead that spread
    ``height // 2`` px each side, overflowing into the adjacent slot.
    """
    c = HeadlessCanvas(width=160, height=16)
    paint_reveal(c, cols=32, rows=16, chain_length=5, parallel=1)
    YELLOW = (255, 255, 0)
    # Interior slot boundary: slot 0 owns x=0..31; slot 1 owns x=32..63.
    # No yellow pixel from slot 0's arrow should appear at x=32 or x=33.
    for boundary_x in (32, 33):
        for y in range(16):
            assert c.get_pixel(boundary_x, y) != YELLOW, (
                f"yellow arrow bleeds into slot 1 at x={boundary_x}, y={y}"
            )
    # Arrow shaft must be at least 2 px wide somewhere within slot 0.
    max_yellow_in_row = max(
        sum(1 for x in range(32) if c.get_pixel(x, y) == YELLOW) for y in range(16)
    )
    assert max_yellow_in_row >= 2, "arrow shaft should be >= 2 px wide in some row"


# ---------------------------------------------------------------------------
# Task 3: verify calibration pattern
# ---------------------------------------------------------------------------


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
        c.get_pixel(x, y) != (0, 0, 0) for x in range(192, 256) for y in range(32, 64)
    )
    assert cell8 and cell1
    # the two cells render different indices (8 vs 1)
    region8 = [c.get_pixel(x, y) for x in range(0, 64) for y in range(0, 32)]
    region1 = [c.get_pixel(x, y) for x in range(192, 256) for y in range(32, 64)]
    assert region8 != region1


def test_paint_verify_index_digit_within_cell():
    """Entry 8 sits at canvas (0,0); its "8" digit must light pixels there."""
    c = HeadlessCanvas(width=256, height=64)
    paint_verify(c, mapper=BIGSIGN_STRING, cols=64, rows=32)
    # index drawn at (x+3, y+2) = (3, 2) with scale=4.
    # Digit "8" row 0 col 0 = "1" → the 4×4 block starting at (3,2) is white.
    assert c.get_pixel(3, 2) == (255, 255, 255), (
        "index 8 digit pixel not white at (3,2)"
    )
    # Sanity: the pixel is inside entry 8's cell [0,64)×[0,32)
    assert 0 <= 3 < 64 and 0 <= 2 < 32


def test_paint_verify_arrow_does_not_bleed_across_panel_boundary():
    """Per-panel arrow must be bounded within its cell.

    Regression for the old unbounded call: at bigsign geometry (cols=64,
    rows=32) the old cx=x+cols-max(4,scale*2)=x+56 with default
    head_half=14 spreads the arrowhead to x+56+13=x+69, 6 px into the
    adjacent cell.  With the fix, rightmost pixel ≤ x+62.

    Entry 5 occupies x=64..127, y=32..63.  Neither x=127 (the slot's own
    right border, painted teal) nor x=128 (start of entry 3's cell, also
    teal) should be yellow from entry 5's arrow.  Entry 3's own arrow is
    centred at x=176, far from x=127..128.
    """
    c = HeadlessCanvas(width=256, height=64)
    paint_verify(c, mapper=BIGSIGN_STRING, cols=64, rows=32)
    YELLOW = (255, 255, 0)
    for check_x in (127, 128):
        for y in range(32, 64):
            assert c.get_pixel(check_x, y) != YELLOW, (
                f"yellow arrow bleeds at x={check_x}, y={y}"
            )


def test_parse_remap_bad_flag_raises_layout_error():
    with pytest.raises(LayoutError, match="orientation"):
        parse_remap_string("Remap:64,32|0,0z")


def test_parse_remap_bad_coordinates_raises_layout_error():
    with pytest.raises(LayoutError, match="coordinates"):
        parse_remap_string("Remap:64,32|abc,defn")


def test_parse_remap_empty_trailing_cell_raises_layout_error():
    """Trailing pipe must raise LayoutError, not IndexError."""
    with pytest.raises(LayoutError):
        parse_remap_string("Remap:256,64|")


# ---------------------------------------------------------------------------
# Task 4: CLI smoke test (no hardware)
# ---------------------------------------------------------------------------


def test_cli_derive_from_stdin_prints_string(tmp_path):
    # derive reads geometry from --config [display]; use the bundled bigsign example
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/panel_map.py",
            "derive",
            "--config",
            "config/config.bigsign.example.toml",
        ],
        input=BIGSIGN_GRID,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert BIGSIGN_STRING in proc.stdout
