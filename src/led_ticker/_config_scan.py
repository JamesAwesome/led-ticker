"""Static analysis of a config's plugin dependencies — no widget build, no
rgbmatrix, no HTTP. Holds the Store's config_references walk plus
required_plugins() and the startup dependency warning. Pure; safe to import
from the display process (must not import webui/aiohttp)."""

import re
import tomllib
from collections.abc import Iterable
from pathlib import Path

from led_ticker.app.plugin_cmd import _requirement_key
from led_ticker.plugins_catalog import load_catalog

_TRANSITION_KEYS = ("transition", "entry_transition", "widget_transition")

# Inline emoji token in widget text, e.g. ":pokeball.ball:". A namespaced slug
# carries a dot; the namespace is the leading segment.
_EMOJI_TOKEN = re.compile(r":([a-z0-9_]+)\.[a-z0-9_.]+:")


def _references_from_data(data: dict) -> dict[str, list[dict[str, str]]]:
    """The recursive reference walk over already-parsed TOML. Returns
    {namespace: [{"section", "type"}, ...]} for every dotted type/transition
    value and inline :ns.slug: emoji. UNFILTERED — includes non-catalog
    namespaces (the Store needs them for in_use_by)."""
    out: dict[str, list[dict[str, str]]] = {}
    # Dedup: one entry per unique (ns, section, type). Emoji-heavy configs
    # otherwise flood the Store's in-use note — a title with two identical
    # tokens plus widget text with two more yielded four copies of the same
    # reference (the baseball-card wall-of-text regression). Order preserved.
    seen: set[tuple[str, str, str]] = set()

    def _add_ref(ns: str, section: str, ref_type: str) -> None:
        key = (ns, section, ref_type)
        if key in seen:
            return
        seen.add(key)
        out.setdefault(ns, []).append({"section": section, "type": ref_type})

    def add(ns_source: str, section: str) -> None:
        if "." in ns_source:
            _add_ref(ns_source.split(".")[0], section, ns_source)

    def add_emoji_refs(text: str, section: str) -> None:
        for m in _EMOJI_TOKEN.finditer(text):
            _add_ref(m.group(1), section, m.group(0))

    def walk(obj: object, section: str) -> None:
        if isinstance(obj, dict):
            title = obj.get("title")
            sec = title.get("text") if isinstance(title, dict) else section
            sec = sec if isinstance(sec, str) and sec else section
            t = obj.get("type")
            if isinstance(t, str):
                add(t, sec)
            for key in _TRANSITION_KEYS:
                v = obj.get(key)
                if isinstance(v, str):
                    add(v, sec)
            for v in obj.values():
                if isinstance(v, str):
                    add_emoji_refs(v, sec)
                walk(v, sec)
        elif isinstance(obj, list):
            for v in obj:
                if isinstance(v, str):
                    add_emoji_refs(v, section)
                walk(v, section)

    walk(data, "config")
    return out


def config_references(config_path: Path) -> dict[str, list[dict[str, str]]]:
    """Plugin references in a config file, keyed by namespace. Used by the web
    Store. Missing/unparseable file -> {}."""
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except OSError, tomllib.TOMLDecodeError, UnicodeDecodeError:
        return {}
    return _references_from_data(data)


def _load(source: str | Path) -> dict:
    try:
        return tomllib.loads(Path(source).read_text(encoding="utf-8"))
    except OSError, tomllib.TOMLDecodeError, UnicodeDecodeError:
        return {}


def _namespace_to_package() -> dict[str, str]:
    """Catalog-derived namespace -> pip package. The same expression the Store
    uses; flair's four namespaces collapse to led-ticker-flair. Derived from
    load_catalog() (the drift-guarded SoT) — no hand map.

    NOTE: the "pip package name" guarantee holds because every catalog source is
    a pypi package today. A future git/#subdirectory source would yield a dedup
    key, not a pip-installable name."""
    return {
        e.namespace: _requirement_key(e.requirement()) for e in load_catalog().entries
    }


def _referenced_namespaces(data: dict) -> set[str]:
    """All plugin namespaces a config references — the recursive walk PLUS the
    two deploy surfaces the Store walk omits: top-level [transitions]
    default/between_sections, and [display] backend (a bare namespace).
    UNFILTERED (includes non-catalog namespaces and built-in backends)."""
    namespaces = set(_references_from_data(data))
    trans = data.get("transitions")
    if isinstance(trans, dict):
        for key in ("default", "between_sections"):
            v = trans.get(key)
            if isinstance(v, str) and "." in v:
                namespaces.add(v.split(".")[0])
    # [display] backend is a BARE namespace (no dot), so the dotted walk misses
    # it. Scoped to exactly this key so a stray free-text value can't over-count.
    # Sharp edge: if a future catalog namespace ever equals a built-in backend
    # name (rgbmatrix/headless), this would false-flag. None collide today.
    display = data.get("display")
    if isinstance(display, dict):
        backend = display.get("backend")
        if isinstance(backend, str):
            namespaces.add(backend)
    return namespaces


def required_plugins(source: dict | str | Path) -> set[str]:
    """Pip packages a config requires, from its ACTIVE (uncommented) plugin
    references. Parses with tomllib (comments excluded); never builds widgets,
    so it works whether or not the plugins are installed. Non-plugin dotted
    values and non-catalog namespaces fall through."""
    data = source if isinstance(source, dict) else _load(source)
    nsmap = _namespace_to_package()
    return {nsmap[ns] for ns in _referenced_namespaces(data) if ns in nsmap}


def plugin_dependency_warning(
    config_source: dict | str | Path,
    loaded_namespaces: Iterable[str],
    failed_namespaces: Iterable[str],
) -> str | None:
    """A one-shot WARNING message when a config needs plugins that aren't
    loaded, else None. Distinguishes absent (install) from installed-but-failed
    (fix). All three inputs use plugin NAMESPACES; packages are derived here."""
    data = config_source if isinstance(config_source, dict) else _load(config_source)
    nsmap = _namespace_to_package()
    required = required_plugins(data)
    installed = {nsmap[ns] for ns in loaded_namespaces if ns in nsmap}
    failed_pkgs = {nsmap[ns] for ns in failed_namespaces if ns in nsmap}
    absent = required - installed - failed_pkgs
    broken = required & failed_pkgs
    if not absent and not broken:
        return None
    lines: list[str] = []
    if absent:
        lines.append(
            "Config references plugins that aren't installed: "
            + ", ".join(sorted(absent))
            + " — their widgets/transitions will be skipped. Install them "
            "(config/requirements-plugins.txt or the web UI Store) and restart."
        )
    if broken:
        lines.append(
            "Installed but failed to load: "
            + ", ".join(sorted(broken))
            + " — fix or remove it (see the plugin-load errors above)."
        )
    lines.append("https://docs.ledticker.dev/plugins/")
    return "\n".join(lines)
