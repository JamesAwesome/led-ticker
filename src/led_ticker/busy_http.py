"""HTTP push source for the busy light.

A one-route aiohttp app that flips BusyLight.is_busy from a remote trigger
(a work Mac's hotkey macro or macOS Focus automation). aiohttp is already a
runtime dependency (used as a client by the data widgets); this is the first
server. build_busy_app() is pure for testing; serve_busy() is the production
runner.
"""

from __future__ import annotations

import logging

from aiohttp import web

from led_ticker.busy_light import BusyLight

logger = logging.getLogger(__name__)

_TRUTHY = frozenset({"on", "1", "true"})
_FALSY = frozenset({"off", "0", "false"})


def _token_ok(request: web.Request, token: str) -> bool:
    if not token:
        return True
    provided = request.headers.get("X-Busy-Token") or request.query.get("token")
    return provided == token


def build_busy_app(busy: BusyLight, token: str = "") -> web.Application:
    """Build the aiohttp app. GET /busy?state=on|off or POST /busy (body=on|off)
    flips the flag; GET /busy with no state reports current state."""

    async def handle(request: web.Request) -> web.Response:
        if not _token_ok(request, token):
            return web.json_response({"error": "unauthorized"}, status=401)
        state = request.query.get("state")
        if state is None and request.body_exists:
            state = (await request.text()).strip()
        if state is None:
            return web.json_response({"busy": busy.is_busy})
        s = state.strip().lower()
        if s in _TRUTHY:
            busy.set_busy(True)
        elif s in _FALSY:
            busy.set_busy(False)
        else:
            return web.json_response({"error": "bad state"}, status=400)
        return web.json_response({"busy": busy.is_busy})

    app = web.Application()
    app.router.add_get("/busy", handle)
    app.router.add_post("/busy", handle)
    return app


async def serve_busy(
    busy: BusyLight, *, host: str, port: int, token: str = ""
) -> web.AppRunner:
    """Start the listener and return the running AppRunner (caller keeps it
    alive and calls .cleanup() on shutdown)."""
    runner = web.AppRunner(build_busy_app(busy, token=token))
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("busy-light HTTP listener on %s:%d", host, port)
    return runner
