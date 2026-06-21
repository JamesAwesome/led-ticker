"""Completeness guard for the Moon Bunny -> Firebird anonymization.

Asserts the real studio identity appears NOWHERE in the tracked tree except the
archival design docs under docs/superpowers/ (which record history as written).
Prevents both an incomplete rename and a future reintroduction."""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Real-brand needles (case-insensitive). "aerial" is included because the real
# studio is an aerial-arts studio; it must not survive in shipped/docs copy.
NEEDLES = ["moonbunny", "moon bunny", "moonbunnyaerial", "aerial"]
# Archival design docs record the old brand as written at the time — allowed.
ALLOW_PREFIXES = ("docs/superpowers/",)


def _tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    )
    return [p for p in out.stdout.splitlines() if p]


def test_no_real_brand_strings_outside_archival():
    offenders = []
    for needle in NEEDLES:
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
