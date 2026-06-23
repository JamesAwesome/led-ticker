# Discoverability Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the public `led-ticker` GitHub repo and its `led-ticker-core` PyPI package discoverable via accurate hardware/library keywords and proper repo metadata.

**Architecture:** Three independent, low-risk surfaces — (1) GitHub repo settings via `gh repo edit`, (2) README prose additions, (3) `pyproject.toml` PyPI metadata — plus a documented manual follow-up for the social preview image. No application code changes.

**Tech Stack:** `gh` CLI, Markdown, TOML (`pyproject.toml`, hatchling build backend).

## Global Constraints

- **Positioning:** DIY / hardware-first. No competitor name-drops ("alternative to X"). No keyword-stuffing — every term reads as natural prose or legitimate metadata.
- **Factual alignment:** README hardware claims must match existing `## Hardware` prose and `CLAUDE.md` invariants — no new/invented claims. Canonical board is `hardware_mapping = "adafruit-hat"`.
- **PyPI safety:** Every trove classifier must come from the official PyPI classifier list verbatim — an invalid classifier breaks the package upload.
- **Worktree convention:** Work in the `docs/discoverability-pass` worktree; run `make dev` before pushing.
- **Repo:** `JamesAwesome/led-ticker` (public). PyPI package name: `led-ticker-core`.

---

### Task 1: GitHub repo metadata

**Files:**
- None (repo settings via `gh` CLI).

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by later tasks (independent surface).

- [ ] **Step 1: Capture current state for rollback**

Run:
```bash
gh repo view JamesAwesome/led-ticker --json description,homepageUrl,repositoryTopics
```
Expected: shows `description: "My LED Ticker code"`, empty `homepageUrl`, null/empty topics. Note these in case rollback is needed.

- [ ] **Step 2: Set description + homepage**

Run:
```bash
gh repo edit JamesAwesome/led-ticker \
  --description "Drive Adafruit RGB Matrix HAT / HUB75 LED panels from a Raspberry Pi with a TOML config — scrolling news, weather, crypto, and more. Asyncio Python." \
  --homepage "https://docs.ledticker.dev"
```
Expected: command exits 0, prints the repo URL.

- [ ] **Step 3: Set topics**

Run (each `--add-topic` is one topic; GitHub lowercases/validates):
```bash
gh repo edit JamesAwesome/led-ticker \
  --add-topic raspberry-pi \
  --add-topic raspberry-pi-5 \
  --add-topic raspberry-pi-4 \
  --add-topic led-matrix \
  --add-topic rgb-led-matrix \
  --add-topic hub75 \
  --add-topic adafruit \
  --add-topic led-sign \
  --add-topic led-ticker \
  --add-topic led-display \
  --add-topic rpi-rgb-led-matrix \
  --add-topic hzeller \
  --add-topic python \
  --add-topic asyncio \
  --add-topic docker \
  --add-topic pixel-art \
  --add-topic scrolling-text \
  --add-topic bdf-fonts
```
Expected: exits 0. (If any topic is rejected for format, GitHub will name it — fix that one term and re-run only it.)

- [ ] **Step 4: Verify**

Run:
```bash
gh repo view JamesAwesome/led-ticker --json description,homepageUrl,repositoryTopics
```
Expected: new description, `homepageUrl: "https://docs.ledticker.dev"`, and all 18 topics present.

- [ ] **Step 5: No commit** — this task changes no files. Proceed to Task 2.

---

### Task 2: README keyword integration

**Files:**
- Modify: `README.md` (H1 tagline area near line 6; `## Hardware` section near lines 104–108).

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add tagline sentence under the intro**

In `README.md`, the current intro (line 6) reads:

```markdown
An asyncio Python toolkit that drives RGB LED matrix panels from a Raspberry Pi via a TOML config. Two reference builds share one codebase and one Docker image:
```

Replace it with (adds one natural keyword-bearing sentence; keeps the existing sentence intact):

```markdown
An asyncio Python toolkit that drives RGB LED matrix panels from a Raspberry Pi via a TOML config. It runs HUB75 panels through an Adafruit RGB Matrix HAT (or Bonnet) on top of the [`hzeller/rpi-rgb-led-matrix`](https://github.com/hzeller/rpi-rgb-led-matrix) library, so anything that library drives, led-ticker drives. Two reference builds share one codebase and one Docker image:
```

- [ ] **Step 2: Add a "Hardware compatibility" subsection**

In `README.md`, the `## Hardware` section currently ends with the line:

