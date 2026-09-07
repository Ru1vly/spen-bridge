#!/usr/bin/env bash
# One-command installer for S Pen Bridge.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Ru1vly/spen-bridge/main/install.sh | bash
#
# Clones the repo (or updates it if already installed), grants uinput
# permissions, sets up the Python virtual environment, and installs a
# desktop launcher entry. Re-running this script is safe: it updates the
# existing install in place instead of cloning a second copy.

set -euo pipefail

REPO_URL="https://github.com/Ru1vly/spen-bridge.git"
INSTALL_DIR="${SPEN_BRIDGE_DIR:-$HOME/spen-bridge}"

require() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Error: '$1' is required but was not found on PATH. Install it and re-run this script." >&2
        exit 1
    fi
}

require git
require python3

if [ -d "$INSTALL_DIR/.git" ]; then
    echo "[*] Existing install found at $INSTALL_DIR, updating..."
    git -C "$INSTALL_DIR" pull --ff-only
else
    echo "[*] Cloning S Pen Bridge into $INSTALL_DIR..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"
chmod +x server/setup_uinput.sh start.sh

echo "[*] Setting up uinput permissions (this step may ask for your sudo password)..."
./server/setup_uinput.sh

echo "[*] Setting up the Python environment..."
if command -v uv >/dev/null 2>&1; then
    uv venv server/.venv
    uv pip install --python server/.venv/bin/python -r server/requirements.txt
else
    python3 -m venv server/.venv
    server/.venv/bin/pip install --upgrade pip
    server/.venv/bin/pip install -r server/requirements.txt
fi

echo "[*] Installing the application launcher..."
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
cat > "$APPS_DIR/spen-bridge.desktop" <<EOF
[Desktop Entry]
Name=S Pen Bridge
GenericName=Graphics Tablet Controller
Comment=Turn Samsung Galaxy Tab and S Pen into a Linux graphics tablet
Exec=$INSTALL_DIR/start.sh
Icon=$INSTALL_DIR/spen_icon.png
Terminal=false
Type=Application
Categories=Graphics;Utility;
Keywords=spen;tablet;wacom;stylus;samsung;krita;gimp;
StartupNotify=true
EOF
chmod 755 "$APPS_DIR/spen-bridge.desktop"

echo ""
echo "Install complete."
echo "Launch S Pen Bridge from your application menu, or run:"
echo "  $INSTALL_DIR/start.sh"
echo ""
echo "If you were just added to the 'input' group, log out and log back in before first launch."
echo "Next, install the Android app on your tablet: see docs/SETUP.md."
