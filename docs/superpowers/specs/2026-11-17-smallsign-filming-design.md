# Smallsign filming: hero loop, feature clips, YouTube loop

**Date:** 2026-11-17
**Status:** approved 2026-11-17 (James), defaults accepted for open questions 1 and 3; questions 2 and 4 deferred to the PR 2 YouTube session

## Intent

Real-hardware footage of the smallsign (Pi 4, 5× 32×16 panels, 160×16, scale 1)
for the docs site and a YouTube showcase. Today every demo on the site is a
software render; the renders are accurate but they do not show what an LED
panel looks like in a room. We want:

1. a **hero loop** for the docs homepage, README and showcase page;
2. **feature clips**, one effect each, to drop into the pages that already
   describe that effect (color providers, borders, backgrounds, animations,
   transitions, the smallsign hardware page);
3. a **YouTube loop**, several minutes long, in the shape of the live sign's
   daily loop.

Plus the tooling to do it repeatably: swap the sign's config, record from the
Insta360 Link webcam on James's Mac, cut the recording into cropped GIFs (and
an mp4 for the hero), and put the sign back the way it was.


> **Session 0 amendment (2026-11-17):** the Insta360 Link's zoom is digital
> only and `uvcc` turned out to work, so camera framing (pan/tilt/zoom, white
> balance) is set from the terminal by `film aim` rather than in the Link
> Controller app; exposure is not exposed over UVC and stays app-only. Real
> detail from the desk is ≈ 6 camera px per LED (below the ≥ 8 target; fine
> for 800 px GIFs, not for a 4K hero). Real-footage GIFs are 4–6× larger
> than renders: the hero ships as a web mp4, GIFs are denoised. Panel and
> slate detection are slate-driven (the frames with the most saturated
> pixels are the slates; the panel is what saturates in them; a slate is a
> frame where ≥ 60 % of the box saturates) — change-based masks and the
> crop-mean slate test both failed on real footage. Measured loops: hero
> 33 s, features ≈ 330 s, YouTube 323 s.

## Why now

The docs have 284 rendered GIFs and zero photographs or video of a running
sign. The spike recorded on 2026-11-17 (10 s, 1920×1080 at 30 fps, ffmpeg +
avfoundation) shows the camera path works: exposure stayed steady across a
scrolling headline, no refresh banding, text legible. The Link's UVC modes
top out at 3840×2160@30 and 1920×1080@30; nothing above 30 fps. The sign
filled roughly 600 camera pixels for 160 LEDs (about 4 px per LED) at the
camera's current wide framing, which is too soft for a GIF; the Link's zoom
and gimbal should get that to 8–12 px per LED.

## Goals

- Footage that is re-filmable: the hero and feature clips use only
  deterministic content (no live data), so the same config produces the same
  footage next year.
- One command each for deploy, record, restore and clip.
- Clips cut by **detecting slate flashes in the footage**, not by estimating a
  timeline, so no hand-timed cut lists.
- Sign returns to its live config automatically, verified.

## Non-goals

- Re-filming the existing 284 rendered catalog GIFs. Real footage goes where a
  render undersells hardware: hero, showcase, smallsign hardware page, the
  transitions catalog page, and one clip per effect family page.
- Bigsign / longboi footage. The tooling should not assume smallsign geometry,
  but only smallsign is in scope.
- Audio. Everything is silent loops.
- Shipping a camera driver. Pan/tilt/zoom/exposure are set once per session
  (see Camera) and ffmpeg records whatever the camera is doing.

## Anti-goals (what would make this a failure)

- Public footage containing the live config's internal copy (work Slack
  channel name, internal tool names), the personal RSS feed, or the Nintendo
  banner sprites (marked local-only in the live config).
- The busy-light dot landing in a take.
- The sign left on a filming config, or left dark, after a session.
- Docs GIFs so large they slow the pages. Camera noise inflates GIFs; see
  Output.

## Constraints

