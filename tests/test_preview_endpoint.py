"""GET /api/preview: binary frames, idle/unsupported envelopes, marker touch."""

from aiohttp.test_utils import TestClient, TestServer

from led_ticker.preview import HEADER, PREVIEW_MAGIC, PREVIEW_VERSION
from led_ticker.webui import build_webui_app


async def _client(tmp_path, token=""):
    config_path = tmp_path / "config.toml"
    config_path.write_text("[display]\nrows = 16\ncols = 32\n")
    app = build_webui_app(
        config_path=config_path, status_path=tmp_path / "status.json", token=token
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


def _write_frame(tmp_path, width=32, height=16, seq=7):
    payload = (b"\x01\x02\x03" * (width * height))[: width * height * 3]
    header = HEADER.pack(PREVIEW_MAGIC, PREVIEW_VERSION, width, height, 0, seq)
    (tmp_path / "preview.bin").write_bytes(header + payload)
    return payload


async def test_preview_serves_frame_with_headers(tmp_path):
    payload = _write_frame(tmp_path)
    client = await _client(tmp_path)
    try:
        resp = await client.get("/api/preview")
        assert resp.status == 200
        assert resp.content_type == "application/octet-stream"
        assert resp.headers["X-Preview-Width"] == "32"
        assert resp.headers["X-Preview-Height"] == "16"
        assert resp.headers["X-Preview-Seq"] == "7"
        assert await resp.read() == payload
    finally:
        await client.close()


async def test_preview_touches_watch_marker(tmp_path):
    client = await _client(tmp_path)
    try:
        await client.get("/api/preview")  # even an idle fetch wakes the mirror
        assert (tmp_path / "preview-requested").exists()
    finally:
        await client.close()


async def test_preview_idle_when_no_frame(tmp_path):
    client = await _client(tmp_path)
    try:
        resp = await client.get("/api/preview")
        assert resp.status == 200
        assert (await resp.json())["state"] == "idle"
    finally:
        await client.close()


async def test_preview_unsupported_on_bad_magic_version_or_size(tmp_path):
    client = await _client(tmp_path)
    cases = [
        b"XXXX" + bytes(12),  # bad magic
        HEADER.pack(PREVIEW_MAGIC, 99, 32, 16, 0, 1) + bytes(32 * 16 * 3),  # version
        HEADER.pack(PREVIEW_MAGIC, PREVIEW_VERSION, 32, 16, 0, 1) + b"short",  # size
        b"tiny",  # shorter than the header
    ]
    try:
        for blob in cases:
            (tmp_path / "preview.bin").write_bytes(blob)
            resp = await client.get("/api/preview")
            assert resp.status == 200
            assert (await resp.json())["state"] == "unsupported"
    finally:
        await client.close()


async def test_preview_is_auth_gated(tmp_path):
    client = await _client(tmp_path, token="s3cret")
    try:
        assert (await client.get("/api/preview")).status == 401
        assert not (tmp_path / "preview-requested").exists()  # 401s do not wake
    finally:
        await client.close()
