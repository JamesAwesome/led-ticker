"""Importable backend conformance suite.

Encodes the load-bearing hardware-rendering constraints (CLAUDE.md) as checks
every backend must pass. External backend authors run:

    from led_ticker.backends.conformance import run_backend_conformance
    run_backend_conformance(lambda: MyBackend(...))

`backend_factory` must return a FRESH, un-setup backend each call.

The suite also verifies the backend is **engine-buildable**: it derives the
class from the factory and constructs it the way the engine does
(`cls(width, height, pixel_mapper_config=…)`), so a conformant backend cannot
TypeError at frame build. RgbMatrixBackend is exempt (the engine special-cases
its construction).
"""

import contextlib
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from led_ticker.backends import Backend, BackendNotReadyError  # noqa: F401
from led_ticker.preview import PreviewTee
from led_ticker.scaled_canvas import ScaledCanvas


def _check_protocol(factory: Callable[[], Backend]) -> None:
    assert isinstance(factory(), Backend), "does not satisfy the Backend protocol"


def _check_swap_returns_new_buffer(factory: Callable[[], Backend]) -> None:
    b = factory()
    b.setup()
    front = b.create_canvas()
    back = b.swap(front)
    assert back is not front, (
        "swap() must return a DIFFERENT canvas (constraints #1/#8)"
    )


def _check_swap_return_is_reusable(factory: Callable[[], Backend]) -> None:
    # LedFrame.get_clean_canvas recycles the buffer swap() returned (the
    # process-lifetime allocation invariant). That is only sound if a
    # swap-returned canvas is a live, drawable back buffer: Clear/SetPixel
    # must not raise, and re-swapping it must keep the double-buffer
    # alternation going (each swap returns a different object than it was
    # handed).
    b = factory()
    b.setup()
    c = b.create_canvas()
    for _ in range(3):
        returned = b.swap(c)
        assert returned is not c, "swap() must not return the canvas it was handed"
        returned.Clear()  # must not raise
        returned.SetPixel(0, 0, 9, 9, 9)  # must not raise
        c = returned


def _check_canvas_contract(factory: Callable[[], Backend]) -> None:
    b = factory()
    b.setup()
    c = b.create_canvas()
    for meth in ("SetPixel", "Clear", "Fill", "SubFill", "SetImage"):
        assert hasattr(c, meth), f"canvas missing {meth} (Canvas contract)"
    # Presence-only: we assert the draw doesn't raise, not the pixel value.
    # Constraint #3 (no GetPixel) means the kit cannot assume a backend canvas
    # supports readback, so value-verification would over-constrain the contract.
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
    try:
        tee = PreviewTee(
            hw=hw,
            width=hw.width,
            height=hw.height,
            frame_path=frame_path,
        )
        tee.SetPixel(0, 0, 7, 8, 9)  # must not raise
    finally:
        frame_path.unlink(missing_ok=True)


def _check_setup_ordering(factory: Callable[[], Backend]) -> None:
    # Backends may legitimately allow create_canvas() before setup() (e.g.
    # HeadlessBackend has nothing to build); the ORDERING guarantee lives at
    # the LedFrame level (tested in test_led_frame_backend.py), not here. So a
    # pre-setup create_canvas() may either raise OR return a usable canvas.
    # What every backend MUST guarantee is that create_canvas() works AFTER
    # setup(). Attempt the pre-setup call permissively, then assert post-setup.
    b = factory()
    # Raising before setup() is an acceptable backend choice; so is returning a
    # usable canvas (HeadlessBackend does). Either way, suppress and move on —
    # the post-setup assertion below is the real contract.
    with contextlib.suppress(Exception):
        b.create_canvas()
    b.setup()
    assert b.create_canvas() is not None


def _check_brightness_contract(factory: Callable[[], Backend]) -> None:
    # Brightness is buffered before setup() and applied/live after. Set it
    # before setup(), confirm the value survives setup(); set it after, confirm
    # the getter reflects it.
    b = factory()
    b.brightness = 37
    b.setup()
    assert b.brightness == 37, "brightness set before setup() must survive setup()"
    b.brightness = 88
    assert b.brightness == 88, "brightness set after setup() must be readable"


def _check_engine_buildable(factory: Callable[[], Backend]) -> None:
    # The engine constructs a non-rgbmatrix backend via a fixed convention —
    # `backend_cls(width, height, pixel_mapper_config=…)` (app/factories.py
    # build_frame_from_config). A backend can pass every check above through a
    # caller-written factory yet TypeError at engine build if its __init__ does
    # not accept that signature (the gap the telnet review caught). Derive the
    # class from the factory's instance and construct it the way the engine does,
    # so a conformant backend is guaranteed buildable.
    from led_ticker.backends.rgbmatrix import RgbMatrixBackend  # noqa: PLC0415

    # `cls` is Any: we deliberately call its ctor with the engine convention,
    # which the Backend Protocol's typed __init__ doesn't advertise.
    cls: Any = type(factory())
    if cls is RgbMatrixBackend:
        # The engine special-cases RgbMatrixBackend construction (it does NOT use
        # the (width, height, pixel_mapper_config) convention). Mirror that
        # exemption — matching `if backend_cls is RgbMatrixBackend` in factories.py.
        return
    try:
        built = cls(64, 32, pixel_mapper_config="")
    except TypeError as e:
        raise AssertionError(
            f"{cls.__name__} is not engine-buildable: the engine constructs "
            f"non-rgbmatrix backends as `cls(width, height, pixel_mapper_config=…)` "
            f"(app/factories.py build_frame_from_config). If this is an "
            f"unexpected-keyword TypeError, give __init__ that signature, e.g. "
            f"`def __init__(self, width, height, *, pixel_mapper_config=''): ...`; "
            f"otherwise __init__ raised TypeError internally for args "
            f"(64, 32, pixel_mapper_config=''). ({e})"
        ) from e
    assert isinstance(built, Backend), (
        f"{cls.__name__}(width, height, pixel_mapper_config=…) must return a Backend"
    )
    built.setup()
    assert built.create_canvas() is not None, (
        f"{cls.__name__} built via the engine convention has a broken create_canvas()"
    )


_CHECKS = [
    _check_protocol,
    _check_swap_returns_new_buffer,
    _check_swap_return_is_reusable,
    _check_canvas_contract,
    _check_no_getpixel_required,
    _check_wrappability,
    _check_setup_ordering,
    _check_brightness_contract,
    _check_engine_buildable,
]


def run_backend_conformance(backend_factory: Callable[[], Backend]) -> None:
    """Run every conformance check against backends from `backend_factory`.
    Raises AssertionError naming the first failing constraint."""
    for check in _CHECKS:
        check(backend_factory)
