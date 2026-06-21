import asyncio

from led_ticker import widget


async def test_spawn_tracked_lands_in_active_sink():
    sink: set = set()
    token = widget._build_sink.set(sink)
    try:
        t = widget.spawn_tracked(asyncio.sleep(0.01))
    finally:
        widget._build_sink.reset(token)
    assert t in sink
    assert t in widget._BACKGROUND_TASKS
    t.cancel()


async def test_spawn_tracked_no_sink_only_global():
    # no active sink -> only the global registry
    t = widget.spawn_tracked(asyncio.sleep(0.01))
    assert t in widget._BACKGROUND_TASKS
    t.cancel()
