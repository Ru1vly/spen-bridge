#!/usr/bin/env bash
# Setup script to ensure current user can access /dev/uinput without sudo.

set -euo pipefail

echo "[*] Setting up uinput permissions for S Pen on Linux..."

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

# Create udev rule for /dev/uinput access by the 'input' group
UDEV_RULE_FILE="/etc/udev/rules.d/99-uinput-spen.rules"
echo "[+] Installing udev rule to ${UDEV_RULE_FILE}..."
echo 'KERNEL=="uinput", SUBSYSTEM=="misc", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"' | sudo tee "$UDEV_RULE_FILE" > /dev/null

# Add current user to 'input' group if not already a member
if ! id -nG "$USER" | grep -qw "input"; then
    echo "[+] Adding user '$USER' to 'input' group..."
    sudo usermod -aG input "$USER"
    echo "[!] NOTE: You may need to log out and log back in for group membership to take effect."
else
    echo "[+] User '$USER' is already in 'input' group."
fi

# Reload udev rules and trigger
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "[✓] uinput permissions setup complete!"
