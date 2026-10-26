// check-tables tripwire: pin what counts as an unrendered pipe-table. The
// degraded fixtures are verbatim shapes captured from real builds (GFM off
// site-wide, and a single malformed table) — smart punctuation turns the
// delimiter hyphens into en/em dashes, which an ASCII-only regex misses.

import { test } from "node:test";
import assert from "node:assert/strict";

import { hasUnrenderedTable } from "../scripts/check-tables.mjs";

test("GFM-off build: en/em-dash delimiter row is caught", () => {
  const html =
    "<p>| Field | Type | Default | Notes |\n| ––––––––––––– | —— | –––––––– | ——— |\n" +
    '| <code dir="auto">rows</code> | int | 1 | x |</p>';
  assert.equal(hasUnrenderedTable(html), true);
});

test("single malformed table (em-dash cells) is caught", () => {
  assert.equal(hasUnrenderedTable("<p>| A | B | C |\n| — | — |\n| 1 | 2 | 3 |</p>"), true);
});

test("ASCII delimiter row (smart punctuation off) is caught", () => {
  assert.equal(hasUnrenderedTable("<p>| a | b |\n| :--- | ---: |</p>"), true);
});

test("rendered table is not flagged", () => {
  const html =
    "<table><thead><tr><th>a</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>";
  assert.equal(hasUnrenderedTable(html), false);
});

test("delimiter rows inside code blocks and spans are ignored", () => {
  const html =
    '<pre class="x"><code>| a | b |\n|---|---|</code></pre>' +
    "<p>Use <code>|---|</code> rows.</p>";
  assert.equal(hasUnrenderedTable(html), false);
});
