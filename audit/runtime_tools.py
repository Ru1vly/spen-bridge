"""Resolve persistent diagnostic tools; never depend on an earlier /tmp session."""

import os
import shutil
from pathlib import Path


def adb_path():
    explicit = os.environ.get("SPEN_ADB")
    if explicit:
        candidate = Path(explicit).expanduser()
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise RuntimeError("SPEN_ADB must name an executable Android Debug Bridge")
        return str(candidate)
    found = shutil.which("adb")
    if found:
        return found
    candidates = [Path.home() / ".local/share/spen-bridge/android/platform-tools/adb"]
    for name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(name):
            candidates.append(Path(os.environ[name]) / "platform-tools/adb")
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise RuntimeError("ADB is unavailable: install Platform Tools or set SPEN_ADB")


def adb_command(serial=None):
    target = serial or os.environ.get("SPEN_ADB_SERIAL", "R3CTA0KD6NM")
    if not target or "\0" in target or "\n" in target:
        raise ValueError("Invalid ADB serial")
    return [adb_path(), "-s", target]
