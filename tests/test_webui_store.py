from led_ticker.plugins_catalog import load_catalog
from led_ticker.webui.store import build_store, config_references, redact_anonymous


def test_config_references_widget_and_transition(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[[playlist.section]]\nmode="swap"\ntransition="nyancat.forward"\n'
        '[[playlist.section.widget]]\ntype="rss.feed"\n'
    )
    refs = config_references(cfg)
    assert "rss" in refs and refs["rss"][0]["type"] == "rss.feed"
    assert "nyancat" in refs  # via the transition key


def test_config_references_missing_or_bad_is_empty(tmp_path):
    assert config_references(tmp_path / "absent.toml") == {}
    bad = tmp_path / "config.toml"
    bad.write_text("[[[ not toml")
    assert config_references(bad) == {}


def test_build_store_states(tmp_path):
    cat = load_catalog()
    ns = cat.entries[0].namespace  # a real catalog plugin
    man = tmp_path / "requirements-plugins.txt"
    man.write_text(cat.entries[0].requirement() + "\n")  # declared
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    # declared + active -> active
    res = build_store(
        manifest_path=man,
        config_path=cfg,
        status={"plugins": [{"namespace": ns}]},
        token_configured=True,
    )
    entry = next(p for p in res["plugins"] if p["namespace"] == ns)
    assert entry["state"] == "active"
    assert res["auth_required"] is True and res["display_online"] is True
    # declared + not active -> restart_to_activate, counts as pending
    res2 = build_store(
        manifest_path=man, config_path=cfg, status={}, token_configured=True
    )
    e2 = next(p for p in res2["plugins"] if p["namespace"] == ns)
    assert e2["state"] == "restart_to_activate"
    assert res2["display_online"] is False and res2["pending_count"] >= 1


def test_build_store_available_and_in_use(tmp_path):
    cat = load_catalog()
    ns = cat.entries[0].namespace
    man = tmp_path / "requirements-plugins.txt"
    man.write_text("")  # nothing declared
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    res = build_store(
        manifest_path=man, config_path=cfg, status={}, token_configured=False
    )
    entry = next(p for p in res["plugins"] if p["namespace"] == ns)
    assert entry["state"] == "available" and entry["removable"] is False
    assert res["auth_required"] is False


def test_build_store_externally_installed(tmp_path):
    """A namespace active in status but not in the catalog gets externally_installed."""
    man = tmp_path / "requirements-plugins.txt"
    man.write_text("")
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    res = build_store(
        manifest_path=man,
        config_path=cfg,
        status={"plugins": [{"namespace": "mycorp.custom"}]},
        token_configured=False,
    )
    ext = next((p for p in res["plugins"] if p["namespace"] == "mycorp.custom"), None)
    assert ext is not None
    assert ext["state"] == "externally_installed"
    assert ext["removable"] is False


def test_build_store_pending_count(tmp_path):
    """pending_count == number of DISTINCT pending pip packages (dedup by
    requirement key), not pending namespaces — the flair siblings share one
    package, so installing it is one pending install, not four."""
    from led_ticker.app.plugin_cmd import _requirement_key

    cat = load_catalog()
    man = tmp_path / "requirements-plugins.txt"
    # Declare all catalog entries but report none as active
    lines = "\n".join(e.requirement() for e in cat.entries) + "\n"
    man.write_text(lines)
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    res = build_store(
        manifest_path=man, config_path=cfg, status={}, token_configured=False
    )
    pending_entries = [p for p in res["plugins"] if p["state"] == "restart_to_activate"]
    distinct_keys = {_requirement_key(e.requirement()) for e in cat.entries}
    assert res["pending_count"] == len(distinct_keys)
    # Fewer distinct packages than namespaces (flair collapses 4 → 1).
    assert res["pending_count"] < len(pending_entries)


