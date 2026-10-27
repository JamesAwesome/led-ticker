// Inline `code` in plain-string props (DemoGif captions). Captions are authored
// with Markdown backticks — DOCS-STYLE's own model caption does — but a prop is
// rendered as escaped text, so readers saw literal backticks. Split into
// alternating text/code segments; the component renders each as auto-escaped
// text, so no set:html is involved.

// [{ text, code }] segments. Unbalanced backticks fall back to one plain
// segment rather than guessing which span was meant. Single backticks only:
// a code span can't itself contain a backtick (no ``a`b`` form).
/** @param {string} text @returns {{ text: string, code: boolean }[]} */
export function inlineCodeSegments(text) {
  const parts = text.split("`");
  if (parts.length % 2 === 0) return [{ text, code: false }];
  return parts.map((p, i) => ({ text: p, code: i % 2 === 1 })).filter((s) => s.text !== "");
}

// Alt text has no markup: drop the backticks so screen readers don't
// announce them.
/** @param {string} text @returns {string} */
export function stripInlineCode(text) {
  return text.replaceAll("`", "");
}
