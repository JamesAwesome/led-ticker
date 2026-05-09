#!/usr/bin/env node
/**
 * preinstall guard: refuse to install with anything other than pnpm.
 *
 * Detection. Two env vars are inspected because no single one is
 * reliable across pnpm versions and Corepack-managed CI runners:
 *
 *   npm_config_user_agent   "pnpm/<version> ..." when pnpm is the
 *                           runner, "npm/..." for npm, "yarn/..." for
 *                           yarn. Sometimes empty or "npm/…" even
 *                           under pnpm in Corepack-managed CI envs.
 *   npm_execpath            Path to the package-manager binary that
 *                           kicked off the lifecycle script. For
 *                           pnpm this contains the substring "pnpm";
 *                           for npm it contains "npm-cli.js"; for
 *                           yarn, "yarn.js".
 *
 * If EITHER signal positively identifies pnpm we accept; otherwise
 * we print the boxed error and exit 1.
 *
 * Why this lives as a Node script instead of `npx only-allow pnpm`:
 * `npx` is bundled with npm, and on Corepack CI the npx process can
 * reset npm_config_user_agent to "npm/..." before only-allow inspects
 * it, which made only-allow refuse pnpm itself.
 */
const ua = process.env.npm_config_user_agent ?? "";
const execpath = process.env.npm_execpath ?? "";

const uaSaysPnpm = ua.startsWith("pnpm/");
const execSaysPnpm = /\bpnpm\b/.test(execpath);

if (!uaSaysPnpm && !execSaysPnpm) {
  // Print the env we saw alongside the error so a future debugger
  // doesn't have to guess what the runner actually set.
  console.error(
    `\nDETECTED npm_config_user_agent=${JSON.stringify(ua)}` +
      `\nDETECTED npm_execpath=${JSON.stringify(execpath)}`,
  );
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
