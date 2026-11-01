# S Pen Bridge — full audit, 31 October 2026

## Verdict

The redesigned desktop and Android apps read as native applications, with a clearer task hierarchy and usable compact layouts. **Do not yet claim production-grade low latency or end-to-end freshness.** Two reproducible transport defects remain: synchronous heartbeat waits stall outgoing input, and the receiver accepts input that became stale in transit. No authentication bypass or remote code execution was demonstrated in this audit.

This is a report-only pass: application code was not changed. See `evidence/full-2026-10-31/source-integrity.json`: all 114 fingerprinted application/configuration files match the audit's starting snapshot. New files are audit fixtures, results, screenshots, and this report. Existing uncommitted work was preserved.

## Executive summary

**11 actionable findings: 0 P0, 2 P1, 9 P2, 0 P3.** P1 means fix before making a release-quality latency claim; P2 means a meaningful problem with a workaround or restricted exposure. Severity describes this application's demonstrated impact, not a vendor CVSS score. Coverage limitations below are not counted as additional defects.

1. **P1 LAT-01:** heartbeat replies block the input sender; 60 ms simulated PONG delay produced 51.86 ms p99 queue latency, and 150 ms caused repeated resets with no input delivered in the fixture.
2. **P1 LAT-02:** a 250 ms delayed authenticated pen-down reached the desktop backend; local queue freshness does not cover in-flight TCP data.
3. **P2 UX-01:** USB-only setup cannot save valid pairing data without a non-loopback Wi-Fi host.
4. **P2 SEC-01:** four unauthenticated incomplete TLS connections block a new paired connection while admission is saturated.
5. Remaining P2 items concern runtime font/theme changes, a clickable overlay over the full drawing area, app-profile switching delay, smoothing copy, native-library patch coverage, and Android SDK maintenance.

## Native UI health

This is a provisional source-and-native-render assessment, not screen-reader certification or a hardware frame-rate score.

| Dimension | Score / 4 | Evidence and limitation |
|---|---:|---|
| Accessibility | 3 | Named Qt sliders, Android icon descriptions/headings/live status, scalable Android text; runtime desktop text scaling fails. Actual TalkBack/Orca/NVDA sessions remain untested. |
| Performance | 2 | Bounded buffers, coalesced GUI notifications and inexpensive tonal cards; heartbeat stalls materially affect pen interaction. Physical frame timing remains unmeasured. |
| Appearance / theming | 3 | Semantic light/dark roles and readable tested text pairs; desktop does not follow a runtime system theme change. |
| Platform conformance | 3 | Native Qt controls and Android Views/Material components, normal Back behavior, native keyboard interaction. SDK baseline needs maintenance. |
| Adaptivity | 3 | Desktop rail/tabs and scrollable editors; Android phone/tablet, rotation, keyboard and larger-text matrix. Fold posture, split screen and maximum text scale need device coverage. |
| **Total** | **14 / 20 — Good, with weak dimensions to address** | This score does not override the two transport release concerns. |

**Platform verdict:** native, not a website port. The Connection / Pen settings / App profiles / Preferences separation works; pressure, mapping, buttons and device controls have distinct homes. The active input profile and the profile being edited are differentiated. Android Connect / Drawing area / Controls tabs reduce scanning, and validation reveals the relevant page. Light and dark schemes preserve hierarchy. The compact desktop puts connection setup before the pen canvas, so the canvas requires scrolling at 760×700; this is a conscious tradeoff, not horizontal clipping.

The interface is **One UI-inspired custom styling**, not an official Samsung Qt or Android One UI component library. Android uses Google Material 1.12.0 and AppCompat 1.7.0; desktop uses PySide6/Qt 6.11.2. See `../docs/UI_LIBRARY_PROVENANCE.md`. Visual resemblance is not evidence of official-library provenance or of using the latest dependencies.

## Detailed findings

### [P1] LAT-01 — heartbeat reception blocks outgoing pen events