- **Sign state (checked 2026-11-17):** smallsign runs core `v4.34.0` with
  `led-ticker-flair==0.24.0`, `led-ticker-rss==0.3.0`,
  `led-ticker-weather==0.4.0`, hockey 0.4.0, football 0.4.0, basketball
  0.3.0. Filming configs use only what is installed; the hero and feature
  clips need only core + flair.
- **Live config is James's daily loop** (`~/led-ticker/config/config.toml` on
  `smallsign`, gitignored). Every deploy backs it up and every session ends by
  restoring it.
- **Hot-reload lands at a section seam and restarts the playlist from
  section 0** (`app/run.py`: the per-section reload check `break`s out of the
  section loop). `brightness`, `schedule`, `timezone`, `hot_reload` are the
  only hot-reloadable `[display]` fields; anything else, including a
  `[busy_light]` change (`reload.nonreloadable_changed`), is restart-required. **Decision (mine):** the deploy step
  always does `docker restart led-ticker` after copying the config. It is
  slower than a hot-reload but it guarantees start-from-top, applies every
  field, and is one code path.
- **Brightness:** filming configs set a fixed `brightness` and omit
  `[display.schedule]` (the live config dims to 15 after 22:00). The spike
  at 60 was not blown out at the camera's auto exposure; the builder should
  record a short brightness ladder (40 / 50 / 60) under locked exposure
  before committing to a value.
- **Busy light:** filming configs set `[busy_light] enabled = false`.
- **Camera control from the CLI** (`uvcc`, npm) could not be installed by
  the assistant in auto mode; James runs it himself if he wants scripted
  PTZ/exposure. Fallback is the Insta360 Link Controller app, set once.
- Repo rules: branch + PR, worktree for branch work, `uv run pyright` before
  push, no `from __future__ import annotations`.

## Who does what, and how it ships

The assistant runs the hardware steps from James's Mac in-session: SSH to
the sign, ffmpeg against the Insta360 (both proven in the spike). James aims
and locks the camera (section D) and is present for the sessions. Two PRs:
**PR 1** tooling + filming configs + tests + runbook; **PR 2** the filmed
media and docs wiring, after the sessions. Section C is planned now but
lands in PR 2.

## The deliverables

### A. Filming configs (committed)

Location (**my call**): `docs/site/filming/<name>.toml`, next to the pinned
demo TOMLs they parallel. Each is a complete smallsign config: `[display]`
for the smallsign (rows 16, cols 32, chain 5, adafruit-hat, gpio_slowdown 2),
fixed brightness, no schedule, busy light off, `hot_reload = true`.

Shared conventions:

- **Slate section.** A one-widget section that paints the whole panel white
  for 1.0 s with `cut` transitions on both sides. (Implementation left to the
  builder: a `message` with `bg_color = [255,255,255]` and a single space, or
  an `image` of a white PNG; either must fill all 160×16 pixels.) The clip
  tool finds slates by luminance, so **every segment boundary in every
  filming config is a slate**, including one at the very top of the
  playlist. The YouTube loop has a slate only at the top.
- **Copy and palette (my call, see open question 4).** Follow
  `docs/DOCS-STYLE.md` §6: all hero and feature copy is the fictional
  Firebird Yoga storefront, in the phoenix palette (flame `[255,92,38]`,
  ember `[214,40,57]`, amber `[255,183,3]`, cream `[255,244,214]`, dusk
  `[99,60,138]`), so the filmed media matches every rendered demo and
  `config/config.firebird.example.toml`. The hero's closing card reads
  `FIREBIRD YOGA · docs.ledticker.dev`. The YouTube loop keeps the live
  sign's fall palette but with public copy. No people, no employers, no
  personal feeds.
- **Assets.** Only emoji from the curated 8×8 registry (fall set, weather
  icons, standard set). No `[[source]] type = "image"` and no files outside
  the repo: the committed-configs test requires bundled assets only, and
  `film-deploy` copies exactly one file. The world-time icons on the sign
  (`config/assets/worldtime/`) are sign-local and are **not** used; the
  world-time beat uses curated emoji (`:sun:`, `:snow:`, `:red_apple:`,
  `:star_yellow:`) around `:clock.*:` sources instead.
