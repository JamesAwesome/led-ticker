.PHONY: dev test lint format pre-commit clean build-docker

PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin

# --- Developer Setup ---

dev:  ## Create venv and install package with dev dependencies
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -e ".[dev]"

# --- Testing ---

test:  ## Run pytest with coverage (no Docker needed)
	PYTHONPATH=tests/stubs $(BIN)/pytest -s --cov=src/ --cov-report=term-missing

# --- Quality ---

lint:  ## Run ruff linter
	$(BIN)/ruff check src/ tests/

format:  ## Run ruff formatter
	$(BIN)/ruff format src/ tests/

pre-commit:  ## Run all pre-commit hooks
	$(BIN)/pre-commit run --all-files

# --- Docker (production image only) ---

build-docker:  ## Build the production Pi Docker image
	docker build -t led-ticker:latest .

# --- Cleanup ---

clean:  ## Remove build artifacts and caches
	rm -rf .venv/ .pytest_cache/ .mypy_cache/ .ruff_cache/ .coverage htmlcov/ dist/ *.egg-info src/*.egg-info
