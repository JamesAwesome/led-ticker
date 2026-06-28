"""
Tripwire: the engine must never gate behaviour on a concrete backend/canvas type.

`isinstance(canvas, ScaledCanvas)` IS expected and correct — ScaledCanvas is a
public wrapper, not a backend type — and is explicitly excluded from this check.

Concrete backend/canvas types that would silently mishandle a non-rgbmatrix
backend (e.g. the future TelnetBackend):
  - RgbMatrixBackend
  - HeadlessBackend
  - HeadlessCanvas
"""

import pathlib
import re


def test_engine_does_not_gate_on_concrete_backend_types() -> None:
    root = pathlib.Path(__file__).resolve().parents[2] / "src" / "led_ticker"
    files = ["frame.py", "ticker.py", "app/run.py", "scaled_canvas.py"]
    pat = re.compile(
        r"isinstance\([^)]*,\s*(RgbMatrixBackend|HeadlessBackend|HeadlessCanvas)\b"
    )
    offenders: dict[str, list[str]] = {}
    for f in files:
        text = (root / f).read_text()
        hits = [ln for ln in text.splitlines() if pat.search(ln)]
        if hits:
            offenders[f] = hits
    assert not offenders, (
        "engine gates on a concrete backend/canvas type — a non-rgbmatrix backend "
        f"would silently miss this branch: {offenders}"
    )
