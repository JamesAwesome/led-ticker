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
    """pending_count == number of restart_to_activate entries."""
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
    assert res["pending_count"] == len(pending_entries)
    assert res["pending_count"] == len(cat.entries)


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
    """active / restart_to_activate / externally_installed → 'installed'."""
    result = redact_anonymous(_FULL_PAYLOAD)
    ns_state = {p["namespace"]: p["state"] for p in result["plugins"]}
    assert ns_state["rss"] == "installed"
    assert ns_state["weather"] == "installed"
    assert ns_state["mycorp.custom"] == "installed"


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
    """Public catalog fields (namespace, name, summary, provides, source) preserved."""
    result = redact_anonymous(_FULL_PAYLOAD)
    for orig, anon in zip(_FULL_PAYLOAD["plugins"], result["plugins"], strict=True):
        assert anon["namespace"] == orig["namespace"]
        assert anon["name"] == orig["name"]
        assert anon["summary"] == orig["summary"]
        assert anon["provides"] == orig["provides"]
        assert anon["source"] == orig["source"]


def test_redact_anonymous_display_online_and_auth_required_preserved():
    """display_online and auth_required pass through unchanged."""
    result = redact_anonymous(_FULL_PAYLOAD)
    assert result["display_online"] == _FULL_PAYLOAD["display_online"]
    assert result["auth_required"] == _FULL_PAYLOAD["auth_required"]


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
