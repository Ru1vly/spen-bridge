#!/usr/bin/env bash
# S Pen Bridge: All-in-One Launcher

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Detect active IP on local network
IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7}' || echo "127.0.0.1")

# Check uinput permissions
if [ ! -w /dev/uinput ]; then
    echo "[!] Warning: /dev/uinput is not writable by current user."
    echo "    Running ./server/setup_uinput.sh..."
    ./server/setup_uinput.sh
fi

# Check if GUI or CLI mode
IS_CLI=0
for arg in "$@"; do
    if [ "$arg" == "--cli" ]; then
        IS_CLI=1
    fi
done

if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    IS_CLI=1
fi

if [ "$IS_CLI" -eq 0 ]; then
    echo "========================================================"
    echo "       S Pen Bridge: Launching Desktop GUI        "
    echo "========================================================"
    exec "$DIR/server/.venv/bin/python" "$DIR/server/main.py" --gui "$@"
fi

# CLI / Headless Mode
echo "========================================================"
echo "          S Pen Bridge: Console Server            "
echo "========================================================"
echo " Detected PC IP: $IP"
echo " Tablet Port:   40118"
echo ""
echo "[ON YOUR SAMSUNG TABLET / S22-S24 ULTRA]:"
echo "   1. Install the 'S Pen Bridge' app (see docs/SETUP.md)."
echo "   2. Ensure it's on the same Wi-Fi network as this PC."
echo "   3. Open Settings -> Server IP: $IP (Port: 40118)."
echo "   4. Tap Save & Reconnect -> Status turns GREEN!"
echo "   5. Open Krita, GIMP, or Blender on your PC and draw!"
echo "========================================================"
echo ""

# Start virtual tablet server
exec "$DIR/server/.venv/bin/python" "$DIR/server/main.py" "$@"
