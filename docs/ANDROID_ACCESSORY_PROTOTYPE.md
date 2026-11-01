# Android accessory transport prototype

This debug-only experiment removes the assumption that a blocking accessory file descriptor can be cancelled safely by closing it from another thread. Blocking accessory I/O lives in a dedicated, non-exported `:accessory_relay` process. The normal app sees a nonblocking socket pair with explicit read deadlines, bounded write progress and shutdown-based cancellation. Stopping the helper terminates only that helper process, guarded by its exact process name.

The prototype is not enabled in the normal app, is absent from release APKs and has not been installed on the physical S22. Existing USB-over-ADB and Wi-Fi connections are unchanged. It requires API 30+; the application's ordinary minimum SDK remains 26.

## Components

- `DescriptorByteTransport`: owns the parent IPC descriptor; reuses poll structures, uses nonblocking reads/writes, observes read deadlines and a two-second write progress deadline, and shuts down both socket directions before closing. Polling is bounded to 25 ms for cancellation; available bytes move immediately.
- `AccessoryRelayService`: private Binder/Messenger entry point, same-UID message check, fixed 16 KiB directional buffers, one read and one write worker, one-shot ownership and a 20-second startup watchdog. Active experiments are limited to 1–15 seconds. Accessory permission must already be granted; no permission request or USB mode change is made.
- `AccessoryStreamConnection`: publishes the cancellable parent socket before binding, transfers descriptors by Binder, consumes a local readiness header, checks helper PID isolation and observes helper death. Close signals stop asynchronously; diagnostic callers can wait for helper death before starting a replacement session.
- `StreamSocket` / `SocketProtocolLink.openStream`: the existing public stream adapter and certificate-pinned TLS/mutual pairing path. Credentials stay in the parent, and the helper forwards opaque encrypted bytes.

