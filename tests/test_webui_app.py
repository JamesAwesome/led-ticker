"""Route tests for the webui sidecar app."""

import json
import time

from aiohttp.test_utils import TestClient, TestServer

from led_ticker.status_board import SCHEMA_VERSION, StatusBoard
from led_ticker.webui import build_webui_app


async def _client(tmp_path, *, token="", config_text=None, status=None):
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_text or "[display]\nrows = 16\ncols = 32\n")
    status_path = tmp_path / "status.json"
    if status is not None:
        body = json.dumps(status) if isinstance(status, dict) else status
        status_path.write_text(body)
    app = build_webui_app(config_path=config_path, status_path=status_path, token=token)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


def _fresh_status(**over):
    board = StatusBoard(path="/unused")
    snap = board.snapshot()
    snap.update(over)
    return snap


async def test_status_ok(tmp_path):
    client = await _client(tmp_path, status=_fresh_status())
    try:
        resp = await client.get("/api/status")
        body = await resp.json()
        assert resp.status == 200
        assert body["state"] == "ok"
        assert body["status"]["schema"] == SCHEMA_VERSION
    finally:
        await client.close()


async def test_status_missing_file(tmp_path):
    client = await _client(tmp_path)  # no status.json written
    try:
        body = await (await client.get("/api/status")).json()
        assert body["state"] == "missing"
        assert "running" in body["hint"]  # friendly first-run hint
    finally:
        await client.close()


async def test_status_malformed_file(tmp_path):
    client = await _client(tmp_path, status="{not json")
    try:
        body = await (await client.get("/api/status")).json()
        assert body["state"] == "unreadable"
    finally:
        await client.close()


async def test_status_schema_mismatch(tmp_path):
    client = await _client(tmp_path, status=_fresh_status(schema=SCHEMA_VERSION + 1))
    try:
        body = await (await client.get("/api/status")).json()
        assert body["state"] == "schema_mismatch"
        assert body["found"] == SCHEMA_VERSION + 1
        assert body["supported"] == SCHEMA_VERSION
    finally:
        await client.close()


async def test_status_stale(tmp_path):
    old = _fresh_status(published_at=time.time() - 3600, min_interval=2.0)
    client = await _client(tmp_path, status=old)
    try:
        body = await (await client.get("/api/status")).json()
        assert body["state"] == "stale"
        assert body["status"]["hostname"]  # data still served
    finally:
        await client.close()


async def test_auth_token_enforced_on_all_routes(tmp_path):
    client = await _client(tmp_path, token="s3cret", status=_fresh_status())
    try:
        for path in ("/api/status",):  # Tasks 8-9 widen this tuple to /, /api/config
            assert (await client.get(path)).status == 401
        ok = await client.get("/api/status", headers={"X-Web-Token": "s3cret"})
        assert ok.status == 200
        ok2 = await client.get("/api/status", params={"token": "s3cret"})
        assert ok2.status == 200
    finally:
        await client.close()


async def test_status_non_dict_json(tmp_path):
    # json.loads("3") -> int; status.get would AttributeError without the guard
    client = await _client(tmp_path, status='"just a string"')
    try:
        body = await (await client.get("/api/status")).json()
        assert body["state"] == "unreadable"
        assert "not a JSON object" in body["detail"]
    finally:
        await client.close()


async def test_status_non_numeric_timing_fields(tmp_path):
    # A schema-valid envelope with corrupt timing fields (truncated or
    # hand-edited file) must classify as unreadable, never raise out of
    # the handler as a 500.
    for bad in (
        _fresh_status(published_at="not-a-number"),
        _fresh_status(published_at=None),
        _fresh_status(min_interval="soon"),
    ):
        client = await _client(tmp_path, status=bad)
        try:
            resp = await client.get("/api/status")
            body = await resp.json()
            assert resp.status == 200
            assert body["state"] == "unreadable"
            assert "timing" in body["detail"]
        finally:
            await client.close()


async def test_config_view_is_redacted(tmp_path):
    cfg = (
        '[web]\ntoken = "supersecret"\n\n'
        "[display]\nrows = 16\ncols = 32\nchain_length = 5\n"
    )
    client = await _client(tmp_path, config_text=cfg)
    try:
        body = await (await client.get("/api/config")).json()
        assert "supersecret" not in body["toml"]
        assert "•••" in body["toml"]
        assert body["geometry"]["panel_width"] == 32 * 5
    finally:
        await client.close()


async def test_config_view_missing_file_degrades(tmp_path):
    client = await _client(tmp_path)
    (tmp_path / "config.toml").unlink()
    try:
        resp = await client.get("/api/config")
        body = await resp.json()
        assert resp.status == 200
        assert body["state"] == "unreadable"
    finally:
        await client.close()


async def test_validate_good_toml(tmp_path):
    good = (
        "[display]\nrows = 32\ncols = 64\nchain_length = 8\ndefault_scale = 1\n\n"
        '[[playlist.section]]\nmode = "swap"\nhold_time = 3\n'
        '[[playlist.section.widget]]\ntype = "message"\ntext = "hi"\n'
    )
    client = await _client(tmp_path)
    try:
        resp = await client.post("/api/validate", data=good)
        body = await resp.json()
        assert resp.status == 200
        assert body["valid"] is True
    finally:
        await client.close()


async def test_validate_bad_toml_is_200_with_issues(tmp_path):
    client = await _client(tmp_path)
    try:
        resp = await client.post("/api/validate", data="this is [not toml")
        assert resp.status == 200  # results, not errors
        body = await resp.json()
        assert body["valid"] is False
    finally:
        await client.close()


async def test_validate_oversize_body_is_413(tmp_path):
    client = await _client(tmp_path)
    try:
        resp = await client.post("/api/validate", data="x" * (1024 * 1024 + 1))
        assert resp.status == 413
    finally:
        await client.close()


