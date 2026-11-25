"""Leaf module for engine-wide constants.

Import-light by contract (no led_ticker imports): `validate.py` (static
config preflight) and `animations.py` import from here without pulling in
the engine. `ticker.py` re-exports ENGINE_TICK_MS for back-compat with
existing `from led_ticker.ticker import ENGINE_TICK_MS` call sites.
"""

ENGINE_TICK_MS: int = 50  # 20 fps for held-text frame animation

# Settle-to-rest budget (#305, #526): at the hold->transition handoff a
# render loop may extend the hold so animated effects (shimmer sweep,
# typewriter reveal, blink ON phase) land at a rest point. All-or-nothing:
# a remainder above the cap gets NO extension (never pay latency without a
# clean landing). ~1 s keeps the slip inside the rotation's jitter budget.
# `frames_to_rest` counts FRAMES (50 ms each, #525) and every loop converts
# the owed time into its own ticks — `ceil((frames * 50 - banked carry) /
# tick_ms)`, refused when a tick is longer than MAX_SETTLE_MS or would
# START at or past it (`tick_ms > MAX_SETTLE_MS or (ticks - 1) * tick_ms >=
# MAX_SETTLE_MS`); the LAST tick may cross the line (#570 — refusing on the
# delivered total `ticks * tick_ms` dropped every top-of-budget settle on a
# tick that does not divide 1000: 20 frames at 30 ms = 1020 ms, at a 67 ms
# swap interval = 1005 ms for every carry), so the overshoot is bounded by
# one tick. The engine's hold tick is ENGINE_TICK_MS floored at the frame's
# swap interval (`Ticker._settle_hold_ticks`; on an uncapped frame that is
# one tick per frame, MAX_SETTLE_TICKS at most), the image play() loops
# tick at `scroll_speed_ms` floored the same way
# (`_BaseImageWidget._settle_ticks`).
MAX_SETTLE_MS: int = 1000
MAX_SETTLE_TICKS: int = MAX_SETTLE_MS // ENGINE_TICK_MS
