"""
Synthetic S Pen stroke generator.
Connects over TCP (or directly to VirtualTablet) and simulates realistic
pen hover, touchdown, varying pressure, tilt, and lift-off.
Useful for testing Krita / GIMP / Inkscape without needing an Android device.
"""

import argparse
import math
from pathlib import Path
import socket
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.protocol import (
    PenEvent,
    pack_events,
    ACTION_HOVER_ENTER,
    ACTION_HOVER_EXIT,
    ACTION_DOWN,
    ACTION_MOVE,
    ACTION_UP,
    TOOL_STYLUS,
    BUTTON_TOUCH,
)


def generate_spiral_points(center_x=0.5, center_y=0.5, max_r=0.25, loops=3, steps=150):
    points = []
    for i in range(steps):
        t = i / steps
        angle = t * loops * 2.0 * math.pi
        r = t * max_r
        x = center_x + r * math.cos(angle)
        y = center_y + r * math.sin(angle)
        # Pressure increases in the middle and tapers at ends
        pressure = math.sin(t * math.pi) * 0.9 + 0.1
        # Tilt oscillates gently
        tilt_x = math.sin(angle) * 30.0
        tilt_y = math.cos(angle) * 30.0
        points.append((x, y, pressure, tilt_x, tilt_y))
    return points


def run_synthetic_network_test(host="127.0.0.1", port=40118, count=1):
    print(f"Connecting to S Pen server at {host}:{port}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    print("Connected! Sending synthetic strokes...")
    time.sleep(0.5)

    spiral = generate_spiral_points()

    for stroke_num in range(1, count + 1):
        print(f"Drawing synthetic stroke #{stroke_num} ({len(spiral)} points)...")

        # 1. Hover into position
        start_x, start_y, _, _, _ = spiral[0]
        hover_in = PenEvent(
            action=ACTION_HOVER_ENTER,
            tool_type=TOOL_STYLUS,
            buttons=0,
            x=start_x,
            y=start_y,
            pressure=0.0,
        )
        sock.sendall(pack_events([hover_in]))
        time.sleep(0.02)

        # 2. Touch down
        first_x, first_y, first_p, first_tx, first_ty = spiral[0]
        down_ev = PenEvent(
            action=ACTION_DOWN,
            tool_type=TOOL_STYLUS,
            buttons=BUTTON_TOUCH,
            x=first_x,
            y=first_y,
            pressure=first_p,
            tilt_x=first_tx,
            tilt_y=first_ty,
        )
        sock.sendall(pack_events([down_ev]))
        time.sleep(0.005)

        # 3. Stream motion points
        for x, y, pressure, tilt_x, tilt_y in spiral[1:]:
            move_ev = PenEvent(
                action=ACTION_MOVE,
                tool_type=TOOL_STYLUS,
                buttons=BUTTON_TOUCH,
                x=x,
                y=y,
                pressure=pressure,
                tilt_x=tilt_x,
                tilt_y=tilt_y,
            )
            sock.sendall(pack_events([move_ev]))
            time.sleep(0.005)  # ~200 Hz rate

        # 4. Pen up
        last_x, last_y, _, _, _ = spiral[-1]
        up_ev = PenEvent(
            action=ACTION_UP,
            tool_type=TOOL_STYLUS,
            buttons=0,
            x=last_x,
            y=last_y,
            pressure=0.0,
        )
        sock.sendall(pack_events([up_ev]))
        time.sleep(0.02)

        # 5. Hover exit
        exit_ev = PenEvent(
            action=ACTION_HOVER_EXIT,
            tool_type=TOOL_STYLUS,
            buttons=0,
            x=last_x,
            y=last_y,
            pressure=0.0,
        )
        sock.sendall(pack_events([exit_ev]))
        time.sleep(0.2)

    print("Synthetic strokes complete!")
    sock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=40118)
    parser.add_argument("--count", type=int, default=1)
    args = parser.parse_args()

    run_synthetic_network_test(host=args.host, port=args.port, count=args.count)
