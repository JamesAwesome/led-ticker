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

import re

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
