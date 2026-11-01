# S22 Ultra → Fedora: measurement and optimization plan

## Current status

Passive normal-app tracing and the sender improvements are implemented and were deployed to the S22 before the host reboot. Settings opened and returned to the canvas in the same process during the recorded runtime check. This does not establish that every earlier reported crash is resolved. The latest desktop is running again; the phone is currently absent from ADB. The user deferred real-pen testing. No automatic phone restart, reinstall or accessory-mode switch is authorized by that deferral.

Current source validation: 53 Android unit tests, debug/release assembly and lint passed; 154 Python tests passed with one optional-environment skip. Some later source changes, including the stream adapter, are not installed on the phone. See [implementation status](LATENCY_IMPLEMENTATION_STATUS.md) for deployment boundaries and [capture procedure](PASSIVE_LATENCY_CAPTURE.md) for the next normal-input measurement.

Production-sender synthetic USB trials subsequently delivered 5,000/5,000 records at 1,000.20 packets/sec and 9,000/9,000 at 3,001.01 packets/sec through TLS into an isolated in-memory receiver. These establish short-run transport capacity, not fresh sensor cadence or end-to-end latency. The older baseline below used a different instrumentation workload and must not be treated as a matched before/after latency comparison.

## What the real USB baseline measured

A synthetic Java source ran inside Android debug Instrumentation, under the app UID, with 500 warm-up reports followed by 5,000 measured reports per run. Each report contained one production-format event plus a PING. A temporary, pinned TLS identity and an isolated production Python receiver were used through a separately allocated ADB reverse port. The receiver used only an in-memory sink; no desktop clicks, cursor movements or key events were generated. Temporary credentials, cache files and the temporary reverse route were removed. The desktop's normal 40118 route was retained.

| Run | Actual phone send rate | Median round trip | p99 round trip | Maximum observed round trip |
|---|---:|---:|---:|---:|
| 1 | 917.5 reports/sec | 2,324.5 µs | 17,736.4 µs | 41,382.7 µs |
| 2 | 981.7 reports/sec | 1,535.1 µs | 7,854.5 µs | 44,116.4 µs |
| 3 | 897.7 reports/sec | 1,832.1 µs | 25,023.5 µs | 46,917.1 µs |

All 16,500 offered events, including warm-up, reached the isolated receiver. The intended rate was 1,000 reports/sec, but pacing missed deadlines; none of these runs establishes a reliable 1 kHz report cadence. Timing was explicitly best-effort and missed pacing slots are recorded.

These are **phone write → desktop event processing → PONG received on phone** measurements. They exclude S Pen sampling, Android MotionEvent dispatch, production PenTransport queuing, OS input injection and display. The per-report PING adds traffic and response work; this is a diagnostic transport workload, not the ordinary app's wire pattern. Round trip must not be divided by two and presented as measured one-way latency.

The diagnostic source also allocates objects per report and uses a normal-priority paced Java thread. Its scheduling and allocation costs are part of this baseline; the results are not an intrinsic lower bound on USB or evidence that changing one library will eliminate all tail latency.

Evidence: `audit/evidence/s22-usb-debug-2026-10-31/usb-probe.json`, `installation-diagnostic.json`, `debug-isolation.json`. Initial and final cold activity launches measured 383 ms and 495 ms respectively; launch time is unrelated to individual pen-event latency. Initial gfxinfo contained only four startup frames and cannot establish steady drawing FPS.

## Next measurement: passive normal-app tracing

This tracing is implemented in the debug app and opt-in desktop receiver. The real-pen comparison remains deferred at the user's request. The specifications below describe what the capture must distinguish.

### Report the rates separately

1. **Android-delivered distinct pen samples/sec**, including historical samples in each MotionEvent. Count sample timestamps/identities rather than only callback count. Also report callbacks/sec to reveal batching. Do not call this a physical digitizer scan rate without an independent kernel/device measurement.
2. **Transmitted event records/sec** and **packets/sec**, separately. One packet can contain multiple events. Repeated/interpolated states must be separately labeled and never counted as newly measured pen positions.
3. **Desktop received records/sec** and **native submitted reports/sec**. Track input loss, duplicates, intentional drops, cancels, reconnects and generation changes.
4. Report one-second buckets, full-run averages, longest inter-report gap, p95/p99 intervals and deadline misses. An average of 1,000/sec does not establish a maximum 1 ms interval or a maximum sample age.

### Timestamp the actual path

