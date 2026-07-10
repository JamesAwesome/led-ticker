"""Web status UI sidecar (led-ticker webui).

Pure builder (build_webui_app) + production runner (serve_webui/run_webui),
mirroring busy_http. The sidecar never writes status.json. It touches
config.toml only through the token-gated PUT /api/config editor
(validate → conflict-check → backup → atomic write); all GET and preview
routes remain read-only. Without a token, the editor is disabled and Save
returns 403. It must keep working when the display process is absent —
every degraded state is a friendly JSON answer, not a 500. This module
must never import rgbmatrix (tripwire lands in tests/test_webui_purity.py).
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import shutil
import time
import tomllib
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

from aiohttp import web

from led_ticker._build import build_ref
from led_ticker.config import resolve_secret_token
from led_ticker.plugin_reconcile import STAMP_NAME
from led_ticker.preview import HEADER, PREVIEW_MAGIC, PREVIEW_VERSION
from led_ticker.reload import config_hash
from led_ticker.status_board import SCHEMA_VERSION
from led_ticker.validate import (
    ValidationResult,
    validate_config,
    validate_config_text,
)
from led_ticker.webui._paths import list_config_names, safe_config_member
from led_ticker.webui.redact import REDACTED, redact_toml, restore_redacted

# led_ticker.validate was verified clean of rgbmatrix at task-8 implementation
# time:  python -c "import led_ticker.validate; print([m for m in
# sys.modules if 'rgbmatrix' in m])"  → [].  Top-level import is safe.

logger = logging.getLogger(__name__)

STALE_FACTOR = 3.0  # stale when published_at is older than factor × min_interval
MAX_VALIDATE_BODY = 1024 * 1024  # 1 MB (used by the /api/validate task)

# Routes that are intentionally open (no auth required) even when a token is
# configured. The store endpoint is public so the UI can render the plugin list
# for unauthenticated visitors who want to see what is installed.
_OPEN_PATHS = frozenset({"/api/store"})


def _token_ok(provided: str | None, token: str) -> bool:
    """Constant-time token check.

    Returns True when the caller is authorized: either no token is configured
    (open system) or the provided value matches in constant time.  Using
    hmac.compare_digest avoids leaking the token via response-timing on a
    char-by-char `==` comparison.  The open/no-token case is decided BEFORE the
    compare so an open system never depends on the (empty) token bytes.
    """
    if not token:
        return True
    return hmac.compare_digest(provided or "", token)


def _read_status(status_path: Path) -> dict:
    """Classify the status file into the API envelope. Never raises."""
    try:
        # Size is unbounded: the only writer is the trusted display process,
        # and status.json is a single small snapshot — not user-controlled input.
        raw = status_path.read_text()
    except FileNotFoundError:
        return {
            "state": "missing",
            "hint": (
                "The display process hasn't published yet — is led-ticker "
                "running, and does its config have a [web] block?"
            ),
        }
    except OSError as e:
        return {"state": "unreadable", "detail": str(e)}
    try:
        status = json.loads(raw)
    except ValueError as e:
        return {"state": "unreadable", "detail": f"bad JSON: {e}"}
    if not isinstance(status, dict):
        return {
            "state": "unreadable",
            "detail": f"not a JSON object (got {type(status).__name__})",
        }
    found = status.get("schema")
    if found != SCHEMA_VERSION:
        return {
            "state": "schema_mismatch",
            "found": found,
            "supported": SCHEMA_VERSION,
            "hint": "led-ticker and the webui are running different versions.",
        }
    try:
        age = time.time() - float(status.get("published_at", 0))
        threshold = STALE_FACTOR * float(status.get("min_interval", 2.0))
    except (TypeError, ValueError) as e:
        # Schema-valid envelope but corrupt timing fields (truncated write,
        # hand-edited file). Classify, never raise.
        return {"state": "unreadable", "detail": f"bad timing field: {e}"}
    state = "stale" if age > threshold else "ok"
    return {"state": state, "age_seconds": round(age, 1), "status": status}


def _fresh_inner_status(status_path: Path) -> dict:
    """Inner status dict ONLY when the envelope is fresh ("ok"), else {}.

    `_read_status` carries the parsed status under "status" for both "ok" AND
    "stale" envelopes (stale = the file is present but the display process hasn't
    republished within the staleness threshold — e.g. the process died leaving a
    snapshot on disk). For the Store, an empty dict is what marks the display
    offline (build_store: display_online = bool(status)). Forwarding a stale
    inner status would report display_online=True and live "Active" badges for a
    dead display. Gate on freshness so stale ⇒ offline, matching the spec.
    """
    envelope = _read_status(status_path)
    return envelope.get("status", {}) if envelope.get("state") == "ok" else {}


def _build_store(**kwargs: Any) -> dict[str, Any]:
    """Call build_store from led_ticker.webui.store with lazy import.

    Defined at module level so tests can monkeypatch it on this module.
    The import is deferred to avoid pulling in rgbmatrix at webui import time.
    """
    from led_ticker.webui.store import build_store  # noqa: PLC0415

    return build_store(**kwargs)


def _read_stamp_readonly(
    volume_root: Path = Path("/data/plugins"),
) -> dict[str, str] | None:
    """The reconcile stamp, if readable — for the Store's restart_to_upgrade
    badge. The webui mounts the plugin volume :ro, so plugin_reconcile's
    read_stamp (which gates on os.W_OK, mirroring the install target) would
    return None here; this reader gates on EXISTENCE only, like
    apply_volume_visibility. Never raises; None = no badge, never an error."""
    path = volume_root / STAMP_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    # PEP 758 (Python 3.14) parenthesis-free tuple catch — not a typo.
    except OSError, ValueError:
        return None
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        return None
    return data


def _load_catalog_lazy():
    """Load the plugin catalog with lazy import (no rgbmatrix at import time).

    Defined at module level so tests can monkeypatch it on this module.
    """
    from led_ticker.plugins_catalog import load_catalog  # noqa: PLC0415

    return load_catalog()


async def _update_manifest_atomic(
    manifest_path: Path,
    transform: Callable[[str], str | None],
    lock: asyncio.Lock,
) -> None:
    """Atomic read-modify-write of the manifest under a single locked section.

    The ENTIRE read→compute→write cycle runs inside ``lock`` so two concurrent
    authenticated requests (install/install, remove/remove, install/remove)
    cannot interleave around an await and lose an update — mirroring
    save_handler's whole-critical-section lock discipline.

    ``transform`` receives the freshly-read manifest text (``""`` when absent)
    and returns the new text to write, or ``None`` to skip the write entirely
    (e.g. an idempotent install where the requirement is already declared — so
    no spurious .bak is produced).

    Write durability mirrors save_handler: .bak backup → tmp + os.replace.
    """
    async with lock:
        current = (
            manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else ""
        )
        new_text = transform(current)
        if new_text is None:
            return
        tmp = manifest_path.with_name(manifest_path.name + ".tmp")
        try:
            if manifest_path.exists():
                bak = manifest_path.with_suffix(manifest_path.suffix + ".bak")
                shutil.copy2(manifest_path, bak)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(new_text, encoding="utf-8")
            os.replace(tmp, manifest_path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise


def build_webui_app(
    *,
    config_path: Path,
    status_path: Path,
    token: str = "",
    allow_restart: bool = False,
) -> web.Application:
    """Build the aiohttp app. Pure: no I/O at build time."""

    @web.middleware
    async def auth(request: web.Request, handler):
        if token and request.path not in _OPEN_PATHS:
            provided = request.headers.get("X-Web-Token") or request.query.get("token")
            if not _token_ok(provided, token):
                return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request)

    async def status_handler(request: web.Request) -> web.Response:
        payload = _read_status(status_path)
        payload["webui_build"] = build_ref()
        payload["allow_restart"] = allow_restart
        return web.json_response(payload)

    restart_marker_path = status_path.parent / "restart-requested"

    async def restart_handler(request: web.Request) -> web.Response:
        """POST /api/restart — write the restart marker for the display process.

        Token-gated by the global auth middleware (restart is NOT in _OPEN_PATHS).
        Mirrors install/save convention: no token configured → 403 editing disabled,
        not allow_restart → 403 restart disabled.
        """
        if not token:
            return web.json_response({"error": "editing disabled"}, status=403)
        if not allow_restart:
            return web.json_response({"error": "restart disabled"}, status=403)
        restart_marker_path.write_text("")
        return web.json_response({"ok": True})

    preview_frame_path = status_path.parent / "preview.bin"
    preview_marker_path = status_path.parent / "preview-requested"

    async def preview_handler(request: web.Request) -> web.Response:
        # The fetch IS the watch signal: touch the marker first, so even an
        # idle answer wakes the display's mirror for the next poll. This is
        # the sidecar's only write, ever — one empty file, mtime-only.
        try:
            preview_marker_path.touch()
        except OSError:
            logger.debug("could not touch preview marker", exc_info=True)
        try:
            data = preview_frame_path.read_bytes()
        except FileNotFoundError:
            return web.json_response({"state": "idle"})
        except OSError as e:
            return web.json_response({"state": "idle", "detail": str(e)})
        if len(data) < HEADER.size:
            return web.json_response({"state": "unsupported"})
        magic, ver, w, h, _res, seq = HEADER.unpack(data[: HEADER.size])
        if (
            magic != PREVIEW_MAGIC
            or ver != PREVIEW_VERSION
            or len(data) != HEADER.size + w * h * 3
        ):
            return web.json_response({"state": "unsupported"})
        return web.Response(
            body=data[HEADER.size :],
            content_type="application/octet-stream",
            headers={
                "X-Preview-Width": str(w),
                "X-Preview-Height": str(h),
                "X-Preview-Seq": str(seq),
            },
        )

    async def store_handler(request: web.Request) -> web.Response:
        inner_status: dict = _fresh_inner_status(status_path)
        manifest_path = config_path.parent / "requirements-plugins.txt"
        payload = _build_store(
            manifest_path=manifest_path,
            config_path=config_path,
            status=inner_status,
            token_configured=bool(token),
            stamp=_read_stamp_readonly(),
        )
        provided = request.headers.get("X-Web-Token") or request.query.get("token")
        if not _token_ok(provided, token):
            from led_ticker.webui.store import redact_anonymous  # noqa: PLC0415

            payload = redact_anonymous(payload)
        payload["allow_restart"] = allow_restart
        return web.json_response(payload)

    manifest_lock = asyncio.Lock()

    async def install_handler(request: web.Request) -> web.Response:
        """POST /api/store/install — add a catalog plugin to the manifest.

        Token-gated by the global auth middleware (install is NOT in _OPEN_PATHS).
        Mirrors save_handler's "no token → 403 editing disabled" convention for
        clarity (the middleware already blocks tokenless requests when a token is
        configured, but a missing token means editing is administratively disabled).
        """
        if not token:
            return web.json_response({"error": "editing disabled"}, status=403)

        if (request.content_length or 0) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)

        try:
            payload = await request.json()
        except ValueError:
            return web.json_response({"error": "body must be JSON"}, status=400)

        namespace = payload.get("namespace") if isinstance(payload, dict) else None
        if not isinstance(namespace, str) or not namespace:
            return web.json_response({"error": "missing namespace"}, status=400)

        # Resolve namespace → CatalogEntry.  Catalog.get() is NAME-based, so
        # build a namespace map the same way store.py does (O(N), N is small).
        catalog = _load_catalog_lazy()
        entry = next((e for e in catalog.entries if e.namespace == namespace), None)
        if entry is None:
            return web.json_response({"error": "unknown plugin"}, status=400)

        manifest_path = config_path.parent / "requirements-plugins.txt"

        # Import helpers lazily to keep the module rgbmatrix-pure.
        from led_ticker.app.plugin_cmd import _requirement_key  # noqa: PLC0415

        req = entry.requirement()
        req_key = _requirement_key(req)

        def add_requirement(current: str) -> str | None:
            # Runs INSIDE manifest_lock against the freshly-read manifest text.
            # Returning None skips the write (idempotent: already declared → no
            # spurious .bak).  Dedup logic mirrors _update_requirements.
            lines = current.splitlines()
            declared = any(
                stripped
                and not stripped.startswith("#")
                and _requirement_key(stripped) == req_key
                for stripped in (line.strip() for line in lines)
            )
            if declared:
                return None  # idempotent: no write — and no stale line to drop,
                # since any matching line would have set `declared` above.
            # Not declared: every existing line is a keeper; append the fresh req.
            return "\n".join([*lines, req]).rstrip("\n") + "\n"

        try:
            await _update_manifest_atomic(manifest_path, add_requirement, manifest_lock)
        except OSError as e:
            return web.json_response(
                {"error": f"manifest write failed: {e}"}, status=500
            )

        # Return the rebuilt store entry for this namespace so the UI refreshes.
        inner_status: dict = _fresh_inner_status(status_path)
        store_payload = _build_store(
            manifest_path=manifest_path,
            config_path=config_path,
            status=inner_status,
            token_configured=bool(token),
            stamp=_read_stamp_readonly(),
        )
        plugin_entry = next(
            (
                p
                for p in store_payload.get("plugins", [])
                if p["namespace"] == namespace
            ),
            {"namespace": namespace},
        )
        return web.json_response(plugin_entry)

    async def remove_handler(request: web.Request) -> web.Response:
        """DELETE /api/store/remove — drop a catalog plugin from the manifest.

        Token-gated by the global auth middleware (remove is NOT in _OPEN_PATHS).
        Mirrors install_handler's "no token → 403 editing disabled" convention.
        Guards against removing a plugin that the running config still references
        (config-ref 409) so the panel can't be broken by a dangling type/transition.
        """
        if not token:
            return web.json_response({"error": "editing disabled"}, status=403)

        if (request.content_length or 0) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)

        try:
            payload = await request.json()
        except ValueError:
            return web.json_response({"error": "body must be JSON"}, status=400)

        namespace = payload.get("namespace") if isinstance(payload, dict) else None
        if not isinstance(namespace, str) or not namespace:
            return web.json_response({"error": "missing namespace"}, status=400)

        # Resolve namespace → CatalogEntry.
        catalog = _load_catalog_lazy()
        entry = next((e for e in catalog.entries if e.namespace == namespace), None)
        if entry is None:
            return web.json_response({"error": "unknown plugin"}, status=400)

        # Import helpers lazily to keep the module rgbmatrix-pure.
        from led_ticker.app.plugin_cmd import (  # noqa: PLC0415
            _entry_match_keys,
            _requirement_key,
        )

        req = entry.requirement()
        req_key = _requirement_key(req)
        # The manifest line may have been declared via a NON-default source
        # (e.g. `--source git` when pypi is the catalog default); drop it by any
        # of the entry's source keys so removal matches build_store's (widened)
        # declared? detection — otherwise the Store would show a Remove button
        # that silently no-ops. `req_key` stays the pack-sibling grouping key
        # below (shared packages are single-source, unaffected by the widening).
        match_keys = _entry_match_keys(entry)

        # Config-reference guard: refuse if the running config still uses THIS
        # plugin OR any sibling namespace that shares the same pip package.
        # Multiple catalog namespaces can map to one package (e.g. nyancat/
        # pokeball/pacman/sailor_moon → led-ticker-flair); removing the manifest
        # line drops the package for all of them, so removing one must not break
        # a config that references a sibling.
        from led_ticker.webui.store import config_references  # noqa: PLC0415

        siblings = {
            e.namespace
            for e in catalog.entries
            if _requirement_key(e.requirement()) == req_key
        }
        siblings.add(namespace)
        config_refs = config_references(config_path)
        refs = [r for ns in siblings for r in config_refs.get(ns, [])]
        if refs:
            return web.json_response({"error": "in_use", "in_use_by": refs}, status=409)

        manifest_path = config_path.parent / "requirements-plugins.txt"

        def drop_requirement(current: str) -> str:
            # Runs INSIDE manifest_lock against the freshly-read manifest text.
            kept: list[str] = []
            for line in current.splitlines():
                stripped = line.strip()
                if (
                    stripped
                    and not stripped.startswith("#")
                    and _requirement_key(stripped) in match_keys
                ):
                    continue  # drop this line
                kept.append(line)
            body = "\n".join(kept).rstrip("\n")
            return body + "\n" if body else ""

        try:
            await _update_manifest_atomic(
                manifest_path, drop_requirement, manifest_lock
            )
        except OSError as e:
            return web.json_response(
                {"error": f"manifest write failed: {e}"}, status=500
            )

        # Return the rebuilt store entry for this namespace so the UI refreshes.
        # config_refs was already parsed above for the in-use guard; pass it so
        # build_store doesn't re-parse config.toml a second time per DELETE.
        inner_status: dict = _fresh_inner_status(status_path)
        store_payload = _build_store(
            manifest_path=manifest_path,
            config_path=config_path,
            status=inner_status,
            token_configured=bool(token),
            refs=config_refs,
            stamp=_read_stamp_readonly(),
        )
        plugin_entry = next(
            (
                p
                for p in store_payload.get("plugins", [])
                if p["namespace"] == namespace
            ),
            {"namespace": namespace},
        )
        return web.json_response(plugin_entry)

    async def upgrade_handler(request: web.Request) -> web.Response:
        """POST /api/store/upgrade — rewrite a plugin's manifest line to the
        latest version (resolver queries PyPI / git; NO pip here — the display
        process's boot reconcile installs the change after a restart).

        Token-gated by the global auth middleware (upgrade is NOT in
        _OPEN_PATHS); mirrors install_handler's "no token → 403" convention.
        The network resolve runs in a thread (asyncio.to_thread) so a slow
        remote can't stall the event loop, and BEFORE the manifest lock; the
        locked transform re-checks the line so a concurrent edit → 409, never
        a lost update.
        """
        if not token:
            return web.json_response({"error": "editing disabled"}, status=403)

        if (request.content_length or 0) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)

        try:
            payload = await request.json()
        except ValueError:
            return web.json_response({"error": "body must be JSON"}, status=400)

        namespace = payload.get("namespace") if isinstance(payload, dict) else None
        if not isinstance(namespace, str) or not namespace:
            return web.json_response({"error": "missing namespace"}, status=400)

        catalog = _load_catalog_lazy()
        entry = next((e for e in catalog.entries if e.namespace == namespace), None)
        if entry is None:
            return web.json_response({"error": "unknown plugin"}, status=400)

        # Lazy imports keep the module rgbmatrix-pure.
        from led_ticker.app import plugin_upgrade  # noqa: PLC0415
        from led_ticker.app.plugin_cmd import (  # noqa: PLC0415
            _entry_match_keys,
            _find_requirement_lines_for_keys,
            _requirement_key,
            _strip_comment,
        )

        # Match against EVERY source key the entry could be declared under, so a
        # plugin added via its non-default source (e.g. `--source git` when pypi
        # is the catalog default) is found instead of 404ing as "not declared".
        match_keys = _entry_match_keys(entry)
        manifest_path = config_path.parent / "requirements-plugins.txt"

        current_lines = _find_requirement_lines_for_keys(manifest_path, match_keys)
        if not current_lines:
            return web.json_response({"error": "not declared"}, status=404)
        old_spec = _strip_comment(current_lines[-1])

        try:
            new_spec = await asyncio.to_thread(
                plugin_upgrade.resolve_latest, old_spec, catalog_name=entry.name
            )
        except plugin_upgrade.UpgradeError as e:
            return web.json_response({"error": str(e)}, status=502)

        if new_spec == old_spec:
            return web.json_response(
                {"up_to_date": True, "namespace": namespace, "current": old_spec}
            )

        import datetime  # noqa: PLC0415

        provenance = f"# upgraded {datetime.date.today().isoformat()}, was {old_spec}"

        class _Conflict(Exception):
            pass

        def replace_line(current: str) -> str | None:
            # Runs INSIDE manifest_lock against the freshly-read manifest text.
            # The resolve happened OUTSIDE the lock, so re-verify the line we
            # resolved from is still there — a concurrent install/remove/save
            # between resolve and write must 409, not be silently clobbered.
            out: list[str] = []
            replaced = False
            for line in current.splitlines():
                stripped = line.strip()
                if (
                    stripped
                    and not stripped.startswith("#")
                    and _requirement_key(stripped) in match_keys
                ):
                    if _strip_comment(stripped) != old_spec:
                        raise _Conflict
                    out.append(f"{new_spec}  {provenance}")
                    replaced = True
                    continue
                out.append(line)
            if not replaced:
                raise _Conflict
            return "\n".join(out).rstrip("\n") + "\n"

        try:
            await _update_manifest_atomic(manifest_path, replace_line, manifest_lock)
        except _Conflict:
            return web.json_response(
                {"error": "manifest changed concurrently — retry"}, status=409
            )
        except OSError as e:
            return web.json_response(
                {"error": f"manifest write failed: {e}"}, status=500
            )

        inner_status: dict = _fresh_inner_status(status_path)
        store_payload = _build_store(
            manifest_path=manifest_path,
            config_path=config_path,
            status=inner_status,
            token_configured=bool(token),
            stamp=_read_stamp_readonly(),
        )
        plugin_entry: dict[str, Any] = next(
            (
                p
                for p in store_payload.get("plugins", [])
                if p["namespace"] == namespace
            ),
            {"namespace": namespace},
        )
        plugin_entry["upgraded"] = {"from": old_spec, "to": new_spec}
        return web.json_response(plugin_entry)

    app = web.Application(middlewares=[auth])
    app.router.add_get("/api/status", status_handler)
    app.router.add_post("/api/restart", restart_handler)
    app.router.add_get("/api/store", store_handler)
    app.router.add_post("/api/store/install", install_handler)
    app.router.add_delete("/api/store/remove", remove_handler)
    app.router.add_post("/api/store/upgrade", upgrade_handler)
    _add_config_routes(app, config_path, token, asyncio.Lock())
    app.router.add_get("/api/preview", preview_handler)
    _add_page_route(app)
    return app


def _result_to_json(result: ValidationResult) -> dict:
    """Serialize a ValidationResult for the browser.

    Deliberately excludes result.path — for text validation it is a
    throwaway temp file whose path must not be leaked to the browser.
    ValidationIssue fields: rule, location, message, fix, severity.
    """

    def _issue(i) -> dict:
        return {
            "rule": i.rule,
            "location": i.location,
            "message": i.message,
            "fix": i.fix,
            "severity": i.severity,
        }

    return {
        "valid": result.valid,
        "errors": [_issue(i) for i in result.errors],
        "warnings": [_issue(i) for i in result.warnings],
    }


def _add_config_routes(
    app: web.Application,
    config_path: Path,
    token: str = "",
    save_lock: asyncio.Lock | None = None,
) -> None:
    """Register config routes: GET /api/configs, GET /api/config,
    POST /api/validate, PUT /api/config."""
    if save_lock is None:
        save_lock = asyncio.Lock()

    async def configs_handler(request: web.Request) -> web.Response:
        config_dir = config_path.parent
        return web.json_response(
            {
                "configs": list_config_names(config_dir),
                "running": config_path.name,
            }
        )

    async def config_handler(request: web.Request) -> web.Response:
        target = config_path
        name = request.query.get("name")
        if name is not None:
            member = safe_config_member(config_path.parent, name)
            if member is None:
                return web.json_response({"error": "unknown config"}, status=404)
            target = member
        try:
            text = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return web.json_response({"state": "unreadable", "detail": str(e)})
        geometry: dict = {}
        try:
            display = tomllib.loads(text).get("display", {})
            rows = int(display.get("rows", 16))
            cols = int(display.get("cols", 32))
            chain = int(display.get("chain_length", 1))
            parallel = int(display.get("parallel", 1))
            geometry = {
                "rows": rows,
                "cols": cols,
                "chain_length": chain,
                "parallel": parallel,
                "default_scale": int(display.get("default_scale", 1)),
                "panel_width": cols * chain,
                "panel_height": rows * parallel,
            }
        except ValueError, TypeError, tomllib.TOMLDecodeError:
            pass  # geometry is best-effort; the redacted text is the point
        return web.json_response(
            {
                "state": "ok",
                "toml": redact_toml(text),
                "geometry": geometry,
                "hash": config_hash(target) or "",
            }
        )

    async def validate_handler(request: web.Request) -> web.Response:
        if (request.content_length or 0) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)
        body = await request.text()
        if len(body.encode()) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)
        result = await validate_config_text(body, config_dir=config_path.parent)
        return web.json_response(_result_to_json(result))

    async def validate_file_handler(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except ValueError:
            return web.json_response({"error": "body must be JSON"}, status=400)
        name = payload.get("name") if isinstance(payload, dict) else None
        if not isinstance(name, str):
            return web.json_response({"error": "missing name"}, status=400)
        target = safe_config_member(config_path.parent, name)
        if target is None:
            return web.json_response({"error": "unknown config"}, status=404)
        try:
            result = await validate_config(target)
        except FileNotFoundError:
            # TOCTOU: the file passed the guard but vanished before the
            # validate. Same envelope as never-existed — no oracle, no 500.
            return web.json_response({"error": "unknown config"}, status=404)
        return web.json_response(_result_to_json(result))

    async def save_handler(request: web.Request) -> web.Response:
        if not token:
            return web.json_response({"error": "editing disabled"}, status=403)
        if (request.content_length or 0) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)
        try:
            payload = await request.json()
        except ValueError:
            return web.json_response({"error": "body must be JSON"}, status=400)
        toml_text = payload.get("toml") if isinstance(payload, dict) else None
        base_hash = payload.get("base_hash") if isinstance(payload, dict) else None
        if not isinstance(toml_text, str) or not isinstance(base_hash, str):
            return web.json_response({"error": "missing toml/base_hash"}, status=400)
        if len(toml_text.encode()) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)

        # Serialize the whole critical section (conflict-check → os.replace) so
        # two concurrent PUTs can't interleave and clobber each other.
        async with save_lock:
            # Single read: derive BOTH the conflict hash and the redaction
            # source text from the SAME bytes, so they can never diverge.
            try:
                disk_bytes = config_path.read_bytes()
            except OSError:
                disk_bytes = None
            current = (
                hashlib.sha256(disk_bytes).hexdigest()
                if disk_bytes is not None
                else None
            )
            disk_text = disk_bytes.decode("utf-8") if disk_bytes is not None else ""

            # Conflict check FIRST — never validate/work against a file that moved.
            if current is None:
                # Absent/unreadable file: GET returns hash="" for this state.
                # Honor that convention — a non-empty base_hash means the client
                # based its edit on a file that no longer exists.
                if base_hash != "":
                    return web.json_response(
                        {"error": "file disappeared", "hash": ""}, status=409
                    )
            elif base_hash != current:
                return web.json_response(
                    {"error": "conflict", "hash": current}, status=409
                )

            # Restore any redacted secret from disk (no-op for secret-free config).
            merged = restore_redacted(toml_text, disk_text)
            if REDACTED.strip() in merged:
                return web.json_response(
                    {
                        "error": (
                            "unresolved redacted value; replace ••• with the real "
                            "value or edit the file directly"
                        )
                    },
                    status=400,
                )

            result = await validate_config_text(merged, config_dir=config_path.parent)
            if not result.valid:
                return web.json_response(_result_to_json(result), status=422)

            # Re-check before replace: a host edit may have landed on disk while
            # we validated (the lock only stops concurrent PUTs). Abort if so.
            try:
                recheck_bytes = config_path.read_bytes()
            except OSError:
                recheck_bytes = None
            recheck = (
                hashlib.sha256(recheck_bytes).hexdigest()
                if recheck_bytes is not None
                else None
            )
            if recheck != current:
                return web.json_response(
                    {"error": "conflict", "hash": recheck or ""}, status=409
                )

            # Backup + atomic write.
            tmp = config_path.with_name(config_path.name + ".tmp")
            try:
                if config_path.exists():
                    bak = config_path.with_suffix(config_path.suffix + ".bak")
                    shutil.copy2(config_path, bak)
                tmp.write_text(merged, encoding="utf-8")
                os.replace(tmp, config_path)
            except OSError as e:
                tmp.unlink(missing_ok=True)
                return web.json_response({"error": f"write failed: {e}"}, status=500)

            return web.json_response(
                {"state": "saved", "hash": config_hash(config_path) or ""}
            )

    app.router.add_get("/api/configs", configs_handler)
    app.router.add_get("/api/config", config_handler)
    app.router.add_post("/api/validate", validate_handler)
    app.router.add_post("/api/validate-file", validate_file_handler)
    app.router.add_put("/api/config", save_handler)

    async def inventory_handler(request: web.Request) -> web.Response:
        from led_ticker.webui.inventory import build_inventory  # noqa: PLC0415

        return web.json_response(build_inventory(config_path.parent))

    app.router.add_get("/api/inventory", inventory_handler)


def _add_page_route(app: web.Application) -> None:
    async def index(request: web.Request) -> web.Response:
        html = (
            resources.files("led_ticker.webui").joinpath("static/index.html")
        ).read_text(encoding="utf-8")
        return web.Response(text=html, content_type="text/html")

    app.router.add_get("/", index)


async def serve_webui(
    *,
    config_path: Path,
    status_path: Path,
    host: str,
    port: int,
    token: str = "",
    allow_restart: bool = False,
) -> web.AppRunner:
    """Start the listener; caller keeps the runner and calls .cleanup().
    Same contract as busy_http.serve_busy."""
    runner = web.AppRunner(
        build_webui_app(
            config_path=config_path,
            status_path=status_path,
            token=token,
            allow_restart=allow_restart,
        )
    )
    await runner.setup()
    try:
        site = web.TCPSite(runner, host, port)
        await site.start()
    except Exception:
        await runner.cleanup()
        raise
    logger.info("webui listening on %s:%d", host, port)
    return runner


async def run_webui(config_path: Path, web_cfg) -> None:
    """Process entry point for `led-ticker webui`. Runs until cancelled."""
    runner = await serve_webui(
        config_path=config_path,
        status_path=Path(web_cfg.status_path).expanduser(),
        host=web_cfg.http_host,
        port=web_cfg.http_port,
        token=resolve_secret_token(
            "LED_TICKER_WEB_TOKEN", web_cfg.token, label="web.token"
        ),
        allow_restart=web_cfg.allow_restart,
    )
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
