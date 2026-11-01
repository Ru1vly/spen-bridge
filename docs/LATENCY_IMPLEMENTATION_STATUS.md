# Latency implementation status

Active objective: implement improvements that provide the best possible latency and packet rate, using the S22 Ultra over USB to the Fedora desktop. The earlier 300 µs maximum and 1,000 sends/sec requirements remain unachieved end-to-end requirements; they have not been redefined as a percentile or a simulated-link result.

## Progress in the first implementation pass

Application changes:

- `PenSurfaceView`: persistent unbuffered pointer-source dispatch on API 30+, covering hover and contact on the S22's Android 14; accepted contact-stream fallback on API 26–29.
- `PenTransport`: PONG reads run on a separate bounded single-worker executor. One ordered writer continues sending while a response is pending. Expected sequence/content checks, a two-second response deadline, raw-socket cancellation, generation boundaries and bounded shutdown remain enforced. Completion notification occurs after the Future reaches its done state.
- `Protocol.EventEncoder` / `SocketProtocolLink`: single-writer reusable frame storage and synchronous length-limited writes avoid allocating/copying a payload and frame for every production send. The immutable convenience API and generic test links retain independent packet copies. Protocol-v2 wire format is unchanged.
- Linux backend: combine the native events of each individual sample into one uinput write ending with SYN_REPORT. No timer-based batching and no accumulation across input samples. Aligned partial writes complete without duplicating edges; failed frames are discarded rather than replayed on reset.

## Evidence

Root: `audit/evidence/latency-improvements-2026-10-31/`.

### Simulated-link sender latency

Production PenTransport/SessionBuffer, approximately 480 events/sec, controlled PONG delay, JVM only:

| PONG delay | Earlier p99 queue time | New p99 queue time | New delivery |
|---:|---:|---:|---:|
| 0 ms | 216.9 µs | 174.1 µs | 1,243/1,243 |
| 10 ms | 1,853.3 µs | 161.1 µs | 1,245/1,245 |
| 60 ms | 51,855.4 µs | 144.7 µs | 1,240/1,240 |
| 150 ms | repeated resets; 0 sent | 141.2 µs | 1,247/1,247 |

No errors or reconnects occurred in the new observations. These are separate runs on a general-purpose host, not matched physical USB trials. Maxima still vary: the new 60 ms case had a 2,372 µs maximum, despite low p99. This does not establish a 300 µs maximum.

### Sender packet-rate test

Production queue/encoder/writer with a simulated link and 150 ms PONG replies:

- 3,000 one-event packets over 2.999 s: approximately 1,000 packets/sec, all 3,000 events delivered, no errors; p99 queue time 554 µs, observed maximum 6,691 µs.
- 3,000 five-event packets over 2.999 s: approximately 1,000 packets/sec / 5,000 events/sec, all 15,000 events delivered, no errors; p99 648 µs, maximum 2,710 µs.

These are short sender-capacity tests. They exclude actual pen sampling, TLS/socket backpressure, ADB, USB, OS injection and display. They do not imply 1,000 fresh S Pen measurements/sec or reliable physical USB cadence.

### Linux input submission

Paired AB/BA comparison: six rounds per variant on the same newly created, exclusively grabbed virtual device, benchmark process pinned to one CPU. Values below are medians of per-round statistics; no desktop input was sent.

| Mode | Median before | Median combined-write | p99 before | p99 combined-write |
|---|---:|---:|---:|---:|
| Pointer | 22.215 µs | 20.153 µs | 50.644 µs | 42.114 µs |
| Tablet | 21.557 µs | 18.569 µs | 48.163 µs | 41.352 µs |

The initial unpaired before/after runs are retained too; their variation is why the optimization decision uses the paired experiment. Native write consolidation is a measured small improvement, not an explanation for millisecond USB or Android scheduling delay.

### Validation

