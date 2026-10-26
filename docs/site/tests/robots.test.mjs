// robots.txt contract. Search-engine crawlers must skip the agent-facing
// Markdown exports (a full plaintext copy of every page) so they can never
// out-compete the HTML pages as the canonical copy of that text, while every
// other client — including LLM agents that honor robots.txt — keeps full
// access. The exclusion is scoped per-crawler ON PURPOSE: a blanket
// `User-agent: *` Disallow would also lock out the agents the files exist for.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const robots = readFileSync(new URL("../public/robots.txt", import.meta.url), "utf8");

/** Parse robots.txt into groups: { agents: string[], rules: [directive, path][] }. */
function parseGroups(text) {
  const groups = [];
  let current = null;
  let lastWasAgent = false;
  for (const raw of text.split("\n")) {
    const line = raw.replace(/#.*/, "").trim();
    if (!line) continue;
    const idx = line.indexOf(":");
    if (idx === -1) continue;
    const directive = line.slice(0, idx).trim().toLowerCase();
    const value = line.slice(idx + 1).trim();
    if (directive === "user-agent") {
      if (!lastWasAgent) {
        current = { agents: [], rules: [] };
        groups.push(current);
      }
      current.agents.push(value.toLowerCase());
      lastWasAgent = true;
    } else if (directive === "allow" || directive === "disallow") {
      lastWasAgent = false;
      current?.rules.push([directive, value]);
    } else {
      lastWasAgent = false;
    }
  }
  return groups;
}

const groups = parseGroups(robots);
const groupFor = (agent) => groups.find((g) => g.agents.includes(agent));
const disallowed = (g) => g.rules.filter(([d]) => d === "disallow").map(([, p]) => p);
const allowed = (g) => g.rules.filter(([d]) => d === "allow").map(([, p]) => p);

const LLMS_CONTENT_EXPORTS = ["/llms-full.txt", "/llms-small.txt", "/_llms-txt/"];

test("the wildcard group keeps the whole site open, exports included", () => {
  const g = groupFor("*");
  assert.ok(g, "no `User-agent: *` group");
  assert.deepEqual(disallowed(g), []);
  assert.ok(allowed(g).includes("/"));
});

for (const bot of ["googlebot", "bingbot"]) {
  test(`${bot} is told to skip the Markdown content exports but nothing else`, () => {
    const g = groupFor(bot);
    assert.ok(
      g,
      `no group names ${bot} — a crawler-specific group is required because ` +
        `a named group REPLACES the * group for that crawler`,
    );
    // The named group replaces `*` for this crawler, so it must restate Allow: /.
    assert.ok(allowed(g).includes("/"), `${bot} group must restate \`Allow: /\``);
    for (const p of LLMS_CONTENT_EXPORTS) {
      assert.ok(disallowed(g).includes(p), `${bot} group must Disallow ${p}`);
    }
    // The entrypoint index is tiny and carries no page content — leave it crawlable.
    assert.ok(!disallowed(g).includes("/llms.txt"), "/llms.txt (the index) stays crawlable");
    // Nothing beyond the exports may be blocked: the HTML pages are the point.
    const extra = disallowed(g).filter((p) => !LLMS_CONTENT_EXPORTS.includes(p));
    assert.deepEqual(extra, [], `unexpected Disallow for ${bot}: ${extra.join(", ")}`);
  });
}

test("sitemap index is advertised", () => {
  assert.match(robots, /^Sitemap: https:\/\/docs\.ledticker\.dev\/sitemap-index\.xml$/m);
});
