# Smallsign Filming (PR 1: tooling + filming configs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `tools/film/` (deploy a filming config to the smallsign, record the Insta360 Link with ffmpeg, restore the sign, cut footage into cropped GIFs/mp4 by slate detection) plus the three committed filming configs and a runbook, so the filming sessions (PR 2) are one command each.

**Architecture:** A small stdlib-only Python package under `tools/` in the `tools/gif_plan` style: every shell-out (`ffmpeg`, `ssh`, `scp`) goes through one injectable `Runner` so tests never touch hardware. Frame analysis decodes footage to low-res grayscale via ffmpeg `rawvideo` and does slate/crop detection in pure Python. A thin argparse CLI fronts five Make targets. Filming configs live in `docs/site/filming/` and carry `# film: <name>` comments that the clip tool zips with detected segments.

**Tech Stack:** Python 3.14 (stdlib: argparse, subprocess, hashlib, json, re, tomllib, dataclasses), ffmpeg (Homebrew, already present), ssh/scp to host `smallsign`, Pillow only for contact sheets (already a core dep). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-17-smallsign-filming-design.md`

## Global Constraints

- **Ask James before touching the webcam or the sign.** Any step that records from the Insta360 (`film record`, Task 2 step 4b, Task 8) or changes the sign (`film deploy`, `film restore`, `docker restart`) runs only after James has said go for that specific step in this session, so he can prepare and is not interrupted. Never run these unattended, from a subagent, or as part of a test. The fake-runner tests are the only automated path through this code.
- Branch + PR; do the work in a `git worktree` sibling, never on the main checkout. `uv run pyright` before push (not part of `make test`).
- No `from __future__ import annotations` anywhere (Python 3.14 / PEP 649 rule).
- `tools/film/` must not import `led_ticker` (build tool; stays out of `--cov=src/`). Exception: the config-validation test in Task 7 may import `led_ticker.validate`.
- Sign facts: host alias `smallsign`, repo at `~/led-ticker`, config at `~/led-ticker/config/config.toml` (root-owned; `smallsign` has passwordless sudo), container `led-ticker`, webui sidecar `led-ticker-webui` is running, status snapshot at `/run/led-ticker/status.json` inside the container with keys `started_at` (epoch float) and `swap_count` (int). Core `v4.34.0`, `led-ticker-flair==0.24.0`.
- Camera: avfoundation device name `Insta360 Link`; UVC modes top out at `3840x2160@30`; use `-framerate 30`. Record 4K by default, `--size 1920x1080` fallback.
- Filming configs: smallsign `[display]` = `rows = 16`, `cols = 32`, `chain_length = 5`, `gpio_slowdown = 2`, `hardware_mapping = "adafruit-hat"`, `hot_reload = true`, fixed `brightness` (60 until the Task 8 ladder says otherwise), **no** `[display.schedule]`, `[busy_light] enabled = false`. Only core + flair features; curated 8×8 emoji only; no `[[source]] type = "image"`; no file paths.
- Copy/palette: `docs/DOCS-STYLE.md` §6 Firebird Yoga, phoenix palette flame `[255, 92, 38]`, ember `[214, 40, 57]`, amber `[255, 183, 3]`, cream `[255, 244, 214]`, dusk `[99, 60, 138]`. Hero closing card text is exactly `FIREBIRD YOGA · docs.ledticker.dev`. Never pure white text (cream instead) except on the slate; never pure black.
- Slate = a section that paints the whole panel white, cut in and out: `bg_color = [255, 255, 255]`, `hold_time = 1.0` for every inner slate and **`hold_time = 2.0` for the top-of-playlist slate (the loop anchor; the clip tool tells loops apart by slate length)**, `transition = "cut"`, one `message` widget `text = "."`, `font_color = [255, 255, 255]`. Global `[transitions] between_sections = "cut"`; content sections use `widget_transition` (not `transition`) so their entry stays a cut unless they set `entry_transition` explicitly.
- Output budget: feature GIF ≤ 2.5 MB, hero GIF ≤ 4 MB; yield order width 800 → 640, then fps 20 → 15; after that, report, don't trim silently.
- Every `## `-commented Makefile target needs a `| \`make <target>\` | ... |` row in `docs/site/src/content/docs/reference/cli.mdx` (drift test `tests/test_docs_cli_make_targets_drift.py`) and a `.PHONY` entry.

## Review Focus

1. **Camera not aimed at the sign** (no bright rectangle in any frame): `film clip` must fail with "no slate found" and must not guess a crop. Test in Task 2.
2. **Wrong device name** (`--device "Insta 360"`): `film record` must print the avfoundation device list and exit 2, not hang on ffmpeg. Test in Task 4.
3. **Previous session crashed, film-bak still on the sign**: `film deploy` must refuse unless `--restore-first`, so the real backup is never overwritten by a filming config. Test in Task 5.
4. **Someone edited the sign's config mid-session** (webui editor or hand edit): `film restore` must refuse when the sign's `config.toml` sha256 no longer matches what deploy wrote, unless `--force`. Test in Task 5.
5. **Recording starts mid-loop** (deploy waits for the display, so the first slate is always missed; features run into a second loop): clips must be anchored to the 2.0 s slate, never zipped by raw order, or every GIF is named one slot late with the count check passing. Test in Task 2.
6. **Static bright objects in frame** (the blown-out window, white plush touching the panel): the crop must come from pixels that *change* over time, not from bright pixels in one frame. Test in Task 2.
7. **Segment/name count mismatch** (a slate dropped because exposure clipped, or a section added without a `# film:` comment): `film clip` must print both lists and exit non-zero, never write misnamed GIFs. Test in Task 3.

---

### Task 1: Package scaffold, Runner, manifest parser