- Android debug/release assembly and lint completed successfully. Ordinary application tests restored after opt-in audit fixtures: **46 passed**, zero failures/errors.
- Python isolated environment: **131 passed, 1 optional-environment skip, 19 subtests**. Qt/GI-capable environment: **132 passed, 19 subtests** (two upstream deprecation warnings).
- Real Linux kernel checks passed for pointer/tablet: contact/tool/barrel/pressure/tilt, reset, remapping, stale-flag exit, authenticated TLS disconnect release. Only newly created, exclusively grabbed devices were exercised.
- New sender regressions cover delayed PONG with input and UP/CANCEL still transmitted, missing PONG despite continuing writes, mismatched PONG, and stop/join during pending read. Real TLS test verifies length-limited sending does not leak unused buffer bytes.
- Native writer tests cover complete-frame ordering, aligned short writes, write failure without stale replay, and nonprogress/misaligned write rejection.
- New Python tests/benchmark scripts pass Ruff. Existing legacy typing-style notices in the backend were not treated as functional failures.
- A monitor smoke test incorrectly assumed every live desktop was at least 1920×1080; it now checks valid positive reported dimensions, allowing the user's current smaller/scaled mode. This is a test-environment correction, not a product display change.

## Second pass: passive tracing and physical USB capacity

Bounded debug-only Android traces and opt-in desktop traces now record source, queue, TLS write, host decode and submission boundaries. Export occurs after capture. Sequence, count and payload fingerprints permit conservative pairing without retaining pen coordinates. Release builds omit the debug receiver and synthetic generator. Clock-offset intervals are reported as uncertainty; cross-device timestamps are not directly subtracted.

Physical USB trials used the production Android sender, TLS and Python receiver with an isolated in-memory sink, not OS injection or real pen samples:

| Trial | Delivered | Observed packet rate | Android queue p99 | TLS write p99 |
|---|---:|---:|---:|---:|
| 1 kHz, tracing enabled | 5,000 / 5,000 | 1,000.20/sec | 785.273 µs | 562.852 µs |
| 3 kHz, tracing enabled | 9,000 / 9,000 | 3,001.01/sec | 1,052.265 µs | 232.813 µs |

There were no observed queue resets or trace overflows. These short trials establish transport capacity, not 1,000 fresh sensor measurements/sec or a 300 µs maximum. Host submission figures from these runs measure an in-memory sink and must not be presented as uinput latency. Evidence: `audit/evidence/passive-tracing-2026-10-31/production-usb-results.json` and associated binary captures.

A cancellable byte-stream Socket adapter and shared pinned-TLS authentication path are unit-tested and emulator-validated as a foundation for a direct USB experiment. They are not wired into the production USB route. Android accessory kernel reads require an explicit cancellation design; a naive blocking file-descriptor adapter is insufficient. No USB mode change has been performed.

## Deployment state

The improved debug APK and passive diagnostics were installed before the host reboot, preserving pairing and preferences. Settings opened and returned to the canvas in the same app process during the recorded check. See `deployment.json` and `settings-runtime.json` in the evidence directory for historical deployment details.

After the host reboot, the latest desktop was started with passive diagnostics; `current-runtime.json` identifies the new process and private trace directory. The phone is currently absent from ADB. No phone restart or reinstall was performed during this continuation. Subsequent source-only stream adapter and trace timer cleanup changes are not installed on the phone.

Current Python validation: **154 passed, one optional-environment skip, 23 subtests passed**. Android stream prototype: **53 tests passed**, debug/release assembly and lint passed. Final logs: `android-stream-prototype-tests.txt` and `android-stream-prototype-final-build.txt`. The earlier build log retains the corrected test compilation failure.

## Completion gates — goal remains active

