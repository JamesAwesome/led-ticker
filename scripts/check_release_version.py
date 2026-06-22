"""Guard: the release tag (vX.Y.Z) must match pyproject's version.

Exit 1 on mismatch.
"""

import sys
import tomllib


def parse_and_check(
    tag: str, pyproject_path: str = "pyproject.toml"
) -> tuple[bool, str]:
    if not tag.startswith("v"):
        return False, f"Tag {tag!r} must start with 'v' (expected vX.Y.Z)."
    tag_version = tag[1:]
    with open(pyproject_path, "rb") as f:
        version = tomllib.load(f)["project"]["version"]
    if tag_version != version:
        return False, (
            f"Release tag {tag!r} (version {tag_version}) does not match "
            f"pyproject version {version!r}. Bump the version or fix the tag."
        )
    return True, f"OK: tag {tag} matches pyproject version {version}."


def main() -> int:
    tag = sys.argv[1]
    pyproject = sys.argv[2] if len(sys.argv) > 2 else "pyproject.toml"
    ok, msg = parse_and_check(tag, pyproject)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