**Files:**
- Create: `tools/film/__init__.py` (empty), `tools/film/conftest.py`, `tools/film/runner.py`, `tools/film/manifest.py`
- Modify: `pyproject.toml` (`testpaths` add `"tools/film"`), `.gitignore` (add `captures/`)
- Test: `tools/film/test_runner.py`, `tools/film/test_manifest.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Result: argv: list[str]; returncode: int; stdout: bytes; stderr: bytes
  class Runner(Protocol):
      def run(self, argv: list[str], *, input: bytes | None = None, timeout: float | None = None) -> Result: ...
  class SubprocessRunner:  # real; wraps subprocess.run(capture_output=True); FileNotFoundError -> ToolMissing(argv[0])
  class FakeRunner:        # tests; FakeRunner(responses: dict[str, Result | Callable[[list[str]], Result]]) keyed by argv[0]; records .calls: list[list[str]]
  class ToolMissing(RuntimeError): tool: str   # message: "<tool> not found on PATH; brew install <tool>" for ffmpeg/ffprobe, plain for ssh/scp
  def ssh_argv(host: str, remote_cmd: str) -> list[str]   # ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, remote_cmd]
  def scp_argv(local: Path, host: str, remote_path: str) -> list[str]
  # manifest.py
  def film_names(toml_text: str) -> list[str]   # for each `[[playlist.section]]` header line carrying a trailing `# film: <name>` comment, in file order; name regex [a-z0-9][a-z0-9-]*; ManifestError(ValueError) on malformed or duplicate; slates (no comment) skipped
  class ManifestError(ValueError)
  ```

- [ ] **Step 1: Write the failing tests**

```python
# tools/film/test_runner.py
def test_fake_runner_records_calls_and_returns_response():
    r = FakeRunner({"echo": Result(["echo"], 0, b"hi", b"")})
    out = r.run(["echo", "x"])
    assert out.stdout == b"hi" and r.calls == [["echo", "x"]]

def test_fake_runner_unknown_tool_raises_tool_missing():
    with pytest.raises(ToolMissing) as e: FakeRunner({}).run(["nope"])
    assert e.value.tool == "nope"

def test_subprocess_runner_missing_binary_is_tool_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ToolMissing) as e: SubprocessRunner().run(["ffmpeg", "-version"])
    assert "brew install ffmpeg" in str(e.value)

def test_ssh_argv_uses_batch_mode():
    assert ssh_argv("smallsign", "ls")[:3] == ["ssh", "-o", "BatchMode=yes"]

# tools/film/test_manifest.py
def test_names_in_order_skipping_slates():
    text = '[[playlist.section]]\nmode="slideshow"\n[[playlist.section]]  # film: color-rainbow\n[[playlist.section]]\n[[playlist.section]] # film: border-bands\n'
    assert film_names(text) == ["color-rainbow", "border-bands"]

def test_duplicate_name_is_error():
    with pytest.raises(ManifestError): film_names('[[playlist.section]] # film: a\n[[playlist.section]] # film: a\n')

def test_bad_name_is_error():
    with pytest.raises(ManifestError): film_names('[[playlist.section]] # film: Bad_Name\n')

def test_no_names_returns_empty():
    assert film_names('[display]\nrows = 16\n') == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tools/film/test_runner.py tools/film/test_manifest.py -v`
Expected: FAIL (import errors)

- [ ] **Step 3: Implement `tools/film/runner.py`, `manifest.py` (one compiled regex `^\s*\[\[playlist\.section\]\]\s*#\s*film:\s*(\S+)\s*$`, MULTILINE) and `conftest.py`** (copy the `_REPO_ROOT` sys.path shim from `tools/gif_plan/conftest.py`, minus the `__future__` import). Add `"tools/film"` to `testpaths`; add `captures/` to `.gitignore`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tools/film -v`
Expected: 8 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/film pyproject.toml .gitignore
git commit -m "feat(film): scaffold tools/film with Runner and # film: manifest parser"
```

---

### Task 2: Frame decode, slate/crop analysis, loop anchoring

**Files:**
- Create: `tools/film/analyze.py`
- Test: `tools/film/test_analyze.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class GrayFrames: width: int; height: int; fps: float; frames: list[bytes]   # each len == width*height, 8-bit gray
  @dataclass(frozen=True)
  class BBox: x: int; y: int; w: int; h: int
  @dataclass(frozen=True)
  class Interval: start: int; end: int   # frame indices, half-open

  def decode_gray(path: Path, runner: Runner, *, fps: float = 10.0, width: int = 320) -> GrayFrames
      # ffmpeg -i path -vf fps=<fps>,scale=<width>:-2,format=gray -f rawvideo -  ; height from ffprobe (-show_entries stream=width,height) scaled proportionally, even
  def mean_luma(frame: bytes, bbox: BBox | None, width: int) -> float
  def find_slates(luma: list[float], fps: float, *, threshold: float = 180.0, min_seconds: float = 0.5) -> list[Interval]
  def find_panel_bbox(frames: list[bytes], width: int, height: int, *, threshold: int = 60, pad_frac: float = 0.04) -> BBox
      # per-pixel (max - min) across frames; bbox of pixels whose range > threshold (the panel changes, the room does not),
      # padded by pad_frac of its own w/h each side, clamped to frame; NoSlateError if nothing changes
  def segments_between(slates: list[Interval], total_frames: int) -> list[Interval]
      # content between consecutive slates; the tail after the last slate is NOT a segment
  class NoSlateError(RuntimeError)
  ANCHOR_SECONDS = 1.5   # slates at least this long are loop anchors (the 2.0 s top slate); inner slates are 1.0 s
  @dataclass(frozen=True)
  class Footage: frames: GrayFrames; bbox: BBox; slates: list[Interval]; anchors: list[Interval]; segments: list[Interval]
  class IncompleteLoopError(RuntimeError)   # "recording holds N complete loop(s); take=K needs K+1 anchors — record longer"
  def analyze_footage(frames: GrayFrames, *, crop: BBox | None = None, take: int = 1) -> Footage
      # 1) bbox = crop or find_panel_bbox(frames.frames, ...) (NoSlateError → message "no slate found; is the camera aimed at the sign?")
      # 2) luma per frame inside bbox → find_slates; anchors = slates with length >= ANCHOR_SECONDS*fps
      # 3) need len(anchors) >= take + 1 else IncompleteLoopError; loop = anchors[take-1] .. anchors[take]
      # 4) segments = segments_between([anchors[take-1]] + inner slates within the loop + [anchors[take]], total)
  ```
- Consumes: `Runner`, `ToolMissing` from Task 1.

- [ ] **Step 1: Write the failing tests** (synthetic frames: helper `gray(w, h, fill)` → bytes; `rect(frame, w, bbox, value)` paints a rectangle)

```python
def test_find_slates_two_slates_min_length():
    luma = [10]*20 + [250]*10 + [30]*40 + [250]*2 + [30]*8 + [250]*10 + [20]*10   # fps 10 → 0.2 s blip ignored
    assert find_slates(luma, fps=10.0) == [Interval(20, 30), Interval(80, 90)]

