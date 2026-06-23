"""Bundled plugin catalog: maps a friendly plugin name to install source(s).

The source of truth is `plugins_catalog.json` (shipped in the package, also
rendered on the docs site). `led-ticker plugin list/search/install` reads it
offline via `load_catalog()`. Sources are pip-style — a plugin can be installed
from a `git` URL and/or a `pypi` package, mirroring how pip accepts both. v1
first-party entries are git-only; a `pypi` source is added later (PyPI publishing
slice) with no schema change.
"""

import functools
import json
from importlib import resources

import attrs

_CATALOG_RESOURCE = "plugins_catalog.json"
SCHEMA_VERSION = 3
_VALID_SOURCE_TYPES = ("git", "pypi")

# Every surface a plugin can register (see led_ticker.plugin PluginAPI).
# Canonical order = list/display order. `emoji` covers the lo-res + hi-res pair.
_SURFACE_KINDS = (
    "widgets",
    "transitions",
    "emoji",
    "fonts",
    "borders",
    "color_providers",
    "animations",
    "easing",
)

# Order the install hint picks a "primary" surface in (first non-empty wins).
_PRIMARY_ORDER = (
    "widgets",
    "transitions",
    "color_providers",
    "animations",
    "borders",
    "emoji",
    "fonts",
    "easing",
)


@attrs.define(frozen=True)
class PluginProvides:
    """The typed surface a catalog plugin contributes, grouped by kind.

    Each field is a tuple of fully-qualified ``namespace.name`` strings. Fields
    are named exactly as ``_SURFACE_KINDS`` so the loader can splat a dict in.
    """

    widgets: tuple[str, ...] = ()
    transitions: tuple[str, ...] = ()
    emoji: tuple[str, ...] = ()
    fonts: tuple[str, ...] = ()
    borders: tuple[str, ...] = ()
    color_providers: tuple[str, ...] = ()
    animations: tuple[str, ...] = ()
    easing: tuple[str, ...] = ()

    def all_names(self) -> tuple[str, ...]:
        """Every provided name across all kinds, in canonical order."""
        return tuple(name for kind in _SURFACE_KINDS for name in getattr(self, kind))

    def is_empty(self) -> bool:
        """True when no names are registered in any kind."""
        return not self.all_names()

    def groups(self) -> list[tuple[str, tuple[str, ...]]]:
        """Non-empty ``(kind, names)`` pairs in canonical order (for display)."""
        return [
            (kind, getattr(self, kind))
            for kind in _SURFACE_KINDS
            if getattr(self, kind)
        ]

    def primary(self) -> tuple[str, str] | None:
        """The ``(kind, first_name)`` for the install hint, by priority order."""
        for kind in _PRIMARY_ORDER:
            names = getattr(self, kind)
            if names:
                return (kind, names[0])
        return None


@attrs.define(frozen=True)
class CatalogSource:
    """One installable source for a plugin (a `git` URL or a `pypi` package)."""

    type: str  # "git" | "pypi"
    url: str | None = None  # git
    ref: str | None = None  # git — recommended pin (tag/branch/sha)
    subdirectory: str | None = None  # git — package path within a monorepo
    package: str | None = None  # pypi
    version: str | None = None  # pypi — recommended pin (may be None until published)


@attrs.define(frozen=True)
class CatalogEntry:
    """A catalog plugin: a friendly name plus its install source(s)."""

    name: str
    namespace: str
    summary: str
    homepage: str
    provides: PluginProvides
    sources: tuple[CatalogSource, ...]

    def source_for(self, source_type: str | None) -> CatalogSource:
        """Return the requested source, or the first (preferred) when None."""
        if source_type is None:
            return self.sources[0]
        for src in self.sources:
            if src.type == source_type:
                return src
        available = ", ".join(s.type for s in self.sources)
        raise ValueError(
            f"plugin {self.name!r} has no {source_type!r} source "
            f"(available: {available})"
        )

    def requirement(self, *, source: str | None = None, pinned: bool = True) -> str:
        """Build the pip requirement line for this plugin.

        git pinned   -> ``git+https://host/owner/repo.git@<ref>``
        git unpinned -> ``git+https://host/owner/repo.git@main``
        pypi pinned  -> ``package==<version>`` (when a version is declared)
        pypi unpinned/unpublished -> ``package``
        """
        src = self.source_for(source)
        if src.type == "git":
            assert src.url is not None  # guaranteed for git sources (see _parse_source)
            base = src.url.removesuffix(".git")
            ref = src.ref if (pinned and src.ref) else "main"
            req = f"git+{base}.git@{ref}"
            if src.subdirectory:
                req += f"#subdirectory={src.subdirectory}"
            return req
        # pypi
        if pinned and src.version:
            return f"{src.package}=={src.version}"
        return str(src.package)


