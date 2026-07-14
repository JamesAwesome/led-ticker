// RelatedPages slug normalization: a slug pointing at a directory index page
// ("transitions/index") must link to the directory URL ("/transitions/"), not
// the nonexistent "/transitions/index/" (was a live 404 on two pages).

import { test } from "node:test";
import assert from "node:assert/strict";

import { relatedHref, relatedLabel } from "../src/utils/related-pages.mjs";

test("plain slug maps to /slug/", () => {
  assert.equal(relatedHref("concepts/display"), "/concepts/display/");
  assert.equal(relatedLabel("concepts/display"), "concepts/display");
});

test("trailing /index collapses to the directory URL", () => {
  assert.equal(relatedHref("transitions/index"), "/transitions/");
  assert.equal(relatedLabel("transitions/index"), "transitions");
});

test("bare index maps to the site root", () => {
  assert.equal(relatedHref("index"), "/");
  assert.equal(relatedLabel("index"), "home");
});
