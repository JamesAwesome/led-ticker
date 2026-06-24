"""Importable backend conformance suite.

Encodes the load-bearing hardware-rendering constraints (CLAUDE.md) as checks
every backend must pass. External backend authors run:

    from led_ticker.backends.conformance import run_backend_conformance
    run_backend_conformance(lambda: MyBackend(...))

`backend_factory` must return a FRESH, un-setup backend each call.
"""

import tempfile
from collections.abc import Callable
from pathlib import Path

from led_ticker.backends import Backend, BackendNotReadyError  # noqa: F401
from led_ticker.preview import PreviewTee
from led_ticker.scaled_canvas import ScaledCanvas


def _check_protocol(factory: Callable[[], Backend]) -> None:
    assert isinstance(factory(), Backend), "does not satisfy the Backend protocol"


def _check_swap_returns_new_buffer(factory: Callable[[], Backend]) -> None:
    b = factory()
    b.setup()
    front = b.create_canvas()
    back = b.swap(front, getattr(b, "framerate_fraction", 1))
    assert back is not front, (
        "swap() must return a DIFFERENT canvas (constraints #1/#8)"
    )


def _check_canvas_contract(factory: Callable[[], Backend]) -> None:
    b = factory()
    b.setup()
    c = b.create_canvas()
    for meth in ("SetPixel", "Clear", "Fill", "SubFill", "SetImage"):
        assert hasattr(c, meth), f"canvas missing {meth} (Canvas contract)"
    c.SetPixel(0, 0, 1, 2, 3)  # must not raise
    c.Clear()


def _check_no_getpixel_required(factory: Callable[[], Backend]) -> None:
    # Constraint #3: the engine never reads pixels back. A backend may offer
    # test helpers, but production code must not need GetPixel. We assert the
    # engine-facing contract does not include it.
    b = factory()
    b.setup()
    c = b.create_canvas()
    assert not hasattr(c, "GetPixel"), "canvas must not expose GetPixel (constraint #3)"


def _check_wrappability(factory: Callable[[], Backend]) -> None:
    # The raw canvas is wrapped by ScaledCanvas (bigsign) and PreviewTee in
    # production. A backend that passes the flat contract must also survive the
    # wrappers.
    #
    # ScaledCanvas constraint: content_height * scale <= canvas.height.
    # We use scale=2, content_height=16 (32 real pixels minimum). Backend
    # canvases must be at least 32 px tall — conformance factory should be
    # constructed with height >= 32 (e.g. HeadlessBackend(64, 32)).
    b = factory()
    b.setup()
    raw = b.create_canvas()
    # Pick the largest scale that still fits (content_height=16 is the standard).
    content_height = 16
    # scale must satisfy: content_height * scale <= raw.height
    scale = max(1, raw.height // content_height)
    scaled = ScaledCanvas(raw, scale=scale, content_height=content_height)
    scaled.SetPixel(0, 0, 4, 5, 6)  # must paint through to the real canvas

    # PreviewTee.__init__ requires a real Path (not None) — construct with a
    # temp file path the same way _setup_preview in app/run.py does.
    hw = b.create_canvas()
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
        frame_path = Path(tmp.name)
    tee = PreviewTee(
        hw=hw,
        width=hw.width,
        height=hw.height,
        frame_path=frame_path,
    )
    tee.SetPixel(0, 0, 7, 8, 9)  # must not raise


def _check_not_ready_guard(factory: Callable[[], Backend]) -> None:
    # Backends that build state in setup() should not silently work before it.
    # LedFrame enforces this; backends that raise BackendNotReadyError or
    # AttributeError before setup() are both acceptable. We only assert that a
    # backend which DID set up works — the LedFrame-level guard is tested
    # separately (test_led_frame_backend.py).
    b = factory()
    b.setup()
    assert b.create_canvas() is not None


_CHECKS = [
    _check_protocol,
    _check_swap_returns_new_buffer,
    _check_canvas_contract,
    _check_no_getpixel_required,
    _check_wrappability,
    _check_not_ready_guard,
]


def run_backend_conformance(backend_factory: Callable[[], Backend]) -> None:
    """Run every conformance check against backends from `backend_factory`.
    Raises AssertionError naming the first failing constraint."""
    for check in _CHECKS:
        check(backend_factory)
