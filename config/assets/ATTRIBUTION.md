# Sample-media attribution

The repo ships one sample-media asset family (the Firebird phoenix), used by the example
configs and docs demos. All formats are derived from a single CC0 source by
`tools/derive_phoenix_assets.py`.

- **Source:** "pixel-phoenix" by **zonked** — https://opengameart.org/content/pixel-phoenix
- **License:** CC0 1.0 (public domain) — https://creativecommons.org/publicdomain/zero/1.0/
  No attribution is required; this record is kept for provenance.
- **Vendored source:** `config/assets/_src/phoenix-cc0-no-bg.gif` (20×20, animated, transparent).
- **Derived:** `phoenix.gif`, `phoenix_transparent.gif`, `phoenix.png`, `phoenix_transparent.png`,
  `phoenix.webp` (220×220, nearest-neighbor upscale).

Real-brand or third-party media is never committed — it is gitignored per-deployment.
