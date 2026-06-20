"""Bundled plugin catalog: integrity + the requirement() builder."""

import pytest

from led_ticker.plugins_catalog import (
    Catalog,
    CatalogEntry,
    CatalogSource,
    _parse_entry,
    _parse_source,
    load_catalog,
)

# --- bundled catalog integrity (guards a hand-edited plugins_catalog.json) ---


def test_bundled_catalog_loads_and_is_v1():
    cat = load_catalog()
    assert isinstance(cat, Catalog)
    assert cat.entries  # non-empty


def test_bundled_catalog_has_the_first_party_plugins():
    cat = load_catalog()
    names = {e.name for e in cat.entries}
    assert {"pool", "baseball", "crypto", "calendar"} <= names


def test_bundled_entries_are_well_formed():
    cat = load_catalog()
    for e in cat.entries:
        assert e.name and e.namespace and e.summary
        assert e.sources, f"{e.name} has no sources"
        for s in e.sources:
            assert s.type in ("git", "pypi")
            if s.type == "git":
                assert s.url and s.ref
            else:
                assert s.package


def test_pool_provides_monitor():
    cat = load_catalog()
    assert "pool.monitor" in cat.get("pool").provides


def test_baseball_provides_all_current_widgets():
    # Locks the catalog against the scores/standings-only drift: the plugin's
    # register() on main contributes five widgets. (Transitions + the emoji are
    # described in the summary, which the search haystack covers.)
    cat = load_catalog()
    assert set(cat.get("baseball").provides) == {
        "baseball.scores",
        "baseball.standings",
        "baseball.promotions",
        "baseball.statcast",
        "baseball.attendance",
    }


def test_search_finds_new_baseball_widgets_and_surfaces():
    cat = load_catalog()
    # a newer widget (via provides), a transition + the emoji (via summary)
    assert "baseball" in {e.name for e in cat.search("attendance")}
    assert "baseball" in {e.name for e in cat.search("statcast")}
    assert "baseball" in {e.name for e in cat.search("roll")}
    # "baseball.ball" is not a substring of the name/provides, so a hit proves
    # the emoji slug is discoverable via the summary.
    assert "baseball" in {e.name for e in cat.search("baseball.ball")}


# --- requirement() builder ---


def _git_entry(ref="v1.2.0"):
    return CatalogEntry(
        name="pool",
        namespace="pool",
        summary="x",
        homepage="",
        provides=("pool.monitor",),
        sources=(
            CatalogSource(
                type="git",
                url="https://github.com/JamesAwesome/led-ticker-pool",
                ref=ref,
            ),
        ),
    )


def test_requirement_git_pinned_uses_ref():
    req = _git_entry().requirement()
    assert req == "git+https://github.com/JamesAwesome/led-ticker-pool.git@v1.2.0"


def test_requirement_git_unpinned_uses_main():
    req = _git_entry().requirement(pinned=False)
    assert req.endswith("led-ticker-pool.git@main")


def test_requirement_git_with_subdirectory():
    from led_ticker.plugins_catalog import CatalogEntry, CatalogSource

    e = CatalogEntry(
        name="rss",
        namespace="rss",
        summary="RSS/Atom headlines.",
        homepage="https://github.com/JamesAwesome/led-ticker-plugins",
        provides=("rss.feed",),
        sources=(
            CatalogSource(
                type="git",
                url="https://github.com/JamesAwesome/led-ticker-plugins",
                ref="rss-v0.2.0",
                subdirectory="plugins/rss",
            ),
        ),
    )
    assert e.requirement() == (
        "git+https://github.com/JamesAwesome/led-ticker-plugins.git"
        "@rss-v0.2.0#subdirectory=plugins/rss"
    )
    # unpinned still carries the subdirectory, falling back to @main
    assert e.requirement(pinned=False) == (
        "git+https://github.com/JamesAwesome/led-ticker-plugins.git"
        "@main#subdirectory=plugins/rss"
    )


def test_requirement_git_url_already_dot_git_not_doubled():
    e = CatalogEntry(
        "p",
        "p",
        "x",
        "",
        (),
        (CatalogSource(type="git", url="https://h/o/p.git", ref="main"),),
    )
    assert e.requirement() == "git+https://h/o/p.git@main"


def test_requirement_pypi_pinned_and_unpinned():
    e = CatalogEntry(
        "p",
        "p",
        "x",
        "",
        (),
        (CatalogSource(type="pypi", package="led-ticker-pool", version="1.2.0"),),
    )
    assert e.requirement() == "led-ticker-pool==1.2.0"
    assert e.requirement(pinned=False) == "led-ticker-pool"


def test_requirement_pypi_no_version_falls_back_to_bare_name():
    e = CatalogEntry(
        "p",
        "p",
        "x",
        "",
        (),
        (CatalogSource(type="pypi", package="led-ticker-pool", version=None),),
    )
    assert e.requirement() == "led-ticker-pool"


def test_source_for_prefers_first_then_honors_explicit():
    e = CatalogEntry(
        "p",
        "p",
        "x",
        "",
        (),
        (
            CatalogSource(type="git", url="https://h/o/p", ref="main"),
            CatalogSource(type="pypi", package="led-ticker-pool"),
        ),
    )
    assert e.source_for(None).type == "git"  # first = preferred
    assert e.source_for("pypi").type == "pypi"


def test_source_for_missing_type_raises():
    with pytest.raises(ValueError, match="no 'pypi' source"):
        _git_entry().requirement(source="pypi")


# --- get / search ---


def test_get_and_search_case_insensitive():
    cat = load_catalog()
    assert cat.get("pool").name == "pool"
    assert cat.get("POOL").name == "pool"  # get() is case-insensitive (matches search)
    assert cat.get("Pool").name == "pool"
    assert cat.get("nope") is None
    assert "baseball" in {e.name for e in cat.search("MLB")}  # matches summary
    assert "pool" in {e.name for e in cat.search("POOL")}
    assert cat.search("zzzznomatch") == []


def test_search_matches_provides():
    cat = load_catalog()
    assert "crypto" in {e.name for e in cat.search("coingecko")}


# --- parse validation (malformed catalog) ---


def test_parse_source_rejects_bad_type():
    with pytest.raises(ValueError, match="invalid type"):
        _parse_source({"type": "svn", "url": "x"})


def test_parse_source_git_requires_url():
    with pytest.raises(ValueError, match="missing 'url'"):
        _parse_source({"type": "git"})


def test_parse_entry_requires_sources():
    with pytest.raises(ValueError, match="missing 'sources'"):
        _parse_entry({"name": "p", "namespace": "p", "summary": "x"})


def test_parse_entry_empty_sources_rejected():
    with pytest.raises(ValueError, match="no sources"):
        _parse_entry({"name": "p", "namespace": "p", "summary": "x", "sources": []})
