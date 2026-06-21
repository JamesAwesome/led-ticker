"""Completeness guard for the Moon Bunny -> Firebird anonymization.

Asserts the real studio identity appears NOWHERE in the tracked tree except the
archival design docs under docs/superpowers/ (which record history as written).
Prevents both an incomplete rename and a future reintroduction."""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Real-brand needles (case-insensitive). "aerial" is included because the real
# studio is an aerial-arts studio; it must not survive in shipped/docs copy.
# NOTE: "aerial" is also common English (e.g. "aerial view") — if a future
# docs page legitimately uses the word, add it to ALLOW_PREFIXES rather than
# removing it from NEEDLES or silently widening the allow-list.
NEEDLES = ["moonbunny", "moon bunny", "moonbunnyaerial", "aerial"]
# Archival design docs record the old brand as written at the time — allowed.
ALLOW_PREFIXES = ("docs/superpowers/",)


def test_no_real_brand_strings_outside_archival():
    offenders = []
    for needle in NEEDLES:
        # NOTE: `git grep` exits with code 1 when there are NO matches (the
        # passing/clean case), so `check=True` must NOT be added here — it
        # would raise CalledProcessError on a clean tree.
        res = subprocess.run(
            [
                "git",
                "grep",
                "-il",
                needle,
                "--",
                ":!docs/superpowers",
                ":!tests/test_no_real_brand.py",
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        for path in res.stdout.splitlines():
            if path and not path.startswith(ALLOW_PREFIXES):
                offenders.append(f"{needle}: {path}")
    assert not offenders, (
        "real-brand strings still present (anonymization incomplete):\n"
        + "\n".join(sorted(set(offenders)))
    )
