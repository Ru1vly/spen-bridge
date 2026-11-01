"""Capture the One UI rewrite on a disposable Android emulator.

Never runs on hardware. Uses only synthetic pairing values and verifies save,
validation, hide/show, area presets, both themes and emulated device classes.
Pass --serial if the emulator uses a different adb port. It resets this app's
emulator preferences and restores emulator screen/theme/text overrides on exit.
"""
import argparse
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--adb", default="adb")
parser.add_argument("--serial", default="emulator-5554")
args = parser.parse_args()
output = Path(__file__).parent / "evidence" / "layout-v2"
output.mkdir(parents=True, exist_ok=True)
package = "com.spenbridge.app"
checks = []


def adb(*command, binary=False, data=None):
    result = subprocess.run([args.adb, "-s", args.serial, *command], input=data, capture_output=True, check=True)
    return result.stdout if binary else result.stdout.decode().strip()


def shell(*command):
    return adb("shell", *command)


if not args.serial.startswith("emulator-") or shell("getprop", "ro.kernel.qemu") != "1":
    raise SystemExit("This harness only modifies a disposable Android emulator.")


def hierarchy():
    for attempt in range(3):
        shell("rm", "-f", "/sdcard/spen-oneui.xml")
        result = shell("uiautomator", "dump", "/sdcard/spen-oneui.xml")
        if "dumped to:" not in result:
            time.sleep(0.5)
            continue
        xml = adb("exec-out", "cat", "/sdcard/spen-oneui.xml")
        try:
            return ET.fromstring(xml)
        except ET.ParseError:
            time.sleep(0.5)
    raise RuntimeError("No valid UI hierarchy")


def find(ident, tree=None):
    tree = hierarchy() if tree is None else tree
    return next((n for n in tree.iter("node") if n.get("resource-id") == f"{package}:id/{ident}"), None)


