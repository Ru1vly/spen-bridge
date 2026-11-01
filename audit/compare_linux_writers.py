"""Paired syscall-combining comparison on one exclusively grabbed device per mode."""

import json
import os
import statistics
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.backends.linux_uinput import LinuxUinputTablet
from server.protocol import ACTION_MOVE, BUTTON_TOUCH, PenEvent

os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
rows = []
for mode in ("pointer", "tablet"):
    tablet = device = None
    try:
        tablet = LinuxUinputTablet(
            name="SPen writer comparison " + uuid.uuid4().hex[:8],
            mode=mode,
            desktop_size=(1920, 1080),
        )
        combined = tablet.uinput
        raw = combined.raw
        device = combined.device
        if device is None:
            raise RuntimeError("No isolated node; no events sent")
        device.grab()
        for repeat in range(6):
            for label in (
                ("legacy", "combined") if repeat % 2 == 0 else ("combined", "legacy")
            ):
                tablet.uinput = raw if label == "legacy" else combined
                values = []
                for i in range(6000):
                    ev = PenEvent(
                        ACTION_MOVE,
                        0,
                        BUTTON_TOUCH,
                        (i % 1000) / 1000,
                        0.5,
                        0.7,
                        10,
                        -10,
                    )
                    start = time.perf_counter_ns()
                    tablet.handle_event(ev)
                    elapsed = time.perf_counter_ns() - start
                    if i >= 1000:
                        values.append(elapsed / 1000)
                    if i % 32 == 0:
                        try:
                            list(device.read())
                        except BlockingIOError:
                            pass
                values.sort()
                rows.append(
                    {
                        "mode": mode,
                        "variant": label,
                        "repeat": repeat,
                        "p50_us": values[2499],
                        "p95_us": values[4749],
                        "p99_us": values[4949],
                        "max_us": values[-1],
                    }
                )
        tablet.uinput = combined
    finally:
        if tablet:
            tablet.close()
        if device:
            device.close()
report = {
    "scope": "paired AB/BA rounds, same real exclusively grabbed virtual device, benchmark process pinned to one CPU; no desktop events",
    "rows": rows,
}
Path(
    "audit/evidence/latency-improvements-2026-10-31/linux-writer-comparison.json"
).write_text(json.dumps(report, indent=2))
for mode in ("pointer", "tablet"):
    for label in ("legacy", "combined"):
        selected = [r for r in rows if r["mode"] == mode and r["variant"] == label]
        print(
            mode,
            label,
            {
                k: round(statistics.median(r[k] for r in selected), 3)
                for k in ("p50_us", "p95_us", "p99_us")
            },
        )
