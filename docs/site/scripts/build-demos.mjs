#!/usr/bin/env node
/**
 * Prebuild step: render each demo TOML to a gif if missing or stale.
 *
 * Walks `demos/*.toml`. For each, checks `public/demos/<name>.gif`.
 * If the gif is missing or older than the TOML, runs the Python renderer.
 * Any failure aborts the build with a non-zero exit so we never deploy
 * with broken demo gifs.
 */

import { existsSync, mkdirSync, readdirSync, readFileSync, statSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SITE_ROOT = resolve(__dirname, "..");
const REPO_ROOT = resolve(SITE_ROOT, "..", "..");
const DEMOS_DIR = join(SITE_ROOT, "demos");
const OUT_DIR = join(SITE_ROOT, "public", "demos");
const RENDERER = join(REPO_ROOT, "tools", "render_demo", "render.py");

const DEFAULT_DURATION_S = 5;

function isStale(gifPath, tomlPath) {
  if (!existsSync(gifPath)) return true;
  return statSync(tomlPath).mtimeMs > statSync(gifPath).mtimeMs;
}

// Read an optional `# render-duration: N` comment from the TOML so demos
// that need a longer capture (e.g. a wide marquee that has to complete one
// full traversal before the gif loops back) can declare it inline. Falls
// back to DEFAULT_DURATION_S if absent or malformed.
function readRenderDuration(tomlPath) {
  const text = readFileSync(tomlPath, "utf8");
  const match = text.match(/^#\s*render-duration:\s*([\d.]+)/m);
  if (!match) return DEFAULT_DURATION_S;
  const value = Number(match[1]);
  return Number.isFinite(value) && value > 0 ? value : DEFAULT_DURATION_S;
}

function renderDemo(tomlPath, gifPath) {
  const duration = readRenderDuration(tomlPath);
  console.log(`[build-demos] rendering ${tomlPath} -> ${gifPath} (${duration}s)`);
  const result = spawnSync(
    "uv",
    ["run", "python", RENDERER, tomlPath, "-o", gifPath, "--duration", String(duration)],
    { cwd: REPO_ROOT, stdio: "inherit" },
  );
  if (result.status !== 0) {
    console.error(`[build-demos] FAILED: ${tomlPath}`);
    process.exit(1);
  }
}

function main() {
  if (!existsSync(DEMOS_DIR)) {
    console.log(`[build-demos] no demos dir at ${DEMOS_DIR}; nothing to do`);
    return;
  }
  mkdirSync(OUT_DIR, { recursive: true });

  const tomls = readdirSync(DEMOS_DIR).filter((f) => f.endsWith(".toml"));
  if (tomls.length === 0) {
    console.log(`[build-demos] no .toml files in ${DEMOS_DIR}; nothing to do`);
    return;
  }

  let rendered = 0;
  let skipped = 0;
  for (const file of tomls) {
    const tomlPath = join(DEMOS_DIR, file);
    const gifName = file.replace(/\.toml$/, ".gif");
    const gifPath = join(OUT_DIR, gifName);
    if (isStale(gifPath, tomlPath)) {
      renderDemo(tomlPath, gifPath);
      rendered++;
    } else {
      skipped++;
    }
  }
  console.log(`[build-demos] done. rendered=${rendered} skipped=${skipped}`);
}

main();
