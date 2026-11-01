"""Compatibility entry point for the current disposable-emulator layout checks.

Forwards --adb/--serial to capture_layout_android.py. Historical first-rewrite
screenshots remain in evidence/one-ui; current evidence is in evidence/layout-v2.
"""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("capture_layout_android.py")), run_name="__main__")
