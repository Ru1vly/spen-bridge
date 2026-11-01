# Audit remediation

The scope is all findings A01–A34 in [AUDIT.md](AUDIT.md), including the
performance, architecture and platform-verification notes. The audit is retained
as baseline evidence. This ledger records implementation and verification as the
work progresses; a passing narrow test does not close a platform-wide finding.

**Work in progress:** desktop and Android now implement paired protocol-v2 TLS.
The source changes cover the findings below; portable verification has passed. Release verification still requires native targets. Native Windows, compositor, S Pen and broader accessibility gates are not
satisfied by portable unit tests. The full goal remains unverified.

| ID | Current implementation and remaining verification |
| --- | --- |
| A01 | Desktop and Android require TLS, exact certificate pin/validity and fresh role-separated HMAC proofs. Loopback default, explicit Wi-Fi opt-in, desktop Pair Tablet and validated private Android settings implemented. TLS rejection, cross-language golden-proof and real JVM loopback pin/proof/heartbeat tests pass. Native endpoint verification remains. |
| A02 | Linux reset releases held outputs, pressure, proximity and smoothing. Mock-device/session tests pass; failed input/release reports close the backend and stop the listener. Real kernel state and paired-TLS disconnect release pass in both modes under an exclusive grab. Compositor behavior remains a platform gate. |
| A03 | One authenticated owner; additional peers cannot inject or reset it. EOF releases even with an idle unauthenticated peer. TLS tests pass. |
| A04 | Raw accepted sockets, TLS handshakes and authenticated handlers are tracked and cancelled/joined before shutdown. Raw-handshake shutdown is covered by the portable supported-version suite; native stress remains. |
| A05 | Desired output sets combine tip/barrel sources, release old mappings and reset cancel/exit regardless of incoming flags. Unit tests and isolated real-kernel reset/remap/stale-flag checks pass. Native compositor/application behavior remains. |
| A06 | Explicit worker lifecycle and one owner loop for create/update/swap/close; duplicate start and stop-during-initialization tests pass. GUI exit joins cleanup and cancels startup timers. Platform stress remains. |
| A07 | Android bounded session buffer preserves all accepted transitions, rejects stale batches, resets whole sessions on overflow and drops offline input. Capture epochs also validate MotionEvent/history uptime before accepting samples. UI capture starts only after fresh-session pointer reset. Pure JVM queue/transport tests pass; S Pen soak remains. |
| A08 | Omitted-value sentinel permits explicit clearing of mapping bounds. Tests pass. |
| A09 | Backend capability contract and GUI choices implemented. Hover-to-contact no longer inserts a cancel that retriggers barrel actions; focus reset releases remaining proximity/barrel outputs after tip-up. Unsupported stored choices remain explicitly marked until corrected. Linux/Windows Undo and eraser logic and ABI/failure cleanup have mock tests. Native application behavior remains. |
| A10 | Centered aspect-correct target fit and live updates implemented; pure math tests pass. Shared pressure transfer function replaces duplicate math. GUI rendering inspected at small sizes; native mapping/compositor behavior remains. |
| A11 | Shared CLI/GUI effective-settings resolver includes click disable and selected-monitor mapping; CLI has owner-loop automatic profiles and explicit overrides. Resolver tests pass; CLI orchestration/failure tests pass, including selected-monitor mapping and replacement-device cleanup on failed swap. Native platform behavior remains. |
| A12 | Strict whole-batch validation in Python and Kotlin; finite/ranged fields, enums, record alignment and length bounds enforced. Kotlin splitting preserves all 2731 records and sequence wrap in tests. Shared golden packet/proof tests pass. |
| A13 | Desktop schema/recovery notice and Android typed-preference fallback, host/port/fingerprint/code validation implemented. Corrupt config is preserved, backup restored and a visible review notice shown. Editor ranges preserve all valid settings, including negative monitor origins. Android device settings interaction remains. |
| A14 | Atomic owner-only writes, fsync/replace, validated backup and preserved damaged input implemented. Failure/recovery tests pass. |
| A15 | System/manual profile changes mark dirty, automatic focus remains runtime state, save failure blocks exit, and tray Quit shares confirmation. Tests pass. |
| A16 | Reset joins shutdown, requires successful persistence, rebinds config owners and syncs global controls/header. Failure/success tests pass. |
| A17 | Android validates TLS, challenge, server proof and sequenced empty heartbeat replies before healthy session use. Absolute frame deadlines and blocked-writer watchdog implemented. Fake-link failure/cancellation tests pass; device network-failure soak remains. |
| A18 | Android immutable endpoint snapshots, generation-guarded callbacks, one socket owner, pre-DNS cancellation publication, bounded resolver, explicit raw-socket cancellation and joined worker/watchdog implemented. Endpoint-change/stop/blocking tests pass. Actual OS DNS/radio tests remain. |
| A19 | Sender starts/stops with visible activity lifecycle; focus loss cancels input. Wi-Fi lock is held only for foreground authenticated non-loopback sessions and released on stop/failure. Device power/lifecycle verification remains. |
| A20 | Signed xrandr offsets parsed; negative-X/Y test passes. Native mixed-display behavior remains. |
| A21 | Windows installer refuses first install without a root-device creator (DevCon), limits pnputil to an existing root node, and checks exactly one present node with OK status before success. Eight PowerShell logic cases pass using fake PnP/installer commands. Real Windows PnP/signing remains. |
| A22 | Permission setup preserves initiating account through sudo/pkexec, uses dedicated spen-uinput group and per-user ACL, never adds input membership, scopes udev trigger and verifies effective access. Rootless isolated-container checks pass with real account/group/ACL tools, including numeric pkexec UID lookup; only kernel commands are mocked. Real module/udev installation on a disposable host remains; no host permission changes performed during tests. |
| A23 | Android FULL geometry always uses the complete surface regardless of saved crop/offset values. Pure geometry tests cover FULL, custom and aspect-fit modes; device rendering remains. |
| A24 | Android tracks an active (input device, pointer ID), rejects finger by default, permits pen preemption of allowed finger, uses historical samples for the active index and cancels on focus/size/session changes. Cross-device ID reuse is tested. Pure ownership tests pass; palm/S Pen device tests remain. |
| A25 | Bounded worker queue/one pending GUI notification, bounded stroke-aware preview, one painter per batch, neutral/disconnect reset and eraser badge implemented/tested. Qt rendering inspected; sustained device/compositor stress remains. |
| A26 | Admission now occurs before TLS allocation: at most four tracked raw/session handlers, bounded backlog, handshake/frame deadlines and traffic budgets. Raw and authenticated cap/shutdown regression tests pass in the supported-version suite. Long native soak remains. |
| A27 | Keyboard-native collapsible headers, named/larger controls, keyboard monitor selection, narrower two-row header and viewport-fitting profile controls implemented. Android named 48dp controls, performClick and string resources added. Qt small-window renders inspected with one correction pass; 150% DPI render evidence captured. Form controls have explicit accessible names. Native KDE/Xwayland AT-SPI and Orca smoke checks pass after fixing unnamed profile rows and accessibility-toggle expansion. Orca speaks profile names and expanded/collapsed state. QTest keyboard regressions pass; TalkBack, device font scale and broader assistive-technology checks remain. |
| A28 | Shared desktop-entry escaping is used by both installers; elevation uses argument lists and shell quoting. Real Gio launch test passes with spaces, apostrophes, double quotes, dollar signs, backticks, percent and backslash in checkout path. Static entry identifies itself as a packaging template. |
| A29 | Panel distinguishes running endpoint from configured changes pending restart; copy and asynchronous ADB use actual running port. Tests pass. Installer no longer silently opens a hardcoded firewall port; documented explicit private-subnet rule uses selected port/executable and verifies filters. Native firewall gate remains. |
| A30 | Bounded plain-text logs and external labels implemented; focused-window titles are no longer logged on switching. Unit tests and inspected Qt renders pass. |
| A31 | Portable mocked-input regressions, 29 Android JVM tests, Python hash locks, Android dependency locks/verification metadata, Gradle distribution checksum and commit-pinned CI actions added. Linux Python 3.10–3.14, Windows driver/application and Android workflows configured. Runtime scans pass (cryptography updated to 50.0.0 after scan). The 117-case baseline passes locally on Python 3.10–3.14 with pinned Qt 6.11.2; two subsequent regressions pass on 3.14 (119 total). GUI fixtures ignore real user auto-start/QSettings, and the mode-swap test uses an isolated listener. Gradle 8.14.6 strict clean build, all 29 JVM tests and updated capture checks pass; real Windows validation remains. |
| A32 | Added MIT LICENSE consistent with existing declaration, aligned Windows experimental status, removed zero-latency claims and documented paired TLS, default USB endpoint, Wi-Fi opt-in, actual-port forwarding, firewall and dedicated uinput permissions. Setup, pairing, protocol and development documentation has been cross-checked against the implementation; native instructions require platform verification. |
| A33 | Installer reuses existing valid uv environment and only creates one when missing. Twice-run disposable command-stub integration passes. Noninteractive /dev/tty opening is checked rather than relying on readable device metadata. |
| A34 | Kotlin 2.4.21, Gradle 8.14.6 and explicit compatible R8 9.1.57 selected. The Gradle upgrade also fixes newly checked upstream daemon/repository advisories affecting 8.7. Lint 9.4.1 override analyzes Kotlin 2.4 metadata without compatibility errors. Strict clean debug/release builds, 29 JVM tests including real pinned loopback TLS and capture epochs, and lint pass (99 tasks). The refreshed OSV scan reports no findings across 64 runtime/build coordinates, including Gradle. |

