from led_ticker.webui.store import config_references


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
