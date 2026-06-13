"""The sidecar must be importable without rgbmatrix — it runs unprivileged
on machines (or containers) with no matrix hardware libs at all."""

import os
import subprocess
import sys


def _env_without_stubs() -> dict:
    """Build an env dict with the tests/stubs path stripped from PYTHONPATH.

    make test sets PYTHONPATH=tests/stubs, which makes rgbmatrix resolvable
    (the stub). We want a subprocess that has NO rgbmatrix available at all —
    the sidecar must import cleanly even on a machine with neither hardware
    nor stubs present.  The venv's site-packages (reached via sys.executable)
    gives led_ticker itself without PYTHONPATH.
    """
    env = dict(os.environ)
    raw = env.get("PYTHONPATH", "")
    filtered = os.pathsep.join(
        p for p in raw.split(os.pathsep) if p and "stubs" not in p
    )
    if filtered:
        env["PYTHONPATH"] = filtered
    else:
        env.pop("PYTHONPATH", None)
    return env


def test_webui_import_does_not_touch_rgbmatrix():
    # Run WITHOUT tests/stubs on the path: if the import chain reaches
    # rgbmatrix at all, sys.modules will show it (stub or real).
    code = (
        "import sys\n"
        "import led_ticker.webui, led_ticker.status_board,"
        " led_ticker.webui.inventory, led_ticker.preview\n"
        "hit = [m for m in sys.modules if m.startswith('rgbmatrix')]\n"
        "assert not hit, f'webui import pulled in {hit}'\n"
        "print('PURE')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=_env_without_stubs(),
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "PURE" in proc.stdout


def test_cli_imports_without_rgbmatrix():
    """cli.py uses the lazy _compat shim — importing the module must not raise
    even when rgbmatrix (and the stubs) are absent from the path.

    We do NOT assert that rgbmatrix is absent from sys.modules after the import:
    the run-display path legitimately triggers the shim.  What matters is that
    the import itself succeeds so the sidecar subprocess can boot.
    """
    code = "import led_ticker.app.cli; print('CLI-OK')"
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=_env_without_stubs(),
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "CLI-OK" in proc.stdout
