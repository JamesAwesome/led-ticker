"""Tests for the busy-light HTTP listener."""

import aiohttp
from aiohttp.test_utils import TestClient, TestServer

from led_ticker.busy_http import build_busy_app, serve_busy
from led_ticker.busy_light import BusyLight


async def _client(busy, token=""):
    app = build_busy_app(busy, token=token)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


async def test_get_query_sets_busy_on_and_off():
    busy = BusyLight(file_path="/x")
    client = await _client(busy)
    try:
        resp = await client.get("/busy", params={"state": "on"})
        assert resp.status == 200
        assert (await resp.json())["busy"] is True
        assert busy.is_busy is True

        resp = await client.get("/busy", params={"state": "off"})
        assert (await resp.json())["busy"] is False
        assert busy.is_busy is False
    finally:
        await client.close()


async def test_post_body_sets_busy():
    busy = BusyLight(file_path="/x")
    client = await _client(busy)
    try:
        resp = await client.post("/busy", data="on")
        assert resp.status == 200
        assert busy.is_busy is True
    finally:
        await client.close()


async def test_get_no_state_reports_current():
    busy = BusyLight(file_path="/x")
    busy.is_busy = True
    client = await _client(busy)
    try:
        resp = await client.get("/busy")
        assert resp.status == 200
        assert (await resp.json())["busy"] is True
    finally:
        await client.close()


async def test_bad_state_returns_400():
    busy = BusyLight(file_path="/x")
    client = await _client(busy)
    try:
        resp = await client.get("/busy", params={"state": "maybe"})
        assert resp.status == 400
        assert busy.is_busy is False
    finally:
        await client.close()


async def test_token_required_when_configured():
    busy = BusyLight(file_path="/x")
    client = await _client(busy, token="s3cret")
    try:
        # missing token
        resp = await client.get("/busy", params={"state": "on"})
        assert resp.status == 401
        assert busy.is_busy is False
        # query token
        resp = await client.get("/busy", params={"state": "on", "token": "s3cret"})
        assert resp.status == 200
        assert busy.is_busy is True
        # header token
        busy.is_busy = False
        resp = await client.get(
            "/busy", params={"state": "on"}, headers={"X-Busy-Token": "s3cret"}
        )
        assert resp.status == 200
        assert busy.is_busy is True
    finally:
        await client.close()


async def test_wrong_token_returns_401():
    busy = BusyLight(file_path="/x")
    client = await _client(busy, token="s3cret")
    try:
        resp = await client.get("/busy", params={"state": "on", "token": "nope"})
        assert resp.status == 401
        assert busy.is_busy is False
    finally:
        await client.close()


async def test_serve_busy_binds_and_responds():
    busy = BusyLight(file_path="/x")
    runner = await serve_busy(busy, host="127.0.0.1", port=0)
    try:
        port = runner.addresses[0][1]
        async with aiohttp.ClientSession() as s, s.get(
            f"http://127.0.0.1:{port}/busy", params={"state": "on"}
        ) as r:
            assert r.status == 200
        assert busy.is_busy is True
    finally:
        await runner.cleanup()
