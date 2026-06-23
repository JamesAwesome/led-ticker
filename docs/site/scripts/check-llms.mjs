// Guards the agent-facing Markdown export. Run AFTER `pnpm run build`.
// Fails if the llms.txt files are missing/empty or if the high-value
// OptionsTable field tables / TomlExample blocks did not survive into
// llms-full.txt (a future Astro/Starlight/plugin bump could silently gut them).
import { readFileSync, existsSync } from "node:fs";

const dist = new URL("../dist/", import.meta.url);
const required = ["llms.txt", "llms-full.txt"]; // llms-small.txt is nice-to-have
const errors = [];

for (const f of required) {
  const p = new URL(f, dist);
  if (!existsSync(p)) {
    errors.push(`missing dist/${f}`);
    continue;
  }
  const body = readFileSync(p, "utf8");
  if (body.trim().length < 200) errors.push(`dist/${f} is suspiciously small`);
}

const full = existsSync(new URL("llms-full.txt", dist))
  ? readFileSync(new URL("llms-full.txt", dist), "utf8")
  : "";

// Fidelity sentinels — confirmed present in the fact-pack tables, absent from prose.
const OPTIONS_TABLE_SENTINEL = "Rasterization threshold for hires fonts"; // font_threshold row, OptionsTable fact-packs
const TOML_FENCE_SENTINEL = "```toml"; // a TomlExample survived

if (!full.includes(OPTIONS_TABLE_SENTINEL))
  errors.push(
    `llms-full.txt is missing the OptionsTable field reference (sentinel: "${OPTIONS_TABLE_SENTINEL}") — widget option tables did not survive the export`,
  );
if (!full.includes(TOML_FENCE_SENTINEL))
  errors.push(
    `llms-full.txt is missing a TOML code fence (sentinel: "${TOML_FENCE_SENTINEL}") — TomlExample blocks did not survive the export`,
  );

if (errors.length) {
  console.error("check-llms FAILED:\n  - " + errors.join("\n  - "));
  process.exit(1);
}
console.log(
  "check-llms OK: llms.txt + llms-full.txt present, OptionsTable + TOML content preserved",
);