- **Location:** `android/app/src/main/java/com/spenbridge/app/PenTransport.kt:299–307`; queue policy in `SessionBuffer.kt:7–8,42–48`.
- **Category:** input latency / performance.
- **Evidence:** `evidence/full-2026-10-31/android-transport-latency.json`. An audit-only JVM fixture exercised the production transport and buffer with approximately 480 offered MOVE events/sec and controlled PONG delay. The same worker calls `link.receive(2000)` before it can drain input. At 60 ms delay, p95 was 17.54 ms and p99 51.86 ms. At 150 ms, 1,245 events were offered, zero sent, and 18 error states / 19 connections observed during the 2.6-second offering interval. This fixture uses an immediate retry link and must not be read as the exact real-world reconnect frequency.
- **Impact:** periodic visible stalls on variable-latency Wi-Fi; sustained RTT above the 100 ms freshness threshold can prevent drawing rather than merely increase lag. Zero-delay testing hides the defect.
- **Recommendation:** make receiving PONG asynchronous with respect to event draining. Preserve a single ordered writer, bounded queues, cancellation, handshake ownership, and disconnect release. Add a regression fixture with delayed/missing PONG during continuous contact, including UP/CANCEL handling. Do not simply extend queue age to conceal the stall.
- **Suggested workflow:** `$impeccable optimize` for interaction responsiveness; transport repair also needs protocol-level engineering tests.

### [P1] LAT-02 — freshness stops at the Android queue boundary

- **Location:** `server/protocol.py:1–22` (24-byte event record); `server/server.py` event decoding/dispatch; Android `InputFreshness.kt` and `SessionBuffer.kt`.
- **Category:** input latency / input safety.
- **Evidence:** `evidence/full-2026-10-31/network-delay.json`; fixture `../audit/network_delay_probe.py`. A paired synthetic client traversed an opaque TCP relay with 250 ms upstream delay. The production server delivered the DOWN to its in-memory backend at **250.69 ms** event age. No OS event was injected. Protocol records contain coordinates/pressure/buttons but no source sample time or usable age budget. The current local 100 ms policy cannot assess data already handed to TLS/TCP.
- **Impact:** network recovery can deliver delayed movement/contact to the current cursor context; a local freshness guarantee must not be described as end-to-end protection. This does not imply a remote attacker can authenticate or inject arbitrary input.
- **Recommendation:** design a versioned freshness contract with session-bound monotonic clock-offset estimation or another receiver-verifiable deadline scheme; reject over-budget samples and safely cancel/release held state. Independent device clocks cannot be compared directly. Test delay, jitter, queued DOWN/UP, clock drift, reordering at reconnect boundaries, and recovery without stale replay.
- **Suggested workflow:** `$impeccable harden`; engineering verification must include the transport and both backends.

### [P2] UX-01 — USB setup unnecessarily requires a Wi-Fi address

- **Location:** `android/app/src/main/java/com/spenbridge/app/SettingsActivity.kt:232–246`, contrasted with `PenTransport.kt:255–265`.
- **Category:** onboarding / validation.
- **Evidence:** reproduced in `evidence/full-2026-10-31/mobile-extra/edge-checks.json` and the native `android-usb-only-save-blocked.png`: valid synthetic pairing plus blank Wi-Fi host cannot save. Source confirms Save rejects blank hosts and loopback hosts unconditionally. The USB transport replaces the configured host with `127.0.0.1` and can use paired credentials without a Wi-Fi host. Reproduce by entering a valid port, fingerprint and code, leaving Wi-Fi address blank, and pressing Save; validation blocks saving.
- **Impact:** a USB-only user must supply an irrelevant LAN hostname/address (or a syntactically valid placeholder); changing unrelated settings also encounters this validation.
- **Recommendation:** make the Wi-Fi fallback address optional for USB-only use, with explicit fallback availability and validation when Wi-Fi is enabled. Preserve exact fingerprint/code validation.
- **Suggested command:** `$impeccable onboard` / `$impeccable clarify`.

### [P2] SEC-01 — bounded pre-authentication admission remains easy to monopolize

