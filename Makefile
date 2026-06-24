.PHONY: dev hooks test lint typecheck format clean build-docker rebuild docs-dev docs-build docs-check-llms docs-lint docs-format validate render-demo render-long-demos render-long-demo render-pinned-demos plan-gif render-emoji-previews derive-phoenix derive-pride derive-heart-tunnel setup-demo-fonts panel-test panel-test-docker

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
	uv run pytest -s --cov=src/ --cov-report=term-missing

# --- Quality ---

lint:  ## Run ruff linter
	uv run ruff check src/ tests/ tools/

typecheck:  ## Run pyright type checker
	uv run pyright src/

format:  ## Run ruff formatter
	uv run ruff format src/ tests/ tools/

# --- Config validation ---

# Validate a config TOML against the loader (no hardware, no display).
# CONFIG defaults to config/config.toml; override for example/test configs.
CONFIG ?= config/config.toml
validate:  ## Validate a config TOML. Usage: make validate [CONFIG=path/to.toml]
	uv run led-ticker validate $(CONFIG)

# --- Panel diagnostics ---

# Cycle full panel through R/G/B/White/Black for hardware-layer diagnostics.
# Use this when widgets render wrong but you don't know if it's a config or
# wiring/driver issue. Reuses [display] from the given config TOML.
PANEL_CONFIG = $(if $(filter command,$(origin CONFIG)),$(CONFIG),config/config.longboi.toml)
HOLD ?= 2

panel-test:  ## Cycle full panel through R/G/B/W/B. Usage: make panel-test [CONFIG=config/config.longboi.toml] [HOLD=2]
	uv run python scripts/panel_color_test.py \
	  --config $(PANEL_CONFIG) \
	  --hold $(HOLD)

# Run the panel-test inside the production Docker image — this is what you'll
# run on longboi/bigsign/smallsign over SSH. Requires `make build-docker` to
# have run at least once.
#
# IMPORTANT: stop the running ticker first or the diagnostic will fight it for
# the matrix:
#   docker compose stop       # or: sudo systemctl stop led-ticker
#   make panel-test-docker
#   docker compose start      # or: sudo systemctl start led-ticker
#
# --privileged + --network host match compose.yaml so behavior is identical to
# prod. -it gives the script a TTY so Ctrl-C reaches Python and the black-
# frame cleanup runs. -v scripts:ro means script edits don't require rebuilding
# the image.
panel-test-docker:  ## Cycle R/G/B/W/B inside Docker. Stop the running ticker first.
	docker run --rm -it --privileged --network host \
	  -v $(PWD)/config:/code/config:ro \
	  -v $(PWD)/scripts:/code/scripts:ro \
	  led-ticker \
	  python /code/scripts/panel_color_test.py \
	    --config /code/$(PANEL_CONFIG) \
	    --hold $(HOLD)

# --- Docker (production image only) ---

# rgbmatrix fork is hardcoded in the Dockerfile (jamesawesome/main).
# Validated to run on both the Pi 4 sign and the Pi 5 bigsign.

# branch@shortsha(+dirty) — baked into the image as LED_TICKER_BUILD_REF.
BUILD_REF ?= $(shell git rev-parse --abbrev-ref HEAD 2>/dev/null)@$(shell git rev-parse --short HEAD 2>/dev/null)$(shell git diff --quiet HEAD 2>/dev/null || echo +dirty)

build-docker:  ## Build the production Docker image (Pi 4 + Pi 5)
	docker build -t led-ticker --build-arg BUILD_REF="$(BUILD_REF)" .

rebuild:  ## Stamped rebuild + recreate ALL services incl. the webui sidecar
	BUILD_REF="$(BUILD_REF)" COMPOSE_PROFILES=webui docker compose up -d --build --force-recreate

# --- Cleanup ---