```markdown
Hardware reference (BOM, wiring, panel-tuning knobs): <https://docs.ledticker.dev/hardware/building-your-own/>.
```

Immediately AFTER that line, insert:

```markdown

### Hardware compatibility

led-ticker works with the same hardware as the underlying `hzeller/rpi-rgb-led-matrix` library:

- **Controller boards:** Adafruit RGB Matrix HAT and RGB Matrix Bonnet (`hardware_mapping = "adafruit-hat"`). Other HUB75 wiring/GPIO mappings supported by the library also work.
- **Panels:** HUB75 RGB LED matrix panels — any pitch (P3, P4, P5, …). The reference builds use P3 32×64 and 16×32 panels; chains and serpentine layouts are configured in TOML.
- **Raspberry Pi:** Pi 4 (BCM2711 GPIO backend) and Pi 5 (RP1 PIO/RIO backend). The single Docker image detects the SoC at runtime.

See the [hardware reference](https://docs.ledticker.dev/hardware/building-your-own/) for BOMs, wiring diagrams, and panel-tuning knobs.
```

- [ ] **Step 3: Verify links and prose**

Run:
```bash
grep -n "hzeller\|Adafruit RGB Matrix\|Hardware compatibility\|HUB75" README.md
```
Expected: matches in the intro and the new subsection. Read the diff (`git diff README.md`) and confirm it reads naturally — no duplicated facts, no stuffing.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): add hardware/library keywords (Adafruit HAT, HUB75, hzeller)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: PyPI metadata in pyproject.toml

**Files:**
- Modify: `pyproject.toml` (`[project]` table — `classifiers` at lines 16–22; add a `keywords` field).

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add a `keywords` array**

In `pyproject.toml`, the `[project]` table currently has `classifiers` starting at line 16. Immediately BEFORE the `classifiers = [` line, insert a `keywords` array:

```toml
keywords = [
    "raspberry-pi",
    "led-matrix",
    "rgb-led-matrix",
    "hub75",
    "adafruit",
    "led-sign",
    "led-ticker",
    "led-display",
    "rpi-rgb-led-matrix",
    "asyncio",
    "pixel-art",
    "scrolling-text",
]
```

- [ ] **Step 2: Expand classifiers**

The current `classifiers` block is:

```toml
classifiers = [
    "Development Status :: 4 - Beta",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.14",
    "Operating System :: POSIX :: Linux",
    "Topic :: Multimedia :: Graphics",
]
```

Replace it with (adds three valid trove classifiers — all present on the official PyPI list):

```toml
classifiers = [
    "Development Status :: 4 - Beta",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.14",
    "Operating System :: POSIX :: Linux",
    "Topic :: Multimedia :: Graphics",
    "Topic :: System :: Hardware",
    "Framework :: AsyncIO",
    "Intended Audience :: Developers",
]
```

- [ ] **Step 3: Verify TOML parses**

Run:
```bash
python -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); print('keywords:', d['project']['keywords']); print('classifiers:', len(d['project']['classifiers']))"
```
Expected: prints the 12 keywords and `classifiers: 8`. No exception.

- [ ] **Step 4: Verify the build still works**

Run:
```bash
make dev
```
Expected: `uv sync` completes without error (validates the project metadata is well-formed).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "build: add PyPI keywords + classifiers for led-ticker-core discoverability

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Document the social-preview follow-up

**Files:**
- Modify: `docs/superpowers/specs/2026-06-23-discoverability-pass-design.md` (append a checklist) — OR surface in the PR body. This task adds NO new tracked-doc churn beyond the maintainer note.

**Interfaces:**
- Consumes: nothing.
- Produces: a maintainer to-do captured in the PR.

- [ ] **Step 1: Add the manual follow-up to the PR body / handoff**

No file edit required. When opening the PR (or in the handoff summary), include this maintainer checklist item verbatim:

> **Manual follow-up (cannot be done via CLI):** Upload a 1280×640 social-preview PNG via GitHub → repo **Settings → General → Social preview**. A real LED-panel photo is the ideal asset. This sets the og:image shown when the repo is shared in Slack/Discord/social.

Expected: the item appears in the PR description so it is not lost.

- [ ] **Step 2: No commit** — handoff/PR-body only.

---

## Final verification (before opening PR)

- [ ] `gh repo view JamesAwesome/led-ticker --json description,homepageUrl,repositoryTopics` shows all Task 1 changes.
- [ ] `git diff main -- README.md pyproject.toml` shows only the intended additions.
- [ ] `make dev` succeeds in the worktree.
- [ ] PR body includes the Task 4 social-preview follow-up note.
