"""Tests for shadow canvas and compositing functions."""

from led_ticker.shadow_canvas import (
    ShadowCanvas,
    composite_curtain,
    composite_dissolve,
    composite_split,
    composite_wipe,
)


class TestShadowCanvas:
    def test_initial_pixels_are_black(self):
        sc = ShadowCanvas(10, 10)
        assert sc.get_pixel(0, 0) == (0, 0, 0)
        assert sc.get_pixel(9, 9) == (0, 0, 0)

    def test_set_and_get_pixel(self):
        sc = ShadowCanvas(10, 10)
        sc.SetPixel(5, 5, 255, 0, 0)
        assert sc.get_pixel(5, 5) == (255, 0, 0)

    def test_clear_resets_pixels(self):
        sc = ShadowCanvas(10, 10)
        sc.SetPixel(5, 5, 255, 0, 0)
        sc.Clear()
        assert sc.get_pixel(5, 5) == (0, 0, 0)

    def test_fill(self):
        sc = ShadowCanvas(4, 4)
        sc.Fill(0, 255, 0)
        for y in range(4):
            for x in range(4):
                assert sc.get_pixel(x, y) == (0, 255, 0)

    def test_out_of_bounds_ignored(self):
        sc = ShadowCanvas(10, 10)
        sc.SetPixel(-1, 0, 255, 0, 0)  # no crash
        sc.SetPixel(10, 0, 255, 0, 0)  # no crash
        assert sc.get_pixel(-1, 0) == (0, 0, 0)

    def test_dimensions(self):
        sc = ShadowCanvas(160, 16)
        assert sc.width == 160
        assert sc.height == 16


class TestCompositeWipe:
    def test_wipe_left_at_zero(self):
        """At boundary=0, all pixels come from old."""
        old = ShadowCanvas(10, 2)
        new = ShadowCanvas(10, 2)
        old.Fill(255, 0, 0)
        new.Fill(0, 255, 0)
        canvas = ShadowCanvas(10, 2)

        composite_wipe(old, new, 0, canvas, "left")
        assert canvas.get_pixel(0, 0) == (255, 0, 0)
        assert canvas.get_pixel(9, 0) == (255, 0, 0)

    def test_wipe_left_at_full(self):
        """At boundary=width, all pixels come from new."""
        old = ShadowCanvas(10, 2)
        new = ShadowCanvas(10, 2)
        old.Fill(255, 0, 0)
        new.Fill(0, 255, 0)
        canvas = ShadowCanvas(10, 2)

        composite_wipe(old, new, 10, canvas, "left")
        assert canvas.get_pixel(0, 0) == (0, 255, 0)
        assert canvas.get_pixel(9, 0) == (0, 255, 0)

    def test_wipe_left_at_midpoint(self):
        """At boundary=5, left half is new, right half is old."""
        old = ShadowCanvas(10, 2)
        new = ShadowCanvas(10, 2)
        old.Fill(255, 0, 0)
        new.Fill(0, 255, 0)
        canvas = ShadowCanvas(10, 2)

        composite_wipe(old, new, 5, canvas, "left")
        assert canvas.get_pixel(4, 0) == (0, 255, 0)  # new
        assert canvas.get_pixel(5, 0) == (255, 0, 0)  # old

    def test_wipe_right_at_midpoint(self):
        """At boundary=5, right half is new, left half is old."""
        old = ShadowCanvas(10, 2)
        new = ShadowCanvas(10, 2)
        old.Fill(255, 0, 0)
        new.Fill(0, 255, 0)
        canvas = ShadowCanvas(10, 2)

        composite_wipe(old, new, 5, canvas, "right")
        assert canvas.get_pixel(0, 0) == (255, 0, 0)  # old
        assert canvas.get_pixel(9, 0) == (0, 255, 0)  # new


