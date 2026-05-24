"""Benchmark ScaledCanvas.SetPixel call overhead using the test stub canvas.

Run from the project root:
    PYTHONPATH=tests/stubs python tools/bench_setpixel.py
"""

import sys
import timeit

sys.path.insert(0, "src")
sys.path.insert(0, "tests/stubs")

from led_ticker.scaled_canvas import ScaledCanvas


# Stub canvas that counts SetPixel calls
class CountingCanvas:
    width = 256
    height = 64

    def __init__(self):
        self.calls = 0

    def SetPixel(self, x, y, r, g, b):
        self.calls += 1

    def SubFill(self, x, y, width, height, red, green, blue):
        # Delegate to SetPixel to measure Python-loop overhead
        for dy in range(height):
            for dx in range(width):
                self.SetPixel(x + dx, y + dy, red, green, blue)

    def Clear(self):
        pass


inner = CountingCanvas()
sc = ScaledCanvas(real=inner, scale=4)


def draw_full_frame():
    inner.calls = 0
    for y in range(16):
        for x in range(64):
            sc.SetPixel(x, y, 255, 100, 0)
    return inner.calls


# Warmup
draw_full_frame()

calls = draw_full_frame()
print(f"Calls per frame (original): {calls}  (expected: {64 * 16 * 4 * 4})")

N = 200
elapsed = timeit.timeit(draw_full_frame, number=N)
ms_per_frame = elapsed / N * 1000
budget_ms = 50.0  # 20 fps

print(f"Python-side time per frame: {ms_per_frame:.3f} ms  (budget: {budget_ms} ms)")
print(
    f"SetPixel overhead fraction: {ms_per_frame / budget_ms * 100:.1f}% of frame budget"
)

print()
print("-- SubFill path (after prototype change) --")


class SubFillCountingCanvas:
    width = 256
    height = 64

    def __init__(self):
        self.subfill_calls = 0
        self._pixels = {}

    def SubFill(self, x, y, width, height, red, green, blue):
        self.subfill_calls += 1

    def Clear(self):
        pass


inner2 = SubFillCountingCanvas()
sc2 = ScaledCanvas(real=inner2, scale=4)


def draw_full_frame_subfill():
    inner2.subfill_calls = 0
    for y in range(16):
        for x in range(64):
            sc2.SetPixel(x, y, 255, 100, 0)
    return inner2.subfill_calls


# Warmup
draw_full_frame_subfill()

calls2 = draw_full_frame_subfill()
print(f"SubFill calls per frame: {calls2}  (expected: {64 * 16})")

elapsed2 = timeit.timeit(draw_full_frame_subfill, number=N)
ms2 = elapsed2 / N * 1000

print(f"Python-side time per frame: {ms2:.3f} ms  (budget: {budget_ms} ms)")
print(f"Speedup vs original: {ms_per_frame / ms2:.1f}×")
print(f"SubFill overhead fraction: {ms2 / budget_ms * 100:.1f}% of frame budget")
