"""Make the repo root importable so `from tools.film.x import y` resolves
under `make test` (which only sets pythonpath=tests/stubs). Mirrors
tools/gif_plan/conftest.py."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
