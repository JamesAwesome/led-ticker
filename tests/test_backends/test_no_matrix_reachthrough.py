import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "led_ticker"

# Files allowed to mention `.matrix` (none, after the refactor). frame.py no
# longer references a matrix attribute; the backend owns it.
ALLOWED: set[str] = set()


def test_no_matrix_reachthrough_outside_backends():
    offenders = []
    for path in SRC.rglob("*.py"):
        if "backends" in path.parts:
            continue  # backends own the matrix internally
        rel = str(path.relative_to(SRC))
        if rel in ALLOWED:
            continue
        text = path.read_text()
        for i, line in enumerate(text.splitlines(), 1):
            # Match `.matrix.` or `.matrix =` (attribute reach-through),
            # not the word in comments/strings like "RGBMatrix".
            if re.search(r"\b\w+\.matrix\b", line) and "self.matrix" not in line:
                offenders.append(f"{rel}:{i}: {line.strip()}")
    assert not offenders, "reach-through to `.matrix` found:\n" + "\n".join(offenders)
