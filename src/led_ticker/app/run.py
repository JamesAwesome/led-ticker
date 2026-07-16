"""Main application async loop.

Loads config, builds the LED frame, and iterates over playlist sections
indefinitely. Widget construction and coercion happen in factories.py;
the run loop here only orchestrates.
"""

import asyncio
import contextlib
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

import aiohttp

from led_ticker import reload as _reload
from led_ticker import status_board
from led_ticker._plugin_loader import (
    _guarded_overlay,
    _run_shutdown_hooks,
    _run_startup_hooks,
    load_plugins_for_config,
)
from led_ticker.app.factories import (
    RUN_MODES,
    _build_title,
    _build_trans_obj,
    _build_widget,
    _cache_key,
    _configure_user_font_dir,
    _resolve_buffer_msg,
    _resolve_title_delay,
    build_frame_from_config,
    build_source,
)
from led_ticker.busy_http import serve_busy
from led_ticker.config import load_config, resolve_secret_token
from led_ticker.plugin import StartupContext
from led_ticker.sources import (
    DataRegistry,
    prime_polled_sources,
    set_data_registry,
    spawn_source_refresh,
)
from led_ticker.ticker import (
    TICKER_QUEUE_MAXSIZE,
    RestartRequested,
    Ticker,
    _displayable,
    _expand_sources,
    _maybe_wrap,
    _schedule_active,
)
from led_ticker.transitions import Transition, run_transition
from led_ticker.widget import _build_sink, run_monitor_loop, spawn_tracked


def _consume_restart_marker(marker_path: Path) -> bool:
    """True if a web-UI restart was requested. Deletes the marker FIRST so the
    restarted process doesn't re-read it and exit again (loop-safety)."""
    if not marker_path.exists():
        return False
    marker_path.unlink(missing_ok=True)
    return True


async def _ttl_ticker(busy: Any, interval: float = 1.0) -> None:
    """Clear pushed busy state once its TTL expires. 1 Hz; no-op when no
    deadline is armed."""
    while True:
        await asyncio.sleep(interval)
        busy.tick_ttl()


_SCHEDULE_TICK_SECONDS = 30.0


async def _schedule_ticker(
    led_frame: Any,
    scheduler: Any,
    tz: Any,
    base: int,
    *,
    override: Any = None,
    interval: float = _SCHEDULE_TICK_SECONDS,
) -> None:
    """Set matrix.brightness from the schedule every `interval` seconds.

    Applies immediately (correct on frame 1), logs only on change, and guards
    each tick so a transient exception keeps the ticker alive. `override`, when
    given, is a `Callable[[], int | None]` whose non-None value wins over the
    schedule (forward-looking seam for a future webhook)."""
    from datetime import datetime

    last: int | None = None

    def apply() -> None:
        nonlocal last
        try:
            o = override() if override is not None else None
            level = (
                o if o is not None else scheduler.brightness_for(datetime.now(tz), base)
            )
            led_frame.brightness = level
            if level != last:
                logging.info("schedule: brightness -> %d", level)
                last = level
        except Exception:
            logging.exception("schedule: brightness compute failed; holding")

    apply()
    while True:
        await asyncio.sleep(interval)
        apply()


