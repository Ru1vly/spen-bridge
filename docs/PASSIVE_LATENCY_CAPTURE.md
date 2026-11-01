# Passive latency capture

The capture tool observes the normal debug app without restarting it, reinstalling it or generating input. The desktop must be running with `SPEN_TRACE_DIR`; the current diagnostic launcher records its PID and private directory in `audit/evidence/passive-tracing-2026-10-31/current-runtime.json`. Historical `deployment.json` is not a live process record.

When the user is ready, with the phone connected and the normal app open:

```sh
server/.venv/bin/python audit/capture_normal_input.py --seconds 30 --output audit/evidence/real-pen-next
```

The tool starts bounded traces, waits for capture/export, copies the files and writes `analysis.json`. It checks the phone process identity before and after capture. It refuses a stale desktop PID. ADB discovery supports the persistent local install and the `SPEN_ADB` / `SPEN_ADB_SERIAL` overrides.

Android records contain event timestamps, callback boundaries, queue acceptance, write boundaries, heartbeat times and fingerprints. Desktop records contain complete-frame arrival, decode/dispatch boundaries and heartbeat times. Coordinates and pairing credentials are not recorded. Debug records use bounded memory; overflow must be checked before drawing conclusions. Export happens after capture.

Interpret stages independently. Android source-to-callback delay and queue/write delay share the phone clock. Host decode/submission stages share the desktop clock. Cross-device pairing uses sequence, event count and payload fingerprint, excluding ambiguous matches. Heartbeats bound clock offset; they do not prove equal forward/reverse delay. Never subtract raw timestamps between devices or call half the round trip measured one-way latency.

Count fresh input events separately from packets and synthetic events. A 1 kHz sender can carry repeated, historical or synthetic data; this does not establish 1 kHz fresh sensor sampling. An in-memory diagnostic sink excludes OS input injection. End-to-end 300 µs maximum remains unverified.
