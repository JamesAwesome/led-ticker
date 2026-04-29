.PHONY: dev hooks test lint typecheck format clean build-docker build-docker-pi5

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

# RGBMATRIX_REF pins the rpi-rgb-led-matrix fork/branch baked into the image.
# Default 'main' targets the existing Pi 4 sign; the bigsign target below
# overrides this with a Pi 5–capable ref (set when fork research lands).
RGBMATRIX_REF ?= main
RGBMATRIX_REF_PI5 ?= main

build-docker:  ## Build the production Pi 4 Docker image
	docker build --build-arg RGBMATRIX_REF=$(RGBMATRIX_REF) -t led-ticker:pi4 .

build-docker-pi5:  ## Build the bigsign Pi 5 Docker image
	docker build --build-arg RGBMATRIX_REF=$(RGBMATRIX_REF_PI5) -t led-ticker:pi5 .

# --- Cleanup ---

clean:  ## Remove build artifacts and caches
	rm -rf .venv/ .pytest_cache/ .mypy_cache/ .ruff_cache/ .coverage htmlcov/ dist/ *.egg-info src/*.egg-info
