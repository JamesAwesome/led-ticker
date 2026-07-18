"""Unit tests for the shared three-branch `draw_text_run` helper.

Covers all three draw branches (emoji / per-char / whole-string) with and
without a per-char color override, asserting on the `_StubCanvas` pixel map
exactly as `test_message.py`'s colored-token suite does. These are the
behavioral teeth for the message extraction (Task 2) and the shared
foundation two_row / image adopt in Phase 2.
"""

from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widgets._text_run import draw_text_run


def _stub(width=160, height=16):
    from rgbmatrix import _StubCanvas

    return _StubCanvas(width=width, height=height)


def _const(rgb):
    from rgbmatrix.graphics import Color

    from led_ticker.color_providers import _ConstantColor

    return _ConstantColor(Color(*rgb))


def _lit(canvas):
    return {xy: v for xy, v in canvas._pixels.items() if v != (0, 0, 0)}


# --------------------------------------------------------------------------
# Branch 3: whole-string / constant host
# --------------------------------------------------------------------------


def test_constant_no_override_all_host_color():
    """Constant provider, no override -> plain draw_text; every lit pixel is
    the host color."""
    host = (0, 200, 0)
    c = _stub()
    adv = draw_text_run(
        c,
        FONT_DEFAULT,
        0,
        12,
        _const(host),
        "AB99",
        0,
        override=None,
        has_emoji=False,
    )
    lit = _lit(c)
    assert lit, "text must render some pixels"
    got = set(lit.values())
    assert got == {host}, f"expected only host color; got {got!r}"
    assert adv > 0


def test_constant_with_override_forces_per_char():
    """Constant host + override on the trailing chars: literal chars stay host,
    the override chars take the token color, and the token pixels are strictly
    RIGHT of the literal pixels (index alignment on the forced per-char path)."""
    host = (0, 200, 0)
    tok = (200, 0, 0)
    from rgbmatrix.graphics import Color

    override = [None, None, Color(*tok), Color(*tok)]  # colors "99" in "AB99"
    c = _stub()
    draw_text_run(
        c,
        FONT_DEFAULT,
        0,
        12,
        _const(host),
        "AB99",
        0,
        override=override,
        has_emoji=False,
    )
    lit = _lit(c)
    colors = set(lit.values())
    assert host in colors, "literal 'AB' should be host color"
    assert tok in colors, "override chars '99' should be token color"
    assert colors <= {host, tok}, f"only host+token expected; got {colors!r}"
    host_xs = [x for (x, _y), v in lit.items() if v == host]
    tok_xs = [x for (x, _y), v in lit.items() if v == tok]
    assert max(host_xs) < min(tok_xs), (
        f"literal must be left of override chars; host max={max(host_xs)} "
        f"tok min={min(tok_xs)}"
    )


def test_constant_with_override_equals_no_override_when_all_none():
    """An all-None override renders byte-identically to no override at all
    (the forced-per-char path with only host colors == the plain draw_text
    path). Guards that the forced path doesn't shift geometry."""
    host = (0, 200, 0)
    c_none = _stub()
    draw_text_run(
        c_none,
        FONT_DEFAULT,
        0,
        12,
        _const(host),
        "AB99",
        0,
        override=None,
        has_emoji=False,
    )
    c_allnone = _stub()
    draw_text_run(
        c_allnone,
        FONT_DEFAULT,
        0,
        12,
        _const(host),
        "AB99",
        0,
        override=[None, None, None, None],
        has_emoji=False,
    )
    assert c_none._pixels == c_allnone._pixels


# --------------------------------------------------------------------------
# Branch 2: per-char provider (rainbow / gradient)
# --------------------------------------------------------------------------


def test_per_char_no_override_varied_hues():
    """A per-char provider (rainbow) with no override renders varied hues."""
    from led_ticker.color_providers import Rainbow

    c = _stub()
    draw_text_run(
        c,
        FONT_DEFAULT,
        0,
        12,
        Rainbow(),
        "ABCDEF",
        0,
        override=None,
        has_emoji=False,
    )
    hues = set(_lit(c).values())
    assert len(hues) >= 2, f"rainbow should produce varied hues; got {hues!r}"


def test_per_char_with_override_wins_per_char():
    """Per-char host (rainbow) + override: override chars are ALL the token
    color, literal chars carry varied rainbow hues -> override wins per-char."""
    from rgbmatrix.graphics import Color

    from led_ticker.color_providers import Rainbow

    tok = (200, 0, 0)
    override = [None, None, None, Color(*tok), Color(*tok)]  # "99" in "ABC99"
    c = _stub()
    draw_text_run(
        c,
        FONT_DEFAULT,
        0,
        12,
        Rainbow(),
        "ABC99",
        0,
        override=override,
        has_emoji=False,
    )
    lit = _lit(c)
    tok_present = [xy for xy, v in lit.items() if v == tok]
    assert tok_present, "override chars should render the token color under rainbow"
    non_tok = {v for v in lit.values() if v != tok}
    assert len(non_tok) >= 2, f"literal chars should carry varied hues; got {non_tok!r}"
    assert tok not in non_tok, "rainbow must not coincidentally match the token red"


# --------------------------------------------------------------------------
# Branch 1: emoji present
# --------------------------------------------------------------------------