async def test_validate_response_does_not_leak_temp_path(tmp_path):
    # validate_config_text materializes the body to a throwaway temp file;
    # the JSON response must not expose that ephemeral path to the browser.
    client = await _client(tmp_path)
    try:
        resp = await client.post("/api/validate", data="this is [not toml")
        text = await resp.text()
        assert "led-ticker-validate-" not in text
    finally:
        await client.close()


async def test_auth_gates_unknown_routes_and_new_routes(tmp_path):
    # Auth runs BEFORE routing: unknown paths must 401 (not 404) when a
    # token is configured — no route-existence oracle.
    client = await _client(tmp_path, token="s3cret", status=_fresh_status())
    try:
        for path in ("/api/config", "/no/such/route"):
            assert (await client.get(path)).status == 401
        resp = await client.post("/api/validate", data="x")
        assert resp.status == 401
    finally:
        await client.close()


async def test_root_serves_page(tmp_path):
    client = await _client(tmp_path)
    try:
        resp = await client.get("/")
        assert resp.status == 200
        assert resp.content_type == "text/html"
        text = await resp.text()
        for marker in (
            "Status",
            "Config",
            "Validate",
            "Inventory",
            "/api/status",
            "/api/configs",
            "validate-file",
            "/api/inventory",
            "line-gutter",
            "config-gutter",
            "/api/preview",
            "preview-canvas",
            "overlays-card",
            "no overlays installed",
            "plugin-reconcile-card",
            "Plugin install results",
            # Store tab markers
            'data-tab="store"',
            'id="tab-store"',
            "Only verified plugins are shown",
            "store-auth-banner",
            "store-offline-banner",
            "store-pending-banner",
            "store-list",
            "/api/store",
        ):
            assert marker in text, f"missing marker: {marker!r}"
    finally:
        await client.close()


async def test_root_is_auth_gated(tmp_path):
    client = await _client(tmp_path, token="s3cret")
    try:
        assert (await client.get("/")).status == 401
        ok = await client.get("/", params={"token": "s3cret"})
        assert ok.status == 200
    finally:
        await client.close()


async def test_status_carries_plugin_reconcile(tmp_path):
    """plugin_reconcile list is present in the /api/status payload (even when empty)."""
    client = await _client(tmp_path, status=_fresh_status())
    try:
        body = await (await client.get("/api/status")).json()
        assert body["state"] == "ok"
        assert "plugin_reconcile" in body["status"]
        assert isinstance(body["status"]["plugin_reconcile"], list)
    finally:
        await client.close()


async def test_status_plugin_reconcile_entries(tmp_path):
    """plugin_reconcile entries are passed through; failed/blocked carry detail."""
    reconcile = [
        {"namespace": "rss.feed", "action": "installed", "detail": ""},
        {
            "namespace": "weather.current",
            "action": "blocked",
            "detail": "config still references 'weather' widgets",
        },
        {
            "namespace": "nyancat",
            "action": "failed",
            "detail": "ImportError: no module named nyancat",
        },
    ]
    client = await _client(tmp_path, status=_fresh_status(plugin_reconcile=reconcile))
    try:
        body = await (await client.get("/api/status")).json()
        assert body["state"] == "ok"
        pr = body["status"]["plugin_reconcile"]
        assert len(pr) == 3
        assert pr[0] == {"namespace": "rss.feed", "action": "installed", "detail": ""}
        assert pr[1]["action"] == "blocked"
        assert "weather" in pr[1]["detail"]
        assert pr[2]["action"] == "failed"
    finally:
        await client.close()


async def test_serve_webui_starts_and_cleans_up(tmp_path):
    from led_ticker.webui import serve_webui

    config_path = tmp_path / "config.toml"
    config_path.write_text("[display]\nrows = 16\n")
    runner = await serve_webui(
        config_path=config_path,
        status_path=tmp_path / "status.json",
        host="127.0.0.1",
        port=0,  # OS-assigned free port
        token="",
    )
    try:
        assert runner.addresses
    finally:
        await runner.cleanup()


async def test_configs_listing(tmp_path):
    (tmp_path / "other.toml").write_text("[display]\nrows = 16\n")
    client = await _client(tmp_path)
    try:
        body = await (await client.get("/api/configs")).json()
        assert body["configs"] == ["config.toml", "other.toml"]
        assert body["running"] == "config.toml"
    finally:
        await client.close()


async def test_configs_listing_is_auth_gated(tmp_path):
    client = await _client(tmp_path, token="s3cret")
    try:
        assert (await client.get("/api/configs")).status == 401
    finally:
        await client.close()


def test_cli_webui_requires_web_block(tmp_path):
    import os
    import subprocess
    import sys

    cfg = tmp_path / "config.toml"
    cfg.write_text("[display]\nrows = 16\n")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, "-m", "led_ticker.app.cli", "webui", "--config", str(cfg)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert proc.returncode == 2
    assert "[web]" in proc.stderr


async def test_validate_file_happy_path_matches_direct_validation(tmp_path):
    good = (
        "[display]\nrows = 32\ncols = 64\nchain_length = 8\ndefault_scale = 1\n\n"
        '[[playlist.section]]\nmode = "swap"\nhold_time = 3\n'
        '[[playlist.section.widget]]\ntype = "message"\ntext = "hi"\n'
    )
    (tmp_path / "candidate.toml").write_text(good)
    client = await _client(tmp_path)
    try:
        resp = await client.post("/api/validate-file", json={"name": "candidate.toml"})
        body = await resp.json()
        assert resp.status == 200
        assert body["valid"] is True

        from led_ticker.validate import validate_config

        direct = await validate_config(tmp_path / "candidate.toml")
        assert body["valid"] == direct.valid
    finally:
        await client.close()


