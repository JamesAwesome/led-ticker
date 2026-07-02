"""Integration test: boot real configs through the full production run() path.

== Bug class caught ==

A ``[[sections]]`` vs ``[[playlist.section]]`` TOML schema typo yields a config
that parses to 0 sections.  ``led-ticker validate`` passed silently, all 1438+
unit tests were green, and the panel busy-looped dark (infinite idle branch).
Two core fixes landed (PR #335: empty-playlist idle+warn; validate errors on 0
sections), but nothing in CI exercises ``run()``'s real startup — unit tests stub
around it, ``validate`` is static, and ``tools/render_demo`` uses a separate
renderer pipeline.  These tests close the "boots cleanly but renders dark"
gap end-to-end.

== What each test does ==

Each test starts ``run()`` as an asyncio task, condition-polls the headless
backend's ``swap()`` calls until ≥20 frames accumulate or 15 s elapses, then
asserts:
  - liveness:  ≥20 frames were swapped (proves the engine tick loop is running)
  - content:   ≥1 non-black frame (catches the dark-panel class of bug)
  - motion:    ≥2 distinct content hashes among non-black frames
               (frozen / stuck panel would fail here)

Polling uses a two-gate exit condition: ≥20 total swapped frames (liveness)
AND ≥2 distinct non-black content hashes (content+motion), with a 15 s ceiling.
For the purpose-built slideshow configs (each section held 0.5 s = 10 ticks), both
gates clear at frame 20 (≈1 s): 10 frames of section-1 hash + 10 frames of
section-2 hash.  For ``config.example.toml`` (ticker mode, ``title_delay=5``),
the title scrolls in from off-canvas: the first visible pixel arrives at ≈frame 46
(≈2.3 s into the run), so the poll runs past the 20-frame liveness gate until two
distinct non-black hashes accumulate (≈frame 47, still well within 15 s).

== Status board note ==

run() only activates a StatusBoard when ``[web]`` is configured in the TOML.
None of the fixture configs include ``[web]``, so ``get_active_board()`` returns
None and the ``swap_count`` assertion is skipped.  This is correct behaviour:
the headless integration path intentionally avoids the web-UI sidecar dependency.

== Runtime ==

Measured on a 2024 M-series MacBook Pro: ≈1–3 s per test, ≈5–8 s total.
Well under the 20 s per-test ceiling; no ``@pytest.mark.slow`` needed.

== Placement ==

Ordinary pytest under ``tests/``.  The tests run in the normal suite — no
special CI job, no Docker, no hardware.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import pathlib
import re
import time
from typing import Any

import pytest

from led_ticker import status_board as sb
from led_ticker.app.run import run
from led_ticker.backends.headless import HeadlessBackend, HeadlessCanvas
from led_ticker.widget import _BACKGROUND_TASKS

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CONFIG_DIR = _REPO_ROOT / "config"

# _MIN_FRAMES (liveness gate) — must accumulate at least this many total swaps.
# 20 frames at ENGINE_TICK_MS=50 ms ≈ 1 s covers both 0.5 s slideshow holds
# (2 × 10 ticks) AND acts as the baseline before any content check.
_MIN_FRAMES = 20

# _MIN_DISTINCT (content+motion gate) — poll continues until this many DISTINCT
# non-black content hashes are present (or _CEILING_S elapses).  2 satisfies
# both the content assertion (≥1 non-black) and the motion assertion (≥2 distinct
# hashes) in one condition.  For slideshow configs both gates are met at frame 20
# (section-1 hash ≠ section-2 hash).  For ticker-mode configs (config.example.toml)
# the title scrolls in from off-canvas: ~46 frames (≈2.3 s) elapse before the
# first pixel is visible, so the poll continues past _MIN_FRAMES until two distinct
# non-black hashes have accumulated — still well within _CEILING_S.  A dark-panel
# bug never produces any non-black frame; the poll times out and content assertion
# fails with a clear message.
_MIN_DISTINCT = 2
_CEILING_S = 15.0

# --------------------------------------------------------------------------- #
# Inline fixture configs                                                       #
# --------------------------------------------------------------------------- #

# Two slideshow sections (message + clock), cut transitions so frames
# accumulate as fast as ENGINE_TICK_MS allows.  20 frames spans both holds
# (2 × 10 ticks @ 50 ms each ≈ 1 s), yielding frames from two distinct
# sections → two distinct content hashes → motion assertion passes.
_SMALLSIGN_CONFIG = """\
[display]
rows = 16
cols = 32
chain_length = 5
backend = "headless"
hot_reload = false

