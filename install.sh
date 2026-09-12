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

# If stdin is not a terminal (e.g. curl | bash), reconnect to /dev/tty for sudo password prompts
if [ ! -t 0 ] && [ -r /dev/tty ]; then
    exec </dev/tty
fi

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

if ! command -v uv >/dev/null 2>&1; then
    if ! python3 -c "import venv" >/dev/null 2>&1; then
        echo "Error: Python 'venv' module is required. On Debian/Ubuntu install it with: sudo apt install python3-venv" >&2
        exit 1
    fi
fi

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
Categories=Graphics;2DGraphics;
Keywords=spen;tablet;wacom;stylus;samsung;krita;gimp;
StartupNotify=true
EOF
chmod 755 "$APPS_DIR/spen-bridge.desktop"

echo ""
echo "Install complete."
echo "Launch S Pen Bridge from your application menu, or run:"
echo "  $INSTALL_DIR/start.sh"
echo ""
echo "uinput permissions are configured with uaccess. If /dev/uinput is not accessible in this session, log out and log back in."
echo "Next, install the Android app on your tablet: see docs/SETUP.md."
