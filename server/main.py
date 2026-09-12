"""
S Pen Bridge: main entry point (supports both GUI and headless CLI).
"""

import argparse
import asyncio
import logging
import os
from pathlib import Path
import signal
import sys

# Ensure repository root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.backends.factory import create_tablet_backend
from server.config import load_config
from server.monitors import detect_monitors
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
        help="Host/IP address to bind the server to (default: from config or 0.0.0.0)",
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
        action="store_true",
        help="Enable INPUT_PROP_DIRECT (screen-mapped display tablet mode)",
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
    return parser.parse_args()


async def run_cli(args):
    config = load_config()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    host = args.host or config.host
    port = args.port or config.port
    name = args.name or config.device_name
    mode = args.mode or config.device_mode
    direct = args.direct or config.direct_mode

    screen_bounds = None
    if args.screen_bounds:
        parts = [int(p.strip()) for p in args.screen_bounds.split(",")]
        if len(parts) == 4:
            screen_bounds = (parts[0], parts[1], parts[2], parts[3])
    elif config.mapping_mode == "custom" and len(config.custom_bounds) == 4:
        screen_bounds = tuple(config.custom_bounds)

    desktop_size = None
    if args.desktop_size:
        parts = [int(p.strip()) for p in args.desktop_size.split(",")]
        if len(parts) == 2:
            desktop_size = (parts[0], parts[1])
    elif screen_bounds is not None:
        # Auto-detect rather than trusting a possibly-stale saved config.desktop_size:
        # it's only ever used as the scaling denominator when screen_bounds maps to
        # less than the full desktop, so a wrong value here silently caps how far
        # down/right the pen can reach. See
        # TabletConfig.get_screen_bounds_and_desktop()'s docstring for the same issue
        # on the GUI side.
        _, detected_desktop_size = detect_monitors()
        desktop_size = detected_desktop_size

    tablet = create_tablet_backend(
        name=name,
        mode=mode,
        direct_mode=direct,
        screen_bounds=screen_bounds,
        desktop_size=desktop_size,
        pressure_curve_type=config.pressure_curve_type,
        pressure_gamma=config.pressure_gamma,
        pressure_min=config.pressure_min,
        pressure_max=config.pressure_max,
        stroke_smoothing=config.stroke_smoothing,
        button_primary=config.button_primary,
        button_secondary=config.button_secondary,
        aspect_ratio_lock=config.aspect_ratio_lock,
        tablet_aspect_ratio=config.tablet_aspect_ratio,
    )

    server = SPenServer(tablet=tablet, host=host, port=port)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

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
        print("\n" + "=" * 55)
        print(" S Pen Bridge Server is running (Headless Mode)!")
        print(f" Listening on {host}:{port}")
        print(" Ready for Android app connection.")
        print(" Press Ctrl+C to stop.")
        print("=" * 55 + "\n")
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass
    finally:
        await server.stop()
        tablet.close()


def main():
    args = parse_args()
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


if __name__ == "__main__":
    main()
