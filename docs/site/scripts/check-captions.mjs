// Guards DemoGif caption rendering. Run AFTER `pnpm run build`.
// Captions are authored with Markdown backticks, which only DemoGif turns into
// <code>; if that ever regresses, readers see literal backticks in every
// caption (the homepage hero included) and screen readers get them in alt
// text. Fails on a backtick in any <figcaption> outside <code>, or in any alt.
import { readFileSync, readdirSync, existsSync, realpathSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const FIGCAPTION = /<figcaption[^>]*>([\s\S]*?)<\/figcaption>/g;
const ALT = /\balt="([^"]*)"/g;

// Literal-backtick problems in one page's HTML, as short descriptions.
export function captionBacktickProblems(html) {
  const problems = [];
  for (const [, inner] of html.matchAll(FIGCAPTION)) {
    if (inner.replace(/<code[\s\S]*?<\/code>/g, "").includes("`"))
      problems.push(`figcaption shows a literal backtick: ${inner.slice(0, 80)}`);
  }
  for (const [, alt] of html.matchAll(ALT)) {
    if (alt.includes("`")) problems.push(`alt text contains a backtick: ${alt.slice(0, 80)}`);
  }
  return problems;
}

function* htmlFiles(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name);
    if (entry.isDirectory()) yield* htmlFiles(p);
    else if (entry.name.endsWith(".html")) yield p;
  }
}

function main() {
  const dist = fileURLToPath(new URL("../dist/", import.meta.url));
  const errors = [];
  if (!existsSync(dist)) {
    errors.push("missing dist/ — run `pnpm run build` first");
  } else {
    for (const file of htmlFiles(dist)) {
      for (const p of captionBacktickProblems(readFileSync(file, "utf8")))
        errors.push(`${relative(dist, file)}: ${p}`);
    }
  }

  if (errors.length) {
    console.error("check-captions FAILED:\n  - " + errors.join("\n  - "));
    process.exit(1);
  }
  console.log("check-captions OK: no literal backticks in figcaptions or alt text");
}

// Run only as the CLI, not when a test imports the predicate. Compare real
// paths: Node resolves symlinks for import.meta.url but not argv[1].
if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) main();
