"""Web status UI sidecar (led-ticker webui).

Pure builder (build_webui_app) + production runner (serve_webui/run_webui,
added in a later task), mirroring busy_http. The sidecar is a pure READER: it
never writes status.json and never touches the config file. It must keep
working when the display process is absent — every degraded state is a
friendly JSON answer, not a 500. This module must never import rgbmatrix
(tripwire lands in tests/test_webui_purity.py).
"""

import json
import logging
import time
from pathlib import Path

from aiohttp import web

from led_ticker.status_board import SCHEMA_VERSION

logger = logging.getLogger(__name__)

STALE_FACTOR = 3.0  # stale when published_at is older than factor × min_interval
MAX_VALIDATE_BODY = 1024 * 1024  # 1 MB (used by the /api/validate task)


def _read_status(status_path: Path) -> dict:
    """Classify the status file into the API envelope. Never raises."""
    try:
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


def _add_config_routes(app: web.Application, config_path: Path) -> None:
    """Filled in by the /api/config + /api/validate task."""


def _add_page_route(app: web.Application) -> None:
    """Filled in by the static-page task."""