- [x] Implement and test unbuffered hover/contact request in source.
- [x] Remove PONG wait from ordered event sender; verify timeout/cancellation safety.
- [x] Reuse production encoding storage while preserving the wire contract.
- [x] Benchmark native write consolidation and verify real-kernel release safety.
- [x] Demonstrate 1,000 packets/sec capacity in the production sender against a simulated link.
- [x] Add passive, bounded per-stage traces in the normal phone app and receiver, with sample/session identity, overflow reporting and no process restart during a capture.
- [x] Deploy the improved debug APK with pairing/data preserved and verify normal Settings/lifecycle behavior on the S22.
- [x] Start the latest desktop backend in a disclosed, controlled restart.
- [ ] Measure actual USB hover/contact delivery, packet/event rates, tails and drops, with smoothing disabled and then configured defaults.
- [ ] Attribute remaining delay between Android dispatch, queue, TLS/ADB and host submission; establish one-way uncertainty before claiming microsecond end-to-end measurements.
- [ ] Evaluate a native receiver/direct accessory USB experiment if ADB/host overhead remains dominant; do not substitute a simulated-link success for this architecture decision.
- [ ] Reconcile achievable fresh sensor cadence with 1 kHz output reporting without relabeling repeats/predictions as measurements.
- [ ] Verify the agreed 300 µs boundary or explicitly report which target remains unachieved. Do not mark the objective complete based only on current tests.

The user deferred real-pen testing and requested continued benchmarks. Remaining gates require distinguishing transport capacity, fresh sensor cadence and end-to-end delay; the objective remains active.

## Receiver deadline experiment

A proposed replacement of per-packet `asyncio.wait_for` with an explicit timeout context was benchmarked and rejected. The installed Python 3.14 implementation already delegates positive-timeout waits to a timeout context; the hypothesized extra task was absent. Two six-round AB/BA buffered-parser experiments gave inconsistent small differences (first prototype slower, confirmation slightly faster). Neither measured TLS, USB, OS injection or real pen freshness. No production optimization was retained from this experiment.

Evidence: `frame-deadline-benchmark.json`, `frame-deadline-benchmark-confirmation.json` and `python-final-frame-deadline.txt` in the passive-tracing evidence directory. New regressions enforce a complete-frame deadline for stalled headers and bodies and propagation of external cancellation. This experiment rules out the assumed task-per-packet issue on this installed interpreter; it does not explain the observed millisecond tails.

## Direct USB host prototype

A native Linux libusb relay is implemented under `native/usb-relay/`. It forwards encrypted bytes to the existing loopback receiver; it does not terminate TLS, hold pairing credentials, parse events, switch USB modes or detach kernel drivers. It accepts explicitly selected devices already in accessory mode and excludes their ADB interfaces. Fixed buffers, partial-transfer accounting, progress deadlines and joined worker cleanup are implemented. This is a host-side prototype, not a deployed mobile transport.

Seven native relay tests passed with Clang AddressSanitizer and UndefinedBehaviorSanitizer, including production descriptor selection, real TLS/pairing over the relay, rejection of an incorrect pairing proof, fragmented timeout transfers, multi-buffer byte preservation, zero-length USB packet handling, bounded idle/blocked-write cleanup and invalid transfer progress. GCC sanitizer runtimes were absent on the host; Clang's available runtimes were used. Clang static analysis reported no diagnostics. Production builds use strict compiler warnings.

A paired host-only synthetic benchmark delivered all 16,000 measured records through the relay across 1 kHz and 3 kHz trials (plus 800 warm-up records). The source was a Linux thread and the USB connection was a socket fixture. Both sides used the same host monotonic clock; TLS remained active and the receiver used an in-memory sink. This does **not** measure Android, physical USB, fresh sensor sampling or OS injection.

| Host-only synthetic trial | Direct TLS median | With relay median | Direct p99 | With relay p99 |
|---|---:|---:|---:|---:|
| 1 kHz | 283.164 µs | 302.862 µs | 864.360 µs | 868.909 µs |
| 3 kHz | 171.424 µs | 185.272 µs | 669.265 µs | 809.885 µs |

