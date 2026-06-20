"""Tripwire: the Available-plugins page documents exactly the catalog's plugins.

`available.mdx` renders each plugin's facts via `<PluginCatalog name="X" />`,
fed by the bundled `plugins_catalog.json`. The component guarantees the *facts*
of each documented plugin can't drift; this test guarantees the documented
*set* matches the catalog — catching a plugin added to the catalog but not given
a docs section, a removed plugin left in the docs, or a typo'd `name`.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = REPO_ROOT / "src" / "led_ticker" / "plugins_catalog.json"
PAGE = (
    REPO_ROOT
    / "docs"
    / "site"
    / "src"
    / "content"
    / "docs"
    / "plugins"
    / "available.mdx"
)

_USAGE_RE = re.compile(r'<PluginCatalog\s+name="([^"]+)"\s*/>')


def _catalog_names() -> set[str]:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    return {p["name"] for p in data["plugins"]}


def _documented_names() -> set[str]:
    return set(_USAGE_RE.findall(PAGE.read_text(encoding="utf-8")))


def test_available_page_documents_exactly_the_catalog():
    catalog = _catalog_names()
    documented = _documented_names()
    missing = catalog - documented
    extra = documented - catalog
    assert not missing, f"catalog plugins missing a docs section: {sorted(missing)}"
    assert not extra, f"docs reference unknown plugins: {sorted(extra)}"


def test_every_plugin_is_documented_once():
    # No accidental duplicate <PluginCatalog name="x"/> for the same plugin.
    names = _USAGE_RE.findall(PAGE.read_text(encoding="utf-8"))
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"plugins rendered more than once: {sorted(dupes)}"
