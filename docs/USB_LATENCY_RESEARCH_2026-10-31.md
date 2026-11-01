# Reducing S22 Ultra → Fedora pen latency

Research date: 31 October 2026. Scope: primary Android/AOSP/Linux/libusb/osu!framework documentation, current application source, and this phone's recorded USB session. This pass changed no application code, installed no APK and changed no phone/desktop settings. ADB capabilities and available sysfs metadata were inspected read-only.

The implementation has advanced since this initial research snapshot; see [current status](LATENCY_IMPLEMENTATION_STATUS.md). The later ADB transport finding below is a new candidate, not a measured improvement.

## Conclusion

There are concrete, avoidable delays worth fixing before treating current performance as a hardware limit. **Unbuffered stylus delivery—including hover—and removal of synchronous heartbeat waits are the first experiments.** If ADB remains dominant afterward, direct Android Open Accessory bulk transport with a native desktop receiver is a credible architectural experiment.

A **300 µs added forwarding budget after a sample becomes available** is a useful experimental objective, not an achieved result or a hard real-time guarantee. It is different from physical motion → visible response. Current evidence does not establish either one-way latency or a firmware-imposed permanent 480 Hz ceiling.

## Interpret the existing measurements correctly

- Phone kernel pen reports had median spacing **2.080 ms**, approximately **480 Hz**. That is report cadence, not measured bridge delay.
- Desktop virtual input had **0.109 ms median spacing**, but **8.597 ms p95 / 9.798 ms p99**. This burst structure suggests accumulation and release of reports somewhere in the pipeline; it does not identify the layer by itself.
- Roughly four 2.08 ms source intervals fit an 8.33 ms display period. That makes frame-related input batching a particularly plausible hypothesis, **not proof**: we have not yet recorded Android callback times, active phone refresh cadence or matched packet identities.
- Synthetic real-USB round-trip medians were **1.54–2.32 ms**, with substantial tails. Those tests included a PONG per event, Java allocation/pacing and a Python receiver. They cannot isolate ADB cost or be halved into measured one-way latency.
- A source offering a distinct measurement every 2.08 ms cannot supply genuinely new observations every 1 ms unless its source behavior changes. Repeating/predicting reports changes output cadence or apparent response, not the number of measured positions. This observation does not prevent forwarding each available sample in less than 2 ms.

## Ranked changes

### 1. Request unbuffered input for both contact and hover

**Priority: highest. Confidence: mechanism documented; improvement on this phone unmeasured.**

