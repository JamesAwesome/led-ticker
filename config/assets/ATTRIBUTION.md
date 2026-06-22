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

Real-brand / customer-IP media is not committed — users add their own locally (drop files
into `config/assets/` and reference them in config). The repo also ships `pride.gif` and
`pride_trans.gif` as generic demo assets; these have been in the project since its earliest
public history and do not carry a known licence record. They are tracked here for now and
will be replaced with project-generated CC0 equivalents in a follow-up (tracked).
