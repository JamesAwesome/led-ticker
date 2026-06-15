"""Implementations for `led-ticker plugin list / search / install`.

Kept out of cli.py so the catalog-resolution + requirements-file + pip logic is
testable in isolation (cli.py stays a thin argparse dispatcher). All pip calls go
through `sys.executable -m pip` so the active interpreter's environment is the
install target; the module never imports pip.
"""

import difflib
import importlib.metadata
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from led_ticker.plugins_catalog import Catalog, CatalogEntry, load_catalog

_PLUGINS_ENTRY_GROUP = "led_ticker.plugins"


_CANONICAL_REQUIREMENTS = Path("config") / "requirements-plugins.txt"


def _requirements_path(config_path: Path, config_explicit: bool) -> Path:
    """Where to write requirements-plugins.txt.

    When the user passed an explicit ``--config``, the file lives next to it.
    Otherwise default to the canonical ``config/requirements-plugins.txt`` — the
    only requirements file the Docker build and ``deploy/install.sh`` read — so a
    bare ``led-ticker plugin install pool`` from the project root does the right
    thing instead of dropping the file in the cwd.
    """
    if config_explicit:
        return config_path.parent / "requirements-plugins.txt"
    return _CANONICAL_REQUIREMENTS


def _requirement_key(requirement: str) -> str:
    """A normalized dedup key for a pip requirement / requirements-file line.

    git -> the repo stem (``led-ticker-pool``); pypi -> the package name. So a
    re-install of the same plugin (even switching git<->pypi or changing the pin)
    replaces its line instead of duplicating it.
    """
    req = requirement.strip()
    if req.startswith(("git+", "-e ")):
        # git+https://host/owner/led-ticker-pool.git@<ref>[#egg=...] -> led-ticker-pool
        url = req.removeprefix("-e ").strip()
        url = url.split("#", 1)[0]  # drop the #egg= fragment
        # Strip the @ref. A ref can itself contain '/' (e.g. @feature/foo), so
        # cut at the first '@' AFTER the URL path begins — not a user@host
        # credential, and not a '/' inside the ref.
        scheme = url.find("//")
        path_start = url.find("/", scheme + 2) if scheme != -1 else url.find("/")
        at = url.find("@", path_start) if path_start != -1 else url.find("@")
        if at != -1:
            url = url[:at]
        stem = url.rstrip("/").split("/")[-1].removesuffix(".git")
        return stem.lower().replace("_", "-")
    # pypi: name up to the first version/marker/extra delimiter
    for delim in ("==", ">=", "<=", "~=", "!=", ">", "<", "[", ";", " "):
        idx = req.find(delim)
        if idx != -1:
            req = req[:idx]
    return req.strip().lower().replace("_", "-")


def _trailing_comment(line: str) -> str | None:
    """The pip-style trailing comment on a requirements line, or None.

    pip treats ``#`` as a comment only at line-start or when preceded by
    whitespace; a ``#egg=`` / ``#subdirectory=`` fragment inside a git URL is NOT
    a comment. Returns the comment text including the leading ``#`` (stripped of
    surrounding whitespace), or None when the line has no comment.
    """
    match = re.search(r"(?:^|\s)(#.*)$", line)
    return match.group(1).strip() if match else None


def _update_requirements(path: Path, requirement: str) -> str | None:
    """Add `requirement` to the requirements file, replacing any prior line for
    the same plugin. Preserves comments and unrelated lines — including a trailing
    inline comment on the line being replaced, which is carried onto the new line.
    Returns the replaced line (verbatim) when one was found, else None (appended)."""
    key = _requirement_key(requirement)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept: list[str] = []
    replaced_line: str | None = None
    new_line = requirement
    for line in lines:
        stripped = line.strip()
        if (
            stripped
            and not stripped.startswith("#")
            and (_requirement_key(stripped) == key)
        ):
            replaced_line = line
            # Carry a trailing inline comment ("pkg==1.0  # prod pin") onto the
            # new line so a deliberate annotation isn't silently lost. Detect a
            # comment the way pip does — only a '#' at line-start or preceded by
            # whitespace — so a '#egg='/'#subdirectory=' URL fragment (part of a
            # git spec, NOT a comment) isn't mistaken for one and mangled.
            comment = _trailing_comment(line)
            if comment:
                new_line = f"{requirement}  {comment}"
            continue  # drop the old line for this plugin
        kept.append(line)
    kept.append(new_line)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(kept).rstrip("\n") + "\n", encoding="utf-8")
    return replaced_line


