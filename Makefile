.PHONY: dev test lint format clean build-docker

# --- Developer Setup ---

dev:  ## Install package with dev dependencies
	uv sync --extra dev

# --- Testing ---

test:  ## Run pytest with coverage (no Docker needed)
	PYTHONPATH=tests/stubs uv run pytest -s --cov=src/ --cov-report=term-missing

# --- Quality ---

lint:  ## Run ruff linter
	uv run ruff check src/ tests/

format:  ## Run ruff formatter
	uv run ruff format src/ tests/

# --- Docker (production image only) ---

build-docker:  ## Build the production Pi Docker image
	docker build -t led-ticker:latest .

# --- Cleanup ---

clean:  ## Remove build artifacts and caches
	rm -rf .venv/ .pytest_cache/ .mypy_cache/ .ruff_cache/ .coverage htmlcov/ dist/ *.egg-info src/*.egg-info
