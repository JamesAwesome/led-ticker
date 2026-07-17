#!/usr/bin/env python3
"""Cut a release the safe way: derive vNext from the LIVE remote at
execution time, guard the ordering, then `gh release create` on the
origin/main tip.

    uv run python scripts/cut_release.py <patch|minor|major> --notes FILE [--title T]

Exists because a background pipeline once carried a stale "vNext" from a
plan written 40 minutes earlier and cut v4.16.1 AFTER v4.17.0 shipped from
a parallel session (2026-07-16 incident). The version base here is always
`git fetch origin --tags` + the tag list as of NOW — never a number from a
plan. The same ordering check publish.yml enforces (scripts/release_guard.py)
runs locally before the release is created.
"""

import argparse
import re
import subprocess
import sys

from release_guard import _parse, check_release_order  # same-dir import


def compute_next(existing_tags: list[str], bump: str) -> str:
    """Pure: the next vX.Y.Z after the highest existing release tag."""
    versioned = [v for t in existing_tags if (v := _parse(t)) is not None]
    if not versioned:
        return "v0.1.0"
    major, minor, patch = max(versioned)
    if bump == "major":
        return f"v{major + 1}.0.0"
    if bump == "minor":
        return f"v{major}.{minor + 1}.0"
    return f"v{major}.{minor}.{patch + 1}"


def _run(*cmd: str, capture: bool = True) -> str:
    res = subprocess.run(list(cmd), capture_output=capture, text=True, check=True)
    return (res.stdout or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bump", choices=["patch", "minor", "major"])
    ap.add_argument("--notes", required=True, help="release-notes file")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    _run("git", "fetch", "origin", "--tags", "--quiet")
    tags = _run("git", "tag", "-l", "v*").split()
    tag = compute_next(tags, args.bump)
    sha = _run("git", "rev-parse", "origin/main")

    def is_ancestor(a: str, b_tag: str) -> bool:
        # the new tag doesn't exist yet — its commit is the main tip
        target = sha if b_tag == tag else b_tag
        return (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", a, target],
                capture_output=True,
            ).returncode
            == 0
        )

    err = check_release_order(tag, tags, is_ancestor)
    if err:
        print(f"refusing to cut: {err}", file=sys.stderr)
        return 1

    title = args.title or tag
    url = _run(
        "gh",
        "release",
        "create",
        tag,
        "--target",
        sha,
        "--title",
        title,
        "--notes-file",
        args.notes,
    )
    print(f"{tag} cut on {sha[:9]}: {url or '(created)'}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, re.sub(r"[^/]+$", "", __file__) or ".")
    sys.exit(main())
