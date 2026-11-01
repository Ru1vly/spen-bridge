# USB performance requirements

User requirement recorded 31 October 2026: **300 µs maximum input latency and 1,000 transmissions per second over USB**. These are requirements, not achieved or certified performance claims.

## Target hardware

- Phone: Samsung Galaxy S22 Ultra (user confirmed).
- Desktop: Dell Latitude 5420, Intel Core i5-1145G7, 4 cores / 8 threads.
- OS: Fedora Linux 44 KDE Plasma Desktop Edition, x86-64.
- Kernel: 7.2.11-200.fc44.x86_64, PREEMPT_DYNAMIC.
- Desktop details were inspected directly; no user-supplied system report is required.
- Physical phone now detected and ADB-authorized: Samsung SM-S908B (Galaxy S22 Ultra), Android 14 / API 34. The current USB link negotiates 480 Mbit/s (USB 2.0 high speed); S Pen Bridge is installed. Actual digitizer sampling and application-path USB latency remain unmeasured; USB link speed alone does not establish latency.

## Measurement boundary

The start/end of the 300 µs requirement must be defined before claiming compliance. The target hardware and desktop OS are now known, as listed above. Distinct boundaries are:

1. Android receives a pen sample → desktop backend submits OS input.
2. Physical pen movement → desktop OS input.
3. Physical pen movement → visible desktop response.

The existing architecture is Android MotionEvent → Kotlin transport → paired TLS/TCP → ADB reverse over USB → Python receiver → native input backend. It is not a direct 1 kHz USB HID endpoint. Its OS scheduling, runtime pauses and ADB scheduling are not hard real-time. Replacing one software component alone cannot establish a global 300 µs maximum.

## Rate is not sample freshness

- 1,000 transmissions/sec corresponds to a nominal 1 ms interval. This does not by itself imply 1,000 distinct digitizer samples/sec, nor prove a maximum sample age.
- Preserve the true source sample times and distinguish hardware samples, historical samples, repeated states and predicted/interpolated states. Do not manufacture a higher measured input rate by relabeling duplicate reports as fresh samples.
- Dispatch available input promptly; a fixed 1 ms flush timer alone can add nearly 1 ms of waiting, exceeding a 300 µs budget before transport.
- Preserve contact/button transitions and release semantics when handling backlog. A latest-position policy must not silently drop UP/CANCEL or erase pressure extrema without an explicit fidelity tradeoff.
- Receiver-side freshness requires a versioned clock/deadline contract. Independent Android and desktop monotonic timestamps cannot be subtracted without clock relationship and uncertainty estimates.

## Current evidence

`audit/evidence/usb-1000hz-2026-10-31/pipeline.json` records one short synthetic run against the production receiver with one event per packet, offered at 1,000 events/sec:

| Metric | Result |
|---|---:|
| Delivered | 2,000 / 2,000 |
| Elapsed | 2.002 seconds |
| Median write → backend callback | 310.7 µs |
| p95 | 643.2 µs |
| p99 | 1,142.2 µs |
| Maximum observed | 2,106.1 µs |

This is **same-host loopback TLS with an in-memory backend**, not USB, Android capture, actual OS injection or display. It demonstrates short-run receiver capacity and failure of the 300 µs maximum even in this limited test; it does not establish sustained USB cadence. Client pacing is best-effort, not a certified 1 ms inter-report maximum. Observed maxima from finite tests cannot prove an unconditional maximum on general-purpose operating systems.

## Work required before acceptance

1. Use the confirmed S22 Ultra / Fedora Linux desktop target; distinguish the timing boundary and whether 1 kHz means distinct sensor samples, event packets, or native input reports.
2. Remove heartbeat receive waits from the sender's input dispatch path; enforce deadline-aware freshness across the wire, not only the local queue.
3. Measure source delivery rate, actual packet/report intervals, sample age, queue dwell, transport delay and native submission separately. Baseline with smoothing disabled and measure release builds under load.
4. Benchmark real USB/ADB before deciding whether to replace it with a direct USB transport/native hot path. Direct USB or HID must be evaluated for device support, driver/accessory requirements and security; it is not an automatic latency guarantee.
5. Report losses, stalls, resets and deadline violations alongside percentiles and observed maximum. Never drop over-budget samples just to make a latency table pass without reporting the dropped samples and safe release behavior.

References: [Android stylus input and unbuffered dispatch](https://developer.android.com/develop/ui/views/touch-and-input/stylus-input/advanced-stylus-features), [AOSP ADB architecture and queues](https://android.googlesource.com/platform/packages/modules/adb/+/HEAD/docs/dev/internals.md). Android's unbuffered dispatch can reduce batching delay; it does not change digitizer capability or make the OS hard real-time.
