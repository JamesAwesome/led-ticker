"""Leaf module for engine-wide constants.

Import-light by contract (no led_ticker imports): `validate.py` (static
config preflight) and `animations.py` import from here without pulling in
the engine. `ticker.py` re-exports ENGINE_TICK_MS for back-compat with
existing `from led_ticker.ticker import ENGINE_TICK_MS` call sites.
"""

ENGINE_TICK_MS: int = 50  # 20 fps for held-text frame animation
