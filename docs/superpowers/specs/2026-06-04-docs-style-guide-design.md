# Docs Style Guide & Review Rubric — Design (Phase 0)

**Date:** 2026-06-04
**Status:** Approved (brainstorm), pending implementation plan

## Context: the larger docs effort

This is **Phase 0** of a phased deep-dive expansion + review of the led-ticker docs site. The agreed phase order:

- **Phase 0 (this spec):** a docs style guide + review rubric that codifies the lessons from prior doc work (the pool docs + the 4-round persona-reviewed plugin authoring guide). It becomes the checklist a **technical-writer subagent** applies to every task in later phases.
- **Phase 1:** expand the home/landing page — position led-ticker as an *extensible library*, keep it inviting to hobbyists, signpost both audiences.
- **Phase 2:** expand technical/API docs — a "how it works"/render-architecture page, a `led_ticker.plugin` API reference, transition/color-provider authoring walkthroughs.
- **Phase 3:** deep-dive review + fixes of the existing ~58 pages (the audit thrust, distinct from the per-task review that runs throughout Phases 1–3).

Each phase is its own spec → plan → implementation cycle. This spec covers **Phase 0 only**.

## Goal

Capture, in one durable, linkable place, the doc-writing standards we converged on over four rounds of UX/DX, PM, technical-writer, and hobbyist-programmer review — so later phases (and the tech-writer reviewer) start from those standards instead of rediscovering them. It also folds in patterns from a review of [Adafruit Learn](https://learn.adafruit.com/) guides: Adafruit makes the RGB Matrix HAT/Bonnet and panels our users buy and targets the same hobbyist-maker audience, so their beginner-onboarding style is a strong, directly-applicable model.

## Decisions (from brainstorm)

- **Form:** an internal repo doc `docs/DOCS-STYLE.md` (contributor/agent-facing), with a one-line pointer added to `CLAUDE.md`. **Not** a user-facing docs-site page.
- **Rubric length:** a **tight ~10-item per-page checklist** (fast to apply per task), not an exhaustive list.

## Deliverable

`docs/DOCS-STYLE.md` with these sections:

### 1. Audience & voice
- Two readers: **hobbyist sign-owners** who *configure* (TOML), and **developers** who *extend/build on the library* (plugins/API). Many pages serve one; some serve both — name the reader at the top.
- Voice: pragmatic, second-person, concrete, no marketing language. Match the existing tutorial/widget pages.

### 2. Principles
Each principle is one rule + a one-line "why," drawn from the persona reviews:
1. **Lead with the payoff** — a rendered GIF/screenshot or a concrete "what you'll build / what you'll see" up front (not after the mechanics).
2. **Prerequisites first** — state what's needed before any steps, and *how* to run commands (which venv / Docker exec / where files live).
3. **Gloss jargon on first use** — entry point, `attrs`, canvas, BDF, color provider, namespace, baseline, "constraint-based," "headless stub," etc. — one plain-language sentence or a link to a concept page.
4. **Complete, copy-pasteable examples** — show the whole file/config, not fragments the reader must assemble; reproduce a "complete listing" where a page builds something up. Teaching comments in code are encouraged even if they wouldn't appear in production code.
5. **Concrete commands** — never `path/to/...`; give a runnable command and say where its output lands.
6. **Internal consistency** — snippets, prose, and any complete listing must agree; field defaults must match validation logic; bind doc code to a tested file (a tripwire test) where feasible so it can't silently drift.
7. **Visual payoff for anything visual** — a `DemoGif` (via `render-demo`) for widgets/transitions/effects.
8. **Failure & recovery** — surface the common errors and their fixes (and what success looks like).
9. **Honesty about limits** — document real quirks/limitations rather than hiding them (e.g. `render-demo` won't load a local-dir plugin; install first).
10. **Cross-link, don't re-explain** — link to the concept/reference page rather than restating it.

Patterns borrowed from **Adafruit Learn** (some reinforce the above; the last six are new/under-used for us):

11. **"What you'll need" box** — a scannable box near the top of any task page listing prerequisites parts-list style (API key + which `.env` var, which config base, hardware-or-no-hardware), instead of burying them in prose. (Adafruit's bill-of-materials, stated up front.)
12. **Time/effort stamp** — a small "~10 min · no hardware needed"-style line near the top of each tutorial chapter to defuse intimidation. (Adafruit's "color blasting within the hour.")
13. **Local troubleshooting** — a short, symptom-first "If it doesn't work" box (2–3 common failures → fixes) on widget/tool/tutorial pages, *where the reader already is* — not only the central `pitfalls.mdx`. (Adafruit's per-guide Help FAQ.)
14. **Blameless error copy** — frame errors/validation as "a common mix-up — here's the fix," explaining the cause *then* the fix; never imply the reader screwed up. (Adafruit: "won't damage it, but won't work — get it right first time.")
15. **Anticipate beginner anxiety** — one reassuring line where a step looks intimidating ("you don't need to be a Python expert for this"). (Adafruit: "'I've never coded in my life!' You absolutely can!")
16. **A next-step CTA on every page** — every page (including reference/concept pages) ends by pulling the reader forward (`TutorialNav`/`RelatedPages` or a "next" link), not just tutorials. (Adafruit's persistent "Next Page.")

### Do NOT copy (from Adafruit)
- **No product upsell / buy-now links** in prose — we're open source; link hardware once on the Hardware pages, never mid-tutorial.
- **Don't over-illustrate trivial steps** — one outcome GIF/screenshot per *meaningful* step, not per CLI line.
- **Don't duplicate datasheet-grade hardware tables** (HUB75 pinouts, power-draw formulas, deep GPIO tuning) — link out to Adafruit's own guide instead.
- **Borrow the warmth, keep our voice** — one enthusiastic outcome line per page is plenty; stay matter-of-fact, not breathless-marketing ("dazzling," "color blasting").

### 3. Per-page review checklist (the rubric)
A tight checkbox list (≈10 items) the tech-writer reviewer runs against each completed task, derived from the principles above:
- [ ] Reader named; a scannable "what you'll need"/prerequisites block up front (incl. how/where to run commands).
- [ ] Payoff/visual near the top; tutorial chapters carry a time/effort stamp.
- [ ] Every new term glossed or linked on first use.
- [ ] Examples complete + copy-pasteable; commands concrete (no `path/to/...`; says where output lands).
- [ ] Snippets/prose/any complete listing internally consistent; defaults match validation.
- [ ] Code bound to a tested source where feasible (no silent drift).
- [ ] Local "if it doesn't work" troubleshooting where relevant; error copy is blameless (cause → fix).
- [ ] Cross-links instead of duplication; a next-step CTA at the bottom.
- [ ] Builds clean (`make docs-build`) + lint clean (`make docs-lint`); fences balanced.
- [ ] Tone consistent + matter-of-fact (no upsell, no breathless marketing).

### 4. Mechanics
- Components: `DemoGif`, `OptionsTable` (+ `docs/content-source/**` fact-packs), `TomlExample`, `TutorialNav`, and Starlight `Aside`/`Steps`/`Tabs`. One line on when to use each.
- GIFs: how to render one (`make render-demo CONFIG=… OUT=…`) and where demo assets live (`docs/site/public/demos*/`); note that `render-demo` needs an *installed* plugin for plugin widgets.
- Build/lint: `make docs-build`, `make docs-lint`, `make docs-format`. **Gotchas we hit:** don't pipe `docs-lint` to `tail` (it masks the exit code); run `docs-format` then re-lint when prettier complains; authoring pages nested under `plugins/authoring/` import components with an extra `../`.

### 5. The review loop
How the **technical-writer subagent** reviews each completed task in Phases 1–3: it reads the changed/added page(s), runs the §3 checklist, and returns concrete, prioritized fixes (must-fix vs nice-to-have). The implementer fixes; re-review until the checklist passes. This is the mechanism the later phase plans reuse (in place of, or alongside, the generic code-quality review).

## CLAUDE.md pointer

Add a one-line entry under the docs/authoring guidance pointing at `docs/DOCS-STYLE.md` as the standard for any docs-site change.

## Verification

- `docs/DOCS-STYLE.md` exists, is coherent, and the CLAUDE.md pointer is present.
- No docs-site build impact (it's a repo markdown file, not under `docs/site/`).

## References (the Adafruit Learn review)

The Adafruit-derived patterns above came from reviewing these guides (same hardware + audience as ours); cite them in `DOCS-STYLE.md` so the provenance is clear:
- [Adafruit RGB Matrix Bonnet for Raspberry Pi — Overview / Matrix Setup / Help](https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/overview) (our exact hardware; great "expected result per step" + symptom-first Help FAQ).
- [RGB LED Matrix Basics — Overview](https://learn.adafruit.com/32x16-32x32-rgb-led-matrix/overview) (outcome-first opener; time estimate).
- [Welcome to CircuitPython — Overview](https://learn.adafruit.com/welcome-to-circuitpython/overview) (beginner-anxiety reassurance; "you'll learn X, then Y").

## Out of scope (Phase 0)

- Any actual docs-site content changes (home page, API pages, audits) — those are Phases 1–3.
- A user-facing "Contributing to docs" site page (deferred; could be a later add if community contributions pick up).
- Auto-generating the rubric from anything — it's hand-written.
