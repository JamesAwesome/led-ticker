"""Bare first-import tripwires for the public plugin surface.

The transitions package auto-imports every `transitions/*.py` module mid-init,
BEFORE its own re-exports of `HARD_EXCLUDED` / `META_TYPES` /
`default_pool_names`. A transition module that imports `led_ticker.app.*` at
module level therefore pulls `app.factories`, which imports those names from
the partially initialised package, and `import led_ticker.plugin` fails for
every plugin test suite. The console entry (`led_ticker.app`) imports the app
first and masks the cycle, so only a fresh interpreter with no prior
led_ticker import can catch it (design `2026-11-21-fade-design.md`, cycle 3).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("module", ["led_ticker.plugin", "led_ticker.transitions"])
def test_bare_first_import_has_no_cycle(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        env={**os.environ, "PYTHONPATH": f"{REPO}/src:{REPO}/tests/stubs"},
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stderr
