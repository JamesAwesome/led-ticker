"""Bundled plugin catalog: integrity + the requirement() builder."""

import pytest

from led_ticker.plugins_catalog import (
    Catalog,
    CatalogEntry,
    CatalogSource,
    PluginProvides,
    _parse_entry,
    _parse_source,
    load_catalog,
)

# --- bundled catalog integrity (guards a hand-edited plugins_catalog.json) ---


def test_bundled_catalog_loads_and_is_v3():
    cat = load_catalog()
    assert isinstance(cat, Catalog)
    assert cat.entries  # non-empty


def test_bundled_catalog_has_the_first_party_plugins():
    cat = load_catalog()
    names = {e.name for e in cat.entries}
    assert names == {
        "pool",
        "baseball",
        "crypto",
        "calendar",
        "rss",
        "weather",
        "nyancat",
        "pokeball",
        "pacman",
        "sailor_moon",
    }
    # the split is done — no monolithic feeds/arcade entries remain
    assert "feeds" not in names and "arcade" not in names


_DATA_PLUGINS = ("pool", "baseball", "crypto", "calendar", "rss", "weather")
_HOMAGE_PLUGINS = ("nyancat", "pokeball", "pacman", "sailor_moon")


def test_data_plugins_default_to_pypi():
    """The 6 published data plugins have pypi as their first (preferred) source."""
    cat = load_catalog()
    for name in _DATA_PLUGINS:
        e = cat.get(name)
        assert e is not None, f"missing plugin {name!r}"
        src = e.source_for(None)
        assert src.type == "pypi", f"{name}: expected pypi default, got {src.type!r}"
        assert src.package == f"led-ticker-{name}"
        # no version field → unpinned bare requirement
        assert e.requirement() == f"led-ticker-{name}"
        # pinned=True still yields bare name — no version declared
        assert e.requirement(pinned=True) == f"led-ticker-{name}"


def test_data_plugins_retain_git_source():
    """The 6 data plugins keep a git source as the second entry."""
    cat = load_catalog()
    for name in _DATA_PLUGINS:
        e = cat.get(name)
        src = e.source_for("git")
        assert src.url == "https://github.com/JamesAwesome/led-ticker-plugins"
        assert src.subdirectory == f"plugins/{name}"
        assert src.ref and src.ref.startswith(f"{name}-v")
        assert e.requirement(source="git").endswith(f"#subdirectory=plugins/{name}")


def test_homage_plugins_install_from_the_monorepo():
    """The 4 homage plugins (not on PyPI) install git-only from the monorepo."""
    cat = load_catalog()
    for name in _HOMAGE_PLUGINS:
        e = cat.get(name)
        assert e is not None, f"missing plugin {name!r}"
        assert len(e.sources) == 1, f"{name}: expected 1 source, got {len(e.sources)}"
        src = e.sources[0]
        assert src.type == "git"
        assert src.url == "https://github.com/JamesAwesome/led-ticker-plugins"
        assert src.subdirectory == f"plugins/{name}"
        assert src.ref and src.ref.startswith(f"{name}-v")
        # the emitted requirement carries the subdirectory fragment
        assert e.requirement().endswith(f"#subdirectory=plugins/{name}")


def test_split_families_provide_their_types():
    cat = load_catalog()
    assert cat.get("rss").provides.widgets == ("rss.feed",)
    assert cat.get("weather").provides.widgets == ("weather.current",)
    for fam in ("nyancat", "pokeball", "pacman", "sailor_moon"):
        prov = cat.get(fam).provides
        assert prov.widgets == ()  # transition-only plugins
        assert set(prov.transitions) == {
            f"{fam}.forward",
            f"{fam}.reverse",
            f"{fam}.alternating",
        }


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
    assert cat.get("pool").provides.widgets == ("pool.monitor",)


def test_baseball_provides_full_typed_surface():
    cat = load_catalog()
    prov = cat.get("baseball").provides
    assert set(prov.widgets) == {
        "baseball.scores",
        "baseball.standings",
        "baseball.promotions",
        "baseball.statcast",
        "baseball.attendance",
    }
    assert set(prov.transitions) == {
        "baseball.roll",
        "baseball.roll_reverse",
        "baseball.roll_alternating",
    }
    assert prov.emoji == ("baseball.ball",)


def test_pokeball_provides_transitions_and_emoji():
    prov = load_catalog().get("pokeball").provides
    assert set(prov.transitions) == {
        "pokeball.forward",
        "pokeball.reverse",
        "pokeball.alternating",
    }
    assert prov.emoji == ("pokeball.ball",)


def test_schema_version_is_3():
    from led_ticker.plugins_catalog import SCHEMA_VERSION

    assert SCHEMA_VERSION == 3


def test_parse_provides_valid_multi_kind():
    from led_ticker.plugins_catalog import _parse_provides

    p = _parse_provides({"widgets": ["a.w"], "transitions": ["a.t"], "emoji": ["a.e"]})
    assert p.widgets == ("a.w",)
    assert p.transitions == ("a.t",)
    assert p.emoji == ("a.e",)


