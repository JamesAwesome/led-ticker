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
# `frames_to_rest` counts FRAMES, so each loop converts the wall-clock
# budget at its own tick period: the engine's `_swap_and_scroll` ticks at
# ENGINE_TICK_MS (MAX_SETTLE_TICKS); the image play() loops tick at
# `scroll_speed_ms` and use `MAX_SETTLE_MS // tick_ms`.
MAX_SETTLE_MS: int = 1000
MAX_SETTLE_TICKS: int = MAX_SETTLE_MS // ENGINE_TICK_MS