def test_build_store_removable_respects_in_use(tmp_path):
    """removable is False when the plugin is referenced in config."""
    cat = load_catalog()
    ns = cat.entries[0].namespace
    first_entry = cat.entries[0]
    if first_entry.provides.widgets:
        widget_type = first_entry.provides.widgets[0]
    else:
        widget_type = f"{ns}.monitor"
    man = tmp_path / "requirements-plugins.txt"
    man.write_text(first_entry.requirement() + "\n")
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'[[playlist.section.widget]]\ntype="{widget_type}"\n')
    res = build_store(
        manifest_path=man,
        config_path=cfg,
        status={"plugins": [{"namespace": ns}]},
        token_configured=False,
    )
    entry = next(p for p in res["plugins"] if p["namespace"] == ns)
    assert entry["removable"] is False
    assert len(entry["in_use_by"]) >= 1


def test_build_store_online_active_state(tmp_path):
    """When display is online and a declared plugin is active, state='active'.

    The brief says: when display_online is False, the FRONTEND relabels the
    badge — the JSON payload keeps state names stable regardless of online status.
    """
    cat = load_catalog()
    ns = cat.entries[0].namespace
    man = tmp_path / "requirements-plugins.txt"
    man.write_text(cat.entries[0].requirement() + "\n")
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    # Online case: status carries the namespace → active
    res = build_store(
        manifest_path=man,
        config_path=cfg,
        status={"plugins": [{"namespace": ns}]},
        token_configured=False,
    )
    assert res["display_online"] is True
    entry = next(p for p in res["plugins"] if p["namespace"] == ns)
    assert entry["state"] == "active"

    # Offline case: status={} → declared plugin becomes restart_to_activate,
    # display_online is False, pending_count >= 1.
    res_offline = build_store(
        manifest_path=man,
        config_path=cfg,
        status={},
        token_configured=False,
    )
    assert res_offline["display_online"] is False
    entry_off = next(p for p in res_offline["plugins"] if p["namespace"] == ns)
    assert entry_off["state"] == "restart_to_activate"
    assert res_offline["pending_count"] >= 1


def test_build_store_entry_fields(tmp_path):
    """Each plugin entry has the required fields."""
    man = tmp_path / "requirements-plugins.txt"
    man.write_text("")
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    res = build_store(
        manifest_path=man, config_path=cfg, status={}, token_configured=False
    )
    required = {
        "namespace",
        "name",
        "summary",
        "provides",
        "source",
        "state",
        "removable",
        "in_use_by",
    }
    for entry in res["plugins"]:
        assert required <= entry.keys(), f"Missing fields in {entry}"


# ---------------------------------------------------------------------------
# redact_anonymous
# ---------------------------------------------------------------------------

_FULL_PAYLOAD = {
    "display_online": True,
    "pending_count": 2,
    "auth_required": True,
    "plugins": [
        {
            "namespace": "rss",
            "name": "RSS Feed",
            "summary": "RSS headlines",
            "provides": {"widgets": ["rss.feed"]},
            "source": "git",
            "state": "active",
            "removable": True,
            "in_use_by": [{"section": "Morning", "type": "rss.feed"}],
        },
        {
            "namespace": "weather",
            "name": "Weather",
            "summary": "Current conditions",
            "provides": {"widgets": ["weather.current"]},
            "source": "pypi",
            "state": "restart_to_activate",
            "removable": False,
            "in_use_by": [],
        },
        {
            "namespace": "crypto",
            "name": "Crypto",
            "summary": "CoinGecko ticker",
            "provides": {"widgets": ["crypto.coingecko"]},
            "source": "git",
            "state": "available",
            "removable": False,
            "in_use_by": [],
        },
        {
            "namespace": "mycorp.custom",
            "name": "mycorp.custom",
            "summary": "",
            "provides": {},
            "source": "",
            "state": "externally_installed",
            "removable": False,
            "in_use_by": [{"section": "Custom Section", "type": "mycorp.widget"}],
        },
    ],
}


def test_redact_anonymous_in_use_by_emptied():
    """All in_use_by lists must be emptied (config section names are private)."""
    result = redact_anonymous(_FULL_PAYLOAD)
    for plugin in result["plugins"]:
        assert plugin["in_use_by"] == [], (
            f"in_use_by not emptied for {plugin['namespace']}"
        )


def test_redact_anonymous_removable_false():
    """removable must always be False (no remove button for anon callers)."""
    result = redact_anonymous(_FULL_PAYLOAD)
    for plugin in result["plugins"]:
        assert plugin["removable"] is False, (
            f"removable not False for {plugin['namespace']}"
        )


