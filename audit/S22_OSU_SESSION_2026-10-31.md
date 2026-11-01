# S22 Ultra osu! session findings

Capture: 31 October 2026, 09:03:56 UTC, duration 764.40 seconds (12 min 44 sec). Recorder stopped at the user's request. Evidence: `evidence/s22-osu-session-2026-10-31/summary.json`, `per-second.jsonl`, `active-rate-analysis.json`.

## Main findings

1. **Observed phone report stream is approximately 480 Hz, not 1,000 Hz.** Median S Pen kernel SYN_REPORT interval was 2,080 µs. Normalized active-window median was 477.7 reports/sec. This characterizes this session/configuration; it is not a claim about every supported digitizer mode or the phone's physical scan-rate ceiling.
2. **Desktop reports arrive in bursts.** Median virtual-tablet report spacing was 109 µs, but p95 was 8,597 µs and p99 9,798 µs. A small median inter-report interval does not mean low pen-to-PC latency: closely spaced output may be the release of an accumulated batch.
3. **No disconnect or virtual-device recreation was logged during this capture.** The desktop log's last disconnect precedes capture start; the recorder observed one host-device segment and reported no errors. This is stability evidence at those boundaries, not proof of zero packet loss or absence of every app error.
4. **The 300 µs one-way target remains unmeasured.** Source and destination events were not paired and their clocks are independent. The capture cannot establish phone-to-desktop latency, an age deadline, or the number of events that exceeded that deadline.

| Report-spacing metric | Phone S Pen kernel stream | Desktop virtual tablet |
|---|---:|---:|
| Median | 2.080 ms | 0.109 ms |
| p95 | 2.175 ms | 8.597 ms |
| p99 | 3.013 ms | 9.798 ms |
| Total SYN_REPORT frames | 228,308 | 231,230 |

These percentiles are **spacing between consecutive reports**, not delivery-latency percentiles. Long idle/menu gaps are included in the full histogram; the longest gap was approximately 108 seconds on both sides and is not classified as a transport stall. Rate analysis uses 468 near-one-second windows with at least 400 phone reports/sec and normalizes by actual elapsed time. ADB stream buffering may affect individual host-observed bucket counts; source event timestamps remain the stronger evidence for the roughly 480 Hz cadence.

The different totals are not evidence of lost or duplicated pen samples by themselves. Kernel source reports and native output frames are not guaranteed to map one-to-one; state changes and resets can create additional output frames. Sequence-matched application traces are required to quantify loss and duplicates.

## Likely explanation and next experiment

Burst-shaped desktop output is consistent with buffering/batching or scheduling between phone kernel input and Linux injection. Source review finds no request for unbuffered stylus dispatch in the current PenSurfaceView; Android input delivery batching is therefore a candidate, not a proven sole cause. ADB/TLS scheduling, the app UI thread, production heartbeat handling and host scheduling also remain candidates.

Next implementation should add bounded passive traces inside the normal app and receiver: source event time, callback arrival, enqueue/dequeue, write start/finish, receive/decode and native submission. Match samples by session/packet/event identity and export after drawing. Compare an unbuffered-dispatch build against the current build with smoothing disabled, then repeat configured defaults. Keep control-message reads independent from event transmission and report trace overhead and overflow.

Do not manufacture 1,000 “fresh” positions/sec by duplicating the observed approximately 480 Hz input. If a 1 kHz output cadence is desired separately, label repeated/predicted reports explicitly. Do not increase latency with a fixed 1 ms batching timer while claiming a 300 µs budget.

## Capture limitations

Only the phone's sec_e-pen node and the named desktop virtual tablet were read. No devices were grabbed and no input was injected. No screenshots, keyboard stream or pen coordinates were persisted. ADB monitoring adds traffic and is not zero-overhead. An initial setup capture is retained separately under `evidence/s22-osu-session-2026-10-31-setup`; it is excluded from these findings because the first host reader lacked a supported clock-selection method. The main capture used a working ioctl-based clock selection and recorded both streams successfully. Application processes were not restarted by this passive recorder.
