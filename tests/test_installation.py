"""Installer regressions using disposable files and command stubs, never elevation."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from server.launcher import desktop_entry

ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def test_real_desktop_launcher_preserves_reserved_path_characters(self):
        try:
            import gi
            gi.require_version('Gio', '2.0')
            gi.require_version('GioUnix', '2.0')
            from gi.repository import GioUnix
        except ImportError:
            self.skipTest('Gio is needed for native desktop-entry parsing')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'a space \' quote " dollar $ backtick ` percent % slash \\ dir'
            interpreter = root / 'server/.venv/bin/python'
            interpreter.parent.mkdir(parents=True)
            output = Path(directory) / 'args.json'
            interpreter.write_text('#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\n'
                                   f'Path({str(output)!r}).write_text(json.dumps(sys.argv[1:]))\n')
            interpreter.chmod(0o755)
            entry = Path(directory) / 'test.desktop'
            entry.write_text(desktop_entry(root))
            info = GioUnix.DesktopAppInfo.new_from_filename(str(entry))
            self.assertIsNotNone(info)
            self.assertTrue(info.launch([], None))
            captured = None
            for _ in range(100):
                try:
                    captured = json.loads(output.read_text())
                    break
                except (OSError, json.JSONDecodeError):
                    time.sleep(.01)
            self.assertEqual(captured, [str(root / 'server/main.py'), '--gui'])

    def test_linux_install_can_run_twice_without_recreating_uv_environment(self):
        if os.name == 'nt':
            self.skipTest('Bash installer is Linux-only')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            checkout = base / 'checkout with spaces'
            (checkout / '.git').mkdir(parents=True)
            (checkout / 'server').mkdir()
            (checkout / 'server/setup_uinput.sh').write_text('#!/bin/sh\nexit 0\n')
            (checkout / 'start.sh').write_text('#!/bin/sh\nexit 0\n')
            binary = base / 'bin'
            binary.mkdir()
            for name, script in {
                'git': '#!/bin/sh\nexit 0\n',
                'uv': '''#!/bin/sh
set -eu
if [ "$1" = venv ]; then
    test ! -e server/.venv
    mkdir -p server/.venv/bin
    cat > server/.venv/bin/python <<'STUB'
#!/bin/sh
# Emulate only launcher generation, never install or execute repository code.
if [ "$1" = -m ] && [ "$2" = server.launcher ]; then
    printf '[Desktop Entry]\\n' > "$4"
fi
STUB
    chmod +x server/.venv/bin/python
fi
''',
            }.items():
                path = binary / name
                path.write_text(script)
                path.chmod(0o755)
            env = dict(os.environ, PATH=f'{binary}:{os.environ["PATH"]}',
                       HOME=str(base), SPEN_BRIDGE_DIR=str(checkout))
            for _ in range(2):
                result = subprocess.run(['bash', str(ROOT / 'install.sh')], env=env,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((base / '.local/share/applications/spen-bridge.desktop').is_file())
