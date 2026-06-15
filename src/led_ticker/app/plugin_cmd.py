"""Implementations for `led-ticker plugin list / search / install`.

Kept out of cli.py so the catalog-resolution + requirements-file + pip logic is
testable in isolation (cli.py stays a thin argparse dispatcher). All pip calls go
through `sys.executable -m pip` so the active interpreter's environment is the
install target; the module never imports pip.
"""

import difflib
import importlib.metadata
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
            # new line so a deliberate annotation isn't silently lost.
            if "#" in line:
                new_line = f"{requirement}  {line[line.index('#') :].strip()}"
            continue  # drop the old line for this plugin
        kept.append(line)
    kept.append(new_line)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(kept).rstrip("\n") + "\n", encoding="utf-8")
    return replaced_line


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
    config_explicit: bool = True,
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
        # Not a catalog name. A bare token (no pip-spec markers) that's close to
        # a catalog name is almost certainly a typo — suggest it rather than
        # silently pip-installing an arbitrary (possibly typosquatted) package.
        _SPEC_MARKERS = (
            "git+",
            "://",
            "@",
            "==",
            ">=",
            "<=",
            "~=",
            "!=",
            "/",
            "[",
            " ",
        )
        if not any(m in target for m in _SPEC_MARKERS):
            close = difflib.get_close_matches(
                target.lower(),
                [e.name for e in catalog.entries],
                n=1,
                cutoff=0.7,
            )
            if close:
                print(
                    f"{target!r} is not a known plugin. Did you mean {close[0]!r}? "
                    f"(run: led-ticker plugin install {close[0]})",
                    file=sys.stderr,
                )
                return 2
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

    req_path = _requirements_path(config_path, config_explicit)
    # Docker and deploy/install.sh only read config/requirements-plugins.txt; warn
    # if we'd write somewhere else so the plugin isn't silently dropped on rebuild.
    outside_config = req_path.parent.name != "config"
    config_warning = (
        f"note: {req_path} is not under a 'config/' directory — Docker and "
        "deploy/install.sh read config/requirements-plugins.txt. Run from your "
        "project root or pass --config config/config.toml."
        if outside_config
        else None
    )

    if dry_run:
        print("Dry run — no changes made.")
        print(f"  requirement: {requirement}")
        print(f"  would update: {req_path}")
        if not save_only:
            print(
                f"  would run:   {sys.executable} -m pip install "
                f"-c <frozen-core-constraints> {requirement}"
            )
        if config_warning:
            print(config_warning, file=sys.stderr)
        return 0

    try:
        replaced_line = _update_requirements(req_path, requirement)
    except OSError as e:
        print(f"could not write {req_path}: {e}", file=sys.stderr)
        return 2
    if replaced_line is not None:
        print(f"Replaced {replaced_line.strip()!r} -> {requirement!r} in {req_path}")
    else:
        print(f"Added {requirement!r} in {req_path}")
    if config_warning:
        print(config_warning, file=sys.stderr)

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