@attrs.define(frozen=True)
class Catalog:
    """The parsed plugin catalog."""

    entries: tuple[CatalogEntry, ...]

    def get(self, name: str) -> CatalogEntry | None:
        """Look up a plugin by name, case-insensitively (matches search())."""
        key = name.lower()
        for entry in self.entries:
            if entry.name.lower() == key:
                return entry
        return None

    def search(self, query: str) -> list[CatalogEntry]:
        """Case-insensitive substring match over name, summary, and provides."""
        q = query.lower()
        out: list[CatalogEntry] = []
        for entry in self.entries:
            haystack = " ".join(
                [entry.name, entry.summary, *entry.provides.all_names()]
            ).lower()
            if q in haystack:
                out.append(entry)
        return out


def _parse_source(raw: dict) -> CatalogSource:
    stype = raw.get("type")
    if stype not in _VALID_SOURCE_TYPES:
        raise ValueError(
            f"catalog source has invalid type {stype!r} "
            f"(expected one of {_VALID_SOURCE_TYPES})"
        )
    if stype == "git":
        if not raw.get("url"):
            raise ValueError("git catalog source is missing 'url'")
        return CatalogSource(
            type="git",
            url=raw["url"],
            ref=raw.get("ref", "main"),
            subdirectory=raw.get("subdirectory"),
        )
    if not raw.get("package"):
        raise ValueError("pypi catalog source is missing 'package'")
    return CatalogSource(
        type="pypi", package=raw["package"], version=raw.get("version")
    )


def _parse_provides(raw: object) -> PluginProvides:
    """Parse the typed `provides` object. Rejects a non-object, unknown surface
    kinds (typo guard), and non-string entries. Absent/None -> all-empty."""
    if raw is None:
        return PluginProvides()
    if not isinstance(raw, dict):
        raise ValueError(
            f"catalog entry 'provides' must be an object, got {type(raw).__name__}"
        )
    unknown = [k for k in raw if k not in _SURFACE_KINDS]
    if unknown:
        raise ValueError(
            f"catalog 'provides' has unknown surface kind(s) {sorted(unknown)} "
            f"(valid: {list(_SURFACE_KINDS)})"
        )
    kwargs: dict[str, tuple[str, ...]] = {}
    for kind in _SURFACE_KINDS:
        vals = raw.get(kind, [])
        if not isinstance(vals, list) or not all(isinstance(v, str) for v in vals):
            raise ValueError(f"catalog 'provides.{kind}' must be a list of strings")
        kwargs[kind] = tuple(vals)
    return PluginProvides(**kwargs)


def _parse_entry(raw: dict) -> CatalogEntry:
    for key in ("name", "namespace", "summary", "sources"):
        if key not in raw:
            raise ValueError(f"catalog entry is missing {key!r}: {raw!r}")
    sources = tuple(_parse_source(s) for s in raw["sources"])
    if not sources:
        raise ValueError(f"catalog entry {raw['name']!r} has no sources")
    return CatalogEntry(
        name=raw["name"],
        namespace=raw["namespace"],
        summary=raw["summary"],
        homepage=raw.get("homepage", ""),
        provides=_parse_provides(raw.get("provides")),
        sources=sources,
    )


def _parse_catalog(data: dict) -> Catalog:
    """Validate a parsed catalog document and build the Catalog."""
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"plugins_catalog.json schema_version {version!r} is not the "
            f"supported version {SCHEMA_VERSION}"
        )
    entries = tuple(_parse_entry(e) for e in data.get("plugins", []))
    return Catalog(entries=entries)


@functools.cache
def load_catalog() -> Catalog:
    """Load + validate the bundled catalog. Raises ValueError on a malformed file.

    Cached: the catalog is an immutable bundled package resource, so re-parsing
    it on every reconcile pass / CLI call is pure waste. The Catalog is frozen,
    so sharing one instance is safe.
    """
    text = (
        resources.files("led_ticker")
        .joinpath(_CATALOG_RESOURCE)
        .read_text(encoding="utf-8")
    )
    return _parse_catalog(json.loads(text))