def test_parse_provides_absent_is_empty():
    from led_ticker.plugins_catalog import _parse_provides

    assert _parse_provides(None).is_empty() is True


def test_parse_provides_rejects_non_dict():
    from led_ticker.plugins_catalog import _parse_provides

    with pytest.raises(ValueError, match="must be an object"):
        _parse_provides(["a.w"])


def test_parse_provides_rejects_unknown_kind():
    from led_ticker.plugins_catalog import _parse_provides

    with pytest.raises(ValueError, match="unknown surface kind"):
        _parse_provides({"widgetz": ["a.w"]})


def test_parse_provides_rejects_non_string_list():
    from led_ticker.plugins_catalog import _parse_provides

    with pytest.raises(ValueError, match="list of strings"):
        _parse_provides({"widgets": [123]})


def test_search_finds_each_kind():
    cat = load_catalog()
    assert "baseball" in {e.name for e in cat.search("attendance")}  # widget
    assert "baseball" in {e.name for e in cat.search("roll")}  # transition
    assert "baseball" in {e.name for e in cat.search("baseball.ball")}  # emoji
    assert "nyancat" in {e.name for e in cat.search("nyancat.forward")}  # trans-only


# --- requirement() builder ---


def _git_entry(ref="v1.2.0"):
    return CatalogEntry(
        name="pool",
        namespace="pool",
        summary="x",
        homepage="",
        provides=PluginProvides(widgets=("pool.monitor",)),
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
        provides=PluginProvides(widgets=("rss.feed",)),
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
        PluginProvides(),
        (CatalogSource(type="git", url="https://h/o/p.git", ref="main"),),
    )
    assert e.requirement() == "git+https://h/o/p.git@main"


def test_requirement_pypi_pinned_and_unpinned():
    e = CatalogEntry(
        "p",
        "p",
        "x",
        "",
        PluginProvides(),
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
        PluginProvides(),
        (CatalogSource(type="pypi", package="led-ticker-pool", version=None),),
    )
    assert e.requirement() == "led-ticker-pool"


def test_source_for_prefers_first_then_honors_explicit():
    e = CatalogEntry(
        "p",
        "p",
        "x",
        "",
        PluginProvides(),
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


# --- PluginProvides value object ---


def test_provides_all_names_in_canonical_order():
    p = PluginProvides(
        widgets=("ns.w1", "ns.w2"),
        transitions=("ns.t1",),
        emoji=("ns.e1",),
    )
    assert p.all_names() == ("ns.w1", "ns.w2", "ns.t1", "ns.e1")


def test_provides_is_empty():
    assert PluginProvides().is_empty() is True
    assert PluginProvides(transitions=("ns.t",)).is_empty() is False


def test_provides_groups_skips_empty_kinds_in_order():
    p = PluginProvides(emoji=("ns.e",), widgets=("ns.w",))
    # widgets before emoji (canonical order), transitions omitted (empty)
    assert p.groups() == [("widgets", ("ns.w",)), ("emoji", ("ns.e",))]


def test_provides_primary_prefers_widgets_then_transitions():
    both = PluginProvides(widgets=("ns.w",), transitions=("ns.t",))
    assert both.primary() == ("widgets", "ns.w")
    trans_only = PluginProvides(transitions=("ns.t1", "ns.t2"))
    assert trans_only.primary() == ("transitions", "ns.t1")
    emoji_only = PluginProvides(emoji=("ns.ball",))
    assert emoji_only.primary() == ("emoji", "ns.ball")
    assert PluginProvides().primary() is None


# --- Fix 1: search haystack includes provides.all_names() ---


def test_search_matches_a_provided_name_absent_from_name_and_summary():
    # Isolates the provides.all_names() haystack term: the query appears ONLY in
    # provides, so a regression dropping it from Catalog.search would fail here.
    cat = Catalog(
        entries=(
            CatalogEntry(
                name="x",
                namespace="x",
                summary="nothing here",
                homepage="",
                provides=PluginProvides(transitions=("x.only_in_provides",)),
                sources=(CatalogSource(type="git", url="https://h/o/x", ref="main"),),
            ),
        )
    )
    assert "x" in {e.name for e in cat.search("only_in_provides")}
    assert cat.search("totally_absent_token") == []  # negative direction


# --- Fix 2: schema-version rejection gate ---


def test_parse_catalog_rejects_wrong_schema_version():
    from led_ticker.plugins_catalog import _parse_catalog

    with pytest.raises(ValueError, match="is not the supported version"):
        _parse_catalog({"schema_version": 2, "plugins": []})


# --- Fix 3: _parse_provides rejects a bare string value ---


def test_parse_provides_rejects_non_list_value():
    from led_ticker.plugins_catalog import _parse_provides

    # a bare string is iterable; the isinstance(list) guard must reject it
    with pytest.raises(ValueError, match="list of strings"):
        _parse_provides({"widgets": "a.w"})