[transitions]
default = "cut"
between_sections = "cut"

[[playlist.section]]
mode = "slideshow"
hold_time = 0.5
loop_count = 1

[[playlist.section.widget]]
type = "message"
text = "Hello LED world"

[[playlist.section]]
mode = "slideshow"
hold_time = 0.5
loop_count = 1

[[playlist.section.widget]]
type = "clock"
format = "12h"
"""

# Bigsign-shaped: rows×parallel = 64, default_scale = 4
# → content_height (16) × scale (4) = 64 = panel_h_real: exactly at the ceiling
#   (validated with `led-ticker validate` before merging this test).
# Headless canvas dims via HeadlessBackend: cols×chain_length = 256, rows = 64.
# Exercises the ScaledCanvas wrapper path end-to-end.
_BIGSIGN_CONFIG = """\
[display]
rows = 64
cols = 32
chain_length = 8
parallel = 1
default_scale = 4
backend = "headless"
hot_reload = false

[transitions]
default = "cut"
between_sections = "cut"

[[playlist.section]]
mode = "slideshow"
hold_time = 0.5
loop_count = 1

[[playlist.section.widget]]
type = "message"
text = "Bigsign test"

[[playlist.section]]
mode = "slideshow"
hold_time = 0.5
loop_count = 1

[[playlist.section.widget]]
type = "clock"
format = "12h"
"""

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _canvas_content_hash(canvas: HeadlessCanvas) -> str:
    """Dense row-major pixel scan → MD5 hex.

    Iterating the sparse ``_pixels`` dict directly would give
    order-dependent bytes; a fixed scan guarantees identical canvases
    always hash identically.
    """
    buf = bytearray(canvas.width * canvas.height * 3)
    idx = 0
    for y in range(canvas.height):
        for x in range(canvas.width):
            r, g, b = canvas._pixels.get((x, y), (0, 0, 0))
            buf[idx] = r
            buf[idx + 1] = g
            buf[idx + 2] = b
            idx += 3
    return hashlib.md5(bytes(buf), usedforsecurity=False).hexdigest()


async def _run_and_collect_frames(
    monkeypatch: Any,
    config_path: pathlib.Path,
) -> list[tuple[int, str]]:
    """Start ``run(config_path)`` and collect (count_nonzero, hash) per frame.

    Polls until _MIN_FRAMES frames arrive or _CEILING_S elapses.  If run()
    exits early (startup failure), re-raises its exception immediately so
    the test sees the real traceback rather than a timeout.

    Teardown:
      - cancels the run() task and awaits it (suppressing CancelledError)
      - cancels any background stragglers in _BACKGROUND_TASKS
        (monitor loops, schedule ticker, source-refresh heartbeat)
      - clears the status board (belt-and-suspenders; run()'s own finally
        block also calls clear_active_board via _teardown_status_board)
    """
    frames: list[tuple[int, str]] = []
    _original_swap = HeadlessBackend.swap

    def _recording_swap(
        self: HeadlessBackend, canvas: HeadlessCanvas
    ) -> HeadlessCanvas:
        frames.append((canvas.count_nonzero(), _canvas_content_hash(canvas)))
        return _original_swap(self, canvas)

    monkeypatch.setattr(HeadlessBackend, "swap", _recording_swap)

    def _poll_done() -> bool:
        """True once both the liveness gate and the content/motion gate are met.

        Liveness: ≥_MIN_FRAMES total frames swapped.
        Content+motion: ≥_MIN_DISTINCT distinct non-black content hashes present.
        Both must be true simultaneously so a burst of all-black frames followed
        by a single non-black frame cannot exit prematurely.
        """
        if len(frames) < _MIN_FRAMES:
            return False
        distinct = {h for nz, h in frames if nz > 0}
        return len(distinct) >= _MIN_DISTINCT

    task = asyncio.create_task(run(config_path))
    deadline = time.monotonic() + _CEILING_S
    try:
        while not _poll_done() and time.monotonic() < deadline:
            if task.done():
                # run() exited unexpectedly — surface its exception immediately
                # rather than letting the test time out with a confusing failure.
                task.result()  # re-raises if run() died; returns None on clean exit
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        # Cancel background tasks spawned via spawn_tracked (monitor loops,
        # schedule ticker, source-refresh heartbeat).  Snapshot before
        # iterating: done-callbacks mutate the set as tasks complete.
        stragglers = list(_BACKGROUND_TASKS)
        for t in stragglers:
            t.cancel()
        if stragglers:
            await asyncio.gather(*stragglers, return_exceptions=True)
        # Belt-and-suspenders: run()'s own finally also calls clear_active_board,
        # but a test may cancel run() before that path runs.
        sb.clear_active_board()

    return frames


def _assert_render(frames: list[tuple[int, str]], *, label: str) -> None:
    """Three render-quality assertions: liveness, content, and motion."""
    assert len(frames) >= _MIN_FRAMES, (
        f"{label}: expected ≥{_MIN_FRAMES} frames, got {len(frames)}"
    )

    non_black = [(nz, h) for nz, h in frames if nz > 0]
    assert len(non_black) >= 1, (
        f"{label}: all {len(frames)} frames were black — dark-panel class detected"
    )

    distinct_hashes = {h for _, h in non_black}
    assert len(distinct_hashes) >= _MIN_DISTINCT, (
        f"{label}: only {len(distinct_hashes)} distinct non-black hash(es) "
        f"among {len(non_black)} non-black frames — panel appears frozen"
    )


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_boot_smallsign(tmp_path: pathlib.Path, monkeypatch: Any) -> None:
    """Purpose-built smallsign (160×16, scale=1) boots and renders content.

    Two slideshow sections with cut transitions; 20 frames spans both 0.5 s
    holds so the motion assertion sees frames from two distinct sections.
    """
    cfg = tmp_path / "config.toml"
    cfg.write_text(_SMALLSIGN_CONFIG)

    frames = await _run_and_collect_frames(monkeypatch, cfg)
    _assert_render(frames, label="smallsign")

    # run() only activates a StatusBoard when [web] is configured.
    # Fixture has no [web] block → board is None.  Assert tolerantly.
    board = sb.get_active_board()
    if board is not None:
        assert board.swap_count > 0, "smallsign: status board swap_count == 0"


@pytest.mark.asyncio
async def test_boot_bigsign_shaped(tmp_path: pathlib.Path, monkeypatch: Any) -> None:
    """Purpose-built bigsign-shaped config (256×64, scale=4) boots and renders.

    Exercises the ScaledCanvas wrapper path end-to-end: all widget draws go
    through a scale=4 wrapper and must still produce non-black, varying frames.
    """
    cfg = tmp_path / "config.toml"
    cfg.write_text(_BIGSIGN_CONFIG)

    frames = await _run_and_collect_frames(monkeypatch, cfg)
    _assert_render(frames, label="bigsign-shaped")

    board = sb.get_active_board()
    if board is not None:
        assert board.swap_count > 0, "bigsign-shaped: status board swap_count == 0"


@pytest.mark.asyncio
async def test_boot_example_config(tmp_path: pathlib.Path, monkeypatch: Any) -> None:
    """config/config.example.toml (the first config new users copy) must boot.

    This is the example-rot guard: if any widget in the starter config becomes
    unbootable in CI, this test catches it.  The test injects
    ``backend = "headless"`` into ``[display]`` via text substitution and
    symlinks ``config/assets/`` into ``tmp_path`` so relative asset paths
    (e.g. ``path = "assets/phoenix.gif"``) resolve correctly.

    The example uses ``mode = "ticker"`` with ``title_delay = 5`` for its first
    section, so the title starts 160 px off the right edge and takes ≈46 engine
    ticks (≈2.3 s) before the first pixel enters the visible canvas.  The
    two-gate poll (≥20 total frames AND ≥2 distinct non-black hashes) handles
    this transparently: the liveness gate clears quickly; the content+motion gate
    clears once two distinct non-black frames appear (≈frame 47).
    """
    source = (_CONFIG_DIR / "config.example.toml").read_text()

    # Inject or replace backend = "headless" inside [display].
    # Robust to the example ever gaining its own backend line.
    source, n = re.subn(r"(?m)^backend\s*=.*$", 'backend = "headless"', source)
    if not n:
        source = source.replace("[display]\n", '[display]\nbackend = "headless"\n', 1)

    # Suppress the mtime watcher on the static tmp file (inert but cleaner).
    source, n = re.subn(r"(?m)^#?\s*hot_reload\s*=.*$", "hot_reload = false", source)
    if not n:
        source = source.replace("[display]\n", "[display]\nhot_reload = false\n", 1)

    cfg = tmp_path / "config.toml"
    cfg.write_text(source)

    # Symlink config/assets/ so relative asset paths resolve from tmp_path.
    (tmp_path / "assets").symlink_to(_CONFIG_DIR / "assets")

    frames = await _run_and_collect_frames(monkeypatch, cfg)
    _assert_render(frames, label="config.example.toml")

    board = sb.get_active_board()
    if board is not None:
        assert board.swap_count > 0, "example: status board swap_count == 0"
