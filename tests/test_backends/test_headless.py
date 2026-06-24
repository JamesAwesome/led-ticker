from led_ticker.backends import Backend, get_backend_class
from led_ticker.backends.headless import HeadlessBackend, HeadlessCanvas


def test_registered_as_headless():
    assert get_backend_class("headless") is HeadlessBackend


def test_satisfies_backend_protocol():
    assert isinstance(HeadlessBackend(160, 16), Backend)


def test_canvas_full_method_surface():
    c = HeadlessCanvas(width=8, height=8)
    c.SetPixel(1, 1, 10, 20, 30)
    assert c.get_pixel(1, 1) == (10, 20, 30)
    c.SubFill(0, 0, 2, 2, 5, 5, 5)
    assert c.get_pixel(0, 0) == (5, 5, 5)
    c.Fill(9, 9, 9)
    assert c.count_nonzero() == 64
    c.Clear()
    assert c.count_nonzero() == 0


def test_swap_returns_a_different_canvas_object():
    # Constraints #1/#8: the returned back-buffer is NOT the one handed in.
    b = HeadlessBackend(160, 16)
    b.setup()
    front = b.create_canvas()
    back = b.swap(front)
    assert back is not front


def test_u_mapper_reshapes_canvas():
    b = HeadlessBackend(64 * 8, 32, pixel_mapper_config="U-mapper")
    b.setup()
    c = b.create_canvas()
    # U-mapper folds the chain in half: doubles height, halves width.
    assert (c.width, c.height) == (64 * 8 // 2, 32 * 2)


def test_setpixel_clips_out_of_bounds():
    c = HeadlessCanvas(width=4, height=4)
    c.SetPixel(99, 99, 1, 2, 3)  # silently ignored
    assert c.count_nonzero() == 0


def test_setimage_paints_with_offset_and_alpha_flatten():
    from PIL import Image

    img = Image.new("RGBA", (2, 1))
    img.putpixel((0, 0), (10, 20, 30, 255))  # opaque -> paints RGB
    img.putpixel((1, 0), (99, 99, 99, 0))  # alpha 0 -> flattens to black
    c = HeadlessCanvas(width=8, height=8)
    c.SetImage(img, offset_x=2, offset_y=3)
    assert c.get_pixel(2, 3) == (10, 20, 30)
    assert c.get_pixel(3, 3) == (0, 0, 0)
