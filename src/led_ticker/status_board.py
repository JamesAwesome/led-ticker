"""Status publishing for the web UI sidecar.

The display process is the sole writer of status.json; the ``led-ticker webui``
sidecar is a pure reader. Snapshots are versioned (SCHEMA_VERSION), written
atomically (temp + os.replace), throttled to boundaries (never per-tick), and
the publisher disables itself on any failure — a status write must never
affect the panel (same rule as overlay hooks).
"""

import asyncio
import json
import logging
import os
import socket
import time
from collections import deque
from pathlib import Path
from typing import Any

import attrs

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
MIN_PUBLISH_INTERVAL = 2.0
LOG_TAIL_MAX = 50


@attrs.define
class StatusBoard:
    """Mutable status state + throttled atomic publisher."""

    path: Path = attrs.field(converter=lambda p: Path(p).expanduser())
    min_interval: float = MIN_PUBLISH_INTERVAL
    started_at: float = attrs.field(factory=time.time)
    hostname: str = attrs.field(factory=socket.gethostname)
    config_path: str = ""
    geometry: dict[str, Any] = attrs.field(factory=dict)
    plugins: list[dict[str, Any]] = attrs.field(factory=list)
    failed_plugins: list[dict[str, str]] = attrs.field(factory=list)
    section: dict[str, Any] = attrs.field(factory=dict)
    widget: dict[str, Any] = attrs.field(factory=dict)
    monitor_updates: dict[str, float] = attrs.field(factory=dict)
    log_tail: deque = attrs.field(factory=lambda: deque(maxlen=LOG_TAIL_MAX))
    disabled: bool = attrs.field(default=False, init=False)
    _last_publish: float = attrs.field(default=0.0, init=False)
    _flush_scheduled: bool = attrs.field(default=False, init=False)
    _dirty: bool = attrs.field(default=False, init=False)

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "published_at": time.time(),
            "min_interval": self.min_interval,
            "started_at": self.started_at,
            "hostname": self.hostname,
            "config_path": self.config_path,
            "geometry": self.geometry,
            "plugins": self.plugins,
            "failed_plugins": self.failed_plugins,
            "section": self.section,
            "widget": self.widget,
            "monitor_updates": self.monitor_updates,
            "log_tail": list(self.log_tail),
        }

    def publish(self, *, force: bool = False) -> None:
        """Write the snapshot if forced or outside the throttle interval.

        Gated calls mark dirty and schedule a delayed flush (when an event
        loop is running) so the last event in a burst still lands.
        """
        if self.disabled:
            return
        self._dirty = True
        now = time.monotonic()
        if force or (now - self._last_publish) >= self.min_interval:
            self._flush()
            return
        if self._flush_scheduled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # sync context (tests): stay dirty until next eligible call
        self._flush_scheduled = True
        delay = self.min_interval - (now - self._last_publish)
        loop.call_later(delay, self._scheduled_flush)

    def _scheduled_flush(self) -> None:
        self._flush_scheduled = False
        if self._dirty and not self.disabled:
            self._flush()

    def prepare_dir(self) -> None:
        """Create the status directory and open its permissions.

        Must run BEFORE the matrix is built: the rgbmatrix library drops
        privileges (root -> daemon) inside RGBMatrix(), so every publish
        after startup runs as an unprivileged user. Without 0o777 here,
        those writes fail EACCES on the root-owned directory (named-volume
        mountpoints in Docker are root:root 755). Deliberately no sticky
        bit: the first forced publish happens pre-drop as root, and the
        post-drop user must be able to os.replace over that root-owned
        file. Best-effort — an error here surfaces on the first publish
        via the normal self-disable path.
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(self.path.parent, 0o777)
        except OSError:
            logger.debug("could not prepare status dir %s", self.path.parent)

    def _flush(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            # A crash between write and replace can leave a tmp file a
            # different (post-privilege-drop) user can't open for writing;
            # unlink needs only directory write permission, so clear it.
            tmp.unlink(missing_ok=True)
            tmp.write_text(json.dumps(self.snapshot()))
            os.replace(tmp, self.path)
            self._last_publish = time.monotonic()
            self._dirty = False
        except Exception:
            # Disable BEFORE logging: StatusLogHandler feeds records back into
            # this board, so logging while enabled would recurse.
            self.disabled = True
            logger.warning(
                "status publish to %s failed; disabling status publishing "
                "for this session (panel unaffected)",
                self.path,
                exc_info=True,
            )


# --- module-level active board -------------------------------------------
# Engine call sites (run_monitor_loop, Ticker._show_one) go through these
# no-op-when-absent functions so instrumentation is one line and dead-cheap
# when [web] is not configured.

_ACTIVE: StatusBoard | None = None


def set_active_board(board: StatusBoard) -> None:
    global _ACTIVE
    _ACTIVE = board


def clear_active_board() -> None:
    global _ACTIVE
    _ACTIVE = None


def get_active_board() -> StatusBoard | None:
    return _ACTIVE


def record_monitor_update(name: str) -> None:
    if _ACTIVE is not None:
        _ACTIVE.monitor_updates[name] = time.time()
        _ACTIVE.publish()


def record_widget_visit(widget: Any) -> None:
    if _ACTIVE is None:
        return
    try:
        _ACTIVE.widget = _widget_summary(widget)
    except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
        return
    _ACTIVE.publish()


def record_section(
    *, index: int, total: int, mode: str, title: str, widget_count: int
) -> None:
    if _ACTIVE is not None:
        _ACTIVE.section = {
            "index": index,
            "total": total,
            "mode": mode,
            "title": title,
            "widget_count": widget_count,
        }
        _ACTIVE.publish(force=True)  # section change publishes immediately


def _widget_summary(widget: Any) -> dict[str, str]:
    text = getattr(widget, "text", None) or getattr(widget, "top_text", None)
    path = getattr(widget, "path", None)
    if text:
        summary = str(text)[:80]
    elif path is not None:
        summary = str(path)
    else:
        summary = ""
    return {"type": type(widget).__name__, "summary": summary}


class StatusLogHandler(logging.Handler):
    """Feeds WARNING+ records into the board's bounded log tail."""

    def __init__(self, board: StatusBoard) -> None:
        super().__init__(level=logging.WARNING)
        self.board = board

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.board.log_tail.append(
                {
                    "ts": record.created,
                    "level": record.levelname,
                    "name": record.name,
                    "message": record.getMessage(),
                }
            )
            self.board.publish()
        except Exception:  # noqa: BLE001 - a log handler must never raise
            pass
