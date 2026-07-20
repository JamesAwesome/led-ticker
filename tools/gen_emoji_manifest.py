#!/usr/bin/env python3
"""Build tools/assets/emoji_manifest.txt: one `U+XXXX<TAB>slug` line per
single-codepoint standard emoji, slugs from CLDR short names.

Run ONCE on a dev machine (network); the committed manifest is the
reviewable source of truth for what's in the pack and what it's named.

    uv run python tools/gen_emoji_manifest.py > tools/assets/emoji_manifest.txt

Sources:
- CLDR annotations (short names):
  https://raw.githubusercontent.com/unicode-org/cldr-json/main/cldr-json/cldr-annotations-full/annotations/en/annotations.json
Inclusion: single-codepoint entries with a `tts` name. Exclusions:
regional indicators (U+1F1E6-1F1FF), skin-tone modifiers (U+1F3FB-1F3FF),
ZWJ/VS/keycap components, and any codepoint already covered by the curated
`_UNICODE_EMOJI_MAP` (curated wins at the SOURCE).
"""

import json
import re
import sys
import unicodedata
import urllib.request

_CLDR_URL = (
    "https://raw.githubusercontent.com/unicode-org/cldr-json/main/"
    "cldr-json/cldr-annotations-full/annotations/en/annotations.json"
)
_SLUG_RE = re.compile(r"^[a-z_][a-z0-9_.]*$")


def _slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    if not s or not s[0].isalpha():
        s = f"e_{s}"
    return s


def main() -> None:
    from led_ticker.pixel_emoji import _UNICODE_EMOJI_MAP, _emoji_key

    curated_keys = set(_UNICODE_EMOJI_MAP)
    with urllib.request.urlopen(_CLDR_URL, timeout=60) as r:
        ann = json.load(r)["annotations"]["annotations"]
    seen: dict[str, int] = {}
    out: list[tuple[int, str]] = []
    for chars, data in ann.items():
        if len(chars) != 1:
            continue  # single-codepoint scope (spec decision 1)
        cp = ord(chars)
        if 0x1F1E6 <= cp <= 0x1F1FF or 0x1F3FB <= cp <= 0x1F3FF:
            continue
        if _emoji_key(chars) in curated_keys:
            continue  # curated wins at the source
        tts = data.get("tts")
        if not tts:
            continue
        slug = _slugify(tts[0])
        n = seen.get(slug, 0) + 1
        seen[slug] = n
        if n > 1:
            slug = f"{slug}_{n}"
        assert _SLUG_RE.match(slug), slug
        out.append((cp, slug))
    for cp, slug in sorted(out):
        sys.stdout.write(f"U+{cp:04X}\t{slug}\n")


if __name__ == "__main__":
    main()
