"""Web status UI sidecar (led-ticker webui).

Pure builder (build_webui_app) + production runner (serve_webui/run_webui),
mirroring busy_http. The sidecar never writes status.json. It touches
config.toml only through the token-gated PUT /api/config editor
(validate → conflict-check → backup → atomic write); all GET and preview
routes remain read-only. Without a token, the editor is disabled and Save
returns 403. It must keep working when the display process is absent —
every degraded state is a friendly JSON answer, not a 500. This module
must never import rgbmatrix (tripwire lands in tests/test_webui_purity.py).
"""

import asyncio
import json
import logging
import os
import shutil
import time
import tomllib
from importlib import resources
from pathlib import Path

from aiohttp import web

from led_ticker.config import resolve_secret_token
from led_ticker.preview import HEADER, PREVIEW_MAGIC, PREVIEW_VERSION
from led_ticker.reload import config_hash
from led_ticker.status_board import SCHEMA_VERSION
from led_ticker.validate import (
    ValidationResult,
    validate_config,
    validate_config_text,
)
from led_ticker.webui._paths import list_config_names, safe_config_member
from led_ticker.webui.redact import REDACTED, redact_toml, restore_redacted

# led_ticker.validate was verified clean of rgbmatrix at task-8 implementation
# time:  python -c "import led_ticker.validate; print([m for m in
# sys.modules if 'rgbmatrix' in m])"  → [].  Top-level import is safe.

logger = logging.getLogger(__name__)

STALE_FACTOR = 3.0  # stale when published_at is older than factor × min_interval
MAX_VALIDATE_BODY = 1024 * 1024  # 1 MB (used by the /api/validate task)


def _read_status(status_path: Path) -> dict:
    """Classify the status file into the API envelope. Never raises."""
    try:
        # Size is unbounded: the only writer is the trusted display process,
        # and status.json is a single small snapshot — not user-controlled input.
        raw = status_path.read_text()
    except FileNotFoundError:
        return {
            "state": "missing",
            "hint": (
                "The display process hasn't published yet — is led-ticker "
                "running, and does its config have a [web] block?"
            ),
        }
    except OSError as e:
        return {"state": "unreadable", "detail": str(e)}
    try:
        status = json.loads(raw)
    except ValueError as e:
        return {"state": "unreadable", "detail": f"bad JSON: {e}"}
    if not isinstance(status, dict):
        return {
            "state": "unreadable",
            "detail": f"not a JSON object (got {type(status).__name__})",
        }
    found = status.get("schema")
    if found != SCHEMA_VERSION:
        return {
            "state": "schema_mismatch",
            "found": found,
            "supported": SCHEMA_VERSION,
            "hint": "led-ticker and the webui are running different versions.",
        }
    try:
        age = time.time() - float(status.get("published_at", 0))
        threshold = STALE_FACTOR * float(status.get("min_interval", 2.0))
    except (TypeError, ValueError) as e:
        # Schema-valid envelope but corrupt timing fields (truncated write,
        # hand-edited file). Classify, never raise.
        return {"state": "unreadable", "detail": f"bad timing field: {e}"}
    state = "stale" if age > threshold else "ok"
    return {"state": state, "age_seconds": round(age, 1), "status": status}