- **Panel color rules.** Pure white washes to blue-white on camera, use
  cream; pure black is invisible; avoid dark-on-dark. Where the phoenix
  palette lacks contrast on a given effect, the builder may add one accent
  from the live fall palette rather than a new color.

#### A1. `hero.toml` (target 20–25 s between the top slate and the loop point)

Beat sheet (all deterministic, core + flair 0.24):

| # | Beat | What it shows |
|---|------|---------------|
| 0 | Slate | sync |
| 1 | `flair.stickers` entry into a typewriter `message` with `lightbulbs` chase border | entry transition, animation, border |
| 2 | `countdown` with `bands` border | widget, border |
| 3 | Scrolling `message` with `gradient` text over `flair.fireworks` background and inline emoji | color provider, background, emoji |
| 4 | `nyancat.alternating` section change | sprite-trail transition |
| 5 | Two world-time `message` cards with curated emoji and `clock` sources, `flair.laser.alternating` between them | sources, emoji, flair transition |
| 6 | `message` `FIREBIRD YOGA · docs.ledticker.dev` in `shimmer` (amber over cream), held | closing card, loop point |

Hold times short (3–4 s) so it reads as a teaser. **Loop seam (my call):**
the slate is a hard `cut` on both sides. Beat 1 enters from the slate with
`cut`, so the `flair.stickers` moment moves to the beat 1 → beat 2 widget
transition; beat 6 is a held card with no exit transition, and the slate
cuts in after it. The hero GIF runs from the first non-slate frame to the
last frame before the next slate; the page's GIF loop is then a hard cut
from the held closing card back to beat 1, which is how every GIF on the
site already loops.

#### A2. `features.toml` (one slate-delimited segment per effect, 4–6 s each)

Segments, in order, each its own section with a slate before it:

- Color providers: `rainbow`, `gradient`, `shimmer`, `color_cycle`,
  constant + `font_color = "random"` (five segments).
- Borders: `lightbulbs` chase, `lightbulbs` alternate, `bands`, `rainbow`
  chase, `color_cycle`, `constant` (six).
- Backgrounds: `flair.twinkle`, `flair.fireworks`, `flair.snow` (three).
- Animations: `typewriter`, `flair.twinkle`, `flair.fisheye`,
  `flair.propeller`, `flair.blink` (five).
- Widgets: `countdown`, `two_row`, `clock` source inline in a message, 8×8
  emoji sampler (four).
- Transitions reel: each transition shown as "A card → transition → B card"
  with a slate between transitions. Core: `push_left`, `wipe_alternating`,
  `dissolve`, `split`, `color_flash`, `scroll`. Flair: `nyancat`, `pokeball`,
  `pacman`, `sailor_moon`, `splitflap`, `sand`, `laser`, `interlock`,
  `blinds`, `accordion`, `fairy`, `stickers`, `fireworks`, `lightning`,
  `spinout`, `poker`, `snow`. (Builder trims any that read badly at 160×16;
  list what was dropped.)

Total run time is a few minutes; that is fine, it is recorded once.

#### A3. `youtube.toml` (3–5 min loop)

The live config's shape with public copy: fall greeting section, a
"news"-style section using a public RSS feed (**my call:** NASA breaking
news, or whatever James prefers), weather for a few cities, the world-time
section as-is, countdowns to public holidays, and the sports section only if
James wants live scores in a permanent video. Live data is allowed here
because this footage is a one-off upload, not re-filmable docs media.

### B. Tooling (committed)

Location (**my call**): `tools/film/` as a small Python package in the
`tools/render_demo` style, with Make targets. Python 3.14, stdlib +
subprocess around `ffmpeg`, `ssh`, `scp`; no new runtime deps in core.
Optional Pillow (already a dep) for frame analysis.

