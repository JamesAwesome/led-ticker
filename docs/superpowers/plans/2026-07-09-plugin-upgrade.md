# Plugin Upgrade Through Reconcile — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an operator upgrade an installed plugin without destroying the plugin volume — via a manifest-line-change stamp in reconcile, a `led-ticker plugin upgrade` CLI verb, and a web-UI Upgrade button.

**Architecture:** (1) Boot reconcile records the exact manifest line each namespace was installed from in `/data/plugins/installed.json`; any line change → reinstall in place. (2) A network-side resolver (`resolve_latest`) finds the newest version for a line (PyPI JSON API / `git ls-remote --tags`). (3) CLI verb and webui endpoint both call the resolver and atomically rewrite the manifest pin; the privileged pip work happens at the next boot's reconcile. Spec: `docs/superpowers/specs/2026-07-09-plugin-upgrade-design.md`.

**Tech Stack:** Python 3.14 stdlib only (urllib, subprocess, json, re) — NO new dependencies (`packaging` is not a core dep; version compare uses digit-tuple parsing). aiohttp for the webui endpoint (already a dep). Vanilla JS in `webui/static/index.html`.

## Global Constraints

- Worktree: `/Users/james/projects/github/jamesawesome/led-ticker-plugin-upgrade`, branch `feat/plugin-upgrade-reconcile`. All paths below are relative to that worktree root. Do all work there — the primary checkout's branch may be switched externally.
- `reconcile()` NEVER raises and the panel always boots — every new failure path logs + degrades (spec "Error handling").
- Reconcile runs on the boot path (panel dark until it returns): no new network calls there. The resolver runs ONLY in CLI/webui context.
- Webui modules must never import rgbmatrix (tripwire `tests/test_webui_purity.py`) — keep new webui imports lazy, mirroring existing handlers.
- No `from __future__ import annotations` anywhere (PEP 649 project rule).
- "No churn": an UNCHANGED manifest line must never reinstall on restart — this property replaces `_exact_pin`'s reason for existing and gets its own tripwire test.
- Stamp comparison uses the comment-stripped requirement portion of the line, so provenance comments never churn.
- Git tag convention: `<name>-vX.Y.Z`; `<name>` resolution order: basename of `#subdirectory=` → catalog entry name → bare `vX.Y.Z` accepted. Version strings must match `^\d+(\.\d+)*$` (this also excludes pre-releases).
- Run tests with `uv run pytest <file> -v` from the worktree root. Before any push: `uv run pyright` (pre-push only, not in make test).
- Commit after every task (each task ends green). NEVER merge or push without James's explicit go-ahead.

## Plan-level refinement of the spec (flag to reviewer)

The spec says the `_exact_pin` drift block is "retired". The stamp can only live where a writable state dir exists — i.e. volume targets (`/data/plugins` in Docker). On the local-venv target (bare-metal dev, no volume) there is no stamp home, so this plan **gates** the existing `_exact_pin` block to run only when the stamp is unavailable, rather than deleting it. That is full retirement on the production path (stamp present) with no regression for local dev. Existing `_exact_pin` tests keep passing unchanged.

## File Structure

- Modify: `src/led_ticker/plugin_reconcile.py` — stamp read/write + drift detection + stamp maintenance (Tasks 1–2)
- Modify: `src/led_ticker/app/plugin_cmd.py` — `_strip_comment` helper; `comment=` param on `_update_requirements` (Tasks 1, 5)
- Create: `src/led_ticker/app/plugin_upgrade.py` — `UpgradeError`, version/git-line helpers, `resolve_latest`, `cmd_upgrade` (Tasks 3–5)
- Modify: `src/led_ticker/app/cli.py` — `plugin upgrade` subparser + dispatch (Task 5)
- Modify: `src/led_ticker/webui/__init__.py` — `upgrade_handler` + route (Task 6)
- Modify: `src/led_ticker/webui/store.py` — `restart_to_upgrade` state from stamp (Task 7)
- Modify: `src/led_ticker/webui/static/index.html` — Upgrade button + badge (Task 7)
- Modify: `CLAUDE.md`, `docs/plugin-system.md`, `docs/site/src/content/docs/plugins/index.mdx`, `docs/site/src/content/docs/reference/cli.mdx` (Task 8)
- Tests: `tests/test_plugin_reconcile.py`, `tests/test_plugin_upgrade.py` (new), `tests/test_webui_app.py`, `tests/test_webui_store.py`

---

### Task 1: `_strip_comment` helper + stamp read/write

**Files:**
- Modify: `src/led_ticker/app/plugin_cmd.py` (add `_strip_comment` next to `_trailing_comment`, ~line 134)
- Modify: `src/led_ticker/plugin_reconcile.py` (add `STAMP_NAME`, `read_stamp`, `write_stamp`; add `import json` to the import block)
- Test: `tests/test_plugin_reconcile.py` (append a new section), `tests/test_plugin_requirements.py` (for `_strip_comment` — it lives beside the other plugin_cmd line-helper tests)

**Interfaces:**
- Consumes: `plugin_cmd._trailing_comment` regex convention (a `#` counts as a comment only at line start or after whitespace, so `#subdirectory=` URL fragments are NOT comments).
- Produces (later tasks rely on these exact names):
  - `plugin_cmd._strip_comment(line: str) -> str` — requirement portion, comment removed, stripped.
  - `plugin_reconcile.STAMP_NAME = "installed.json"`
  - `plugin_reconcile.read_stamp(volume_root: Path) -> dict[str, str] | None` — `None` when `volume_root` is not a writable dir (stamp unavailable → legacy behavior); `{}` when the file is missing or corrupt (re-adopt); else the parsed mapping.
  - `plugin_reconcile.write_stamp(volume_root: Path, stamp: dict[str, str]) -> None` — atomic tmp+`os.replace`, never raises (logs a warning on OSError).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plugin_requirements.py`:

```python
# --- _strip_comment -----------------------------------------------------------


def test_strip_comment_plain_line():
    from led_ticker.app.plugin_cmd import _strip_comment

    assert _strip_comment("led-ticker-pool==0.1.0") == "led-ticker-pool==0.1.0"


def test_strip_comment_removes_trailing_comment():
    from led_ticker.app.plugin_cmd import _strip_comment

    assert (
        _strip_comment("led-ticker-pool==0.1.0  # upgraded 2026-07-09, was @main")
        == "led-ticker-pool==0.1.0"
    )


def test_strip_comment_preserves_url_fragment():
    from led_ticker.app.plugin_cmd import _strip_comment

    line = "git+https://github.com/x/y@main#subdirectory=plugins/pool"
    assert _strip_comment(line) == line


def test_strip_comment_url_fragment_plus_real_comment():
    from led_ticker.app.plugin_cmd import _strip_comment

    assert (
        _strip_comment("git+https://github.com/x/y@v1#subdirectory=p/q  # note")
        == "git+https://github.com/x/y@v1#subdirectory=p/q"
    )
```

Append to `tests/test_plugin_reconcile.py`:

```python
# --- installed-state stamp ----------------------------------------------------


def test_read_stamp_unavailable_when_no_volume(tmp_path):
    import led_ticker.plugin_reconcile as r

    assert r.read_stamp(tmp_path / "nope") is None


def test_read_stamp_missing_file_is_empty_dict(tmp_path):
    import led_ticker.plugin_reconcile as r

    assert r.read_stamp(tmp_path) == {}


def test_stamp_roundtrip(tmp_path):
    import led_ticker.plugin_reconcile as r

    r.write_stamp(tmp_path, {"pool": "led-ticker-pool==0.1.0"})
    assert r.read_stamp(tmp_path) == {"pool": "led-ticker-pool==0.1.0"}
    assert (tmp_path / r.STAMP_NAME).exists()


def test_read_stamp_corrupt_file_is_empty_dict(tmp_path):
    import led_ticker.plugin_reconcile as r

    (tmp_path / r.STAMP_NAME).write_text("{not json")
    assert r.read_stamp(tmp_path) == {}


def test_read_stamp_non_dict_payload_is_empty_dict(tmp_path):
    import led_ticker.plugin_reconcile as r

    (tmp_path / r.STAMP_NAME).write_text('["a", "b"]')
    assert r.read_stamp(tmp_path) == {}


def test_read_stamp_non_string_values_is_empty_dict(tmp_path):
    import led_ticker.plugin_reconcile as r

    (tmp_path / r.STAMP_NAME).write_text('{"pool": 3}')
    assert r.read_stamp(tmp_path) == {}


def test_write_stamp_never_raises(tmp_path):
    import led_ticker.plugin_reconcile as r

    # Target is a FILE, so the stamp path is unwritable — must log, not raise.
    blocker = tmp_path / "vol"
    blocker.write_text("i am a file, not a dir")
    r.write_stamp(blocker, {"pool": "x"})  # no exception
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_plugin_requirements.py -k strip_comment tests/test_plugin_reconcile.py -k stamp -v`
Expected: FAIL — `AttributeError`/`ImportError` (`_strip_comment`, `read_stamp` not defined)

- [ ] **Step 3: Implement**

In `src/led_ticker/app/plugin_cmd.py`, directly below `_trailing_comment`:

```python
def _strip_comment(line: str) -> str:
    """The requirement portion of a manifest line, trailing comment removed.

    Comment detection mirrors ``_trailing_comment`` (pip semantics: ``#`` at
    line start or after whitespace), so a ``#subdirectory=`` / ``#egg=`` URL
    fragment survives intact. Used to compare manifest lines by their pip
    meaning — a provenance comment must never make two equal requirements
    look different (or reconcile would churn a reinstall on every boot).
    """
    match = re.search(r"(?:^|\s)#.*$", line)
    return (line[: match.start()] if match else line).strip()
```

In `src/led_ticker/plugin_reconcile.py`: add `import json` to the stdlib import block, then below `resolve_target` add:

```python
STAMP_NAME = "installed.json"


