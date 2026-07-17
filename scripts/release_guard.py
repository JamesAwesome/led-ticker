#!/usr/bin/env python3
"""Release order guard: version order must equal commit-ancestry order.

Invoked by publish.yml AFTER the exact-tag guard, BEFORE build/upload:

    python3 scripts/release_guard.py "$TAG"

Exits non-zero (with a ::error:: line) when the tag would create an
out-of-order release. Born from the v4.16.1/v4.17.0 incident (2026-07-16):
a parallel workstream shipped v4.17.0, then a background pipeline carrying
a stale "vNext" cut v4.16.1 on NEWER code — a lower version containing
strictly more fixes, hidden from resolver-visible "latest". The mirror
failure (a higher version tagged on OLDER code) is equally guarded.

Trunk-only by decision (spec: docs/superpowers/specs/
2026-07-16-release-order-guard-design.md): no backport escape hatch — a
genuine future maintenance release is a conscious edit to this guard.

Prefer cutting releases with scripts/cut_release.py, which derives the
next version from the live remote at execution time and runs this same
check before creating the release.
"""

import re
import subprocess
import sys

_VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _parse(tag: str) -> tuple[int, int, int] | None:
    m = _VERSION_RE.match(tag)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def check_release_order(new_tag, existing_tags, is_ancestor):
    """Pure guard logic. Returns None when the release is well-ordered,
    else a human-readable failure reason.

    - `new_tag` must be a plain vX.Y.Z (anything else is rejected — the
      project releases only plain triples).
    - Malformed tags in `existing_tags` are ignored (historical noise must
      not brick releases); the comparison set is the parseable ones.
    - Monotonic: new version strictly greater than every existing one.
    - Ancestry: the previous-latest tag's commit must be an ancestor of the
      new tag's commit (version order == history order; trunk-only).
    """
    new_v = _parse(new_tag)
    if new_v is None:
        return f"tag {new_tag!r} is not a plain vX.Y.Z release tag"
    versioned = [(v, t) for t in existing_tags if (v := _parse(t)) is not None]
    if not versioned:
        return None  # first release: trivially ordered
    prev_v, prev_tag = max(versioned)
    if new_v <= prev_v:
        return (
            f"version out of order: {new_tag} is not greater than the latest "
            f"existing release {prev_tag} — cut the next version on the "
            f"current main tip instead"
        )
    if not is_ancestor(prev_tag, new_tag):
        return (
            f"history out of order: the previous release {prev_tag} is not an "
            f"ancestor of {new_tag}'s commit — a higher version must ship "
            f"newer code (trunk-only releases)"
        )
    return None


def _git_is_ancestor(a: str, b: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", a, b],
            capture_output=True,
        ).returncode
        == 0
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: release_guard.py <tag>", file=sys.stderr)
        return 2
    new_tag = sys.argv[1]
    if (
        subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", new_tag + "^{commit}"],
            capture_output=True,
        ).returncode
        != 0
    ):
        print(
            f"::error::release order guard: tag {new_tag!r} does not "
            "resolve to a commit here"
        )
        return 1
    tags = subprocess.run(
        ["git", "tag", "-l", "v*"], capture_output=True, text=True, check=True
    ).stdout.split()
    existing = [t for t in tags if t != new_tag]
    err = check_release_order(new_tag, existing, _git_is_ancestor)
    if err:
        print(f"::error::release order guard: {err}")
        return 1
    print(f"release order guard: {new_tag} is well-ordered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