Make targets:

```
make film-deploy  CONFIG=docs/site/filming/hero.toml   [HOST=smallsign]
make film-record  OUT=captures/hero.mp4 SECONDS=60     [DEVICE="Insta360 Link"]
make film-restore                                      [HOST=smallsign]
make film-clip    IN=captures/hero.mp4 MANIFEST=docs/site/filming/hero.toml OUT=docs/site/public/filmed/
make film-session CONFIG=... OUT=... SECONDS=...        # deploy → record → restore
```

Behaviors:

- **deploy:** `ssh HOST` to copy `config.toml` →
  `config.toml.film-bak-<UTC timestamp>` (refuse to overwrite an existing
  film-bak unless `--force`; refuse if a film-bak already exists and
  `--restore-first` is not given, so two sessions cannot clobber the real
  backup). `scp` the filming config to `config.toml`, `docker restart
  led-ticker`, then tail `docker logs` until the startup line appears or 90 s
  elapse. Exit non-zero on timeout.
- **record:** `ffmpeg -f avfoundation -i "<device>:none"` at 3840×2160@30 (the
  Link's top UVC mode; `--size 1920x1080` as a fallback), h264
  `-crf 16`, to `OUT`. Prints the device list if the named device is missing.
  Does **not** touch camera settings.
- **restore:** copies the newest film-bak back to `config.toml`, restarts the
  container, waits for startup, then deletes the film-bak only after a
  successful restart. Idempotent: with no film-bak present it says so and
  exits 0.
- **clip:**
  1. Finds the panel's bounding box from the first slate (brightest
     rectangle; threshold on luminance), unless `--crop x:y:w:h` is given.
     Pads the crop by a few percent so a sliver of bezel shows (**my call**;
     see question 2 below).
  2. Finds every slate (mean luminance of the crop above threshold for
     ≥ 0.5 s), yielding N segments.
  3. Reads the manifest's segment names from the filming TOML. **My call on
     format:** each slate-delimited section carries a comment
     `# film: <clip-name>` on its `[[playlist.section]]` line; the tool
     parses those comments in order and zips them with the detected
     segments. Mismatched counts are a hard error with both lists printed.
  4. Emits one GIF per segment: two-pass palette (`palettegen` /
     `paletteuse`, `stats_mode=diff`, `dither=bayer:bayer_scale=3`), 20 fps,
     width 800 px, trimmed so the first and last frames do not include slate
     fade. Also emits an mp4 (h264, same crop, 30 fps) for any segment named
     in `--mp4 name,name`, intended for the hero.
  5. Writes a contact sheet PNG per segment (first / middle / last frame) so
     James can review without opening every GIF.
- **Output budget (my call).** Feature clip GIFs ≤ 2.5 MB each, hero GIF
  ≤ 4 MB (the README needs a GIF; GitHub will not play a linked mp4). Yield
  order when over budget: width 800 → 640, then fps 20 → 15, then trim.
  Hero on the docs site is **mp4-primary** with the GIF as fallback, so
  `DemoGif.astro` grows an optional `video` source and a `filmed` flag that
  turns off `image-rendering: pixelated` (wrong for photographic footage).
  That component change is required, not optional. A `_headers` cache rule
  for `/filmed/*` matches the existing demo dirs.
- **Restore safety.** `film-deploy` records the sha256 of the config it
  wrote. `film-restore` refuses (exit non-zero, no changes) if the sign's
  current `config.toml` no longer matches that hash, since that means
  something else (the webui editor, a hand edit) wrote it during the
  session; `--force` overrides. `film-deploy` likewise refuses if the webui
  has written a `config.toml.bak` newer than our film-bak.
- **"Display is up" signal.** There is no post-frame-setup INFO line in
  core today. The builder picks one of: poll the status board / webui
  status endpoint on the sign until the swap counter advances, or add a
  single `display up` INFO log line to core (tiny, hot-path-free) and tail
  for it. Either way deploy and restore share the wait helper.
