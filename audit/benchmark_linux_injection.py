"""Measure real Linux injection with exclusively grabbed, newly created devices."""

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.backends.linux_uinput import LinuxUinputTablet
from server.protocol import ACTION_MOVE, BUTTON_TOUCH, PenEvent

p = argparse.ArgumentParser()
p.add_argument("--output", required=True)
p.add_argument("--legacy-writes", action="store_true")
args = p.parse_args()
rows = []
for mode in ("pointer", "tablet"):
    tablet = device = None
    try:
        tablet = LinuxUinputTablet(
            name="SPen latency isolated " + uuid.uuid4().hex[:8],
            mode=mode,
            desktop_size=(1920, 1080),
        )
        if args.legacy_writes and hasattr(tablet.uinput, "raw"):
            tablet.uinput = tablet.uinput.raw
        device = tablet.uinput.device
        if device is None:
            raise RuntimeError("No isolated event node; no events sent")
        device.grab()
        values = []
        for i in range(12000):
            event = PenEvent(
                ACTION_MOVE, 0, BUTTON_TOUCH, (i % 1000) / 1000, 0.5, 0.7, 10, -10
            )
            began = time.perf_counter_ns()
            tablet.handle_event(event)
            ended = time.perf_counter_ns()
            if i >= 2000:
                values.append((ended - began) / 1000)
            # Drain this grabbed reader so the benchmark does not flood its own queue.
            if i % 32 == 0:
                try:
                    list(device.read())
                except BlockingIOError:
                    pass
        values.sort()
        row = {
            "mode": mode,
            "samples": len(values),
            "p50_us": values[4999],
            "p95_us": values[9499],
            "p99_us": values[9899],
            "max_us": values[-1],
            "exclusive_grab": True,
            "desktop_events_sent": False,
        }
        rows.append(row)
    finally:
        if tablet:
            tablet.close()
        if device:
            device.close()
Path(args.output).write_text(
    json.dumps(
        {
            "scope": "synchronous Python backend handle_event through real uinput writes; no transport, newly created exclusively grabbed devices",
            "rows": rows,
        },
        indent=2,
    )
)
print(json.dumps(rows, indent=2))