clean:  ## Remove build artifacts and caches
	rm -rf .venv/ .pytest_cache/ .mypy_cache/ .ruff_cache/ .coverage htmlcov/ dist/ *.egg-info src/*.egg-info

# --- Docs site ---

docs-dev:  ## Run the Astro Starlight dev server (http://localhost:4321/)
	cd docs/site && (corepack enable 2>/dev/null || true) && pnpm install && node scripts/build-demos.mjs && pnpm run dev

docs-build:  ## Build the docs site to docs/site/dist/
	cd docs/site && (corepack enable 2>/dev/null || true) && pnpm install --frozen-lockfile && pnpm run build

docs-check-llms:  ## Build the docs + verify the llms.txt Markdown export
	cd docs/site && (corepack enable 2>/dev/null || true) && pnpm install --frozen-lockfile && pnpm run build && pnpm run check:llms

docs-lint:  ## Lint the docs site (prettier --check + astro check)
	cd docs/site && (corepack enable 2>/dev/null || true) && pnpm install --frozen-lockfile && pnpm run lint

docs-format:  ## Auto-format the docs site with prettier
	cd docs/site && (corepack enable 2>/dev/null || true) && pnpm install --frozen-lockfile && pnpm run format

render-demo:  ## Render a single demo gif. Usage: make render-demo CONFIG=path/to.toml OUT=out.gif
	uv run python tools/render_demo/render.py $(CONFIG) -o $(OUT)

plan-gif:  ## Recommended render --duration for a demo (+ cutoff guard). Usage: make plan-gif CONFIG=path/to.toml
	uv run python tools/gif_plan/plan.py $(CONFIG)

render-emoji-previews:  ## Re-generate per-slug emoji preview PNGs in docs/site/public/emoji/
	uv run python tools/render_emoji_previews.py

derive-phoenix:  ## Re-derive config/assets/phoenix.* from the vendored CC0 source
	uv run python tools/derive_phoenix_assets.py

derive-pride:  ## Re-generate config/assets/pride.* (CC0 rainbow flag)
	uv run python tools/derive_pride_assets.py

derive-heart-tunnel:  ## Re-generate config/assets/heart-tunnel-opaque.jpg (CC0 trans heart tunnel)
	uv run python tools/derive_heart_tunnel.py

# Long-running widget demos (data-fetch widgets — coinbase, mlb, rss_feed, …).
# Source TOMLs in docs/site/demos-long/, output to docs/site/public/demos-long/
# which IS committed to git (vs the auto-render path under public/demos/ which
# is gitignored and regenerates on every Cloudflare build). Cloudflare can't run
# these — they make live HTTP calls and some need API keys not in CI.

render-long-demos:  ## Render every long-running widget demo (~30 sec each); local only
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	failures=""; \
	for toml in docs/site/demos-long/*.toml; do \
		[ -f "$$toml" ] || continue; \
		name=$$(basename "$$toml" .toml); \
		out="docs/site/public/demos-long/$$name.gif"; \
		req=$$(grep -E '^# requires-env:' "$$toml" | head -1 | awk '{print $$3}'); \
		if [ -n "$$req" ] && [ -z "$$(printenv $$req)" ]; then \
			echo "[render-long-demos] SKIP $$name (needs $$req — add it to .env or export it to render)"; \
			continue; \
		fi; \
		dur=$$(grep -E '^# render-duration:' "$$toml" | head -1 | awk '{print $$3}'); \
		dur=$${dur:-30}; \
		echo "[render-long-demos] $$toml -> $$out ($${dur}s)"; \
		if ! uv run python tools/render_demo/render.py "$$toml" -o "$$out" --duration $$dur; then \
			failures="$$failures $$name"; \
		fi; \
	done; \
	if [ -n "$$failures" ]; then \
		echo "[render-long-demos] FAILED demos:$$failures"; \
		exit 1; \
	fi

render-long-demo:  ## Render one long-running demo. Usage: make render-long-demo NAME=widget-coinbase
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	toml="docs/site/demos-long/$(NAME).toml"; \
	dur=$$(grep -E '^# render-duration:' "$$toml" | head -1 | awk '{print $$3}'); \
	dur=$${dur:-30}; \
	echo "[render-long-demo] $$toml ($${dur}s)"; \
	uv run python tools/render_demo/render.py "$$toml" \
		-o docs/site/public/demos-long/$(NAME).gif --duration $$dur

# Pinned short-render demos. Source TOMLs in docs/site/demos-pinned/, output
# to docs/site/public/demos-pinned/ which IS committed. Same not-in-CI
# semantics as demos-long/ but for fast renders we want to control by hand
# (e.g. Common-pattern showcases on widget pages — we want a stable look,
# not a CI re-render every deploy).
render-pinned-demos:  ## Render every pinned short-render demo; local only, output committed
	@failures=""; \
	for toml in docs/site/demos-pinned/*.toml; do \
		[ -f "$$toml" ] || continue; \
		name=$$(basename "$$toml" .toml); \
		out="docs/site/public/demos-pinned/$$name.gif"; \
		dur=$$(grep -E '^# render-duration:' "$$toml" | head -1 | awk '{print $$3}'); \
		dur=$${dur:-5}; \
		echo "[render-pinned-demos] $$toml -> $$out ($${dur}s)"; \
		if ! uv run python tools/render_demo/render.py "$$toml" -o "$$out" --duration $$dur; then \
			failures="$$failures $$name"; \
		fi; \
	done; \
	if [ -n "$$failures" ]; then \
		echo "[render-pinned-demos] FAILED demos:$$failures"; \
		exit 1; \
	fi

# Download Atkinson Hyperlegible TTFs into the gitignored fonts dir used by the
# tutorial Chapter 4 demos (tutorial-04a-font, tutorial-04c-image-with-text).
# Idempotent — skips files already present. Gitignored destination, so the
# binaries never enter the repo; readers download their own copy per Chapter 4.
setup-demo-fonts:  ## Download Atkinson Hyperlegible to docs/site/demos-long/fonts/
	@mkdir -p docs/site/demos-long/fonts
	@if [ ! -f docs/site/demos-long/fonts/AtkinsonHyperlegible-Bold.ttf ]; then \
		echo "[setup-demo-fonts] downloading AtkinsonHyperlegible-Bold.ttf"; \
		curl -sL "https://fonts.gstatic.com/s/atkinsonhyperlegible/v12/9Bt73C1KxNDXMspQ1lPyU89-1h6ONRlW45G8WbcNcw.ttf" \
			-o docs/site/demos-long/fonts/AtkinsonHyperlegible-Bold.ttf; \
	else echo "[setup-demo-fonts] AtkinsonHyperlegible-Bold.ttf already present"; fi
	@if [ ! -f docs/site/demos-long/fonts/AtkinsonHyperlegible-Regular.ttf ]; then \
		echo "[setup-demo-fonts] downloading AtkinsonHyperlegible-Regular.ttf"; \
		curl -sL "https://fonts.gstatic.com/s/atkinsonhyperlegible/v12/9Bt23C1KxNDXMspQ1lPyU89-1h6ONRlW45GE5Q.ttf" \
			-o docs/site/demos-long/fonts/AtkinsonHyperlegible-Regular.ttf; \
	else echo "[setup-demo-fonts] AtkinsonHyperlegible-Regular.ttf already present"; fi
	@echo "[setup-demo-fonts] ready — tutorial-04* demos can render with the polished font"
