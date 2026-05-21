"""Tests for led_ticker._compat module."""

from led_ticker._compat import RGBMatrix, RGBMatrixOptions, graphics


def test_graphics_color():
    color = graphics.Color(255, 0, 0)
    assert color.red == 255
    assert color.green == 0
    assert color.blue == 0


def test_graphics_font_loads_bdf():
    import os

    font = graphics.Font()
    font_dir = os.path.join(
        os.path.dirname(__file__), "..", "src", "led_ticker", "fonts"
    )
    font.LoadFont(os.path.join(font_dir, "6x12.bdf"))
    # Space character should be 6 pixels wide in 6x12 font
    assert font.CharacterWidth(ord(" ")) == 6


def test_graphics_draw_text():
    font = graphics.Font()
    import os

    font_dir = os.path.join(
        os.path.dirname(__file__), "..", "src", "led_ticker", "fonts"
    )
    font.LoadFont(os.path.join(font_dir, "6x12.bdf"))
    color = graphics.Color(255, 255, 255)

    width = graphics.DrawText(None, font, 0, 12, color, "hello")
    assert width == 30  # 5 chars * 6px


def test_rgbmatrix_stub():
    opts = RGBMatrixOptions()
    opts.cols = 32
    opts.chain_length = 5
    matrix = RGBMatrix(options=opts)
    canvas = matrix.CreateFrameCanvas()
    assert canvas.width == 160  # 32 * 5
