"""Clock widget: current time as a held/centered text display.

format_clock is a pure, timezone-agnostic formatter (it formats an
already-localized datetime). Presets are built from datetime fields rather
than via %- strftime codes, which are a libc passthrough Python does not
guarantee — building from fields keeps preset output deterministic across
platforms. A custom format string (containing %) is passed to strftime
verbatim.
"""

from datetime import datetime


def format_clock(now: datetime, fmt: str) -> str:
    """Format `now` per `fmt`: a preset ("12h"/"24h") or a strftime template.

    A value containing "%" is treated as a strftime template. Otherwise it
    must be a known preset keyword; an unknown preset raises ValueError.
    """
    if "%" in fmt:
        return now.strftime(fmt)
    if fmt == "12h":
        hour12 = now.hour % 12 or 12
        meridiem = "AM" if now.hour < 12 else "PM"
        return f"{hour12}:{now.minute:02d} {meridiem}"
    if fmt == "24h":
        return f"{now.hour:02d}:{now.minute:02d}"
    raise ValueError(
        f"clock format {fmt!r} is not a known preset (expected '12h' or '24h') "
        "and is not a strftime template (no '%'). "
        "Use '12h', '24h', or a strftime string like '%H:%M'."
    )