Attach diagnostic identity to trace records using session generation + packet sequence + event index (or an extended diagnostic counter), and match logs offline. Keep trace buffers bounded and export after the run rather than logging synchronously on each input event. Record overflow explicitly; an overflowed trace is incomplete evidence. Source and transmission records must distinguish rebatched historical samples from newly delivered samples.

| Point | Clock / location | What it isolates |
|---|---|---|
| Sample event time | Android event timestamp, including history | Android-reported event time; not a hardware physical-motion timestamp |
| App callback received | Android monotonic clock aligned to event time base | Android delivery/batching delay |
| Queued / dequeued / socket write start and finish | Same Android clock | App handling, queue dwell, encoding, write-call blocking |
| Desktop complete event received | Desktop monotonic clock | Start of host processing |
| Native report submitted | Same desktop clock | Decode, profile/filter, mapping and injection-call overhead |
| Virtual input observed | Kernel evdev timestamp with explicitly selected compatible clock | Kernel delivery boundary, if instrumented |

Android 14 provides nanosecond-form current and historical event timestamps, but nanosecond precision does not imply nanosecond accuracy. Match clock time bases; do not subtract unrelated monotonic clocks or use wall-clock timestamps for microsecond claims. [Android MotionEvent documentation](https://developer.android.com/reference/android/view/MotionEvent).

### Cross-device timing

- Phone-local and desktop-local stage times can be measured directly on their respective clocks.
- Direct phone-to-desktop one-way delay requires clock-offset estimation with a reported uncertainty bound or external hardware with a common time base.
- A four-timestamp exchange can bound/estimate offset; asymmetric USB queues and scheduling remain uncertainty. If that uncertainty is material relative to 300 µs, the one-way result is **inconclusive**, not a pass. RTT/2 is not a substitute.
- Physical pen motion → desktop pixels is a separate experiment requiring an appropriate external trigger/optical measurement setup. Software submission time excludes sensor and display latency.

### Controlled session

After passive tracing is implemented and disclosed, start one 30-second real drawing run explicitly. Keep normal app navigation usable. Measure continuous strokes and hover separately, then idle/reconnect and a bounded desktop-load case. Record device thermal state, USB link/route, app build hash, smoothing settings, report loss and measurement overhead. No background reinstall or instrumentation restart during interaction.

Prefer an exclusively grabbed diagnostic virtual input device when testing synthetic OS submission, so test reports cannot operate desktop applications. A real drawing test through the user's ordinary tablet device must be clearly distinguished from the isolated synthetic test.

## Engineering order toward the target

1. **Correctness first:** stabilize Settings/lifecycle behavior if the symptom reproduces; remove synchronous heartbeat reception from the production sender's input dispatch loop. Retain safe stop, generation ownership and release/cancel behavior.
2. **Establish the 300 µs boundary:** maintain the user's hard maximum requirement as unachieved. Do not silently replace it with median/p99 or redefine total input latency as one small stage. If the user accepts an added-bridge budget, state that explicitly.
3. **Instrument and measure:** implement the passive traces above, characterize actual S22 delivery rate and USB timing, and identify the dominant stage. Baseline with smoothing disabled; then measure configured defaults separately.
4. **Remove avoidable waiting:** evaluate unbuffered stylus dispatch, reuse hot-path storage, pre-encode buffers, avoid UI/logging dependencies, and keep receiving control messages independent from sending events. Do not add a fixed 1 ms batching wait while claiming a 300 µs budget.
5. **Receiver and transport experiments:** measure a native forwarding hot path against Python under identical authenticated workloads. Evaluate alternatives to ADB only after measuring where ADB contributes delay. A direct USB bulk/accessory path needs a verified S22-compatible device/host design; a normal APK cannot simply be assumed to turn a stock phone into a USB HID gadget.
6. **Freshness contract:** add a versioned receiver-verifiable age/deadline policy with clock uncertainty accounted for. Preserve UP/CANCEL and button transitions. Report every stale drop and reset; do not discard late samples just to improve the latency distribution.
7. **Repeat under load and on release-like builds:** report median, p95, p99, maximum observed, deadline violations, actual rates and drops. Compare instrumented and uninstrumented overhead. A finite test's maximum is not an unconditional real-time guarantee on general-purpose Android/Linux.

## Acceptance dashboard

- Distinct Android-delivered samples/sec: measured, never inferred from transmit rate.
- Transmitted/received/native-submitted events/sec and actual inter-report gaps.
- App queue dwell and host processing distributions.
- USB round-trip distribution; one-way value only with defensible uncertainty.
- Samples exceeding 300 µs at the agreed boundary, drops, trace overflow and resets.
- Result: **pass / fail / unmeasurable with current setup**, with the measurement boundary stated next to it.
