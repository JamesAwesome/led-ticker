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

import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import PurePosixPath

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
    releases = data.get("releases", {})
    best: tuple[int, ...] | None = None
    best_text: str | None = None
    for version_text, files in releases.items():
        parsed = _parse_version(version_text)
        if parsed is None:
            continue  # pre-release or unparseable
        if not files or all(f.get("yanked") for f in files):
            continue  # nothing installable
        if best is None or parsed > best:
            best, best_text = parsed, version_text
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
