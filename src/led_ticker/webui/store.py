"""Pure state derivation for the web Plugin Store (no rgbmatrix, no HTTP).

Combines the catalog, the manifest, status.json, and config references into
the payload the Store tab renders. Verified pure by tests/test_webui_purity.py.
"""

import tomllib
from pathlib import Path
from typing import Any

from led_ticker.app.plugin_cmd import _declared_keys, _requirement_key
from led_ticker.plugins_catalog import Catalog, CatalogEntry, load_catalog

_TRANSITION_KEYS = ("transition", "entry_transition", "widget_transition")


def config_references(config_path: Path) -> dict[str, list[dict[str, str]]]:
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except OSError, tomllib.TOMLDecodeError, UnicodeDecodeError:
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


def _active_namespaces(status: dict[str, Any]) -> set[str]:
    """The set of plugin namespaces currently loaded according to status.json.

    status["plugins"] is a list of dicts each carrying a "namespace" key, as
    written by app/run.py. Returns an empty set when the status is absent or
    the plugins key is missing.
    """
    plugins = status.get("plugins", [])
    return {p["namespace"] for p in plugins if isinstance(p, dict) and "namespace" in p}


def build_store(
    *,
    manifest_path: Path,
    config_path: Path,
    status: dict[str, Any],
    token_configured: bool,
    catalog: Catalog | None = None,
) -> dict[str, Any]:
    """Derive the Plugin Store payload from all state sources.

    Returns a dict with:
      display_online    bool   — whether status.json was present/fresh
      pending_count     int    — entries in restart_to_activate state
      auth_required     bool   — whether a token is configured (UI shows prompt)
      plugins           list   — one entry per catalog plugin + any extras
        Each entry: namespace, name, summary, provides (dict of kind->list),
        source (str), state, removable (bool), in_use_by (list of {section,type})
    """
    catalog = catalog or load_catalog()

    display_online: bool = bool(status)
    active: set[str] = _active_namespaces(status)
    declared_keys: set[str] = _declared_keys(manifest_path)
    refs = config_references(config_path)

    # Build namespace -> CatalogEntry map for O(1) lookup.
    ns_to_entry: dict[str, CatalogEntry] = {e.namespace: e for e in catalog.entries}

    # Precompute each catalog entry's manifest dedup key (mirrors plugin_cmd.cmd_list).
    entry_key: dict[str, str] = {
        e.namespace: _requirement_key(e.requirement()) for e in catalog.entries
    }

    plugins: list[dict[str, Any]] = []

    # Catalog entries — one entry each regardless of install state.
    for entry in catalog.entries:
        ns = entry.namespace
        is_declared = entry_key[ns] in declared_keys
        is_active = ns in active

        if is_declared and is_active:
            state = "active"
        elif is_declared:
            state = "restart_to_activate"
        else:
            # Edge case: catalog plugin is active (in status["plugins"]) but NOT
            # declared in the manifest.  This can happen when a plugin was installed
            # outside the manifest (e.g. manually pip-installed), or if the manifest
            # was edited to remove it while the display process is still running.
            # Under Spec 1's true-sync guarantee this should be rare; on the next
            # restart the plugin will be uninstalled (no manifest line → reconciler
            # drops it).  We represent it as "available" here because:
            #   - it does NOT appear in the externally_installed bucket (that is only
            #     for namespaces absent from the catalog entirely), and
            #   - clicking Install correctly adds the manifest line, which is the
            #     right remediation action for the user.
            # "available" is the v1-acceptable representation; a future v2 could
            # introduce "catalog_active_undeclared" if the distinction matters.
            state = "available"

        in_use = refs.get(ns, [])
        removable: bool = bool(is_declared and not in_use)

        # Convert PluginProvides tuples to plain lists for JSON serialisation.
        provides: dict[str, list[str]] = {
            kind: list(names) for kind, names in entry.provides.groups()
        }

        # Primary source type string (e.g. "pypi" or "git").
        source: str = entry.sources[0].type if entry.sources else ""

        plugins.append(
            {
                "namespace": ns,
                "name": entry.name,
                "summary": entry.summary,
                "provides": provides,
                "source": source,
                "state": state,
                "removable": removable,
                "in_use_by": in_use,
            }
        )

    # Externally installed: namespaces active in status but absent from catalog.
    catalog_namespaces = set(ns_to_entry.keys())
    for ns in sorted(active - catalog_namespaces):
        in_use = refs.get(ns, [])
        plugins.append(
            {
                "namespace": ns,
                "name": ns,
                "summary": "",
                "provides": {},
                "source": "",
                "state": "externally_installed",
                "removable": False,
                "in_use_by": in_use,
            }
        )

    pending_count = sum(1 for p in plugins if p["state"] == "restart_to_activate")

    return {
        "display_online": display_online,
        "pending_count": pending_count,
        "auth_required": token_configured,
        "plugins": plugins,
    }
