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

# CLI mode uses the validated config and reports the actual listener itself.
echo 'Starting S Pen Bridge. Pair using --show-pairing; USB is the default.'

# Start virtual tablet server
exec "$DIR/server/.venv/bin/python" "$DIR/server/main.py" "$@"
