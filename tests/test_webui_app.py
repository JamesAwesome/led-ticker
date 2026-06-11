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
