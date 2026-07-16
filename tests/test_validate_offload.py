"""#302: the reload-path validate must not block the event loop.

Strategy: monkeypatch the extracted sync brackets with versions that
time.sleep (a REAL thread block); a concurrent heartbeat task must keep
ticking while validate_config runs. If the brackets ran on the loop, the
heartbeat would freeze for the sleep duration."""

import asyncio
import time
from pathlib import Path

import pytest

from led_ticker import validate as validate_mod

CONFIG = Path(__file__).parent.parent / "config" / "config.example.toml"


@pytest.mark.asyncio
async def test_validate_config_does_not_block_the_loop(monkeypatch):
    real_pre = validate_mod._validate_static_prebuild

    def slow_pre(path, *, strict, config_dir):
        time.sleep(0.5)  # real thread block — NOT asyncio.sleep
        return real_pre(path, strict=strict, config_dir=config_dir)

    monkeypatch.setattr(validate_mod, "_validate_static_prebuild", slow_pre)

    beats = 0

    async def heartbeat():
        nonlocal beats
        while True:
            beats += 1
            await asyncio.sleep(0.05)

    hb = asyncio.create_task(heartbeat())
    try:
        result = await validate_mod.validate_config(CONFIG)
    finally:
        hb.cancel()
        with pytest.raises(asyncio.CancelledError):
            await hb
    # 0.5s of thread-blocked prebuild → the loop should have ticked ~10x.
    # Generous floor (3) keeps slow CI honest without flaking.
    assert beats >= 3, f"event loop starved during validate ({beats} beats)"
    assert result is not None


@pytest.mark.asyncio
async def test_load_and_validate_offloads_the_duplicate_load(monkeypatch):
    """The reload path's second load_config must run via to_thread."""
    from led_ticker import reload as reload_mod

    calls = []
    real_to_thread = asyncio.to_thread

    async def spy_to_thread(fn, *args, **kwargs):
        calls.append(getattr(fn, "__name__", repr(fn)))
        return await real_to_thread(fn, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", spy_to_thread)
    config, errors, transient = await reload_mod.load_and_validate(CONFIG)
    assert config is not None and errors == [] and transient is False
    assert "load_config" in calls, f"duplicate load not offloaded: {calls}"
    assert "_validate_static_prebuild" in calls
    assert "_validate_static_postbuild" in calls
