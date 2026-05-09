#!/usr/bin/env node
/**
 * preinstall guard: refuse to install with anything other than pnpm.
 *
 * Reads $npm_config_user_agent — every modern package manager (npm,
 * pnpm, yarn) sets this when it runs lifecycle scripts, prefixed with
 * its own name. pnpm sets "pnpm/<version> ...", npm sets "npm/...",
 * yarn sets "yarn/...". If the prefix isn't "pnpm/", we print a clear
 * message and exit 1.
 *
 * Why this lives as a Node script instead of `npx only-allow pnpm`:
 * `npx` is bundled with npm, and on CI runners (Corepack-managed
 * pnpm + npm-bundled npx on PATH) the npx process resets
 * npm_config_user_agent to "npm/..." before only-allow runs, which
 * makes only-allow refuse pnpm itself. A direct Node check has no
 * external dependency and reads the env var unmodified.
 */
const ua = process.env.npm_config_user_agent ?? "";

if (!ua.startsWith("pnpm/")) {
  const msg = `
╔═════════════════════════════════════════════════════════════╗
║                                                             ║
║   This project requires pnpm.                               ║
║   Use "pnpm install" instead.                               ║
║                                                             ║
║   If pnpm isn't installed, run:  corepack enable            ║
║   See https://pnpm.io/ for details.                         ║
║                                                             ║
╚═════════════════════════════════════════════════════════════╝
`;
  console.error(msg);
  process.exit(1);
}