- **YouTube deliverable** is an mp4 file handed to James; uploading is his.
  The clip tool's `--mp4` for the YouTube segment uses the **full camera
  frame**, uncropped (the 16:9 framing is a camera decision, open
  question 1), trimmed from the top slate to the loop point.
- Nothing in `tools/film/` imports `led_ticker`; it is a build tool and must
  not appear in coverage or in the Docker image.

Tests (`tools/film/test_*.py`, run by `make test` like `tools/gif_plan`):
slate detection on a synthetic clip (white / content / white / content),
manifest parsing from TOML comments, count-mismatch error, restore
idempotence with a fake ssh runner. The ffmpeg/ssh shell-outs go through one
injectable runner so tests never hit hardware.

### C. Docs wiring

- Homepage hero: replace the current `message-rainbow.gif` `<DemoGif>` with
  the filmed hero (GIF, with the mp4 offered where the site component
  supports a video source; adding `<video>` support to `DemoGif.astro` is in
  scope if it is small, otherwise GIF only and note it).
- Showcase page and smallsign hardware page: hero or a feature clip plus a
  one-line caption in the existing caption voice.
- One filmed clip per effect-family page (color providers, borders,
  backgrounds, animations, transitions) placed near the top as "on real
  hardware", leaving the rendered catalog GIFs in place.
- Filmed media lives in `docs/site/public/filmed/`; filming TOMLs in
  `docs/site/filming/`. Follow `docs/DOCS-STYLE.md`.

### D. Camera (procedure, not code)

Set once per session in the Insta360 Link Controller app (or `uvcc` if James
installs it): gimbal aimed at the shelf, zoom until the panel fills ~90 % of
the frame width, **manual exposure** (fixed shutter, ISO low), **manual white
balance**, **manual focus**, HDR off, face-tracking off. These are UVC
settings and persist while ffmpeg records. Document the final values in
`docs/site/filming/README.md` so the next session matches.

Room: film with the room lights as they are in the spike (daylight, panel on
a dark shelf) or darker; avoid a window behind the camera.

## Sequence

1. Capture spike part 2 (throwaway): lock exposure, zoom in, record a
   brightness ladder (40/50/60) of the current loop at 4K; pick brightness
   and confirm px-per-LED ≥ 8.
2. `tools/film/` + tests.
3. `hero.toml`, `features.toml`, `youtube.toml`, validated with
   `led-ticker validate` locally and `make plan-gif` for rough run times.
4. Film sessions: features first (longest, least precious), then hero (a few
   takes), then YouTube.
5. Clip, review contact sheets, wire into docs, PR.

## Open questions for James

1. **YouTube frame.** The panel is 10:1; a 16:9 frame needs something around
   it. Options: the shelf as-is (plush, leaves, room), a dark backdrop, or a
   letterboxed strip. Your call; it changes how the camera is framed for that
   session.
2. **Docs crop.** Tight strip (panel only) or a few percent of bezel/shelf so
   it reads as a physical object? I have assumed a few percent.
3. **Sports in the YouTube loop.** Include live scores (unrepeatable) or
   leave them out?
4. **Identity.** I have gone with `docs/DOCS-STYLE.md` §6: Firebird Yoga
   copy and the phoenix palette for the hero and feature clips, with the
   closing card `FIREBIRD YOGA · docs.ledticker.dev`. Alternative is a
   generic `led-ticker` wordmark. A wrong guess here means re-filming
   everything, so please confirm.

## Left to the builder

- Exact slate implementation; whichever fills the panel reliably.
- Which transitions get cut from the reel for reading badly at 160×16.
- Threshold values for slate and crop detection, tuned on the real footage.
- The display-up wait mechanism (status poll vs. a new INFO line).
- `.gitignore` for `captures/`, `tools/film` in pytest `testpaths`, the CLI
  reference page entry for the new Make targets (there is a drift test).
