from led_ticker.plugins_catalog import load_catalog
from led_ticker.webui.store import build_store, config_references


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


def test_build_store_display_offline_active_state_stable(tmp_path):
    """When display is online, active entries show state='active'.

    The brief says: when display_online is False, the FRONTEND relabels —
    the payload keeps the state name stable. Here we verify the active path.
    """
    cat = load_catalog()
    ns = cat.entries[0].namespace
    man = tmp_path / "requirements-plugins.txt"
    man.write_text(cat.entries[0].requirement() + "\n")
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    res = build_store(
        manifest_path=man,
        config_path=cfg,
        status={"plugins": [{"namespace": ns}]},
        token_configured=False,
    )
    assert res["display_online"] is True
    entry = next(p for p in res["plugins"] if p["namespace"] == ns)
    assert entry["state"] == "active"


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
