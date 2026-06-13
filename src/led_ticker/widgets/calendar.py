"""Calendar widget: upcoming events from a subscribed iCal (.ics) feed.

Always a Container (like rss_feed): a shared data core fetches + parses the
feed, then update() populates feed_stories per the `layout` knob — `agenda`
builds one TickerMessage per event; `next` builds one live countdown widget.
"""

from typing import Any

import aiohttp
import attrs

from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widget import Widget
from led_ticker.widgets import register
from led_ticker.widgets.message import TickerMessage


@register("calendar")
@attrs.define
class Calendar:
    """Container that shows upcoming .ics events as an agenda or next-event line."""

    session: aiohttp.ClientSession
    ics_url: str
    layout: str = "agenda"
    max_events: int = 5
    lookahead_days: int = 7
    time_format: str = "12h"
    timezone: str | None = None
    empty_text: str = "No upcoming events"
    filter: list[str] = attrs.field(factory=list)
    highlight: list[str] = attrs.field(factory=list)
    padding: int = 6
    font: Any = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: Any = attrs.field(default=None, kw_only=True)
    highlight_color: Any = attrs.field(default=None, kw_only=True)
    bg_color: Any = attrs.field(default=None, kw_only=True)
    border: Any | None = attrs.field(default=None, kw_only=True)
    feed_stories: list[Widget] = attrs.field(init=False, factory=list)
    feed_title: TickerMessage | None = attrs.field(init=False, default=None)
