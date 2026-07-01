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
import re
import socket
import time
from collections import deque
from pathlib import Path
from typing import Any

import attrs

from led_ticker._build import build_ref

logger = logging.getLogger(__name__)

# SCHEMA_VERSION guards the TOP-LEVEL key set (see the tripwire in
# tests/test_status_board.py). Additive fields nested inside existing
# entries (e.g. plugins[].names, added in v1.1) are version-compatible:
# readers must tolerate their absence.
SCHEMA_VERSION = 9
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
    disabled_widgets: list[dict[str, str]] = attrs.field(factory=list)
    plugin_reconcile: list[dict[str, str]] = attrs.field(factory=list)
    last_reload: dict[str, Any] = attrs.field(factory=dict)
    config_validation: dict[str, Any] = attrs.field(factory=dict)
    section: dict[str, Any] = attrs.field(factory=dict)
    widget: dict[str, Any] = attrs.field(factory=dict)
    monitor_updates: dict[str, float] = attrs.field(factory=dict)
    # name -> {kind, interval, last_ok, error}. Registered on poll-loop entry,
    # updated on success, error-recorded on failure; cleared on reload.
    monitors: dict[str, dict] = attrs.field(factory=dict)
    # Incremented by LedFrame.swap() via record_swap(); serialized by the
    # heartbeat. A counter that stops advancing while the file stays fresh
    # is how the page distinguishes a wedged render loop from a healthy
    # one — the heartbeat alone only proves the PROCESS is alive.
    swap_count: int = attrs.field(default=0, init=False)
    # Overlay roster (static, set once at startup via set_overlay_roster) and
    # busy-light state (dynamic, refreshed each heartbeat beat via record_busy).
    # Both are pure-setter targets — no publish here; the heartbeat's existing
    # per-beat publish serializes them for free.
    overlay_roster: list[dict[str, Any]] = attrs.field(factory=list)
    busy: dict[str, Any] = attrs.field(factory=lambda: {"enabled": False})
    log_tail: deque = attrs.field(factory=lambda: deque(maxlen=LOG_TAIL_MAX))
    disabled: bool = attrs.field(default=False, init=False)
    _last_publish: float = attrs.field(default=0.0, init=False)
    _flush_scheduled: bool = attrs.field(default=False, init=False)
    _dirty: bool = attrs.field(default=False, init=False)

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "build": build_ref(),
            "published_at": time.time(),
            "min_interval": self.min_interval,
            "started_at": self.started_at,
            "hostname": self.hostname,
            "config_path": self.config_path,
            "geometry": self.geometry,
            "plugins": self.plugins,
            "failed_plugins": self.failed_plugins,
            "disabled_widgets": self.disabled_widgets,
            "plugin_reconcile": self.plugin_reconcile,
            "last_reload": self.last_reload,
            "config_validation": self.config_validation,
            "section": self.section,
            "widget": self.widget,
            "monitors": [
                {"name": name, **entry} for name, entry in self.monitors.items()
            ],
            "swap_count": self.swap_count,
            "overlays": {"roster": self.overlay_roster, "busy": self.busy},
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


def _monitor_name(obj: Any) -> str:
    """Stable monitor key: a source's .id, else a widget's .name, else classname.
    (Fixes the collision where two polled sources both keyed as their classname.)"""
    return getattr(obj, "id", None) or getattr(obj, "name", None) or type(obj).__name__


def register_monitor(name: str, kind: str, interval: float) -> str:
    """Add/refresh a monitor roster entry (preserving last_ok/error on re-register).
    On a name collision append #N so each monitor gets a distinct row. Returns
    the final (possibly suffixed) name. Never raises."""
    if _ACTIVE is None:
        return name
    try:
        m = _ACTIVE.monitors
        if name in m:
            # same key already taken -> suffix
            n, final = 2, f"{name}#2"
            while final in m:
                n += 1
                final = f"{name}#{n}"
            name = final
        entry = m.get(name) or {
            "kind": kind,
            "interval": interval,
            "last_ok": None,
            "error": None,
        }
        entry["kind"], entry["interval"] = kind, interval
        m[name] = entry
        _ACTIVE.publish()
    except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
        pass
    return name


def record_monitor_error(
    name: str, message: str, consecutive: int, retry_in: float
) -> None:
    """Record a failed poll for the named monitor.

    Instrumentation only — never raises."""
    if _ACTIVE is None:
        return
    try:
        entry = _ACTIVE.monitors.setdefault(
            name, {"kind": "widget", "interval": 0.0, "last_ok": None, "error": None}
        )
        entry["error"] = {
            "message": message,
            "consecutive": consecutive,
            "at": time.time(),
            "retry_in": retry_in,
        }
        _ACTIVE.publish()
    except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
        pass


def clear_monitors() -> None:
    """Empty the monitors roster (called on config reload).

    Instrumentation only — never raises."""
    if _ACTIVE is None:
        return
    try:
        _ACTIVE.monitors.clear()
        _ACTIVE.publish()
    except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
        pass


