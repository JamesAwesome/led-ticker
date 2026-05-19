"""Pure coercion helpers for config load.

Each helper returns `(coerced_value, warning_or_None)`. The caller
decides whether to surface the warning via `led-ticker validate`
output, runtime `logging.warning`, or both.

Bool is rejected explicitly in `coerce_int` / `coerce_float` because
bool is a subclass of `int` in Python. Silently coercing `true → 1`
would reopen the hole that the existing `bottom_text_loops` and
`font_threshold` validators close.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoercionWarning:
    field: str
    original: object
    coerced: object
    message: str


def coerce_int(value: object, *, field: str) -> tuple[int, CoercionWarning | None]:
    """Coerce string-of-digits → int. Raise ValueError otherwise.

    Rejects: bool, float, non-numeric strings, None.
    """
    if isinstance(value, bool):
        raise ValueError(
            f"{field} must be an int; got bool ({value!r}). "
            f"TOML has native true/false — if you meant a number, drop the "
            f"true/false and write 0 or 1 explicitly."
        )
    if isinstance(value, int):
        return value, None
    if isinstance(value, str):
        try:
            coerced = int(value)
        except ValueError:
            raise ValueError(
                f"{field} must be an int; got str ({value!r}). "
                f"Drop the quotes around the number (e.g. {field} = 25 "
                f'instead of {field} = "25").'
            ) from None
        return coerced, CoercionWarning(
            field=field,
            original=value,
            coerced=coerced,
            message=(
                f'{field} was a string ("{value}"); coerced to int {coerced}. '
                f"Drop the quotes around the number to silence this warning."
            ),
        )
    raise ValueError(f"{field} must be an int; got {type(value).__name__} ({value!r}).")