_SPEC_MARKERS = ("git+", "://", "@", "==", ">=", "<=", "~=", "!=", "/", "[", " ")
_REBUILD_HINT = (
    "Run a rebuild/redeploy (e.g. `docker compose up -d --build`) to install it."
)


def _config_warning(req_path: Path) -> str | None:
    """A warning when the manifest isn't under a 'config/' dir (Docker/install.sh
    only read config/requirements-plugins.txt), else None."""
    if req_path.parent.name == "config":
        return None
    return (
        f"note: {req_path} is not under a 'config/' directory — Docker and "
        "deploy/install.sh read config/requirements-plugins.txt. Run from your "
        "project root or pass --config config/config.toml."
    )


def _resolve_requirement(
    target: str,
    catalog: Catalog,
    *,
    source: str | None,
    pinned: bool,
    verb: str = "install",
) -> tuple[str, CatalogEntry | None] | None:
    """Resolve a catalog name or raw pip spec to (requirement, entry).

    Returns None (after printing an actionable message) when the target is a
    likely typo of a catalog name, or when --source is given for a non-catalog
    spec, or when the requested source is missing — the caller returns exit 2.

    ``verb`` is the invoking command ("add" / "install"); the did-you-mean hint
    echoes it so a Docker user who typos ``plugin add`` is steered back to
    ``add`` (the no-pip path) rather than ``install``.
    """
    entry = catalog.get(target)
    if entry is not None:
        try:
            return entry.requirement(source=source, pinned=pinned), entry
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return None
    # Not a catalog name. A bare token (no pip-spec markers) close to a catalog
    # name is almost certainly a typo — suggest it rather than installing an
    # arbitrary (possibly typosquatted) package.
    if not any(m in target for m in _SPEC_MARKERS):
        close = difflib.get_close_matches(
            target.lower(), [e.name for e in catalog.entries], n=1, cutoff=0.7
        )
        if close:
            print(
                f"{target!r} is not a known plugin. Did you mean {close[0]!r}? "
                f"(run: led-ticker plugin {verb} {close[0]})",
                file=sys.stderr,
            )
            return None
    # Raw mode: the argument IS the pip spec, mirroring pip install.
    if source is not None:
        print(
            f"{target!r} is not a catalog plugin; --source only applies to "
            "catalog names. Pass a full pip spec instead.",
            file=sys.stderr,
        )
        return None
    return target, None


def _apply_to_manifest(req_path: Path, requirement: str) -> int:
    """Write `requirement` to the manifest (dedup + comment carry) and echo the
    change. Returns 0 on success, 2 on a write failure (message printed)."""
    try:
        replaced_line = _update_requirements(req_path, requirement)
    except OSError as e:
        print(f"could not write {req_path}: {e}", file=sys.stderr)
        return 2
    if replaced_line is None:
        print(f"Added {requirement!r} in {req_path}")
    elif replaced_line.strip() == requirement:
        print(f"{requirement!r} is already declared in {req_path} (no change).")
    else:
        print(f"Replaced {replaced_line.strip()!r} -> {requirement!r} in {req_path}")
    return 0


def _find_requirement_lines(path: Path, key: str) -> list[str]:
    """Read-only: every manifest line matching `key` (verbatim). Used by dry-run
    remove/uninstall so the preview matches what the real command would do —
    including a drifted manifest holding more than one line for the same plugin."""
    if not path.exists():
        return []
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if (s := line.strip()) and not s.startswith("#") and _requirement_key(s) == key
    ]


