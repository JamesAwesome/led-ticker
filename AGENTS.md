# Codex adapter

Read and follow [CLAUDE.md](CLAUDE.md) before working in this repository. It is
the canonical project guidance for both Claude Code and Codex. Read it in chunks
if needed so none of its invariants are truncated. Keep shared instructions there.

Codex discovers the existing Claude skills through the relative directory
symlinks in `.agents/skills/`. Edit their sources in `.claude/skills/`; keep
references and examples with them instead of copying them into this adapter.

For docs reviews, read `.claude/commands/review-docs.md` and use the requested
scope as its `$ARGUMENTS`. Translate Claude tool and model names to the available
Codex equivalents; use the same review criteria. Claude's local settings and
permissions do not configure Codex.
