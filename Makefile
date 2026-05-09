.PHONY: dev hooks test lint typecheck format clean build-docker docs-dev docs-build docs-lint docs-format render-demo

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