def test_find_slates_none_raises():
    with pytest.raises(NoSlateError): find_slates([10]*50, fps=10.0)

def test_segments_between_excludes_tail():
    assert segments_between([Interval(0, 10), Interval(50, 60), Interval(90, 100)], 120) == [Interval(10, 50), Interval(60, 90)]

def test_find_panel_bbox_ignores_static_bright_objects_and_pads():
    base = gray(320, 180, 0); rect(base, 320, BBox(0, 0, 60, 180), 255)      # blown-out window, static
    rect(base, 320, BBox(90, 80, 10, 10), 240)                              # white plush touching the panel, static
    f1 = bytes(base); rect(f1, 320, BBox(100, 80, 100, 10), 255)            # panel lit (slate)
    f2 = bytes(base); rect(f2, 320, BBox(100, 80, 100, 10), 20)             # panel showing dark content
    b = find_panel_bbox([f1, f2, f1], 320, 180)
    assert (b.x, b.w) == (96, 108) and b.y == 80 and b.h == 10   # pad 4% of w=4px each side; h pad rounds to 0

def test_find_panel_bbox_nothing_changes_raises():
    with pytest.raises(NoSlateError): find_panel_bbox([gray(32, 18, 200)] * 5, 32, 18)

def test_mean_luma_inside_bbox_only():
    f = gray(10, 10, 0); rect(f, 10, BBox(0, 0, 5, 10), 200)
    assert mean_luma(f, BBox(0, 0, 5, 10), 10) == 200.0 and mean_luma(f, None, 10) == 100.0

def test_decode_gray_builds_ffmpeg_argv_and_splits_frames():
    probe = Result(["ffprobe"], 0, b"1920,1080\n", b"")
    raw = Result(["ffmpeg"], 0, bytes(320*180*3), b"")
    runner = FakeRunner({"ffprobe": probe, "ffmpeg": raw})
    frames = decode_gray(Path("x.mp4"), runner)
    assert (frames.width, frames.height, len(frames.frames)) == (320, 180, 3)
    assert "fps=10.0,scale=320:-2,format=gray" in " ".join(runner.calls[-1])

  ANCHOR_SECONDS = 1.5   # slates at least this long are loop anchors (the 2.0 s top slate); inner slates are 1.0 s
  @dataclass(frozen=True)
  class Footage: frames: GrayFrames; bbox: BBox; slates: list[Interval]; anchors: list[Interval]; segments: list[Interval]
  class IncompleteLoopError(RuntimeError)   # "recording holds N complete loop(s); take=K needs K+1 anchors — record longer"
  def analyze_footage(frames: GrayFrames, *, crop: BBox | None = None, take: int = 1) -> Footage
      # 1) bbox = crop or find_panel_bbox(frames.frames, ...) (NoSlateError → message "no slate found; is the camera aimed at the sign?")
      # 2) luma per frame inside bbox → find_slates; anchors = slates with length >= ANCHOR_SECONDS*fps
      # 3) need len(anchors) >= take + 1 else IncompleteLoopError; loop = anchors[take-1] .. anchors[take]
      # 4) segments = segments_between([anchors[take-1]] + inner slates within the loop + [anchors[take]], total)
  ```

- [ ] **Step 1: Write the failing tests**

def test_analyze_footage_no_bright_frame_is_no_slate_error():
    frames = GrayFrames(32, 18, 10.0, [gray(32, 18, 40)] * 30)
    with pytest.raises(NoSlateError, match="aimed"): analyze_footage(frames)

def _loop(content, slate, anchor_frames=20, inner_frames=10):   # fps 10: anchor 2.0 s, inner 1.0 s; two content segments A, B per loop
    return [slate]*anchor_frames + [content]*20 + [slate]*inner_frames + [content]*30

def test_analyze_footage_recording_starts_mid_loop_anchors_to_long_slate():
    dark = gray(32, 18, 10); slate = bytes(dark); rect(slate, 32, BBox(4, 6, 24, 4), 255)
    content = bytes(dark); rect(content, 32, BBox(4, 6, 24, 4), 90)
    frames = GrayFrames(32, 18, 10.0, [content]*15 + [slate]*10 + [content]*30 + _loop(content, slate) + _loop(content, slate) + [slate]*20)
    f = analyze_footage(frames)                       # starts inside B of a previous loop
    assert f.bbox == BBox(3, 6, 26, 4)                # 4% of w=24 → 1 px pad each side; h pad rounds to 0
    assert len(f.anchors) == 3
    assert f.segments == [Interval(75, 95), Interval(105, 135)]   # A then B of the FIRST complete loop, 20 and 30 frames

def test_analyze_footage_take_2_selects_second_loop():
    f = analyze_footage(frames_from_previous_test(), take=2)
    assert f.segments == [Interval(155, 175), Interval(185, 215)]

def test_analyze_footage_incomplete_loop_is_error():
    frames = GrayFrames(32, 18, 10.0, [slate]*20 + [content]*20 + [slate]*10 + [content]*30)   # one anchor only
    with pytest.raises(IncompleteLoopError, match="record longer"): analyze_footage(frames)

def test_analyze_footage_explicit_crop_skips_detection():
    f = analyze_footage(frames_from_previous_test(), crop=BBox(0, 0, 32, 18))
    assert f.bbox == BBox(0, 0, 32, 18)
```

- [ ] **Step 2: Run to verify fail** → FAIL
- [ ] **Step 3: Implement `tools/film/analyze.py`** (including `analyze_footage`). `find_slates`: run-length over `luma > threshold`, keep runs `>= round(min_seconds*fps)`. `find_panel_bbox`: two bytearrays (running max, running min) over all frames, then one pass tracking min/max x,y where `max - min > threshold`; raise `NoSlateError` if none. `decode_gray`: ffprobe `-v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0`, then ffmpeg `-v error -i <path> -vf ... -f rawvideo -`; split stdout into `width*height` chunks; raise `NoSlateError`? no — raise `RuntimeError("ffmpeg produced no frames")` on empty.
- [ ] **Step 4: Run to verify pass** → 12 PASS
- [ ] **Step 4b: Real-footage check (manual, no commit of media).** `uv run python -m tools.film.cli record captures/probe.mp4 --seconds 10` of whatever the sign is showing, then in a REPL `decode_gray` + `find_panel_bbox` on it and `contact_sheet` the bbox: the crop must be the panel alone, not the window or the plush beside it. Adjust `threshold` if needed and note the value in the README (Task 7).
- [ ] **Step 5: Commit** — `git commit -m "feat(film): grayscale decode, slate/anchor detection, change-based panel crop"`

