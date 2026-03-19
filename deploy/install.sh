#!/usr/bin/env bash
set -euo pipefail

# Install led-ticker on a Raspberry Pi (bare-metal, no Docker)
# Run as root: sudo bash deploy/install.sh

INSTALL_DIR="/opt/led-ticker"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Installing led-ticker to ${INSTALL_DIR}"

# Create install directory
mkdir -p "${INSTALL_DIR}"

# Create virtual environment
python3 -m venv "${INSTALL_DIR}/venv"
source "${INSTALL_DIR}/venv/bin/activate"

# Build and install rgbmatrix
if ! python3 -c "import rgbmatrix" 2>/dev/null; then
    echo "==> Building rgbmatrix from source..."
    apt-get update && apt-get install -y build-essential git python3-dev
    cd /tmp
    rm -rf rpi-rgb-led-matrix
    git clone --depth=1 https://github.com/hzeller/rpi-rgb-led-matrix.git
    cd rpi-rgb-led-matrix
    make build-python PYTHON="${INSTALL_DIR}/venv/bin/python3"
    make install-python PYTHON="${INSTALL_DIR}/venv/bin/python3"
    cd /tmp && rm -rf rpi-rgb-led-matrix
fi

# Install the package
echo "==> Installing led-ticker package..."
pip install "${REPO_DIR}"

# Copy config if not present
if [ ! -f "${INSTALL_DIR}/config.toml" ]; then
    cp "${REPO_DIR}/config.example.toml" "${INSTALL_DIR}/config.toml"
    echo "==> Copied config.example.toml to ${INSTALL_DIR}/config.toml"
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