async def test_validate_file_traversal_and_absent_are_identical_404s(tmp_path):
    client = await _client(tmp_path)
    try:
        bodies = []
        for name in (
            "../escape.toml",
            "/etc/passwd",
            "sub/x.toml",
            "nope.toml",
            "a\x00.toml",
        ):
            resp = await client.post("/api/validate-file", json={"name": name})
            assert resp.status == 404
            bodies.append(await resp.json())
        assert all(b == bodies[0] for b in bodies)  # no oracle
    finally:
        await client.close()


async def test_validate_file_bad_body_is_400(tmp_path):
    client = await _client(tmp_path)
    try:
        assert (await client.post("/api/validate-file", data="not json")).status == 400
        assert (await client.post("/api/validate-file", json={})).status == 400
        assert (await client.post("/api/validate-file", json={"name": 7})).status == 400
    finally:
        await client.close()


async def test_validate_file_vanishing_target_is_404_not_500(tmp_path, monkeypatch):
    # TOCTOU: file passes the guard but is deleted before validate_config
    # runs. Must classify as the same 404 as never-existed, never a 500.
    import led_ticker.webui as webui_mod

    async def vanished(path, *, strict=False):
        raise FileNotFoundError(path)

    (tmp_path / "ghost.toml").write_text("[display]\nrows = 16\n")
    client = await _client(tmp_path)
    monkeypatch.setattr(webui_mod, "validate_config", vanished)
    try:
        resp = await client.post("/api/validate-file", json={"name": "ghost.toml"})
        assert resp.status == 404
        assert (await resp.json()) == {"error": "unknown config"}
    finally:
        await client.close()


async def test_config_view_by_name_is_redacted(tmp_path):
    (tmp_path / "alt.toml").write_text('[web]\ntoken = "altsecret"\n')
    client = await _client(tmp_path)
    try:
        body = await (
            await client.get("/api/config", params={"name": "alt.toml"})
        ).json()
        assert body["state"] == "ok"
        assert "altsecret" not in body["toml"]
        assert "•••" in body["toml"]
    finally:
        await client.close()


async def test_config_view_by_name_traversal_is_404(tmp_path):
    client = await _client(tmp_path)
    try:
        for name in ("../x.toml", "/etc/passwd", "nope.toml"):
            assert (
                await client.get("/api/config", params={"name": name})
            ).status == 404
    finally:
        await client.close()


async def test_config_view_returns_hash(tmp_path):
    from led_ticker.reload import config_hash

    content = "[display]\nrows = 16\ncols = 32\n"
    client = await _client(tmp_path, config_text=content)
    config_path = tmp_path / "config.toml"
    try:
        body = await (await client.get("/api/config")).json()
        assert body["state"] == "ok"
        expected = config_hash(config_path)
        assert expected is not None
        assert body["hash"] == expected
        assert len(body["hash"]) == 64  # sha256 hex length
    finally:
        await client.close()


async def test_config_view_by_name_returns_hash(tmp_path):
    from led_ticker.reload import config_hash

    content = "[display]\nrows = 16\n"
    (tmp_path / "other.toml").write_text(content)
    client = await _client(tmp_path)
    try:
        body = await (
            await client.get("/api/config", params={"name": "other.toml"})
        ).json()
        assert body["state"] == "ok"
        expected = config_hash(tmp_path / "other.toml")
        assert expected is not None
        assert body["hash"] == expected
    finally:
        await client.close()


async def test_config_view_without_name_unchanged(tmp_path):
    client = await _client(tmp_path)
    try:
        body = await (await client.get("/api/config")).json()
        assert body["state"] == "ok"  # the running config, as in v1
    finally:
        await client.close()


async def test_inventory_route(tmp_path):
    client = await _client(tmp_path)
    try:
        body = await (await client.get("/api/inventory")).json()
        assert set(body) >= {"fonts", "assets", "assets_truncated", "emoji"}
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# PUT /api/config — save handler (Task 3)
# ---------------------------------------------------------------------------

_GOOD_CONFIG = (
    "[display]\nrows = 16\ncols = 32\nchain_length = 5\ndefault_scale = 1\n\n"
    '[[playlist.section]]\nmode = "swap"\nhold_time = 3\n'
    '[[playlist.section.widget]]\ntype = "message"\ntext = "hi"\n'
)


async def test_put_config_rejects_without_token(tmp_path):
    """No token configured → 403, file unchanged."""
    original = _GOOD_CONFIG
    client = await _client(tmp_path, token="", config_text=original)
    config_path = tmp_path / "config.toml"
    from led_ticker.reload import config_hash

    h = config_hash(config_path)
    try:
        resp = await client.put("/api/config", json={"toml": original, "base_hash": h})
        assert resp.status == 403
        body = await resp.json()
        assert "editing disabled" in body["error"]
        assert config_path.read_text() == original  # unchanged
        assert not (tmp_path / "config.toml.bak").exists()
    finally:
        await client.close()


