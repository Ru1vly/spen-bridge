#!/usr/bin/env bash
# Grant only uinput access, never access to physical input-event devices.
set -euo pipefail

# Preserve the initiating account across sudo and pkexec. GUI passes it explicitly.
TARGET_USER="${SPEN_BRIDGE_USER:-${SUDO_USER:-${PKEXEC_UID:-${USER:-}}}}"
if [[ "$TARGET_USER" =~ ^[0-9]+$ ]]; then
    TARGET_USER="$(getent passwd "$TARGET_USER" | cut -d: -f1)" || TARGET_USER=""
fi
if [[ -z "$TARGET_USER" || "$TARGET_USER" == -* ]] || ! id "$TARGET_USER" >/dev/null 2>&1 || [[ "$(id -u "$TARGET_USER")" == 0 ]]; then
    echo 'Run this as your desktop user, or set SPEN_BRIDGE_USER to that account.' >&2
    exit 1
fi
if [[ $EUID -ne 0 ]]; then
    exec sudo env "SPEN_BRIDGE_USER=$TARGET_USER" bash "$0" "$@"
fi
command -v setfacl >/dev/null || { echo 'Install the acl package (setfacl) and retry.' >&2; exit 1; }
modprobe uinput
install -d /etc/modules-load.d /etc/udev/rules.d
printf 'uinput\n' > /etc/modules-load.d/uinput.conf
# Dedicated group grants creation of virtual devices only. No membership in input.
getent group spen-uinput >/dev/null || groupadd --system spen-uinput
usermod -aG spen-uinput "$TARGET_USER"
printf '%s\n' 'KERNEL=="uinput", SUBSYSTEM=="misc", MODE="0660", GROUP="spen-uinput", OPTIONS+="static_node=uinput"' > /etc/udev/rules.d/99-uinput-spen.rules
udevadm control --reload-rules
udevadm trigger --subsystem-match=misc --sysname-match=uinput
udevadm settle --timeout=10
if [[ ! -e /dev/uinput ]]; then
    echo '/dev/uinput was not created; check the kernel module.' >&2
    exit 1
fi
chgrp spen-uinput /dev/uinput
chmod 0660 /dev/uinput
setfacl -m "u:${TARGET_USER}:rw" /dev/uinput
# Verify the effective ACL rather than reporting success after ignored failures.
runuser -u "$TARGET_USER" -- test -w /dev/uinput
echo "uinput access configured for $TARGET_USER. Physical input devices were not granted."
