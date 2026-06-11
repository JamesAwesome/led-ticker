"""Traversal guard for filename-accepting webui endpoints.

This is the security surface of validate-by-file: every rejection mode
must hold, and rejections must be indistinguishable from absent files."""

from led_ticker.webui._paths import list_config_names, safe_config_member


def _mk(tmp_path):
    (tmp_path / "config.toml").write_text("[display]\n")
    (tmp_path / "config.bigsign.toml").write_text("[display]\n")
    (tmp_path / "notes.txt").write_text("not toml")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.toml").write_text("[display]\n")
    return tmp_path


def test_listing_is_toml_basenames_sorted(tmp_path):
    d = _mk(tmp_path)
    assert list_config_names(d) == ["config.bigsign.toml", "config.toml"]


def test_listing_missing_dir_is_empty(tmp_path):
    assert list_config_names(tmp_path / "absent") == []


def test_happy_path_resolves(tmp_path):
    d = _mk(tmp_path)
    p = safe_config_member(d, "config.toml")
    assert p is not None and p.name == "config.toml"


def test_rejects_relative_escape(tmp_path):
    d = _mk(tmp_path)
    (tmp_path.parent / "outside.toml").write_text("[display]\n")
    assert safe_config_member(d, "../outside.toml") is None


def test_rejects_absolute_path(tmp_path):
    d = _mk(tmp_path)
    assert safe_config_member(d, "/etc/passwd") is None


def test_rejects_subdirectory_member(tmp_path):
    d = _mk(tmp_path)
    assert safe_config_member(d, "sub/nested.toml") is None


def test_rejects_non_toml_suffix(tmp_path):
    d = _mk(tmp_path)
    assert safe_config_member(d, "notes.txt") is None


def test_rejects_symlink_escaping_dir(tmp_path):
    d = _mk(tmp_path)
    outside = tmp_path.parent / "secret.toml"
    outside.write_text("[display]\n")
    (d / "sneaky.toml").symlink_to(outside)
    assert safe_config_member(d, "sneaky.toml") is None


def test_rejects_absent_file_same_as_traversal(tmp_path):
    d = _mk(tmp_path)
    # Absent and traversal must be the same outcome (no filesystem oracle).
    assert safe_config_member(d, "nope.toml") is None