Validation must include desired-behavior regression tests replacing the original
defect assertions, Python portable and mocked-device suites, Android unit tests,
debug/release builds and lint, installer checks and rendered GUI inspection.

## Current verification

`QT_QPA_PLATFORM=offscreen /tmp/spen-audit-venv/bin/python -m pytest -q`:
**119 passed, 17 subtests passed** on Python 3.14. The earlier 117-case baseline yielded **116 passed, 1 optional Gio skip** on each of 3.10–3.13, including all seven formerly hardware-gated
Linux logic tests. Pytest injects no OS input. The synthetic integration test sends
all 153 generated events to a memory backend over paired TLS.

`ruff check --isolated --select E9,F server tests audit/reproduce.py`, Python
compileall and `git diff --check` pass. `python audit/reproduce.py` now runs the
desired-behavior suite; `baseline_reproduce.py` preserves the historical defects.
Evidence is retained under `audit/evidence/remediation-*`.
Android strict clean verification passes all 29 JVM tests, debug and unsigned release packaging, and lint on Gradle 8.14.6. Runtime Python advisory scans on 3.10 and 3.14 and the 64-coordinate Android/build scan report no known advisories. All six PowerShell scripts parse with PowerShell 7.6.9; eight mocked driver-installer cases pass. No real Windows driver was installed.
Qt render evidence covers 760×540, 960×640 and larger-font control geometry.
At the original verification, no Android device or Windows test machine was available. On 2026-10-30 a Samsung SM-S908B was connected and authorized; the USB follow-up below records native connection checks. Windows and the remaining device/compositor checks remain unverified.

