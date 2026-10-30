"""Shared desktop-entry generation for both installers.

Escaping follows https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html
rather than shell quoting; desktop launchers do not execute a shell.
"""
from pathlib import Path
import sys


def _string(value):
    return str(value).replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')


def exec_argument(value):
    value = str(value)
    if any(ord(char) < 32 for char in value):
        raise ValueError('Launcher paths cannot contain control characters')
    quoted = ''.join('\\' + char if char in '\\"`$' else char for char in value)
    return '"' + _string(quoted).replace('%', '%%') + '"'


def desktop_entry(root):
    root = Path(root).resolve()
    executable = root / 'server' / '.venv' / 'bin' / 'python'
    return f'''[Desktop Entry]
Name=S Pen Bridge
Comment=Use a paired Samsung tablet as a graphics tablet
Exec=/usr/bin/env -- {exec_argument(executable)} {exec_argument(root / 'server' / 'main.py')} --gui
Icon={_string(root / 'spen_icon.png')}
Terminal=false
Type=Application
Categories=Graphics;2DGraphics;
Keywords=spen;tablet;stylus;samsung;
StartupNotify=true
'''


def install_launcher(root, destination):
    content = desktop_entry(root)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding='utf-8')
    destination.chmod(0o755)


if __name__ == '__main__':
    install_launcher(*sys.argv[1:])
