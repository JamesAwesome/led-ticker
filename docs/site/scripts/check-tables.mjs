// Guards GFM pipe-table rendering. Run AFTER `pnpm run build`.
// Tables have silently degraded to literal `| a | b |` text once already (the
// Astro 6.4 Markdown rework), and since Starlight 0.42 they rely entirely on
// the default pipeline's GFM support — a future Astro/Starlight/MDX bump that
// drops it would pass every other check. Fails if any built page shows a raw
// table delimiter row outside code, or the config-options page has no tables.
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// A GFM delimiter row (`|---|:--:|`) that survived as text means the table
// was never parsed. Smart punctuation rewrites the hyphens of an unparsed
// table into en/em dashes before the HTML is written, so match the whole
// U+2010–U+2015 dash range too — ASCII-only never fires on a real build.
const DELIMITER_ROW = /\|\s*:?[-‐-―]+:?\s*\|/;

// Code blocks/spans may legitimately show a delimiter row, so drop them.
const stripCode = (html) =>
  html.replace(/<pre[\s\S]*?<\/pre>/g, "").replace(/<code[\s\S]*?<\/code>/g, "");

export function hasUnrenderedTable(html) {
  return DELIMITER_ROW.test(stripCode(html));
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
      if (hasUnrenderedTable(readFileSync(file, "utf8")))
        errors.push(
          `${relative(dist, file)} contains an unrendered pipe-table (literal delimiter row)`,
        );
    }
    const options = join(dist, "reference/config-options/index.html");
    if (!existsSync(options) || !readFileSync(options, "utf8").includes("<table"))
      errors.push("reference/config-options has no <table> — markdown tables are not rendering");
  }

  if (errors.length) {
    console.error("check-tables FAILED:\n  - " + errors.join("\n  - "));
    process.exit(1);
  }
  console.log("check-tables OK: no unrendered pipe-tables; config-options renders its tables");
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) main();
