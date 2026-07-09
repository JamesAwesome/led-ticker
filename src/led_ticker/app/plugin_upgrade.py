"""Resolve "latest" for a manifest requirement line + the `plugin upgrade` verb.

Network-side counterpart of plugin_reconcile's stamp: the upgrade verb (CLI
`led-ticker plugin upgrade`, webui POST /api/store/upgrade) rewrites the
manifest line to the newest concrete pin; the boot reconcile then notices the
line changed and pip-reinstalls in place. This module NEVER runs on the boot
path — network calls are fine here, forbidden there.

Version compare is digit-tuple only (`^\\d+(\\.\\d+)*$`): stdlib-only (core
does not depend on `packaging`), and it excludes pre-release tags by
construction. Git tag convention: `<name>-vX.Y.Z` (see the docs-site plugins
page); `<name>` resolves subdirectory-basename → catalog-name → bare `v`.
"""

import datetime
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath

from led_ticker.app.plugin_cmd import (
    _config_warning,
    _dist_key,
    _find_requirement_lines,
    _requirement_key,
    _requirements_path,
    _strip_comment,
    _update_requirements,
)
from led_ticker.plugins_catalog import Catalog, load_catalog

_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")


class UpgradeError(Exception):
    """Resolution failed; str(e) is the user-facing reason. The manifest is
    never touched when this is raised."""


def _parse_version(text: str) -> tuple[int, ...] | None:
    """``"1.2.3"`` -> ``(1, 2, 3)``; None for anything else (incl. pre-releases)."""
    if not _VERSION_RE.match(text):
        return None
    return tuple(int(part) for part in text.split("."))


def _split_git_line(line: str) -> tuple[str, str | None, str | None]:
    """``git+https://host/o/r@ref#frag`` -> ``(git+https://host/o/r, ref, frag)``.

    The ``@`` cut happens after the URL path begins (a ref may contain ``/``,
    and ``user@host`` credentials must not be mistaken for a ref) — same rule
    as plugin_cmd._requirement_key.
    """
    spec, _, fragment = line.partition("#")
    spec = spec.strip()
    scheme = spec.find("//")
    path_start = spec.find("/", scheme + 2) if scheme != -1 else spec.find("/")
    at = spec.find("@", path_start) if path_start != -1 else spec.find("@")
    if at != -1:
        return spec[:at], spec[at + 1 :], fragment or None
    return spec, None, fragment or None


def _join_git_line(base: str, ref: str, fragment: str | None) -> str:
    """Inverse of ``_split_git_line`` for a concrete ref."""
    line = f"{base}@{ref}"
    if fragment:
        line += f"#{fragment}"
    return line


_PYPI_TIMEOUT_S = 15
_GIT_TIMEOUT_S = 30


def _fetch_pypi_json(package: str) -> dict:
    """GET https://pypi.org/pypi/<package>/json. Raises UpgradeError."""
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        with urllib.request.urlopen(url, timeout=_PYPI_TIMEOUT_S) as resp:  # noqa: S310
            return json.load(resp)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise UpgradeError(f"could not query PyPI for {package!r}: {e}") from e


def _run_git(args: list[str]) -> str:
    """Run ``git <args>`` and return stdout. Raises UpgradeError on any failure
    (nonzero exit, timeout, git binary absent)."""
    try:
        proc = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
        )
    except FileNotFoundError as e:
        raise UpgradeError("git is not installed on this host") from e
    except subprocess.TimeoutExpired as e:
        raise UpgradeError(f"git {args[0]} timed out after {_GIT_TIMEOUT_S}s") from e
    except OSError as e:
        raise UpgradeError(f"git {args[0]} failed to run: {e}") from e
    if proc.returncode != 0:
        raise UpgradeError(
            f"git {args[0]} failed: {(proc.stderr or '').strip() or proc.returncode}"
        )
    return proc.stdout