def build_webui_app(
    *, config_path: Path, status_path: Path, token: str = ""
) -> web.Application:
    """Build the aiohttp app. Pure: no I/O at build time."""

    @web.middleware
    async def auth(request: web.Request, handler):
        if token:
            provided = request.headers.get("X-Web-Token") or request.query.get("token")
            if provided != token:
                return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request)

    async def status_handler(request: web.Request) -> web.Response:
        return web.json_response(_read_status(status_path))

    preview_frame_path = status_path.parent / "preview.bin"
    preview_marker_path = status_path.parent / "preview-requested"

    async def preview_handler(request: web.Request) -> web.Response:
        # The fetch IS the watch signal: touch the marker first, so even an
        # idle answer wakes the display's mirror for the next poll. This is
        # the sidecar's only write, ever — one empty file, mtime-only.
        try:
            preview_marker_path.touch()
        except OSError:
            logger.debug("could not touch preview marker", exc_info=True)
        try:
            data = preview_frame_path.read_bytes()
        except FileNotFoundError:
            return web.json_response({"state": "idle"})
        except OSError as e:
            return web.json_response({"state": "idle", "detail": str(e)})
        if len(data) < HEADER.size:
            return web.json_response({"state": "unsupported"})
        magic, ver, w, h, _res, seq = HEADER.unpack(data[: HEADER.size])
        if (
            magic != PREVIEW_MAGIC
            or ver != PREVIEW_VERSION
            or len(data) != HEADER.size + w * h * 3
        ):
            return web.json_response({"state": "unsupported"})
        return web.Response(
            body=data[HEADER.size :],
            content_type="application/octet-stream",
            headers={
                "X-Preview-Width": str(w),
                "X-Preview-Height": str(h),
                "X-Preview-Seq": str(seq),
            },
        )

    app = web.Application(middlewares=[auth])
    app.router.add_get("/api/status", status_handler)
    _add_config_routes(app, config_path, token)
    app.router.add_get("/api/preview", preview_handler)
    _add_page_route(app)
    return app


def _result_to_json(result: ValidationResult) -> dict:
    """Serialize a ValidationResult for the browser.

    Deliberately excludes result.path — for text validation it is a
    throwaway temp file whose path must not be leaked to the browser.
    ValidationIssue fields: rule, location, message, fix, severity.
    """

    def _issue(i) -> dict:
        return {
            "rule": i.rule,
            "location": i.location,
            "message": i.message,
            "fix": i.fix,
            "severity": i.severity,
        }

    return {
        "valid": result.valid,
        "errors": [_issue(i) for i in result.errors],
        "warnings": [_issue(i) for i in result.warnings],
    }


