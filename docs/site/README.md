# led-ticker docs site

Astro Starlight site for the led-ticker documentation.

## Local development

```bash
cd docs/site
npm install
npm run dev
```

Visits `http://localhost:4321/led-ticker/` (Astro picks the port; check the terminal output).

## Building demo gifs

`npm run build` runs `scripts/build-demos.mjs` first, which iterates `demos/*.toml`
and calls the Python renderer for any missing or stale gifs in `public/demos/`.
The renderer requires `uv` and the Python deps installed at the repo root
(`uv sync` from the repo root).

## Deploy

GitHub Actions builds and deploys on push to `main`. See `.github/workflows/docs.yml`.
