// Sitemap <lastmod> support: derive each page's last-modified date from the
// git commit history of its source file, so the sitemap reports real change
// dates instead of nothing (or, worse, the build timestamp — which would
// claim every page changed on every deploy).

import { execFileSync } from "node:child_process";

/**
 * One `git log` pass over the docs content tree. Returns a Map of
 * repo-relative file path -> ISO-8601 committer date of the most recent
 * commit touching it (first occurrence in log order wins).
 */
export function buildLastmodMap(repoRoot, contentDir) {
  const out = execFileSync(
    "git",
    ["log", "--format=__COMMIT__%cI", "--name-only", "--", contentDir],
    { cwd: repoRoot, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 },
  );
  const map = new Map();
  let date = null;
  for (const line of out.split("\n")) {
    if (line.startsWith("__COMMIT__")) {
      date = line.slice("__COMMIT__".length);
    } else if (line && date && !map.has(line)) {
      map.set(line, date);
    }
  }
  return map;
}

/**
 * Resolve a page URL to its source file's lastmod, or undefined when no
 * candidate file is in the map (the sitemap entry just omits <lastmod>).
 */
export function lastmodForUrl(url, map, site, contentDir) {
  const slug = url.replace(site, "").replace(/^\/+|\/+$/g, "");
  const candidates = slug
    ? [
        `${contentDir}/${slug}.mdx`,
        `${contentDir}/${slug}/index.mdx`,
        `${contentDir}/${slug}.md`,
        `${contentDir}/${slug}/index.md`,
      ]
    : [`${contentDir}/index.mdx`, `${contentDir}/index.md`];
  for (const c of candidates) {
    const d = map.get(c);
    if (d) return d;
  }
  return undefined;
}