- **Location:** `server/server.py:38–39,230–253`.
- **Category:** security / availability.
- **Evidence:** `evidence/full-2026-10-31/pipeline.json`: four raw incomplete TLS handshakes consumed all four admission slots; a new valid paired connection failed; admission recovered after those sockets closed. The probe uses a 0.5 s test handshake deadline; production default is 5 s. An attacker able to reach the listener can renew attempts. The separate stress run confirms existing authenticated traffic is not simply displaced by the same flood.
- **Impact:** reconnect or initial pairing can be denied on an exposed LAN listener. This is not an authentication bypass, unbounded task leak, or demonstrated compromise. Loopback-only binding restricts exposure to local processes.
- **Recommendation:** retain the global cap, add source-aware admission/backoff, and consider a separately protected loopback/USB admission path. Do not assume a reserved slot is authenticated before authentication completes. Verify fairness under distributed attempts and normal reconnect bursts.
- **Suggested command:** `$impeccable harden` for user-facing recovery; network admission needs a security regression test.

### [P2] UI-01 — desktop does not follow runtime font and theme changes

- **Location:** `server/gui/main_window.py:101–103`; `server/gui/theme.py:32–35` and per-widget explicit fonts/styles.
- **Category:** accessibility / theming.
- **Evidence:** `evidence/full-2026-10-31/qt-probes.json`: changing QApplication's requested font from 11 pt to 16 pt left the connection hint at 11 pt; `colorSchemeChanged` had zero receivers in the constructed app. Startup renders at 16 pt do adapt, so this is specifically a live-update gap.
- **Impact:** users changing system accessibility text or dark appearance while the app remains open need a restart, and some fixed-size helper text remains small.
- **Recommendation:** respond to application font/palette and system color-scheme changes, rebuild semantic styling without losing edits, and scale helper text through shared roles. Verify open dialogs, painted canvases and focus indicators too.
- **Suggested commands:** `$impeccable adapt`, `$impeccable typeset`.

### [P2] UI-02 — collapsing controls still leaves a clickable overlay inside the mapped canvas

- **Location:** `android/app/src/main/java/com/spenbridge/app/MainActivity.kt:92,138–141,223`; `activity_main.xml` status container.
- **Category:** drawing UX / adaptivity.
- **Evidence:** `mobile-extra/android-full-area-collapsed.png` and XML show a clickable top status chip over FULL mapped area. `collapseBar()` hides only `topBar`; FULL area calculation spans the entire view. The status node advertises “Open connection settings,” and source wires that action, but the targeted emulator tap did **not** open Settings; the restored toolbar Settings button did. See `mobile-extra/edge-checks.json`. This audit does not claim accidental navigation was dynamically reproduced.
- **Impact:** part of the advertised full drawing area remains covered by an interactive control. Its announced navigation action also failed in the targeted emulator probe. The restore button necessarily occupies space too, but an additional always-clickable status chip is avoidable.
- **Recommendation:** provide a deliberate canvas mode: non-intercepting status, hide/fade status during capture, or reserve and communicate an input-safe area. Keep a reliable accessible way to restore controls and read connection state; if a status action is exposed, make its announced action work consistently.
- **Suggested command:** `$impeccable adapt`.

### [P2] LAT-03 — automatic profile switching has a polling delay

- **Location:** `server/gui/main_window.py:42,95–97`; `server/window_watcher.py:49–60`; `server/window_watcher_linux.py` subprocess timeouts.
- **Category:** interaction latency / correctness.
- **Evidence:** source-confirmed 300 ms sleep between focus queries; query execution time is additional (individual Linux subprocess timeouts are 400 ms). This is not a measured 300 ms input transport delay or a guaranteed maximum.
- **Impact:** a stroke immediately after changing focused applications can initially use the previous mapping, button behavior or smoothing profile.
- **Recommendation:** prefer OS focus notifications where available, retain a bounded fallback poll, and define whether a profile is latched for a contact stroke or switched with a safe cancel. Show actual active-profile state promptly; test focus changes during contact.
- **Suggested command:** `$impeccable optimize`.

