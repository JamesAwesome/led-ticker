"""Filename guard for endpoints that accept a config-file name.

Rejections return None and are deliberately indistinguishable from absent
files at the API layer (404 either way) — the endpoint must not be usable
as a filesystem-existence oracle.
"""

from pathlib import Path


def list_config_names(config_dir: Path) -> list[str]:
    """Sorted basenames of *.toml directly inside config_dir (non-recursive).
    Missing/unreadable dir yields []."""
    try:
        return sorted(
            p.name for p in config_dir.iterdir() if p.suffix == ".toml" and p.is_file()
        )
    except OSError:
        return []


def safe_config_member(config_dir: Path, name: str) -> Path | None:
    """Resolve `name` to a file inside config_dir, or None.

    Three independent checks (all must pass):
    1. basename-only — rejects path separators, `..`, absolute paths
    2. suffix allowlist — only .toml
    3. resolved containment — the real file's parent is exactly the real
       config_dir, which also defeats symlinks pointing out of the dir
    """
    if not name or name != Path(name).name or Path(name).is_absolute():
        return None
    if Path(name).suffix != ".toml":
        return None
    try:
        candidate = (config_dir / name).resolve(strict=True)
        if not candidate.is_file():
            return None
        if candidate.parent != config_dir.resolve(strict=True):
            return None
    except OSError, ValueError:
        # ValueError: e.g. an embedded NUL byte in the name — os.path.realpath
        # raises it rather than OSError; must classify as absent, not 500.
        return None
    return candidate