Current `PenSurfaceView.kt` handles contact and hover but calls neither form of `requestUnbufferedDispatch`. Android recommends requesting immediate event delivery for low-latency stylus handling. The event overload applies to the touch stream through UP; the API-30 source-class overload is persistent and supports arbitrary source classes. Android 14 on this S22 supports both. [Android stylus guidance](https://developer.android.com/develop/ui/views/touch-and-input/stylus-input/advanced-stylus-features), [View API](https://developer.android.com/reference/android/view/View#requestUnbufferedDispatch(int)).

**Why hover matters:** osu! can be played with the pen above the display. Adding only an ACTION_DOWN request could leave the main gameplay path buffered. Apply a source-class request to the actual pen view, verify source matching and attach/focus behavior, and retain an API-26–29 contact fallback. Do not apply it indiscriminately to Settings scrolling: the View documentation warns about adverse interactions with resampling and scrolling.

**Expected benefit:** remove framework waiting where that waiting exists. It does not change physical scan rate. **No numerical gain is promised.**

**A/B test:** same device, same USB route, same map, smoothing off; record current/historical event timestamps, callback arrival and history size. Run hover and contact separately. Success means lower event-to-callback age and less burst-shaped desktop delivery without lost edges, broken palm rejection, stuck contact or worse tails.

**Code:** `android/app/src/main/java/com/spenbridge/app/PenSurfaceView.kt:277` and `onHoverEvent`.

### 2. Make heartbeat reception independent of event transmission

**Priority: highest. Confidence: defect directly reproduced.**

The production transport sends PING and calls blocking `receive(2000)` in the same loop that drains the input queue (`PenTransport.kt:299–307`). The audit's controlled-link test demonstrated queue latency tracking delayed PONG replies, and reset loops above the local age limit.

Use a dedicated receive path/nonblocking response state while retaining one ordered writer, deadlines, a bounded session queue and safe cancellation. Track successful acknowledgements separately from local socket-write progress; a successful buffered write does not prove remote liveness. Shut down and join the receive path on stop/endpoint change, and reject replies from old generations.

**Expected benefit:** removes one known source of periodic sender stalls. It does not explain every 8–10 ms output gap and is not an argument for disabling heartbeat safety.

**Test:** delayed/missing/mismatched PONG while sending continuously, hover and held contact, UP/CANCEL preservation, reconnect and lifecycle stop. Compare p99/max queue dwell, resets and loss—not just throughput.

### 3. Remove allocation and avoidable work from the per-sample path

**Priority: next, guided by tracing. Confidence: source-confirmed work, cost not yet isolated.**

The app builds lists and event objects and encodes buffers per dispatch. The Linux receiver validates, maps and writes multiple axis/button events per sample. Avoid constructing extra temporary objects, synchronous logging and preview work on the forwarding path. Android specifically recommends minimizing allocation in stylus motion handling. [Android motion-handling guidance](https://developer.android.com/develop/ui/views/touch-and-input/stylus-input/advanced-stylus-features).

A preallocated bounded buffer and reusable encoding storage are candidates, but ownership/generation correctness comes first. Lock-free data structures and higher thread priority are experiments, not automatic wins. Do not add a 1 ms batching timer: its waiting alone could exceed the requested 300 µs budget. Current queue wakeup uses notification; its maximum idle wait is **not** a fixed delay on every sample.

`TCP_NODELAY` is already enabled at both ends. Recommending that toggle as a new fix would be misleading. `postInvalidateOnAnimation()` schedules the Android preview; the current network send is not explicitly delayed until that draw call. The framework's earlier input delivery can still be buffered.

### 4. Reduce desktop forwarding overhead without rewriting the GUI

**Priority: after measured stage attribution. Confidence: plausible optimization.**

The current Linux backend performs separate uinput writes for coordinates, pressure, tilt, button edges and SYN. Experiment with assembling a complete native input report into one write, preserving its final SYN_REPORT. This means combining syscalls **within one available sample**, not accumulating samples over time. Linux uinput is a userspace event-injection interface; its implementation accepts streams of input events. [Kernel uinput documentation](https://docs.kernel.org/input/uinput.html), [kernel implementation](https://kernel.googlesource.com/pub/scm/linux/kernel/git/krzk/linux/+/bf4afc53b77aeaa48b5409da5c8da6bb4eff7f43/drivers/input/misc/uinput.c).

If measured Python decode/filter/submission overhead remains material, prototype a small native forwarding component (Rust/C/C++) that retains the Qt control panel. Preserve exact mapping, pressure, release behavior and authenticated session ownership. Compare the same input stream and backend capabilities; do not claim a language change alone guarantees 300 µs.

The 33 ms desktop diagnostic-preview timer is downstream of native injection; increasing preview FPS does not accelerate osu! input. Likewise, native Linux input does not inherently require a new kernel driver for a first optimization pass.

### 5. Assess ADB limitations before enabling its burst mode

**Priority: transport experiment, not a blind switch.**

AOSP documents historical per-stream acknowledgement gating and an experimental `ADB_BURST_MODE` that allows multiple writes in flight. Its published improvement concerns large file-transfer throughput, not sub-millisecond input latency. [AOSP delayed-ACK/burst design](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/docs/dev/delayed_ack.md).

Our host client is platform-tools **37.0.1**. The currently negotiated feature list does **not** include `delayed_ack` (`audit/evidence/latency-research-2026-10-31/adb-capabilities.json`). That establishes current negotiation only, not which endpoint or configuration is responsible or whether another firmware would support it. There is no evidence that changing one environment variable will fix this phone's latency. Changing a running ADB server also interrupts active routes and should be a disclosed controlled experiment, not a background tweak during gameplay.

Avoid concurrent high-volume ADB logs/file copies in clean latency tests. Our passive recorder added some ADB traffic; future traces should be buffered locally and exported afterward. This reduces measurement interference, not necessarily the underlying app delay.

### 6. Prototype direct accessory USB if ADB remains the bottleneck

**Priority: strongest architectural alternative; higher implementation effort.**

Android Open Accessory provides direct app-to-host bulk communication: the PC is USB host and the phone enters accessory mode. A compatible Android app accesses an accessory descriptor/file descriptor, while a desktop component owns the bulk endpoints. This can remove the adbd/ADB-server multiplexing path and loopback TCP hops. Hardware support must be verified on this exact S22 firmware. [AOSP AOA protocol](https://source.android.com/docs/core/interaction/accessories/aoa), [Android accessory API](https://developer.android.com/develop/connectivity/usb/accessory).

A native Linux receiver using asynchronous libusb transfers can keep a receive request pending and submit the resulting pen report promptly. Transfer-buffer lengths and short-packet behavior matter: do not wait to fill a large application buffer before processing a small report. Keep authentication, sequence and freshness controls; moving off TCP does not remove their purpose. [libusb asynchronous transfer API](https://libusb.sourceforge.io/api-1.0/group__libusb__asyncio.html).

**Limits:** USB bulk uses available bandwidth rather than the scheduled bandwidth of interrupt/isochronous transfers; direct bulk is not a hard latency guarantee. [Linux USB transfer model](https://docs.kernel.org/driver-api/usb/usb.html).

AOA enumeration can disconnect/re-enumerate USB and require a phone permission prompt. Do not switch modes automatically while the user is playing. Use an explicit, scheduled prototype test with fallback to the existing paired route.

**Important direction distinction:** AOAv2's HID feature sends accessory input **to Android**. It does not turn a normal phone app into a PC-facing USB HID tablet. AOA bulk plus desktop uinput is the relevant experiment. [AOSP AOAv2 HID direction](https://source.android.com/docs/core/interaction/accessories/aoa2#hid-support).

### 7. Treat physical source-rate changes as a separate investigation

No documented stock Android application API was found in the reviewed primary material to force this S22 Ultra's pen digitizer to 1,000 genuinely measured positions/sec. Read-only inspection found the vendor `sec_epen` sysfs directory but unprivileged enumeration was denied; no controls were written and no rate-change claim is justified. Public driver/firmware evidence would need to match SM-S908B and the installed firmware before suggesting a vendor control.

Do not infer that Samsung's advertised pen-rendering latency is a raw sensor lower bound. Do not confuse touchscreen sampling specifications with the pen digitizer. Do not claim that a 1 kHz transmission timer creates 1 kHz fresh measurements.

If hardware timing cannot be changed, a higher output cadence can only repeat or estimate positions between measured samples. Prediction may reduce perceived delay but introduces position error. Android describes predicted events as estimates that must be replaced by actual events; such rendering behavior is not proof of lower real input latency. For osu! accuracy, prediction should be a separate explicit experiment, not the default optimization. [Android motion prediction](https://developer.android.com/develop/ui/views/touch-and-input/stylus-input/advanced-stylus-features).

### 8. Evaluate game/display timing after pre-injection burstiness is understood

For lazer/osu!framework, the documented input thread normally runs at 1,000 Hz; this is an application processing cadence, not a guarantee of new hardware samples or a 1 ms maximum response. The user's exact client/configuration must be identified before applying client-specific settings. [osu!framework threading](https://github.com/ppy/osu-framework/wiki/Threading).

Game scheduling, Wayland presentation and monitor scanout affect physical motion-to-visible response, but our observed bursty timestamps are at the virtual input device before the game consumes them. Changing game frame limits alone cannot explain away or necessarily repair that upstream behavior. Measure both stages rather than tuning unrelated display settings first.

## Measurement needed to choose the winner

Implement passive, bounded, timestamped tracing in the normal app/receiver, with an explicit run start and no instrumentation process restart while the user plays. Record callback and history age, queue dwell, socket-write duration, host processing and native submission. Match session/packet/event identities. Export trace buffers after the run and record any overflow, loss or reset.

Perfetto can correlate Android input, UI work, scheduler delays, CPU frequency and application trace sections, helping distinguish waiting for a frame from CPU starvation or runtime pauses. Restrict categories to the question being tested; profile overhead itself. [Perfetto system tracing](https://perfetto.dev/docs/getting-started/system-tracing).

Phone-local and host-local times are directly measurable on their own clocks. Cross-device one-way timing needs an offset/uncertainty model or a shared hardware time base. If uncertainty is too large relative to 300 µs, report **inconclusive** rather than a false pass. Report percentile tails, observed maximum and deadline-violation count as well as averages. A finite observed maximum is not an unconditional real-time guarantee.

## Recommended experimental sequence

| Order | Experiment | Primary decision |
|---:|---|---|
| 1 | Add passive stage tracing and verify normal Settings/lifecycle use | Can measurements run without interrupting interaction? |
| 2 | Unbuffered contact **and hover**, otherwise unchanged | Does source-to-callback waiting and burstiness shrink? |
| 3 | Independent PONG receive with unchanged wire/security | Do heartbeat-period tails and queue stalls disappear? |
| 4 | Buffer reuse and complete-report uinput writes | Which allocation/syscall work is measurable? |
| 5 | Native receiver A/B, only if host overhead warrants it | Is Python a material contributor? |
| 6 | Scheduled AOA + asynchronous libusb prototype | Does bypassing ADB materially improve one-way bounds/tails? |
| 7 | Vendor source-rate investigation and separately labeled prediction | Can fresh measurement cadence change on stock hardware? |

Keep a paired baseline for each change; use the same map/workload, hover/contact mode and profile. Confirm smoothing remains zero for the gaming baseline; currently persisted Default and osu! profiles are zero. Changing CPU power policy or enabling real-time scheduling should follow evidence of scheduling delay, not be bundled into the first A/B test. Intel pstate's governor name alone is not a measurement of CPU throttling.

**Research outcome:** materially lower added latency is worth pursuing; current results do not establish a permanent 2 ms forwarding floor. The first small changes have a documented mechanism and one is a reproduced bug. The total 300 µs hard maximum and 1,000 fresh measurements/sec remain unproven requirements, not promises.

## Follow-up: ADB transport acknowledgement window

ADB has an opt-in Burst Mode that permits further transport writes without waiting for each acknowledgement. Google documents it as experimental and disabled by default. [Official ADB guide](https://developer.android.com/tools/adb#adb-burst-mode-starting-with-adb-3600). AOSP explains its byte-credit window; large-file throughput results do not establish small pen-packet latency. [ADB transport design](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/docs/dev/delayed_ack.md).

Read-only inspection of the already-running server found ADB 37.0.1, the NATIVE USB backend, `burst_mode: false`, and no host `delayed_ack` feature. The phone is absent, so negotiated route support is unknown. AOSP Android 14 advertises the device-side feature, but that does not prove this Samsung build supports it. [Android 14 implementation](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/android14-release/transport.cpp).

This makes a same-route Burst Mode comparison a lower-disruption candidate before promoting the accessory prototype. **No daemon restart, mode change, benchmark or phone operation was performed.** The saved physical USB trials did not record this setting, so current host state must not be retroactively attributed to them.

The physical USB harness now records server version/backend/Burst Mode, host feature advertisement and route feature advertisement before timing starts. Missing command output or an absent phone stays unknown. A host without the feature does not establish that the device lacks it. Four tiny parser tests pass; actual harness/device integration remains untested.

For a later scheduled comparison: retain the same app build, TLS/pairing, USB cable, source rate and smoothing; save existing reverse routes; change only Burst Mode at server startup; restore those routes; verify `delayed_ack` negotiation; and compare ordered delivery, inter-packet gaps, phone queue/write tails and drops. Restarting the shared ADB server interrupts its connections, so it must occur between idle trials, never during a stroke or game. Preserve the user's resource constraint: no emulator, large transfer or stress build is needed to test this setting. Keep the USB backend fixed; its current observed value is NATIVE regardless of defaults described elsewhere.

Evidence: `adb-burst-mode-preflight.json` and `adb-transport-metadata-unit.txt` under `audit/evidence/passive-tracing-2026-10-31/`. A 300 µs maximum and 1 kHz fresh sensor rate remain unverified.
