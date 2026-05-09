.PHONY: dev hooks test lint typecheck format clean build-docker docs-dev docs-build docs-lint docs-format render-demo render-long-demos render-long-demo

# --- Developer Setup ---

dev:  ## Install package with dev dependencies and pre-commit hooks
	uv sync --extra dev
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push

hooks:  ## Install pre-commit hooks
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push

# --- Testing ---

test:  ## Run pytest with coverage (no Docker needed)
	PYTHONPATH=tests/stubs uv run pytest -s --cov=src/ --cov-report=term-missing

# --- Quality ---

lint:  ## Run ruff linter
	uv run ruff check src/ tests/

typecheck:  ## Run pyright type checker
	uv run pyright src/

format:  ## Run ruff formatter
	uv run ruff format src/ tests/

# --- Docker (production image only) ---

# rgbmatrix fork is hardcoded in the Dockerfile (jamesawesome/main).
# Validated to run on both the Pi 4 sign and the Pi 5 bigsign.
build-docker:  ## Build the production Docker image (Pi 4 + Pi 5)
	docker build -t led-ticker .

# --- Cleanup ---

clean:  ## Remove build artifacts and caches
	rm -rf .venv/ .pytest_cache/ .mypy_cache/ .ruff_cache/ .coverage htmlcov/ dist/ *.egg-info src/*.egg-info

# --- Docs site ---

docs-dev:  ## Run the Astro Starlight dev server (http://localhost:4321/)
	cd docs/site && (corepack enable 2>/dev/null || true) && pnpm install && node scripts/build-demos.mjs && pnpm run dev

docs-build:  ## Build the docs site to docs/site/dist/
	cd docs/site && (corepack enable 2>/dev/null || true) && pnpm install --frozen-lockfile && pnpm run build

docs-lint:  ## Lint the docs site (prettier --check + astro check)
	cd docs/site && (corepack enable 2>/dev/null || true) && pnpm install --frozen-lockfile && pnpm run lint

docs-format:  ## Auto-format the docs site with prettier
	cd docs/site && (corepack enable 2>/dev/null || true) && pnpm install --frozen-lockfile && pnpm run format

render-demo:  ## Render a single demo gif. Usage: make render-demo CONFIG=path/to.toml OUT=out.gif
	uv run python tools/render_demo/render.py $(CONFIG) -o $(OUT)

# Long-running widget demos (data-fetch widgets — coinbase, mlb, rss_feed, …).
# Source TOMLs in docs/site/demos-long/, output to docs/site/public/demos-long/
# which IS committed to git (vs the auto-render path under public/demos/ which
# is gitignored and regenerates on every Cloudflare build). Cloudflare can't run
# these — they make live HTTP calls and some need API keys not in CI.

render-long-demos:  ## Render every long-running widget demo (~30 sec each); local only
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	for toml in docs/site/demos-long/*.toml; do \
		[ -f "$$toml" ] || continue; \
		name=$$(basename "$$toml" .toml); \
		out="docs/site/public/demos-long/$$name.gif"; \
		req=$$(grep -E '^# requires-env:' "$$toml" | head -1 | awk '{print $$3}'); \
		if [ -n "$$req" ] && [ -z "$$(printenv $$req)" ]; then \
			echo "[render-long-demos] SKIP $$name (needs $$req — add it to .env or export it to render)"; \
			continue; \
		fi; \
		echo "[render-long-demos] $$toml -> $$out"; \
		uv run python tools/render_demo/render.py "$$toml" -o "$$out" --duration 30 || exit 1; \
	done

render-long-demo:  ## Render one long-running demo. Usage: make render-long-demo NAME=widget-coinbase
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	uv run python tools/render_demo/render.py docs/site/demos-long/$(NAME).toml \
		-o docs/site/public/demos-long/$(NAME).gif --duration 30
