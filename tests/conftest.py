"""Shared test fixtures."""

import os
import sys

# Ensure the rgbmatrix stub is available before any led_ticker imports
stubs_path = os.path.join(os.path.dirname(__file__), "stubs")
if stubs_path not in sys.path:
    sys.path.insert(0, stubs_path)
