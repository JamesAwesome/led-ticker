// Slug → link normalization for the RelatedPages component. A slug that
// names a directory index page ("transitions/index") must link to the
// directory URL ("/transitions/") — "/transitions/index/" is a 404.

function normalize(slug) {
  return slug.replace(/(^|\/)index$/, "").replace(/\/$/, "");
}

export function relatedHref(slug) {
  const s = normalize(slug);
  return s ? `/${s}/` : "/";
}

export function relatedLabel(slug) {
  return normalize(slug) || "home";
}