def test_emoji_no_override_matches_draw_with_emoji():
    """has_emoji + no override is byte-identical (pixels AND advance) to a
    direct draw_with_emoji call — the emoji branch is a pure pass-through."""
    from led_ticker.pixel_emoji import count_text_chars, draw_with_emoji

    host = _const((0, 200, 0))
    text = ":sun: 9"

    c_helper = _stub()
    adv_helper = draw_text_run(
        c_helper,
        FONT_DEFAULT,
        0,
        12,
        host,
        text,
        0,
        override=None,
        has_emoji=True,
    )

    c_direct = _stub()
    adv_direct = draw_with_emoji(
        c_direct,
        FONT_DEFAULT,
        0,
        12,
        host,
        text,
        y_offset=0,
        frame=0,
        total_chars=count_text_chars(text),
        color_override=None,
    )

    assert c_helper._pixels == c_direct._pixels
    assert adv_helper == adv_direct


def test_emoji_with_override_colors_token_leaves_sprite_intact():
    """INDEX-ALIGNMENT: ':sun: 99' with an override coloring the trailing '9'.
    The `:sun:` sprite pixels are byte-identical to the colorless render (the
    override indexes the emoji-EXCLUDING char space) and the colored char
    differs (green -> red)."""
    from rgbmatrix.graphics import Color

    text = ":sun: 99"
    host = _const((0, 200, 0))
    tok = (200, 0, 0)

    # emoji-excluding char space of ":sun: 99" is " 99" (indices 0,1,2);
    # color the LAST '9' (index 2).
    override = [None, None, Color(*tok)]

    c_plain = _stub()
    draw_text_run(
        c_plain,
        FONT_DEFAULT,
        0,
        12,
        host,
        text,
        0,
        override=None,
        has_emoji=True,
    )

    c_over = _stub()
    draw_text_run(
        c_over,
        FONT_DEFAULT,
        0,
        12,
        host,
        text,
        0,
        override=override,
        has_emoji=True,
    )

    diff = {
        xy
        for xy in set(c_plain._pixels) | set(c_over._pixels)
        if c_plain._pixels.get(xy, (0, 0, 0)) != c_over._pixels.get(xy, (0, 0, 0))
    }
    assert diff, "the override must change some pixels (green->red)"
    changed_colors = {c_over._pixels.get(xy, (0, 0, 0)) for xy in diff}
    # every changed pixel is the token red (or turned-off); no other new color.
    assert changed_colors <= {tok, (0, 0, 0)}, (
        f"only the token color should appear in changed pixels; got {changed_colors!r}"
    )
    # the token red must actually appear in the override render.
    assert tok in set(c_over._pixels.values()), "token color must render"


def test_emoji_override_out_of_range_index_defers_to_provider():
    """The emoji override callable returns None for indices past the override
    length (defer to provider) rather than raising — matches message's
    `_ov[i] if i < len(_ov) else None`."""
    from rgbmatrix.graphics import Color

    host = _const((0, 200, 0))
    # override shorter than the text-char count: only index 0 colored.
    override = [Color(200, 0, 0)]
    c = _stub()
    # must not raise
    adv = draw_text_run(
        c,
        FONT_DEFAULT,
        0,
        12,
        host,
        ":sun: 99",
        0,
        override=override,
        has_emoji=True,
    )
    assert adv > 0


# --------------------------------------------------------------------------
# total_chars threading
# --------------------------------------------------------------------------


def test_explicit_total_chars_threaded_not_recomputed():
    """When total_chars is passed explicitly the helper uses it (does not
    recompute from visible_text) — this is what lets message anchor a
    typewriter slice's per-char hue to the FULL text length. A gradient
    provider is per-char and color depends on `total`, so a different total
    yields different pixels."""
    from rgbmatrix.graphics import Color

    from led_ticker.color_providers import Gradient

    prov = Gradient(from_color=Color(255, 0, 0), to_color=Color(0, 0, 255))
    # Draw the same 3-char slice with total_chars=3 vs total_chars=12.
    c3 = _stub()
    draw_text_run(
        c3,
        FONT_DEFAULT,
        0,
        12,
        prov,
        "ABC",
        0,
        override=None,
        has_emoji=False,
        total_chars=3,
    )
    c12 = _stub()
    draw_text_run(
        c12,
        FONT_DEFAULT,
        0,
        12,
        prov,
        "ABC",
        0,
        override=None,
        has_emoji=False,
        total_chars=12,
    )
    assert c3._pixels != c12._pixels, (
        "per-char color depends on the explicit total_chars anchor"
    )


# --------------------------------------------------------------------------
# hires_downscale pass-through (added for the Phase-2 helper consolidation)
# --------------------------------------------------------------------------


def test_hires_downscale_forwarded_to_draw_with_emoji(monkeypatch):
    """The emoji branch forwards `hires_downscale` to draw_with_emoji so the
    image single-row / message fisheye-lens paths can route through the shared
    helper instead of hand-duplicating the three branches."""
    import led_ticker.widgets._text_run as tr

    captured = {}

    def _spy(*a, **kw):
        captured.update(kw)
        return 0

    monkeypatch.setattr(tr, "draw_with_emoji", _spy)
    draw_text_run(
        _stub(),
        FONT_DEFAULT,
        0,
        12,
        _const((255, 255, 255)),
        ":sun: 9",
        0,
        has_emoji=True,
        hires_downscale=0.5,
    )
    assert captured.get("hires_downscale") == 0.5


def test_hires_downscale_ignored_by_plain_branch():
    """A plain (no-emoji, constant) run still renders when hires_downscale is
    passed — the plain branches don't take it and must not choke."""
    c = _stub()
    adv = draw_text_run(
        c,
        FONT_DEFAULT,
        0,
        12,
        _const((0, 200, 0)),
        "AB",
        0,
        has_emoji=False,
        hires_downscale=0.5,
    )
    assert adv > 0
    assert _lit(c)  # something drew
