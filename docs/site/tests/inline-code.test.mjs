// DemoGif caption backticks render as <code>, and alt text loses them. The
// unbalanced case must not guess — it falls back to the caption as plain text.

import { test } from "node:test";
import assert from "node:assert/strict";

import { inlineCodeSegments, stripInlineCode } from "../src/utils/inline-code.mjs";

test("backticked spans become code segments", () => {
  assert.deepEqual(inlineCodeSegments("A `message` widget with `font_color`"), [
    { text: "A ", code: false },
    { text: "message", code: true },
    { text: " widget with ", code: false },
    { text: "font_color", code: true },
  ]);
});

test("caption without backticks is one plain segment", () => {
  assert.deepEqual(inlineCodeSegments("A plain caption"), [
    { text: "A plain caption", code: false },
  ]);
});

test("unbalanced backticks fall back to plain text", () => {
  const caption = "A `message widget";
  assert.deepEqual(inlineCodeSegments(caption), [{ text: caption, code: false }]);
});

test("alt text drops backticks", () => {
  assert.equal(stripInlineCode("A `message` widget"), "A message widget");
});
