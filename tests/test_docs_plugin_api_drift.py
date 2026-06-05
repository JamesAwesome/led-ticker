"""Tripwire test for docs/site/.../plugins/api-reference.mdx drift.

The plugin API reference page hand-curates the public ``led_ticker.plugin``
surface: the registration methods on ``PluginAPI`` and the names in
``__all__``. Hand curation buys readable, cross-linked tables that pure
autogeneration would lose — but it can drift when ``plugin.py`` changes.

This test is that pressure. It asserts:
- the registration methods documented in the page's ``api-methods`` region
  exactly match ``PluginAPI``'s public methods, and
- the names documented in the page's ``api-exports`` region exactly match
  ``led_ticker.plugin.__all__``.

Marked regions in the .mdx make parsing robust:

    <!-- api-methods:start --> ... <!-- api-methods:end -->
    <!-- api-exports:start --> ... <!-- api-exports:end -->

When ``plugin.py``'s public surface changes, update the page inside those
markers — the test fails loudly (naming the missing/extra symbols) until the
page and the code agree.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from led_ticker import plugin
from led_ticker.plugin import PluginAPI

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE_PATH = (
    REPO_ROOT
    / "docs"
    / "site"
    / "src"
    / "content"
    / "docs"
    / "plugins"
    / "api-reference.mdx"
)

_FIRST_COL_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|", re.MULTILINE)


def _region(page_text: str, name: str) -> str:
    """Return the text between ``<!-- name:start -->`` and ``<!-- name:end -->``."""
    match = re.search(
        rf"<!--\s*{re.escape(name)}:start\s*-->(.*?)<!--\s*{re.escape(name)}:end\s*-->",
        page_text,
        re.DOTALL,
    )
    assert match, f"Marker region {name!r} not found in {PAGE_PATH}"
    return match.group(1)


def _documented_methods(page_text: str) -> set[str]:
    """Method names from ``api.<name>(`` occurrences in the api-methods region."""
    return set(re.findall(r"api\.(\w+)", _region(page_text, "api-methods")))


def _documented_exports(page_text: str) -> set[str]:
    """First-column backtick names in the api-exports region, call sigs stripped."""
    names: set[str] = set()
    for cell in _FIRST_COL_RE.findall(_region(page_text, "api-exports")):
        names.add(cell.split("(", 1)[0].strip())
    return names


def _real_methods() -> set[str]:
    """Public (non-underscore) methods on PluginAPI — the registration surface."""
    return {
        name
        for name, _ in inspect.getmembers(PluginAPI, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def test_docs_page_exists() -> None:
    assert PAGE_PATH.exists(), f"Plugin API reference page not found at {PAGE_PATH}"


def test_registration_methods_match() -> None:
    page_text = PAGE_PATH.read_text()
    documented = _documented_methods(page_text)
    real = _real_methods()
    missing = real - documented
    extra = documented - real
    assert not missing, (
        f"PluginAPI methods missing from the API reference methods tables: "
        f"{sorted(missing)}.\n"
        "Add a row inside the <!-- api-methods --> region of "
        "docs/site/src/content/docs/plugins/api-reference.mdx."
    )
    assert not extra, (
        f"API reference methods tables list names that aren't public PluginAPI "
        f"methods: {sorted(extra)}.\n"
        "They were renamed/removed in src/led_ticker/plugin.py, or the table "
        "has a typo."
    )


def test_exported_names_match() -> None:
    page_text = PAGE_PATH.read_text()
    documented = _documented_exports(page_text)
    real = set(plugin.__all__)
    missing = real - documented
    extra = documented - real
    assert not missing, (
        f"Names in led_ticker.plugin.__all__ missing from the API reference "
        f"exports tables: {sorted(missing)}.\n"
        "Add a row inside the <!-- api-exports --> region of "
        "docs/site/src/content/docs/plugins/api-reference.mdx."
    )
    assert not extra, (
        f"API reference exports tables list names not in "
        f"led_ticker.plugin.__all__: {sorted(extra)}.\n"
        "They were removed from __all__, or the table has a typo."
    )
