# Shared fact pack

This directory holds shared markdown content consumed by BOTH:
- The `creating-a-config` skill at `.claude/skills/creating-a-config/`,
  loaded by `SKILL.md` directly.
- The docs site at `docs/site/`, imported by MDX components like
  `<OptionsTable source="widgets/message" />`.

When you add or change content here, both consumers update with no
extra work.

## Layout

- `widgets/<name>.md` — option table + base description per widget.
- `transitions/<family>.md` — push / wipe / sprite / special.
- `rules/<NN>-<slug>.md` — one file per decision rule (numbered).
- `emoji.md`, `color-providers.md`, `animations.md`, `borders.md`, `fonts.md` — vocab references.
- `hardware/<sign>.md` — small sign / bigsign hardware specs.

## What goes where

- This pack: facts (option tables, lists, rules).
- Skill (`SKILL.md`, `references/snippets.md`): wizard flow + recipe library.
- Docs site (`docs/site/src/content/docs/`): tutorials, walkthroughs, framing.
