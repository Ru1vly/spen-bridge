"""CLI orchestration with fake devices, signals and window watcher."""
import asyncio
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from server.config import TabletConfig
from server.main import run_cli


class CliTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, *, failure=False):
        config = TabletConfig(auto_switch_profiles=True)
        config.profiles['Default'].click_on_touch = False
        config.profiles['Krita'].device_mode = 'tablet'
        config.profiles['Krita'].mapping_mode = 'monitor'
        config.profiles['Krita'].selected_monitor = 'left'
        args = SimpleNamespace(debug=False, host=None, wifi=False, usb=False, port=41234,
                               name='CLI tablet', mode=None, direct=None, screen_bounds=None, desktop_size=None)
        devices, calls, handlers = [], [], []

        class Device:
            def __init__(self, **options):
                self.__dict__.update(options)
                self.closed = False
                devices.append(self)
            def update_settings(self, **values):
                calls.append(('update', values))
                self.__dict__.update(values)
            def close(self):
                self.closed = True
                if failure and self is devices[0]:
                    raise OSError('device disappeared')

        class Server:
            def __init__(self, **options):
                self.__dict__.update(options)
                calls.append(('server', options))
            async def start(self):
                calls.append(('start',))
                asyncio.get_running_loop().call_later(.04, handlers[0])
            async def stop(self):
                calls.append(('stop',))

        class Watcher:
            def __init__(self, callback): self.callback = callback
            def start(self): self.callback('krita', '')
            def stop(self): calls.append(('watcher_stop',))

        loop = asyncio.get_running_loop()
        monitors = ([dict(name='left', x=-1280, y=0, width=1280, height=1024)], (3200, 1080))
        with ExitStack() as stack:
            for target, value in [('load_config', lambda: config), ('load_identity', lambda: Mock()),
                                  ('detect_monitors', lambda: monitors), ('create_tablet_backend', Device),
                                  ('SPenServer', Server), ('WindowWatcher', Watcher)]:
                stack.enter_context(patch(f'server.main.{target}', value))
            stack.enter_context(patch.object(loop, 'add_signal_handler', side_effect=lambda sig, callback: handlers.append(callback)))
            stack.enter_context(patch('server.main.signal.signal'))
            stack.enter_context(patch('builtins.print'))
            if failure:
                with self.assertRaises(OSError):
                    await asyncio.wait_for(run_cli(args), 1)
            else:
                await asyncio.wait_for(run_cli(args), 1)
        return config, devices, calls

    async def test_cli_applies_network_click_mapping_and_automatic_profile_settings(self):
        config, devices, calls = await self.exercise()
        self.assertFalse(devices[0].click_on_touch)
        self.assertEqual(config.active_profile_name, 'Krita')
        active = devices[-1]
        self.assertEqual(active.screen_bounds, (-1280, 0, 1280, 1024))
        server = next(call[1] for call in calls if call[0] == 'server')
        self.assertEqual((server['host'], server['port']), ('127.0.0.1', 41234))
        self.assertTrue(all(device.closed for device in devices))
        self.assertIn(('stop',), calls)
        self.assertIn(('watcher_stop',), calls)

    async def test_failed_profile_swap_closes_replacement_and_keeps_previous_selection(self):
        import sys
        if sys.platform == 'win32':
            self.skipTest('Windows keeps the single installed device open')
        config, devices, calls = await self.exercise(failure=True)
        self.assertEqual(config.active_profile_name, 'Default')
        self.assertEqual(len(devices), 2)
        self.assertTrue(all(device.closed for device in devices))
        self.assertIn(('stop',), calls)
