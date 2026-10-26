// Search-indexing contract for the agent-facing Markdown exports.
//
// llms-full.txt (and llms-small.txt, the /_llms-txt/ topic sets) are a
// plaintext copy of every docs page. Search engines must not INDEX them, or
// they compete with the HTML pages as the canonical copy of their own text.
//
// Mechanism: `X-Robots-Tag: noindex` in public/_headers (Cloudflare Pages).
// NOT a robots.txt Disallow — the two are mutually exclusive: a crawler can
// only see a noindex header on a URL it is allowed to fetch, and a
// robots-blocked URL that is linked from a crawlable page (the homepage links
// /llms-full.txt; /llms.txt links every export) still gets indexed URL-only. noindex is
// also engine-agnostic, and LLM agents ignore it, so agent access is untouched.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (rel) => readFileSync(new URL(rel, import.meta.url), "utf8");
const robots = read("../public/robots.txt");
const headers = read("../public/_headers");

/** Cloudflare Pages `_headers`: unindented line = path; indented = `Name: value`. */
function parseHeaders(text) {
  const rules = new Map(); // path -> [[name, value]]
  let current = null;
  for (const raw of text.split(/\r?\n/)) {
    if (!raw.trim() || raw.trim().startsWith("#")) continue;
    if (/^\s/.test(raw)) {
      const idx = raw.indexOf(":");
      assert.ok(current && idx !== -1, `malformed _headers line: ${JSON.stringify(raw)}`);
      current.push([raw.slice(0, idx).trim().toLowerCase(), raw.slice(idx + 1).trim()]);
    } else {
      current = [];
      rules.set(raw.trim(), current);
    }
  }
  return rules;
}

const rules = parseHeaders(headers);
const robotsTagFor = (path) =>
  (rules.get(path) ?? []).filter(([n]) => n === "x-robots-tag").map(([, v]) => v);

const NOINDEX_EXPORTS = ["/llms-full.txt", "/llms-small.txt", "/_llms-txt/*"];

for (const p of NOINDEX_EXPORTS) {
  test(`${p} is served with X-Robots-Tag: noindex`, () => {
    const tags = robotsTagFor(p);
    assert.equal(tags.length, 1, `expected exactly one X-Robots-Tag for ${p}, got ${tags.length}`);
    assert.match(tags[0], /(^|,)\s*noindex\s*(,|$)/i);
  });
}

test("X-Robots-Tag is set ONLY on the content exports — never on HTML or the index", () => {
  const tagged = [...rules.keys()].filter((p) => robotsTagFor(p).length > 0).sort();
  assert.deepEqual(tagged, [...NOINDEX_EXPORTS].sort());
  // /llms.txt is the entrypoint index: tiny, no page content — stays indexable.
  assert.deepEqual(robotsTagFor("/llms.txt"), []);
});

test("robots.txt keeps every URL crawlable so the noindex header can be seen", () => {
  const directives = robots
    .split(/\r?\n/)
    .map((l) => l.replace(/#.*/, "").trim())
    .filter(Boolean);
  const disallows = directives.filter(
    (l) => /^disallow\s*:/i.test(l) && !/^disallow\s*:\s*$/i.test(l),
  );
  assert.deepEqual(
    disallows,
    [],
    `robots.txt must not Disallow anything: ${disallows.join(" | ")}`,
  );
  assert.ok(
    directives.some((l) => /^user-agent\s*:\s*\*$/i.test(l)),
    "no `User-agent: *` group",
  );
  assert.match(robots, /^Sitemap: https:\/\/docs\.ledticker\.dev\/sitemap-index\.xml$/m);
});
