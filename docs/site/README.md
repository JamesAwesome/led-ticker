# led-ticker docs site

Astro Starlight site for the led-ticker documentation. Hosted on Cloudflare Pages.

## Local development

This project uses [pnpm](https://pnpm.io/) via Node's built-in [corepack](https://nodejs.org/api/corepack.html).
The pinned pnpm version lives in `package.json`'s `packageManager` field; `corepack enable`
activates it automatically.

```bash
cd docs/site
corepack enable
pnpm install
pnpm run dev
```

Visits `http://localhost:4321/` (Astro picks the port; check the terminal output).

If `corepack enable` fails (some Node installs ship without it), install pnpm directly:

```bash
npm install -g pnpm@11
pnpm install
pnpm run dev
```

## Building demo gifs

`pnpm run build` runs `scripts/build-demos.mjs` first, which iterates `demos/*.toml`
and calls the Python renderer for any missing or stale gifs in `public/demos/`.
The renderer requires `uv` and the Python deps installed at the repo root
(`uv sync` from the repo root).

## Deploy (Cloudflare Pages)

The site uses Cloudflare Pages with two build paths:

- **Production (push to `main`)** — Cloudflare's GitHub integration auto-builds and deploys via the build command in the dashboard.
- **PR previews** — `.github/workflows/docs-pr-preview.yml` triggers on `pull_request` events and deploys via `cloudflare/wrangler-action`. Random feature-branch pushes (no PR) do NOT build.

### One-time Cloudflare Pages dashboard setup

1. Cloudflare dashboard → Workers & Pages → Create → Pages → Connect to Git
2. Authorize Cloudflare to access this private repo
3. **Project name:** `led-ticker`
4. **Production branch:** `main`
5. **Build command:** `bash docs/site/cloudflare-build.sh`
6. **Build output directory:** `docs/site/dist`
7. **Settings → Builds & deployments → Configure preview deployments → None.**
   This stops Cloudflare from auto-building every non-production branch. PR
   previews come from the GH Actions workflow instead.
8. (Optional) Add a custom domain under Pages → Custom domains.

### One-time GitHub Actions secrets

The PR preview workflow uses `cloudflare/wrangler-action`, which needs:

1. Repo Settings → Secrets and variables → Actions → New repository secret:
   - `CLOUDFLARE_API_TOKEN` — generate at Cloudflare dashboard → My Profile → API Tokens. Permissions: **Account → Cloudflare Pages → Edit** (and the account scope set to your account).
   - `CLOUDFLARE_ACCOUNT_ID` — your Cloudflare account ID, visible at the bottom of any Pages project's Settings page.

PR previews after merge: Cloudflare keeps preview deployments around but they don't surface anywhere unless someone has the URL. Manage retention in the Pages dashboard.
