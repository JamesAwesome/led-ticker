"""Shared helper for "this name didn't resolve" errors across every
registry (transitions, widgets, borders, color providers, animations).

A namespaced name (`<plugin>.<name>`) that fails to resolve almost
always means the owning plugin isn't installed. This helper turns that
into an actionable hint. It is pure and context-free — it does NOT
consult the loaded-plugin set, so it works from the bare runtime
registry lookups that have no `LoadedPlugins` handle.

The fix text points at `config/requirements-plugins.txt` today; when the
`led-ticker plugin install` CLI ships (plugin-registry project), this is
the one place to update.
"""


def plugin_hint(name: str, kind: str) -> str | None:
    """Return an install hint if `name` looks like a reference to an
    uninstalled plugin component, else None.

    A hint is returned only when the namespace (segment before the first
    dot) is a valid Python identifier — real plugin namespaces always are
    (e.g. ``baseball``, ``pool``, ``crypto``), while dotted non-plugin
    values like ``"1.5"`` or ``"."`` are not and fall through to None.

    `kind` is the human word for the registry — "transition", "widget",
    "border", "color provider", "animation".
    """
    if "." not in name:
        return None
    namespace = name.split(".", 1)[0]
    if not namespace.isidentifier():
        return None
    return (
        f"{name!r} looks like a plugin {kind}, but no {namespace!r} plugin "
        f"is loaded. Add the plugin to config/requirements-plugins.txt and "
        f"reinstall, or check the namespace. "
        f"See https://docs.ledticker.dev/plugins/."
    )
