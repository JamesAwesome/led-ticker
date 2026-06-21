"""Completeness guard for the Moon Bunny -> Firebird anonymization.

Asserts the real studio identity appears NOWHERE in the tracked tree except the
archival design docs under docs/superpowers/ (which record history as written).
Prevents both an incomplete rename and a future reintroduction.

Also guards against the retired Moon Bunny pastel palette RGB values creeping
back in. Firebird is phoenix-warm (§6): flame/ember/amber/cream/dusk.
The old Moon Bunny pastels (lavender [189,169,234], soft-pink [255,176,240],
old-cream [254,255,204]) must not appear in brand or example contexts outside
the archival design docs."""

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

# Retired Moon Bunny pastel palette — must not appear in brand/example contexts.
# These are EXTENDED regex patterns for `git grep -E`.
# Firebird brand colors are the phoenix-warm §6 palette:
#   flame [255,92,38] · ember [214,40,57] · amber [255,183,3]
#   cream [255,244,214] · dusk [99,60,138]
# The IG social-handle magenta [225,48,108] is NOT a brand color.
OLD_PALETTE_PATTERNS = [
    r"189,\s*169,\s*234",  # lavender
    r"255,\s*176,\s*240",  # soft-pink
    r"254,\s*255,\s*204",  # old-cream (Moon Bunny)
]


def _git_grep(
    pattern: str, flags: list[str], excludes: list[str]
) -> subprocess.CompletedProcess:
    """Run git grep and return the result.

    git grep exits 0 = matches found, 1 = no matches (clean), anything else = error.
    """
    cmd = ["git", "grep"] + flags + [pattern, "--"] + excludes
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)


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
        assert res.returncode in (0, 1), (
            f"git grep failed (rc={res.returncode}): {res.stderr}"
        )
        for path in res.stdout.splitlines():
            if path and not path.startswith(ALLOW_PREFIXES):
                offenders.append(f"{needle}: {path}")
    assert not offenders, (
        "real-brand strings still present (anonymization incomplete):\n"
        + "\n".join(sorted(set(offenders)))
    )


def test_no_retired_moon_bunny_palette_outside_archival():
    """Assert retired Moon Bunny pastel RGBs do not appear outside archival docs.

    The three retired pastels are lavender [189,169,234], soft-pink [255,176,240],
    and old-cream [254,255,204]. Firebird is phoenix-warm (§6); these colors have
    no place in brand examples, skill fallbacks, or tutorial snippets."""
    offenders = []
    for pattern in OLD_PALETTE_PATTERNS:
        res = _git_grep(
            pattern,
            flags=["-ilE"],
            excludes=[
                "--",
                ":!docs/superpowers",
                ":!tests/test_no_real_brand.py",
            ],
        )
        assert res.returncode in (0, 1), (
            f"git grep failed (rc={res.returncode}): {res.stderr}"
        )
        for path in res.stdout.splitlines():
            if path and not path.startswith(ALLOW_PREFIXES):
                offenders.append(f"{pattern}: {path}")
    assert not offenders, (
        "Retired Moon Bunny palette RGB values found outside archival docs "
        "(Firebird is phoenix-warm §6 — purge these pastels):\n"
        + "\n".join(sorted(set(offenders)))
    )