def test_redact_anonymous_state_coarsened_installed():
    """active / restart_to_activate → 'installed' (catalog entries only)."""
    result = redact_anonymous(_FULL_PAYLOAD)
    ns_state = {p["namespace"]: p["state"] for p in result["plugins"]}
    assert ns_state["rss"] == "installed"
    assert ns_state["weather"] == "installed"


def test_redact_anonymous_drops_externally_installed():
    """Off-catalog host-installed namespaces must NOT leak to anon callers.

    externally_installed entries are pure deployment data (a plugin the
    operator pip-installed on the host, absent from the public catalog).  An
    unauthenticated visitor to a token-protected sign must not be able to
    enumerate them — they are dropped entirely, not merely coarsened.
    """
    result = redact_anonymous(_FULL_PAYLOAD)
    anon_namespaces = {p["namespace"] for p in result["plugins"]}
    assert "mycorp.custom" not in anon_namespaces
    # Catalog entries remain visible.
    assert "rss" in anon_namespaces
    assert "weather" in anon_namespaces
    assert "crypto" in anon_namespaces


def test_redact_anonymous_state_coarsened_available():
    """available → 'available' (stays as-is)."""
    result = redact_anonymous(_FULL_PAYLOAD)
    ns_state = {p["namespace"]: p["state"] for p in result["plugins"]}
    assert ns_state["crypto"] == "available"


def test_redact_anonymous_pending_count_zeroed():
    """pending_count → 0 (detail leaks how many pending restarts)."""
    result = redact_anonymous(_FULL_PAYLOAD)
    assert result["pending_count"] == 0


def test_redact_anonymous_catalog_fields_preserved():
    """Public catalog fields (namespace, name, summary, provides, source) preserved.

    externally_installed entries are dropped (see
    test_redact_anonymous_drops_externally_installed), so this only asserts
    preservation for the surviving catalog entries, matched by namespace.
    """
    result = redact_anonymous(_FULL_PAYLOAD)
    orig_by_ns = {p["namespace"]: p for p in _FULL_PAYLOAD["plugins"]}
    catalog_origs = [
        p for p in _FULL_PAYLOAD["plugins"] if p["state"] != "externally_installed"
    ]
    # Every surviving anon entry corresponds to a non-externally-installed orig.
    assert len(result["plugins"]) == len(catalog_origs)
    for anon in result["plugins"]:
        orig = orig_by_ns[anon["namespace"]]
        assert orig["state"] != "externally_installed"
        assert anon["namespace"] == orig["namespace"]
        assert anon["name"] == orig["name"]
        assert anon["summary"] == orig["summary"]
        assert anon["provides"] == orig["provides"]
        assert anon["source"] == orig["source"]


def test_redact_anonymous_display_online_dropped_auth_required_preserved():
    """display_online is dropped (deployment liveness, hidden from anon callers);
    auth_required passes through unchanged."""
    result = redact_anonymous(_FULL_PAYLOAD)
    assert "display_online" not in result
    assert result["auth_required"] == _FULL_PAYLOAD["auth_required"]


def test_redact_anonymous_is_idempotent():
    """A second apply must be a fixed point — coarsening an already-coarsened
    payload must not regress 'installed' back to 'available', and display_online
    stays dropped."""
    once = redact_anonymous(_FULL_PAYLOAD)
    twice = redact_anonymous(once)
    assert twice == once


def test_redact_anonymous_does_not_mutate_input():
    """redact_anonymous must return a new dict; original must be unchanged."""
    import copy

    original = copy.deepcopy(_FULL_PAYLOAD)
    result = redact_anonymous(_FULL_PAYLOAD)
    # Original is unchanged.
    assert original == _FULL_PAYLOAD
    # Result is a different object.
    assert result is not _FULL_PAYLOAD
    assert result["plugins"] is not _FULL_PAYLOAD["plugins"]


# ---------------------------------------------------------------------------
# Shared-package siblings (led-ticker-flair: nyancat/pokeball/pacman/sailor_moon
# all resolve to one pip package). Removing one must not orphan a sibling.
# ---------------------------------------------------------------------------

