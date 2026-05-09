#!/usr/bin/env bash
# Cloudflare Pages build entry point.
#
# Cloudflare's build env provides Node and Python out of the box, but
# not `uv` or pre-activated pnpm. We:
#   1. Install uv via the official script
#   2. Enable corepack and activate the pnpm version pinned in
#      docs/site/package.json's `packageManager` field
#   3. Sync Python deps so the gif renderer can import led_ticker
#   4. pnpm install + pnpm run build (which prebuilds demo gifs via
#      the build-demos.mjs script that shells out to uv run python)
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

echo "[cloudflare-build] enabling corepack"
corepack enable

echo "[cloudflare-build] syncing Python deps"
uv sync

echo "[cloudflare-build] installing Node deps for the docs site (pnpm)"
cd docs/site
pnpm install --frozen-lockfile

echo "[cloudflare-build] building docs site (renders demo gifs first)"
pnpm run build

echo "[cloudflare-build] done. Output in docs/site/dist"
