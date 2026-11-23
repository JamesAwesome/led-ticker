"""`run_transition` forwards the incoming geometry and the outgoing bg colour to
`frame_at` (plugin API minor bump; fade design `2026-11-21-fade-design.md`,
"Runner"). Every core and plugin `frame_at` takes `**kwargs`, so the three new
keys are additive."""

import unittest.mock as mock

from led_ticker import plugin
from led_ticker.transitions import run_transition


class _Recorder:
    min_frames = 0

    def __init__(self):
        self.kwargs = []

    def frame_at(self, t, canvas, outgoing, incoming, **kw):
        self.kwargs.append(kw)
        return canvas


def _tall_canvas():
    """A 64-row mock so the runner's re-wrap at scale 2 / height 12 fits."""
    c = mock.MagicMock()
    c.width, c.height, c.scale = 256, 64, 1
    return c


async def test_frame_at_receives_geometry_and_outgoing_bg(
    mock_frame, make_widget, no_sleep
):
    canvas = _tall_canvas()
    mock_frame.swap.return_value = canvas
    t = _Recorder()
    await run_transition(
        canvas,
        mock_frame,
        make_widget(),
        make_widget(),
        transition=t,
        duration=0.1,
        incoming_scale=2,
        incoming_content_height=12,
        outgoing_bg_color=(1, 2, 3),
        incoming_bg_color=(4, 5, 6),
    )
    first = t.kwargs[0]
    assert first["incoming_scale"] == 2
    assert first["incoming_content_height"] == 12
    assert first["outgoing_bg_color"] == (1, 2, 3)
    assert first["incoming_bg_color"] == (4, 5, 6)
    assert first["outgoing_scroll_pos"] == 0 and first["duration_ms"] == 100


async def test_frame_at_within_section_sees_incoming_scale_none(
    canvas, mock_frame, make_widget, no_sleep
):
    t = _Recorder()
    await run_transition(
        canvas, mock_frame, make_widget(), make_widget(), transition=t, duration=0.1
    )
    first = t.kwargs[0]
    assert first["incoming_scale"] is None
    assert first["incoming_content_height"] == 16
    assert first["outgoing_bg_color"] is None and first["incoming_bg_color"] is None


async def test_bg_kwargs_are_normalised_tuples(
    canvas, mock_frame, make_widget, no_sleep
):
    """`_normalize_bg` runs before the loop; frame_at sees the runner's Fill tuple."""
    from rgbmatrix.graphics import Color

    t = _Recorder()
    await run_transition(
        canvas,
        mock_frame,
        make_widget(),
        make_widget(),
        transition=t,
        duration=0.1,
        outgoing_bg_color=Color(7, 8, 9),
    )
    assert t.kwargs[0]["outgoing_bg_color"] == (7, 8, 9)


def test_api_version_is_at_least_1_5():
    assert plugin.API_VERSION >= (1, 5)