def _add_config_routes(
    app: web.Application, config_path: Path, token: str = ""
) -> None:
    """Register config routes: GET /api/configs, GET /api/config,
    POST /api/validate, PUT /api/config."""

    async def configs_handler(request: web.Request) -> web.Response:
        config_dir = config_path.parent
        return web.json_response(
            {
                "configs": list_config_names(config_dir),
                "running": config_path.name,
            }
        )

    async def config_handler(request: web.Request) -> web.Response:
        target = config_path
        name = request.query.get("name")
        if name is not None:
            member = safe_config_member(config_path.parent, name)
            if member is None:
                return web.json_response({"error": "unknown config"}, status=404)
            target = member
        try:
            text = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return web.json_response({"state": "unreadable", "detail": str(e)})
        geometry: dict = {}
        try:
            display = tomllib.loads(text).get("display", {})
            rows = int(display.get("rows", 16))
            cols = int(display.get("cols", 32))
            chain = int(display.get("chain_length", 1))
            parallel = int(display.get("parallel", 1))
            geometry = {
                "rows": rows,
                "cols": cols,
                "chain_length": chain,
                "parallel": parallel,
                "default_scale": int(display.get("default_scale", 1)),
                "panel_width": cols * chain,
                "panel_height": rows * parallel,
            }
        except (ValueError, TypeError, tomllib.TOMLDecodeError):
            pass  # geometry is best-effort; the redacted text is the point
        return web.json_response(
            {
                "state": "ok",
                "toml": redact_toml(text),
                "geometry": geometry,
                "hash": config_hash(target) or "",
            }
        )

    async def validate_handler(request: web.Request) -> web.Response:
        if (request.content_length or 0) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)
        body = await request.text()
        if len(body.encode()) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)
        result = await validate_config_text(body)
        return web.json_response(_result_to_json(result))

    async def validate_file_handler(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except ValueError:
            return web.json_response({"error": "body must be JSON"}, status=400)
        name = payload.get("name") if isinstance(payload, dict) else None
        if not isinstance(name, str):
            return web.json_response({"error": "missing name"}, status=400)
        target = safe_config_member(config_path.parent, name)
        if target is None:
            return web.json_response({"error": "unknown config"}, status=404)
        try:
            result = await validate_config(target)
        except FileNotFoundError:
            # TOCTOU: the file passed the guard but vanished before the
            # validate. Same envelope as never-existed — no oracle, no 500.
            return web.json_response({"error": "unknown config"}, status=404)
        return web.json_response(_result_to_json(result))

    async def save_handler(request: web.Request) -> web.Response:
        if not token:
            return web.json_response({"error": "editing disabled"}, status=403)
        if (request.content_length or 0) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)
        try:
            payload = await request.json()
        except ValueError:
            return web.json_response({"error": "body must be JSON"}, status=400)
        toml_text = payload.get("toml") if isinstance(payload, dict) else None
        base_hash = payload.get("base_hash") if isinstance(payload, dict) else None
        if not isinstance(toml_text, str) or not isinstance(base_hash, str):
            return web.json_response({"error": "missing toml/base_hash"}, status=400)
        if len(toml_text.encode()) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)

        # Conflict check FIRST — never validate/work against a file that moved.
        current = config_hash(config_path)
        if current is not None and base_hash != current:
            return web.json_response(
                {"error": "conflict", "hash": current}, status=409
            )

        # Restore any redacted secret from disk (no-op for secret-free config).
        try:
            disk_text = config_path.read_text(encoding="utf-8")
        except OSError:
            disk_text = ""
        merged = restore_redacted(toml_text, disk_text)
        if REDACTED.strip() in merged:
            return web.json_response(
                {
                    "error": (
                        "unresolved redacted value; replace ••• with the real "
                        "value or edit the file directly"
                    )
                },
                status=400,
            )

        result = await validate_config_text(merged)
        if not result.valid:
            return web.json_response(_result_to_json(result), status=422)

        # Backup + atomic write.
        try:
            if config_path.exists():
                bak = config_path.with_suffix(config_path.suffix + ".bak")
                shutil.copy2(config_path, bak)
            tmp = config_path.with_name(config_path.name + ".tmp")
            tmp.write_text(merged, encoding="utf-8")
            os.replace(tmp, config_path)
        except OSError as e:
            return web.json_response({"error": f"write failed: {e}"}, status=500)

        return web.json_response(
            {"state": "saved", "hash": config_hash(config_path) or ""}
        )

    app.router.add_get("/api/configs", configs_handler)
    app.router.add_get("/api/config", config_handler)
    app.router.add_post("/api/validate", validate_handler)
    app.router.add_post("/api/validate-file", validate_file_handler)
    app.router.add_put("/api/config", save_handler)

    async def inventory_handler(request: web.Request) -> web.Response:
        from led_ticker.webui.inventory import build_inventory  # noqa: PLC0415

        return web.json_response(build_inventory(config_path.parent))

    app.router.add_get("/api/inventory", inventory_handler)


def _add_page_route(app: web.Application) -> None:
    async def index(request: web.Request) -> web.Response:
        html = (
            resources.files("led_ticker.webui").joinpath("static/index.html")
        ).read_text(encoding="utf-8")
        return web.Response(text=html, content_type="text/html")

    app.router.add_get("/", index)


async def serve_webui(
    *, config_path: Path, status_path: Path, host: str, port: int, token: str = ""
) -> web.AppRunner:
    """Start the listener; caller keeps the runner and calls .cleanup().
    Same contract as busy_http.serve_busy."""
    runner = web.AppRunner(
        build_webui_app(config_path=config_path, status_path=status_path, token=token)
    )
    await runner.setup()
    try:
        site = web.TCPSite(runner, host, port)
        await site.start()
    except Exception:
        await runner.cleanup()
        raise
    logger.info("webui listening on %s:%d", host, port)
    return runner


async def run_webui(config_path: Path, web_cfg) -> None:
    """Process entry point for `led-ticker webui`. Runs until cancelled."""
    runner = await serve_webui(
        config_path=config_path,
        status_path=Path(web_cfg.status_path).expanduser(),
        host=web_cfg.http_host,
        port=web_cfg.http_port,
        token=resolve_secret_token(
            "LED_TICKER_WEB_TOKEN", web_cfg.token, label="web.token"
        ),
    )
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