def _remove_requirement(path: Path, key: str) -> list[str]:
    """Drop the manifest line(s) for `key`, preserving comments + other lines.
    Returns every removed line (verbatim) — usually one, but a drifted manifest
    can hold several lines that normalize to the same key, and ALL are removed."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    removed: list[str] = []
    for line in lines:
        stripped = line.strip()
        if (
            stripped
            and not stripped.startswith("#")
            and (_requirement_key(stripped) == key)
        ):
            removed.append(line)
            continue
        kept.append(line)
    if removed:
        body = "\n".join(kept).rstrip("\n")
        path.write_text(body + "\n" if body else "", encoding="utf-8")
    return removed


def _removed_phrase(lines: list[str], key: str) -> str:
    """Human phrase for removed/matching manifest line(s): the verbatim line when
    there's exactly one, else a count (so a drifted multi-line manifest doesn't
    silently report only the last line)."""
    if len(lines) == 1:
        return repr(lines[0].strip())
    return f"{len(lines)} lines for {key!r}"


def _dist_key(target: str, catalog: Catalog) -> str:
    """The dedup key for a target — a catalog name resolves via its requirement
    (`pool` -> `led-ticker-pool`); a raw spec via the spec itself.

    `uninstall` also uses this as the pip distribution name. That holds for the
    git repo stem == package name convention the first-party plugins follow; a
    raw git spec whose repo dir differs from its pyproject `name` would
    pip-uninstall the wrong name (pip then no-ops with "not installed"). The
    manifest line is still removed correctly either way.
    """
    entry = catalog.get(target)
    if entry is not None:
        return _requirement_key(entry.requirement())
    return _requirement_key(target)


def _declared_keys(req_path: Path) -> set[str]:
    """Dedup keys of every (non-comment) line in the manifest, or empty if absent."""
    if not req_path.exists():
        return set()
    keys: set[str] = set()
    for line in req_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            keys.add(_requirement_key(stripped))
    return keys


def _installed_namespaces() -> set[str]:
    """Plugin namespaces registered as entry points in the active environment.

    Calls ``importlib.metadata.entry_points`` via the module (not a pre-bound
    name) so the test suite's hermetic entry-point stub applies here too.
    """
    eps = importlib.metadata.entry_points(group=_PLUGINS_ENTRY_GROUP)
    return {ep.name for ep in eps}


def _pip_install(requirement: str) -> int:
    """Freeze the current env to a constraints file, then pip-install the
    requirement under it so a plugin can't move core's pinned deps. Returns the
    pip exit code (0 = success)."""
    freeze = subprocess.run(
        [sys.executable, "-m", "pip", "list", "--format=freeze"],
        capture_output=True,
        text=True,
    )
    if freeze.returncode != 0:
        print(freeze.stderr, file=sys.stderr)
        return freeze.returncode
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(freeze.stdout)
        constraints = fh.name
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-c", constraints, requirement],
        )
    finally:
        Path(constraints).unlink(missing_ok=True)
    return proc.returncode


def _pip_uninstall(dist: str) -> int:
    """pip-uninstall a distribution by name. Returns the pip exit code (pip exits
    0 with a warning when the package isn't installed)."""
    proc = subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", dist])
    return proc.returncode


# --- command entry points (return a process exit code) ----------------------


def cmd_list(
    catalog: Catalog | None = None,
    *,
    config_path: Path | None = None,
    config_explicit: bool = True,
) -> int:
    catalog = catalog or load_catalog()
    installed = _installed_namespaces()
    declared = (
        _declared_keys(_requirements_path(config_path, config_explicit))
        if config_path is not None
        else set()
    )
    if not catalog.entries:
        print("The plugin catalog is empty.")
        return 0
    print(f"Available plugins ({len(catalog.entries)}):")
    for entry in catalog.entries:
        marks = []
        if _requirement_key(entry.requirement()) in declared:
            marks.append("[declared]")
        if entry.namespace in installed:
            marks.append("[installed]")
        suffix = f"  {' '.join(marks)}" if marks else ""
        print(f"  {entry.name}{suffix} — {entry.summary}")
        if entry.provides:
            print(f"      provides: {', '.join(entry.provides)}")
    print(
        "\n[declared] = in requirements-plugins.txt (installs on next build); "
        "[installed] = in this environment now."
    )
    print("Add with:  led-ticker plugin add <name>   (or `install` to pip it now)")
    return 0


def cmd_search(query: str, catalog: Catalog | None = None) -> int:
    catalog = catalog or load_catalog()
    matches = catalog.search(query)
    if not matches:
        print(f"No plugins match {query!r}.")
        return 0
    installed = _installed_namespaces()
    print(f"{len(matches)} plugin(s) match {query!r}:")
    for entry in matches:
        mark = "  [installed]" if entry.namespace in installed else ""
        print(f"  {entry.name}{mark} — {entry.summary}")
    return 0


def cmd_add(
    target: str,
    *,
    config_path: Path,
    config_explicit: bool = True,
    source: str | None = None,
    pinned: bool = True,
    dry_run: bool = False,
    catalog: Catalog | None = None,
) -> int:
    """Add a plugin to the manifest only (no pip) — the Docker-native path."""
    catalog = catalog or load_catalog()
    resolved = _resolve_requirement(
        target, catalog, source=source, pinned=pinned, verb="add"
    )
    if resolved is None:
        return 2
    requirement, _entry = resolved
    req_path = _requirements_path(config_path, config_explicit)
    config_warning = _config_warning(req_path)

    if dry_run:
        print("Dry run — no changes made.")
        print(f"  requirement: {requirement}")
        print(f"  would update: {req_path}")
        if config_warning:
            print(config_warning, file=sys.stderr)
        return 0

    code = _apply_to_manifest(req_path, requirement)
    if code != 0:
        return code
    if config_warning:
        print(config_warning, file=sys.stderr)
    print(_REBUILD_HINT)
    return 0


def cmd_install(
    target: str,
    *,
    config_path: Path,
    config_explicit: bool = True,
    source: str | None = None,
    pinned: bool = True,
    dry_run: bool = False,
    catalog: Catalog | None = None,
) -> int:
    """Add a plugin to the manifest AND pip-install it (bare-metal/dev)."""
    catalog = catalog or load_catalog()
    resolved = _resolve_requirement(
        target, catalog, source=source, pinned=pinned, verb="install"
    )
    if resolved is None:
        return 2
    requirement, entry = resolved
    req_path = _requirements_path(config_path, config_explicit)
    config_warning = _config_warning(req_path)

    if dry_run:
        print("Dry run — no changes made.")
        print(f"  requirement: {requirement}")
        print(f"  would update: {req_path}")
        print(
            f"  would run:   {sys.executable} -m pip install "
            f"-c <frozen-core-constraints> {requirement}"
        )
        if config_warning:
            print(config_warning, file=sys.stderr)
        return 0

    code = _apply_to_manifest(req_path, requirement)
    if code != 0:
        return code
    if config_warning:
        print(config_warning, file=sys.stderr)

    code = _pip_install(requirement)
    if code != 0:
        print(
            f"pip install failed (exit {code}); the requirements file was "
            "updated but the package is not installed.",
            file=sys.stderr,
        )
        return code

    if entry is not None and entry.provides:
        print(
            f'Installed. Add e.g.  type = "{entry.provides[0]}"  to a widget '
            "section, then restart led-ticker."
        )
    else:
        print("Installed. Restart led-ticker to load the plugin.")
    return 0


def cmd_remove(
    target: str,
    *,
    config_path: Path,
    config_explicit: bool = True,
    dry_run: bool = False,
    catalog: Catalog | None = None,
) -> int:
    """Remove a plugin from the manifest only (no pip) — the Docker-native path."""
    catalog = catalog or load_catalog()
    key = _dist_key(target, catalog)
    req_path = _requirements_path(config_path, config_explicit)
    config_warning = _config_warning(req_path)

    if dry_run:
        print("Dry run — no changes made.")
        matches = _find_requirement_lines(req_path, key)
        if matches:
            print(f"  would remove {_removed_phrase(matches, key)} from: {req_path}")
        else:
            print(f"  {target!r} is not in {req_path} (nothing to remove).")
        if config_warning:
            print(config_warning, file=sys.stderr)
        return 0

    try:
        removed = _remove_requirement(req_path, key)
    except OSError as e:
        print(f"could not write {req_path}: {e}", file=sys.stderr)
        return 2
    if not removed:
        print(f"{target!r} is not in {req_path} (nothing to remove).")
        if config_warning:
            print(config_warning, file=sys.stderr)
        return 0
    print(f"Removed {_removed_phrase(removed, key)} from {req_path}")
    if config_warning:
        print(config_warning, file=sys.stderr)
    print(_REBUILD_HINT.replace("install it", "apply it"))
    return 0


def cmd_uninstall(
    target: str,
    *,
    config_path: Path,
    config_explicit: bool = True,
    dry_run: bool = False,
    catalog: Catalog | None = None,
) -> int:
    """Remove a plugin from the manifest AND pip-uninstall it (bare-metal/dev)."""
    catalog = catalog or load_catalog()
    key = _dist_key(target, catalog)
    req_path = _requirements_path(config_path, config_explicit)
    config_warning = _config_warning(req_path)

    if dry_run:
        print("Dry run — no changes made.")
        matches = _find_requirement_lines(req_path, key)
        if matches:
            print(f"  would remove {_removed_phrase(matches, key)} from: {req_path}")
        else:
            print(f"  {target!r} is not in {req_path} (nothing to remove).")
        print(f"  would run:   {sys.executable} -m pip uninstall -y {key}")
        if config_warning:
            print(config_warning, file=sys.stderr)
        return 0

    try:
        removed = _remove_requirement(req_path, key)
    except OSError as e:
        print(f"could not write {req_path}: {e}", file=sys.stderr)
        return 2
    if removed:
        print(f"Removed {_removed_phrase(removed, key)} from {req_path}")
    else:
        print(f"{target!r} was not in {req_path}.")
    if config_warning:
        print(config_warning, file=sys.stderr)

    code = _pip_uninstall(key)
    if code != 0:
        print(
            f"pip uninstall exited {code} (the package may not have been installed).",
            file=sys.stderr,
        )
        return code
    print(f"Uninstalled {key}.")
    return 0
