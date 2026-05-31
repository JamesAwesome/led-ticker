"""Tripwire: every run_monitor_loop spawn must go through spawn_tracked so the
task is strongly referenced. A bare asyncio.create_task(run_monitor_loop(...))
can be garbage-collected mid-flight (see test_http_server_task_survives_gc).
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "led_ticker"


def test_no_bare_create_task_for_run_monitor_loop():
    offenders = []
    for f in SRC.rglob("*.py"):
        if re.search(r"asyncio\.create_task\(\s*run_monitor_loop", f.read_text()):
            offenders.append(str(f.relative_to(SRC)))
    assert not offenders, (
        "use spawn_tracked(run_monitor_loop(...)), not asyncio.create_task — "
        f"offenders: {offenders}"
    )
