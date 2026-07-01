"""Tripwire test for docs/site/.../reference/cli.mdx Make-target drift.

The CLI reference page hand-curates a "Make targets" table describing every
target in the repo's Makefile. The hand curation buys usage examples and
cross-links that pure auto-generation would lose, but it's also a drift
risk — when the Makefile grows a new target, the docs page has no built-in
pressure to keep up. (This is exactly how the deploy-lifecycle targets
`up`/`update`/`restart`/`down`/`logs` shipped in the Makefile but never
reached the page.)

This test is that pressure. The Makefile is the source of truth: every
target carrying a `## ` help comment is a documented, user-runnable target.
The test asserts a strict 1:1 correspondence:

- Every `## `-commented Makefile target appears as a `make <target>` row in
  the page's Make-targets table.
- Every `make <target>` row on the page names a real `## `-commented target.

When you add a Makefile target with a `## ` help comment:
  - document it: add a `| `make <target>` | ... |` row to cli.mdx
  - or, if it's genuinely not worth surfacing, drop the `## ` comment (it
    then also disappears from `make help`).

The test fails loudly either way until the Makefile and page agree.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAKEFILE_PATH = REPO_ROOT / "Makefile"
PAGE_PATH = (
    REPO_ROOT / "docs" / "site" / "src" / "content" / "docs" / "reference" / "cli.mdx"
)

# A documented Makefile target: `name:` (optionally with prereqs) followed by
# a `## ` help comment on the same line. Mirrors the `make help` convention.
_MAKE_TARGET_RE = re.compile(r"^([a-zA-Z0-9_.-]+):[^=]*?##")

# A Make-targets table row on the page: first column is `make <target>` in
# backticks, e.g. `| \`make up\` | Start the sign... |`.
_PAGE_ROW_RE = re.compile(r"^\|\s*`make\s+([a-zA-Z0-9_.-]+)`\s*\|")


def _makefile_targets() -> set[str]:
    """Every Makefile target carrying a `## ` help comment."""
    targets: set[str] = set()
    for line in MAKEFILE_PATH.read_text().splitlines():
        match = _MAKE_TARGET_RE.match(line)
        if match:
            targets.add(match.group(1))
    return targets


def _documented_targets() -> set[str]:
    """Every `make <target>` named in the page's Make-targets table."""
    targets: set[str] = set()
    for line in PAGE_PATH.read_text().splitlines():
        match = _PAGE_ROW_RE.match(line)
        if match:
            targets.add(match.group(1))
    return targets


def test_makefile_and_docs_page_exist() -> None:
    """Correctness check: the files are where the test expects them."""
    assert MAKEFILE_PATH.exists(), f"Makefile not found at {MAKEFILE_PATH}"
    assert PAGE_PATH.exists(), f"CLI reference page not found at {PAGE_PATH}"


def test_make_targets_have_help_comments() -> None:
    """Sanity: the Makefile actually uses the `## ` help convention, so the
    source-of-truth parse isn't silently empty."""
    assert _makefile_targets(), (
        "No `## `-commented targets parsed from the Makefile — the help "
        "convention may have changed; update _MAKE_TARGET_RE."
    )


def test_cli_docs_make_targets_match_makefile() -> None:
    """Every documented Makefile target is on the CLI reference page, and the
    page lists no target that isn't in the Makefile."""
    in_makefile = _makefile_targets()
    on_page = _documented_targets()

    missing = in_makefile - on_page
    extra = on_page - in_makefile

    assert not missing, (
        "Makefile targets missing from the cli.mdx Make-targets table: "
        f"{sorted(missing)}.\n"
        "Add a `| `make <target>` | ... |` row in "
        "docs/site/src/content/docs/reference/cli.mdx, or drop the target's "
        "`## ` help comment if it shouldn't be documented."
    )
    assert not extra, (
        "cli.mdx Make-targets table lists targets not in the Makefile: "
        f"{sorted(extra)}.\n"
        "Either add the target (with a `## ` help comment) to the Makefile, "
        "or drop the row from the docs table."
    )
