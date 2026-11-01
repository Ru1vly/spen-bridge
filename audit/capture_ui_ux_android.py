"""Native UI checks on an emulator or an explicitly selected isolated device app; restore overrides."""
import argparse
from pathlib import Path
import re
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--serial', default='emulator-5556')
parser.add_argument('--isolated-device', action='store_true', help='Use only the separate .uiaudit application on a physical device')
args = parser.parse_args()
if not args.serial.startswith('emulator-') and not args.isolated_device:
    raise SystemExit('Physical devices require --isolated-device; the real app is never cleared')
root = Path(__file__).resolve().parents[1]
out = root / 'audit/evidence/ui-ux-fixes' / ('device-2026-11-01' if args.isolated_device else 'emulator')
out.mkdir(parents=True, exist_ok=True)
base = ['adb', '-s', args.serial]

def adb(*command, timeout=90, binary=False):
    p = subprocess.run(base + list(command), check=True, capture_output=True, timeout=timeout)
    return p.stdout if binary else p.stdout.decode().strip()

def shell(*command):
    return adb('shell', *command)

if (not args.isolated_device and shell('getprop', 'ro.kernel.qemu') != '1') or shell('getprop', 'sys.boot_completed') != '1':
    raise SystemExit('Requires a booted Android runtime')
size = shell('wm', 'size')
density = shell('wm', 'density')
rotation = shell('settings', 'get', 'system', 'user_rotation')
accelerometer = shell('settings', 'get', 'system', 'accelerometer_rotation')
font = shell('settings', 'get', 'system', 'font_scale')
night = shell('cmd', 'uimode', 'night')
package = 'com.spenbridge.app.uiaudit' if args.isolated_device else 'com.spenbridge.app'
apk = root / ('android/app/build/outputs/apk/audit/app-audit.apk' if args.isolated_device else 'android/app/build/outputs/apk/debug/app-debug.apk')
# Record only display/accessibility configuration, never app preferences or pairing data.
import json
(out / 'original-device-overrides.json').write_text(json.dumps(dict(size=size,density=density,rotation=rotation,accelerometer=accelerometer,font=font,night=night),indent=2)+'\n')
try:
    print(adb('install', '-r', str(apk)), flush=True)
    for name, dimensions, dpi, rotate, scale, theme in [
        ('phone-light-portrait', '1080x2400', '420', '0', '1.0', 'no'),
        ('phone-dark-landscape-large', '1080x2400', '420', '1', '1.3', 'yes'),
        ('tablet-light-portrait', '1600x2560', '240', '0', '1.0', 'no'),
        ('tablet-dark-landscape-large', '1600x2560', '240', '1', '1.3', 'yes'),
    ]:
        shell('wm', 'size', dimensions)
        shell('wm', 'density', dpi)
        shell('settings', 'put', 'system', 'accelerometer_rotation', '0')
        shell('settings', 'put', 'system', 'user_rotation', rotate)
        shell('settings', 'put', 'system', 'font_scale', scale)
        shell('cmd', 'uimode', 'night', theme)
        shell('input', 'keyevent', 'KEYCODE_WAKEUP')
        time.sleep(2)
        instrument = ['shell','am','instrument','-w']
        if args.isolated_device:
            instrument += ['-e','isolated_device','true']
        instrument += ['-e','orientation','landscape' if rotate == '1' else 'portrait']
        instrument += [package + '/com.spenbridge.app.UiUxAuditInstrumentation']
        result = adb(*instrument, timeout=240)
        (out / f'android-{name}.txt').write_text(result + '\n')
        if 'ui_ux_checks=PASS:' not in result:
            raise RuntimeError(f'{name} failed: {result}')
        for screen in ['settings-index', 'settings-connection', 'settings-input', 'settings-area', 'settings-support', 'tablet-hover']:
            png = adb('exec-out', 'run-as', package, 'cat', f'files/ui-ux-audit/{screen}.png', binary=True)
            assert png.startswith(b'\x89PNG'), f'Invalid screenshot: {screen}'
            import struct
            w, h = struct.unpack('>II', png[16:24])
            assert (w > h) == (rotate == '1'), f'Wrong native orientation: {name}, {screen}'
            (out / f'android-{name}-{screen}.png').write_bytes(png)
        print(name, 'native checks and captures passed', flush=True)
finally:
    for command, original in [('size', size), ('density', density)]:
        match = re.search(r'Override (?:size|density): ([^\n]+)', original)
        shell('wm', command, match.group(1).strip() if match else 'reset')
    for key, value in [('user_rotation', rotation), ('accelerometer_rotation', accelerometer), ('font_scale', font)]:
        if value == 'null':
            shell('settings', 'delete', 'system', key)
        else:
            shell('settings', 'put', 'system', key, value)
    match = re.search(r'Night mode: (\w+)', night)
    if match:
        shell('cmd', 'uimode', 'night', match.group(1))
