// Sitemap <lastmod> support: map each docs URL to the git last-commit date of
// its source .mdx file. Runs against the real repo history, so assertions stay
// structural (ISO dates, known pages resolve) rather than pinning exact dates.

import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { buildLastmodMap, lastmodForUrl } from "../scripts/git-lastmod.mjs";

const SITE = "https://docs.ledticker.dev";
const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const contentDir = "docs/site/src/content/docs";

const map = buildLastmodMap(repoRoot, contentDir);

test("map contains ISO-8601 dates for content files", () => {
  assert.ok(map.size > 20, `expected >20 entries, got ${map.size}`);
  for (const [file, date] of map) {
    assert.match(file, /^docs\/site\/src\/content\/docs\//);
    assert.match(date, /^\d{4}-\d{2}-\d{2}T/, `bad date for ${file}: ${date}`);
    break;
  }
});

test("a leaf page URL resolves to its .mdx commit date", () => {
  const d = lastmodForUrl(`${SITE}/widgets/two_row/`, map, SITE, contentDir);
  assert.match(d, /^\d{4}-\d{2}-\d{2}T/);
});

test("a directory index URL resolves via index.mdx", () => {
  const d = lastmodForUrl(`${SITE}/widgets/`, map, SITE, contentDir);
  assert.match(d, /^\d{4}-\d{2}-\d{2}T/);
});

test("the homepage resolves via the root index.mdx", () => {
  const d = lastmodForUrl(`${SITE}/`, map, SITE, contentDir);
  assert.match(d, /^\d{4}-\d{2}-\d{2}T/);
});

test("an unknown URL returns undefined (page just omits lastmod)", () => {
  const d = lastmodForUrl(`${SITE}/no/such/page/`, map, SITE, contentDir);
  assert.equal(d, undefined);
});
