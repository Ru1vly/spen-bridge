#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]]
[[ ! -e /dev/uinput ]] # This container must never receive a host input device.
mkdir -p /test-stubs
for command in modprobe udevadm; do
    printf '#!/bin/sh\nprintf "%%s\\n" "$0 $*" >> /tmp/kernel-commands\n' > "/test-stubs/$command"
    chmod +x "/test-stubs/$command"
done
export PATH="/test-stubs:$PATH"
touch /dev/uinput
chmod 0600 /dev/uinput
if env -u SPEN_BRIDGE_USER -u SUDO_USER -u PKEXEC_UID USER=root bash /work/setup_uinput.sh >/tmp/root-result 2>&1; then
    echo 'Root target was incorrectly accepted' >&2; exit 1
fi
if env SPEN_BRIDGE_USER=nonexistent-spen-account USER=root bash /work/setup_uinput.sh >/tmp/invalid-result 2>&1; then
    echo 'Unknown target was incorrectly accepted' >&2; exit 1
fi
[[ ! -e /etc/udev/rules.d/99-uinput-spen.rules ]]
env -u SPEN_BRIDGE_USER -u PKEXEC_UID SUDO_USER=tester USER=root bash /work/setup_uinput.sh >/tmp/sudo-result
[[ -f /dev/uinput && ! -c /dev/uinput ]]
[[ $(stat -c %a /dev/uinput) == 660 ]]
[[ $(stat -c %G /dev/uinput) == spen-uinput ]]
getfacl -cp /dev/uinput | grep -q '^user:tester:rw-'
runuser -u tester -- test -w /dev/uinput
if id -nG tester | tr ' ' '\n' | grep -qx input; then
    echo 'Broad input membership was incorrectly granted' >&2; exit 1
fi
grep -q 'GROUP="spen-uinput"' /etc/udev/rules.d/99-uinput-spen.rules
if grep -q 'uaccess' /etc/udev/rules.d/99-uinput-spen.rules; then exit 1; fi
setfacl -b /dev/uinput
chmod 0600 /dev/uinput
env -u SPEN_BRIDGE_USER -u SUDO_USER PKEXEC_UID=1000 USER=root bash /work/setup_uinput.sh >/tmp/pkexec-result
getfacl -cp /dev/uinput | grep -q '^user:tester:rw-'
runuser -u tester -- test -w /dev/uinput
[[ -f /dev/uinput && ! -c /dev/uinput ]]
printf '%s\n' '{"root_target_rejected":true,"invalid_target_rejected":true,"sudo_user_preserved":true,"pkexec_uid_preserved":true,"dedicated_group_verified":true,"physical_input_group_not_granted":true,"real_acl_checked":true,"kernel_commands_mocked":true,"host_permissions_changed":false}'
