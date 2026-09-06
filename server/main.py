"""
S Pen on Linux — Server CLI entry point.
"""

import argparse
import asyncio
import logging
from pathlib import Path
import signal
import sys

# Ensure repository root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.virtual_tablet import VirtualTablet
from server.server import SPenServer


def parse_args():
    parser = argparse.ArgumentParser(
        description="S Pen on Linux — Turn Samsung S Pen and tablet into a Linux graphics tablet."
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host/IP address to bind the server to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=40118,
        help="TCP port to listen on (default: 40118)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="Samsung S Pen Virtual Tablet",
        help="Virtual tablet device name (default: 'Samsung S Pen Virtual Tablet')",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["pointer", "tablet"],
        default="pointer",
        help="Device mode: 'pointer' (default, absolute cursor + clicks for all Wayland compositors) or 'tablet' (pure tablet-v2)",
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


async def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    screen_bounds = None
    if args.screen_bounds:
        parts = [int(p.strip()) for p in args.screen_bounds.split(",")]
        if len(parts) == 4:
            screen_bounds = (parts[0], parts[1], parts[2], parts[3])

    desktop_size = None
    if args.desktop_size:
        parts = [int(p.strip()) for p in args.desktop_size.split(",")]
        if len(parts) == 2:
            desktop_size = (parts[0], parts[1])

    tablet = VirtualTablet(
        name=args.name,
        mode=args.mode,
        direct_mode=args.direct,
        screen_bounds=screen_bounds,
        desktop_size=desktop_size,
    )

    server = SPenServer(tablet=tablet, host=args.host, port=args.port)

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
            pass

    try:
        await server.start()
        print("\n" + "=" * 50)
        print(" S Pen on Linux Server is running!")
        print(f" Listening on {args.host}:{args.port}")
        print(" Ready for Android app connection.")
        print(" Press Ctrl+C to stop.")
        print("=" * 50 + "\n")
        await stop_event.wait()
    finally:
        await server.stop()
        tablet.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
