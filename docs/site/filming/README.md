# Filming the smallsign

Real-hardware footage for the docs site and a YouTube loop, recorded from the
Insta360 Link on the Mac with `tools/film/` (see `make help` → `film-*`). The
design is in `docs/superpowers/specs/2026-11-17-smallsign-filming-design.md`.

Nothing here touches the camera or the sign without James's go-ahead for that
step.

## Configs

| file            | what                                               | slate layout                                                                  |
| --------------- | -------------------------------------------------- | ----------------------------------------------------------------------------- |
| `hero.toml`     | ~30 s teaser for the homepage / README / showcase  | one 2.0 s anchor slate, then three content sections (one `# film: hero` clip) |
| `features.toml` | one 4–6 s clip per effect (46 clips)               | 2.0 s anchor slate, then a 1.0 s slate before every section                   |
| `youtube.toml`  | 3–5 min loop in the live sign's shape, public copy | one 2.0 s anchor slate (one `# film: youtube` clip, full camera frame)        |

All three: smallsign `[display]`, fixed `brightness`, an empty `[web]` table (the
status board must be on: `film deploy` waits on `status.json`), no `[display.schedule]`,
`[busy_light] enabled = false`, no file assets, Firebird Yoga copy
(`docs/DOCS-STYLE.md` §6). Validate with `uv run led-ticker validate <file>`.

## Camera setup (once per session)

The Insta360 Link is driven over UVC with `uvcc` (runs via `npx`, so Node
must be on PATH — `nvm use`). The Link only applies pan/tilt/zoom while a
video stream is open, so `make film-aim` holds a throwaway ffmpeg stream
while it sends the controls and then reads them back; it fails loudly if
the camera ignored them (another app holding the device, or the camera
asleep). Framing survives stream close/reopen while the camera stays
powered, so run it once at the start of a session (or pass `AIM=1` to
`make film-session`).

Measured 2026-11-17 with the camera on the desk and the sign on the top
shelf (the preset `camera.SMALLSIGN_SHELF`):

| setting                                   | value                                                                   |
| ----------------------------------------- | ----------------------------------------------------------------------- |
| pan / tilt (arc-seconds)                  | `-27720` / `36000`                                                      |
| zoom                                      | `350` (3.5×, digital); panel ≈ 77 % of frame width, ≈ 18 px per LED     |
| white balance                             | locked `5000` K (auto WB drifts with the panel's colors)                |
| focus                                     | auto (sharp on the panel; `FOCUS=n` locks it if it hunts)               |
| exposure                                  | auto — not exposed over UVC; dips content ≈ 20 % for ~1 s after a slate |
| panel brightness (`[display] brightness`) | `40` (ladder 40/50/60: auto-exposure equalizes them; 40 blooms least)   |
| panel-crop threshold (`find_panel_bbox`)  | defaults (change 60 / bright 200); detected box ≈ 7 % bezel top/bottom  |

Zoom is digital, so the real detail is what the sensor sees at 1×: about
6 px per LED from the desk. That is enough for 800 px GIFs (5 px per LED)
but not for a crisp 4K hero; move the camera to the shelf for that. A
specular highlight sits on the panel face right of centre (room light);
kill that light before a real take.

## A session

```bash
make film-aim                                                      # frame the panel, lock WB (once per session)
make film-deploy  CONFIG=docs/site/filming/features.toml          # backs up + restarts the sign
make film-record  OUT=captures/features.mp4 SECONDS=900           # two full loops + anchors
make film-restore                                                  # puts the live config back
make film-clip    IN=captures/features.mp4 MANIFEST=docs/site/filming/features.toml OUT=docs/site/public/filmed/
```

or `make film-session CONFIG=... OUT=... SECONDS=... AIM=1` for deploy → aim → record →
restore in one go (restore runs even if the recording fails).

How long to record: `make plan-gif CONFIG=<file>` gives one loop's length;
record at least two loops plus a few seconds so the footage holds two anchor
slates. `film clip` needs a complete loop between two anchors; `TAKE=2`
selects the second loop if the first had a glitch.

Brightness ladder (done in session 0, 2026-11-17 — result `40`, baked into
the three configs): `make film-deploy CONFIG=... BRIGHTNESS=40`, record
20 s, repeat with `BRIGHTNESS=50 RESTORE_FIRST=1` and `BRIGHTNESS=60
RESTORE_FIRST=1`; `make film-restore` at the end.

## Output

`film clip` writes, per `# film:` name: `<name>.gif` (≤ 2.5 MB, hero ≤ 4 MB;
ladder 800px/20fps → 640/20 → 640/15, then reported as OVER BUDGET),
`<name>.contact.png` (first / middle / last frame for review), and
`<name>.mp4` for names passed in `MP4=`. For the YouTube loop use
`MP4=youtube MP4_ONLY=1 FULL_FRAME=1`: one uncropped mp4, no GIF encodes. `film clip`
prints the detected panel box (analysis and source pixels), the peak slate luma and the
anchor count before writing anything; if the box is wrong pass `CROP=x:y:w:h` in
analysis (320-wide) pixels, if slates are missed lower `SLATE_THRESHOLD`, if the box
bleeds into the room raise `CHANGE_THRESHOLD`. Docs media goes to
`docs/site/public/filmed/`; YouTube output stays in `captures/` (gitignored).

## If something goes wrong

- Sign left on a filming config: `make film-restore` (add `FORCE=1` if it
  refuses because the config changed under us — read the message first).
- `no slate found`: the camera is not on the panel, or exposure clipped the
  room brighter than the panel. Re-aim / lower exposure.
- `recording holds 0 complete loop(s)`: record longer.
- Segment/name count mismatch: a transition held the panel white long enough
  to read as a slate, or a section lacks its `# film:` comment. The message
  lists both sides.
