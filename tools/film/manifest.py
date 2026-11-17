"""Segment names for the clip tool: a ``# film: <name>`` comment on a
``[[playlist.section]]`` header line names the clip that section produces.
Slates carry no comment and are skipped. tomllib drops comments, so this
is a regex over the raw text."""

import re

_HEADER = re.compile(
    r"^\s*\[\[playlist\.section\]\]\s*#\s*film:\s*(\S+)\s*$", re.MULTILINE
)
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ManifestError(ValueError):
    pass


def film_names(toml_text: str) -> list[str]:
    names: list[str] = []
    for m in _HEADER.finditer(toml_text):
        name = m.group(1)
        if not _NAME.match(name):
            raise ManifestError(f"bad film name {name!r}: use [a-z0-9][a-z0-9-]*")
        if name in names:
            raise ManifestError(f"duplicate film name {name!r}")
        names.append(name)
    return names
