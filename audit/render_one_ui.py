"""Compatibility entry point for the current native layout capture matrix.

The first rewrite captures remain in evidence/one-ui as historical evidence.
Current layouts and native font/overflow assertions live in render_layout.py.
"""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("render_layout.py")), run_name="__main__")
