"""
S Pen Bridge: main entry point (supports both GUI and headless CLI).
"""

import argparse
import copy
import asyncio
import logging
import os
from pathlib import Path
import signal
import ipaddress
import json
import sys

# Ensure repository root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.backends.factory import create_tablet_backend
from server.config import load_config
from server.monitors import detect_monitors
from server.settings import effective_settings, listener_address, runtime_settings
from server.security import load_identity
from server.window_watcher import WindowWatcher
from server.server import SPenServer


def parse_args():
    parser = argparse.ArgumentParser(
        description="S Pen Bridge: turn Samsung S Pen and tablet into a Linux graphics tablet."
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the desktop graphical control panel (default when desktop display is active)",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Force headless CLI server mode",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Bind address; an explicit non-loopback address opts into paired Wi-Fi",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="TCP port to listen on (default: from config or 40118)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Virtual tablet device name",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["pointer", "tablet"],
        default=None,
        help="Device mode: 'pointer' (default, absolute cursor + clicks) or 'tablet' (pure tablet-v2)",
    )
    parser.add_argument(
        "--direct",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable INPUT_PROP_DIRECT (screen-mapped display tablet mode)",
    )
    parser.add_argument(
        "--screen-bounds",
        type=str,
        default=None,
        help="Map tablet to specific screen region: 'x,y,width,height' (e.g. '0,0,1920,1080')",
    )
    parser.add_argument(
        "--desktop-size",
        type=str,
        default=None,
        help="Full desktop resolution: 'width,height' (e.g. '1920,2160')",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging",
    )
    transport = parser.add_mutually_exclusive_group()
    transport.add_argument("--wifi", action="store_true", help="Listen for paired Wi-Fi clients")
    transport.add_argument("--usb", action="store_true", help="Listen only on loopback for adb reverse")
    parser.add_argument("--show-pairing", action="store_true",
                        help="Display the certificate fingerprint and secret pairing code, then exit")
    return parser.parse_args()


async def run_cli(args):
    config = load_config()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.host is not None:
        config.host = args.host
        try:
            config.wifi_enabled = not ipaddress.ip_address(args.host).is_loopback
        except ValueError:
            config.wifi_enabled = args.host != "localhost"
    if getattr(args, "wifi", False):
        config.wifi_enabled = True
        if config.host in ("localhost", "127.0.0.1", "::1"):
            config.host = "0.0.0.0"
    if getattr(args, "usb", False):
        config.wifi_enabled = False
    if args.port is not None:
        config.port = args.port
    if args.name is not None:
        config.device_name = args.name
    explicit_bounds = None
    if args.screen_bounds:
        explicit_bounds = tuple(int(p.strip()) for p in args.screen_bounds.split(","))
        if len(explicit_bounds) != 4:
            raise ValueError("--screen-bounds requires x,y,width,height")
    explicit_desktop = None
    if args.desktop_size:
        explicit_desktop = tuple(int(p.strip()) for p in args.desktop_size.split(","))
        if len(explicit_desktop) != 2:
            raise ValueError("--desktop-size requires width,height")
        config.desktop_size = list(explicit_desktop)
    for profile in config.profiles.values():
        if args.mode is not None:
            profile.device_mode = args.mode
        if args.direct is not None:
            profile.direct_mode = args.direct
        if explicit_bounds is not None:
            profile.mapping_mode = "custom"
            profile.custom_bounds = list(explicit_bounds)
    config.validate()
    identity = load_identity()
    if config.recovery_notice:
        logging.warning(config.recovery_notice)
    detected = detect_monitors()
    if explicit_desktop:
        detected = detected[0], explicit_desktop
    options = effective_settings(config, detected)
    tablet = create_tablet_backend(**options)
    server = SPenServer(tablet=tablet, host=listener_address(config), port=config.port,
                        tls_context=identity.server_context(), pairing_code=identity.pairing_code)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    server.on_device_error = lambda message: (logging.error("Input device failed: %s", message), stop_event.set())

    def apply_profile(app_id, title):
        if stop_event.is_set():
            return
        profile = config.find_profile_for_app(app_id, title) or config.profiles["Default"]
        if profile.name == config.active_profile_name:
            return
        candidate = copy.deepcopy(config)
        candidate.active_profile_name = profile.name
        values = effective_settings(candidate, detected)
        # CLI profile swaps run on the same event loop as pen dispatch.
        nonlocal tablet
        try:
            if any(getattr(tablet, k) != values[k] for k in ("mode", "direct_mode", "name")) and sys.platform != "win32":
                replacement = create_tablet_backend(**values)
                try:
                    tablet.close()
                except Exception:
                    replacement.close()
                    raise
                tablet = server.tablet = replacement
            else:
                tablet.update_settings(**runtime_settings(values))
            config.active_profile_name = profile.name
            logging.info("Active tablet profile: %s", profile.name)
        except Exception:
            logging.exception("Profile switch failed; stopping input for cleanup")
            stop_event.set()

    watcher = WindowWatcher(callback=lambda app, title: loop.call_soon_threadsafe(apply_profile, app, title))

    def _sig_handler():
        logging.info("Shutting down...")
        stop_event.set()

    try:
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    except (AttributeError, ValueError):
        pass

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _sig_handler)
        except NotImplementedError:
            # Fallback for Windows where loop.add_signal_handler is not supported
            try:
                signal.signal(sig, lambda s, f: loop.call_soon_threadsafe(_sig_handler))
            except (ValueError, AttributeError):
                pass

    try:
        await server.start()
        if config.auto_switch_profiles:
            watcher.start()
        print("\n" + "=" * 55)
        print(" S Pen Bridge Server is running (Headless Mode)!")
        print(f" Listening on {listener_address(config)}:{config.port} (TLS, pairing required)")
        print(" Run with --show-pairing to view credentials for your tablet.")
        print(" Press Ctrl+C to stop.")
        print("=" * 55 + "\n")
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass
    finally:
        watcher.stop()
        try:
            await server.stop()
        finally:
            tablet.close()


def main():
    args = parse_args()
    if args.show_pairing:
        try:
            from server.validation import number
            config = load_config()
            port = config.port if args.port is None else args.port
            number(port, "port", 1, 65535, integer=True)
            identity = load_identity()
            print(json.dumps(dict(protocol=2, port=port,
                                  fingerprint=identity.fingerprint, pairing_code=identity.pairing_code), indent=2))
        except (ValueError, OSError) as error:
            logging.error("Cannot load pairing details: %s", error)
            raise SystemExit(2) from None
        return
    has_display = sys.platform == "win32" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )

    if args.gui or (not args.cli and has_display and len(sys.argv) == 1):
        from server.gui import launch_gui
        launch_gui()
    else:
        try:
            asyncio.run(run_cli(args))
        except KeyboardInterrupt:
            pass
        except (ValueError, OSError) as error:
            logging.error("Cannot start server: %s", error)
            raise SystemExit(2) from None


if __name__ == "__main__":
    main()