def tap(ident):
    node = find(ident)
    if node is None:
        raise RuntimeError(f"{ident} is not in the current UI")
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds")))
    if x2 <= x1 or y2 <= y1:
        raise RuntimeError(f"{ident} has empty bounds")
    shell("input", "tap", str((x1+x2)//2), str((y1+y2)//2))
    time.sleep(0.25)


def tap_text(label):
    tree = hierarchy()
    node = next((n for n in tree.iter("node") if n.get("content-desc") == label or n.get("text").casefold() == label.casefold()), None)
    if node is None:
        raise RuntimeError(f"Tab {label} is not in the current UI")
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds")))
    shell("input", "tap", str((x1+x2)//2), str((y1+y2)//2))
    time.sleep(0.25)


def scroll_up():
    node = find("settingsScroll")
    if node is None:
        raise RuntimeError("Settings scroll region is not visible")
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds")))
    x = str((x1+x2)//2)
    shell("input", "swipe", x, str(y1+(y2-y1)*85//100), x, str(y1+(y2-y1)*15//100), "350")


def wait_rotation(rotation):
    for _ in range(8):
        tree = hierarchy()
        if tree.get("rotation") == str(rotation):
            return
    raise RuntimeError(f"Display did not settle at rotation {rotation}")


def open_settings():
    for attempt in range(2):
        tap("btnSettings")
        for _ in range(3):
            if find("settingsTabs") is not None:
                return
    raise RuntimeError("Settings did not become visible after tapping its control")


def capture(name):
    tree = hierarchy()  # also waits for idle; avoid capturing launch/rotation animations.
    path = output / f"{name}.png"
    png = adb("exec-out", "screencap", "-p", binary=True)
    import struct
    width, height = struct.unpack(">II", png[16:24])
    if "portrait" in name:
        assert height > width, (name, width, height)
    if "landscape" in name:
        assert width > height, (name, width, height)
    path.write_bytes(png)
    (output / f"{name}.xml").write_text(ET.tostring(tree, encoding="unicode"))
    assert any(n.get("package") == package for n in tree.iter("node")), name
    checks.append({"capture": name, "app_visible": True})


def seed_prefs():
    shell("am", "force-stop", package)
    prefs = b'''<?xml version="1.0" encoding="utf-8"?><map><boolean name="force_landscape" value="false"/><boolean name="sidebar_on_left" value="true"/></map>'''
    shell("run-as", package, "mkdir", "-p", "shared_prefs")
    adb("shell", "run-as", package, "sh", "-c", "'cat > shared_prefs/SPenBridgePrefs.xml'", data=prefs)


def launch():
    shell("am", "start", "-n", f"{package}/.MainActivity")
    time.sleep(0.8)


def configure(size, density, dark=False, font="1.0", rotation="0"):
    shell("am", "force-stop", package)
    shell("wm", "size", size)
    shell("wm", "density", str(density))
    shell("settings", "put", "system", "font_scale", font)
    shell("cmd", "uimode", "night", "yes" if dark else "no")
    shell("wm", "fixed-to-user-rotation", "enabled")
    shell("wm", "user-rotation", "lock", rotation)
    launch()
    wait_rotation(rotation)


try:
    shell("input", "keyevent", "KEYCODE_WAKEUP")
    shell("wm", "dismiss-keyguard")
    seed_prefs()
    for dark in (False, True):
        scheme = "dark" if dark else "light"
        for device, size, density in (("phone", "1080x2400", 420), ("tablet", "1200x1920", 240)):
            configure(size, density, dark)
            capture(f"android-{device}-{scheme}-portrait-canvas")
            tap("btnCollapse")
            assert find("btnExpand") is not None
            if device == "phone":
                capture(f"android-{device}-{scheme}-collapsed")
            tap("btnExpand")
            assert find("btnSettings") is not None
            open_settings()
            capture(f"android-{device}-{scheme}-portrait-settings")
            tap_text("Drawing area")
            capture(f"android-{device}-{scheme}-portrait-area")
            tap_text("Controls")
            capture(f"android-{device}-{scheme}-portrait-controls")
            shell("input", "keyevent", "KEYCODE_BACK")
            shell("wm", "user-rotation", "lock", "1")
            wait_rotation("1")
            capture(f"android-{device}-{scheme}-landscape-canvas")
            open_settings()
            capture(f"android-{device}-{scheme}-landscape-settings")
            if device == "phone":
                tap("editServerIp")
                capture(f"android-{device}-{scheme}-landscape-keyboard")
                shell("input", "keyevent", "KEYCODE_BACK")
            shell("input", "keyevent", "KEYCODE_BACK")
        configure("1080x2400", 420, dark, font="1.3")
        open_settings()
        capture(f"android-phone-{scheme}-large-text")
        tap_text("Drawing area")
        # Scroll only the selected drawing-area page.
        for i in range(7):
            if find("rbAreaCustom") is not None:
                break
            scroll_up()
        tap("rbAreaCustom")
        capture(f"android-phone-{scheme}-drawing-area")
        tap_text("Controls")
        capture(f"android-phone-{scheme}-display-controls")
        tap("btnSave")
        assert find("editServerIp") is not None, "Validation did not reveal Connection page"
        capture(f"android-phone-{scheme}-validation")
        shell("input", "keyevent", "KEYCODE_BACK")
        shell("input", "keyevent", "KEYCODE_BACK")
    # Exercise a successful save with clearly synthetic, non-routable pairing data.
    configure("1080x2400", 420, False)
    open_settings()
    for ident, value in (("editServerIp", "desktop.example.test"), ("editFingerprint", "0"*64), ("editPairingCode", "A"*43)):
        for _ in range(5):
            if find(ident) is not None:
                break
            scroll_up()
        tap(ident)
        shell("input", "text", value)
        shell("input", "keyevent", "KEYCODE_BACK")
    tap("btnSave")
    assert find("btnSettings") is not None, "Valid settings did not return to canvas"
    saved = adb("shell", "run-as", package, "cat", "shared_prefs/SPenBridgePrefs.xml")
    assert "desktop.example.test" in saved and "0"*64 in saved
    checks.append({"valid_settings_saved": True, "synthetic_identity_only": True})
    capture("android-phone-saved-canvas")
    open_settings()
    tap_text("Controls")
    shell("wm", "user-rotation", "lock", "1")
    wait_rotation("1")
    assert find("switchSidebarLeft") is not None, "Settings section was lost on rotation"
    capture("android-phone-controls-after-rotation")
    tap("switchSidebarLeft")
    tap("btnSave")
    shell("wm", "user-rotation", "lock", "1")
    wait_rotation("1")
    capture("android-phone-right-controls")
    node = find("btnSettings")
    x1, _, x2, _ = map(int, re.findall(r"\d+", node.get("bounds")))
    assert (x1+x2)//2 > 1200, "Right-side toolbar did not move to the right"
    checks.append({"right_side_controls": True})
finally:
    shell("am", "force-stop", package)
    shell("wm", "size", "reset")
    shell("wm", "density", "reset")
    shell("wm", "user-rotation", "free")
    shell("wm", "fixed-to-user-rotation", "default")
    shell("settings", "put", "system", "font_scale", "1.0")
    shell("cmd", "uimode", "night", "no")
    (output / "android-runtime-checks.json").write_text(json.dumps(checks, indent=2)+"\n")
print(json.dumps({"checks": len(checks), "output": str(output)}))
