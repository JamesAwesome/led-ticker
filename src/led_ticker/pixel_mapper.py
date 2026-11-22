"""Leaf module: the canvas a ``pixel_mapper_config`` string produces.

Import-light by contract (no led_ticker imports) so the rgbmatrix TEST STUB
(``tests/stubs/rgbmatrix``), ``HeadlessBackend`` and ``validate.py`` can all
share ONE parse instead of three (#560 C2). Before this module existed the
stub and the headless backend honoured only ``U-mapper`` while validate read
``Remap:W,H``, so a real bigsign ``[display]`` block built a 512x32 software
canvas (and failed the ``content_height`` ceiling) while validate reported
the same config clean.

Two entry points, deliberately separate:

- :func:`remap_canvas_size` — the ``Remap:W,H|…`` header only, ``None``
  otherwise. This is what validate uses: its panel-size estimate never
  folded a bare ``U-mapper`` and still doesn't (changing that would move
  rule 1 for U-mapper configs; do it on purpose, with a test).
- :func:`mapped_canvas_size` — the full software-backend geometry: a
  ``Remap`` header wins, else ``U-mapper`` folds the chain in half, else
  the naive ``cols*chain x rows*parallel`` passes through.

A malformed ``Remap:`` header (``Remap:custom``) never raises — both return
the naive geometry, matching the real library's behaviour of ignoring a
mapper it can't parse rather than refusing to start.
"""

_REMAP_PREFIX = "Remap:"


def remap_canvas_size(pixel_mapper_config: str) -> tuple[int, int] | None:
    """``(width, height)`` from a ``Remap:W,H|…`` header, else ``None``.

    ``None`` for an empty string, any other mapper (``U-mapper``), or a
    header that doesn't parse as two positive ints.
    """
    if not pixel_mapper_config.startswith(_REMAP_PREFIX):
        return None
    header = pixel_mapper_config[len(_REMAP_PREFIX) :].split("|", 1)[0]
    parts = header.split(",")
    if len(parts) != 2:
        return None
    try:
        width, height = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def mapped_canvas_size(
    width: int, height: int, pixel_mapper_config: str
) -> tuple[int, int]:
    """The software canvas for ``width x height`` (``cols*chain`` x
    ``rows*parallel``) under ``pixel_mapper_config``.

    ``Remap:W,H|…`` → ``(W, H)``; ``U-mapper`` → ``(width // 2, height * 2)``
    (folds the chain in half); anything else (including a malformed
    ``Remap:``) → ``(width, height)``.
    """
    remapped = remap_canvas_size(pixel_mapper_config)
    if remapped is not None:
        return remapped
    if pixel_mapper_config == "U-mapper":
        return width // 2, height * 2
    return width, height