The accessory reader uses a full-size buffer because Android requires a complete USB transfer to be read at once. The paired native host prototype caps writes at 16 KiB. Physical S22 behavior still needs verification. [Android UsbManager documentation](https://developer.android.com/reference/android/hardware/usb/UsbManager#openAccessory(android.hardware.usb.UsbAccessory)). Socket-pair descriptor transfer and Binder messaging use public Android APIs. [ParcelFileDescriptor](https://developer.android.com/reference/android/os/ParcelFileDescriptor#createSocketPair()), [bound services](https://developer.android.com/develop/background-work/services/bound-services).

## Emulator validation

`audit/run_accessory_emulator_selftest.py` refuses physical devices, verifies emulator properties before installing, and invokes instrumentation only on its explicitly selected emulator. Instrumentation restarts that emulator's target app; it must never be used as a passive phone capture.

```sh
server/.venv/bin/python audit/run_accessory_emulator_selftest.py --serial emulator-5556
```

The runner allocates its own ADB reverse route, private ephemeral TLS identity and owner-only app-cache config, verifies transfer without printing credentials, and uses only an in-memory receiver. Cleanup removes its private config/route and stops its receiver. No native input device or MotionEvent is created.

Ten functional emulator checks passed, including helper termination while the parent main looper was blocked: read timeout, cancellation of blocked write, cancellation of a blocked helper read, bidirectional multi-buffer preservation, idle helper watchdog, cancellation before binding, rejection of a wrong certificate pin, rejection of a wrong pairing secret and successful Android Conscrypt TLS/pairing through the helper. The main app process survived all helper terminations within the run.

Throughput is reported separately from those functional checks, including missing records and transport states. The source is synthetic and paced in an Android emulator. The fixture uses a TCP descriptor through ADB in place of accessory USB; this is not a direct USB timing test.

| Latest emulator trial | Offered | Written / host received | Median TLS write call | p99 write call | Maximum write call |
|---|---:|---:|---:|---:|---:|
| 1,000/sec | 2,000 | 368 / 368 | 415.016 µs | 8,562.515 µs | 20,035.788 µs |
| 3,000/sec | 6,000 | 113 / 113 | 721.032 µs | 7,903.292 µs | 9,331.202 µs |

The latest completed run did not sustain delivery at either rate. The user reported unacceptable desktop resource contention during this work; the emulator and build daemons were then stopped. The experiment does not establish which stage caused each reset. Earlier runs, including 2,000/2,000 delivery at 1 kHz, remain in the evidence history. An earlier run delivered all 8,000 source records, followed by a repeat that failed the 3 kHz completeness assertion. All evidence is retained; no failure was erased by selecting a passing run. Emulator/host load and the extra process/TLS route differ from physical S22 measurements. None of these figures proves fresh 1 kHz pen sensing or 300 µs end-to-end latency.

Evidence under `audit/evidence/passive-tracing-2026-10-31/`:

- `android-accessory-emulator-validated.json`: functional checks and latest partial-delivery benchmark.
- `android-accessory-emulator-capacity.json`: earlier complete-delivery run whose host harness subsequently hit the listener shutdown race.
- `android-accessory-emulator-capacity-final.instrumentation.txt`: retained completeness failure from the repeat.
- `android-accessory-build-verification.json`: APK hashes, release isolation and 53 passing JVM tests.
- `android-accessory-prototype-build.txt`: debug/release assembly, unit tests and lint.

## Remaining gates

1. Serialize replacement helper sessions and test reconnect after overflow/timeout; closing a session is asynchronous and callers must not assume its process has exited immediately.
2. Diagnose the 3 kHz reset with per-stage traces. Preserve bounded queue/freshness and transition safety; increasing backlog to hide overload is not an improvement.
3. Verify physical accessory permission/open/close, full-transfer reads, USB detach and recovery on the S22 without disrupting ordinary app navigation.
4. Verify fast host-side disconnection and input release when the helper stops while the USB device remains attached. A transparent bulk byte stream alone cannot be assumed to signal TCP-style EOF; the native relay now has a three-second inbound-byte liveness policy verified against a simulated attached peer and authenticated receiver. Physical helper-stop to kernel input-release timing still needs verification before real OS input.
5. Connect the experimental route to the production sender through an explicit opt-in after those gates. Keep certificate pinning, mutual proofs, one owner, raw cancellation and safe release.
6. Compare physical AOA and ADB under matched conditions, including fresh sensor cadence, packet/event rate, tails, drops, CPU/thermal state and clock uncertainty. The 300 µs maximum remains unachieved.

## Shutdown race fixed during validation

The receiver previously closed its listening socket before awaiting cancellation of `sock_accept`. Concurrent cleanup reused that FD for an ADB child-process watcher; the old accept callback removed the new watch, leaving an exited child unreaped and the harness waiting indefinitely. The fix waits for accept cancellation before closing the listener, including cancellation of `stop()` itself. A deterministic real FD-reuse regression failed before the fix and passed after it. The test also verifies listener closure when stopping is cancelled. The existing desktop process was not restarted for this source change.

## Lightweight offline diagnosis and pending tracing

The saved main-looper-blocked check passed (`android-helper-stop-before.json`); it did not reproduce the proposed dependency on the parent main looper. No shutdown-dispatch change was made on that assumption. The helper can also terminate after parent IPC EOF. This does not prove replacement ordering under every cancellation/open race.

`audit/summarize_android_trace.py` streams existing bounded trace files without loading every record into memory. It separates queue-to-write delay, write-call time, admission resets and stale-queue resets, flags overflow, and caps detailed reset output. It makes no cross-device one-way latency or fresh sensor rate claim.

```sh
server/.venv/bin/python audit/summarize_android_trace.py SAVED_ANDROID_TRACE.bin --output summary.json
```

Three tiny offline unit tests pass. Reanalysis of the existing physical USB 1 kHz synthetic trace retained 5,000 sends, no resets/overflow, queue-to-write p99 785.273 µs and write-call p99 562.852 µs. This is reanalysis of old data, not a new USB trial.

An optional `--trace` flag is added in source to the emulator diagnostic harness. It captures source, queue, write and reset records using the existing bounded debug trace, exports after the run and summarizes the copied files. Tracing adds measurement overhead and must be reported as such. The new Kotlin capture integration is **not built or emulator-validated**: heavy verification remains deferred to respect interactive computer use. No emulator, build daemon or benchmark should be started automatically while the computer is in use.