def _pypi_package_name(line: str) -> str:
    """Package name from a pypi requirement line (name up to the first
    version/marker/extra delimiter) — mirrors plugin_cmd._requirement_key's
    pypi branch, but preserves case (PyPI URLs are case-insensitive anyway)."""
    name = line
    for delim in ("==", ">=", "<=", "~=", "!=", ">", "<", "[", ";", " "):
        idx = name.find(delim)
        if idx != -1:
            name = name[:idx]
    return name.strip()


def _latest_pypi(line: str, fetch_json) -> str:
    package = _pypi_package_name(line)
    data = fetch_json(package)
    if not isinstance(data, dict):
        raise UpgradeError(f"unexpected PyPI response shape for {package!r}")
    releases = data.get("releases", {})
    if not isinstance(releases, dict):
        raise UpgradeError(f"unexpected PyPI response shape for {package!r}")
    best: tuple[int, ...] | None = None
    best_text: str | None = None
    try:
        for version_text, files in releases.items():
            parsed = _parse_version(version_text)
            if parsed is None:
                continue  # pre-release or unparseable
            if not isinstance(files, list):
                raise UpgradeError(f"unexpected PyPI response shape for {package!r}")
            if not files or all(f.get("yanked") for f in files):
                continue  # nothing installable
            if best is None or parsed > best:
                best, best_text = parsed, version_text
    except (TypeError, AttributeError) as e:
        raise UpgradeError(f"unexpected PyPI response shape for {package!r}") from e
    if best_text is None:
        raise UpgradeError(f"no installable release of {package!r} found on PyPI")
    return f"{package}=={best_text}"


def _tag_prefixes(fragment: str | None, catalog_name: str | None) -> list[str]:
    """Candidate tag prefixes in resolution order (docs-site tag convention):
    subdirectory basename -> catalog name -> bare ``v`` (single-plugin repos)."""
    prefixes: list[str] = []
    if fragment:
        for part in fragment.split("&"):
            if part.startswith("subdirectory="):
                name = PurePosixPath(part.removeprefix("subdirectory=")).name
                if name:
                    prefixes.append(f"{name}-v")
    if catalog_name:
        prefixes.append(f"{catalog_name}-v")
    prefixes.append("v")
    return prefixes


def _latest_git(line: str, catalog_name: str | None, run_git) -> str:
    base, ref, fragment = _split_git_line(line)
    url = base.removeprefix("git+")
    tags: list[str] = []
    for out_line in run_git(["ls-remote", "--tags", url]).splitlines():
        _, _, refname = out_line.partition("\t")
        tag = refname.strip().removeprefix("refs/tags/").removesuffix("^{}")
        if tag:
            tags.append(tag)
    for prefix in _tag_prefixes(fragment, catalog_name):
        best: tuple[int, ...] | None = None
        best_tag: str | None = None
        for tag in tags:
            if not tag.startswith(prefix):
                continue
            parsed = _parse_version(tag.removeprefix(prefix))
            if parsed is None:
                continue
            if best is None or parsed > best:
                best, best_tag = parsed, tag
        if best_tag is not None:
            return _join_git_line(base, best_tag, fragment)
    # No convention-matching tags: pin the tip of the tracked branch (or HEAD).
    out = run_git(["ls-remote", url, ref or "HEAD"])
    sha = out.split()[0] if out.split() else ""
    if not sha:
        raise UpgradeError(
            f"no matching version tags and could not resolve {ref or 'HEAD'!r} on {url}"
        )
    return _join_git_line(base, sha, fragment)


def resolve_latest(
    line: str,
    *,
    catalog_name: str | None = None,
    fetch_json=None,
    run_git=None,
) -> str:
    """The newest concrete pin for a (comment-stripped) manifest line.

    Returns a NEW comment-free line; equal to the input means already up to
    date. Raises UpgradeError with a user-facing reason on any failure — the
    caller must not have touched the manifest yet.
    """
    line = line.strip()
    if line.startswith("git+"):
        return _latest_git(line, catalog_name, run_git or _run_git)
    if line.startswith("-e ") or "://" in line:
        raise UpgradeError(
            f"don't know how to find the latest version of {line!r} — "
            "edit the manifest line by hand"
        )
    return _latest_pypi(line, fetch_json or _fetch_pypi_json)


