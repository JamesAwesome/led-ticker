#!/usr/bin/env bash
set -euo pipefail

# Install led-ticker on a Raspberry Pi (bare-metal, no Docker)
# Run as root: sudo bash deploy/install.sh
#
# Override the rgbmatrix fork via env vars (defaults target Pi 4):
#   PI5=1 sudo bash deploy/install.sh
#     → jamesawesome/rpi-rgb-led-matrix @ pi5_support
#   RGBMATRIX_REPO=... RGBMATRIX_REF=... sudo bash deploy/install.sh

INSTALL_DIR="/opt/led-ticker"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Both Pi 4 and Pi 5 build from our jamesawesome fork:
# main = Pi 4 (existing sign), pi5_support = kingdo9 PR #1886 + our build patch.
: "${RGBMATRIX_REPO:=https://github.com/jamesawesome/rpi-rgb-led-matrix.git}"
if [ "${PI5:-0}" = "1" ]; then
    : "${RGBMATRIX_REF:=pi5_support}"
else
    : "${RGBMATRIX_REF:=main}"
fi

echo "==> Installing led-ticker to ${INSTALL_DIR}"
echo "    rgbmatrix repo: ${RGBMATRIX_REPO}"
echo "    rgbmatrix ref:  ${RGBMATRIX_REF}"

# Create install directory
mkdir -p "${INSTALL_DIR}"

# Create virtual environment
python3 -m venv "${INSTALL_DIR}/venv"
source "${INSTALL_DIR}/venv/bin/activate"

# Build and install rgbmatrix
if ! python3 -c "import rgbmatrix" 2>/dev/null; then
    echo "==> Building rgbmatrix from source..."
    apt-get update && apt-get install -y build-essential git python3-dev cmake
    cd /tmp
    rm -rf rpi-rgb-led-matrix
    git clone --depth=1 --branch "${RGBMATRIX_REF}" "${RGBMATRIX_REPO}" rpi-rgb-led-matrix
    cd rpi-rgb-led-matrix
    "${INSTALL_DIR}/venv/bin/pip" install .
    cd /tmp && rm -rf rpi-rgb-led-matrix
fi

# Install the package
echo "==> Installing led-ticker package (upgrading if already installed)..."
pip install --upgrade "${REPO_DIR}"

# Install declared plugins (config/requirements-plugins.txt), if present.
# Constrained to the core dependency versions just installed, so a plugin can
# add its own new deps but cannot move core's stack (a conflicting pin fails
# here rather than silently at runtime). led-ticker is already installed, so it
# resolves without PyPI. No fallback to the .example template.
PLUGINS_REQ="${REPO_DIR}/config/requirements-plugins.txt"
if [ -f "$PLUGINS_REQ" ]; then
    echo "==> Installing plugins from config/requirements-plugins.txt..."
    CONSTRAINTS="$(mktemp)"
    pip list --format=freeze > "$CONSTRAINTS"
    pip install -c "$CONSTRAINTS" -r "$PLUGINS_REQ"
    rm -f "$CONSTRAINTS"
fi

# Copy config if not present (bigsign gets its own example)
if [ ! -f "${INSTALL_DIR}/config.toml" ]; then
    if [ "${PI5:-0}" = "1" ]; then
        cp "${REPO_DIR}/config/config.bigsign.example.toml" "${INSTALL_DIR}/config.toml"
        echo "==> Copied config.bigsign.example.toml to ${INSTALL_DIR}/config.toml"
    else
        cp "${REPO_DIR}/config/config.example.toml" "${INSTALL_DIR}/config.toml"
        echo "==> Copied config.example.toml to ${INSTALL_DIR}/config.toml"
    fi
    echo "    Edit this file to configure your display."
fi

# Copy .env if not present
if [ ! -f "${INSTALL_DIR}/.env" ]; then
    cp "${REPO_DIR}/.env.example" "${INSTALL_DIR}/.env"
    echo "==> Copied .env.example to ${INSTALL_DIR}/.env"
    echo "    Add your API keys to this file."
fi

# Install systemd service
echo "==> Installing systemd service..."
cp "${REPO_DIR}/deploy/led-ticker.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable led-ticker

echo ""
echo "Installation complete!"
echo ""
echo "  Config: ${INSTALL_DIR}/config.toml"
echo "  Env:    ${INSTALL_DIR}/.env"
echo ""
echo "  Start:  sudo systemctl start led-ticker"
echo "  Logs:   sudo journalctl -u led-ticker -f"