---

### Task 3: `film clip` – GIF/mp4 emission, budget ladder, name zipping, contact sheet

**Files:**
- Create: `tools/film/clip.py`
- Test: `tools/film/test_clip.py`

**Interfaces:**
- Consumes: `Footage`, `Interval`, `BBox`, `GrayFrames` (Task 2); `film_names` (Task 1); `Runner` (Task 1).
- Produces:
  ```python
  @dataclass(frozen=True)
  class ClipSettings: width: int = 800; fps: int = 20; max_bytes: int = 2_500_000; trim_frames: int = 1
  LADDER: tuple[tuple[int, int], ...] = ((800, 20), (640, 20), (640, 15))
  class CountMismatch(RuntimeError)   # message lists detected segments (as seconds) and manifest names
  def plan_clips(footage: Footage, names: list[str]) -> list[tuple[str, Interval]]   # zip; CountMismatch if len differs
  def gif_argv(src: Path, out: Path, seg: Interval, fps_src: float, bbox: BBox, scale_from_width: int, src_width: int, settings: ClipSettings) -> list[str]
      # -ss/-t from frame indices (trim_frames off each end); crop scaled from analysis width to source width; filter:
      # crop=W:H:X:Y,fps=<fps>,scale=<width>:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3
  def mp4_argv(src: Path, out: Path, seg: Interval, fps_src: float, bbox: BBox | None, analysis_width: int, src_width: int) -> list[str]   # libx264 -crf 18 -pix_fmt yuv420p -movflags +faststart; bbox None = full frame
  def emit_gif_within_budget(src: Path, out: Path, seg: Interval, fps_src: float, bbox: BBox, analysis_width: int, src_width: int, *, runner: Runner, size_of: Callable[[Path], int], settings: ClipSettings) -> tuple[int, int, int]
      # try LADDER rungs until size_of(out) <= max_bytes; return (width, fps, bytes). If none fits, keep the smallest and return it; caller prints a warning naming the clip.
  def contact_sheet(frames: GrayFrames, seg: Interval, bbox: BBox, out: Path) -> None   # Pillow: first/middle/last crop, scaled 4x nearest, stacked vertically
  def clip_footage(src: Path, manifest: Path, out_dir: Path, *, runner, crop: BBox | None, take: int, mp4_names: set[str], hero_budget_names: set[str], settings) -> list[Path]
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_plan_clips_zips_names_in_order(): ...  # 2 segments, 2 names → [("a", seg0), ("b", seg1)]

def test_plan_clips_count_mismatch_lists_both():
    with pytest.raises(CountMismatch) as e: plan_clips(footage_with(3), ["a", "b"])
    assert "3 segment" in str(e.value) and "'a', 'b'" in str(e.value)

def test_gif_argv_has_two_pass_palette_and_scaled_crop():
    argv = gif_argv(Path("in.mp4"), Path("o.gif"), Interval(10, 50), 10.0, BBox(10, 20, 100, 10), 320, 3840, ClipSettings())
    vf = argv[argv.index("-filter_complex") + 1]
    assert "crop=1200:120:120:240" in vf and "palettegen=stats_mode=diff" in vf and "paletteuse=dither=bayer:bayer_scale=3" in vf
    assert argv[argv.index("-ss") + 1] == "1.100" and argv[argv.index("-t") + 1] == "3.800"   # 1 frame trimmed each end at 10 fps

def test_emit_gif_walks_ladder_until_under_budget():
    sizes = iter([5_000_000, 3_000_000, 2_000_000])
    runner = FakeRunner({"ffmpeg": Result(["ffmpeg"], 0, b"", b"")})
    w, fps, n = emit_gif_within_budget(..., runner=runner, size_of=lambda p: next(sizes), settings=ClipSettings())
    assert (w, fps, n) == (640, 15, 2_000_000) and len(runner.calls) == 3

def test_emit_gif_over_budget_after_ladder_returns_smallest(): ...  # sizes all > budget → returns last rung, 3 calls

def test_mp4_argv_full_frame_when_bbox_none(): ...  # no "crop=" in -vf
```

- [ ] **Step 2: Run to verify fail** → FAIL
- [ ] **Step 3: Implement `tools/film/clip.py`.** `clip_footage` order: decode → analyze → names → plan → per clip: gif (budget `4_000_000` for names in `hero_budget_names`, else `settings.max_bytes`), mp4 if in `mp4_names`, contact sheet `<name>.contact.png`; print one line per clip `name  w×fps  bytes  [OVER BUDGET]`.
- [ ] **Step 4: Run to verify pass** → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(film): clip emission with palette GIFs, budget ladder, contact sheets"`

---

### Task 4: `film record`

**Files:**
- Create: `tools/film/record.py`
- Test: `tools/film/test_record.py`

**Interfaces:**
- Produces:
  ```python
  DEFAULT_DEVICE = "Insta360 Link"
  def list_devices(runner: Runner) -> list[str]   # parses `ffmpeg -f avfoundation -list_devices true -i ""` stderr video section → names
  class DeviceNotFound(RuntimeError)   # message includes the device list
  def record_argv(device_index: int, out: Path, seconds: float, *, size: str = "3840x2160", fps: int = 30) -> list[str]
      # ffmpeg -y -f avfoundation -framerate <fps> -video_size <size> -i "<idx>:none" -t <seconds> -c:v libx264 -preset veryfast -crf 16 -pix_fmt yuv420p <out>
  def record(device: str, out: Path, seconds: float, runner: Runner, *, size: str = "3840x2160", fps: int = 30) -> Path
  ```

- [ ] **Step 1: Write the failing tests**

