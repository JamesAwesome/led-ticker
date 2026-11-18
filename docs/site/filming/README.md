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

| setting                                   | value                                                                             |
| ----------------------------------------- | --------------------------------------------------------------------------------- |
| pan / tilt (arc-seconds)                  | `-27720` / `36000`                                                                |
| zoom                                      | `350` (3.5×, digital); panel ≈ 77 % of frame width, ≈ 18 px per LED               |
| white balance                             | locked `5000` K (auto WB drifts with the panel's colors)                          |
| focus                                     | auto (sharp on the panel; `FOCUS=n` locks it if it hunts)                         |
| exposure                                  | auto — not exposed over UVC; dips content ≈ 20 % for ~1 s after a slate           |
| panel brightness (`[display] brightness`) | `40` (ladder 40/50/60: auto-exposure equalizes them; 40 blooms least)             |
| panel detection (`find_panel_bbox`)       | slate-driven: bright 245, slate fraction 0.6; box ≈ the LED area + 4 % pad (10:1) |

Zoom is digital, so the real detail is what the sensor sees at 1×: about
6 px per LED from the desk. That is enough for 800 px GIFs (5 px per LED)
but not for a crisp 4K hero; move the camera to the shelf for that. A
specular highlight sits on the panel face right of centre (room light);
kill that light before a real take.

Still app-only (Insta360 Link Controller, none of these are UVC controls):
**exposure lock** (auto exposure dips the content ≈ 20 % for about a second
after every white slate, and every clip starts right after one), HDR off,
tracking off (it would fight the preset mid-take), mirror off. The
session-0 ladder ran under auto exposure; lock it before a real take if the
dip shows in the GIFs.

Lighting trade-off (both shot 2026-11-17): with the room lights **on** the
camera's auto exposure has something to meter, so white text keeps its
dots, but a room light reflects off the panel face right of centre. With
the lights **off** the reflection is gone but the sensor gains up: more
grain (the hero web mp4 grows 2.0 → 3.0 MB) and white text and white emoji
bloom into blobs; colour is unaffected. Best of both: lights off plus an
exposure lock in the Link Controller app, or lights on with the offending
lamp moved off the panel's reflection line. James's call (2026-11-17): the **dark** takes are the docs set
(`docs/site/public/filmed/`); six lit takes sit beside them in
`docs/site/public/filmed/lit/` as comparisons (rainbow, lightbulbs, emoji
sampler, two-row, splitflap, typewriter), the full lit set stays in
`captures/lit-room/filmed/`, and the YouTube loop exists in both
(`captures/youtube-out/youtube-{dark,lit}.mp4`). The lit hero was
overwritten by the dark session; re-shoot it if a lit hero is ever wanted.
Note the idle camera
reports `absolute_zoom = 100` even while the framing is still applied;
`film aim` reads back inside an open stream, so trust it, not a bare
`uvcc export`.

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
denoised, ladder 800px/20fps → 640/20 → 640/15 → 640/12 → 560/12 → 480/10,
then reported as OVER BUDGET), `<name>.contact.png` (first / middle / last
frame for review), and for names passed in `MP4=` both `<name>.mp4` (crf 18,
archival) and `<name>.web.mp4` (1280 wide, crf 24, ≈ 2 MB for the 30 s hero —
the docs-site hero is this video, not the GIF; real footage never fits a
30 s loop in 4 MB of GIF). For the YouTube loop use
`MP4=youtube MP4_ONLY=1 FULL_FRAME=1`: one uncropped mp4, no GIF encodes.
`film clip` prints the detected panel box (analysis and source pixels), the
peak slate luma and the anchor count before writing anything, and warns if a
rival column run came close to the pick; if the box is wrong pass
`CROP=x:y:w:h` in analysis (320-wide) pixels, if slates are missed lower `SLATE_FRACTION` (a slate is a frame where that share of the box saturates above `BRIGHT_THRESHOLD`).
Docs media goes to `docs/site/public/filmed/`; YouTube output stays in
`captures/` (gitignored).

## Placement shots (wide, with the room in frame)

The docs also carry two "placement" videos that show the shelf and the
decorations around the sign, so a reader can picture where theirs would go.
They are not slate-cut: both are hand-trimmed from full-frame recordings,
cropped to drop the bottom strip of the camera frame (the shelf below the
sign), denoised and scaled to 960 wide so each stays under the 4 MB mp4
budget (2026-11-18 cuts: lit 3.0 MB / 79 s, dark 2.0 MB / 31 s).

```sh
# Lights on — the Firebird section of the YouTube loop (44.5 s → 123.5 s),
# from the lit YouTube recording kept on the Desktop.
ffmpeg -ss 44.5 -t 79 -i youtube-lit.mp4 \
  -vf "crop=iw:ih*0.78:0:0,hqdn3d=4:3:6:4.5,scale=960:-2" \
  -c:v libx264 -crf 28 -preset slow -pix_fmt yuv420p -movflags +faststart -an \
  docs/site/public/filmed/placement-lit.mp4

# Lights off — the hero loop, cut full-frame by `film clip` first:
#   make film-clip IN=raw/hero.mp4 MANIFEST=docs/site/filming/hero.toml OUT=/tmp/wide/ MP4=hero MP4_ONLY=1 FULL_FRAME=1
# then the same crop/scale with a heavier denoise (night grain is expensive).
ffmpeg -i /tmp/wide/hero.mp4 \
  -vf "crop=iw:ih*0.78:0:0,hqdn3d=8:6:12:9,scale=960:-2" \
  -c:v libx264 -crf 28 -preset slow -pix_fmt yuv420p -movflags +faststart -an \
  docs/site/public/filmed/placement-dark.mp4
```

Full-frame 1280-wide encodes at crf 24 came out at 14 MB for both takes;
the grain, not the content, is what costs bits.

## If something goes wrong

- Sign left on a filming config: `make film-restore` (add `FORCE=1` if it
  refuses because the config changed under us — read the message first).
- `no slate found`: the camera is not on the panel, or exposure clipped the
  room brighter than the panel. Re-aim / lower exposure.
- `recording holds 0 complete loop(s)`: record longer.
- Segment/name count mismatch: a transition held the panel white long enough
  to read as a slate, or a section lacks its `# film:` comment. The message
  lists both sides.