def record_monitor_update(name: str) -> None:
    if _ACTIVE is not None:
        try:
            now = time.time()
            _ACTIVE.monitor_updates[name] = now
            entry = _ACTIVE.monitors.get(name)
            if entry is not None:
                entry["last_ok"] = now
                entry["error"] = None
            _ACTIVE.publish()
        except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
            pass


def record_widget_visit(widget: Any) -> None:
    if _ACTIVE is None:
        return
    try:
        _ACTIVE.widget = _widget_summary(widget)
    except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
        return
    _ACTIVE.publish()


def record_disabled_widget(widget: Any, error: str) -> None:
    """Record a widget disabled by the render circuit breaker. Instrumentation
    only — must never raise into the engine."""
    if _ACTIVE is None:
        return
    try:
        entry = {**_widget_summary(widget), "error": error}
        if entry not in _ACTIVE.disabled_widgets:
            _ACTIVE.disabled_widgets.append(entry)
            _ACTIVE.publish()
    except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
        return


def record_plugin_reconcile(actions: list[Any]) -> None:
    """Record the outcome of a plugin reconcile pass. Instrumentation only —
    must never raise into the engine."""
    if _ACTIVE is None:
        return
    try:
        for action in actions:
            _ACTIVE.plugin_reconcile.append(
                {
                    "namespace": action.namespace,
                    "action": action.action,
                    "detail": action.detail,
                }
            )
        _ACTIVE.publish()
    except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
        return


def record_reload(
    *,
    ok: bool,
    ts: str,
    error: str = "",
    restart_required: list[str] | None = None,
) -> None:
    """Record the outcome of a config-reload attempt. Instrumentation only —
    never raises into the engine."""
    if _ACTIVE is None:
        return
    try:
        _ACTIVE.last_reload = {
            "ok": ok,
            "at": ts,
            "error": error,
            "restart_required": list(restart_required or []),
        }
        _ACTIVE.publish(force=True)
    except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
        return


def record_config_validation(
    *,
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    ts: str,
) -> None:
    """Record the startup config-validation outcome (this boot's config health).
    Instrumentation only — a no-op with no active board, and never raises into the
    engine. Set once at boot; reloads use `last_reload`, not this field."""
    if _ACTIVE is None:
        return
    try:
        _ACTIVE.config_validation = {"at": ts, "errors": errors, "warnings": warnings}
        _ACTIVE.publish(force=True)
    except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
        return


def clear_disabled_widgets() -> None:
    """Empty the disabled-widgets list (called on a successful reload, alongside
    RenderBreaker.reset). Instrumentation only — never raises into the engine."""
    if _ACTIVE is None:
        return
    try:
        _ACTIVE.disabled_widgets.clear()
        _ACTIVE.publish(force=True)
    except Exception:  # noqa: BLE001
        return


def record_swap() -> None:
    """Count a hardware swap. Called from LedFrame.swap() at frame cadence
    (~20-60 Hz), so this is increment-only — NO publish, no I/O; the
    heartbeat serializes the current value every couple of seconds. Must
    never raise (it sits on the render path)."""
    if _ACTIVE is not None:
        _ACTIVE.swap_count += 1


def set_overlay_roster(roster: list[dict[str, Any]]) -> None:
    """Set the static overlay roster once at startup. Pure setter (no
    publish) — the heartbeat's per-beat publish serializes it."""
    if _ACTIVE is not None:
        _ACTIVE.overlay_roster = roster


def record_busy(state: dict[str, Any]) -> None:
    """Store the current busy-light state. Pure setter (no publish) — like
    record_swap, NOT record_section; the heartbeat publishes right after."""
    if _ACTIVE is not None:
        _ACTIVE.busy = state


def record_section(
    *, index: int, total: int, mode: str, title: str, widget_count: int
) -> None:
    if _ACTIVE is not None:
        _ACTIVE.section = {
            "index": index,
            "total": total,
            "mode": mode,
            "title": _clean_text(title),
            "widget_count": widget_count,
        }
        _ACTIVE.publish(force=True)  # section change publishes immediately


# Inline pixel-emoji markup (":baseball.ball:") renders as sprites on the
# panel but is noise on the web status page.
_EMOJI_SLUG = re.compile(r":[A-Za-z0-9_.+-]+:")


def _clean_text(value: str) -> str:
    """Strip :emoji.slug: tags and collapse the leftover whitespace."""
    return " ".join(_EMOJI_SLUG.sub(" ", value).split())


def _widget_summary(widget: Any) -> dict[str, str]:
    text = getattr(widget, "text", None) or getattr(widget, "top_text", None)
    if not text:
        # SegmentMessage-style widgets carry (text, color) segment tuples
        # instead of a flat .text — join the text halves.
        segments = getattr(widget, "segments", None)
        if segments:
            try:
                text = " ".join(str(s[0]) for s in segments if s and s[0])
            except TypeError, IndexError:
                text = None
    path = getattr(widget, "path", None)
    if text:
        summary = _clean_text(str(text))[:80]
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
