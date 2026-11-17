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

All three: smallsign `[display]`, fixed `brightness`, no `[display.schedule]`,
`[busy_light] enabled = false`, no file assets, Firebird Yoga copy
(`docs/DOCS-STYLE.md` §6). Validate with `uv run led-ticker validate <file>`.

## Camera setup (once per session, in the Insta360 Link Controller app)

1. Gimbal: aim at the shelf so the whole 160×16 panel is in frame.
2. Zoom: until the panel fills about 90 % of the frame width (we need ≥ 8
   camera px per LED; at 4K that is ≥ 1280 px of panel).
3. Exposure: **manual**, fixed shutter, lowest ISO that keeps cream text
   below clipping. Auto-exposure pumps as sections change.
4. White balance: **manual**. Focus: **manual**, on the panel.
5. HDR off, face tracking off, mirror off.

These are UVC settings; they persist while ffmpeg records. Record the final
values here after session 0:

| setting                                   | value                                   |
| ----------------------------------------- | --------------------------------------- |
| zoom                                      | _TBD_                                   |
| shutter / ISO                             | _TBD_                                   |
| white balance                             | _TBD_                                   |
| panel brightness (`[display] brightness`) | _TBD (ladder 40/50/60 in session 0)_    |
| panel-crop threshold (`find_panel_bbox`)  | _TBD if the default 60 needed changing_ |

## A session

```bash
make film-deploy  CONFIG=docs/site/filming/features.toml          # backs up + restarts the sign
make film-record  OUT=captures/features.mp4 SECONDS=900           # two full loops + anchors
make film-restore                                                  # puts the live config back
make film-clip    IN=captures/features.mp4 MANIFEST=docs/site/filming/features.toml OUT=docs/site/public/filmed/
```

or `make film-session CONFIG=... OUT=... SECONDS=...` for deploy → record →
restore in one go (restore runs even if the recording fails).

How long to record: `make plan-gif CONFIG=<file>` gives one loop's length;
record at least two loops plus a few seconds so the footage holds two anchor
slates. `film clip` needs a complete loop between two anchors; `TAKE=2`
selects the second loop if the first had a glitch.

Brightness ladder (session 0): `make film-deploy CONFIG=... BRIGHTNESS=40`,
record 20 s, then repeat with `BRIGHTNESS=50 RESTORE_FIRST=1` and
`BRIGHTNESS=60 RESTORE_FIRST=1`; `make film-restore` at the end.

## Output

`film clip` writes, per `# film:` name: `<name>.gif` (≤ 2.5 MB, hero ≤ 4 MB;
ladder 800px/20fps → 640/20 → 640/15, then reported as OVER BUDGET),
`<name>.contact.png` (first / middle / last frame for review), and
`<name>.mp4` for names passed in `MP4=`. Docs media goes to
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