class TestCompositeDissolve:
    def test_at_zero_all_old(self):
        old = ShadowCanvas(10, 2)
        new = ShadowCanvas(10, 2)
        old.Fill(255, 0, 0)
        new.Fill(0, 255, 0)
        canvas = ShadowCanvas(10, 2)

        composite_dissolve(old, new, 0.0, canvas)
        # All should be old (red)
        for x in range(10):
            assert canvas.get_pixel(x, 0) == (255, 0, 0)

    def test_at_one_all_new(self):
        old = ShadowCanvas(10, 2)
        new = ShadowCanvas(10, 2)
        old.Fill(255, 0, 0)
        new.Fill(0, 255, 0)
        canvas = ShadowCanvas(10, 2)

        composite_dissolve(old, new, 1.0, canvas)
        for x in range(10):
            for y in range(2):
                assert canvas.get_pixel(x, y) == (0, 255, 0)

    def test_midpoint_has_both_colors(self):
        old = ShadowCanvas(10, 2)
        new = ShadowCanvas(10, 2)
        old.Fill(255, 0, 0)
        new.Fill(0, 255, 0)
        canvas = ShadowCanvas(10, 2)

        composite_dissolve(old, new, 0.5, canvas)
        reds = sum(
            1
            for x in range(10)
            for y in range(2)
            if canvas.get_pixel(x, y) == (255, 0, 0)
        )
        greens = sum(
            1
            for x in range(10)
            for y in range(2)
            if canvas.get_pixel(x, y) == (0, 255, 0)
        )
        assert reds > 0
        assert greens > 0

    def test_deterministic_with_same_seed(self):
        old = ShadowCanvas(10, 2)
        new = ShadowCanvas(10, 2)
        old.Fill(255, 0, 0)
        new.Fill(0, 255, 0)

        c1 = ShadowCanvas(10, 2)
        c2 = ShadowCanvas(10, 2)
        composite_dissolve(old, new, 0.5, c1, seed=123)
        composite_dissolve(old, new, 0.5, c2, seed=123)

        for x in range(10):
            for y in range(2):
                assert c1.get_pixel(x, y) == c2.get_pixel(x, y)

    def test_progress_monotonic(self):
        """More new pixels as progress increases."""
        old = ShadowCanvas(20, 2)
        new = ShadowCanvas(20, 2)
        old.Fill(255, 0, 0)
        new.Fill(0, 255, 0)

        prev_new_count = 0
        for step in range(11):
            p = step / 10.0
            canvas = ShadowCanvas(20, 2)
            composite_dissolve(old, new, p, canvas)
            new_count = sum(
                1
                for x in range(20)
                for y in range(2)
                if canvas.get_pixel(x, y) == (0, 255, 0)
            )
            assert new_count >= prev_new_count
            prev_new_count = new_count


class TestCompositeSplit:
    def test_at_zero_all_old(self):
        old = ShadowCanvas(10, 2)
        new = ShadowCanvas(10, 2)
        old.Fill(255, 0, 0)
        new.Fill(0, 255, 0)
        canvas = ShadowCanvas(10, 2)

        composite_split(old, new, 0.0, canvas)
        for x in range(10):
            assert canvas.get_pixel(x, 0) == (255, 0, 0)

    def test_at_one_all_new(self):
        old = ShadowCanvas(10, 2)
        new = ShadowCanvas(10, 2)
        old.Fill(255, 0, 0)
        new.Fill(0, 255, 0)
        canvas = ShadowCanvas(10, 2)

        composite_split(old, new, 1.0, canvas)
        for x in range(10):
            assert canvas.get_pixel(x, 0) == (0, 255, 0)

    def test_midpoint_center_revealed(self):
        old = ShadowCanvas(10, 2)
        new = ShadowCanvas(10, 2)
        old.Fill(255, 0, 0)
        new.Fill(0, 255, 0)
        canvas = ShadowCanvas(10, 2)

        composite_split(old, new, 0.5, canvas)
        # Center should be new, edges old
        assert canvas.get_pixel(5, 0) == (0, 255, 0)  # center
        assert canvas.get_pixel(0, 0) == (255, 0, 0)  # edge
        assert canvas.get_pixel(9, 0) == (255, 0, 0)  # edge


class TestCompositeCurtain:
    def test_at_zero_all_old(self):
        old = ShadowCanvas(10, 2)
        new = ShadowCanvas(10, 2)
        old.Fill(255, 0, 0)
        new.Fill(0, 255, 0)
        canvas = ShadowCanvas(10, 2)

        composite_curtain(old, new, 0.0, canvas)
        # Old curtain covers everything
        for x in range(10):
            assert canvas.get_pixel(x, 0) == (255, 0, 0)

    def test_at_one_all_new(self):
        old = ShadowCanvas(10, 2)
        new = ShadowCanvas(10, 2)
        old.Fill(255, 0, 0)
        new.Fill(0, 255, 0)
        canvas = ShadowCanvas(10, 2)

        composite_curtain(old, new, 1.0, canvas)
        # Curtains fully off-screen, all new
        for x in range(10):
            assert canvas.get_pixel(x, 0) == (0, 255, 0)

    def test_midpoint_center_revealed(self):
        old = ShadowCanvas(10, 2)
        new = ShadowCanvas(10, 2)
        old.Fill(255, 0, 0)
        new.Fill(0, 255, 0)
        canvas = ShadowCanvas(10, 2)

        composite_curtain(old, new, 0.5, canvas)
        # Center columns should be new (curtains have slid apart)
        assert canvas.get_pixel(5, 0) == (0, 255, 0)
