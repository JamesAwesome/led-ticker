"""Make the repo root importable so `from tools.gif_plan.x import y`
resolves under `make test` (which only sets PYTHONPATH=tests/stubs).

pytest loads this conftest before collecting the sibling test modules,
so the path is in place before their top-level imports run. Mirrors the
per-file shim in tools/render_demo/test_render.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
