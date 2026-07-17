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


@pytest.mark.asyncio
async def test_validate_never_binds_schedules(tmp_path):
    """Validation must be side-effect-free on the schedule registry —
    a worker-thread validate that bound widgets would race the render
    loop's reads."""
    from led_ticker import schedule

    cfg = tmp_path / "c.toml"
    cfg.write_text(
        '[display]\nrows = 16\ncols = 32\nbackend = "headless"\n\n'
        '[[playlist.section]]\nmode = "slideshow"\n\n'
        '[[playlist.section.widget]]\ntype = "message"\ntext = "hi"\n'
        'schedule = { start = "09:00", end = "17:00" }\n'
    )
    before = dict(schedule._BINDINGS)
    result = await validate_mod.validate_config(cfg)
    assert result.valid, result.errors
    assert dict(schedule._BINDINGS) == before


def test_plugin_load_guard_is_first():
    """AST pin: load_plugins' idempotency guard must run before any
    mutating statement. The thread-safety of worker-thread validation
    rests on this guard being checked before any registry work begins —
    a racing second caller must see a pure read, not a partial rebuild.

    load_plugins' real shape is: docstring, `global _LOADED`, then the
    guard `if _LOADED is not None: return _LOADED` — so the pin skips
    over the (non-mutating) docstring and global declaration rather than
    requiring the guard to be the literal first statement.
    """
    import ast
    import inspect

    from led_ticker import _plugin_loader

    tree = ast.parse(inspect.getsource(_plugin_loader.load_plugins))
    fn_def = tree.body[0]
    assert isinstance(fn_def, ast.FunctionDef)
    body = fn_def.body
    stmts = [
        s
        for s in body
        if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
    ]
    idx = 1 if isinstance(stmts[0], ast.Global) else 0
    guard = stmts[idx]
    src = ast.unparse(guard)
    assert isinstance(guard, ast.If), (
        f"expected the idempotency guard immediately after the docstring/"
        f"global declaration, got: {src}"
    )
    assert "_LOADED" in src and "return" in src, src