_UPGRADE_HINT = (
    "The new version installs on next startup — run `docker compose restart` "
    "(no rebuild needed)."
)


def _catalog_name_for_key(key: str, catalog: Catalog) -> str | None:
    """The catalog entry NAME whose requirement dedup-key matches ``key`` —
    feeds the git tag-prefix convention. None for off-catalog lines."""
    for entry in catalog.entries:
        try:
            if _requirement_key(entry.requirement()) == key:
                return entry.name
        except ValueError:
            continue
    return None


def _upgrade_one_line(
    req_path: Path, old_line: str, catalog: Catalog, *, dry_run: bool
) -> int:
    """Resolve + rewrite ONE manifest line. Returns 0 (upgraded or up to date)
    or 1 (resolver failure; manifest untouched, reason printed)."""
    old_spec = _strip_comment(old_line)
    key = _requirement_key(old_spec)
    try:
        new_spec = resolve_latest(
            old_spec, catalog_name=_catalog_name_for_key(key, catalog)
        )
    except UpgradeError as e:
        print(f"{old_spec}: {e}", file=sys.stderr)
        return 1
    if new_spec == old_spec:
        print(f"{old_spec} is already up to date.")
        return 0
    if dry_run:
        print("Dry run — no changes made.")
        print(f"  would replace: {old_spec}")
        print(f"  with:          {new_spec}")
        return 0
    today = datetime.date.today().isoformat()
    provenance = f"# upgraded {today}, was {old_spec}"
    try:
        _update_requirements(req_path, new_spec, comment=provenance)
    except OSError as e:
        print(f"could not write {req_path}: {e}", file=sys.stderr)
        return 2
    print(f"Upgraded: {old_spec} -> {new_spec}")
    return 0


def cmd_upgrade(
    target: str | None,
    *,
    config_path: Path,
    config_explicit: bool = True,
    all_plugins: bool = False,
    dry_run: bool = False,
    catalog: Catalog | None = None,
) -> int:
    """Rewrite manifest line(s) to the latest version (no pip — the boot
    reconcile installs the change). Exit codes: 0 ok/up-to-date, 1 resolver
    failure (any, under --all), 2 usage/manifest error."""
    catalog = catalog or load_catalog()
    req_path = _requirements_path(config_path, config_explicit)
    config_warning = _config_warning(req_path)

    if all_plugins:
        if not req_path.exists():
            print(f"{req_path} does not exist — nothing to upgrade.", file=sys.stderr)
            return 2
        lines = [
            line
            for line in req_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not lines:
            print("No plugins declared — nothing to upgrade.")
            return 0
        worst = 0
        upgraded_any = False
        for line in lines:
            code = _upgrade_one_line(req_path, line, catalog, dry_run=dry_run)
            worst = max(worst, code)
            upgraded_any = upgraded_any or code == 0
        if config_warning:
            print(config_warning, file=sys.stderr)
        if not dry_run and upgraded_any:
            print(_UPGRADE_HINT)
        return worst

    assert target is not None  # cli enforces target XOR --all
    key = _dist_key(target, catalog)
    matches = _find_requirement_lines(req_path, key)
    if not matches:
        print(
            f"{target!r} is not declared in {req_path} — add it first "
            f"(led-ticker plugin add {target}).",
            file=sys.stderr,
        )
        return 2
    code = _upgrade_one_line(req_path, matches[-1], catalog, dry_run=dry_run)
    if config_warning:
        print(config_warning, file=sys.stderr)
    if code == 0 and not dry_run:
        print(_UPGRADE_HINT)
    return code
