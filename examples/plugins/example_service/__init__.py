"""Example led-ticker plugin: a 'service' plugin — a background poller + a status overlay.

Drop `example_service/` into your `config/plugins/` (local use), or package it with an
`[project.entry-points."led_ticker.plugins"]  example_service = "example_service:register"`
entry. No TOML needed — the overlay paints a corner status dot on every screen.

Imports only `led_ticker.plugin` (the public surface) plus stdlib.
"""

import asyncio

from led_ticker.plugin import spawn_tracked


def register(api):
    # Shared state: the background poller writes it, the overlay reads it.
    state = {"online": False}

    def paint(canvas):
        # Runs every frame on the real canvas, BEFORE the hardware swap. Keep it
        # paint-only and fast, and never raise — a raising overlay is disabled and
        # logged, and must never be able to freeze the panel.
        r, g, b = (0, 200, 0) if state["online"] else (200, 0, 0)
        canvas.SetPixel(0, 0, r, g, b)  # a status dot in the top-left corner

    api.overlay(paint)

    async def start(ctx):
        # Runs once, after the frame + HTTP session exist. `ctx.session` is the
        # shared aiohttp ClientSession; `ctx.config` is the parsed app config.
        async def poll():
            while True:
                try:
                    async with ctx.session.get("https://example.com/health") as resp:
                        state["online"] = resp.status == 200
                except Exception:
                    state["online"] = False
                await asyncio.sleep(30)

        # Launch the long-lived poller as a tracked background task.
        spawn_tracked(poll())

    api.on_startup(start)
