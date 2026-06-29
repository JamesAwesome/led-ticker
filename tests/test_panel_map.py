import pytest

from led_ticker.backends.headless import HeadlessCanvas
from led_ticker.panel_map import (
    DIGITS_3x5,
    LayoutError,
    derive_remap_string,
    draw_index,
    paint_reveal,
    parse_layout,
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