_FLAIR_NAMESPACES = ("nyancat", "pokeball", "pacman", "sailor_moon")


def test_build_store_shared_package_siblings_not_removable_when_one_in_use(tmp_path):
    """Config references nyancat.forward; all four flair entries share one pip
    package (led-ticker-flair). Removing pokeball/pacman/sailor_moon would drop
    the package that also provides nyancat → build_store must mark ALL FOUR
    removable=False, not just nyancat."""
    cat = load_catalog()
    flair = {e.namespace for e in cat.entries} & set(_FLAIR_NAMESPACES)
    assert flair == set(_FLAIR_NAMESPACES), "catalog must carry the four flair entries"

    man = tmp_path / "requirements-plugins.txt"
    man.write_text("led-ticker-flair\n")  # one line provides all four namespaces
    cfg = tmp_path / "config.toml"
    cfg.write_text('[[playlist.section]]\nmode="swap"\ntransition="nyancat.forward"\n')

    res = build_store(
        manifest_path=man,
        config_path=cfg,
        status={"plugins": [{"namespace": ns} for ns in _FLAIR_NAMESPACES]},
        token_configured=False,
    )
    for ns in _FLAIR_NAMESPACES:
        entry = next(p for p in res["plugins"] if p["namespace"] == ns)
        assert entry["removable"] is False, (
            f"{ns} shares led-ticker-flair with the in-use nyancat — must not be "
            f"removable, got removable={entry['removable']!r}"
        )


def test_build_store_pending_count_dedups_shared_package(tmp_path):
    """One led-ticker-flair install marks all four flair namespaces
    restart_to_activate, but it is ONE pending package — pending_count must
    count distinct requirement keys, not namespaces (so the banner says 1)."""
    cat = load_catalog()
    flair = {e.namespace for e in cat.entries} & set(_FLAIR_NAMESPACES)
    assert flair == set(_FLAIR_NAMESPACES), "catalog must carry the four flair entries"

    man = tmp_path / "requirements-plugins.txt"
    man.write_text("led-ticker-flair\n")  # one line declares all four namespaces
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    # No flair namespace active → all four are restart_to_activate.
    res = build_store(
        manifest_path=man, config_path=cfg, status={}, token_configured=False
    )
    pending = [p for p in res["plugins"] if p["state"] == "restart_to_activate"]
    assert {p["namespace"] for p in pending} >= set(_FLAIR_NAMESPACES)
    # ...but the four flair rows collapse to ONE pending package: pending_count
    # equals the number of DISTINCT requirement keys, not pending namespaces.
    from led_ticker.app.plugin_cmd import _requirement_key

    distinct_pending_keys = {
        _requirement_key(e.requirement())
        for e in cat.entries
        if e.namespace in {p["namespace"] for p in pending}
    }
    assert res["pending_count"] == len(distinct_pending_keys)
    assert res["pending_count"] < len(pending)  # dedup actually collapsed rows
    # The four flair namespaces contribute exactly one key.
    flair_keys = {
        _requirement_key(e.requirement())
        for e in cat.entries
        if e.namespace in _FLAIR_NAMESPACES
    }
    assert len(flair_keys) == 1


