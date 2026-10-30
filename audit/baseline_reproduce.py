"""Reproduce audit observations without creating an OS input device.

Run from the repository root: python audit/reproduce.py
Requires the app dependencies. Assertions describe the audited defects, not
desired behavior; this is an evidence harness, not a regression test suite.
"""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
scratch = tempfile.TemporaryDirectory(prefix="spen-audit-")
os.environ["XDG_CONFIG_HOME"] = scratch.name

from server.backends.base import TabletBackendBase
from server.config import TabletConfig
from server.protocol import (PenEvent, pack_events, ACTION_DOWN, ACTION_MOVE,
                             ACTION_CANCEL, BUTTON_STYLUS, BUTTON_STYLUS2)
from server.server import SPenServer


class MemoryTablet(TabletBackendBase):
    def _setup_device(self):
        self.events = []
        self.reset_count = 0

    def handle_event(self, event):
        self.events.append(event)

    def _release_touch(self):
        pass

    def reset(self):
        self.reset_count += 1

    def close(self):
        pass


observations = {}
event = PenEvent(ACTION_DOWN, 0, 0, .5, .5, .5)


async def network_checks():
    tablet = MemoryTablet()
    server = SPenServer(tablet, host="127.0.0.1", port=0)
    await server.start()
    port = server.server.sockets[0].getsockname()[1]
    r1, w1 = await asyncio.open_connection("127.0.0.1", port)
    r2, w2 = await asyncio.open_connection("127.0.0.1", port)
    try:
        w1.write(pack_events([event]))
        await w1.drain()
        for _ in range(100):
            if tablet.events:
                break
            await asyncio.sleep(.005)
        assert len(tablet.events) == 1
        observations["unauthenticated_event_without_handshake"] = True
        w1.close()
        await w1.wait_closed()
        for _ in range(100):
            if len(server.active_clients) == 1:
                break
            await asyncio.sleep(.005)
        assert len(server.active_clients) == 1 and tablet.reset_count == 0
        observations["idle_second_client_prevents_disconnect_reset"] = True
        stop_task = asyncio.create_task(server.stop())
        await asyncio.sleep(.05)
        assert server.active_clients
        observations["stop_waits_for_idle_client_on_python314"] = not stop_task.done()
        try:
            await asyncio.wait_for(r2.read(1), .05)
        except asyncio.TimeoutError:
            observations["stop_leaves_idle_connection_open"] = True
        else:
            raise AssertionError("expected accepted connection to remain open")
    finally:
        w2.close()
        await w2.wait_closed()
        await asyncio.sleep(.02)
        if "stop_task" in locals():
            await asyncio.wait_for(stop_task, 1)
        await server.stop()


def backend_checks():
    tablet = MemoryTablet(screen_bounds=(0, 0, 960, 1080), desktop_size=(1920, 1080))
    tablet.update_settings(screen_bounds=None, desktop_size=None)
    assert tablet._map_coordinates(1, 1)[0] == 32767
    observations["full_desktop_update_keeps_half_width_mapping"] = True
    locked = MemoryTablet(aspect_ratio_lock=True, tablet_aspect_ratio="4:3")
    unlocked = MemoryTablet(aspect_ratio_lock=False)
    assert locked._map_coordinates(.8, .2) == unlocked._map_coordinates(.8, .2)
    observations["aspect_lock_does_not_change_mapping"] = True
    try:
        MemoryTablet(screen_bounds=(0, 0, 100, 100), desktop_size=(0, 0))._map_coordinates(.5, .5)
    except ZeroDivisionError:
        observations["unvalidated_zero_desktop_divides_by_zero"] = True

    from evdev import ecodes as e
    from server.backends.linux_uinput import LinuxUinputTablet

    with patch.object(LinuxUinputTablet, "_setup_device"):
        linux = LinuxUinputTablet()
        linux.uinput = Mock()
        linux.handle_event(replace(event, buttons=BUTTON_STYLUS))
        assert not hasattr(linux, "reset")
        observations["linux_has_no_disconnect_reset"] = True
        linux.update_settings(button_primary="middle_click")
        linux.handle_event(replace(event, action=ACTION_MOVE))
        calls = linux.uinput.write.call_args_list
        assert any(c.args == (e.EV_KEY, e.BTN_RIGHT, 1) for c in calls)
        assert not any(c.args == (e.EV_KEY, e.BTN_RIGHT, 0) for c in calls)
        observations["linux_remap_leaves_old_right_button_pressed"] = True
        linux.uinput.reset_mock()
        linux.handle_event(replace(event, buttons=BUTTON_STYLUS, action=ACTION_CANCEL))
        assert linux._button_stylus_pressed
        observations["linux_cancel_retains_barrel_state"] = True
        linux.uinput.reset_mock()
        linux.update_settings(button_primary="right_click", button_secondary="right_click")
        linux.handle_event(replace(event, buttons=BUTTON_STYLUS | BUTTON_STYLUS2))
        linux.uinput.reset_mock()
        linux.handle_event(replace(event, buttons=BUTTON_STYLUS, action=ACTION_MOVE))
        assert any(c.args == (e.EV_KEY, e.BTN_RIGHT, 0) for c in linux.uinput.write.call_args_list)
        observations["linux_shared_mapping_releases_still_held_button"] = True
        linux.uinput.reset_mock()
        linux.handle_event(replace(event, action=255, tool_type=255, buttons=0))
        assert linux.uinput.syn.called
        observations["linux_invalid_action_reaches_device"] = True
        linux.uinput.reset_mock()
        linux.handle_event(replace(event, tool_type=2))
        assert any(c.args == (e.EV_KEY, e.BTN_LEFT, 1) for c in linux.uinput.write.call_args_list)
        observations["linux_finger_generates_click"] = True