`audit/verify_linux_isolated.py` passes against real kernel state in both modes:
held outputs, reset/pressure/tilt, remap, stale-flag exit and paired-TLS EOF release.
The temporary device is exclusively grabbed before any events and destroyed
before releasing the grab. No events reach the desktop. Evidence is in
`remediation-linux-kernel.json`; compositor/drawing-app behavior is not proved.

The recorded verification used matching official PySide6/Shiboken6 6.11.2 wheels, cryptography 50.0.0, JDK 17 and the Android SDK. These toolchains were provisioned under `/tmp`; those temporary installations are no longer present after the session resumed on 2026-10-30. Retained reports describe the completed runs, and rerunning requires provisioning the tools again. The
Impeccable context/harden/craft-floor guidance has been read; this is functional
hardening of existing Qt/Android interfaces. Changed Qt screens were inspected together and received one correction pass.
The subsequent range/accessibility-name changes do not alter the default layout.

A short TLS stress run applies all 10,080 events across 81 authenticated sessions
while admitting/rejecting 120 incomplete TLS attempts. Peak handlers stay at four,
all owners reset, no descriptors leak, and shutdown completes below a millisecond
on this run. This is a short stress check, not a long hardware soak.

Native desktop accessibility evidence is in `remediation-native-accessibility.json`,
`remediation-native-accessibility-tree.txt` and `remediation-orca-speech.txt`.
The smoke check used in-memory configuration and never started an input backend.
It covers AT-SPI activation and Orca speech output; native OS-key delivery,
Braille, TalkBack and a complete screen-reader workflow remain unproven.

Real S Pen, compositor input, Windows signing/installation/PnP/power/Ink and broader accessibility
verification remain unproven. The full goal must not be marked complete using
these portable tests alone.

## USB reconnect follow-up — 2026-10-30

The connected Samsung SM-S908B exposed a setup gap: ADB reverse was applied
only once, so a cable reconnect lost the forward. Enabling USB now starts a
single-flight monitor which checks every two seconds, preserves existing
forwards and recreates missing ones. It targets USB explicitly with `adb -d`,
uses the actual listener port, avoids repeated log messages and stops/joins on
quit. Auto-forward on launch starts this monitor after future app launches.
The local user's auto-forward preference was enabled for the requested setup.

Desktop labels use the authenticated peer and USB-forward state; the Android
app labels its selected USB or network transport and gives USB-specific retry
errors. That first follow-up still selected a single endpoint; the automatic dual-transport correction below supersedes that behavior.

