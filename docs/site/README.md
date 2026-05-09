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

### pnpm only — no npm or yarn

This project blocks `npm install` and `yarn install` to keep the
lockfile and node_modules layout consistent across machines. Three
layers enforce it:

1. **`preinstall` script** in `package.json` runs `npx only-allow pnpm`,
   which detects the running package manager via
   `$npm_config_user_agent` and exits non-zero on anything but pnpm.
   This is the primary block — when you see
   `Use "pnpm install" for installation in this project` from
   `only-allow`, that's this layer firing.
2. **`engines.pnpm: ">=11"`** in `package.json` plus
   **`engine-strict=true`** in `.npmrc` — together pnpm refuses to
   install if you're on an old pnpm version. Catches the case where a
   contributor has a stale pnpm.
3. **A pre-commit hook** (`no-non-pnpm-lockfiles`) fails the commit if
   `package-lock.json` or `yarn.lock` end up tracked. Belt-and-suspenders
   for the case where someone bypasses the preinstall script (e.g. by
   running `npm install --ignore-scripts`).

## Building demo gifs

There are TWO demo pipelines:

**Auto-rendered** (`demos/` → `public/demos/`, gitignored):
`pnpm run build` runs `scripts/build-demos.mjs` first, which iterates `demos/*.toml`
and calls the Python renderer for any missing or stale gifs in `public/demos/`.
The renderer requires `uv` and the Python deps installed at the repo root
(`uv sync` from the repo root). These run on every Cloudflare deploy.

**Long-running** (`demos-long/` → `public/demos-long/`, committed):
For data-fetch widgets (rss_feed, mlb, coinbase, etc.) where 5 seconds isn't
enough, and Cloudflare can't run them anyway since the renderer makes live
HTTP calls. Run from the repo root:

```bash
make render-long-demos                              # render every long demo
make render-long-demo NAME=widget-coinbase          # render just one
```

Output lands in `docs/site/public/demos-long/` and IS committed to git. Each
TOML may declare `# requires-env: VAR` in a comment — if that env var isn't set,
the demo is skipped (so contributors without API keys for `etherscan` /
`weather` can still run the script without errors). A TOML may also declare
`# render-duration: N` to override the make target's 30-second default —
useful for widgets like `two_row` whose held-content cadence captures more
slowly than wallclock (the auto-render pipeline supports the same comment).

## Lint and format

```bash
pnpm run lint     # prettier --check . && astro check
pnpm run format   # prettier --write .
```

Or from the repo root: `make docs-lint` / `make docs-format`.

A pre-commit hook runs the same `lint` script automatically when you
commit a change inside `docs/site/` or `docs/content-source/` — fast
enough to catch formatting drift without slowing unrelated commits.
CI runs it too via the `docs-lint` job in `.github/workflows/ci.yml`.

## Deploy

A single GitHub Actions workflow handles all deploys to Cloudflare Pages.
Cloudflare's automatic Git-triggered builds are disabled — only this
workflow ever pushes to Cloudflare.

| Trigger                                                                         | Result                                            |
| ------------------------------------------------------------------------------- | ------------------------------------------------- |
| Push to `main` (touching `docs/`, `tools/render_demo/`, or the workflow itself) | Production deploy                                 |
| Open / update a PR (same path filter)                                           | Preview deploy at `<branch>.led-ticker.pages.dev` |
| Push to a feature branch with no PR                                             | Nothing — no build, no deploy                     |

The workflow lives at [`.github/workflows/docs-deploy.yml`](../../.github/workflows/docs-deploy.yml).

### One-time Cloudflare Pages dashboard setup

1. Cloudflare dashboard → Workers & Pages → Create → Pages → Connect to Git
2. Authorize Cloudflare to access this private repo
3. **Project name:** `led-ticker`
4. **Production branch:** `main`
5. **Build command** and **Build output directory:** can be left empty —
   Cloudflare won't run a build, GH Actions does. (If the dashboard
   requires values, fill in placeholders; they're inert.)
6. After the project is created, go to the project's **Build → Branch control** settings:
   - Turn OFF **Enable automatic production branch deployments**
   - **Preview branch:** set to **None (Disable automatic branch deployments)**

   This stops Cloudflare from running its own build on every push and
   leaves the GitHub Actions workflow as the only deploy path.

7. (Optional) Add a custom domain under Pages → Custom domains.

### One-time GitHub Actions secrets

The deploy workflow uses `cloudflare/wrangler-action`, which needs:

1. Repo Settings → Secrets and variables → Actions → New repository secret:
   - `CLOUDFLARE_API_TOKEN` — generate at Cloudflare dashboard → My Profile → API Tokens. Permissions: **Account → Cloudflare Pages → Edit** (and the account scope set to your account).
   - `CLOUDFLARE_ACCOUNT_ID` — your Cloudflare account ID, visible at the bottom of any Pages project's Settings page.

### Preview retention

Cloudflare keeps preview deployments around even after the PR merges or
closes. They don't surface anywhere unless someone has the URL. Manage
retention in the Pages dashboard if you want to clean them up.