async def _supervised_schedule(
    led_frame: Any,
    scheduler: Any,
    tz_name: Any,
    base: int,
    *,
    override: Any = None,
) -> None:
    """Run the schedule ticker; on a fatal error, reset brightness to base and
    log (a crashed scheduler must never leave the panel stuck dark)."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # noqa: PLC0415

    tz = None
    if tz_name:
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError, ValueError, TypeError:
            logging.warning(
                "schedule: invalid timezone %r; using system local time", tz_name
            )
    try:
        await _schedule_ticker(led_frame, scheduler, tz, base, override=override)
    except asyncio.CancelledError:
        raise
    except Exception:
        logging.warning(
            "schedule ticker crashed; resetting brightness to base %d",
            base,
            exc_info=True,
        )
        try:
            led_frame.brightness = base
        except Exception:
            logging.exception("schedule: failed to reset brightness to base")


def _schedule_tz_name(display: Any) -> str:
    """Brightness-scheduler timezone: its own field wins (back-compat),
    else the sign-wide [display] timezone, else "" (system local)."""
    return display.schedule.timezone or display.timezone


async def _respawn_schedule(old_task: Any, config: Any, led_frame: Any) -> Any:
    """Cancel the running schedule ticker (if any) and start a fresh one from the
    new config. Disabled -> set brightness to the new base and return None."""
    from led_ticker.schedule import set_schedule_timezone  # noqa: PLC0415

    set_schedule_timezone(config.display.timezone)

    if old_task is not None:
        old_task.cancel()
        await asyncio.sleep(0)  # let the old ticker observe the cancel before respawn
    if config.display.schedule.enabled:
        from led_ticker.schedule import Scheduler  # noqa: PLC0415

        sched = Scheduler.from_config(config.display.schedule)
        return spawn_tracked(
            _supervised_schedule(
                led_frame,
                sched,
                _schedule_tz_name(config.display),
                config.display.brightness,
            )
        )
    led_frame.brightness = config.display.brightness
    return None


async def _build_title_guarded(
    section_title: Any,
    *,
    session: Any,
    config_dir: Any,
    default_bg_color: Any,
    panel_h_for_warning: Any,
) -> Any:
    """Build a section title, but never let a build error freeze the panel: on
    failure log + return None (skip the title this pass; a later good edit retries)."""
    try:
        return await _build_title(
            section_title,
            session=session,
            config_dir=config_dir,
            default_bg_color=default_bg_color,
            panel_h_for_warning=panel_h_for_warning,
        )
    except Exception as exc:  # noqa: BLE001 - a title build error must not freeze the panel
        logging.exception("title build failed; skipping title this pass: %s", exc)
        return None


async def _idle_on_empty_playlist(sections: list, warned: bool) -> tuple[bool, bool]:
    """Guard the render loop against a section-less playlist.

    A config with no `[[playlist.section]]` blocks (e.g. the common typo of
    `[[sections]]`, which parses to zero sections) would otherwise busy-spin the
    outer loop at 100% CPU with nothing to draw. When ``sections`` is empty this
    logs a clear warning (once per empty streak, tracked via ``warned``) and
    idles 1s — still slow enough for the loop's hot-reload check to land a valid
    config — and returns ``(idled=True, warned=True)`` so the caller `continue`s.
    With sections present it returns ``(False, False)`` (no idle, resets the
    warned flag so a later empty state warns again).

    Approved behavior change (#396): the caller now BLANKS the panel (via
    `_blank_swap`) on every idled iteration this returns, unconditionally —
    dark or not. A zero-section playlist has nothing to display, the same
    as the all-scheduled-out dark path, so it is no longer left showing a
    frozen last frame for the duration. This function only paces the
    keepalive (the 1s sleep here sets the cadence); it does not perform the
    swap itself.
    """
    if sections:
        return False, False
    if not warned:
        logging.warning(
            "playlist has no sections — nothing to display; waiting for a valid "
            "config (a hot-reload will pick one up). Check that your sections are "
            "written as [[playlist.section]] with [[playlist.section.widget]]."
        )
    await asyncio.sleep(1.0)
    return True, True


def _section_schedule_active(section: Any) -> bool:
    """Section-level `schedule = {...}` gate. No schedule = always active.
    Same contract as the widget-level check (ticker._schedule_active): an
    evaluation error KEEPS the section — scheduling must never blank the
    panel by accident."""
    sched = getattr(section, "schedule", None)
    if sched is None:
        return True
    try:
        return bool(sched.is_active())
    except Exception:  # noqa: BLE001 - visibility must not crash the run loop
        logging.exception("section schedule check failed; showing section")
        return True


def _blank_swap(led_frame: Any) -> None:
    """One keepalive blank: fetch the (recycled — see LedFrame.get_clean_canvas)
    clean canvas and swap it. Shared by the all-scheduled-out dark idle and
    the empty-playlist idle: every idle path must keep swapping, or overlay
    hooks (busy_light composites inside frame.swap()) and the status board's
    swap_count liveness counter stall for the duration. Allocation-free
    after the process's first swap; the frame remembers its own back
    buffer, so callers thread nothing."""
    canvas = led_frame.get_clean_canvas()
    canvas = led_frame.swap(canvas)  # constraint #1: capture the swap return
    del canvas  # the frame recycles it on the next fetch


async def _idle_when_all_scheduled_out(
    led_frame: Any,
    any_section_ran: bool,
    was_dark: bool,
    dark_streak: int,
) -> tuple[bool, int]:
    """When EVERY section sat outside its schedule window this cycle, blank
    the panel (a closed storefront going dark is correct behavior, not a
    freeze) and idle 1s so the outer loop's reload/restart checks stay
    responsive.

    Allocation is not this function's concern anymore: LedFrame.get_clean_canvas
    recycles the swap-returned buffer, so per-iteration fetches are
    allocation-free — the process-lifetime O(1) invariant is pinned in
    tests/test_frame.py.

    FLICKER guard — debounce: the panel only commits to the dark log/blank
    on the SECOND consecutive all-out cycle, tracked via `dark_streak`.
    Without it, a config whose only section flaps content on/off between
    polls (e.g. a Container emptying briefly on a failed poll) would blank
    the panel on every single poll even though nothing is structurally
    wrong — a visible ~1s black flicker each time. The FIRST all-out cycle
    is a no-op: no blank, no log, just a 1s sleep — the panel keeps showing
    its last frame for one extra second while we wait to see if this is a
    real closed-hours transition or a one-cycle content flap. Only the
    SECOND (and every subsequent) consecutive all-out cycle runs the actual
    dark path.

    Logs only on the dark/wake TRANSITIONS, never per iteration (nor during
    the debounce cycle). Returns `(now_dark, dark_streak)`; callers thread
    both back in on the next call.
    """
    if any_section_ran:
        if was_dark:
            logging.info("schedule: panel waking — re-checking sections")
        return False, 0
    if not was_dark and dark_streak == 0:
        # Debounce cycle: a single all-out pass doesn't commit to dark yet —
        # no fetch, no blank, no log. The panel just keeps its last frame
        # for one more second while we wait to see if this is a real
        # closed-hours transition or a one-cycle content flap.
        await asyncio.sleep(1.0)
        return False, 1
    if not was_dark:
        logging.info(
            "schedule: every section is outside its schedule window — panel dark"
        )
    _blank_swap(led_frame)
    await asyncio.sleep(1.0)
    return True, dark_streak + 1


def _on_display_dark_transition(
    was_dark: bool, now_dark: bool
) -> tuple[None, int, None] | None:
    """Reset outgoing-transition tracking on the False->True (panel just
    went dark) transition. Without this, the morning wake's entry
    transition would draw yesterday evening's `last_widget` at full
    brightness as the outgoing frame — a stale, unrelated widget flashing
    on wake. Returns the (last_widget, last_scroll_pos, last_bg_color)
    reset triple to assign when the transition just happened, else None
    (caller keeps its prior values unchanged). `last_scale` /
    `last_content_height` are wrapper geometry, not content — deliberately
    left untouched; `_entry_transition_active` already treats
    `last_widget is None` as "no entry transition" (boot behavior), so
    resetting `last_widget` alone is sufficient to suppress the stale
    outgoing frame."""
    if was_dark or not now_dark:
        return None
    return None, 0, None


def _section_has_content(
    title: Any, widgets: list[Any], breaker: Any
) -> tuple[bool, list[Any]]:
    """Whether a section pass has anything to show this cycle, plus the
    expanded widget rotation for reuse by the caller (avoids a second
    `_expand_sources` call for `first_widget`).

    A title always counts as content — it renders regardless of the widget
    rotation. Otherwise content requires at least one widget to survive
    `_expand_sources` (containers expanded to `feed_stories`; schedule /
    `should_display()` / breaker filters applied) this pass. An empty
    result means every widget is scheduled out, filtered, or tripped —
    including a Container with zero `feed_stories` (e.g. a boot-time RSS
    feed before its first successful poll). The caller must NOT mark the
    section as "ran" in that case: doing so previously left the panel on
    its last drawn frame while busy-spinning the outer loop (Fix 1,
    2026-07-15) instead of blanking + idling via
    `_idle_when_all_scheduled_out`.
    """
    if title:
        return True, []
    if not widgets:
        return False, []
    expanded = _expand_sources(widgets, breaker)
    return bool(expanded), expanded


async def _build_widget_guarded(
    widget_cfg: Any,
    *,
    session: Any,
    config_dir: Any,
    default_bg_color: Any,
    panel_h_for_warning: Any,
    coercion_collector: Any,
    widget_cache: dict,
    widget_tasks: dict,
) -> Any:
    """Build one widget (cache-aware), capturing its background tasks in a per-build
    sink so a config reload can cancel exactly those. On a build error, log + skip
    (return None) without caching, so a later good edit retries. Returns the widget
    or None."""
    key = _cache_key(widget_cfg)
    if key in widget_cache:
        return widget_cache[key]
    sink: set = set()
    token = _build_sink.set(sink)
    try:
        widget = await _build_widget(
            dict(widget_cfg),
            session,
            config_dir=config_dir,
            default_bg_color=default_bg_color,
            panel_h_for_warning=panel_h_for_warning,
            coercion_collector=coercion_collector,
        )
    except Exception as exc:  # noqa: BLE001 - a bad reloaded widget must not freeze the panel
        logging.exception("widget build failed; skipping for this pass: %s", exc)
        for t in sink:
            t.cancel()
        return None
    finally:
        _build_sink.reset(token)
    widget_cache[key] = widget
    widget_tasks[key] = sink
    return widget


def _build_trans_obj_guarded(trans_cfg: Any) -> Any:
    """Build a transition, degrading to None (= cut) plus a logged warning on
    any build error — so a config referencing an uninstalled/unknown plugin
    transition (e.g. ``arcade.nyancat_alternating`` with the plugin missing)
    can't crash the sign. Parity with `_build_widget_guarded`: a bad transition
    falls back to an instant switch and the panel keeps running.

    The unguarded `_build_trans_obj` still raises; `led-ticker validate` relies
    on that to report the bad transition at preflight (rule 39)."""
    try:
        return _build_trans_obj(trans_cfg)
    except Exception as exc:  # noqa: BLE001 - a bad transition must not freeze the panel
        logging.warning(
            "transition build failed for type %r; falling back to cut (no "
            "transition): %s",
            getattr(trans_cfg, "type", "?"),
            exc,
        )
        return None


def build_source_registry(sources: list, session: Any) -> DataRegistry:
    """Build a DataRegistry from a list of SourceConfig objects.

    Each source is built with ``build_source``; failures are logged and skipped
    so that a single bad ``[[source]]`` block cannot crash startup and go dark.
    The registry returned contains every source that succeeded; ``set_data_registry``
    is NOT called here — the caller is responsible (mirrors reload.py separation).

    Mirrors the "a bad source must not crash the loop" guard in ``reload.py``
    ``_apply_reload``, but at per-source granularity instead of atomic-or-nothing:
    at startup we want as many sources as possible; on reload the atomic swap
    protects a running display from a half-built registry.
    """
    registry = DataRegistry()
    for source_cfg in sources:
        try:
            registry.add(build_source(source_cfg, session=session))
        except Exception as exc:  # noqa: BLE001 - bad source must not crash startup
            logging.error(
                "startup: source %r (type %r) failed to build (%s: %s) — "
                "skipping; fix the [[source]] block and restart",
                getattr(source_cfg, "id", "?"),
                getattr(source_cfg, "type", "?"),
                type(exc).__name__,
                exc,
            )
    return registry


class _ReloadResult(NamedTuple):
    config: Any
    default_section_trans: Any
    schedule_task: Any
    source_refresh_task: Any


async def _detect_and_apply_reload(
    *,
    watcher: Any,
    config_path: Path,
    config: Any,
    widget_cache: dict,
    widget_tasks: dict,
    render_breaker: Any,
    schedule_task: Any,
    source_refresh_task: Any,
    led_frame: Any,
    session: Any = None,
) -> _ReloadResult | None:
    """Check the watcher; if the config changed and validates, apply it.

    Returns a _ReloadResult (new config + rebuilt section-default transition +
    new schedule task + new source-refresh task list) when a reload was applied,
    else None for: no change, transient mid-write, or a rejected (invalid) config.
    Records reload status as a side effect — moved verbatim from the old inline
    run-loop block so the detection cadence (now per-section) is the only
    behavior change. ``session`` is forwarded to ``_apply_reload`` so polled
    sources built during a hot-reload share the same aiohttp.ClientSession."""
    if not watcher.changed():
        return None
    new_config, errors, transient = await _reload.load_and_validate(config_path)
    if transient:
        return None  # file mid-write; retry next cycle, no record
    ts = datetime.now().isoformat()
    if new_config is None:
        logging.error("config reload rejected: %s", "; ".join(errors))
        status_board.record_reload(ok=False, ts=ts, error="; ".join(errors))
        return None
    schedule_task, source_refresh_task, restart_required = await _reload._apply_reload(
        new_config,
        old_config=config,
        widget_cache=widget_cache,
        widget_tasks=widget_tasks,
        render_breaker=render_breaker,
        schedule_task=schedule_task,
        respawn_schedule=lambda ot, cfg: _respawn_schedule(ot, cfg, led_frame),
        source_refresh_task=source_refresh_task,
        session=session,
    )
    default_section_trans = _build_trans_obj_guarded(new_config.between_sections)
    for w in getattr(new_config, "_coerce_warnings", []):
        logging.warning("config coerce: %s", w.message)
    if restart_required:
        logging.warning(
            "config reloaded (partial); restart required for: %s",
            ", ".join(restart_required),
        )
    else:
        logging.info("config reloaded")
    status_board.record_reload(ok=True, ts=ts, restart_required=restart_required)
    return _ReloadResult(
        config=new_config,
        default_section_trans=default_section_trans,
        schedule_task=schedule_task,
        source_refresh_task=source_refresh_task,
    )


def _serialize_issues(issues: list[Any]) -> list[dict[str, Any]]:
    """Flatten ValidationIssue objects to plain dicts for the status board (keeps
    status_board free of validate.py types)."""
    return [
        {"rule": i.rule, "location": i.location, "message": i.message, "fix": i.fix}
        for i in issues
    ]


def _log_validation_report(result: Any) -> None:
    """Log the startup config-validation result: one INFO line when clean, else a
    WARNING summary plus the full human report (reusing validate._format_human)."""
    from led_ticker.validate import _format_human  # noqa: PLC0415

    n_err = len(result.errors)
    n_warn = len(result.warnings)
    if n_err == 0 and n_warn == 0:
        logging.info("config validated — no issues")
        return
    logging.warning(
        "config validation: %d error(s), %d warning(s) — the sign will run, "
        "degrading invalid widgets/transitions; fix and restart (or run "
        "`led-ticker validate`):\n%s",
        n_err,
        n_warn,
        _format_human(result),
    )


async def _run_startup_validation(config_path: Path) -> None:
    """Validate the config once at boot: log the full report and publish it to the
    status board. Never fatal — the sign boots regardless and the build-time guards
    degrade invalid widgets/transitions."""
    from led_ticker.validate import validate_config  # noqa: PLC0415

    try:
        result = await validate_config(config_path)
    except Exception as exc:  # noqa: BLE001 - a validator bug must not stop the sign booting
        logging.warning("startup config validation skipped (validator error): %s", exc)
        return
    _log_validation_report(result)
    status_board.record_config_validation(
        errors=_serialize_issues(result.errors),
        warnings=_serialize_issues(result.warnings),
        ts=datetime.now().isoformat(),
    )


def _entry_transition_active(
    last_widget: Any, first_widget: Any, entry_trans: Any
) -> bool:
    """Whether an inter-section ENTRY transition should run. Requires a DISPLAYABLE
    outgoing widget: a cached `last_widget` that has since gone out of range (e.g. a
    countdown that crossed its date between sections) must NOT render as the
    transition's outgoing frame — that would briefly flash the negative count the
    visibility filter otherwise hides. Same reasoning applies to a `last_widget`
    whose bound `schedule = {...}` has gone inactive between sections — without
    this conjunct it would still flash as the transition's outgoing frame even
    though `_expand_sources` has already excluded it from the rotation."""
    return (
        last_widget is not None
        and _displayable(last_widget)
        and _schedule_active(last_widget)
        and first_widget is not None
        and entry_trans is not None
    )


async def _serve_busy_supervised(busy: Any, cfg: Any) -> None:
    """Run the HTTP listener for the process lifetime. A bind failure logs
    and returns — the display loop must never die because the busy port is
    taken."""
    try:
        runner = await serve_busy(
            busy,
            host=cfg.http_host,
            port=cfg.http_port,
            token=resolve_secret_token(
                "LED_TICKER_BUSY_TOKEN", cfg.token, label="busy_light.token"
            ),
        )
    except OSError as e:
        logging.error(
            "busy-light HTTP listener failed to bind %s:%d (%s); "
            "continuing without remote trigger",
            cfg.http_host,
            cfg.http_port,
            e,
        )
        return
    try:
        await asyncio.Event().wait()  # keep the runner alive
    finally:
        await runner.cleanup()


async def _start_busy_light(cfg: Any, led_frame: Any) -> Any:
    """Build the BusyLight, register its paint hook, and start the source
    (file poller or HTTP listener) plus an optional TTL ticker. Returns the
    BusyLight."""
    from led_ticker.busy_light import BusyLight

    busy = BusyLight(
        file_path=cfg.file_path,
        corner=cfg.corner,
        color=cfg.color,
        size=cfg.size,
        ttl_seconds=cfg.ttl_seconds,
    )
    led_frame.overlay_hooks.append(busy.paint)
    if cfg.source == "http":
        spawn_tracked(_serve_busy_supervised(busy, cfg))
        # Always run the ticker for the HTTP source so a per-request ?ttl=
        # (or the configured ttl_seconds default) is enforced. The file
        # source never arms a deadline, so it needs no ticker.
        spawn_tracked(_ttl_ticker(busy))
    else:
        await busy.update()  # fast initial read so the dot is correct on frame 1
        spawn_tracked(
            run_monitor_loop(
                busy, cfg.poll_interval, splay=False, register_monitor=False
            )
        )
    return busy


def _load_plugins_for_config(config_path: Path):
    """Load plugins honoring the [plugins] config block (enable/dir/disable)."""
    return load_plugins_for_config(config_path)


async def _status_heartbeat(
    board: Any,
    tee: Any = None,
    marker_ttl: float | None = None,
    busy: Any = None,
    busy_source: str = "file",
) -> None:
    """Republish at the throttle cadence so the sidecar's staleness verdict
    measures process liveness, not event frequency. Without this, a widget
    held longer than 3x min_interval flips the page to "stale" while the
    panel is happily playing. Also toggles the preview mirror from the
    watched-marker mtime (one tmpfs stat per beat, off the render path).
    Exits once the board self-disables or is deactivated (teardown), so it
    needs no explicit cancellation."""
    from led_ticker import status_board as _sb  # noqa: PLC0415
    from led_ticker.preview import MARKER_TTL  # noqa: PLC0415

    if marker_ttl is None:
        marker_ttl = MARKER_TTL
    marker = None
    if tee is not None:
        marker = tee._frame_path.parent / "preview-requested"
    try:
        while not board.disabled and _sb.get_active_board() is board:
            if busy is not None:
                try:
                    state = {
                        "enabled": True,
                        "active": busy.is_busy,
                        "source": busy_source,
                        "ttl_remaining": busy.ttl_remaining(),
                    }
                except Exception:
                    state = {
                        "enabled": True,
                        "active": getattr(busy, "is_busy", False),
                        "source": busy_source,
                    }
                    logging.warning("busy state read failed; publishing without ttl")
                _sb.record_busy(state)
            board.publish()
            # Narrow on marker (not tee): they're set together, and pyright
            # can only carry the None-check through the variable it stat()'s.
            if marker is not None:
                try:
                    fresh = (time.time() - marker.stat().st_mtime) < marker_ttl
                except OSError:
                    fresh = False
                tee.set_watched(fresh)
            await asyncio.sleep(board.min_interval)
    finally:
        # The heartbeat is the only thing that can turn the mirror OFF.
        # If it exits (board self-disabled / teardown), the mirror must not
        # stay stranded ON paying the watched tax forever.
        if tee is not None:
            tee.set_watched(False)


def _setup_preview(config: Any, led_frame: Any) -> Any:
    """Install the preview tee when [web] is configured. The tee is sized to
    the physical panel and writes frames next to status.json (the tmpfs
    volume both processes share). Returns the tee, or None."""
    if config.web is None:
        return None
    from led_ticker.preview import PreviewTee  # noqa: PLC0415

    frame_path = Path(config.web.status_path).expanduser().parent / "preview.bin"
    # Size from the CANVAS, never from config arithmetic: pixel_mapper_config
    # (e.g. the bigsign's Remap) reshapes the real canvas, and a wrong tee
    # height makes ScaledCanvas's panel-height check raise at the first wrap
    # — the panel down because of preview machinery (review-team finding).
    hw = led_frame.create_canvas()
    tee = PreviewTee(
        hw=hw,
        width=hw.width,
        height=hw.height,
        frame_path=frame_path,
    )
    led_frame.install_preview(tee)
    return tee


def _teardown_status_board(handle: tuple[Any, logging.Handler] | None) -> None:
    """Undo _setup_status_board: detach the log handler and clear the active
    board. Safe to call with None (when [web] was absent)."""
    if handle is None:
        return
    _board, handler = handle
    logging.getLogger().removeHandler(handler)
    status_board.clear_active_board()


def _setup_status_board(
    config: Any, config_path: Path, plugins: Any
) -> tuple[Any, logging.Handler] | None:
    """Build + activate the StatusBoard and its log handler when [web] is
    configured. Returns (board, handler) so run() can tear both down, or
    None when [web] is absent."""
    if config.web is None:
        return None

    from led_ticker.status_board import (  # noqa: PLC0415
        StatusBoard,
        StatusLogHandler,
        set_active_board,
    )

    board = StatusBoard(path=Path(config.web.status_path))
    board.config_path = str(config_path)
    board.geometry = {
        "rows": config.display.rows,
        "cols": config.display.cols,
        "chain_length": config.display.chain_length,
        "parallel": config.display.parallel,
        "default_scale": config.display.default_scale,
        "panel_width": config.display.cols * config.display.chain_length,
        "panel_height": config.display.rows * config.display.parallel,
    }
    board.plugins = [
        {
            "namespace": info.namespace,
            "source": info.source,
            "counts": dict(info.counts or {}),
            "names": dict(getattr(info, "names", None) or {}),
        }
        for info in plugins.loaded
    ]
    board.failed_plugins = [
        {"namespace": ns, "error": str(err)} for ns, err in plugins.failed
    ]
    set_active_board(board)
    handler = StatusLogHandler(board)
    logging.getLogger().addHandler(handler)
    # Runs pre-frame-build, i.e. while the process is still root: opens the
    # status dir so publishes keep working after the rgbmatrix library
    # drops privileges during RGBMatrix() construction.
    board.prepare_dir()
    board.publish(force=True)
    return board, handler


async def run(config_path: Path, backend_override: str | None = None) -> None:
    """Main application loop.

    Args:
        config_path: Path to the TOML configuration file.
        backend_override: Optional backend name (e.g. ``"headless"``) that
            takes precedence over the ``[display] backend`` config field.
            Passed through to :func:`build_frame_from_config`.  When *None*
            (default), the config field governs — zero behaviour change for
            all existing ``run(path)`` callers.
    """
    # Reconcile installed plugins against the manifest (requirements-plugins.txt)
    # BEFORE plugin load so reconciled packages are importable during entry-point
    # discovery. Also runs before build_frame_from_config, which drops root
    # (constraint #13) — pip install/uninstall needs root on the volume.
    # Tripwire: test_reconcile_runs_before_load_plugins_and_frame_build.
    from led_ticker import plugin_reconcile  # noqa: PLC0415

    # The reconcile body never raises (it wraps itself), but resolve_target and
    # apply_to_syspath run OUTSIDE that guard. This is the dark-panel prologue —
    # before build_frame_from_config — so a raise here freezes the panel
    # (constraint #1). Wrap the whole prologue so ANYTHING in the reconcile path
    # failing still lets the panel boot with no plugins reconciled.
    # Tripwire: test_reconcile_prologue_never_raises.
    _recon_actions: list = []
    try:
        _recon_target = plugin_reconcile.resolve_target()
        _recon_actions = plugin_reconcile.reconcile(config_path)
        # reconcile() already applies the volume site-packages to sys.path
        # internally; this belt-and-suspenders call covers the local-venv path
        # (a no-op when target.site_packages is None) and MUST follow reconcile.
        plugin_reconcile.apply_to_syspath(_recon_target)
    except Exception:  # noqa: BLE001
        logging.error("plugin reconcile prologue failed", exc_info=True)

    # Plugins must load before load_config so plugin-provided easings (and any
    # other config-load-validated surface) are visible to validation.
    plugins = _load_plugins_for_config(config_path)
    for ns, err in plugins.failed:
        logging.warning("plugin %r failed to load: %s", ns, err)

    config = await asyncio.to_thread(load_config, config_path)
    # Deferred import: _config_scan imports led_ticker.app.plugin_cmd, which pulls
    # in this package's __init__ (and back to run.py). A module-level import here
    # cycles when _config_scan is imported before led_ticker.app. Keep it local.
    from led_ticker._config_scan import plugin_dependency_warning

    _plugin_warning = plugin_dependency_warning(
        config_path,
        [info.namespace for info in plugins.loaded],
        [ns for ns, _err in plugins.failed],
    )
    if _plugin_warning:
        logging.getLogger(__name__).warning(_plugin_warning)
    # Seed the watcher immediately after load so any edit that lands between
    # load and the while-True loop is captured in the seed hash (not absorbed
    # into a stale baseline that would make the first-edit invisible).
    watcher = _reload.ConfigWatcher(config_path, enabled=config.display.hot_reload)
    # MUST stay on tmpfs (the ticker-status volume, alongside status.json): the
    # Ticker polls this marker with a `stat` at engine-tick rate (~20/s). On
    # tmpfs that's ~µs and negligible; if status_path ever moved to the SD card,
    # 20 flash stats/sec would add render-tick cost + wear — time-gate it then.
    _restart_marker: Path | None = (
        Path(config.web.status_path).expanduser().parent / "restart-requested"
        if config.web is not None
        else None
    )

    def _restart_requested() -> bool:
        """Consume-and-signal: True (and the marker deleted) iff a web-UI
        restart is pending. Shared by the outer-loop check, the per-section
        check, and the Ticker's per-tick `restart_check` so a queued restart
        is honoured within ~one engine tick rather than a full playlist cycle.
        Deletes the marker BEFORE returning True (loop-safety: the restarted
        process must not re-read it and exit again)."""
        return _restart_marker is not None and _consume_restart_marker(_restart_marker)

    # Surface any coerce warnings recorded by load_config (string-of-digits
    # int/float fields, mixed-case enum strings). Same messages that
    # `led-ticker validate` shows as rule-37 warnings; logging at startup
    # lets users who skip pre-flight still see the fixes.
    for w in config._coerce_warnings:
        logging.warning("config coerce: %s", w.message)
    _configure_user_font_dir(config_path.parent)

    # Status board setup must precede frame construction: RGBMatrix() drops
    # root privileges (default drop_privileges in the rgbmatrix library), and
    # prepare_dir needs root to open the status directory on the root-owned
    # volume mountpoint. Tripwire: test_setup_runs_before_frame_build.
    _status_handle = _setup_status_board(config, config_path, plugins)
    try:
        # Record reconcile outcome now that the board is active. Both the
        # reconcile and this record call run pre-drop (before
        # build_frame_from_config). record_plugin_reconcile is instrumentation
        # only — never raises into the engine.
        status_board.record_plugin_reconcile(_recon_actions)
        # Validate the loaded config once and surface the full report (logs +
        # status board). Never fatal: the build-time guards degrade invalid
        # widgets/transitions, so the sign boots regardless. Runs after plugins
        # load, so installed-plugin types resolve and only genuinely-unknown
        # names flag.
        await _run_startup_validation(config_path)
        led_frame = build_frame_from_config(
            config.display, backend_override=backend_override
        )
        # Privilege-drop boundary (constraint #13): the rgbmatrix backend
        # constructs RGBMatrix here, dropping root -> daemon. All pre-drop work
        # (plugin reconcile, prepare_dir, validation) has already run above;
        # everything below needs a live backend.
        led_frame.setup()
        from led_ticker.render_breaker import RenderBreaker  # noqa: PLC0415

        render_breaker = RenderBreaker()
        preview_tee = _setup_preview(config, led_frame)

        # Busy light first so the heartbeat (spawned below) can read its state.
        busy = None
        if config.busy_light.enabled:
            busy = await _start_busy_light(config.busy_light, led_frame)

        # Plugin overlays composite over every render path via LedFrame.swap(),
        # same as the busy-light. Each is exception-wrapped so a raising plugin
        # overlay disables itself (logged once) rather than freezing the panel.
        for ns, paint in plugins.overlays:
            led_frame.overlay_hooks.append(_guarded_overlay(ns, paint))

        # Publish the static overlay roster once: names come from the
        # registration sites here (a raw overlay_hooks callable has no clean
        # name). busy.enabled and the busy_light roster entry both derive from
        # the one config gate, so they can't disagree.
        if _status_handle is not None:
            from led_ticker.status_board import set_overlay_roster  # noqa: PLC0415

            roster: list[dict[str, str]] = []
            if busy is not None:
                roster.append({"name": "busy_light", "kind": "core"})
            roster.extend({"name": ns, "kind": "plugin"} for ns, _ in plugins.overlays)
            set_overlay_roster(roster)

            spawn_tracked(
                _status_heartbeat(
                    _status_handle[0],
                    tee=preview_tee,
                    busy=busy,
                    busy_source=config.busy_light.source,
                )
            )

        schedule_task: Any = await _respawn_schedule(None, config, led_frame)

        # Default inter-section transition built once at startup. Used for
        # sections that don't specify their own `transition` field — see
        # the per-section override logic below.
        default_section_trans: Transition | None = _build_trans_obj_guarded(
            config.between_sections
        )

        # Compute the panel height to use for hi-res font_size warnings.
        # Only meaningful on the small sign (default_scale == 1) — bigsign
        # users intentionally pick large sizes, no warning needed there.
        panel_h_for_warning: int | None = (
            config.display.rows if config.display.default_scale == 1 else None
        )

        # Sentinel: source_refresh_task is set inside the session block (after
        # the shared session exists so polled sources receive it). Declared here
        # so hot-reload code that references the name doesn't see an unbound
        # variable on an early-exit path.
        source_refresh_task: Any = None

        async with aiohttp.ClientSession() as session:
            # Build the data-source registry from [[source]] blocks inside the
            # session block so polled (network-backed) PolledDataSource subclasses
            # receive the shared aiohttp.ClientSession. Must run BEFORE widget
            # construction so TokenizedField instances created during widget build
            # can resolve against an already-populated registry. Uses only
            # spawn_tracked (asyncio task) and no privileged FS — safe regardless
            # of whether the rgbmatrix backend has dropped root (constraint #13).
            _source_registry = build_source_registry(config.sources, session=session)
            set_data_registry(_source_registry)
            # spawn_source_refresh returns a LIST: the 1 Hz sync task + one
            # run_monitor_loop task per polled source. Store as a list so
            # hot-reload (Task 5) can cancel them all.
            source_refresh_task = spawn_source_refresh(_source_registry)
            # Give polled sources a brief, bounded head start so token widgets
            # show real data on their first display instead of the placeholder
            # (pairs with the engine measure-at-lock fix). Bounded: a slow or
            # down source degrades to the placeholder and self-corrects next tick.
            await prime_polled_sources(_source_registry)

            last_widget: Any = None  # track for section-to-section transitions
            last_scroll_pos: int = 0  # track scroll pos for between-section transitions
            last_scale: int = config.display.default_scale  # outgoing section's scale
            last_content_height: int = 16  # outgoing section's content_height
            last_bg_color: tuple[int, int, int] | None = (
                None  # outgoing section's bg_color (for run_transition's t<0.5 reset)
            )
            widget_cache: dict[str, Any] = {}
            widget_tasks: dict[str, set] = {}

            # Plugin startup hooks run once now that the frame + session exist.
            await _run_startup_hooks(
                plugins.startup_hooks,
                StartupContext(frame=led_frame, session=session, config=config),
            )

            try:
                _empty_playlist_warned = False
                _any_section_ran = True  # first pass: no idle before sections run
                _display_dark = False
                _dark_streak = 0
                while True:
                    # Belt-and-suspenders outer-loop check (once per full
                    # playlist cycle). The per-section check below and the
                    # Ticker's per-tick restart_check give the actual
                    # second-level responsiveness; this catches the rare case
                    # of an empty/no-section playlist that never enters the
                    # inner loops.
                    if _restart_requested():
                        logging.info(
                            "restart requested via web UI"
                            " — exiting for supervisor restart"
                        )
                        sys.exit(0)
                    _reload_res = await _detect_and_apply_reload(
                        watcher=watcher,
                        config_path=config_path,
                        config=config,
                        widget_cache=widget_cache,
                        widget_tasks=widget_tasks,
                        render_breaker=render_breaker,
                        schedule_task=schedule_task,
                        source_refresh_task=source_refresh_task,
                        led_frame=led_frame,
                        session=session,
                    )
                    if _reload_res is not None:
                        config = _reload_res.config
                        default_section_trans = _reload_res.default_section_trans
                        schedule_task = _reload_res.schedule_task
                        source_refresh_task = _reload_res.source_refresh_task
                        # Mirrors the mid-cycle reload pin below: a reload
                        # landing here (e.g. restoring sections after an
                        # empty-playlist interlude) must not let the next
                        # `_idle_when_all_scheduled_out` call treat this as a
                        # continuation of a stale all-out streak — that would
                        # commit a spurious dark on hours-old evidence instead
                        # of giving the freshly-reloaded sections a pass.
                        _any_section_ran = True
                        _dark_streak = 0
                    # A section-less playlist has nothing to draw — idle + warn
                    # (checked AFTER the reload above, so adding sections recovers)
                    # instead of busy-spinning this loop at 100% CPU.
                    _idled, _empty_playlist_warned = await _idle_on_empty_playlist(
                        config.sections, _empty_playlist_warned
                    )
                    if _idled:
                        # Approved behavior change (#396): zero sections =
                        # nothing to display = blank, same semantics as the
                        # all-scheduled-out dark path — NOT a frozen last
                        # frame. Unconditional (dark or not): a hot-reload
                        # can land a zero-section config WHILE the panel is
                        # dark, or the playlist can start/become empty
                        # before any dark commit ever happens — either way
                        # the keepalive swap keeps overlay hooks compositing
                        # and swap_count advancing throughout.
                        _blank_swap(led_frame)
                        # Same rationale as `_on_display_dark_transition`: an
                        # empty-playlist interlude must not let the recovery
                        # entry transition replay the pre-interlude widget as
                        # its outgoing frame from a black panel. Resetting
                        # every iteration is idempotent — cheap insurance
                        # against the interlude lasting more than one pass.
                        last_widget, last_scroll_pos, last_bg_color = None, 0, None
                        continue
                    _was_dark = _display_dark
                    _display_dark, _dark_streak = await _idle_when_all_scheduled_out(
                        led_frame, _any_section_ran, _display_dark, _dark_streak
                    )
                    _dark_reset = _on_display_dark_transition(_was_dark, _display_dark)
                    if _dark_reset is not None:
                        last_widget, last_scroll_pos, last_bg_color = _dark_reset
                    _any_section_ran = False
                    for section_index, section in enumerate(config.sections):
                        # Per-section reload check: caps reload latency at one
                        # section instead of one full playlist cycle, so a save
                        # lands inside the web UI's confirmation window. Applied
                        # at the section seam (never mid-scroll). On a reload we
                        # break to restart the cycle against the new sections.
                        _reload_res = await _detect_and_apply_reload(
                            watcher=watcher,
                            config_path=config_path,
                            config=config,
                            widget_cache=widget_cache,
                            widget_tasks=widget_tasks,
                            render_breaker=render_breaker,
                            schedule_task=schedule_task,
                            source_refresh_task=source_refresh_task,
                            led_frame=led_frame,
                            session=session,
                        )
                        if _reload_res is not None:
                            config = _reload_res.config
                            default_section_trans = _reload_res.default_section_trans
                            schedule_task = _reload_res.schedule_task
                            source_refresh_task = _reload_res.source_refresh_task
                            _any_section_ran = True
                            break
                        # Per-section restart check: caps latency at one
                        # section even for run modes where the per-tick
                        # ticker hook can't fire (e.g. an empty section that
                        # never enters a tick loop). The Ticker's per-tick
                        # restart_check (below) gives finer ~second-level
                        # responsiveness within a section.
                        if _restart_requested():
                            logging.info(
                                "restart requested via web UI"
                                " — exiting for supervisor restart"
                            )
                            sys.exit(0)
                        if not _section_schedule_active(section):
                            logging.debug(
                                "section %d skipped: outside its schedule window",
                                section_index,
                            )
                            continue
                        notif_queue: asyncio.Queue[Any] = asyncio.Queue(
                            maxsize=TICKER_QUEUE_MAXSIZE
                        )
                        widgets: list[Any] = []
                        runtime_coerce: list[Any] = []
                        for widget_cfg in section.widgets:
                            # Cache async widgets to avoid leaking background tasks.
                            # _build_widget_guarded handles both cache hits and
                            # cache-miss builds, capturing background tasks in
                            # widget_tasks so a reload can cancel exactly those.
                            # Containers (Protocol in widget.py) are expanded by the
                            # engine on every cycle pass via _expand_sources — pushing
                            # the container itself (not its current feed_stories)
                            # keeps the displayed content in sync with the container's
                            # background update() task. PoolMonitor satisfies Container
                            # structurally (has feed_stories), so no isinstance check
                            # is needed here.
                            widget = await _build_widget_guarded(
                                widget_cfg,
                                session=session,
                                config_dir=config_path.parent,
                                default_bg_color=section.bg_color,
                                panel_h_for_warning=panel_h_for_warning,
                                coercion_collector=runtime_coerce,
                                widget_cache=widget_cache,
                                widget_tasks=widget_tasks,
                            )
                            if widget is None:
                                continue  # build failed; skip this widget this pass
                            widgets.append(widget)
                        # Drain coerce warnings collected during this section's
                        # widget build. Empty in the common case; one log line per
                        # CoercionWarning otherwise.
                        for w in runtime_coerce:
                            logging.warning("config coerce: %s", w.message)

                        title = await _build_title_guarded(
                            section.title,
                            session=session,
                            config_dir=config_path.parent,
                            default_bg_color=section.bg_color,
                            panel_h_for_warning=panel_h_for_warning,
                        )

                        # Widget-level all-scheduled-out gate: a section with NO
                        # section-level schedule can still end up with nothing to
                        # show if every widget's OWN `schedule = {...}` is
                        # inactive (or a Container is currently empty). Skip the
                        # rest of the section body the same way the section-level
                        # gate above does — _any_section_ran stays False so
                        # `_idle_when_all_scheduled_out` blanks + idles instead of
                        # leaving the panel on its last drawn frame.
                        _has_content, _expanded_widgets = _section_has_content(
                            title, widgets, render_breaker
                        )
                        if not _has_content:
                            logging.debug(
                                "section %d skipped: all widgets scheduled out "
                                "(empty rotation)",
                                section_index,
                            )
                            continue
                        _any_section_ran = True
                        status_board.record_section(
                            index=section_index,
                            total=len(config.sections),
                            mode=section.mode,
                            title=str((section.title or {}).get("text", "")),
                            widget_count=len(section.widgets),
                        )
                        run_method = RUN_MODES.get(
                            section.mode,
                            "run_ticker",
                        )

                        # Entry transition precedence:
                        #   1. entry_transition (explicit per-section entry override)
                        #   2. transition (when transition_specified)
                        #   3. between_sections (global default)
                        if section.entry_transition is not None:
                            entry_trans = _build_trans_obj_guarded(
                                section.entry_transition
                            )
                            entry_duration = section.entry_transition.duration
                            entry_easing = section.entry_transition.easing
                            entry_fps = section.entry_transition.transition_fps
                        elif section.transition_specified:
                            entry_trans = _build_trans_obj_guarded(section.transition)
                            entry_duration = section.transition.duration
                            entry_easing = section.transition.easing
                            entry_fps = section.transition.transition_fps
                        else:
                            entry_trans = default_section_trans
                            entry_duration = config.between_sections.duration
                            entry_easing = config.between_sections.easing
                            entry_fps = config.between_sections.transition_fps

                        # Run section-to-section transition.
                        # Wrap at the OUTGOING section's scale so the outgoing widget
                        # keeps its on-screen size during the dissolve. Any visual jolt
                        # from the scale change happens at the very end of the
                        # transition (one frame), where the new section's first render
                        # immediately overwrites it.
                        #
                        # Containers (RSS / data-widget monitors) don't implement
                        # draw() — they expose `feed_stories` instead. If a section
                        # starts with a container and has no [section.title], expand
                        # to the container's first current story so the transition's
                        # `incoming.draw()` call has a real widget to render.
                        if title:
                            first_widget = title
                        elif _expanded_widgets:
                            first_widget = _expanded_widgets[0]
                        else:
                            first_widget = None
                        just_transitioned = _entry_transition_active(
                            last_widget, first_widget, entry_trans
                        )
                        if just_transitioned:
                            assert (
                                entry_trans is not None
                            )  # narrowed: just_transitioned requires it
                            canvas = _maybe_wrap(
                                led_frame.get_clean_canvas(),
                                last_scale,
                                last_content_height,
                            )
                            canvas = await run_transition(
                                canvas,
                                led_frame,
                                last_widget,
                                first_widget,
                                transition=entry_trans,
                                duration=entry_duration,
                                easing=entry_easing,
                                scroll_speed=(1.0 / entry_fps)
                                if entry_fps is not None
                                else 0.05,
                                outgoing_scroll_pos=last_scroll_pos,
                                # Smoothly cross between scales: outgoing fades out
                                # at last_scale; at t >= 0.5 the wrapper switches
                                # to section.scale so incoming dissolves IN at its
                                # native size (no wrong-scale flash, no snap-in
                                # after the dissolve completes). Content height
                                # must also match the new section so widgets like
                                # two_row don't shift vertically when the section
                                # actually starts running.
                                incoming_scale=section.scale,
                                incoming_content_height=section.content_height,
                                # Preserve bg color through the transition.
                                # `outgoing_bg_color` keeps the previous
                                # section's bg painted at t<0.5 so it doesn't
                                # vanish to black the instant the transition
                                # starts; `incoming_bg_color` ramps in the
                                # new bg at t>=0.5 (and the hires snap respects
                                # it too) so the last transition frame matches
                                # the section's first reset_canvas. Both
                                # default to None — the legacy behavior was
                                # `Clear()` for the entire transition.
                                outgoing_bg_color=last_bg_color,
                                incoming_bg_color=section.bg_color,
                                breaker=render_breaker,
                            )

                        # Widget transition precedence:
                        #   1. widget_transition (explicit per-section widget override)
                        #   2. transition (when transition_specified)
                        #   3. None (cut)
                        widget_trans_cfg = section.widget_transition or (
                            section.transition if section.transition_specified else None
                        )
                        if (
                            widget_trans_cfg is not None
                            and widget_trans_cfg.type != "cut"
                        ):
                            transition_fn = _build_trans_obj_guarded(widget_trans_cfg)
                            transition_config = widget_trans_cfg
                        else:
                            transition_fn = None
                            transition_config = None

                        ticker_kwargs: dict[str, Any] = {
                            "monitors": widgets,
                            "frame": led_frame,
                            "title": title,
                            "title_delay": _resolve_title_delay(
                                section.start_hold, config.title_delay
                            ),
                            "notif_queue": notif_queue,
                            "transition_config": transition_config,
                            "transition_fn": transition_fn,
                            "hold_time": section.hold_time,
                            "continuous_scroll": section.continuous_scroll,
                            "scale": section.scale,
                            "content_height": section.content_height,
                            "breaker": render_breaker,
                            # Per-tick restart check: lets the engine unwind
                            # from inside a long hold/scroll within ~one engine
                            # tick (tens of ms) when a web-UI restart is queued,
                            # instead of waiting for the section/playlist to end.
                            "restart_check": _restart_requested,
                        }
                        if section.scroll_step_ms is not None:
                            ticker_kwargs["scroll_speed"] = (
                                section.scroll_step_ms / 1000
                            )
                        buffer_msg = _resolve_buffer_msg(section)
                        if buffer_msg is not None:
                            ticker_kwargs["buffer_msg"] = buffer_msg
                        ticker = Ticker(**ticker_kwargs)

                        # If a between-section transition just ran, the title is
                        # already on-screen at t=1.0 of the dissolve. Tell the section
                        # to start at pos=0 (no scroll-in) so we don't blank the panel
                        # before redrawing.
                        run_kwargs: dict[str, Any] = {"loop_count": section.loop_count}
                        # `start_pos` is only meaningful for scrolling modes —
                        # `run_slideshow` doesn't have a scroll position to skip past.
                        if just_transitioned and run_method in (
                            "run_ticker",
                            "run_one_at_a_time",
                        ):
                            run_kwargs["start_pos"] = 0

                        try:
                            await getattr(ticker, run_method)(**run_kwargs)
                        except asyncio.CancelledError:
                            raise
                        except RestartRequested:
                            # The Ticker's per-tick restart_check fired mid-hold
                            # /scroll: the marker was already consumed (deleted)
                            # inside `_restart_requested`. The `finally` below
                            # cancels the enqueue task; then exit cleanly for the
                            # supervisor to restart us (SystemExit threads up
                            # through finally → shutdown hooks, same path as the
                            # outer-loop / per-section checks).
                            logging.info(
                                "restart requested via web UI"
                                " — exiting for supervisor restart"
                            )
                            sys.exit(0)
                        finally:
                            if (
                                ticker._enqueue_task is not None
                                and not ticker._enqueue_task.done()
                            ):
                                ticker._enqueue_task.cancel()
                                with contextlib.suppress(
                                    asyncio.CancelledError, Exception
                                ):
                                    await ticker._enqueue_task

                        # Brief pause before between-sections transition
                        if section.continuous_scroll:
                            await asyncio.sleep(1.0)

                        # Track the last widget and scroll pos for the
                        # next section transition
                        last_scroll_pos = ticker.last_scroll_pos
                        last_scale = section.scale
                        last_content_height = section.content_height
                        last_bg_color = section.bg_color
                        # Containers (RSS / data-widget monitors) don't implement
                        # draw() — the next section's transition would crash on
                        # `outgoing.draw()` if last_widget were a container. Expand
                        # to the container's last current story; if the container
                        # is currently empty, keep the previous last_widget (the
                        # next transition will use whatever was last on-screen).
                        # A title fallback applies even when `widgets` is
                        # non-empty: if every widget's rotation is currently
                        # empty (all scheduled out / empty containers) but the
                        # section has a title, the title — not a stale
                        # earlier-section last_widget — is what's actually on
                        # screen, so it must be what the next entry transition
                        # renders as outgoing.
                        if widgets:
                            expanded = _expand_sources(widgets, render_breaker)
                            if expanded:
                                last_widget = expanded[-1]
                            elif title:
                                last_widget = title
                            # else: empty container this cycle — keep prior
                            # last_widget so the next transition still has a
                            # real widget to render as outgoing.
                        elif title:
                            last_widget = title
            finally:
                # Best-effort: run plugin shutdown hooks when the loop exits
                # (normally via cancellation on Ctrl-C / SIGTERM).
                await _run_shutdown_hooks(plugins.shutdown_hooks)
    finally:
        # Tear down the status board and its log handler so a second run()
        # call in the same process (or a cancellation between setup and the
        # main loop) doesn't accumulate stale handlers.
        _teardown_status_board(_status_handle)
