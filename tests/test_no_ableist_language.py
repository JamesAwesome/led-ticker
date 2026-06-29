"""Enforcement guard for the inclusive-language rule (DOCS-STYLE.md §1).

The style guide bans ableist idioms — most prominently "sanity check" /
"sanity test" / "sanity:". This tripwire asserts the word "sanity" appears
NOWHERE in the tracked tree except:

  - docs/superpowers/  — archival design docs, recorded as written at the time.
  - docs/DOCS-STYLE.md — the style guide itself, which names the banned phrase
    in order to ban it.
  - this test file, which names the phrase to test for it.

Prefer "correctness check", "quick check", "smoke test", or "cross-check".
If a future word legitimately contains "sanity" (none does in normal prose),
add its path to the allow-list pathspecs rather than weakening the needle.
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Pathspecs that legitimately contain the word (excluded from the scan).
_ALLOW_PATHSPECS = [
    ":!docs/superpowers",
    ":!docs/DOCS-STYLE.md",
    ":!tests/test_no_ableist_language.py",
]


def test_no_sanity_idiom_outside_allowlist():
    # -i case-insensitive, -w word boundary (so "sanity-check" and "sanity:"
    # both match), -l filenames only. git grep exits 0 = matches found (the
    # FAILING case here), 1 = clean. Do NOT pass check=True: rc=1 is success.
    res = subprocess.run(
        ["git", "grep", "-ilwE", "sanity", "--", *_ALLOW_PATHSPECS],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert res.returncode in (0, 1), (
        f"git grep failed (rc={res.returncode}): {res.stderr}"
    )
    offenders = [p for p in res.stdout.splitlines() if p]
    assert not offenders, (
        'ableist idiom "sanity" found (DOCS-STYLE.md §1 bans it) — use '
        '"correctness check" / "quick check" / "smoke test" instead:\n'
        + "\n".join(sorted(offenders))
    )