```python
LIST = b'[AVFoundation indev @ 0x1] AVFoundation video devices:\n[AVFoundation indev @ 0x1] [0] Insta360 Link\n[AVFoundation indev @ 0x1] [1] FaceTime HD Camera\n[AVFoundation indev @ 0x1] AVFoundation audio devices:\n[AVFoundation indev @ 0x1] [0] Mic\n'
def test_list_devices_parses_video_section_only():
    assert list_devices(FakeRunner({"ffmpeg": Result(["ffmpeg"], 1, b"", LIST)})) == ["Insta360 Link", "FaceTime HD Camera"]

def test_record_unknown_device_raises_with_list():
    with pytest.raises(DeviceNotFound, match="FaceTime HD Camera"):
        record("Insta 360", Path("o.mp4"), 5, FakeRunner({"ffmpeg": Result(["ffmpeg"], 1, b"", LIST)}))

def test_record_argv_uses_index_and_4k30():
    argv = record_argv(0, Path("o.mp4"), 12.5)
    assert argv[argv.index("-i") + 1] == "0:none" and "3840x2160" in argv and argv[argv.index("-t") + 1] == "12.5"

def test_record_resolves_index_then_records():
    runner = FakeRunner({"ffmpeg": lambda argv: Result(argv, 1 if "-list_devices" in argv else 0, b"", LIST)})
    record("Insta360 Link", Path("o.mp4"), 3, runner)
    assert runner.calls[1][runner.calls[1].index("-i") + 1] == "0:none"
```

- [ ] **Step 2: Run to verify fail** → FAIL
- [ ] **Step 3: Implement `tools/film/record.py`.** Regex for device lines: `\[(\d+)\] (.+)$` between the "video devices" and "audio devices" markers.
- [ ] **Step 4: Run to verify pass** → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(film): record from the Insta360 via avfoundation"`

---

### Task 5: `film deploy` / `film restore` / wait-for-display

**Files:**
- Create: `tools/film/sign.py`
- Test: `tools/film/test_sign.py`

**Interfaces:**
- Consumes: `Runner`, `ssh_argv`, `scp_argv` (Task 1).
- Produces:
  ```python
  REMOTE_CONFIG = "~/led-ticker/config/config.toml"
  REMOTE_STAGE = "/tmp/film-deploy.toml"
  CONTAINER = "led-ticker"
  STATE_FILE = Path("captures/.film-state.json")   # {"host", "bak", "sha256", "deployed_at"}
  class DeployRefused(RuntimeError); class RestoreRefused(RuntimeError)
  def film_bak_name(now: datetime) -> str            # "config.toml.film-bak-20261117T150000Z"
  def remote_sha256(host, runner) -> str             # ssh: sha256sum <REMOTE_CONFIG> | cut -d' ' -f1
  def remote_list_film_baks(host, runner) -> list[str]
  def remote_status(host, runner) -> dict            # ssh: docker exec led-ticker cat /run/led-ticker/status.json → json
  def wait_for_display(host, runner, *, previous_started_at: float | None, timeout: float = 90.0, sleep=time.sleep) -> dict
      # poll remote_status every 2 s until started_at != previous_started_at and swap_count > 0; TimeoutError otherwise.
      # Callers read remote_status()["started_at"] BEFORE issuing docker restart (the Pi's clock is never compared to the Mac's).
  def with_brightness(toml_text: str, brightness: int | None) -> str   # rewrite the `[display]` brightness line; None = unchanged
  def deploy(host, config: Path, runner, *, now, restore_first=False, brightness=None, state_file=STATE_FILE) -> dict
      # 1) film-baks present and not restore_first → DeployRefused ; restore_first → restore(force=False) first
      # 2) ssh: sudo cp REMOTE_CONFIG ~/led-ticker/config/<bak>
      # 3) write (possibly brightness-rewritten) config to a tempfile, scp to REMOTE_STAGE, ssh: sudo cp REMOTE_STAGE REMOTE_CONFIG && docker restart led-ticker
      # 4) wait_for_display(previous_started_at=<read in step 0 before the restart>) ; 5) state = {...sha256 of what we wrote...}; write state_file; return state
  def restore(host, runner, *, now, force=False, state_file=STATE_FILE) -> str | None
      # no state and no film-bak → print "nothing to restore", return None
      # remote_sha256 != state.sha256 and not force → RestoreRefused (names both hashes)
      # ssh: sudo cp <newest bak> REMOTE_CONFIG && docker restart ; wait_for_display ; ssh: sudo rm <bak> ; delete state_file ; return bak
  ```

- [ ] **Step 1: Write the failing tests** (a `FakeSign` helper builds a `FakeRunner` whose `ssh` callable dispatches on substrings of the remote command: `sha256sum`→hash, `ls`→bak list, `cat /run/led-ticker/status.json`→status JSON, `sudo cp`/`docker restart`/`sudo rm`→ok; `scp`→ok)

```python
def test_deploy_refuses_when_film_bak_exists_without_restore_first(tmp_path): ...  # baks=["config.toml.film-bak-..."] → DeployRefused

def test_deploy_backs_up_copies_restarts_waits_and_writes_state(tmp_path):
    ...; state = deploy("smallsign", cfg, sign.runner, now=NOW, state_file=tmp_path/"s.json")
    cmds = [c[-1] for c in sign.runner.calls if c[0] == "ssh"]
    assert any("sudo cp ~/led-ticker/config/config.toml ~/led-ticker/config/config.toml.film-bak-20261117T150000Z" in c for c in cmds)
    assert any("docker restart led-ticker" in c for c in cmds)
    assert state["sha256"] == hashlib.sha256(cfg.read_bytes()).hexdigest() and json.loads((tmp_path/"s.json").read_text()) == state

def test_deploy_brightness_override_changes_hash_and_text(tmp_path):
    assert with_brightness("[display]\nrows = 16\nbrightness = 60\n", 40) == "[display]\nrows = 16\nbrightness = 40\n"

def test_wait_for_display_polls_until_started_at_changes_and_swapping(): ...  # statuses: same started_at → new but swap 0 → new swap 5; sleep stubbed; returns third

def test_wait_for_display_times_out(): ...  # TimeoutError after timeout/2 polls

def test_restore_refuses_on_hash_drift(tmp_path): ...  # state sha != remote sha → RestoreRefused; no "sudo cp" issued

def test_restore_force_restores_newest_bak_and_cleans_up(tmp_path): ...  # two baks → newest copied; "sudo rm" of it after wait; state file gone

def test_restore_with_nothing_is_noop(capsys): ...  # returns None, prints "nothing to restore"
```

