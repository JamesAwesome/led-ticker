"""Static analysis of a config's plugin dependencies — no widget build, no
rgbmatrix, no HTTP. Holds the Store's config_references walk plus
required_plugins() and the startup dependency warning. Pure; safe to import
from the display process (must not import webui/aiohttp)."""

import re
import tomllib
from pathlib import Path

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

    def add(ns_source: str, section: str) -> None:
        if "." in ns_source:
            ns = ns_source.split(".")[0]
            out.setdefault(ns, []).append({"section": section, "type": ns_source})

    def add_emoji_refs(text: str, section: str) -> None:
        for m in _EMOJI_TOKEN.finditer(text):
            out.setdefault(m.group(1), []).append(
                {"section": section, "type": m.group(0)}
            )

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
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}
    return _references_from_data(data)
