"""`python -m tools.film.cli` — deploy / aim / record / restore / clip / session.

Exit codes: 0 ok; 1 refused, mismatch, no slate, incomplete loop, runtime
failure (message on stderr); 2 usage, device or tool missing.
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from tools.film.analyze import BBox, IncompleteLoopError, NoSlateError
from tools.film.camera import SMALLSIGN_SHELF, CameraPreset, aim
from tools.film.clip import ClipSettings, CountMismatch, clip_footage
from tools.film.manifest import ManifestError
from tools.film.record import (
    DEFAULT_DEVICE,
    DEFAULT_FPS,
    DEFAULT_SIZE,
    DeviceNotFound,
    list_devices,
    record,
)
from tools.film.runner import Runner, SubprocessRunner, ToolMissing
from tools.film.sign import DeployRefused, RestoreRefused, deploy, restore

DEFAULT_HOST = "smallsign"


def default_runner() -> Runner:
    return SubprocessRunner()


def _bbox(text: str) -> BBox:
    parts = text.split(":")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        raise argparse.ArgumentTypeError("crop must be x:y:w:h (integers)")
    x, y, w, h = (int(p) for p in parts)
    return BBox(x, y, w, h)


def _names(text: str) -> set[str]:
    return {n for n in text.split(",") if n}


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="film", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser(
        "deploy", help="back up the sign's config and deploy a filming config"
    )
    d.add_argument("config", type=Path)
    d.add_argument("--host", default=DEFAULT_HOST)
    d.add_argument("--restore-first", action="store_true")
    d.add_argument("--brightness", type=int)

    a = sub.add_parser(
        "aim", help="point and zoom the Insta360 Link at the sign (uvcc via npx)"
    )
    a.add_argument("--pan", type=int, default=SMALLSIGN_SHELF.pan, help="arc-seconds")
    a.add_argument("--tilt", type=int, default=SMALLSIGN_SHELF.tilt, help="arc-seconds")
    a.add_argument("--zoom", type=int, default=SMALLSIGN_SHELF.zoom, help="100-400")
    wb = a.add_mutually_exclusive_group()
    wb.add_argument(
        "--wb", type=int, default=SMALLSIGN_SHELF.white_balance, help="kelvin, locked"
    )
    wb.add_argument("--auto-wb", action="store_true", help="set white balance to auto")
    a.add_argument("--focus", type=int, help="0-100, locked (default: set auto)")
    a.add_argument("--device", default=DEFAULT_DEVICE)

    r = sub.add_parser("record", help="record the webcam to an mp4")
    r.add_argument("out", type=Path)
    r.add_argument("--seconds", type=float, default=60.0)
    r.add_argument("--device", default=DEFAULT_DEVICE)
    r.add_argument("--size", default=DEFAULT_SIZE)
    r.add_argument("--fps", type=int, default=DEFAULT_FPS)
    r.add_argument("--list-devices", action="store_true")

    s = sub.add_parser("restore", help="restore the sign's pre-filming config")
    s.add_argument("--host", default=DEFAULT_HOST)
    s.add_argument("--force", action="store_true")

    c = sub.add_parser("clip", help="cut footage into cropped GIFs by slate detection")
    c.add_argument("src", type=Path)
    c.add_argument("manifest", type=Path)
    c.add_argument("out_dir", type=Path)
    c.add_argument("--crop", type=_bbox, help="x:y:w:h in analysis (320-wide) pixels")
    c.add_argument("--take", type=int, default=1)
    c.add_argument(
        "--mp4", type=_names, default=set(), help="names that also get an mp4"
    )
    c.add_argument(
        "--hero", type=_names, default=set(), help="names with the 4 MB hero budget"
    )
    c.add_argument(
        "--full-frame", action="store_true", help="mp4s use the whole camera frame"
    )
    c.add_argument(
        "--mp4-only", action="store_true", help="skip the GIFs (YouTube loop)"
    )
    c.add_argument(
        "--slate-threshold",
        type=float,
        default=180.0,
        help="crop-mean luma a slate must exceed",
    )
    c.add_argument(
        "--change-threshold",
        type=int,
        default=60,
        help="per-pixel max-min marking the panel",
    )
    c.add_argument(
        "--bright-threshold",
        type=int,
        default=245,
        help="per-pixel max a panel pixel must reach (the slate)",
    )
    c.add_argument(
        "--dark-threshold",
        type=int,
        default=80,
        help="per-pixel min a panel pixel must fall to (unlit content)",
    )

    e = sub.add_parser("session", help="deploy, record, restore")
    e.add_argument("config", type=Path)
    e.add_argument("out", type=Path)
    e.add_argument("--seconds", type=float, required=True)
    e.add_argument("--host", default=DEFAULT_HOST)
    e.add_argument("--brightness", type=int)
    e.add_argument("--device", default=DEFAULT_DEVICE)
    e.add_argument(
        "--aim", action="store_true", help="run `aim` (shelf preset) before recording"
    )
    return p


def _preset(args: argparse.Namespace) -> CameraPreset:
    return CameraPreset(
        pan=args.pan,
        tilt=args.tilt,
        zoom=args.zoom,
        white_balance=None if args.auto_wb else args.wb,
        focus=args.focus,
    )


def _state_line(state: dict[str, object]) -> str:
    pt = state.get("absolute_pan_tilt")
    pan, tilt = pt if isinstance(pt, list) and len(pt) == 2 else ("?", "?")
    return (
        f"camera: pan={pan} tilt={tilt} zoom={state.get('absolute_zoom')} "
        f"wb={state.get('white_balance_temperature')} "
        f"focus={'auto' if state.get('auto_focus') else state.get('absolute_focus')}"
    )


def _run(args: argparse.Namespace, runner: Runner) -> int:
    now = datetime.now(UTC)
    if args.cmd == "deploy":
        state = deploy(
            args.host,
            args.config,
            runner,
            now=now,
            restore_first=args.restore_first,
            brightness=args.brightness,
        )
        print(f"deployed {args.config} to {args.host}; backup {state.get('bak')}")
    elif args.cmd == "aim":
        print(_state_line(aim(_preset(args), runner, device=args.device)))
    elif args.cmd == "record":
        if args.list_devices:
            for name in list_devices(runner):
                print(name)
            return 0
        out = record(
            args.device, args.out, args.seconds, runner, size=args.size, fps=args.fps
        )
        print(f"recorded {out}")
    elif args.cmd == "restore":
        bak = restore(args.host, runner, now=now, force=args.force)
        if bak:
            print(f"restored {args.host} from {bak}")
    elif args.cmd == "clip":
        written = clip_footage(
            args.src,
            args.manifest,
            args.out_dir,
            runner=runner,
            crop=args.crop,
            take=args.take,
            mp4_names=args.mp4,
            hero_budget_names=args.hero,
            settings=ClipSettings(),
            full_frame=args.full_frame,
            gif=not args.mp4_only,
            slate_threshold=args.slate_threshold,
            change_threshold=args.change_threshold,
            bright_threshold=args.bright_threshold,
            dark_threshold=args.dark_threshold,
        )
        print(f"{len(written)} file(s) written to {args.out_dir}")
    elif args.cmd == "session":
        if args.aim:  # before deploy: a camera failure must leave the sign untouched
            print(_state_line(aim(SMALLSIGN_SHELF, runner, device=args.device)))
        try:
            deploy(args.host, args.config, runner, now=now, brightness=args.brightness)
        except DeployRefused:
            raise  # nothing was changed on the sign
        except Exception:
            restore(
                args.host, runner, now=datetime.now(UTC)
            )  # deploy mutated, then failed
            raise
        try:
            record(args.device, args.out, args.seconds, runner)
        finally:
            restore(args.host, runner, now=datetime.now(UTC))
        print(f"session done: {args.out}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args, default_runner())
    except (ToolMissing, DeviceNotFound) as exc:
        print(f"film: {exc}", file=sys.stderr)
        return 2
    except (
        DeployRefused,
        RestoreRefused,
        CountMismatch,
        NoSlateError,
        IncompleteLoopError,
        ManifestError,
        TimeoutError,
        RuntimeError,
        FileNotFoundError,
        ValueError,
    ) as exc:
        print(f"film: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