### [P2] UX-02 — smoothing control conceals its latency tradeoff

- **Location:** `server/gui/profile_sections/buttons_section.py:58–74`; `server/backends/linux_uinput.py:230–233`; equivalent Windows filtering in `server/backends/windows_hid.py`.
- **Category:** UX copy / input latency.
- **Evidence:** slider allows 90%; description only promises stabilization. Linux EMA uses `alpha = 1 - smoothing`. At 90%, its low-frequency lag is approximately nine samples: about 37.5 ms at 240 samples/sec or 75 ms at 120 samples/sec. These are filter-model estimates, not measured device latency. Default/global and osu profiles use zero; Krita uses 15%.
- **Impact:** users can introduce substantial trailing while trying to improve drawing, then attribute it to USB/network performance.
- **Recommendation:** state “More stabilization adds trailing,” label raw/low-latency behavior clearly, and offer an easy zero-smoothing comparison. Keep reported network latency separate from filtering delay.
- **Suggested command:** `$impeccable clarify`.

### [P2] SEC-02 — Python advisory scan does not establish the native Qt patch baseline

- **Location:** `server/requirements.txt:167–190` pins PySide6 and its packages at 6.11.2.
- **Category:** dependency security / release hygiene.
- **Evidence:** Python package advisory scan returned no known findings, but Qt's current vendor advisories explicitly list Qt 6.11.2 as affected by CVE-2026-101201 (QJsonDocument/QBinaryJson), CVE-2026-95620 (HTTP/2 client), and CVE-2026-107590 (QTextCodec iconv). Vendor fixes are 6.11.3 or later / supplied patches. Runtime reports Qt 6.11.2. Version strings alone cannot prove whether a distribution backported fixes.
- **Reachability:** the app uses Python JSON and Python TLS sockets, not a Qt HTTP client or QTextCodec import path. No exploit route through the S Pen wire protocol was demonstrated. Do not present these as three proven remotely exploitable application vulnerabilities. System and bundled wheel builds also have different patch provenance.
- **Recommendation:** record actual shipped native libraries and patch provenance in an SBOM, choose a patched supported Qt/PySide baseline, then repeat native render and backend tests. Scan embedded native components in addition to PyPI and Maven coordinates.
- **Primary references:** [Qt JSON advisory](https://www.qt.io/blog/security-advisory-cve-2026-101201), [Qt HTTP/2 advisory](https://www.qt.io/blog/security-advisory-cve-2026-95620), [Qt codec advisory](https://www.qt.io/blog/security-advisory-cve-2026-107590).
- **Suggested command:** `$impeccable harden` for regression review after the dependency update.

### [P2] PLAT-01 — Android target and component baseline need a deliberate update

- **Location:** `android/app/build.gradle.kts:10–15,24,45–49`.
- **Category:** platform conformance / maintenance.
- **Evidence:** compile/target SDK 34, Material 1.12.0, AppCompat 1.7.0; fresh lint reports OldTargetApi and dependency update notices. Lint finished with zero errors and 33 warnings. The Maven/toolchain OSV scan found no listed vulnerabilities across 64 queried coordinates. Age/update notices alone are not security findings.
- **Impact:** newer target behavior, edge-to-edge/back handling and platform compatibility remain unvalidated; future distribution readiness cannot be inferred from a successful SDK-34 build.
- **Recommendation:** update compile/target SDK and components as a controlled change, test current Android behavior, insets, keyboard, predictive Back and S Pen capture. Define signing/distribution separately: this audit's release APK is explicitly unsigned, not a ready-to-install signed release. Do not treat successful `assembleRelease` as publication readiness.
- **Suggested command:** `$impeccable harden`, then `$impeccable adapt`.

### [P2] PERF-01 — a maximum-size preview batch exceeds a GUI frame budget

- **Location:** `server/gui/main_window.py:544–564`; `server/widgets/scratchpad.py:86`.
- **Category:** rendering performance / recovery after stalls.
- **Evidence:** `evidence/full-2026-10-31/preview-raster.json`: 20 offscreen raster runs per batch at 960×480. A normal 16-point batch took 2.67 ms p95 including raster capture; a 2,048-point batch took **50.07 ms p95 / 55.13 ms max**. This is a synthetic full-buffer stress case, not the normal 480 Hz workload and not a physical display FPS measurement.
- **Impact:** after a GUI stall or a large drained queue, painting the retained preview in one timer callback can add another visible pause. The operating-system input path is separate; this does not demonstrate a 50 ms OS injection penalty.
- **Recommendation:** give preview recovery a frame-time budget, discard stale visual history safely at stroke boundaries or reduce redundant geometry, and retain accurate input dispatch. Test normal drawing and resumption after a deliberately stalled GUI.
- **Suggested command:** `$impeccable optimize`.

## Measured performance and latency

### Android sender queue — production logic, simulated link

Each row offered events for 2.6 seconds, approximately 480/sec. Delay is enqueue-to-fake-link-send, not screen or network latency. The fake link controls heartbeat response time; it does not simulate bandwidth, Android scheduling, radio power saving, sensor sampling, or display refresh.

| PONG delay | Offered / sent | p50 | p95 | p99 | Maximum |
|---:|---:|---:|---:|---:|---:|
| 0 ms | 1,236 / 1,236 | 0.075 ms | 0.155 ms | 0.217 ms | 2.49 ms |
| 10 ms | 1,241 / 1,241 | 0.058 ms | 0.137 ms | 1.85 ms | 10.12 ms |
| 60 ms | 1,244 / 1,244 | 0.046 ms | 17.54 ms | 51.86 ms | 60.20 ms |
| 150 ms | 1,245 / 0 | — | — | — | repeated reset |

Measured stop times were 0.31–0.42 ms for this cooperative fake link only. They do not establish real DNS/socket/UI-lifecycle shutdown times. The production join bound is 1.5 seconds and remains a scenario to verify on devices.

### Desktop TLS pipeline — loopback synthetic client

Timestamp taken immediately before packet write, ending at the production server's in-memory backend callback. Same-process scheduling/client work is included; Android, Wi-Fi/ADB, real OS injection and display are excluded. Four-sample batches timestamp samples together: the table excludes real-world time spent accumulating a batch.

| Offered rate | Batch | Events delivered | p50 | p95 | p99 | Max |
|---:|---:|---:|---:|---:|---:|---:|
| 240/sec | 1 | 480 | 0.381 ms | 0.631 ms | 1.092 ms | 2.010 ms |
| 480/sec | 1 | 960 | 0.333 ms | 0.608 ms | 0.903 ms | 1.203 ms |
| 960/sec | 1 | 1,920 | 0.245 ms | 0.449 ms | 0.760 ms | 1.858 ms |
| 480/sec | 4 | 960 | 0.416 ms | 0.519 ms | 0.610 ms | 1.025 ms |

Harness process CPU consumption was 0.12–0.50 CPU seconds per roughly two-second row. This includes the test client and TLS and is not an isolated desktop-server CPU measurement. These short runs demonstrate no event loss in the tested cases, not sustained maximum throughput or a network SLA.

### Desktop visual feedback and startup

- Native offscreen construction + first raster capture: **95.8–257.6 ms** over five windows, after imports, device startup mocked. Not physical cold-start time or compositor time.
- Desktop diagnostics/test-canvas flush runs every **33 ms (~30 Hz)**. That can add up to roughly one timer interval to the app's own visual preview; it is not in the operating-system injection path. The scratchpad should not be used as an end-to-end latency meter.
- Event notifications are coalesced; worker and preview queues are capped at 2,048. The canvas uses a backing pixmap and one painter per frame batch. Card elevation avoids expensive subtree shadows. Android trail samples are capped at 4,096, and Android consumes historical MotionEvent samples rather than silently dropping them. [Android MotionEvent batching reference](https://developer.android.com/reference/android/view/MotionEvent).
- Offscreen preview drawing plus raster capture at 960×480: 16-point batch p95 **2.67 ms**, 32-point **2.29 ms**, 128-point **4.55 ms**, maximum-size 2,048-point **50.07 ms** (20 runs each). See PERF-01; normal-rate rendering is substantially cheaper than full-buffer recovery.
- APKs: debug **6,352,727 bytes**, unsigned release **4,890,334 bytes**. Release shrinking is disabled. No large bitmap/rendering bottleneck was demonstrated; a physical-device profiler pass is still needed before optimizing allocation or redraw behavior speculatively.

## Security review: controls verified and residual risks

| Area | Result |
|---|---|
| Authentication / wire confidentiality | TLS required; exact certificate fingerprint pinning and certificate validity checks on Android; nonce-based HMAC proofs with role separation; constant-time proof comparisons; authentication precedes input dispatch. No bypass found in reviewed paths/tests. |
| Pairing / secrets | Random 32-byte pairing secret, credential redaction in endpoint representations, private desktop identity writes, Android app-private preferences, backup/transfer exclusions, password-style pairing entry. Copying credentials to clipboard is an explicit user action, not evidence of unauthenticated exposure. |
| Input integrity | Strict framing and payload/record validation, finite/ranged coordinates and pressure, single authenticated input owner, session generations, stale local queue reset and no offline replay. In-flight freshness remains LAT-02. |
| Resource bounds | Pre-TLS global admission, complete-frame deadlines, byte/event/packet budgets, bounded UI logs/queues. SEC-01 remains a fairness/availability gap. |
| Failure release | Linux pointer and tablet modes verified against real kernel state using newly created, exclusively grabbed virtual devices; reset, remap, stale-flag exit and paired TLS disconnect released held output. Fixtures sent no desktop input. |
| Logs / commands | GUI logs inserted as plain text, stripped of embedded line breaks, length and block count bounded. Reviewed command paths use structured subprocess arguments; no shell-injection finding demonstrated. |
| Android app surface | Settings not exported; launcher is intentionally exported. Cleartext disabled, backup disabled, limited declared networking/wake permissions. No unnecessary broad storage permission found. |
| Windows driver source | Buffered write-access IOCTL, exact report sizes, flag/coordinate/tilt validation, exclusive handle and cleanup releases. ACL permits interactive-user access intentionally. Windows driver runtime/signing, Driver Verifier and multi-session behavior were not tested on this Linux host. |
| Dependency advisories | Hash-locked Python scan: no known package findings. Maven/toolchain OSV scan: 64 coordinates, no findings. These results do not cover every embedded/native component or prove absence of unknown vulnerabilities; see SEC-02. |

Stress evidence: **10,080/10,080 events**, **81 authenticated sessions**, **120 incomplete TLS attempts**, handler count capped at **4**, peak measured application PING round trip **1.54 ms**, stop **0.14 ms**, file descriptors **8 before / 7 after**. No leak was observed in this short run. This does not replace a long soak, WAN threat test or external penetration test.

## Verification inventory

Evidence root: `audit/evidence/full-2026-10-31/`.

- Python: isolated environment **126 passed, 1 optional-environment skip, 19 subtests**; system Qt/GI-capable environment **127 passed, 19 subtests**, with two upstream deprecation warnings.
- Android: debug and release assembly, **41 unit tests**, zero failures/errors, lint **0 errors / 33 warnings**. Audit-only latency test was run through an external Gradle init script; ordinary unit tests were rerun afterward to restore the normal test source set/results.
- Lint warning groups: OldTargetApi 1, UnusedAttribute 4, GradleDependency 6, NewerVersionAvailable 1, ObsoleteSdkInt 1, Overdraw 2, UnusedResources 6, UselessParent 1, MonochromeLauncherIcon 1, UseKtx 1, RtlSymmetry 9. Warning count is not a count of exploitable defects.
- Desktop: **60 fresh native PNGs**, light/dark, 1200×900 at 11 pt, 760×700 at 11 pt, 960×800 at 16 pt; all workspaces, four editor categories, mapping bounds, matching and profile dialogs. Harness asserts no horizontal overflow in Connection/editor scroll regions.
- Qt accessibility probe resolves meaningful names for all four pressure/smoothing sliders. Role-token contrast checks: light body/panel 17.88:1, muted/panel 6.82:1, selected text 5.11:1; dark equivalents 16.44:1, 8.56:1, 6.00:1. This checks specified pairs, not every painted state or a full WCAG certification.
- Android native emulator matrix: **39 fresh PNGs and 41 completed runtime checks**, phone/tablet, light/dark, portrait/landscape, collapsed/restored controls, settings sections, large text at 1.3×, keyboard, invalid-save page reveal, valid synthetic pairing save, rotation state and right-side controls. See `screens-mobile/android-runtime-checks.json` for exact completion and count. Two additional edge screenshots reproduce USB-only validation and FULL-area overlay behavior. `apk-integrity.json` confirms the installed APK exactly matches this audit build by SHA-256.
- Linux real-kernel checks: `linux-isolated.json`; no physical input nodes used. Each new device was exclusively grabbed before input tests; no desktop input events were sent.

Reproduction fixtures are under `audit/`: `full_pipeline_audit.py`, `network_delay_probe.py`, `measure_native_preview.py`, `mobile_edge_probe.py`, `fixtures/latency.init.gradle`, `fixtures/latency/.../TransportLatencyAuditTest.kt`. Their extra source lives outside application source sets and is opt-in. Render/capture harnesses mock desktop device startup or restrict Android modifications to a disposable emulator and synthetic credentials.

## Coverage limits and release gates

A “full audit” covers all four requested areas; it cannot certify untested environments. This pass did **not** measure physical S Pen sensor-to-desktop-photon latency, real USB/ADB transport, crowded Wi-Fi, actual Android power-saving behavior, Windows HID runtime, real monitor mapping, 60/120 Hz presentation, battery/thermal throttling, screen readers, fold hinges, split screen, RTL operation, or 2× font scale. Do not combine loopback and fake-link percentiles into an end-to-end number: percentiles are not additive and the measurements omit major stages.

Before release:

1. Fix LAT-01 and LAT-02; verify a real Android sender against a delayed paired receiver while drawing continuously, including cancellation/reconnect and queued button release.
2. Define a product latency budget, then measure p50/p95/p99 and worst-case with a physical Samsung S Pen device over USB and Wi-Fi. Separate sensor dispatch, queueing, wire, OS injection, filtering and display. Use synchronized instrumentation or high-speed camera/photodiode for the final physical path.
3. Profile a release-signed build on target Samsung hardware: startup, long stroke, historical sample bursts, allocations/GC, frame timings, rotations/settings transitions, radio sleep and thermal/battery conditions. Disable smoothing for baseline comparison; repeat with advertised defaults.
4. Exercise Windows with a signed driver and Driver Verifier; verify disconnect/crash release, privileges, multi-user sessions and real application behavior. Repeat Linux checks without relying on the diagnostic preview as a latency reference.
5. Resolve USB onboarding and admission fairness; test live accessibility/theme changes and overlay interaction; update/verify native dependency patches and Android platform baseline.
6. Run TalkBack and desktop screen-reader/keyboard-only sessions, 2× text, RTL, multiwindow and target foldable/device configurations. Then repeat this audit and the native screenshot matrix.

## Prioritized design workflow

1. `$impeccable optimize`: responsiveness after heartbeat/profile-switch changes.
2. `$impeccable harden`: freshness/recovery messaging and review after transport, admission and dependency repairs.
3. `$impeccable onboard` / `$impeccable clarify`: USB pairing and smoothing tradeoff.
4. `$impeccable adapt` / `$impeccable typeset`: runtime font/theme behavior and safe drawing area.
5. `$impeccable polish`: final native consistency pass after functional repairs.

These workflows do not substitute for protocol/security engineering. They can be run individually, together, or in a chosen order. Re-run `$impeccable audit` after repairs to reassess the score.