async def test_put_config_writes_valid_toml(tmp_path):
    """Valid toml + correct base_hash + token → 200, file updated, .bak holds prior."""
    original = _GOOD_CONFIG
    updated = _GOOD_CONFIG + "\n# edited\n"
    client = await _client(tmp_path, token="t", config_text=original)
    config_path = tmp_path / "config.toml"
    from led_ticker.reload import config_hash

    original_hash = config_hash(config_path)
    assert original_hash is not None
    try:
        resp = await client.put(
            "/api/config",
            json={"toml": updated, "base_hash": original_hash},
            headers={"X-Web-Token": "t"},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["state"] == "saved"
        # File was updated
        assert config_path.read_text() == updated
        # .bak holds the prior contents
        bak = tmp_path / "config.toml.bak"
        assert bak.exists()
        assert bak.read_text() == original
        # Response hash matches new disk hash
        new_hash = config_hash(config_path)
        assert body["hash"] == new_hash
    finally:
        await client.close()


async def test_put_config_rejects_invalid_toml(tmp_path):
    """Invalid config → 422, file unchanged, no .bak."""
    original = _GOOD_CONFIG
    client = await _client(tmp_path, token="t", config_text=original)
    config_path = tmp_path / "config.toml"
    from led_ticker.reload import config_hash

    h = config_hash(config_path)
    bad = "this is [not valid toml config at all ]["
    try:
        resp = await client.put(
            "/api/config",
            json={"toml": bad, "base_hash": h},
            headers={"X-Web-Token": "t"},
        )
        assert resp.status == 422
        body = await resp.json()
        assert body["valid"] is False
        assert config_path.read_text() == original  # unchanged
        assert not (tmp_path / "config.toml.bak").exists()
    finally:
        await client.close()


async def test_put_config_conflict_on_stale_base_hash(tmp_path):
    """base_hash != current disk hash → 409, file unchanged."""
    original = _GOOD_CONFIG
    client = await _client(tmp_path, token="t", config_text=original)
    config_path = tmp_path / "config.toml"
    try:
        resp = await client.put(
            "/api/config",
            json={"toml": original, "base_hash": "deadbeef" * 8},
            headers={"X-Web-Token": "t"},
        )
        assert resp.status == 409
        body = await resp.json()
        assert body["error"] == "conflict"
        assert "hash" in body
        assert config_path.read_text() == original  # unchanged
        assert not (tmp_path / "config.toml.bak").exists()
    finally:
        await client.close()


async def test_put_config_restores_redacted_secret(tmp_path):
    """Submit redacted sentinel → 200, written file has the real secret restored."""
    disk_cfg = (
        '[web]\ntoken = "supersecret"\n\n'
        "[display]\nrows = 16\ncols = 32\nchain_length = 5\ndefault_scale = 1\n\n"
        '[[playlist.section]]\nmode = "swap"\nhold_time = 3\n'
        '[[playlist.section.widget]]\ntype = "message"\ntext = "hi"\n'
    )
    client = await _client(tmp_path, token="t", config_text=disk_cfg)
    config_path = tmp_path / "config.toml"
    from led_ticker.reload import config_hash
    from led_ticker.webui.redact import redact_toml

    # Simulate what the browser gets: the redacted view
    redacted_view = redact_toml(disk_cfg)
    h = config_hash(config_path)
    assert h is not None
    try:
        resp = await client.put(
            "/api/config",
            json={"toml": redacted_view, "base_hash": h},
            headers={"X-Web-Token": "t"},
        )
        assert resp.status == 200
        written = config_path.read_text()
        assert "supersecret" in written
        assert "•••" not in written
    finally:
        await client.close()


async def test_put_config_absent_file_with_nonempty_base_hash_is_409(tmp_path):
    """File absent (GET would return hash="") but client sent a non-empty
    base_hash → the file the edit was based on disappeared → 409, no write."""
    client = await _client(tmp_path, token="t")
    config_path = tmp_path / "config.toml"
    config_path.unlink()  # absent
    try:
        resp = await client.put(
            "/api/config",
            json={"toml": _GOOD_CONFIG, "base_hash": "deadbeef" * 8},
            headers={"X-Web-Token": "t"},
        )
        assert resp.status == 409
        body = await resp.json()
        assert body["error"] == "file disappeared"
        assert body["hash"] == ""
        assert not config_path.exists()  # no write
        assert not (tmp_path / "config.toml.tmp").exists()
    finally:
        await client.close()


async def test_put_config_absent_file_with_empty_base_hash_creates(tmp_path):
    """File absent + base_hash="" (GET convention for absent) → legitimate
    create → 200, file written."""
    client = await _client(tmp_path, token="t")
    config_path = tmp_path / "config.toml"
    config_path.unlink()  # absent
    try:
        resp = await client.put(
            "/api/config",
            json={"toml": _GOOD_CONFIG, "base_hash": ""},
            headers={"X-Web-Token": "t"},
        )
        assert resp.status == 200
        assert config_path.exists()
        assert config_path.read_text() == _GOOD_CONFIG
    finally:
        await client.close()


async def test_put_config_host_edit_mid_handler_is_409(tmp_path):
    """A host edit that lands during the handler (after the conflict-check,
    before os.replace) is caught by the re-check → 409, no write, no .tmp."""
    import led_ticker.webui as webui_mod

    original = _GOOD_CONFIG
    client = await _client(tmp_path, token="t", config_text=original)
    config_path = tmp_path / "config.toml"
    from led_ticker.reload import config_hash

    h = config_hash(config_path)
    assert h is not None

    real_validate = webui_mod.validate_config_text

    async def validate_then_host_edit(text):
        # Simulate a host edit landing mid-handler: mutate the file on disk
        # after the conflict-check passed but before os.replace.
        config_path.write_text(original + "\n# host edit\n")
        return await real_validate(text)

    monkeypatch_done = False
    try:
        webui_mod.validate_config_text = validate_then_host_edit
        monkeypatch_done = True
        resp = await client.put(
            "/api/config",
            json={"toml": original + "\n# my edit\n", "base_hash": h},
            headers={"X-Web-Token": "t"},
        )
        assert resp.status == 409
        body = await resp.json()
        assert body["error"] == "conflict"
        # Our edit was NOT written; the host edit is intact.
        assert config_path.read_text() == original + "\n# host edit\n"
        assert not (tmp_path / "config.toml.tmp").exists()
    finally:
        if monkeypatch_done:
            webui_mod.validate_config_text = real_validate
        await client.close()


async def test_put_config_write_failure_cleans_tmp_and_is_500(tmp_path, monkeypatch):
    """os.replace raising OSError → 500 AND no leftover .tmp file."""
    import led_ticker.webui as webui_mod

    original = _GOOD_CONFIG
    updated = _GOOD_CONFIG + "\n# edited\n"
    client = await _client(tmp_path, token="t", config_text=original)
    config_path = tmp_path / "config.toml"
    from led_ticker.reload import config_hash

    h = config_hash(config_path)

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(webui_mod.os, "replace", boom)
    try:
        resp = await client.put(
            "/api/config",
            json={"toml": updated, "base_hash": h},
            headers={"X-Web-Token": "t"},
        )
        assert resp.status == 500
        body = await resp.json()
        assert "write failed" in body["error"]
        assert not (tmp_path / "config.toml.tmp").exists()  # cleaned up
        assert config_path.read_text() == original  # unchanged
    finally:
        await client.close()


def test_index_html_has_config_validation_card():
    from pathlib import Path

    import led_ticker.webui as webui_pkg

    html = (Path(webui_pkg.__file__).parent / "static" / "index.html").read_text()
    # The card exists and the render reads the new status field.
    assert 'id="config-validation-card"' in html
    assert 'id="config-validation-body"' in html
    assert "config_validation" in html


def test_index_html_has_store_tab():
    """The Store tab nav button and section are present in the page HTML."""
    from pathlib import Path

    import led_ticker.webui as webui_pkg

    html = (Path(webui_pkg.__file__).parent / "static" / "index.html").read_text()
    # Nav button
    assert 'data-tab="store"' in html
    # Tab section
    assert 'id="tab-store"' in html
    # Catalog-only note (key fragment)
    assert "Only verified plugins are shown" in html
    # Pending banner with restart command
    assert "docker compose restart" in html
    # Auth banner
    assert "store-auth-banner" in html
    # Offline banner
    assert "store-offline-banner" in html
    # Store list container
    assert 'id="store-list"' in html
    # Restart-command element (users copy the restart command from here)
    assert 'id="store-restart-cmd"' in html
    # JS function references
    assert "loadStore" in html
    assert "storeAction" in html
    assert "/api/store/install" in html
    assert "/api/store/remove" in html


# ---------------------------------------------------------------------------
# GET /api/store — plugin store (Task 3)
# ---------------------------------------------------------------------------


async def test_store_returns_expected_shape(tmp_path, monkeypatch):
    """GET /api/store → 200 with plugins list and metadata keys."""
    import led_ticker.webui as webui_mod

    fake_payload = {
        "display_online": False,
        "pending_count": 0,
        "auth_required": False,
        "plugins": [{"namespace": "rss.feed", "state": "available"}],
    }

    def fake_build_store(**kwargs):
        return fake_payload

    monkeypatch.setattr(webui_mod, "_build_store", fake_build_store)

    client = await _client(tmp_path)
    try:
        resp = await client.get("/api/store")
        assert resp.status == 200
        body = await resp.json()
        assert "plugins" in body
        assert isinstance(body["plugins"], list)
        assert "display_online" in body
        assert "pending_count" in body
        assert "auth_required" in body
        assert body["plugins"][0]["namespace"] == "rss.feed"
    finally:
        await client.close()


async def test_store_open_without_token(tmp_path, monkeypatch):
    """GET /api/store does not require auth even when a token is configured."""
    import led_ticker.webui as webui_mod

    monkeypatch.setattr(
        webui_mod,
        "_build_store",
        lambda **kwargs: {
            "display_online": False,
            "pending_count": 0,
            "auth_required": True,
            "plugins": [],
        },
    )

    client = await _client(tmp_path, token="s3cret")
    try:
        # No token header — must still return 200 (open route)
        resp = await client.get("/api/store")
        assert resp.status == 200
        body = await resp.json()
        assert body["auth_required"] is True  # token IS configured
    finally:
        await client.close()


# POST /api/store/install — plugin store install (Task 4)
# ---------------------------------------------------------------------------


async def test_install_known_namespace_writes_manifest(tmp_path, monkeypatch):
    """POST /api/store/install with a known namespace → 200 + manifest updated."""
    import led_ticker.webui as webui_mod
    from led_ticker.plugins_catalog import (
        Catalog,
        CatalogEntry,
        CatalogSource,
        PluginProvides,
    )

    # Minimal catalog with one entry whose namespace we'll install.
    fake_entry = CatalogEntry(
        name="rss",
        namespace="rss.feed",
        summary="RSS/Atom feed headlines.",
        homepage="",
        provides=PluginProvides(widgets=("rss.feed",)),
        sources=(
            CatalogSource(
                type="git",
                url="https://github.com/JamesAwesome/led-ticker-plugins",
                ref="main",
                subdirectory="plugins/rss",
            ),
        ),
    )
    fake_catalog = Catalog(entries=(fake_entry,))

    # Patch _build_store so the return value is controlled.
    def fake_build_store(**kwargs):
        return {
            "display_online": False,
            "pending_count": 1,
            "auth_required": True,
            "plugins": [
                {
                    "namespace": "rss.feed",
                    "name": "rss",
                    "summary": "RSS/Atom feed headlines.",
                    "provides": {"widgets": ["rss.feed"]},
                    "source": "git",
                    "state": "restart_to_activate",
                    "removable": True,
                    "in_use_by": [],
                }
            ],
        }

    monkeypatch.setattr(webui_mod, "_build_store", fake_build_store)

    # Patch _load_catalog_lazy so we control catalog resolution.
    monkeypatch.setattr(webui_mod, "_load_catalog_lazy", lambda: fake_catalog)

    client = await _client(tmp_path, token="s3cret")
    manifest_path = tmp_path / "requirements-plugins.txt"
    try:
        resp = await client.post(
            "/api/store/install",
            json={"namespace": "rss.feed"},
            headers={"X-Web-Token": "s3cret"},
        )
        assert resp.status == 200
        body = await resp.json()
        # Response carries the rebuilt store entry for that namespace.
        assert body["namespace"] == "rss.feed"
        # Manifest must now contain the catalog requirement line.
        assert manifest_path.exists(), "manifest was not created"
        manifest_text = manifest_path.read_text()
        assert "led-ticker-plugins" in manifest_text or "rss" in manifest_text
        req = fake_entry.requirement()
        assert req in manifest_text, f"expected {req!r} in manifest"
        # .bak file must NOT exist (no prior manifest to back up).
        bak = manifest_path.with_suffix(manifest_path.suffix + ".bak")
        assert not bak.exists()
    finally:
        await client.close()


async def test_install_bak_created_when_manifest_exists(tmp_path, monkeypatch):
    """When the manifest already exists, install creates a .bak before writing."""
    import led_ticker.webui as webui_mod
    from led_ticker.plugins_catalog import (
        Catalog,
        CatalogEntry,
        CatalogSource,
        PluginProvides,
    )

    fake_entry = CatalogEntry(
        name="rss",
        namespace="rss.feed",
        summary="RSS feed.",
        homepage="",
        provides=PluginProvides(widgets=("rss.feed",)),
        sources=(
            CatalogSource(
                type="git",
                url="https://github.com/JamesAwesome/led-ticker-plugins",
                ref="main",
                subdirectory="plugins/rss",
            ),
        ),
    )
    fake_catalog = Catalog(entries=(fake_entry,))

    monkeypatch.setattr(
        webui_mod,
        "_build_store",
        lambda **kw: {
            "display_online": False,
            "pending_count": 1,
            "auth_required": True,
            "plugins": [
                {
                    "namespace": "rss.feed",
                    "name": "rss",
                    "summary": "",
                    "provides": {},
                    "source": "git",
                    "state": "restart_to_activate",
                    "removable": True,
                    "in_use_by": [],
                }
            ],
        },
    )
    monkeypatch.setattr(webui_mod, "_load_catalog_lazy", lambda: fake_catalog)

    manifest_path = tmp_path / "requirements-plugins.txt"
    manifest_path.write_text("# existing manifest\n")

    client = await _client(tmp_path, token="s3cret")
    try:
        resp = await client.post(
            "/api/store/install",
            json={"namespace": "rss.feed"},
            headers={"X-Web-Token": "s3cret"},
        )
        assert resp.status == 200
        # .bak must exist with the prior content.
        bak = manifest_path.with_suffix(manifest_path.suffix + ".bak")
        assert bak.exists(), ".bak was not created"
        assert bak.read_text() == "# existing manifest\n"
        # requirement line in manifest.
        assert fake_entry.requirement() in manifest_path.read_text()
    finally:
        await client.close()


async def test_install_without_token_rejected(tmp_path, monkeypatch):
    """POST /api/store/install without token (token configured) → 401."""
    import led_ticker.webui as webui_mod

    monkeypatch.setattr(
        webui_mod,
        "_build_store",
        lambda **kw: {
            "display_online": False,
            "pending_count": 0,
            "auth_required": True,
            "plugins": [],
        },
    )

    client = await _client(tmp_path, token="s3cret")
    try:
        # No auth header at all.
        resp = await client.post(
            "/api/store/install",
            json={"namespace": "rss.feed"},
        )
        assert resp.status in (401, 403)
    finally:
        await client.close()


async def test_install_unknown_namespace_returns_400(tmp_path, monkeypatch):
    """POST /api/store/install with a namespace not in the catalog → 400."""
    import led_ticker.webui as webui_mod
    from led_ticker.plugins_catalog import Catalog

    # Empty catalog — no known namespaces.
    monkeypatch.setattr(webui_mod, "_load_catalog_lazy", lambda: Catalog(entries=()))
    monkeypatch.setattr(
        webui_mod,
        "_build_store",
        lambda **kw: {
            "display_online": False,
            "pending_count": 0,
            "auth_required": True,
            "plugins": [],
        },
    )

    client = await _client(tmp_path, token="s3cret")
    try:
        resp = await client.post(
            "/api/store/install",
            json={"namespace": "notreal.plugin"},
            headers={"X-Web-Token": "s3cret"},
        )
        assert resp.status == 400
        body = await resp.json()
        assert body.get("error") == "unknown plugin"
    finally:
        await client.close()


async def test_install_idempotent_when_already_declared(tmp_path, monkeypatch):
    """If requirement already in manifest, install is a no-op → 200, no dup."""
    import led_ticker.webui as webui_mod
    from led_ticker.plugins_catalog import (
        Catalog,
        CatalogEntry,
        CatalogSource,
        PluginProvides,
    )

    fake_entry = CatalogEntry(
        name="rss",
        namespace="rss.feed",
        summary="RSS feed.",
        homepage="",
        provides=PluginProvides(widgets=("rss.feed",)),
        sources=(
            CatalogSource(
                type="git",
                url="https://github.com/JamesAwesome/led-ticker-plugins",
                ref="main",
                subdirectory="plugins/rss",
            ),
        ),
    )
    fake_catalog = Catalog(entries=(fake_entry,))
    req = fake_entry.requirement()

    monkeypatch.setattr(
        webui_mod,
        "_build_store",
        lambda **kw: {
            "display_online": False,
            "pending_count": 0,
            "auth_required": True,
            "plugins": [
                {
                    "namespace": "rss.feed",
                    "name": "rss",
                    "summary": "",
                    "provides": {},
                    "source": "git",
                    "state": "active",
                    "removable": True,
                    "in_use_by": [],
                }
            ],
        },
    )
    monkeypatch.setattr(webui_mod, "_load_catalog_lazy", lambda: fake_catalog)

    manifest_path = tmp_path / "requirements-plugins.txt"
    manifest_path.write_text(req + "\n")

    client = await _client(tmp_path, token="s3cret")
    try:
        resp = await client.post(
            "/api/store/install",
            json={"namespace": "rss.feed"},
            headers={"X-Web-Token": "s3cret"},
        )
        assert resp.status == 200
        # Manifest must not have duplicate lines for the same plugin.
        lines = [
            ln.strip()
            for ln in manifest_path.read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        assert lines.count(req) == 1, "duplicate requirement line written"
    finally:
        await client.close()


# DELETE /api/store/remove — plugin store remove (Task 5)
# ---------------------------------------------------------------------------


def _fake_rss_entry():
    """Return a minimal CatalogEntry for the rss plugin (test fixture).

    Namespace is "rss" (single-segment, matching the real catalog).  The widget
    type "rss.feed" maps back to namespace "rss" via config_references' split-on-dot
    logic (ns_source.split(".")[0]).
    """
    from led_ticker.plugins_catalog import (
        Catalog,
        CatalogEntry,
        CatalogSource,
        PluginProvides,
    )

    entry = CatalogEntry(
        name="rss",
        namespace="rss",
        summary="RSS/Atom feed headlines.",
        homepage="",
        provides=PluginProvides(widgets=("rss.feed",)),
        sources=(
            CatalogSource(
                type="git",
                url="https://github.com/JamesAwesome/led-ticker-plugins",
                ref="main",
                subdirectory="plugins/rss",
            ),
        ),
    )
    return entry, Catalog(entries=(entry,))


async def test_remove_known_namespace_removes_manifest_line(tmp_path, monkeypatch):
    """DELETE /api/store/remove with a declared namespace (not in config) →
    200, manifest line removed, response carries the updated store entry."""
    import led_ticker.webui as webui_mod

    fake_entry, fake_catalog = _fake_rss_entry()
    req = fake_entry.requirement()

    def fake_build_store(**kwargs):
        return {
            "display_online": False,
            "pending_count": 0,
            "auth_required": True,
            "plugins": [
                {
                    "namespace": "rss",
                    "name": "rss",
                    "summary": "RSS/Atom feed headlines.",
                    "provides": {"widgets": ["rss.feed"]},
                    "source": "git",
                    "state": "available",
                    "removable": False,
                    "in_use_by": [],
                }
            ],
        }

    monkeypatch.setattr(webui_mod, "_build_store", fake_build_store)
    monkeypatch.setattr(webui_mod, "_load_catalog_lazy", lambda: fake_catalog)

    # Write a manifest containing the rss requirement.
    manifest_path = tmp_path / "requirements-plugins.txt"
    manifest_path.write_text(req + "\n")

    client = await _client(tmp_path, token="s3cret")
    try:
        resp = await client.delete(
            "/api/store/remove",
            json={"namespace": "rss"},
            headers={"X-Web-Token": "s3cret"},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["namespace"] == "rss"
        # Manifest must no longer contain the requirement line.
        manifest_text = manifest_path.read_text()
        assert req not in manifest_text
    finally:
        await client.close()


async def test_remove_in_use_returns_409(tmp_path, monkeypatch):
    """DELETE /api/store/remove when config references the plugin → 409 with
    in_use_by listing {section, type}; manifest unchanged."""
    import led_ticker.webui as webui_mod

    fake_entry, fake_catalog = _fake_rss_entry()
    req = fake_entry.requirement()

    def fake_build_store(**kwargs):
        return {
            "display_online": False,
            "pending_count": 0,
            "auth_required": True,
            "plugins": [],
        }

    # config_references will return refs for rss.feed because the config TOML
    # contains a widget with type = "rss.feed".
    config_text = '[display]\nrows = 16\ncols = 32\n\n[[section]]\ntype = "rss.feed"\n'

    monkeypatch.setattr(webui_mod, "_build_store", fake_build_store)
    monkeypatch.setattr(webui_mod, "_load_catalog_lazy", lambda: fake_catalog)

    manifest_path = tmp_path / "requirements-plugins.txt"
    manifest_path.write_text(req + "\n")

    client = await _client(tmp_path, token="s3cret", config_text=config_text)
    try:
        resp = await client.delete(
            "/api/store/remove",
            json={"namespace": "rss"},
            headers={"X-Web-Token": "s3cret"},
        )
        assert resp.status == 409
        body = await resp.json()
        assert body.get("error") == "in_use"
        assert "in_use_by" in body
        refs = body["in_use_by"]
        assert isinstance(refs, list) and len(refs) > 0
        assert any(r.get("type") == "rss.feed" for r in refs)
        # Manifest must be UNCHANGED.
        assert manifest_path.read_text() == req + "\n"
    finally:
        await client.close()


async def test_remove_without_token_rejected(tmp_path, monkeypatch):
    """DELETE /api/store/remove without token (token configured) → 401/403."""
    import led_ticker.webui as webui_mod

    _, fake_catalog = _fake_rss_entry()
    monkeypatch.setattr(webui_mod, "_load_catalog_lazy", lambda: fake_catalog)
    monkeypatch.setattr(
        webui_mod,
        "_build_store",
        lambda **kw: {
            "display_online": False,
            "pending_count": 0,
            "auth_required": True,
            "plugins": [],
        },
    )

    client = await _client(tmp_path, token="s3cret")
    try:
        resp = await client.delete(
            "/api/store/remove",
            json={"namespace": "rss"},
        )
        assert resp.status in (401, 403)
    finally:
        await client.close()


async def test_remove_unknown_namespace_returns_400(tmp_path, monkeypatch):
    """DELETE /api/store/remove with a namespace not in the catalog → 400."""
    import led_ticker.webui as webui_mod
    from led_ticker.plugins_catalog import Catalog

    monkeypatch.setattr(webui_mod, "_load_catalog_lazy", lambda: Catalog(entries=()))
    monkeypatch.setattr(
        webui_mod,
        "_build_store",
        lambda **kw: {
            "display_online": False,
            "pending_count": 0,
            "auth_required": True,
            "plugins": [],
        },
    )

    client = await _client(tmp_path, token="s3cret")
    try:
        resp = await client.delete(
            "/api/store/remove",
            json={"namespace": "notreal.plugin"},
            headers={"X-Web-Token": "s3cret"},
        )
        assert resp.status == 400
        body = await resp.json()
        assert body.get("error") == "unknown plugin"
    finally:
        await client.close()


async def test_install_oversize_body_is_413(tmp_path):
    """POST /api/store/install with an oversized body → 413 before JSON parse."""
    client = await _client(tmp_path, token="s3cret")
    try:
        resp = await client.post(
            "/api/store/install",
            data="x" * (1024 * 1024 + 1),
            headers={"X-Web-Token": "s3cret", "Content-Type": "application/json"},
        )
        assert resp.status == 413
    finally:
        await client.close()


async def test_remove_oversize_body_is_413(tmp_path):
    """DELETE /api/store/remove with an oversized body → 413 before JSON parse."""
    client = await _client(tmp_path, token="s3cret")
    try:
        resp = await client.delete(
            "/api/store/remove",
            data="x" * (1024 * 1024 + 1),
            headers={"X-Web-Token": "s3cret", "Content-Type": "application/json"},
        )
        assert resp.status == 413
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# GET /api/store — anonymous redaction (defense-in-depth)
# ---------------------------------------------------------------------------

_RICH_FAKE_PAYLOAD = {
    "display_online": True,
    "pending_count": 1,
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
            "namespace": "crypto",
            "name": "Crypto",
            "summary": "CoinGecko ticker",
            "provides": {"widgets": ["crypto.coingecko"]},
            "source": "git",
            "state": "available",
            "removable": False,
            "in_use_by": [],
        },
    ],
}


async def test_store_token_configured_no_token_header_redacts(tmp_path, monkeypatch):
    """Token configured but no token supplied → response is redacted.

    Specifically: in_use_by empty, state coarsened, removable False,
    pending_count 0.
    """
    import led_ticker.webui as webui_mod

    monkeypatch.setattr(webui_mod, "_build_store", lambda **kw: _RICH_FAKE_PAYLOAD)

    client = await _client(tmp_path, token="s3cret")
    try:
        # No auth header — store is still open (in _OPEN_PATHS).
        resp = await client.get("/api/store")
        assert resp.status == 200
        body = await resp.json()
        # No in_use_by entries must leak.
        for plugin in body["plugins"]:
            assert plugin["in_use_by"] == [], (
                f"in_use_by leaked for {plugin['namespace']}"
            )
        # States coarsened: active → installed, available → available.
        ns_state = {p["namespace"]: p["state"] for p in body["plugins"]}
        assert ns_state["rss"] == "installed"
        assert ns_state["crypto"] == "available"
        # pending_count zeroed.
        assert body["pending_count"] == 0
        # removable always False.
        assert all(not p["removable"] for p in body["plugins"])
        # Public catalog fields intact.
        rss = next(p for p in body["plugins"] if p["namespace"] == "rss")
        assert rss["name"] == "RSS Feed"
        assert rss["summary"] == "RSS headlines"
    finally:
        await client.close()


async def test_store_token_configured_correct_token_gives_full_payload(
    tmp_path, monkeypatch
):
    """Token configured + correct token supplied → full unredacted payload."""
    import led_ticker.webui as webui_mod

    monkeypatch.setattr(webui_mod, "_build_store", lambda **kw: _RICH_FAKE_PAYLOAD)

    client = await _client(tmp_path, token="s3cret")
    try:
        resp = await client.get("/api/store", headers={"X-Web-Token": "s3cret"})
        assert resp.status == 200
        body = await resp.json()
        # Full in_use_by present.
        rss = next(p for p in body["plugins"] if p["namespace"] == "rss")
        assert len(rss["in_use_by"]) == 1
        assert rss["in_use_by"][0]["section"] == "Morning"
        # Granular state preserved.
        assert rss["state"] == "active"
        assert rss["removable"] is True
        # pending_count unredacted.
        assert body["pending_count"] == 1
    finally:
        await client.close()


async def test_store_no_token_configured_gives_full_payload(tmp_path, monkeypatch):
    """No token configured → full payload (no token = open system, nothing to hide)."""
    import led_ticker.webui as webui_mod

    monkeypatch.setattr(webui_mod, "_build_store", lambda **kw: _RICH_FAKE_PAYLOAD)

    # token="" means no token configured.
    client = await _client(tmp_path, token="")
    try:
        resp = await client.get("/api/store")
        assert resp.status == 200
        body = await resp.json()
        # Full in_use_by present.
        rss = next(p for p in body["plugins"] if p["namespace"] == "rss")
        assert len(rss["in_use_by"]) == 1
        assert rss["state"] == "active"
        assert rss["removable"] is True
        assert body["pending_count"] == 1
    finally:
        await client.close()


async def test_store_wrong_token_gives_redacted(tmp_path, monkeypatch):
    """Wrong token → still 200 (open route) but payload is redacted."""
    import led_ticker.webui as webui_mod

    monkeypatch.setattr(webui_mod, "_build_store", lambda **kw: _RICH_FAKE_PAYLOAD)

    client = await _client(tmp_path, token="s3cret")
    try:
        resp = await client.get("/api/store", headers={"X-Web-Token": "wrongtoken"})
        assert resp.status == 200
        body = await resp.json()
        for plugin in body["plugins"]:
            assert plugin["in_use_by"] == []
        rss = next(p for p in body["plugins"] if p["namespace"] == "rss")
        assert rss["state"] == "installed"
        assert rss["removable"] is False
        assert body["pending_count"] == 0
    finally:
        await client.close()


async def test_store_correct_token_via_query_param_gives_full(tmp_path, monkeypatch):
    """Correct token via ?token= query param → full payload (mirrors auth)."""
    import led_ticker.webui as webui_mod

    monkeypatch.setattr(webui_mod, "_build_store", lambda **kw: _RICH_FAKE_PAYLOAD)

    client = await _client(tmp_path, token="s3cret")
    try:
        resp = await client.get("/api/store", params={"token": "s3cret"})
        assert resp.status == 200
        body = await resp.json()
        rss = next(p for p in body["plugins"] if p["namespace"] == "rss")
        assert rss["state"] == "active"
        assert len(rss["in_use_by"]) == 1
    finally:
        await client.close()