Values are medians of two per-run statistics from AB/BA ordering. They characterize software feasibility and added relay cost only; they do not establish that AOA is faster than ADB. The benchmark fixture reports simulated USB disconnect as error -4 after the client closes following its final acknowledged PING; this is retained in the raw record, not hidden as an error-free hardware run. Every measured event was checked for exact order before teardown.

Evidence: `native-usb-relay-build.json`, `native-usb-relay-sanitized.txt`, `native-usb-relay-host-benchmark.json` and `python-native-usb-relay.txt`. Physical enumeration currently found no compatible accessory-mode device. No USB mode change was attempted. The next direct USB gate is a cancellable Android accessory transport, followed by a disclosed physical trial when the phone is available. The 300 µs maximum requirement remains unachieved.

## Android accessory prototype and receiver shutdown

The debug-only Android accessory prototype is implemented and tested on an emulator. It isolates blocking USB I/O in a one-shot helper process and provides cancellable nonblocking IPC to the parent. Nine functional lifecycle/authentication checks passed, including real Android Conscrypt pinned TLS over the helper; release APKs contain none of the prototype classes. The physical phone was not modified. See [prototype details and remaining gates](ANDROID_ACCESSORY_PROTOTYPE.md).

The latest synthetic emulator trial delivered 2,000/2,000 records at 1 kHz; the 3 kHz trial reset after 243/6,000. Earlier complete delivery and subsequent failures are retained. This is not a physical accessory USB test and does not establish the requested maximum latency. Do not promote the route or increase stale/backlog limits to hide the failure.

Validation also exposed and fixed a receiver shutdown FD-reuse race: pending accept cleanup could remove an unrelated child-process watcher after the listener FD was closed and reused. The regression fails before the fix and passes after it; cancellation of stop still closes the listener. Current Python suite: 154 passed, one optional skip, 23 subtests. Debug/release builds, lint and 53 Android JVM tests pass. The desktop process already running predates this shutdown-only source fix; no restart or phone reinstall was performed.

## Native relay liveness safeguard

The experimental host relay now disconnects when no positive inbound phone bytes arrive for three seconds. Host-originated traffic and USB zero-length packets cannot keep a stopped phone alive. This retains the sender's existing one-second heartbeat and does not introduce a packet batching delay or relax the 300 µs input requirement.

Nine native tests passed with Clang AddressSanitizer and UndefinedBehaviorSanitizer. The new authenticated-session test keeps the simulated USB endpoint open, verifies healthy heartbeats for more than three seconds, then stops inbound traffic and observes receiver ownership cleared and reset invoked. Another test confirms downstream-only traffic cannot refresh phone liveness. This proves the software timeout/reset path, not physical S22 kernel input-release timing. Clang static analysis reported no diagnostics.

A new host-only synthetic benchmark retained all 16,000 measured relay records across 1 kHz and 3 kHz trials, plus warm-up. It uses a socket-backed USB fixture, TLS and an in-memory sink. Timing varied from earlier runs; no before/after speedup is claimed for this safety change. The physical phone remained absent from ADB, and neither the normal desktop nor phone was restarted.

Evidence: `native-relay-liveness-verification.json`, `native-relay-liveness-sanitized.txt`, `native-relay-liveness-host-benchmark.json` and `python-relay-liveness.txt` under the passive-tracing evidence directory. Remaining direct USB gates include helper replacement ordering, attribution of the emulator 3 kHz reset, physical bulk/permission/recovery tests and matched real-pen measurements. The goal remains active and the 300 µs maximum remains unachieved.

## Interactive resource constraint

The user reported that resource-heavy jobs prevent normal use of the desktop. The owned emulator and Gradle/Kotlin build daemons were stopped. Do not automatically restart emulators, full builds or high-rate benchmarks while the user is using the computer. Continue with lightweight inspection and edits; leave heavyweight verification pending rather than competing with interactive work. This is a resource constraint, not a request to pause or complete the latency objective.

