#!/usr/bin/env bash
# Setup script to ensure current user can access /dev/uinput without sudo.

set -euo pipefail

# If stdin is not a terminal, reconnect stdin to /dev/tty if available for sudo prompts
if [ ! -t 0 ] && [ -r /dev/tty ]; then
    exec </dev/tty
fi

echo "[*] Setting up uinput permissions for S Pen Bridge..."

# Ensure uinput kernel module is loaded
if ! lsmod | grep -q "^uinput"; then
    echo "[+] Loading uinput kernel module..."
    sudo modprobe uinput
fi

# Ensure uinput loads on boot
if [ ! -f /etc/modules-load.d/uinput.conf ]; then
    echo "[+] Adding uinput to /etc/modules-load.d/uinput.conf..."
    echo "uinput" | sudo tee /etc/modules-load.d/uinput.conf > /dev/null
fi

# Create udev rule for /dev/uinput access.
# TAG+="uaccess" grants immediate read/write access to the active seat user via systemd logind ACLs.
# MODE="0660", GROUP="input" is retained as a fallback for non-systemd/seat environments.
UDEV_RULE_FILE="/etc/udev/rules.d/99-uinput-spen.rules"
echo "[+] Installing udev rule to ${UDEV_RULE_FILE}..."
echo 'KERNEL=="uinput", SUBSYSTEM=="misc", MODE="0660", GROUP="input", TAG+="uaccess", OPTIONS+="static_node=uinput"' | sudo tee "$UDEV_RULE_FILE" > /dev/null

# Add current user to 'input' group as fallback if not already a member
if ! id -nG "$USER" | grep -qw "input"; then
    echo "[+] Adding user '$USER' to 'input' group (fallback)..."
    sudo usermod -aG input "$USER" || true
fi

# Reload udev rules and trigger
sudo udevadm control --reload-rules
sudo udevadm trigger

# Apply ACL immediately to /dev/uinput so current session does not need a logout/relogin
if command -v setfacl >/dev/null 2>&1; then
    sudo setfacl -m "u:${USER}:rw" /dev/uinput 2>/dev/null || true
fi

# Also ensure permissions on /dev/uinput right now if needed
if [ -e /dev/uinput ]; then
    sudo chmod 0660 /dev/uinput 2>/dev/null || true
fi

echo "[+] uinput permissions setup complete!"