def test_config_references_inline_emoji_token(tmp_path):
    """An inline :ns.slug: emoji in widget text counts as a config reference to
    the providing plugin's namespace (so the remove guard can fire)."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[[playlist.section.widget]]\ntype="message"\ntext="hi :pokeball.ball: there"\n'
    )
    refs = config_references(cfg)
    assert "pokeball" in refs, f"expected pokeball emoji ref, got {refs}"
    assert any(r["type"] == ":pokeball.ball:" for r in refs["pokeball"])


def test_build_store_catalog_active_but_undeclared(tmp_path):
    """Catalog plugin active in status but absent from manifest -> 'available'.

    Documented edge case (store.py): can happen when the manifest was edited to
    remove a line while the display is still running. Must NOT be classified as
    'externally_installed' (that bucket is for namespaces absent from the catalog
    entirely)."""
    cat = load_catalog()
    ns = cat.entries[0].namespace
    man = tmp_path / "requirements-plugins.txt"
    man.write_text("")  # not declared
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    res = build_store(
        manifest_path=man,
        config_path=cfg,
        status={"plugins": [{"namespace": ns}]},  # active but not declared
        token_configured=False,
    )
    entry = next(p for p in res["plugins"] if p["namespace"] == ns)
    assert entry["state"] == "available", (
        f"catalog plugin active-but-undeclared should be 'available', "
        f"got {entry['state']!r}"
    )
    assert entry["removable"] is False


# ---------------------------------------------------------------------------
# Pack indicator (led-ticker-flair: nyancat/pokeball/pacman/sailor_moon)
# ---------------------------------------------------------------------------

_FLAIR_NAMESPACES_FULL = ("nyancat", "pokeball", "pacman", "sailor_moon")


def test_build_store_pack_fields_flair_members(tmp_path):
    """Flair pack members each have pack=='flair' and pack_members lists all four
    sorted namespaces; a solo plugin (e.g. rss) has pack=='' and pack_members==[]."""
    cat = load_catalog()
    flair_ns = {e.namespace for e in cat.entries} & set(_FLAIR_NAMESPACES_FULL)
    assert flair_ns == set(_FLAIR_NAMESPACES_FULL), (
        "catalog must carry all four flair entries"
    )

    man = tmp_path / "requirements-plugins.txt"
    man.write_text("")
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    res = build_store(
        manifest_path=man, config_path=cfg, status={}, token_configured=False
    )
    plugins_by_ns = {p["namespace"]: p for p in res["plugins"]}

    # All four flair members must carry pack=="flair" and the full sorted list.
    expected_members = sorted(_FLAIR_NAMESPACES_FULL)
    for ns in _FLAIR_NAMESPACES_FULL:
        entry = plugins_by_ns[ns]
        assert entry["pack"] == "flair", (
            f"{ns}: expected pack=='flair', got {entry['pack']!r}"
        )
        assert entry["pack_members"] == expected_members, (
            f"{ns}: expected pack_members=={expected_members!r}, "
            f"got {entry['pack_members']!r}"
        )

    # A solo plugin (rss ships as led-ticker-rss, only one namespace) must have
    # empty pack fields.
    rss = plugins_by_ns.get("rss")
    assert rss is not None, "rss must be in catalog"
    assert rss["pack"] == "", f"rss: expected pack=='', got {rss['pack']!r}"
    assert rss["pack_members"] == [], (
        f"rss: expected pack_members==[], got {rss['pack_members']!r}"
    )


def test_redact_anonymous_preserves_pack_fields(tmp_path):
    """redact_anonymous must NOT strip pack/pack_members — they are catalog-derived
    public data, same class as name/summary/provides."""
    payload = {
        "display_online": True,
        "pending_count": 0,
        "auth_required": True,
        "plugins": [
            {
                "namespace": "nyancat",
                "name": "nyancat",
                "summary": "Nyan Cat transitions.",
                "provides": {"transitions": ["nyancat.forward"]},
                "source": "pypi",
                "state": "active",
                "removable": False,
                "in_use_by": [{"section": "S", "type": "nyancat.forward"}],
                "pack": "flair",
                "pack_members": ["nyancat", "pacman", "pokeball", "sailor_moon"],
            },
            {
                "namespace": "rss",
                "name": "rss",
                "summary": "RSS headlines.",
                "provides": {"widgets": ["rss.feed"]},
                "source": "pypi",
                "state": "available",
                "removable": False,
                "in_use_by": [],
                "pack": "",
                "pack_members": [],
            },
        ],
    }
    result = redact_anonymous(payload)
    ns_map = {p["namespace"]: p for p in result["plugins"]}

    # Pack member: pack/pack_members preserved.
    nyancat = ns_map["nyancat"]
    assert nyancat["pack"] == "flair", (
        f"pack should be 'flair' after redact, got {nyancat['pack']!r}"
    )
    expected_pack_members = ["nyancat", "pacman", "pokeball", "sailor_moon"]
    assert nyancat["pack_members"] == expected_pack_members, (
        f"pack_members should survive redact, got {nyancat['pack_members']!r}"
    )

    # Solo plugin: empty pack fields also preserved (not altered).
    rss = ns_map["rss"]
    assert rss["pack"] == ""
    assert rss["pack_members"] == []
