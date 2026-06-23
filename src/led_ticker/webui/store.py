"""Pure state derivation for the web Plugin Store (no rgbmatrix, no HTTP).

Combines the catalog, the manifest, status.json, and config references into
the payload the Store tab renders. Verified pure by tests/test_webui_purity.py.
"""

import tomllib
from pathlib import Path

_TRANSITION_KEYS = ("transition", "entry_transition", "widget_transition")


def config_references(config_path: Path) -> dict[str, list[dict[str, str]]]:
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}
    out: dict[str, list[dict[str, str]]] = {}

    def add(ns_source: str, section: str) -> None:
        if "." in ns_source:
            ns = ns_source.split(".")[0]
            out.setdefault(ns, []).append({"section": section, "type": ns_source})

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
                walk(v, sec)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, section)

    walk(data, "config")
    return out
