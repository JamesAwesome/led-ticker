"""Web status UI sidecar (led-ticker webui).

Pure builder (build_webui_app) + production runner (serve_webui/run_webui,
added in a later task), mirroring busy_http. The sidecar is a pure READER: it
never writes status.json and never touches the config file. It must keep
working when the display process is absent — every degraded state is a
friendly JSON answer, not a 500. This module must never import rgbmatrix
(tripwire lands in tests/test_webui_purity.py).
"""

import asyncio
import json
import logging
import time
import tomllib
from importlib import resources
from pathlib import Path

from aiohttp import web

from led_ticker.status_board import SCHEMA_VERSION
from led_ticker.validate import ValidationResult, validate_config_text
from led_ticker.webui.redact import redact_toml

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
            provided = request.headers.get("X-Web-Token") or request.query.get(
                "token"
            )
            if provided != token:
                return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request)

    async def status_handler(request: web.Request) -> web.Response:
        return web.json_response(_read_status(status_path))

    app = web.Application(middlewares=[auth])
    app.router.add_get("/api/status", status_handler)
    _add_config_routes(app, config_path)  # Task 8 fills this in
    _add_page_route(app)  # Task 9 fills this in
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


def _add_config_routes(app: web.Application, config_path: Path) -> None:
    """Register GET /api/config and POST /api/validate on the app."""

    async def config_handler(request: web.Request) -> web.Response:
        try:
            text = config_path.read_text(encoding="utf-8")
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
            {"state": "ok", "toml": redact_toml(text), "geometry": geometry}
        )

    async def validate_handler(request: web.Request) -> web.Response:
        if (request.content_length or 0) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)
        body = await request.text()
        if len(body.encode()) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)
        result = await validate_config_text(body)
        return web.json_response(_result_to_json(result))

    app.router.add_get("/api/config", config_handler)
    app.router.add_post("/api/validate", validate_handler)


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
        host=web_cfg.host,
        port=web_cfg.port,
        token=web_cfg.token,
    )
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