The updated apps were installed/opened. Removing an active reverse mapping
proved automatic restoration in 0.836 seconds; restarting the phone app then
established a fresh paired connection. Both apps displayed USB. The additional
explicit `adb reconnect` command left the host ADB transport absent despite USB
enumeration; restarting the audit-owned ADB daemon restored device visibility.
The user subsequently confirmed that physical unplug/replug reconnects both updated apps automatically.
See `evidence/remediation-usb-native.json`. These checks do not prove stylus
pressure, hover or power behavior.

Python validation: 120 passed, 1 optional Gio skip, 17 subtests passed (121 tests).
Android: all 29 JVM tests, debug packaging and lint pass with strict dependency
verification. Reports: `remediation-usb-python.txt` and
`remediation-usb-android-build.txt` under `evidence/`. Build tools were restored
under `/tmp` for this follow-up; desktop dependencies are now in `server/.venv`.
ADB is installed persistently under the user's `.local/share/spen-bridge` and
linked from `.local/bin`.

## Deferred Windows verification

On 2026-10-30 the user explicitly deferred the Windows portion for now and
authorized committing the update. Existing Windows source/installer fixes and
portable checks are included; native build, signing, installation, PnP, power,
Driver Verifier and Ink checks remain unverified. This deferral is not a claim
that those checks passed or that the full audit is complete.

## Automatic dual-transport correction — 2026-10-30

The user clarified the required retry policy: USB first, Wi-Fi immediately if
USB fails, then a five-second cooldown only after both fail. The sender now
implements that cycle in its single owner worker. Both attempts use the same
paired desktop identity and port. The Wi-Fi address is retained in Settings;
USB uses loopback automatically and does not overwrite it. Session generations,
queue clearing and fresh capture acknowledgement also apply across fallback.
Status and the Wi-Fi lock use the actual attempted/authenticated route.

The desktop's paired LAN listener was enabled alongside USB on the user's
machine. LAN discovery now selects physical interfaces before Internet routes,
avoiding the VPN's 172.20.0.1 address. The saved phone Wi-Fi target is the actual
192.168.1.15 LAN host. Existing firewall permissions already allowed the port;
no firewall change was made.

Native testing confirmed USB authentication, followed by user unplugging the
cable and reporting automatic Wi-Fi connection. The desktop independently
confirmed an authenticated peer at 192.168.1.3 over its LAN listener. Background
cleanup also exposed an interrupted watchdog shutdown; cleanup was moved out
of inlined return paths and interruption is contained. Two phone background/
resume cycles then kept the process alive and returned to USB when cabled.
See `evidence/remediation-dual-transport-native.json`.

Validation: 35 Android JVM tests pass, including USB-first order, immediate
Wi-Fi fallback, the actual default five-second retry delay, clean route changes,
cooldown interruption, and repeated interrupted shutdown. Strict debug build
and lint pass. Python: 121 passed, one optional Gio skip, 17 subtests passed;
this includes physical-LAN-versus-VPN address selection. Evidence is retained in
`evidence/remediation-dual-transport-*`. Windows verification remains deferred.

## Prefer USB after cable insertion — 2026-10-30

The user requested handover from an already connected Wi-Fi session when USB
becomes available and the pen is idle. Wi-Fi sessions now check the paired USB
path every two seconds with a bounded, read-only TLS/pairing probe. The optional
handshake sequence 1 authenticates readiness without claiming input, resetting
the current owner, accepting events or issuing connection callbacks.

Once readiness is verified, transfer waits for 750 ms without pen events, an
empty input queue and no held tip or barrel button. Accepted input and the idle
handover barrier share one lock. Input remains on Wi-Fi while readiness is
checked; a new contact during a probe defers the switch. Wi-Fi is closed before
the new USB owner connects, and USB capture requires a fresh UI acknowledgement.
Absent/failed probes leave healthy Wi-Fi input untouched. Probe sockets are
cancelled on stop, reset or settings changes, and the bounded executor is joined.

Both updated apps were installed/restarted. The running desktop passed an
actual pinned-TLS read-only probe, and the phone remained authenticated over
Wi-Fi at 192.168.1.3. The user reported a broken cable, so physical Wi-Fi-to-USB
handover could not be confirmed. This verification is pending a working cable.

Validation: 41 Android JVM tests pass, including a real pinned TLS readiness
exchange and active-stroke/idle-handover/cancellation regressions. Strict debug
build and lint pass. Python: 123 passed, one optional Gio skip, 17 subtests passed;
read-only probes are tested both with and without an existing input owner.
Evidence: `evidence/remediation-usb-handover-*`. Windows remains deferred.
