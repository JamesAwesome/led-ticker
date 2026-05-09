#!/usr/bin/env bash
# Cloudflare Pages build entry point.
#
# Cloudflare's build env provides Node and Python out of the box, but
# not `uv`. We install uv via the official script, sync Python deps,
# then run the Astro build (which prebuilds demo gifs via the
# build-demos.mjs script that shells out to the Python renderer).
#
# Set this as the build command in the Cloudflare Pages dashboard:
#   bash docs/site/cloudflare-build.sh
#
# Build output directory: docs/site/dist
# Production branch: main

set -euo pipefail

echo "[cloudflare-build] installing uv"
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "[cloudflare-build] uv version: $(uv --version)"

echo "[cloudflare-build] syncing Python deps"
uv sync

echo "[cloudflare-build] installing Node deps for the docs site"
cd docs/site
npm ci

echo "[cloudflare-build] building docs site (renders demo gifs first)"
npm run build

echo "[cloudflare-build] done. Output in docs/site/dist"