- [ ] **Step 2: Run to verify fail** → FAIL
- [ ] **Step 3: Implement `tools/film/sign.py`.** All remote mutations are single `ssh` calls with `&&`-joined commands so a failed `cp` never reaches `docker restart`.
- [ ] **Step 4: Run to verify pass** → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(film): deploy/restore the sign config with backup, hash guard, display wait"`

---

### Task 6: CLI, Make targets, docs rows

**Files:**
- Create: `tools/film/cli.py`
- Modify: `Makefile` (`.PHONY` line 1; new targets after `plan-gif`), `docs/site/src/content/docs/reference/cli.mdx` (rows after line 274)
- Test: `tools/film/test_cli.py`; existing `tests/test_docs_cli_make_targets_drift.py` must stay green

**Interfaces:**
- Consumes: everything above.
- Produces: `def main(argv: list[str] | None = None) -> int` with subcommands:
  - `deploy CONFIG [--host smallsign] [--restore-first] [--brightness N]`
  - `record OUT [--seconds 60] [--device "Insta360 Link"] [--size 3840x2160] [--fps 30] [--list-devices]`
  - `restore [--host smallsign] [--force]`
  - `clip IN MANIFEST OUT_DIR [--crop x:y:w:h] [--take 1] [--mp4 name,name] [--hero name,name]`
  - `session CONFIG OUT --seconds N [--host] [--brightness] [--device]` = deploy → record → restore (restore runs in `finally`)
  - Exit codes: 0 ok; 1 refused/mismatch/no-slate (message on stderr); 2 usage/device/tool missing.

Make targets (each with a `## ` comment, mirroring `plan-gif`):

```make
film-deploy:  ## Back up the sign's config and deploy a filming config. Usage: make film-deploy CONFIG=docs/site/filming/hero.toml [HOST=smallsign] [BRIGHTNESS=60] [RESTORE_FIRST=1]
	# recipe: uv run python -m tools.film.cli deploy $(CONFIG) $(if $(HOST),--host $(HOST)) $(if $(BRIGHTNESS),--brightness $(BRIGHTNESS)) $(if $(RESTORE_FIRST),--restore-first)
film-record:  ## Record the Insta360 Link to an mp4. Usage: make film-record OUT=captures/hero.mp4 SECONDS=60
film-restore:  ## Restore the sign's pre-filming config. Usage: make film-restore [HOST=smallsign]
film-clip:  ## Cut footage into cropped GIFs by slate detection. Usage: make film-clip IN=captures/hero.mp4 MANIFEST=docs/site/filming/hero.toml OUT=docs/site/public/filmed/ [TAKE=1] [CROP=x:y:w:h]
film-session:  ## deploy → record → restore in one go. Usage: make film-session CONFIG=... OUT=... SECONDS=...
```

- [ ] **Step 1: Write the failing tests**

```python
def test_cli_record_list_devices_exit_0(capsys, monkeypatch): ...  # monkeypatch cli.default_runner → FakeRunner with LIST; "Insta360 Link" in out
def test_cli_clip_count_mismatch_exit_1(...): ...  # monkeypatch clip_footage to raise CountMismatch → rc 1, message on stderr
def test_cli_deploy_refused_exit_1(...): ...
def test_cli_tool_missing_exit_2(...): ...  # ToolMissing → rc 2
def test_cli_session_restores_in_finally(...): ...  # record raises → restore still called
```

- [ ] **Step 2: Run to verify fail** → FAIL
- [ ] **Step 3: Implement `cli.py`, Make targets, `.PHONY`, cli.mdx rows** (five `| \`make film-…\` | … |` rows in the same table as `plan-gif`).
- [ ] **Step 4: Verify** — `uv run pytest tools/film tests/test_docs_cli_make_targets_drift.py tests/test_make_targets.py -v` → PASS; `make film-record OUT=/dev/null SECONDS=0 -n` prints the uv command.
- [ ] **Step 5: Commit** — `git commit -m "feat(film): CLI, Make targets and CLI reference rows"`

---

### Task 7: Filming configs + runbook + validation test

**Files:**
- Create: `docs/site/filming/hero.toml`, `docs/site/filming/features.toml`, `docs/site/filming/youtube.toml`, `docs/site/filming/README.md`
- Test: `tools/film/test_filming_configs.py`

**Interfaces:**
- Consumes: `film_names` (Task 1); `led_ticker.validate` (the one permitted `led_ticker` import; `pytest.importorskip("led_ticker_flair")` so CI without the plugin skips rather than fails).

- [ ] **Step 1: Write the failing test**

```python
FILMING = REPO / "docs/site/filming"
@pytest.mark.parametrize("name", ["hero", "features", "youtube"])
def test_filming_config_validates_clean(name):
    pytest.importorskip("led_ticker_flair")
    rc = subprocess.run(["uv", "run", "led-ticker", "validate", str(FILMING / f"{name}.toml"), "--json"], capture_output=True, text=True)
    report = json.loads(rc.stdout); assert report["errors"] == [], report

def test_filming_configs_have_no_schedule_busy_or_paths():
    for p in FILMING.glob("*.toml"):
        t = p.read_text()
        assert "[display.schedule]" not in t and "path =" not in t and 'type = "image"' not in t
        assert "enabled = false" in t.split("[busy_light]")[1]

def test_hero_and_features_names():
    assert film_names((FILMING / "hero.toml").read_text()) == ["hero"]
    names = film_names((FILMING / "features.toml").read_text()); assert len(names) >= 30 and len(set(names)) == len(names)
```

- [ ] **Step 2: Run to verify fail** → FAIL (files missing)

- [ ] **Step 3: Write `hero.toml`.** Exact content (the spec fixes the copy; durations target ≤ 30 s between slates):

