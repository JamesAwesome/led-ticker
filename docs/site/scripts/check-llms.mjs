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

// --- llms.txt entrypoint lists every documentation set ---
const entry = existsSync(new URL("llms.txt", dist))
  ? readFileSync(new URL("llms.txt", dist), "utf8")
  : "";
const EXPECTED_SETS = [
  "widgets",
  "transitions",
  "configuration",
  "plugin-development",
  "hardware-setup",
];
for (const slug of EXPECTED_SETS) {
  if (!entry.includes(`/_llms-txt/${slug}.txt`))
    errors.push(`llms.txt does not list the "${slug}" documentation set`);
}

// --- each custom set exists, is non-empty, and contains its marker page ---
// Markers verified against the live export on 2026-07-14.
// NOTE: "Rasterization threshold for hires fonts" (the OPTIONS_TABLE_SENTINEL
// above) lives only in the widgets/* OptionsTable fact-packs (message,
// countdown, countup, image, gif) — it never lands in the configuration set,
// which has no OptionsTable-sourced content. The configuration marker below
// instead pins a sentence unique to concepts/fonts.mdx (same font_threshold
// topic, prose form) to prove that page landed in the set.
const SET_MARKERS = {
  widgets: "# two_row",
  transitions: "wipe_left",
  configuration: "anti-aliased during rasterization and then binarized to 1-bit",
  "plugin-development": "API_VERSION",
  "hardware-setup": "Bigsign reference build",
};
for (const [slug, marker] of Object.entries(SET_MARKERS)) {
  const p = new URL(`_llms-txt/${slug}.txt`, dist);
  if (!existsSync(p)) {
    errors.push(`missing dist/_llms-txt/${slug}.txt`);
    continue;
  }
  const body = readFileSync(p, "utf8");
  if (body.trim().length < 1000) errors.push(`dist/_llms-txt/${slug}.txt is suspiciously small`);
  if (!body.includes(marker))
    errors.push(`${slug} set is missing its marker page (sentinel: "${marker}")`);
}

// --- llms-small.txt is the config-author quick reference ---
// measured 427392 bytes on 2026-07-14; budget = measured + ~25%
const SMALL_BUDGET_BYTES = 550_000;
const smallPath = new URL("llms-small.txt", dist);
if (!existsSync(smallPath)) {
  errors.push("missing dist/llms-small.txt");
} else {
  const small = readFileSync(smallPath, "utf8");
  if (!small.includes("# two_row"))
    errors.push('llms-small.txt lost its widget content (sentinel: "# two_row")');
  if (small.includes("Bigsign reference build"))
    errors.push("llms-small.txt still contains hardware content — the exclude list regressed");
  if (Buffer.byteLength(small) > SMALL_BUDGET_BYTES)
    errors.push(
      `llms-small.txt is ${Buffer.byteLength(small)} bytes (budget ${SMALL_BUDGET_BYTES}) — pruning regressed`,
    );
}

// --- llms-full.txt must remain UNpruned ---
if (!full.includes("Bigsign reference build"))
  errors.push("llms-full.txt lost hardware content — full must stay complete");

if (errors.length) {
  console.error("check-llms FAILED:\n  - " + errors.join("\n  - "));
  process.exit(1);
}
console.log(
  "check-llms OK: llms.txt + sets + llms-full present, small pruned within budget, OptionsTable + TOML content preserved",
);
