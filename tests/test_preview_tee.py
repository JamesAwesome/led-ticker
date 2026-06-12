"""PreviewTee: hardware forwarding, shadow mirroring, the spine invariant."""

from rgbmatrix import RGBMatrix, RGBMatrixOptions

from led_ticker.preview import PreviewTee


def _hw_canvas(width=32, height=16):
    options = RGBMatrixOptions()
    options.rows = height
    options.cols = width
    options.chain_length = 1
    matrix = RGBMatrix(options=options)
    canvas = matrix.CreateFrameCanvas()
    canvas.Clear()
    return canvas


def _tee(tmp_path, width=32, height=16):
    return PreviewTee(
        hw=_hw_canvas(width, height),
        width=width,
        height=height,
        frame_path=tmp_path / "preview.bin",
    )


def test_forwards_setpixel_to_hardware(tmp_path):
    tee = _tee(tmp_path)
    tee.SetPixel(3, 4, 10, 20, 30)
    assert tee._hw._pixels[(3, 4)] == (10, 20, 30)


def test_mirror_off_means_zero_shadow_writes(tmp_path):
    tee = _tee(tmp_path)
    tee.SetPixel(3, 4, 10, 20, 30)
    assert bytes(tee._shadow) == bytes(32 * 16 * 3)  # untouched


def test_mirror_on_shadows_setpixel(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.SetPixel(3, 4, 10, 20, 30)
    i = (4 * 32 + 3) * 3
    assert tuple(tee._shadow[i : i + 3]) == (10, 20, 30)
    assert tee._hw._pixels[(3, 4)] == (10, 20, 30)  # forward still happened


def test_out_of_bounds_setpixel_clips_in_shadow(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.SetPixel(-1, 0, 1, 2, 3)
    tee.SetPixel(32, 0, 1, 2, 3)
    tee.SetPixel(0, 16, 1, 2, 3)
    assert bytes(tee._shadow) == bytes(32 * 16 * 3)  # no corruption, no raise


def test_fill_and_clear_mirror_in_bulk(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.Fill(7, 8, 9)
    assert bytes(tee._shadow) == bytes((7, 8, 9)) * (32 * 16)
    tee.Clear()
    assert bytes(tee._shadow) == bytes(32 * 16 * 3)


def test_width_height_exposed(tmp_path):
    tee = _tee(tmp_path)
    assert (tee.width, tee.height) == (32, 16)


def test_spine_invariant_shadow_failure_never_blocks_hardware(tmp_path):
    """A broken shadow disables mirroring; the panel keeps receiving pixels."""
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee._shadow = None  # sabotage: every shadow write now raises
    tee.SetPixel(1, 1, 5, 5, 5)  # must NOT raise
    assert tee._hw._pixels[(1, 1)] == (5, 5, 5)  # hardware got it anyway
    assert tee.mirror is False  # mirroring self-disabled
    tee.Fill(1, 2, 3)  # subsequent calls: plain forwards, no raise
    assert tee._hw._pixels[(0, 0)] == (1, 2, 3)


def test_set_watched_false_unlinks_frame_file(tmp_path):
    tee = _tee(tmp_path)
    (tmp_path / "preview.bin").write_bytes(b"old")
    tee.set_watched(True)
    tee.set_watched(False)
    assert not (tmp_path / "preview.bin").exists()
    tee.set_watched(False)  # idempotent, no raise on missing file
