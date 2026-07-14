// Tests for the Pages Function middleware that 301s the led-ticker.pages.dev
// default domain to the canonical docs.ledticker.dev host (SEO: Google was
// indexing the pages.dev duplicate instead of the real domain).
//
// Run with: pnpm test  (node --test tests/)

import { test } from "node:test";
import assert from "node:assert/strict";

import { onRequest } from "../functions/_middleware.js";

const NEXT_RESPONSE = new Response("static asset body");

function makeContext(url) {
  return {
    request: new Request(url),
    next: () => Promise.resolve(NEXT_RESPONSE),
  };
}

test("pages.dev host 301s to docs.ledticker.dev preserving the path", async () => {
  const res = await onRequest(makeContext("https://led-ticker.pages.dev/widgets/two_row/"));
  assert.equal(res.status, 301);
  assert.equal(res.headers.get("location"), "https://docs.ledticker.dev/widgets/two_row/");
});

test("pages.dev redirect preserves the query string", async () => {
  const res = await onRequest(makeContext("https://led-ticker.pages.dev/search/?q=emoji"));
  assert.equal(res.status, 301);
  assert.equal(res.headers.get("location"), "https://docs.ledticker.dev/search/?q=emoji");
});

test("canonical docs host passes through untouched", async () => {
  const res = await onRequest(makeContext("https://docs.ledticker.dev/widgets/two_row/"));
  assert.equal(res, NEXT_RESPONSE);
});

test("PR preview subdomains are NOT redirected", async () => {
  // Preview deploys live on <branch>.led-ticker.pages.dev — redirecting
  // them to production docs would break every PR preview link.
  const res = await onRequest(makeContext("https://my-feature-branch.led-ticker.pages.dev/"));
  assert.equal(res, NEXT_RESPONSE);
});
