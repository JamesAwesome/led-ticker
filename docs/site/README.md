# led-ticker docs site

Astro Starlight site for the led-ticker documentation. Hosted on Cloudflare Pages.

## Local development

```bash
cd docs/site
npm install
npm run dev
```

Visits `http://localhost:4321/` (Astro picks the port; check the terminal output).

## Building demo gifs

`npm run build` runs `scripts/build-demos.mjs` first, which iterates `demos/*.toml`
and calls the Python renderer for any missing or stale gifs in `public/demos/`.
The renderer requires `uv` and the Python deps installed at the repo root
(`uv sync` from the repo root).

## Deploy (Cloudflare Pages)

The site auto-deploys on push to `main` via Cloudflare Pages' GitHub
integration. One-time setup:

1. Cloudflare dashboard → Workers & Pages → Create → Pages → Connect to Git
2. Authorize Cloudflare to access this private repo
3. Production branch: `main`
4. Build command: `bash docs/site/cloudflare-build.sh`
5. Build output directory: `docs/site/dist`
6. (Optional) Add a custom domain under Pages → Custom domains

The build script (`cloudflare-build.sh`) installs `uv`, syncs Python
deps, runs `npm ci`, and runs `npm run build` (which prebuilds demo
gifs via the Python renderer, then runs `astro build`).

PR previews at `<pr-id>.<project>.pages.dev` are produced automatically;
production deploys to the project's `pages.dev` URL (or your custom
domain).