```toml
# Smallsign filming config — HERO loop. Deploy with: make film-deploy CONFIG=docs/site/filming/hero.toml
# Copy/palette: docs/DOCS-STYLE.md §6 (Firebird Yoga). Only core + led-ticker-flair >= 0.24.

[display]
rows = 16
cols = 32
chain_length = 5
brightness = 60
gpio_slowdown = 2
hardware_mapping = "adafruit-hat"
hot_reload = true

[busy_light]
enabled = false

[title]
delay = 0

[transitions]
default = "cut"
duration = 0.5
easing = "ease_out"
between_sections = "cut"
transition_colors = [[255, 92, 38], [255, 183, 3], [99, 60, 138], [255, 244, 214]]

[[source]]
id = "clock.et"
type = "clock"
format = "%-I:%M %p"
timezone = "America/New_York"
color = [255, 183, 3]

[[source]]
id = "clock.pt"
type = "clock"
format = "%-I:%M %p"
timezone = "America/Los_Angeles"
color = [255, 92, 38]

# --- slate (loop anchor: 2.0 s; inner slates in other configs are 1.0 s) ---
[[playlist.section]]
mode = "slideshow"
bg_color = [255, 255, 255]
hold_time = 2.0
transition = "cut"

[[playlist.section.widget]]
type = "message"
text = "."
font_color = [255, 255, 255]

# --- beats 1-3 ---
[[playlist.section]]  # film: hero
mode = "slideshow"
hold_time = 3.5
widget_transition = {type = "flair.stickers", duration = 2.5, backing = "shadow", emoji = ["fire", "star", "heart", "sun"]}
transition_duration = 2.5

[[playlist.section.widget]]
type = "message"
text = "FIREBIRD YOGA"
font_color = {style = "color_cycle", from = [255, 183, 3], to = [214, 40, 57], speed = 3}
animation = {style = "typewriter", frames_per_char = 3}
border = {style = "lightbulbs", mode = "chase", lit_color = [255, 183, 3], unlit_color = [40, 15, 0], chase_density = 3}

[[playlist.section.widget]]
type = "countdown"
text = "Spring Sessions"
countdown_date = 2027-03-20
font_color = [255, 244, 214]
border = {style = "bands", colors = [[255, 92, 38], [255, 183, 3], [99, 60, 138], [214, 40, 57]], band_width = 8}

[[playlist.section.widget]]
type = "message"
text = "Breathe Deep :heart: Flow Strong :heart_green: Rise Together :fire:"
font_color = {style = "gradient", from = [255, 183, 3], to = [214, 40, 57]}
background = {style = "flair.fireworks", bursts = 3, colors = [[255, 183, 3], [214, 40, 57], [255, 244, 214]]}

# --- beat 4 (nyancat in) + beat 5 ---
[[playlist.section]]
mode = "slideshow"
hold_time = 3
entry_transition = {type = "nyancat.alternating", duration = 3.0}
widget_transition = {type = "flair.laser.alternating", write_from = "opposite"}
transition_duration = 2.0

[[playlist.section.widget]]
type = "message"
text = ":red_apple: NEW YORK :clock.et: :sun:"
font_color = {style = "gradient", from = [255, 244, 214], to = [255, 92, 38]}

[[playlist.section.widget]]
type = "message"
text = ":star_yellow: LOS ANGELES :clock.pt: :moon:"
font_color = {style = "gradient", from = [255, 183, 3], to = [99, 60, 138]}

# --- beat 6: closing card, held; the slate cuts in after it ---
[[playlist.section]]
mode = "slideshow"
hold_time = 4
entry_transition = {type = "flair.splitflap.forward", duration = 3.0}

[[playlist.section.widget]]
type = "message"
text = "FIREBIRD YOGA · docs.ledticker.dev"
font_color = {style = "shimmer", base = [255, 183, 3], shimmer = [255, 244, 214], speed = 14, width = 8, pause = 0.5}
```

Note the hero has **one** `# film: hero` name but three content sections; `plan_clips` sees one segment (slate → slate) because only the slate is bright. Keep it that way.

- [ ] **Step 4: Write `features.toml`.** Same `[display]`/`[busy_light]`/`[title]`/`[transitions]`/`[[source]]` preamble as hero. Then a slate section before **every** content section (the first slate `hold_time = 2.0`, all others `1.0`), each content section carrying `# film: <name>`, `mode = "slideshow"`, `hold_time = 5`, `loop_count = 1`. Copy comes from DOCS-STYLE §6 (class names, program marquees, tagline). Segments and the one field that is the point of each:

| `# film:` name | widget / fields |
|---|---|
| `color-rainbow` | message `Breathe. Move. Rise.` `font_color = "rainbow"` |
| `color-gradient` | message, `{style = "gradient", from = [255, 183, 3], to = [99, 60, 138]}` |
| `color-shimmer` | message, `{style = "shimmer", base = [255, 92, 38], shimmer = [255, 244, 214]}` |
| `color-cycle` | message, `{style = "color_cycle", from = [255, 92, 38], to = [99, 60, 138], speed = 3}` |
| `color-random` | message, `font_color = "random"` |
| `border-lightbulbs-chase` | message cream text, `border = {style = "lightbulbs", mode = "chase", lit_color = [255, 183, 3], unlit_color = [40, 15, 0], chase_density = 3}` |
| `border-lightbulbs-alternate` | same, `mode = "alternate"` |
| `border-bands` | `border = {style = "bands", colors = [[255, 92, 38], [255, 183, 3], [99, 60, 138], [214, 40, 57]], band_width = 8}` |
| `border-rainbow` | `border = "rainbow"` |
| `border-color-cycle` | `border = "color_cycle"` |
| `border-constant` | `border = [255, 92, 38]` |
| `background-twinkle` | `background = {style = "flair.twinkle", density = 0.05, color = [255, 215, 120]}` |
| `background-fireworks` | `background = {style = "flair.fireworks", bursts = 3, colors = [[255, 183, 3], [214, 40, 57], [255, 244, 214]]}` |
| `background-snow` | `background = "flair.snow"` |
| `animation-typewriter` | `animation = {style = "typewriter", frames_per_char = 3}` on `FIREBIRD YOGA` |
| `animation-twinkle` | `animation = {style = "flair.twinkle", density = 0.7, min_brightness = 0.25}` |
| `animation-fisheye` | `animation = "flair.fisheye"` on the storefront scroll marquee |
| `animation-propeller` | `animation = "flair.propeller"` |
| `animation-blink` | `animation = "flair.blink"` |
| `widget-countdown` | countdown `Spring Sessions`, `countdown_date = 2027-03-20`, bands border |
| `widget-two-row` | two_row `top_text = "FIREBIRD YOGA"`, `bottom_text = "Vinyasa Flow · Yin · Hot Power · Restorative"`, `top_color = [255, 183, 3]`, `bottom_color = [255, 244, 214]` |
| `widget-clock` | message `:sun: NEW YORK :clock.et:` |
| `emoji-sampler` | message `:fire: :heart: :star: :sun: :moon: :cloud: :rain: :snow: :red_apple: :taco: :owl: :mushroom:` cream |
| `transition-<t>` for each of `push_left`, `wipe_alternating`, `dissolve`, `split`, `color_flash`, `scroll`, `nyancat`, `pokeball`, `pacman`, `sailor_moon`, `splitflap`, `sand`, `laser`, `interlock`, `blinds`, `accordion`, `fairy`, `stickers`, `fireworks`, `lightning`, `spinout`, `poker`, `snow` | two message widgets `BREATHE` (amber) and `RISE` (flame), `hold_time = 2`, `widget_transition = <type>` (flair families use their `.alternating` / `.forward` variant as in the live config; `transition_duration = 2.5`) |