def read_stamp(volume_root: Path) -> dict[str, str] | None:
    """The installed-state stamp: {namespace: requirement_line-as-installed}.

    Returns None when ``volume_root`` is not a writable directory — no stamp
    home exists (bare-metal/local-venv target), so the caller falls back to
    the legacy ``_exact_pin`` drift check. Returns {} when the file is missing
    or unreadable/corrupt: every current namespace is then re-adopted at its
    current manifest line (no churn), which is both the fresh-volume migration
    AND the corrupt-recovery path. Never raises.
    """
    if not (volume_root.is_dir() and os.access(volume_root, os.W_OK)):
        return None
    path = volume_root / STAMP_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        _log.warning(
            "plugin reconcile: stamp %s unreadable (%s) — re-stamping from "
            "current state",
            path,
            e,
        )
        return {}
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        _log.warning(
            "plugin reconcile: stamp %s has unexpected shape — re-stamping", path
        )
        return {}
    return data


def write_stamp(volume_root: Path, stamp: dict[str, str]) -> None:
    """Atomically persist the stamp. Never raises — a stamp write failure only
    costs drift detection on the next boot, never the panel."""
    path = volume_root / STAMP_NAME
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(
            json.dumps(stamp, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(tmp, path)
    except OSError as e:
        _log.warning("plugin reconcile: could not write stamp %s: %s", path, e)
        tmp.unlink(missing_ok=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_plugin_requirements.py -k strip_comment tests/test_plugin_reconcile.py -k stamp -v`
Expected: 11 PASS

- [ ] **Step 5: Run the full affected files + lint, then commit**

Run: `uv run pytest tests/test_plugin_requirements.py tests/test_plugin_reconcile.py -q && uv run ruff check src tests && uv run ruff format --check src tests`
Expected: all pass

```bash
git add src/led_ticker/app/plugin_cmd.py src/led_ticker/plugin_reconcile.py tests/test_plugin_requirements.py tests/test_plugin_reconcile.py
git commit -m "feat(plugins): installed-state stamp primitives + _strip_comment"
```

---

### Task 2: Reconcile drift detection + stamp maintenance

**Files:**
- Modify: `src/led_ticker/plugin_reconcile.py` — inside `reconcile()`: read stamp after `compute_diff` (~line 425), gate the existing `_exact_pin` loop (~lines 439–466), adopt/drift per namespace, update stamp entries after successful install/uninstall, write once at end of pass.
- Test: `tests/test_plugin_reconcile.py`

**Interfaces:**
- Consumes: `read_stamp` / `write_stamp` / `STAMP_NAME` (Task 1), `plugin_cmd._strip_comment` (Task 1, imported lazily like the module's other plugin_cmd imports).
- Produces: behavioral contract only — a changed manifest line (comment-stripped) for a declared+installed namespace triggers reinstall; stamp reflects post-pass reality. Task 7 reads the same stamp file read-only.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plugin_reconcile.py`. These follow the file's existing convention: monkeypatch module attributes on `r`, drive `reconcile()` with a `tmp_path` manifest. The volume-target path needs `resolve_target` to return a volume target AND `ensure_volume_venv`/`apply_to_syspath` neutralized (mirror `test_reconcile_calls_ensure_volume_venv_for_volume_target`).

```python
def _volume_reconcile_env(tmp_path, monkeypatch, *, manifest_line, installed, stamped):
    """Shared setup for stamp-drift tests: a volume target rooted at tmp_path,
    one namespace 'pool' declared via `manifest_line`, `installed` dists, and
    an optional pre-seeded stamp. Returns the list pip-install calls append to."""
    import led_ticker.plugin_reconcile as r

    config = tmp_path / "config.toml"
    config.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text(manifest_line + "\n")
    monkeypatch.setattr(
        r,
        "resolve_target",
        lambda **k: r.Target("volume", str(tmp_path / "venv/bin/python"), None),
    )
    monkeypatch.setattr(r, "ensure_volume_venv", lambda venv_dir: None)
    monkeypatch.setattr(r, "apply_to_syspath", lambda target: None)
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: {"pool"})
    monkeypatch.setattr(
        r, "_declared_requirements", lambda p: {"pool": manifest_line.strip()}
    )
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: dict(installed))
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)
    monkeypatch.setattr(
        r, "_freeze_to_constraints", lambda py: (str(tmp_path / "c.txt"), 0)
    )
    (tmp_path / "c.txt").write_text("")
    installs = []
    monkeypatch.setattr(
        r,
        "_install_namespace",
        lambda ns, py, constraints=None, requirement_line=None: installs.append(
            (ns, requirement_line)
        )
        or 0,
    )
    monkeypatch.setattr(r, "_uninstall_dist", lambda d, py: 0)
    if stamped is not None:
        r.write_stamp(tmp_path, stamped)
    return installs


def test_reconcile_line_change_reinstalls(tmp_path, monkeypatch):
    """Stamped @v0.1.0, manifest now @v0.2.0 → reinstall under the new line."""
    import led_ticker.plugin_reconcile as r

    old = "git+https://github.com/x/plugins@pool-v0.1.0#subdirectory=plugins/pool"
    new = "git+https://github.com/x/plugins@pool-v0.2.0#subdirectory=plugins/pool"
    installs = _volume_reconcile_env(
        tmp_path,
        monkeypatch,
        manifest_line=new,
        installed={"pool": "led-ticker-pool"},
        stamped={"pool": old},
    )
    actions = r.reconcile(tmp_path / "config.toml", volume_root=tmp_path)
    assert ("pool", new) in installs
    assert any(a.namespace == "pool" and a.action == "installed" for a in actions)
    # Stamp now records the NEW line.
    assert r.read_stamp(tmp_path) == {"pool": new}


def test_reconcile_unchanged_line_no_churn(tmp_path, monkeypatch):
    """Same line stamped and declared → NO reinstall (the no-churn tripwire)."""
    import led_ticker.plugin_reconcile as r

    line = "git+https://github.com/x/plugins@main#subdirectory=plugins/pool"
    installs = _volume_reconcile_env(
        tmp_path,
        monkeypatch,
        manifest_line=line,
        installed={"pool": "led-ticker-pool"},
        stamped={"pool": line},
    )
    r.reconcile(tmp_path / "config.toml", volume_root=tmp_path)
    assert installs == []


def test_reconcile_comment_only_edit_no_churn(tmp_path, monkeypatch):
    """Adding a trailing comment to the line must not trigger a reinstall."""
    import led_ticker.plugin_reconcile as r

    spec = "led-ticker-pool==0.2.0"
    installs = _volume_reconcile_env(
        tmp_path,
        monkeypatch,
        manifest_line=f"{spec}  # upgraded 2026-07-09, was ==0.1.0",
        installed={"pool": "led-ticker-pool"},
        stamped={"pool": spec},
    )
    r.reconcile(tmp_path / "config.toml", volume_root=tmp_path)
    assert installs == []


def test_reconcile_missing_stamp_adopts_without_reinstall(tmp_path, monkeypatch):
    """No stamp file (migration / fresh volume): adopt current lines, no churn."""
    import led_ticker.plugin_reconcile as r

    line = "git+https://github.com/x/plugins@pool-v0.1.0#subdirectory=plugins/pool"
    installs = _volume_reconcile_env(
        tmp_path,
        monkeypatch,
        manifest_line=line,
        installed={"pool": "led-ticker-pool"},
        stamped=None,
    )
    r.reconcile(tmp_path / "config.toml", volume_root=tmp_path)
    assert installs == []
    assert r.read_stamp(tmp_path) == {"pool": line}


def test_reconcile_failed_install_keeps_old_stamp(tmp_path, monkeypatch):
    """pip failure on the new line → stamp keeps the OLD line so next boot retries."""
    import led_ticker.plugin_reconcile as r

    old = "led-ticker-pool==0.1.0"
    new = "led-ticker-pool==0.2.0"
    _volume_reconcile_env(
        tmp_path,
        monkeypatch,
        manifest_line=new,
        installed={"pool": "led-ticker-pool"},
        stamped={"pool": old},
    )
    monkeypatch.setattr(
        r,
        "_install_namespace",
        lambda ns, py, constraints=None, requirement_line=None: 1,
    )
    actions = r.reconcile(tmp_path / "config.toml", volume_root=tmp_path)
    assert any(a.namespace == "pool" and a.action == "failed" for a in actions)
    assert r.read_stamp(tmp_path) == {"pool": old}


def test_reconcile_uninstall_removes_stamp_entry(tmp_path, monkeypatch):
    """A successful uninstall drops the namespace from the stamp."""
    import led_ticker.plugin_reconcile as r

    config = tmp_path / "config.toml"
    config.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("# empty\n")
    monkeypatch.setattr(
        r,
        "resolve_target",
        lambda **k: r.Target("volume", str(tmp_path / "venv/bin/python"), None),
    )
    monkeypatch.setattr(r, "ensure_volume_venv", lambda venv_dir: None)
    monkeypatch.setattr(r, "apply_to_syspath", lambda target: None)
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: set())
    monkeypatch.setattr(r, "_declared_requirements", lambda p: {})
    monkeypatch.setattr(
        r, "installed_plugin_dists", lambda: {"pool": "led-ticker-pool"}
    )
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)
    monkeypatch.setattr(r, "_uninstall_dist", lambda d, py: 0)
    r.write_stamp(tmp_path, {"pool": "led-ticker-pool==0.1.0"})
    r.reconcile(config, volume_root=tmp_path)
    assert r.read_stamp(tmp_path) == {}


def test_reconcile_stampless_target_still_detects_pin_drift(tmp_path, monkeypatch):
    """Legacy path: no stamp home (default /data/plugins absent) → the _exact_pin
    check still catches ==pin drift, exactly as before this feature."""
    import led_ticker.plugin_reconcile as r

    config = tmp_path / "config.toml"
    config.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("led-ticker-pool==0.2.0\n")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: {"pool"})
    monkeypatch.setattr(
        r, "_declared_requirements", lambda p: {"pool": "led-ticker-pool==0.2.0"}
    )
    monkeypatch.setattr(
        r, "installed_plugin_dists", lambda: {"pool": "led-ticker-pool"}
    )
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)
    monkeypatch.setattr(r.importlib.metadata, "version", lambda dist: "0.1.0")
    monkeypatch.setattr(
        r, "_freeze_to_constraints", lambda py: (str(tmp_path / "c.txt"), 0)
    )
    (tmp_path / "c.txt").write_text("")
    installs = []
    monkeypatch.setattr(
        r,
        "_install_namespace",
        lambda ns, py, constraints=None, requirement_line=None: installs.append(ns)
        or 0,
    )
    monkeypatch.setattr(r, "_uninstall_dist", lambda d, py: 0)
    # volume_root deliberately left at a nonexistent path → read_stamp is None.
    r.reconcile(config, volume_root=tmp_path / "no-volume")
    assert installs == ["pool"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_plugin_reconcile.py -k "line_change or no_churn or adopts or keeps_old_stamp or removes_stamp or stampless" -v`
Expected: FAIL (drift not detected / stamp not written). `test_reconcile_stampless_target_still_detects_pin_drift` may already PASS (it exercises today's `_exact_pin` path) — that's fine, it's the regression guard.

- [ ] **Step 3: Implement in `reconcile()`**

In `src/led_ticker/plugin_reconcile.py`, replace the block between `to_install, to_uninstall = compute_diff(declared, installed)` and the `_log.info("plugin reconcile: declared=...")` call (currently the `for ns in sorted(declared & installed):` pin-drift loop) with:

```python
        to_install, to_uninstall = compute_diff(declared, installed)

        # Lazy import mirrors the module's other plugin_cmd imports.
        from led_ticker.app.plugin_cmd import _strip_comment  # noqa: PLC0415

        # ── Drift on ALREADY-installed plugins ────────────────────────────────
        # compute_diff is a pure namespace set-difference with no version/source
        # awareness. The STAMP records the exact manifest line each namespace was
        # installed from; any change to the (comment-stripped) line — a git ref
        # bump, a ==pin edit, a pypi<->git source switch — reinstalls in place.
        # A namespace with NO stamp entry (fresh volume, first boot after this
        # shipped, corrupt stamp) is ADOPTED at its current line without a
        # reinstall, so the feature arrives with zero churn.
        # Tripwires: test_reconcile_line_change_reinstalls,
        # test_reconcile_unchanged_line_no_churn,
        # test_reconcile_missing_stamp_adopts_without_reinstall.
        stamp = read_stamp(volume_root)
        stamp_dirty = False
        if stamp is not None:
            for ns in sorted(declared & installed):
                line = declared_reqs.get(ns)
                if not line:
                    continue
                current = _strip_comment(line)
                recorded = stamp.get(ns)
                if recorded is None:
                    stamp[ns] = current
                    stamp_dirty = True
                elif _strip_comment(recorded) != current:
                    _log.info(
                        "plugin reconcile: %s manifest line changed "
                        "(%s -> %s); reinstalling in place",
                        ns,
                        recorded,
                        current,
                    )
                    to_install.add(ns)
        else:
            # No stamp home (local-venv target): the legacy exact-==pin drift
            # check below is all a restart can reliably detect. Non-pinned
            # sources there still need `plugin upgrade` (which rewrites the
            # line) or a venv rebuild.
            for ns in sorted(declared & installed):
                line = declared_reqs.get(ns)
                if not line:
                    continue
                pin = _exact_pin(line)
                dist = installed_map.get(ns, ns)
                if pin is None:
                    _log.info(
                        "plugin reconcile: %s is declared+installed via a "
                        "non-pinned source (%s); cannot verify the source "
                        "changed on a restart — run `led-ticker plugin "
                        "upgrade %s` to refresh it",
                        ns,
                        line,
                        ns,
                    )
                    continue
                try:
                    current_version = importlib.metadata.version(dist)
                except importlib.metadata.PackageNotFoundError:
                    current_version = None
                if current_version is not None and current_version != pin:
                    _log.info(
                        "plugin reconcile: %s pin changed (installed %s -> "
                        "manifest %s); reinstalling in place",
                        ns,
                        current_version,
                        pin,
                    )
                    to_install.add(ns)
```

Then, in the install loop's SUCCESS branch (`else:` after `if code != 0:` — where `PluginAction(namespace=ns, action="installed")` is appended), add stamp maintenance:

```python
                    else:
                        for ns in covered:
                            actions.append(
                                PluginAction(namespace=ns, action="installed")
                            )
                            if stamp is not None:
                                stamp[ns] = _strip_comment(
                                    declared_reqs.get(ns, ns)
                                )
                                stamp_dirty = True
                        _log.info("plugin reconcile: installed %s", label)
```

In the uninstall loop's success branch (after `actions.append(PluginAction(namespace=ns, action="uninstalled"))`):

```python
                    if stamp is not None and stamp.pop(ns, None) is not None:
                        stamp_dirty = True
```

Finally, just before the `if any(a.action in ("installed", "uninstalled") for a in actions):` cache-invalidation block at the end of the try body:

```python
        if stamp is not None and stamp_dirty:
            write_stamp(volume_root, stamp)
```

- [ ] **Step 4: Run the full reconcile suite**

Run: `uv run pytest tests/test_plugin_reconcile.py -v`
Expected: ALL pass — the new tests AND every pre-existing test (including `test_reconcile_pin_change_on_installed_plugin` and `test_reconcile_unpinned_installed_plugin_not_reinstalled`, which run on the stampless path since the default `/data/plugins` doesn't exist in CI).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check src tests && uv run ruff format src tests`

```bash
git add src/led_ticker/plugin_reconcile.py tests/test_plugin_reconcile.py
git commit -m "feat(plugins): stamp-based manifest-line drift detection in reconcile"
```

---

### Task 3: Version + git-line parsing helpers (new module)

**Files:**
- Create: `src/led_ticker/app/plugin_upgrade.py`
- Test: Create `tests/test_plugin_upgrade.py`

**Interfaces:**
- Produces (Tasks 4–6 rely on these exact names):
  - `UpgradeError(Exception)` — message is user-facing.
  - `_parse_version(text: str) -> tuple[int, ...] | None` — `"1.2.3"` → `(1, 2, 3)`; anything not `^\d+(\.\d+)*$` → `None` (letters ⇒ pre-releases excluded by construction).
  - `_split_git_line(line: str) -> tuple[str, str | None, str | None]` — `(base_url_with_git+, ref, fragment)`.
  - `_join_git_line(base: str, ref: str, fragment: str | None) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plugin_upgrade.py`:

```python
"""Tests for the plugin upgrade resolver + verb (app/plugin_upgrade.py)."""

import pytest

from led_ticker.app import plugin_upgrade as up

# --- _parse_version -----------------------------------------------------------


def test_parse_version_basic():
    assert up._parse_version("0.2.0") == (0, 2, 0)
    assert up._parse_version("10.31") == (10, 31)


def test_parse_version_rejects_prerelease_and_garbage():
    assert up._parse_version("1.2.0rc1") is None
    assert up._parse_version("1.2.0-beta") is None
    assert up._parse_version("main") is None
    assert up._parse_version("") is None


def test_parse_version_orders_numerically_not_lexically():
    assert up._parse_version("0.10.0") > up._parse_version("0.9.9")


# --- git line split / join ----------------------------------------------------

MONOREPO = "git+https://github.com/JamesAwesome/led-ticker-plugins"


def test_split_git_line_full():
    base, ref, frag = up._split_git_line(
        f"{MONOREPO}@pool-v0.1.0#subdirectory=plugins/pool"
    )
    assert base == MONOREPO
    assert ref == "pool-v0.1.0"
    assert frag == "subdirectory=plugins/pool"


def test_split_git_line_no_ref():
    base, ref, frag = up._split_git_line(f"{MONOREPO}#subdirectory=plugins/pool")
    assert base == MONOREPO
    assert ref is None
    assert frag == "subdirectory=plugins/pool"


def test_split_git_line_no_fragment():
    base, ref, frag = up._split_git_line(f"{MONOREPO}@main")
    assert (base, ref, frag) == (MONOREPO, "main", None)


def test_split_git_line_ref_with_slash():
    # A ref may contain '/'; the '@' cut must happen after the URL path begins.
    base, ref, frag = up._split_git_line(f"{MONOREPO}@feature/foo")
    assert ref == "feature/foo"


def test_join_git_line_roundtrip():
    line = f"{MONOREPO}@pool-v0.2.0#subdirectory=plugins/pool"
    assert up._join_git_line(*up._split_git_line(line)) == line


def test_join_git_line_no_fragment():
    assert up._join_git_line(MONOREPO, "abc123", None) == f"{MONOREPO}@abc123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_plugin_upgrade.py -v`
Expected: FAIL — `ModuleNotFoundError: led_ticker.app.plugin_upgrade`

- [ ] **Step 3: Implement**

Create `src/led_ticker/app/plugin_upgrade.py`:

```python
"""Resolve "latest" for a manifest requirement line + the `plugin upgrade` verb.

Network-side counterpart of plugin_reconcile's stamp: the upgrade verb (CLI
`led-ticker plugin upgrade`, webui POST /api/store/upgrade) rewrites the
manifest line to the newest concrete pin; the boot reconcile then notices the
line changed and pip-reinstalls in place. This module NEVER runs on the boot
path — network calls are fine here, forbidden there.

Version compare is digit-tuple only (`^\\d+(\\.\\d+)*$`): stdlib-only (core
does not depend on `packaging`), and it excludes pre-release tags by
construction. Git tag convention: `<name>-vX.Y.Z` (see the docs-site plugins
page); `<name>` resolves subdirectory-basename → catalog-name → bare `v`.
"""

import re

_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")


class UpgradeError(Exception):
    """Resolution failed; str(e) is the user-facing reason. The manifest is
    never touched when this is raised."""


def _parse_version(text: str) -> tuple[int, ...] | None:
    """``"1.2.3"`` -> ``(1, 2, 3)``; None for anything else (incl. pre-releases)."""
    if not _VERSION_RE.match(text):
        return None
    return tuple(int(part) for part in text.split("."))


def _split_git_line(line: str) -> tuple[str, str | None, str | None]:
    """``git+https://host/o/r@ref#frag`` -> ``(git+https://host/o/r, ref, frag)``.

    The ``@`` cut happens after the URL path begins (a ref may contain ``/``,
    and ``user@host`` credentials must not be mistaken for a ref) — same rule
    as plugin_cmd._requirement_key.
    """
    spec, _, fragment = line.partition("#")
    spec = spec.strip()
    scheme = spec.find("//")
    path_start = spec.find("/", scheme + 2) if scheme != -1 else spec.find("/")
    at = spec.find("@", path_start) if path_start != -1 else spec.find("@")
    if at != -1:
        return spec[:at], spec[at + 1 :], fragment or None
    return spec, None, fragment or None


def _join_git_line(base: str, ref: str, fragment: str | None) -> str:
    """Inverse of ``_split_git_line`` for a concrete ref."""
    line = f"{base}@{ref}"
    if fragment:
        line += f"#{fragment}"
    return line
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_plugin_upgrade.py -v`
Expected: 9 PASS

- [ ] **Step 5: Lint + commit**

```bash
git add src/led_ticker/app/plugin_upgrade.py tests/test_plugin_upgrade.py
git commit -m "feat(plugins): version + git-line parsing helpers for upgrade resolver"
```

---

### Task 4: `resolve_latest` (PyPI JSON + git ls-remote)

**Files:**
- Modify: `src/led_ticker/app/plugin_upgrade.py`
- Test: `tests/test_plugin_upgrade.py`

**Interfaces:**
- Consumes: Task 3 helpers; `plugin_cmd._strip_comment`.
- Produces (Tasks 5–6 call exactly this):
  - `resolve_latest(line: str, *, catalog_name: str | None = None, fetch_json=None, run_git=None) -> str` — comment-stripped input line in, NEW comment-free line out (may equal the input ⇒ up to date). Raises `UpgradeError` on any failure. `fetch_json(package: str) -> dict` and `run_git(args: list[str]) -> str` are injection points; `None` selects the real network implementations.
  - Real impls (module-private, used as defaults): `_fetch_pypi_json(package)` (urllib, 15 s timeout), `_run_git(args)` (`subprocess.run(["git", *args], capture_output=True, text=True, timeout=30)`, raises `UpgradeError` on nonzero/timeout/missing binary).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plugin_upgrade.py`:

```python
# --- resolve_latest: pypi -----------------------------------------------------


def _pypi_fetcher(releases):
    """Fake fetch_json returning a minimal PyPI JSON payload."""

    def fetch(package):
        return {"releases": releases}

    return fetch


def test_resolve_latest_pypi_pinned_moves_to_newest():
    fetch = _pypi_fetcher(
        {
            "0.1.0": [{"yanked": False}],
            "0.2.0": [{"yanked": False}],
            "0.10.0": [{"yanked": False}],
        }
    )
    got = up.resolve_latest("led-ticker-pool==0.1.0", fetch_json=fetch)
    assert got == "led-ticker-pool==0.10.0"


def test_resolve_latest_pypi_unpinned_gets_pin():
    fetch = _pypi_fetcher({"0.3.0": [{"yanked": False}]})
    assert up.resolve_latest("led-ticker-pool", fetch_json=fetch) == (
        "led-ticker-pool==0.3.0"
    )


def test_resolve_latest_pypi_skips_yanked_and_prerelease_and_empty():
    fetch = _pypi_fetcher(
        {
            "0.2.0": [{"yanked": False}],
            "0.3.0": [{"yanked": True}],  # all files yanked
            "0.4.0rc1": [{"yanked": False}],  # prerelease (unparseable)
            "0.5.0": [],  # no files uploaded
        }
    )
    got = up.resolve_latest("led-ticker-pool==0.1.0", fetch_json=fetch)
    assert got == "led-ticker-pool==0.2.0"


def test_resolve_latest_pypi_no_candidates_raises():
    fetch = _pypi_fetcher({"0.4.0rc1": [{"yanked": False}]})
    with pytest.raises(up.UpgradeError):
        up.resolve_latest("led-ticker-pool==0.1.0", fetch_json=fetch)


def test_resolve_latest_pypi_fetch_failure_raises():
    def boom(package):
        raise up.UpgradeError("network down")

    with pytest.raises(up.UpgradeError, match="network down"):
        up.resolve_latest("led-ticker-pool==0.1.0", fetch_json=boom)


# --- resolve_latest: git ------------------------------------------------------

LS_REMOTE_TAGS = """\
aaa111\trefs/tags/baseball-v0.3.0
bbb222\trefs/tags/pool-v0.1.0
ccc333\trefs/tags/pool-v0.2.0
ddd444\trefs/tags/pool-v0.2.0^{}
eee555\trefs/tags/pool-v0.3.0rc1
"""


def _git_runner(tags_output, head_output="fff999\tHEAD\n"):
    calls = []

    def run(args):
        calls.append(args)
        if "--tags" in args:
            return tags_output
        return head_output

    run.calls = calls
    return run


def test_resolve_latest_git_bumps_ref_to_newest_matching_tag():
    run = _git_runner(LS_REMOTE_TAGS)
    got = up.resolve_latest(
        f"{MONOREPO}@pool-v0.1.0#subdirectory=plugins/pool", run_git=run
    )
    assert got == f"{MONOREPO}@pool-v0.2.0#subdirectory=plugins/pool"


def test_resolve_latest_git_prefix_from_subdirectory_basename():
    # Prefix comes from the subdirectory basename even when tracking a branch.
    run = _git_runner(LS_REMOTE_TAGS)
    got = up.resolve_latest(
        f"{MONOREPO}@main#subdirectory=plugins/pool", run_git=run
    )
    assert got == f"{MONOREPO}@pool-v0.2.0#subdirectory=plugins/pool"


def test_resolve_latest_git_prefix_from_catalog_name():
    # No subdirectory: fall back to the catalog entry name.
    run = _git_runner("abc\trefs/tags/pool-v0.9.0\n")
    got = up.resolve_latest(f"{MONOREPO}@main", catalog_name="pool", run_git=run)
    assert got == f"{MONOREPO}@pool-v0.9.0"


def test_resolve_latest_git_plain_v_tags_for_single_plugin_repo():
    run = _git_runner("abc\trefs/tags/v1.2.0\nxyz\trefs/tags/v1.10.0\n")
    got = up.resolve_latest("git+https://github.com/x/led-ticker-solo@main", run_git=run)
    assert got == "git+https://github.com/x/led-ticker-solo@v1.10.0"


def test_resolve_latest_git_no_tags_falls_back_to_branch_sha():
    run = _git_runner("", head_output="fff999\trefs/heads/main\n")
    got = up.resolve_latest(
        f"{MONOREPO}@main#subdirectory=plugins/pool", run_git=run
    )
    assert got == f"{MONOREPO}@fff999#subdirectory=plugins/pool"
    # SHA lookup asked for the branch the line was tracking.
    assert run.calls[-1][-1] == "main"


def test_resolve_latest_git_sha_fallback_empty_raises():
    run = _git_runner("", head_output="")
    with pytest.raises(up.UpgradeError):
        up.resolve_latest(f"{MONOREPO}@main", run_git=run)


def test_resolve_latest_rejects_editable_and_unknown_forms():
    with pytest.raises(up.UpgradeError):
        up.resolve_latest("-e git+https://github.com/x/y@main")
    with pytest.raises(up.UpgradeError):
        up.resolve_latest("https://example.com/wheel.whl")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_plugin_upgrade.py -k resolve_latest -v`
Expected: FAIL — `AttributeError: resolve_latest`

- [ ] **Step 3: Implement**

Append to `src/led_ticker/app/plugin_upgrade.py` (extend the import block with `import json`, `import subprocess`, `import urllib.error`, `import urllib.request`, `from pathlib import PurePosixPath`):

```python
_PYPI_TIMEOUT_S = 15
_GIT_TIMEOUT_S = 30


def _fetch_pypi_json(package: str) -> dict:
    """GET https://pypi.org/pypi/<package>/json. Raises UpgradeError."""
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        with urllib.request.urlopen(url, timeout=_PYPI_TIMEOUT_S) as resp:  # noqa: S310
            return json.load(resp)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise UpgradeError(f"could not query PyPI for {package!r}: {e}") from e


def _run_git(args: list[str]) -> str:
    """Run ``git <args>`` and return stdout. Raises UpgradeError on any failure
    (nonzero exit, timeout, git binary absent)."""
    try:
        proc = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
        )
    except FileNotFoundError as e:
        raise UpgradeError("git is not installed on this host") from e
    except subprocess.TimeoutExpired as e:
        raise UpgradeError(f"git {args[0]} timed out after {_GIT_TIMEOUT_S}s") from e
    if proc.returncode != 0:
        raise UpgradeError(
            f"git {args[0]} failed: {(proc.stderr or '').strip() or proc.returncode}"
        )
    return proc.stdout


def _pypi_package_name(line: str) -> str:
    """Package name from a pypi requirement line (name up to the first
    version/marker/extra delimiter) — mirrors plugin_cmd._requirement_key's
    pypi branch, but preserves case (PyPI URLs are case-insensitive anyway)."""
    name = line
    for delim in ("==", ">=", "<=", "~=", "!=", ">", "<", "[", ";", " "):
        idx = name.find(delim)
        if idx != -1:
            name = name[:idx]
    return name.strip()


def _latest_pypi(line: str, fetch_json) -> str:
    package = _pypi_package_name(line)
    data = fetch_json(package)
    releases = data.get("releases", {})
    best: tuple[int, ...] | None = None
    best_text: str | None = None
    for version_text, files in releases.items():
        parsed = _parse_version(version_text)
        if parsed is None:
            continue  # pre-release or unparseable
        if not files or all(f.get("yanked") for f in files):
            continue  # nothing installable
        if best is None or parsed > best:
            best, best_text = parsed, version_text
    if best_text is None:
        raise UpgradeError(f"no installable release of {package!r} found on PyPI")
    return f"{package}=={best_text}"


def _tag_prefixes(fragment: str | None, catalog_name: str | None) -> list[str]:
    """Candidate tag prefixes in resolution order (docs-site tag convention):
    subdirectory basename -> catalog name -> bare ``v`` (single-plugin repos)."""
    prefixes: list[str] = []
    if fragment:
        for part in fragment.split("&"):
            if part.startswith("subdirectory="):
                name = PurePosixPath(part.removeprefix("subdirectory=")).name
                if name:
                    prefixes.append(f"{name}-v")
    if catalog_name:
        prefixes.append(f"{catalog_name}-v")
    prefixes.append("v")
    return prefixes


def _latest_git(line: str, catalog_name: str | None, run_git) -> str:
    base, ref, fragment = _split_git_line(line)
    url = base.removeprefix("git+")
    tags: list[str] = []
    for out_line in run_git(["ls-remote", "--tags", url]).splitlines():
        _, _, refname = out_line.partition("\t")
        tag = refname.strip().removeprefix("refs/tags/").removesuffix("^{}")
        if tag:
            tags.append(tag)
    for prefix in _tag_prefixes(fragment, catalog_name):
        best: tuple[int, ...] | None = None
        best_tag: str | None = None
        for tag in tags:
            if not tag.startswith(prefix):
                continue
            parsed = _parse_version(tag.removeprefix(prefix))
            if parsed is None:
                continue
            if best is None or parsed > best:
                best, best_tag = parsed, tag
        if best_tag is not None:
            return _join_git_line(base, best_tag, fragment)
    # No convention-matching tags: pin the tip of the tracked branch (or HEAD).
    out = run_git(["ls-remote", url, ref or "HEAD"])
    sha = out.split()[0] if out.split() else ""
    if not sha:
        raise UpgradeError(
            f"no matching version tags and could not resolve {ref or 'HEAD'!r} "
            f"on {url}"
        )
    return _join_git_line(base, sha, fragment)


def resolve_latest(
    line: str,
    *,
    catalog_name: str | None = None,
    fetch_json=None,
    run_git=None,
) -> str:
    """The newest concrete pin for a (comment-stripped) manifest line.

    Returns a NEW comment-free line; equal to the input means already up to
    date. Raises UpgradeError with a user-facing reason on any failure — the
    caller must not have touched the manifest yet.
    """
    line = line.strip()
    if line.startswith("git+"):
        return _latest_git(line, catalog_name, run_git or _run_git)
    if line.startswith("-e ") or "://" in line:
        raise UpgradeError(
            f"don't know how to find the latest version of {line!r} — "
            "edit the manifest line by hand"
        )
    return _latest_pypi(line, fetch_json or _fetch_pypi_json)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_plugin_upgrade.py -v`
Expected: ALL pass (Task 3's 9 + these 12)

- [ ] **Step 5: Lint + commit**

```bash
git add src/led_ticker/app/plugin_upgrade.py tests/test_plugin_upgrade.py
git commit -m "feat(plugins): resolve_latest — PyPI JSON + git ls-remote tag resolution"
```

---

### Task 5: `cmd_upgrade` + CLI wiring

**Files:**
- Modify: `src/led_ticker/app/plugin_cmd.py` — add `comment: str | None = None` keyword to `_update_requirements` (~line 136)
- Modify: `src/led_ticker/app/plugin_upgrade.py` — add `cmd_upgrade`
- Modify: `src/led_ticker/app/cli.py` — `upgrade` subparser after the `uninstall` one (~line 260) + dispatch after the `uninstall` branch (~line 341)
- Test: `tests/test_plugin_upgrade.py`, plus one `_update_requirements` test in `tests/test_plugin_requirements.py`

**Interfaces:**
- Consumes: `resolve_latest` (Task 4); `plugin_cmd` helpers `_requirements_path`, `_dist_key`, `_find_requirement_lines`, `_update_requirements`, `_strip_comment`, `_config_warning`; `plugins_catalog.load_catalog`.
- Produces: `cmd_upgrade(target: str | None, *, config_path: Path, config_explicit: bool = True, all_plugins: bool = False, dry_run: bool = False, catalog: Catalog | None = None) -> int` (0 = ok/up-to-date, 1 = resolver failure, 2 = usage/manifest error). CLI: `led-ticker plugin upgrade <name>` / `led-ticker plugin upgrade --all` / `--dry-run`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plugin_requirements.py`:

```python
def test_update_requirements_comment_param_overrides_carry(tmp_path):
    """comment= writes the given provenance comment instead of carrying the old
    line's comment."""
    from led_ticker.app.plugin_cmd import _update_requirements

    path = tmp_path / "requirements-plugins.txt"
    path.write_text("led-ticker-pool==0.1.0  # old note\n")
    _update_requirements(
        path, "led-ticker-pool==0.2.0", comment="# upgraded 2026-07-09, was ==0.1.0"
    )
    assert path.read_text() == (
        "led-ticker-pool==0.2.0  # upgraded 2026-07-09, was ==0.1.0\n"
    )
```

Append to `tests/test_plugin_upgrade.py`:

```python
# --- cmd_upgrade --------------------------------------------------------------
from led_ticker.plugins_catalog import (
    Catalog,
    CatalogEntry,
    CatalogSource,
    PluginProvides,
)


def _pool_catalog():
    entry = CatalogEntry(
        name="pool",
        namespace="pool",
        summary="Pool.",
        homepage="",
        provides=PluginProvides(widgets=("pool.monitor",)),
        sources=(
            CatalogSource(
                type="git",
                url="https://github.com/JamesAwesome/led-ticker-plugins",
                ref="pool-v0.1.0",
                subdirectory="plugins/pool",
            ),
        ),
    )
    return Catalog(entries=(entry,))


def _manifest(tmp_path, text):
    config = tmp_path / "config.toml"
    config.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text(text)
    return config


def test_cmd_upgrade_rewrites_pin_with_provenance(tmp_path, monkeypatch, capsys):
    old = f"{MONOREPO}@pool-v0.1.0#subdirectory=plugins/pool"
    new = f"{MONOREPO}@pool-v0.2.0#subdirectory=plugins/pool"
    config = _manifest(tmp_path, old + "\n")
    monkeypatch.setattr(up, "resolve_latest", lambda line, **kw: new)
    code = up.cmd_upgrade(
        "pool", config_path=config, catalog=_pool_catalog()
    )
    assert code == 0
    text = (tmp_path / "requirements-plugins.txt").read_text()
    assert new in text
    assert "# upgraded" in text and "was" in text
    assert "restart" in capsys.readouterr().out.lower()


def test_cmd_upgrade_up_to_date_writes_nothing(tmp_path, monkeypatch, capsys):
    line = f"{MONOREPO}@pool-v0.2.0#subdirectory=plugins/pool"
    config = _manifest(tmp_path, line + "\n")
    monkeypatch.setattr(up, "resolve_latest", lambda ln, **kw: ln)
    before = (tmp_path / "requirements-plugins.txt").read_text()
    assert up.cmd_upgrade("pool", config_path=config, catalog=_pool_catalog()) == 0
    assert (tmp_path / "requirements-plugins.txt").read_text() == before
    assert "up to date" in capsys.readouterr().out.lower()


def test_cmd_upgrade_not_declared_is_error(tmp_path, capsys):
    config = _manifest(tmp_path, "# nothing declared\n")
    assert up.cmd_upgrade("pool", config_path=config, catalog=_pool_catalog()) == 2
    assert "not declared" in capsys.readouterr().err.lower()


def test_cmd_upgrade_resolver_failure_leaves_manifest(tmp_path, monkeypatch, capsys):
    old = f"{MONOREPO}@pool-v0.1.0#subdirectory=plugins/pool"
    config = _manifest(tmp_path, old + "\n")

    def boom(line, **kw):
        raise up.UpgradeError("no matching tags")

    monkeypatch.setattr(up, "resolve_latest", boom)
    assert up.cmd_upgrade("pool", config_path=config, catalog=_pool_catalog()) == 1
    assert (tmp_path / "requirements-plugins.txt").read_text() == old + "\n"
    assert "no matching tags" in capsys.readouterr().err


def test_cmd_upgrade_dry_run_writes_nothing(tmp_path, monkeypatch, capsys):
    old = f"{MONOREPO}@pool-v0.1.0#subdirectory=plugins/pool"
    new = f"{MONOREPO}@pool-v0.2.0#subdirectory=plugins/pool"
    config = _manifest(tmp_path, old + "\n")
    monkeypatch.setattr(up, "resolve_latest", lambda line, **kw: new)
    code = up.cmd_upgrade(
        "pool", config_path=config, catalog=_pool_catalog(), dry_run=True
    )
    assert code == 0
    assert (tmp_path / "requirements-plugins.txt").read_text() == old + "\n"
    out = capsys.readouterr().out
    assert "Dry run" in out and new in out


def test_cmd_upgrade_all_upgrades_every_line(tmp_path, monkeypatch):
    lines = [
        f"{MONOREPO}@pool-v0.1.0#subdirectory=plugins/pool",
        "led-ticker-crypto==0.1.0",
    ]
    config = _manifest(tmp_path, "\n".join(lines) + "\n")
    monkeypatch.setattr(
        up,
        "resolve_latest",
        lambda line, **kw: line.replace("0.1.0", "0.9.0"),
    )
    code = up.cmd_upgrade(
        None, config_path=config, catalog=_pool_catalog(), all_plugins=True
    )
    assert code == 0
    text = (tmp_path / "requirements-plugins.txt").read_text()
    assert "pool-v0.9.0" in text
    assert "led-ticker-crypto==0.9.0" in text


def test_cmd_upgrade_all_aggregates_failures(tmp_path, monkeypatch):
    lines = [
        f"{MONOREPO}@pool-v0.1.0#subdirectory=plugins/pool",
        "led-ticker-crypto==0.1.0",
    ]
    config = _manifest(tmp_path, "\n".join(lines) + "\n")

    def flaky(line, **kw):
        if "crypto" in line:
            raise up.UpgradeError("pypi down")
        return line.replace("0.1.0", "0.9.0")

    monkeypatch.setattr(up, "resolve_latest", flaky)
    code = up.cmd_upgrade(
        None, config_path=config, catalog=_pool_catalog(), all_plugins=True
    )
    assert code == 1  # partial failure
    text = (tmp_path / "requirements-plugins.txt").read_text()
    assert "pool-v0.9.0" in text  # the good one still upgraded
    assert "led-ticker-crypto==0.1.0" in text  # the bad one untouched
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_plugin_upgrade.py -k cmd_upgrade tests/test_plugin_requirements.py -k comment_param -v`
Expected: FAIL — `_update_requirements() got an unexpected keyword argument 'comment'` / `AttributeError: cmd_upgrade`

- [ ] **Step 3: Implement**

**(a)** In `plugin_cmd._update_requirements`, change the signature and comment-carry block:

```python
def _update_requirements(
    path: Path, requirement: str, *, comment: str | None = None
) -> str | None:
    """Add `requirement` to the requirements file, replacing any prior line for
    the same plugin. Preserves comments and unrelated lines — including a trailing
    inline comment on the line being replaced, which is carried onto the new line
    UNLESS ``comment`` is given (then the new line gets exactly that comment —
    the upgrade verb's provenance note replaces any stale annotation).
    Returns the replaced line (verbatim) when one was found, else None (appended)."""
    key = _requirement_key(requirement)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept: list[str] = []
    replaced_line: str | None = None
    new_line = f"{requirement}  {comment}" if comment else requirement
    for line in lines:
        stripped = line.strip()
        if (
            stripped
            and not stripped.startswith("#")
            and (_requirement_key(stripped) == key)
        ):
            replaced_line = line
            if comment is None:
                carried = _trailing_comment(line)
                if carried:
                    new_line = f"{requirement}  {carried}"
            continue  # drop the old line for this plugin
        kept.append(line)
    kept.append(new_line)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(kept).rstrip("\n") + "\n", encoding="utf-8")
    return replaced_line
```

**(b)** Append to `plugin_upgrade.py` (extend imports: `import datetime`, `import sys`, `from pathlib import Path`, `from led_ticker.plugins_catalog import Catalog, load_catalog`, and from `led_ticker.app.plugin_cmd import _config_warning, _dist_key, _find_requirement_lines, _requirement_key, _requirements_path, _strip_comment, _update_requirements`):

```python
_UPGRADE_HINT = (
    "The new version installs on next startup — run `docker compose restart` "
    "(no rebuild needed)."
)


def _catalog_name_for_key(key: str, catalog: Catalog) -> str | None:
    """The catalog entry NAME whose requirement dedup-key matches ``key`` —
    feeds the git tag-prefix convention. None for off-catalog lines."""
    for entry in catalog.entries:
        try:
            if _requirement_key(entry.requirement()) == key:
                return entry.name
        except ValueError:
            continue
    return None


def _upgrade_one_line(
    req_path: Path, old_line: str, catalog: Catalog, *, dry_run: bool
) -> int:
    """Resolve + rewrite ONE manifest line. Returns 0 (upgraded or up to date)
    or 1 (resolver failure; manifest untouched, reason printed)."""
    old_spec = _strip_comment(old_line)
    key = _requirement_key(old_spec)
    try:
        new_spec = resolve_latest(
            old_spec, catalog_name=_catalog_name_for_key(key, catalog)
        )
    except UpgradeError as e:
        print(f"{old_spec}: {e}", file=sys.stderr)
        return 1
    if new_spec == old_spec:
        print(f"{old_spec} is already up to date.")
        return 0
    if dry_run:
        print("Dry run — no changes made.")
        print(f"  would replace: {old_spec}")
        print(f"  with:          {new_spec}")
        return 0
    today = datetime.date.today().isoformat()
    provenance = f"# upgraded {today}, was {old_spec}"
    try:
        _update_requirements(req_path, new_spec, comment=provenance)
    except OSError as e:
        print(f"could not write {req_path}: {e}", file=sys.stderr)
        return 2
    print(f"Upgraded: {old_spec} -> {new_spec}")
    return 0


def cmd_upgrade(
    target: str | None,
    *,
    config_path: Path,
    config_explicit: bool = True,
    all_plugins: bool = False,
    dry_run: bool = False,
    catalog: Catalog | None = None,
) -> int:
    """Rewrite manifest line(s) to the latest version (no pip — the boot
    reconcile installs the change). Exit codes: 0 ok/up-to-date, 1 resolver
    failure (any, under --all), 2 usage/manifest error."""
    catalog = catalog or load_catalog()
    req_path = _requirements_path(config_path, config_explicit)
    config_warning = _config_warning(req_path)

    if all_plugins:
        if not req_path.exists():
            print(f"{req_path} does not exist — nothing to upgrade.", file=sys.stderr)
            return 2
        lines = [
            line
            for line in req_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not lines:
            print("No plugins declared — nothing to upgrade.")
            return 0
        worst = 0
        upgraded_any = False
        for line in lines:
            code = _upgrade_one_line(req_path, line, catalog, dry_run=dry_run)
            worst = max(worst, code)
            upgraded_any = upgraded_any or code == 0
        if config_warning:
            print(config_warning, file=sys.stderr)
        if not dry_run and upgraded_any:
            print(_UPGRADE_HINT)
        return worst

    assert target is not None  # cli enforces target XOR --all
    key = _dist_key(target, catalog)
    matches = _find_requirement_lines(req_path, key)
    if not matches:
        print(
            f"{target!r} is not declared in {req_path} — add it first "
            f"(led-ticker plugin add {target}).",
            file=sys.stderr,
        )
        return 2
    code = _upgrade_one_line(req_path, matches[-1], catalog, dry_run=dry_run)
    if config_warning:
        print(config_warning, file=sys.stderr)
    if code == 0 and not dry_run:
        print(_UPGRADE_HINT)
    return code
```

**(c)** In `cli.py`, after the `puninstall` parser block (~line 260):

```python
    pupgrade = plugin_sub.add_parser(
        "upgrade",
        help=(
            "Rewrite a plugin's manifest line to the latest version "
            "(installs on next restart)"
        ),
    )
    pupgrade.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Catalog name (e.g. pool) or pip spec; omit with --all",
    )
    pupgrade.add_argument(
        "--all",
        action="store_true",
        dest="all_plugins",
        help="Upgrade every plugin declared in requirements-plugins.txt",
    )
    _add_dry_run_arg(pupgrade)
    _add_config_arg(pupgrade)
```

And in the dispatch chain, after the `if pc == "uninstall":` block:

```python
        if pc == "upgrade":
            if args.all_plugins == (args.target is not None):
                print(
                    "specify exactly one of: a plugin name, or --all",
                    file=sys.stderr,
                )
                sys.exit(2)
            from led_ticker.app.plugin_upgrade import cmd_upgrade  # noqa: PLC0415

            sys.exit(
                cmd_upgrade(
                    args.target,
                    config_path=args.config,
                    config_explicit=config_explicit,
                    all_plugins=args.all_plugins,
                    dry_run=args.dry_run,
                )
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_plugin_upgrade.py tests/test_plugin_requirements.py -v`
Expected: ALL pass

- [ ] **Step 5: Smoke the CLI help + lint + commit**

Run: `uv run led-ticker plugin upgrade --help`
Expected: usage text shows `target`, `--all`, `--dry-run`, `--config`

Run: `uv run pytest tests/ -q -x --no-cov -k "plugin or cli"` then `uv run ruff check src tests && uv run ruff format src tests`

```bash
git add src/led_ticker/app/plugin_cmd.py src/led_ticker/app/plugin_upgrade.py src/led_ticker/app/cli.py tests/test_plugin_upgrade.py tests/test_plugin_requirements.py
git commit -m "feat(plugins): led-ticker plugin upgrade verb (manifest rewrite, no pip)"
```

---

### Task 6: Webui `POST /api/store/upgrade`

**Files:**
- Modify: `src/led_ticker/webui/__init__.py` — `upgrade_handler` after `remove_handler` (~line 464), route registration next to the other store routes (~line 470)
- Test: `tests/test_webui_app.py`

**Interfaces:**
- Consumes: `resolve_latest` / `UpgradeError` (Task 4, lazy import), `_update_manifest_atomic`, `manifest_lock`, `_load_catalog_lazy`, `_build_store`, `_fresh_inner_status`, `plugin_cmd._requirement_key` / `_strip_comment` / `_find_requirement_lines` (lazy imports — webui stays rgbmatrix-pure).
- Produces: `POST /api/store/upgrade` with JSON `{"namespace": "<ns>"}`. Responses: 200 store-entry + `"upgraded": {"from": ..., "to": ...}`; 200 `{"up_to_date": true, ...}`; 403 no token; 400 bad body/unknown plugin; 404 not declared; 409 manifest changed concurrently; 502 resolver failure; 500 write failure. NOT in `_OPEN_PATHS` (auth middleware applies).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_webui_app.py` (reuse the file's `_client` helper and fake-catalog pattern; the git-source fake entry matches `test_install_known_namespace_writes_manifest`):

```python
# ---------------------------------------------------------------------------
# POST /api/store/upgrade — plugin store upgrade
# ---------------------------------------------------------------------------


def _upgrade_fixtures(monkeypatch, *, resolved=None, resolve_error=None):
    """Patch catalog + store + resolver for upgrade_handler tests. Returns the
    fake catalog entry."""
    import led_ticker.webui as webui_mod
    from led_ticker.app import plugin_upgrade
    from led_ticker.plugins_catalog import (
        Catalog,
        CatalogEntry,
        CatalogSource,
        PluginProvides,
    )

    fake_entry = CatalogEntry(
        name="pool",
        namespace="pool",
        summary="Pool.",
        homepage="",
        provides=PluginProvides(widgets=("pool.monitor",)),
        sources=(
            CatalogSource(
                type="git",
                url="https://github.com/JamesAwesome/led-ticker-plugins",
                ref="pool-v0.1.0",
                subdirectory="plugins/pool",
            ),
        ),
    )
    monkeypatch.setattr(
        webui_mod, "_load_catalog_lazy", lambda: Catalog(entries=(fake_entry,))
    )
    monkeypatch.setattr(
        webui_mod,
        "_build_store",
        lambda **kw: {"plugins": [{"namespace": "pool", "state": "active"}]},
    )

    def fake_resolve(line, **kwargs):
        if resolve_error is not None:
            raise plugin_upgrade.UpgradeError(resolve_error)
        return resolved if resolved is not None else line

    monkeypatch.setattr(plugin_upgrade, "resolve_latest", fake_resolve)
    return fake_entry


OLD_LINE = (
    "git+https://github.com/JamesAwesome/led-ticker-plugins@pool-v0.1.0"
    "#subdirectory=plugins/pool"
)
NEW_LINE = (
    "git+https://github.com/JamesAwesome/led-ticker-plugins@pool-v0.2.0"
    "#subdirectory=plugins/pool"
)


async def test_upgrade_rewrites_manifest_line(tmp_path, monkeypatch):
    _upgrade_fixtures(monkeypatch, resolved=NEW_LINE)
    client = await _client(tmp_path, token="s3cret")
    manifest = tmp_path / "requirements-plugins.txt"
    manifest.write_text(OLD_LINE + "\n")
    try:
        resp = await client.post(
            "/api/store/upgrade",
            json={"namespace": "pool"},
            headers={"X-Web-Token": "s3cret"},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["upgraded"] == {"from": OLD_LINE, "to": NEW_LINE}
        text = manifest.read_text()
        assert NEW_LINE in text
        assert "# upgraded" in text
        assert OLD_LINE + "\n" not in text
    finally:
        await client.close()


async def test_upgrade_up_to_date_is_noop(tmp_path, monkeypatch):
    _upgrade_fixtures(monkeypatch)  # resolver echoes the line back
    client = await _client(tmp_path, token="s3cret")
    manifest = tmp_path / "requirements-plugins.txt"
    manifest.write_text(OLD_LINE + "\n")
    try:
        resp = await client.post(
            "/api/store/upgrade",
            json={"namespace": "pool"},
            headers={"X-Web-Token": "s3cret"},
        )
        assert resp.status == 200
        assert (await resp.json())["up_to_date"] is True
        assert manifest.read_text() == OLD_LINE + "\n"
        # No backup written for a no-op.
        assert not manifest.with_suffix(manifest.suffix + ".bak").exists()
    finally:
        await client.close()


async def test_upgrade_requires_token(tmp_path, monkeypatch):
    _upgrade_fixtures(monkeypatch, resolved=NEW_LINE)
    client = await _client(tmp_path, token="s3cret")
    (tmp_path / "requirements-plugins.txt").write_text(OLD_LINE + "\n")
    try:
        resp = await client.post("/api/store/upgrade", json={"namespace": "pool"})
        assert resp.status == 401  # auth middleware (route is not open)
    finally:
        await client.close()


async def test_upgrade_no_token_configured_is_disabled(tmp_path, monkeypatch):
    _upgrade_fixtures(monkeypatch, resolved=NEW_LINE)
    client = await _client(tmp_path)  # no token at all
    try:
        resp = await client.post("/api/store/upgrade", json={"namespace": "pool"})
        assert resp.status == 403
        assert "disabled" in (await resp.json())["error"]
    finally:
        await client.close()


async def test_upgrade_unknown_namespace(tmp_path, monkeypatch):
    _upgrade_fixtures(monkeypatch, resolved=NEW_LINE)
    client = await _client(tmp_path, token="s3cret")
    try:
        resp = await client.post(
            "/api/store/upgrade",
            json={"namespace": "nope"},
            headers={"X-Web-Token": "s3cret"},
        )
        assert resp.status == 400
    finally:
        await client.close()


async def test_upgrade_not_declared_is_404(tmp_path, monkeypatch):
    _upgrade_fixtures(monkeypatch, resolved=NEW_LINE)
    client = await _client(tmp_path, token="s3cret")  # no manifest at all
    try:
        resp = await client.post(
            "/api/store/upgrade",
            json={"namespace": "pool"},
            headers={"X-Web-Token": "s3cret"},
        )
        assert resp.status == 404
    finally:
        await client.close()


async def test_upgrade_resolver_failure_is_502_manifest_untouched(
    tmp_path, monkeypatch
):
    _upgrade_fixtures(monkeypatch, resolve_error="no matching tags")
    client = await _client(tmp_path, token="s3cret")
    manifest = tmp_path / "requirements-plugins.txt"
    manifest.write_text(OLD_LINE + "\n")
    try:
        resp = await client.post(
            "/api/store/upgrade",
            json={"namespace": "pool"},
            headers={"X-Web-Token": "s3cret"},
        )
        assert resp.status == 502
        assert "no matching tags" in (await resp.json())["error"]
        assert manifest.read_text() == OLD_LINE + "\n"
    finally:
        await client.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_webui_app.py -k upgrade -v`
Expected: FAIL — 404 (route not registered)

- [ ] **Step 3: Implement**

In `src/led_ticker/webui/__init__.py`, after `remove_handler`:

```python
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
            _find_requirement_lines,
            _requirement_key,
            _strip_comment,
        )

        req_key = _requirement_key(entry.requirement())
        manifest_path = config_path.parent / "requirements-plugins.txt"

        current_lines = _find_requirement_lines(manifest_path, req_key)
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

        provenance = (
            f"# upgraded {datetime.date.today().isoformat()}, was {old_spec}"
        )

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
                    and _requirement_key(stripped) == req_key
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
        )
        plugin_entry = next(
            (
                p
                for p in store_payload.get("plugins", [])
                if p["namespace"] == namespace
            ),
            {"namespace": namespace},
        )
        plugin_entry["upgraded"] = {"from": old_spec, "to": new_spec}
        return web.json_response(plugin_entry)
```

Register the route next to the other store routes:

```python
    app.router.add_post("/api/store/upgrade", upgrade_handler)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_webui_app.py -k upgrade -v` then the guard suites: `uv run pytest tests/test_webui_app.py tests/test_webui_purity.py -q`
Expected: ALL pass (purity test confirms no rgbmatrix import leaked in)

- [ ] **Step 5: Lint + commit**

```bash
git add src/led_ticker/webui/__init__.py tests/test_webui_app.py
git commit -m "feat(webui): POST /api/store/upgrade — resolve latest + rewrite manifest pin"
```

---

### Task 7: Store state `restart_to_upgrade` + Upgrade button

**Files:**
- Modify: `src/led_ticker/webui/store.py` — optional `stamp` param on `build_store`; new state; pending count; `_INSTALLED_STATES`
- Modify: `src/led_ticker/webui/__init__.py` — read the stamp (read-only) in `store_handler` / `install_handler` / `remove_handler` / `upgrade_handler` call sites via one helper
- Modify: `src/led_ticker/webui/static/index.html` — badge, Upgrade button, `storeAction("upgrade", ...)`
- Test: `tests/test_webui_store.py`, `tests/test_webui_app.py` (one HTML smoke assert)

**Interfaces:**
- Consumes: `plugin_reconcile.read_stamp` semantics via a NEW read-only reader (the webui's plugin volume mount is `:ro`, so `read_stamp`'s `os.W_OK` gate would return None — mirror the `apply_volume_visibility` precedent and gate on existence only). `plugin_cmd._find_requirement_lines`, `_strip_comment`.
- Produces:
  - `store.build_store(..., stamp: dict[str, str] | None = None)` — when a declared+stamped entry's manifest line (comment-stripped) differs from its stamp entry, state becomes `"restart_to_upgrade"` (counted pending). `None` stamp = feature-off, zero behavior change.
  - `webui._read_stamp_readonly(volume_root: Path = Path("/data/plugins")) -> dict[str, str] | None` — never raises; `None` when absent/unreadable.
  - UI: `Upgrade` button on declared rows; `restart_to_upgrade` badge "Restart to upgrade".

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_webui_store.py` (follow that file's existing build_store test conventions — check its imports/fixtures when implementing; the tests below assume a fake catalog entry + manifest file in tmp_path like the file's other tests):

```python
def test_store_restart_to_upgrade_when_stamp_differs(tmp_path, monkeypatch):
    """Declared+active entry whose manifest line ≠ stamped line → pending upgrade."""
    from led_ticker.webui.store import build_store

    catalog = _fake_catalog()  # reuse the file's existing fake-catalog helper
    entry = catalog.entries[0]
    manifest = tmp_path / "requirements-plugins.txt"
    new_line = entry.requirement().replace("v0.1.0", "v0.2.0")
    manifest.write_text(new_line + "  # upgraded 2026-07-09\n")
    config = tmp_path / "config.toml"
    config.write_text("")
    status = {"plugins": [{"namespace": entry.namespace}]}

    payload = build_store(
        manifest_path=manifest,
        config_path=config,
        status=status,
        token_configured=True,
        catalog=catalog,
        stamp={entry.namespace: entry.requirement()},  # old line stamped
    )
    row = next(p for p in payload["plugins"] if p["namespace"] == entry.namespace)
    assert row["state"] == "restart_to_upgrade"
    assert payload["pending_count"] == 1


def test_store_stamp_match_stays_active(tmp_path):
    from led_ticker.webui.store import build_store

    catalog = _fake_catalog()
    entry = catalog.entries[0]
    manifest = tmp_path / "requirements-plugins.txt"
    manifest.write_text(entry.requirement() + "\n")
    config = tmp_path / "config.toml"
    config.write_text("")
    status = {"plugins": [{"namespace": entry.namespace}]}

    payload = build_store(
        manifest_path=manifest,
        config_path=config,
        status=status,
        token_configured=True,
        catalog=catalog,
        stamp={entry.namespace: entry.requirement()},
    )
    row = next(p for p in payload["plugins"] if p["namespace"] == entry.namespace)
    assert row["state"] == "active"
    assert payload["pending_count"] == 0


def test_store_no_stamp_is_behavior_unchanged(tmp_path):
    from led_ticker.webui.store import build_store

    catalog = _fake_catalog()
    entry = catalog.entries[0]
    manifest = tmp_path / "requirements-plugins.txt"
    manifest.write_text(entry.requirement() + "\n")
    config = tmp_path / "config.toml"
    config.write_text("")
    status = {"plugins": [{"namespace": entry.namespace}]}

    payload = build_store(
        manifest_path=manifest,
        config_path=config,
        status=status,
        token_configured=True,
        catalog=catalog,
        stamp=None,
    )
    row = next(p for p in payload["plugins"] if p["namespace"] == entry.namespace)
    assert row["state"] == "active"


def test_redact_anonymous_coarsens_restart_to_upgrade():
    from led_ticker.webui.store import redact_anonymous

    payload = {
        "display_online": True,
        "pending_count": 1,
        "auth_required": True,
        "plugins": [
            {
                "namespace": "pool",
                "state": "restart_to_upgrade",
                "in_use_by": [{"section": "s", "type": "pool.monitor"}],
                "removable": True,
            }
        ],
    }
    out = redact_anonymous(payload)
    assert out["plugins"][0]["state"] == "installed"
    assert out["pending_count"] == 0
```

NOTE: if `tests/test_webui_store.py` has no `_fake_catalog` helper, add one at the top of the new test section modeled on the file's existing catalog construction (a single git-source `CatalogEntry` with `ref="pool-v0.1.0"`, `subdirectory="plugins/pool"`, namespace `pool`) — read the file first and reuse whatever equivalent exists.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_webui_store.py -k "restart_to_upgrade or stamp" -v`
Expected: FAIL — `build_store() got an unexpected keyword argument 'stamp'`

- [ ] **Step 3: Implement store.py**

In `build_store`: add `stamp: dict[str, str] | None = None` to the signature and docstring. Import `_find_requirement_lines` and `_strip_comment` from `led_ticker.app.plugin_cmd` (module already imports from plugin_cmd — top-level is fine, store.py is rgbmatrix-pure). In the per-entry loop, after the existing `state` assignment:

```python
        # Pending upgrade: manifest line rewritten (by `plugin upgrade` / the
        # webui Upgrade button) but the boot reconcile hasn't installed it yet.
        # The stamp records the line-as-installed; a declared entry whose
        # current (comment-stripped) manifest line differs is waiting on a
        # restart. Only overrides the "everything looks fine" state — a
        # restart_to_activate/restart_to_remove entry already shows a pending
        # badge of its own.
        if state == "active" and stamp is not None and ns in stamp:
            lines = _find_requirement_lines(manifest_path, entry_key[ns])
            if lines and _strip_comment(lines[-1]) != _strip_comment(stamp[ns]):
                state = "restart_to_upgrade"
```

Add `"restart_to_upgrade"` to `_PENDING_STATES` (the pending_count tuple) and to `_INSTALLED_STATES` (anonymous redaction coarsens it to "installed").

- [ ] **Step 4: Implement the webui plumbing**

In `src/led_ticker/webui/__init__.py`, add at module level (near `_build_store`):

```python
def _read_stamp_readonly(
    volume_root: Path = Path("/data/plugins"),
) -> dict[str, str] | None:
    """The reconcile stamp, if readable — for the Store's restart_to_upgrade
    badge. The webui mounts the plugin volume :ro, so plugin_reconcile's
    read_stamp (which gates on os.W_OK, mirroring the install target) would
    return None here; this reader gates on EXISTENCE only, like
    apply_volume_visibility. Never raises; None = no badge, never an error."""
    path = volume_root / "installed.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        return None
    return data
```

Pass `stamp=_read_stamp_readonly()` in `store_handler`'s `_build_store(...)` call (the GET path renders badges; the install/remove/upgrade handlers' rebuilt-entry responses may also pass it for consistency — do so, it's one kwarg).

- [ ] **Step 5: Implement the UI**

In `src/led_ticker/webui/static/index.html`:

1. `storeBadge` — after the `restart_to_activate` case:

```js
  if (state === "restart_to_upgrade") return '<span class="store-badge badge-restart">Restart to upgrade</span>';
```

2. `renderStore` — treat the new state as declared (`const isDeclared = p.state === "active" || p.state === "restart_to_activate" || p.state === "restart_to_upgrade";`), and inside the `else if (isDeclared)` branch, BEFORE the Remove button html, add an Upgrade button (auth-gated like Remove, never gated on `removable` — upgrading doesn't orphan siblings, it moves the shared line for all of them):

```js
      const upgradeLabel = pack ? `Upgrade ${esc(pack)} pack` : "Upgrade";
      actionHtml = `<button class="store-btn install" ${needsAuth ? "disabled" : ""}
        data-action="upgrade" data-ns="${esc(p.namespace)}" data-pack="${esc(pack)}" data-pack-members="${esc(packMembers.join(","))}"
        ${needsAuth ? 'title="Enter your token to upgrade plugins"' : ""}>${upgradeLabel}</button>` + actionHtml;
```

(Concatenate so both Upgrade and Remove render in the action area; keep Remove's existing logic untouched.)

3. `storeAction` — route the new action and handle its two success shapes:

```js
async function storeAction(action, namespace) {
  const method = action === "remove" ? "DELETE" : "POST";
  const url = action === "install" ? "/api/store/install"
    : action === "upgrade" ? "/api/store/upgrade"
    : "/api/store/remove";
```

and in the success path (after the existing error handling), before refreshing:

```js
    const body = await r.json();
    if (action === "upgrade") {
      if (body.up_to_date) {
        alert(`${namespace} is already up to date.`);
      } else if (body.upgraded) {
        alert(`Upgraded ${namespace}:\n${body.upgraded.from}\n  → ${body.upgraded.to}\nRestart the display to apply.`);
      }
    }
    loadStore();
```

Match the surrounding code's existing style for error display (it already has a 409 banner path — extend its condition to show the upgrade 502/409 error text via the same mechanism rather than inventing a new one; read the full `storeAction` body before editing).

4. The pack confirm in `renderStore`'s click handler currently derives its verb from `install`/`remove` — extend: `const verb = btn.dataset.action === "install" ? "Installs" : btn.dataset.action === "upgrade" ? "Upgrades" : "Removes";`

- [ ] **Step 6: Run the suites + smoke assert**

Add to `tests/test_webui_app.py` next to the existing `assert "/api/store/install" in html` (~line 877): `assert "/api/store/upgrade" in html`.

Run: `uv run pytest tests/test_webui_store.py tests/test_webui_app.py -q`
Expected: ALL pass

- [ ] **Step 7: Lint + commit**

```bash
git add src/led_ticker/webui/store.py src/led_ticker/webui/__init__.py src/led_ticker/webui/static/index.html tests/test_webui_store.py tests/test_webui_app.py
git commit -m "feat(webui): Upgrade button + restart_to_upgrade store state"
```

---

### Task 8: Docs + CLAUDE.md invariants + full-suite gate

**Files:**
- Modify: `docs/site/src/content/docs/plugins/index.mdx` — new "Upgrading plugins" section (declarative model, the verb, the web button, the tag convention `<name>-vX.Y.Z`, `@main` lines get pinned on first upgrade)
- Modify: `docs/site/src/content/docs/reference/cli.mdx` — `plugin upgrade` entry (`<name>`/`--all`/`--dry-run`, exit codes, "no pip — installs on restart")
- Modify: `docs/plugin-system.md` — stamp mechanics (`/data/plugins/installed.json`, adopt-on-missing, comment-stripped comparison, failure semantics)
- Modify: `CLAUDE.md` — in the Plugin invariants section, one new bullet
- Test: full suite

**Interfaces:** none — prose only. Follow `docs/DOCS-STYLE.md` for the docs-site pages.

- [ ] **Step 1: Write the docs-site sections**

Read `docs/DOCS-STYLE.md` first, then add to `plugins/index.mdx` (match the page's existing heading depth and voice) a section covering:

- Upgrading is declarative: `led-ticker plugin upgrade pool` (or the Store's Upgrade button) rewrites the `requirements-plugins.txt` line to the newest version; the change installs on the next restart — same flow as install/remove, no volume reset.
- Where "newest" comes from: PyPI for `pypi` lines; for git lines, tags matching `<name>-vX.Y.Z` (name = the `#subdirectory=` basename, falling back to the catalog name, then bare `vX.Y.Z`); a branch-tracking line with no matching tags gets pinned to the branch-tip commit.
- A `@main` line becomes a pinned line on its first upgrade (reproducible rebuilds); the old value is kept in a `# upgraded <date>, was <old>` comment.
- `--all` and `--dry-run`.

Add to `reference/cli.mdx` a `plugin upgrade` block alongside the existing `plugin add`/`remove` entries.

- [ ] **Step 2: Write the CLAUDE.md bullet**

In the "Plugin invariants" section of `CLAUDE.md`, after the **Install:** bullet:

```markdown
- **Upgrade:** declarative — `plugin upgrade` (CLI) / `POST /api/store/upgrade` (webui) rewrite the manifest line to the latest pin (resolver: PyPI JSON / `git ls-remote --tags`, convention `<name>-vX.Y.Z`); boot reconcile detects the line change via the installed-state stamp (`/data/plugins/installed.json`, `{namespace: line-as-installed}`, comment-stripped comparison) and pip-reinstalls in place. NEVER add network calls to the reconcile/boot path — resolution happens only in CLI/webui context. A namespace missing from the stamp is ADOPTED at its current line (no churn); the stamp updates only on pip success (failed upgrade retries next boot). Tripwires: `test_reconcile_line_change_reinstalls`, `test_reconcile_unchanged_line_no_churn`, `test_reconcile_missing_stamp_adopts_without_reinstall` (`tests/test_plugin_reconcile.py`).
```

- [ ] **Step 3: Update `docs/plugin-system.md`**

Add a "Upgrades and the installed-state stamp" subsection documenting: stamp path + shape, adopt-on-missing/corrupt, `_strip_comment` comparison, stamp-unavailable fallback to `_exact_pin` on local-venv targets, webui's read-only stamp read for the `restart_to_upgrade` badge, and the resolver's failure → manifest-untouched guarantee.

- [ ] **Step 4: Full-suite gate**

Run: `make test`
Expected: full suite green (1438+ tests + the ~40 new ones).

Run: `uv run pyright`
Expected: clean (pre-push requirement).

If the docs site has a local check available (nvm — verify node/pnpm on PATH first, `source ~/.nvm/nvm.sh` if needed): `make docs-lint` or the repo's docs check target from the Makefile.
Expected: clean; skip with a note in the commit message if node tooling is unavailable.

- [ ] **Step 5: Commit**

```bash
git add docs/ CLAUDE.md
git commit -m "docs(plugins): upgrade verb, tag convention, installed-state stamp invariants"
```

---

## Self-Review (performed at plan-writing time)

1. **Spec coverage:** stamp + drift (Tasks 1–2 ✓), migration/no-churn/corrupt (Task 1–2 tests ✓), resolver PyPI+git+SHA fallback+prefix order (Tasks 3–4 ✓), CLI verb + `--all` + provenance comment + up-to-date no-op + failure-before-write (Task 5 ✓), webui endpoint with token gate / 409 conflict / 502 resolver / restart flow (Task 6 ✓), shared packages (existing group-install covers reconcile; upgrade rewrites the one shared line by key — exercised implicitly since `_dist_key`/`_requirement_key` collapse siblings; UI pack confirm extended in Task 7 ✓), end-to-end behavioral test (Task 2's `test_reconcile_line_change_reinstalls` seeds manifest+stamp disagreement and runs `reconcile()` with stubbed pip ✓), docs + tag convention published (Task 8 ✓). Spec's "retire `_exact_pin`" refined to "gate to stampless targets" — flagged in the header for the reviewer.
2. **Placeholder scan:** no TBDs; Task 7's `_fake_catalog` and `storeAction` notes direct the implementer to read-and-reuse existing in-file helpers rather than leaving a gap — the fallback construction is specified inline.
3. **Type consistency:** `read_stamp/write_stamp(volume_root: Path)`, `resolve_latest(line, *, catalog_name, fetch_json, run_git) -> str`, `UpgradeError`, `cmd_upgrade(target, *, config_path, config_explicit, all_plugins, dry_run, catalog) -> int`, `_strip_comment` in plugin_cmd — used with the same names/signatures in every task that consumes them.
