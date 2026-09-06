#!/usr/bin/env bash
# S Pen on Linux — All-in-One Launcher

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
    echo "       🎨 S Pen on Linux — Launching Desktop GUI        "
    echo "========================================================"
    exec "$DIR/server/.venv/bin/python" "$DIR/server/main.py" --gui "$@"
fi

# CLI / Headless Mode
echo "========================================================"
echo "          🎨 S Pen on Linux — Console Server            "
echo "========================================================"
echo " Detected PC IP: $IP"
echo " Tablet Port:   40118"
echo ""

# Serve APK via mini HTTP server
echo "[+] Starting background APK download server on port 8080..."
python3 -m http.server 8080 --bind 0.0.0.0 > /dev/null 2>&1 &
HTTP_PID=$!

trap "kill $HTTP_PID 2>/dev/null || true" EXIT INT TERM

echo ""
echo "📱 [HOW TO INSTALL ON YOUR SAMSUNG TABLET / S22-S24 ULTRA]:"
echo "   1. Ensure phone/tablet is on the same Wi-Fi network."
echo "   2. Scan this QR code with camera:"
echo ""
if command -v qrencode >/dev/null 2>&1; then
    qrencode -t ANSIUTF8 "http://${IP}:8080/spen-on-linux.apk"
else
    echo "   URL: http://${IP}:8080/spen-on-linux.apk"
fi
echo ""
echo "   Or open in tablet browser: http://${IP}:8080/spen-on-linux.apk"
echo "--------------------------------------------------------"
echo "🖌️  [AFTER INSTALLING]:"
echo "   1. Open 'S Pen on Linux' on your tablet."
echo "   2. Tap Settings -> Server IP: $IP (Port: 40118)."
echo "   3. Tap Save & Reconnect -> Status turns GREEN!"
echo "   4. Open Krita, GIMP, or Blender on your PC and draw!"
echo "========================================================"
echo ""

# Start virtual tablet server
exec "$DIR/server/.venv/bin/python" "$DIR/server/main.py" "$@"
