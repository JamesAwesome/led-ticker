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
        ):
            assert marker in text
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