def configuration_and_cli_checks():
    from types import SimpleNamespace
    from server.main import run_cli
    from server.monitors import get_monitors_from_xrandr
    from server.protocol import EVENT_STRUCT, unpack_events

    config = TabletConfig()
    config.click_on_touch = False
    config.mapping_mode = "monitor"
    config.selected_monitor = "second"
    args = SimpleNamespace(debug=False, host=None, port=None, name=None,
                           mode=None, direct=False, screen_bounds=None, desktop_size=None)

    class Captured(Exception):
        pass

    with patch("server.main.load_config", return_value=config), \
         patch("server.main.create_tablet_backend", side_effect=Captured) as factory:
        try:
            asyncio.run(run_cli(args))
        except Captured:
            pass
        assert "click_on_touch" not in factory.call_args.kwargs
        assert factory.call_args.kwargs["screen_bounds"] is None
        observations["cli_ignores_click_disable_and_monitor_mapping"] = True
    result = SimpleNamespace(returncode=0, stdout=(
        "DP-1 connected 1920x1080-1920+0\n"
        "HDMI-1 connected primary 1920x1080+0+0\n"))
    with patch("server.monitors.subprocess.run", return_value=result):
        assert len(get_monitors_from_xrandr()) == 1
        observations["xrandr_omits_negative_origin_monitor"] = True
    invalid = EVENT_STRUCT.pack(255, 255, 65535, float("nan"), .5, .5, 0, 0)
    assert len(unpack_events(invalid)) == 1
    observations["protocol_accepts_invalid_enums_and_nan"] = True
    config = TabletConfig.from_dict({"port": -1, "desktop_size": [0, 0]})
    assert config.port == -1 and config.desktop_size == [0, 0]
    observations["configuration_accepts_invalid_port_and_dimensions"] = True


def gui_checks():
    from PySide6.QtWidgets import QApplication, QMessageBox
    from server.gui.main_window import MainWindow
    from server.gui.server_worker import ServerWorker

    app = QApplication.instance() or QApplication([])
    config = TabletConfig(auto_start_server=False, minimize_to_tray=False)
    with patch("server.gui.main_window.load_config", return_value=config), \
         patch("server.gui.main_window.WindowWatcher.start"), \
         patch("server.gui.main_window.save_config", return_value=True), \
         patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
         patch.object(QMessageBox, "information"):
        window = MainWindow()
        try:
            panel = window.system_tab.startup_panel
            panel.spin_port.setValue(config.port + 1)
            assert not window._dirty
            observations["system_setting_change_not_marked_dirty"] = True
            window.set_active_profile("osu!")
            assert not window._dirty
            observations["active_profile_change_not_marked_dirty"] = True
            mapping = window.profiles_tab.editor_panel.mapping_section
            mapping.chk_aspect_lock.setChecked(True)
            window._reset_defaults()
            assert not window.config.aspect_ratio_lock and mapping.chk_aspect_lock.isChecked()
            assert window.profiles_tab.list_panel.chk_auto_switch.isChecked() == config.auto_switch_profiles
            observations["reset_leaves_aspect_control_stale"] = True
            config.auto_switch_profiles = False
            window.profiles_tab.list_panel.chk_auto_switch.setChecked(False)
            window._reset_defaults()
            assert window.config.auto_switch_profiles and not window.profiles_tab.list_panel.chk_auto_switch.isChecked()
            observations["reset_leaves_auto_switch_control_stale"] = True
            window.config.auto_start_server = False
            window.show()
            app.processEvents()
            window.grab().save(str(Path(scratch.name) / "profiles.png"))
            window.tabs.setCurrentIndex(1)
            app.processEvents()
            window.grab().save(str(Path(scratch.name) / "system.png"))
            # Preserve rendered evidence only on explicit request.
            if len(sys.argv) > 1:
                import shutil
                destination = Path(sys.argv[1])
                destination.mkdir(parents=True, exist_ok=True)
                for name in ("profiles.png", "system.png"):
                    shutil.copy(Path(scratch.name) / name, destination / name)
        finally:
            window.diag_timer.stop()
            window.window_watcher.stop()
            window.hide()
            window.deleteLater()

    worker = ServerWorker(config)
    with patch("server.gui.server_worker.threading.Thread") as thread:
        worker.start_server()
        worker.start_server()
        assert thread.call_count == 2
        observations["worker_can_start_twice_before_running"] = True


if __name__ == "__main__":
    asyncio.run(network_checks())
    backend_checks()
    configuration_and_cli_checks()
    gui_checks()
    print(json.dumps(observations, indent=2, sort_keys=True))
