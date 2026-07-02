#!/bin/sh
# scripts/setup.sh — one-command led-ticker bootstrap
#
# Usage:
#   sh scripts/setup.sh [try|deploy]
#
#   try     — headless + webui preview (no Pi needed); no config seeding
#   deploy  — seed config/.env then bring up the production stack (default)
#
# Called by: make setup [MODE=try|deploy]
set -eu

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

say() { printf '\033[1;34m[setup]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m[setup]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[setup]\033[0m %s\n' "$*" >&2; }

# ---------------------------------------------------------------------------
# Docker preflight (always runs first)
# ---------------------------------------------------------------------------

check_docker() {
    say "Checking for Docker..."

    if ! command -v docker >/dev/null 2>&1; then
        err "docker not found."
        print_docker_install_guide
        exit 1
    fi

    if ! docker compose version >/dev/null 2>&1; then
        err "'docker compose' (v2 plugin) not available."
        print_docker_install_guide
        exit 1
    fi

    ok "Docker OK: $(docker --version)"
    ok "Compose OK: $(docker compose version)"
}

print_docker_install_guide() {
    cat >&2 <<'EOF'

  Docker is required. Please install it, then re-run this script.

  Linux / Raspberry Pi
  --------------------
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    # Log out and back in (or: newgrp docker) for the group change to take effect.

  macOS / Windows
  ---------------
    Install Docker Desktop:  https://docs.docker.com/get-docker/

  Note: 'docker compose' v2 ships with modern Docker — the old standalone
  'docker-compose' command is NOT required.

EOF
}

# ---------------------------------------------------------------------------
# Mode handling
# ---------------------------------------------------------------------------

MODE="${1:-deploy}"

case "$MODE" in
    try|deploy) ;;   # valid
    -h|--help)
        cat <<'EOF'
Usage: sh scripts/setup.sh [try|deploy]

  deploy  (default)  Seed config/config.toml + .env from examples, then
                     start the production stack with docker compose up -d.

  try                No config seeding — uses the committed
                     config/config.try.example.toml.  Starts the headless
                     engine + webui preview at http://localhost:8080.
EOF
        exit 0
        ;;
    *)
        err "Unknown mode: '$MODE'. Valid values: try | deploy"
        echo "Usage: sh scripts/setup.sh [try|deploy]" >&2
        exit 1
        ;;
esac

# ---------------------------------------------------------------------------
# Preflight (must pass before anything else)
# ---------------------------------------------------------------------------

check_docker

# ---------------------------------------------------------------------------
# deploy — seed config + .env, then bring up production stack
# ---------------------------------------------------------------------------

if [ "$MODE" = "deploy" ]; then
    say "Mode: deploy"

    # Seed config/config.toml
    if [ ! -f config/config.toml ]; then
        cp config/config.example.toml config/config.toml
        ok "Created config/config.toml from config/config.example.toml (smallsign defaults)."
        say "  Tip: for the bigsign layout, replace it with config/config.bigsign.example.toml"
        say "         cp config/config.bigsign.example.toml config/config.toml"
        say "       (that config uses plugins — you'll get an install prompt at startup; see its header)"
    else
        ok "config/config.toml already exists — skipping."
    fi

    # Seed .env
    if [ ! -f .env ]; then
        cp .env.example .env
        ok "Created .env from .env.example — add your API keys there."
    else
        ok ".env already exists — skipping."
    fi

    # Compute the package version on the host (no uv needed) so the image bakes
    # a real version instead of the 0.0.0 scm fallback — a 0.0.0 core blocks
    # every plugin install. Best-effort tag refresh first so it's current.
    [ -e .git ] && git fetch --tags --quiet 2>/dev/null || true
    if ! VERSION="$(sh scripts/compute-version.sh)"; then
        exit 1   # compute-version.sh already printed actionable guidance to stderr.
    fi
    export SETUPTOOLS_SCM_PRETEND_VERSION="$VERSION"
    BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    SHA="$(git rev-parse --short HEAD 2>/dev/null || true)"
    export BUILD_REF="${BRANCH}@${SHA}"

    say "Starting production stack (this may take a minute on first build)..."
    docker compose up -d --build

    ok "Done!  The display engine is running."
    cat <<'EOF'

  Next steps:
    • Watch startup:        make logs    (panels scroll within ~1 min of first boot)
    • Open the web UI:      http://<pi-hostname>.local:8080
                            (http://localhost:8080 if this machine is local;
                             requires COMPOSE_PROFILES=webui — see below)
    • Stop:                 make down

  Web UI (optional sidecar):
    Bring everything up with the web UI enabled:
      COMPOSE_PROFILES=webui make up
    (or add COMPOSE_PROFILES=webui to a .env so every make up/update includes it)

EOF
fi

# ---------------------------------------------------------------------------
# try — headless preview, no config seeding
# ---------------------------------------------------------------------------

if [ "$MODE" = "try" ]; then
    say "Mode: try (headless engine + webui preview — no hardware needed)"

    if [ -f config/config.toml ]; then
        export TRY_CONFIG=/code/config/config.toml
        ok "Previewing YOUR config/config.toml (hot-reload: edit and watch the browser update)"
        # tolerate leading whitespace (valid TOML) before the section header
        if ! grep -q '^[[:space:]]*\[web\]' config/config.toml; then
            err "Warning: config/config.toml has no [web] block — the live preview needs one."
            say "  Add [web] (one line) to config/config.toml, then re-run make try."
        fi
    else
        ok "Using the bundled example — create config/config.toml to preview your own sign, then re-run make try"
    fi

    say "Building + starting... first build takes a minute."
    say "Stop with Ctrl-C, then:  docker compose -f compose.try.yaml -p led-ticker-try down"
    echo ""

    docker compose -f compose.try.yaml -p led-ticker-try up --build

    # (Reached only after the user stops the containers.)
    ok "Try session ended."
    say "To clean up volumes:  docker compose -f compose.try.yaml -p led-ticker-try down -v"
fi
