"""Implementations for `led-ticker plugin list / search / install`.

Kept out of cli.py so the catalog-resolution + requirements-file + pip logic is
testable in isolation (cli.py stays a thin argparse dispatcher). All pip calls go
through `sys.executable -m pip` so the active interpreter's environment is the
install target; the module never imports pip.
"""

import subprocess
import sys
import tempfile
from importlib.metadata import entry_points
from pathlib import Path

from led_ticker.plugins_catalog import Catalog, CatalogEntry, load_catalog

_PLUGINS_ENTRY_GROUP = "led_ticker.plugins"


def _requirements_path(config_path: Path) -> Path:
    """`requirements-plugins.txt` lives next to the config file."""
    return config_path.parent / "requirements-plugins.txt"


def _requirement_key(requirement: str) -> str:
    """A normalized dedup key for a pip requirement / requirements-file line.

    git -> the repo stem (``led-ticker-pool``); pypi -> the package name. So a
    re-install of the same plugin (even switching git<->pypi or changing the pin)
    replaces its line instead of duplicating it.
    """
    req = requirement.strip()
    if req.startswith(("git+", "-e ")):
        # ...github.com/owner/led-ticker-pool.git@ref  ->  led-ticker-pool
        url = req.split("#", 1)[0]  # drop any #egg= fragment
        url = url.split("@")[0] if "@" in url.rsplit("/", 1)[-1] else url
        # strip a trailing @ref only when it's on the last path segment (refs),
        # not the scheme; simplest: take last path segment, drop .git and @ref.
        last = req.split("/")[-1]
        last = last.split("@", 1)[0]
        stem = last.removesuffix(".git")
        return stem.lower().replace("_", "-")
    # pypi: name up to the first version/marker/extra delimiter
    for delim in ("==", ">=", "<=", "~=", "!=", ">", "<", "[", ";", " "):
        idx = req.find(delim)
        if idx != -1:
            req = req[:idx]
    return req.strip().lower().replace("_", "-")


def _update_requirements(path: Path, requirement: str) -> bool:
    """Add `requirement` to the requirements file, replacing any prior line for
    the same plugin. Preserves comments and unrelated lines. Returns True when an
    existing line was replaced (vs appended)."""
    key = _requirement_key(requirement)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept: list[str] = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if (
            stripped
            and not stripped.startswith("#")
            and (_requirement_key(stripped) == key)
        ):
            replaced = True
            continue  # drop the old pin for this plugin
        kept.append(line)
    kept.append(requirement)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(kept).rstrip("\n") + "\n", encoding="utf-8")
    return replaced


def _installed_namespaces() -> set[str]:
    """Plugin namespaces registered as entry points in the active environment."""
    try:
        eps = entry_points(group=_PLUGINS_ENTRY_GROUP)
    except TypeError:  # pragma: no cover - very old importlib.metadata API
        eps = entry_points().get(_PLUGINS_ENTRY_GROUP, [])  # type: ignore[attr-defined]
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


# --- command entry points (return a process exit code) ----------------------


def cmd_list(catalog: Catalog | None = None) -> int:
    catalog = catalog or load_catalog()
    installed = _installed_namespaces()
    if not catalog.entries:
        print("The plugin catalog is empty.")
        return 0
    print(f"Available plugins ({len(catalog.entries)}):")
    for entry in catalog.entries:
        mark = "  [installed]" if entry.namespace in installed else ""
        print(f"  {entry.name}{mark} — {entry.summary}")
        if entry.provides:
            print(f"      provides: {', '.join(entry.provides)}")
    print("\nInstall with:  led-ticker plugin install <name>")
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


def cmd_install(
    target: str,
    *,
    config_path: Path,
    source: str | None = None,
    pinned: bool = True,
    save_only: bool = False,
    dry_run: bool = False,
    catalog: Catalog | None = None,
) -> int:
    """Install (or save) a plugin by catalog name or raw pip spec."""
    catalog = catalog or load_catalog()
    entry: CatalogEntry | None = catalog.get(target)
    if entry is not None:
        try:
            requirement = entry.requirement(source=source, pinned=pinned)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
    else:
        # Raw mode: treat the argument as a pip spec (git+https://…, name==x, …),
        # mirroring `pip install`. --source only applies to catalog entries.
        if source is not None:
            print(
                f"{target!r} is not a catalog plugin; --source only applies to "
                "catalog names. Pass a full pip spec instead.",
                file=sys.stderr,
            )
            return 2
        requirement = target

    req_path = _requirements_path(config_path)

    if dry_run:
        print("Dry run — no changes made.")
        print(f"  requirement: {requirement}")
        print(f"  would update: {req_path}")
        if not save_only:
            print(
                f"  would run:   {sys.executable} -m pip install "
                f"-c <frozen-core-constraints> {requirement}"
            )
        return 0

    replaced = _update_requirements(req_path, requirement)
    verb = "Replaced" if replaced else "Added"
    print(f"{verb} {requirement!r} in {req_path}")

    if save_only:
        print("Saved (--save-only); rebuild/redeploy to install.")
        return 0

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
