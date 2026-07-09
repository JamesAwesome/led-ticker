"""Pure state derivation for the web Plugin Store (no rgbmatrix, no HTTP).

Combines the catalog, the manifest, status.json, and config references into
the payload the Store tab renders. Verified pure by tests/test_webui_purity.py.
"""

from pathlib import Path
from typing import Any

from led_ticker._config_scan import config_references
from led_ticker.app.plugin_cmd import (
    _declared_keys,
    _find_requirement_lines,
    _requirement_key,
    _strip_comment,
)
from led_ticker.plugins_catalog import Catalog, CatalogEntry, load_catalog


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
    refs: dict[str, list[dict[str, str]]] | None = None,
    stamp: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Derive the Plugin Store payload from all state sources.

    Returns a dict with:
      display_online    bool   — whether status.json was present/fresh
      pending_count     int    — entries in restart_to_activate state
      auth_required     bool   — whether a token is configured (UI shows prompt)
      plugins           list   — one entry per catalog plugin + any extras
        Each entry: namespace, name, summary, provides (dict of kind->list),
        source (str), state, removable (bool), in_use_by (list of {section,type})

    ``refs`` (config-reference map) is computed from ``config_path`` when None.
    Callers that already parsed it (e.g. remove_handler) may pass it in so
    config.toml is parsed once per request instead of twice.

    ``stamp`` is the reconcile installed-state stamp ({namespace:
    line-as-installed}, see ``plugin_reconcile.read_stamp`` /
    ``webui._read_stamp_readonly``). When a declared+active entry's current
    manifest line (comment-stripped) differs from its stamped line, the entry
    has been rewritten (by `plugin upgrade` or the Upgrade button) but the
    boot reconcile hasn't installed it yet — state becomes
    ``"restart_to_upgrade"``. ``None`` (the default) is a zero-behavior-change
    no-op — callers that don't pass a stamp see the pre-upgrade-feature
    behavior exactly.
    """
    catalog = catalog or load_catalog()

    display_online: bool = bool(status)
    active: set[str] = _active_namespaces(status)
    declared_keys: set[str] = _declared_keys(manifest_path)
    if refs is None:
        refs = config_references(config_path)

    # Build namespace -> CatalogEntry map for O(1) lookup.
    ns_to_entry: dict[str, CatalogEntry] = {e.namespace: e for e in catalog.entries}

    # Precompute each catalog entry's manifest dedup key (mirrors plugin_cmd.cmd_list).
    entry_key: dict[str, str] = {
        e.namespace: _requirement_key(e.requirement()) for e in catalog.entries
    }

    # Reverse map: dedup key -> namespaces that share it.  Multiple catalog
    # namespaces can resolve to ONE pip package (e.g. nyancat/pokeball/pacman/
    # sailor_moon all ship as led-ticker-flair).  Removing the manifest line
    # deletes the shared package, so the in-use / removable check must consider
    # every sibling namespace sharing the key — not just the requested one.
    key_to_namespaces: dict[str, set[str]] = {}
    for e in catalog.entries:
        key_to_namespaces.setdefault(entry_key[e.namespace], set()).add(e.namespace)

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
        elif is_active:
            # Catalog plugin is active (in status["plugins"]) but NOT declared in
            # the manifest — the user removed its manifest line while the display
            # process is still running it.  A restart is REQUIRED to actually
            # uninstall it (no manifest line → the reconciler drops it on the next
            # boot).  Surface that as `restart_to_remove` and count it as pending
            # so the restart banner appears; the row's action is "Install" (re-add
            # / undo, since it's no longer declared).
            state = "restart_to_remove"
        else:
            # Catalog plugin neither declared nor active — installable.
            state = "available"

        # Pending upgrade: manifest line rewritten (by `plugin upgrade` / the
        # webui Upgrade button) but the boot reconcile hasn't installed it yet.
        # The stamp records the line-as-installed; a declared entry whose
        # current (comment-stripped) manifest line differs is waiting on a
        # restart. Only overrides the "everything looks fine" state — a
        # restart_to_activate/restart_to_remove entry already shows a pending
        # badge of its own.
        if state == "active" and stamp is not None and ns in stamp:
            lines = _find_requirement_lines(manifest_path, entry_key[ns])
            if lines and _strip_comment(lines[-1]) != _strip_comment(stamp[ns]):
                state = "restart_to_upgrade"

        in_use = refs.get(ns, [])
        # Shared-package siblings: removing this manifest line drops the package
        # for ALL namespaces sharing its dedup key.  The widget is removable only
        # if NONE of those siblings is referenced by the running config.  in_use
        # surfaces this namespace's own refs (for the UI note); sibling_in_use
        # gates the removable flag.
        key = entry_key[ns]
        siblings = key_to_namespaces.get(key, {ns})
        sibling_in_use = any(refs.get(sib) for sib in siblings)
        removable: bool = bool(is_declared and not sibling_in_use)

        # Convert PluginProvides tuples to plain lists for JSON serialisation.
        provides: dict[str, list[str]] = {
            kind: list(names) for kind, names in entry.provides.groups()
        }

        # Primary source type string (e.g. "pypi" or "git").
        source: str = entry.sources[0].type if entry.sources else ""

        # Pack label: when multiple catalog namespaces share one pip package,
        # they form a "pack".  Derive a short human label from the dedup key by
        # stripping a leading "led-ticker-" prefix (e.g. "led-ticker-flair" →
        # "flair"); fall back to the full key when the prefix is absent.
        is_pack = len(siblings) > 1
        pack_label: str = ""
        pack_members: list[str] = []
        if is_pack:
            pack_label = key.removeprefix("led-ticker-")
            pack_members = sorted(siblings)

        plugins.append(
            {
                "namespace": ns,
                "name": entry.name,
                "summary": entry.summary,
                "homepage": getattr(entry, "homepage", ""),
                "provides": provides,
                "source": source,
                "state": state,
                "removable": removable,
                "in_use_by": in_use,
                "pack": pack_label,
                "pack_members": pack_members,
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
                "pack": "",
                "pack_members": [],
            }
        )

    # Count DISTINCT pending packages, not namespaces.  Multiple catalog
    # namespaces can share one pip package (e.g. nyancat/pokeball/pacman/
    # sailor_moon → led-ticker-flair); installing that single package marks all
    # four sibling rows restart_to_activate, but it is ONE pending install — so
    # dedup by the manifest requirement key (entry_key) before counting.
    # `restart_to_remove` (active-but-undeclared: the user removed the manifest
    # line, restart needed to actually uninstall) is also pending — count it so
    # the restart banner appears for removals too. `restart_to_upgrade` (manifest
    # line rewritten to a newer version, restart needed to install it) is the
    # same class of pending restart.
    _PENDING_STATES = ("restart_to_activate", "restart_to_remove", "restart_to_upgrade")
    pending_count = len(
        {
            entry_key[p["namespace"]]
            for p in plugins
            if p["state"] in _PENDING_STATES
            and p["namespace"] in entry_key  # catalog entries only
        }
    )

    return {
        "display_online": display_online,
        "pending_count": pending_count,
        "auth_required": token_configured,
        "plugins": plugins,
    }


# States that indicate some form of install presence — coarsened to "installed"
# for anonymous callers (avoids leaking restart-to-activate / external-install
# distinctions that hint at the operator's deployment state).  "installed" is
# itself in the set so a second redact is a fixed point (idempotent): coarsening
# an already-coarsened payload keeps "installed" rather than dropping it back to
# "available".
_INSTALLED_STATES = frozenset(
    {
        "active",
        "restart_to_activate",
        "restart_to_remove",
        "restart_to_upgrade",
        "externally_installed",
        "installed",
    }
)


def redact_anonymous(payload: dict) -> dict:
    """Return a copy of the store payload safe for unauthenticated callers.

    Catalog-browsable fields (namespace, name, summary, provides, source,
    auth_required) are preserved verbatim.  Config-derived or deployment-detail
    fields are redacted:

    - ``in_use_by``    → [] (config section titles are private)
    - ``state``        → "installed" if active/restart_to_activate/
      restart_to_remove, else "available"
    - ``removable``    → False (no remove button without auth)
    - ``pending_count``→ 0 (leaks how many plugins are pending restart)
    - ``display_online``→ dropped (display liveness is deployment state — the
      operator chose to hide it from unauthenticated callers, same class as the
      external-install / pending detail above; the frontend treats a missing
      field as "unknown" and shows no offline banner)

    ``externally_installed`` entries are DROPPED entirely: they are host-only,
    off-catalog plugin namespaces the operator pip-installed (pure deployment
    data, never catalog-browsable).  Surfacing even the namespace to an
    unauthenticated caller would leak the operator's private deployment state —
    exactly the "external-install distinctions" this redaction exists to hide.

    The input dict is not mutated; a new dict (and new plugin list) is returned.
    Pure: no rgbmatrix, no I/O.
    """
    redacted_plugins = []
    for plugin in payload.get("plugins", []):
        if plugin.get("state") == "externally_installed":
            # Off-catalog, host-installed namespace — not browsable; drop it.
            continue
        coarse_state = (
            "installed" if plugin.get("state") in _INSTALLED_STATES else "available"
        )
        redacted_plugins.append(
            {
                **plugin,
                "in_use_by": [],
                "state": coarse_state,
                "removable": False,
            }
        )

    out = {
        **payload,
        "pending_count": 0,
        "plugins": redacted_plugins,
    }
    # Drop deployment-liveness from anonymous callers (idempotent: pop is a no-op
    # on an already-redacted payload).
    out.pop("display_online", None)
    return out