## Offline reset attribution work

The last emulator result, `android-helper-stop-before.json`, passed ten lifecycle/authentication checks, including helper stop with the parent main looper blocked. That rules out the tested main-looper dependency hypothesis; no speculative shutdown-dispatch fix was retained. Under that run's conditions, delivery failed at both 1 kHz (368/2,000) and 3 kHz (113/6,000). Earlier successful trials are retained and must not be treated as sustained guarantees.

A streaming Android-only trace summarizer and three passing lightweight unit tests now distinguish queue admission/staleness resets and local queue/write stages without new device runs. Offline reanalysis of the saved physical USB 1 kHz synthetic trace reproduces all 5,000 transmissions, zero resets/overflow, queue p99 785.273 µs and write-call p99 562.852 µs. Evidence: `android-usb-1000-offline-summary.json` and `android-trace-summary-unit.txt`.

Optional per-stage capture/export is added in the emulator harness source, but the new Kotlin integration remains unbuilt/unvalidated. Full builds, emulation and stress benchmarks remain stopped under the user's resource constraint. Last full Python validation remains the recorded 154-test run; the new summarizer has only its targeted three-test validation. No phone or running desktop changes were made in this pass. The objective remains active.

## Read-only ADB transport finding

The already-running ADB 37.0.1 server reports Burst Mode disabled, a NATIVE USB backend and no advertised host `delayed_ack`. AOSP's acknowledgement-window design makes an opt-in Burst Mode comparison a candidate for reducing transport waiting before committing to accessory USB. This is a hypothesis, not a measured latency improvement. The disconnected phone's support is unknown, and older captures did not record this setting.

The physical USB diagnostic harness now captures transport configuration before timed trials. A new parser has four passing tiny tests and does not conflate host-disabled with device-unsupported. No daemon or app was restarted, no configuration changed, and no high-load job was launched. See [follow-up research](USB_LATENCY_RESEARCH_2026-10-31.md) for primary sources and the controlled comparison requirements. Actual USB testing remains deferred; the goal is not complete.

## Resource-bounded verification attempt

A kernel-enforced transient service was verified at 5% of one CPU, 768 MiB memory maximum, 512 MiB memory high threshold, no swap, nice 19, one build worker and a five-minute runtime limit. The compiler launcher refuses unrestricted CPU/memory/swap settings. Four tiny guard tests passed. This is a job-local budget; it changes no global desktop resource settings.

One offline incremental debug assembly was attempted within those limits, with no emulator, install or performance workload. It timed out during Gradle startup: reported runtime 5min 1.462s, CPU time 15.084s, memory peak 217.5 MiB, swap 0. All of its Java processes exited. The limit was not increased and the build was not retried unrestricted. Therefore the pending Kotlin trace integration remains uncompiled/unverified; this result is not a source compilation failure or a successful build.

The physical USB harness now defaults to a unique trial directory and rejects a nonempty explicit output directory, preserving the existing baseline for future Burst Mode comparisons. This path change has static validation only, not a new device run.

Evidence: `android-limited-debug-compile.txt`, `android-limited-debug-budget.json` and `resource-guard-unit.txt` under the passive-tracing evidence directory. The physical phone is still unavailable and the latency objective remains active.

## Physical validation gate

Read-only revalidation again found no attached ADB device. The next decision-changing experiment is the matched physical USB acknowledgement-window comparison and the subsequently deferred real-pen freshness capture. Existing synthetic capacity results do not complete the 300 µs or fresh-sensor requirements. The optional accessory route must not be promoted based on software fixtures, and further speculative changes cannot be called measured improvements. No build or emulator process remains active.

The repeated external dependency is availability of the S22/USB measurement session. Resume from the installed normal debug app and preserved pairing when that device is available; no emulator or app reinstall is inherently required for the existing synthetic USB baseline. See `physical-validation-gates.json` for the incomplete acceptance evidence. Keep the full objective intact.