That is 23 + 23 = 46 names. Run `uv run led-ticker validate docs/site/filming/features.toml` and drop any transition the validator rejects at 160×16, noting it in README.

- [ ] **Step 5: Write `youtube.toml`.** Live-sign shape with public copy, fall palette, one slate at the top only, `# film: youtube` on the first content section. Sections: fall greeting (typewriter + lightbulbs; `countdown` Thanksgiving `2026-11-26`; scrolling gradient marquee with fall emoji); "Firebird Yoga" studio section (program marquees, two_row class list); weather (`weather.current` for New York, Philadelphia, Chicago, Denver, Los Angeles; `units = "imperial"`); world time (five `clock` sources as in the live config, curated emoji instead of the sign-local icons); countdowns (Solstice `2026-12-21`, Christmas `2026-12-25`, New Years `2027-01-01` with the live config's providers); a news section with `rss.feed` on `https://www.nasa.gov/news-release/feed/`, `update_interval = 3000`. Sports section **omitted** (spec open question 4). Note at the top: needs `led-ticker-weather`, `led-ticker-rss`, `led-ticker-flair`; brightness as hero.

- [ ] **Step 6: Write `README.md`** (runbook, ~40 lines): camera setup checklist from spec §D (gimbal, zoom to ~90 % width, manual exposure/WB/focus, HDR and tracking off, record the chosen values here after Task 8), the five Make targets in session order, the `--brightness` ladder procedure, where output goes, "if the sign is left on a filming config run `make film-restore`".

- [ ] **Step 7: Run to verify pass** — `uv run pytest tools/film/test_filming_configs.py -v` → PASS; `uv run led-ticker validate docs/site/filming/<each>.toml` → 0 errors (warnings allowed: list them in the PR body).
- [ ] **Step 7b: Render-then-clip end-to-end (no hardware).** For `hero` and `features`: `D=$(make plan-gif CONFIG=docs/site/filming/<name>.toml | sed -n 's/^duration: //p')`, then `uv run python tools/render_demo/render.py docs/site/filming/<name>.toml -o captures/<name>-render.gif --duration $((D * 2 + 10))` (two loops so there are two anchors), then `uv run python -m tools.film.cli clip captures/<name>-render.gif docs/site/filming/<name>.toml captures/<name>-render/`. Expected: hero → 1 clip; features → 46 clips (or the trimmed count), no `CountMismatch`. This catches: a transition that holds the panel white long enough to read as a slate (`color_flash`, `flair.lightning`, `flair.fireworks` — if one does, lengthen `ANCHOR_SECONDS`/inner-slate gap or move that transition's segment), the `"."` slate not filling the panel, a missing `·` glyph in the default BDF font (swap for `-` if so), and the hero's real length. Hero target is ≤ 30 s slate-to-slate; if over, shorten holds (3.5 → 3) before shortening the marquee.
- [ ] **Step 8: Commit** — `git commit -m "feat(film): hero, features and youtube filming configs + runbook"`

---

### Task 8: Hardware session 0 — brightness ladder and framing check (manual, with James)

**Files:** `docs/site/filming/README.md` (record values), `docs/site/filming/*.toml` (brightness if it changes)

Not TDD; this dogfoods the tooling and closes the spec's "Sequence step 1".

- [ ] **Step 1:** James locks the camera per README (zoom so the panel fills ~90 % of frame width, manual exposure/WB/focus). Confirm with a 3-second `make film-record OUT=captures/framing.mp4 SECONDS=3` and a Pillow crop of the first frame: panel width in px ÷ 160 ≥ 8.
- [ ] **Step 2:** `make film-deploy CONFIG=docs/site/filming/features.toml BRIGHTNESS=40`, `make film-record OUT=captures/ladder-40.mp4 SECONDS=20`; repeat for 50 and 60 with `RESTORE_FIRST=1` so the existing film-bak is restored before each redeploy. `make film-restore`.
- [ ] **Step 3:** Compare the three recordings' first content segment (contact sheets from `make film-clip` into `captures/ladder-<n>/`): pick the brightest value whose cream text is not clipped to white and whose colors stay distinct. Set that `brightness` in all three filming TOMLs and record camera values in README.
- [ ] **Step 4:** Confirm `ssh smallsign cat ~/led-ticker/config/config.toml | head -3` shows the live config header and `ls ~/led-ticker/config/*film-bak*` is empty.
- [ ] **Step 5: Commit** — `git commit -m "docs(film): camera values and brightness from session 0"`
- [ ] **Step 6: Finish the branch.** `uv run pyright` clean; `make lint`; `make test` green (incl. `tests/test_docs_cli_make_targets_drift.py`). Commit the spec and this plan: `git add docs/superpowers/specs/2026-11-17-smallsign-filming-design.md docs/superpowers/plans/2026-11-17-smallsign-filming.md`. Open the PR per the `open-pr` skill (draft; body lists validator warnings from Task 7 and any transitions dropped from the reel). PR 2 (filming sessions, media, `DemoGif.astro` video source, docs wiring) is planned separately after this merges.

---
