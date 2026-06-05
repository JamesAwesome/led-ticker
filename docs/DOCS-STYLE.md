# Docs Style Guide & Review Rubric

Internal standard for any change to the led-ticker docs site (`docs/site/`). It captures what we learned writing the pool docs and the plugin authoring guide (which went through four rounds of UX/DX, PM, technical-writer, and hobbyist-programmer persona review), plus patterns borrowed from a review of [Adafruit Learn](https://learn.adafruit.com/) guides — Adafruit makes the RGB Matrix HAT/Bonnet and panels our users buy, and targets the same hobbyist-maker audience.

This is a contributor/agent-facing repo doc, **not** a published docs-site page. Its §3 checklist is the rubric the technical-writer reviewer runs against every docs task.

## 1. Audience & voice

We write for **two readers**:

- **Hobbyist sign-owners** who *configure* the sign through TOML. They may be new to Python, the command line, or LED hardware.
- **Developers** who *extend or build on the library* — plugins, widgets, transitions, color providers, the public API.

Many pages serve one reader; some serve both. **Name the reader at the top of the page** so it is clear who a section is for.

**Voice:** pragmatic, second-person ("you"), concrete, no marketing language. Match the existing tutorial and widget pages. Warmth is welcome — one enthusiastic outcome line per page is plenty — but stay matter-of-fact, never breathless.

## 2. Principles

Each principle is one rule plus a one-line "why." Principles 1–10 come from our own persona reviews; 11–16 are borrowed from Adafruit Learn (the last six are new or under-used for us).

1. **Lead with the payoff.** Open with a rendered GIF/screenshot or a concrete "what you'll build / what you'll see," before the mechanics — the reader should know within seconds whether this page is for them.
2. **Prerequisites first.** State what's needed before any steps, and *how* to run commands (which venv / `docker exec` / where files live) — the reader can't follow step 3 if step 0 is missing.
3. **Gloss jargon on first use.** Entry point, `attrs`, canvas, BDF, color provider, namespace, baseline, "constraint-based," "headless stub," etc. — one plain-language sentence or a link to a concept page, because a term you skip is a reader you lose.
4. **Complete, copy-pasteable examples.** Show the whole file/config, not fragments the reader must assemble; reproduce a "complete listing" where a page builds something up. Teaching comments in code are encouraged even where production code wouldn't carry them — a partial example is a support ticket waiting to happen.
5. **Concrete commands.** Never `path/to/...`; give a runnable command and say where its output lands — guessable placeholders aren't runnable.
6. **Internal consistency.** Snippets, prose, and any complete listing must agree; field defaults must match validation logic; bind doc code to a tested file (a tripwire test) where feasible so it can't silently drift — docs that contradict the code erode trust in all the docs.
7. **Visual payoff for anything visual.** A `DemoGif` (via `render-demo`) for widgets/transitions/effects, because "see it move" beats a paragraph describing the motion.
8. **Failure & recovery.** Surface the common errors and their fixes, and show what success looks like — the reader who hits an error and finds it documented stays; the one who doesn't, leaves.
9. **Honesty about limits.** Document real quirks/limitations rather than hiding them (e.g. `render-demo` won't load a local-dir plugin — install it first) — the reader hits the limit either way; documenting it saves the debugging hour.
10. **Cross-link, don't re-explain.** Link to the concept/reference page rather than restating it, so there's one source of truth to keep current.

Borrowed from Adafruit Learn:

11. **"What you'll need" box.** Put a scannable box near the top of any task page listing prerequisites parts-list style (API key + which `.env` var, which config base, hardware-or-no-hardware) instead of burying them in prose — a reader scanning for "can I do this right now?" finds the answer fast.
12. **Time/effort stamp.** Add a small "~10 min · no hardware needed"-style line near the top of each tutorial chapter — a known time commitment defuses intimidation.
13. **Local troubleshooting.** Add a short, symptom-first "If it doesn't work" box (2–3 common failures → fixes) on widget/tool/tutorial pages, *where the reader already is* — not only the central `pitfalls.mdx` — because a reader mid-task won't go hunting in a separate page.
14. **Blameless error copy.** Frame errors/validation as "a common mix-up — here's the fix," explaining the cause *then* the fix; never imply the reader screwed up — blame makes beginners quit.
15. **Anticipate beginner anxiety.** Add one reassuring line where a step looks intimidating ("you don't need to be a Python expert for this") — a single sentence keeps a nervous reader going.
16. **A next-step CTA on every page.** End every page — including reference and concept pages — by pulling the reader forward (`TutorialNav`/`RelatedPages` or a "next" link), not just tutorials — a dead-end page ends the session.

### Do NOT copy (from Adafruit)

- **No product upsell / buy-now links** in prose — we're open source. Link hardware once on the Hardware pages, never mid-tutorial.
- **Don't over-illustrate trivial steps.** One outcome GIF/screenshot per *meaningful* step, not per CLI line.
- **Don't duplicate datasheet-grade hardware tables** (HUB75 pinouts, power-draw formulas, deep GPIO tuning) — link out to Adafruit's own guide instead.
- **Borrow the warmth, keep our voice.** One enthusiastic outcome line per page is plenty; stay matter-of-fact, not breathless-marketing ("dazzling," "color blasting").

## 3. Per-page review checklist (the rubric)

The technical-writer reviewer runs this against each completed docs task. Aim for all boxes checked before a task is considered done.

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

## 4. Mechanics

**Authoring components** (use the right one rather than hand-rolling):

- `DemoGif` — embed a rendered demo GIF for any visual feature (widget/transition/effect).
- `OptionsTable` — render an options table from a `docs/content-source/**` fact-pack instead of hand-maintaining a Markdown table.
- `TomlExample` — show a TOML config block with consistent styling.
- `TutorialNav` — prev/next navigation on tutorial chapters.
- `RelatedPages` — the next-step CTA / related-links block at the bottom of a page.
- Starlight `Aside` (note/tip/caution/danger), `Steps`, and `Tabs` — for callouts, ordered procedures, and tabbed alternatives.

**Demo GIFs:**

- Render one with `make render-demo CONFIG=<config> OUT=<path>` (see `scripts/build-demos.mjs` for the batch build).
- Demo assets live under `docs/site/public/demos*/`.
- `render-demo` only loads an **installed** plugin (via its entry point), not a local-dir plugin — for a plugin widget, `pip install -e .` the plugin first, then render.

**Build & lint:**

- `make docs-build` — full Astro build; the truth for "does it compile."
- `make docs-lint` — lint check.
- `make docs-format` — auto-format (Prettier).

**Gotchas we hit:**

- Don't pipe `docs-lint` to `tail` — it masks the lint exit code, so a format-fallback never fires. Run `docs-format`, then re-run `docs-lint` and check the real exit code.
- When Prettier complains, run `docs-format` first, then re-lint.
- Authoring pages nested under `plugins/authoring/` import components with an extra `../` in the relative path — match the existing imports in that directory.

## 5. The review loop

In Phases 1–3, a **technical-writer reviewer subagent** reviews each completed task:

1. It reads the changed/added page(s).
2. It runs the §3 checklist against them.
3. It returns concrete, prioritized fixes — **must-fix** vs **nice-to-have**.

The implementer fixes the must-fix items; the reviewer re-reviews until the checklist passes. This runs in place of, or alongside, the generic code-quality review for docs tasks, and is the mechanism the later phase plans reuse.

## References (the Adafruit Learn review)

The borrowed patterns above came from reviewing these guides (same hardware + audience as ours):

- [Adafruit RGB Matrix Bonnet for Raspberry Pi — Overview / Matrix Setup / Help](https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/overview) — our exact hardware; strong "expected result per step" and a symptom-first Help FAQ.
- [RGB LED Matrix Basics — Overview](https://learn.adafruit.com/32x16-32x32-rgb-led-matrix/overview) — outcome-first opener; time estimate.
- [Welcome to CircuitPython — Overview](https://learn.adafruit.com/welcome-to-circuitpython/overview) — beginner-anxiety reassurance; "you'll learn X, then Y."
