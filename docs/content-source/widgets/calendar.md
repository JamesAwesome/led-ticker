# Calendar Widget Options

Fetches upcoming events from any subscribed iCal (`.ics`) feed and displays them as a rotating agenda or a live next-event countdown. Always a Container: a background task polls the feed and populates `feed_stories`; the display loop re-reads the list on every pass, so updates appear within one cycle without restarting.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `ics_url` | string | required | Public `.ics` URL to subscribe to (e.g. Google Calendar "Secret address in iCal format"), or a `file://` path for a local file (e.g. `"file:///home/pi/cal.ics"`). |
| `layout` | `"agenda"` \| `"next"` | `"agenda"` | `"agenda"` shows one scrolling line per upcoming event; `"next"` shows a single live countdown to the soonest event (`"Standup in 25m"`). |
| `max_events` | int | `5` | Maximum number of upcoming events to display in agenda mode. |
| `lookahead_days` | int | `7` | Days ahead to scan for events. Recurrence rules are expanded within this window. |
| `time_format` | `"12h"` \| `"24h"` | `"12h"` | Format for the event time in agenda lines. `"12h"` renders `3:00 PM`; `"24h"` renders `15:00`. |
| `timezone` | IANA name \| none | system local | Display timezone override, e.g. `"America/New_York"`. Uses stdlib `zoneinfo`. Defaults to the system local timezone. |
| `empty_text` | string | `"No upcoming events"` | Text shown when no events are found in the lookahead window. |
| `filter` | list of strings | `[]` (all events) | Keep only events whose summary contains any of these keywords (case-insensitive). An empty list shows all events. |
| `highlight` | list of strings | `[]` (none) | Matching events are colored with `highlight_color` and guaranteed to appear even if they would otherwise be dropped by `max_events` capping. |
| `highlight_color` | RGB list / string / table | amber `[255, 200, 60]` | Color applied to highlighted events. Constant `[r,g,b]`, `"rainbow"`, `"color_cycle"`, `"random"`, or `{style="gradient", from=[...], to=[...]}`. |
| `font` | string | `"6x12"` | BDF font name (e.g. `"5x8"`, `"6x12"`) or hires font (e.g. `"Inter-Bold"`). |
| `font_color` | RGB list / string / table | `[255, 255, 255]` | Color for non-highlighted events. Constant `[r,g,b]`, `"rainbow"`, `"color_cycle"`, `"random"`, or `{style="gradient", from=[...], to=[...]}`. |
| `bg_color` | RGB list | none | Background fill color. Painted across the full panel before text. |
| `border` | `"rainbow"` \| `"color_cycle"` \| `"lightbulbs"` \| `[r,g,b]` \| `{style="...", ...}` | none | Perimeter border ring — five styles (rainbow chase, color cycle, constant, bands, lightbulbs); see [/concepts/borders/](/concepts/borders/). |
| `padding` | int | `6` | Horizontal padding (logical pixels) added to each event line when scrolling. |
| `update_interval` | int | `900` | Seconds between feed fetches. Default is 15 minutes. |
