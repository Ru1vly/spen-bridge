# S Pen Bridge application audit

Audited 2026-10-26, baseline commit `042c806` (`minor fix`). Scope: the Android
client, Python server and GUI, Linux uinput backend, Windows transport and
KMDF/VHF source, configuration, installers, protocol, tests, CI, documentation,
accessibility, performance and distribution. Application source was not changed during the baseline audit. Remediation is tracked separately in [REMEDIATION.md](REMEDIATION.md).

**Assessment: address input ownership, cleanup and authentication before broad
Wi-Fi use.** Passing tests currently leave significant lifecycle and feature gaps.
This is an audit with actionable findings, not a certification of the hardware or
of a signed Windows driver.

## Verification and evidence

| Check | Result and boundary |
| --- | --- |
| Original unittest discovery | 56 run: 49 passed, 7 skipped because the original Python environment lacked evdev. |
| Portable pytest run | 49 passed. 60% aggregate statement coverage; excludes seven tests requiring real uinput. See [tests.txt](evidence/tests.txt). |
| Linux test file with `evdev.UInput` replaced by a mock | All seven passed. This exercises Python logic, not kernel registration or compositor behavior. |
| Additional evidence harness | 22 observations reproduced with local TCP sockets and mock input devices. See [baseline_reproduce.py](baseline_reproduce.py) and [reproductions.json](evidence/reproductions.json). Assertions describe existing defects; they are not regression acceptance tests. |
| Syntax | Python compileall, shell `bash -n`, Android XML, driver project XML and packages XML passed. |
| Focused Python lint | Ruff `--isolated --select E9,F63,F7,F82 server tests` passed. `--select F` reports 17 unused imports/locals. No repository lint configuration exists. |
| Python dependencies | pip-audit found no known advisories for the freshly resolved requirement set, and for the audited runtime's available evdev/PySide6/shiboken6 metadata. See [python-dependencies.json](evidence/python-dependencies.json) and [python-runtime-advisories.json](evidence/python-runtime-advisories.json). Separate Addons/Essentials distribution metadata was unavailable for the system Qt installation. This does not audit embedded Qt libraries or WDK packages, and does not pin future installations. Android coordinates are checked separately below. |
| Kotlin protocol | Compiled standalone using the Gradle-bundled Kotlin 1.9.22 compiler and JDK 17. Normal packet bytes exactly matched Python. Three future-type-resolution warnings occur for `Short` bit constants. A 2,731-record payload wraps its advertised length to eight bytes. |
| Android full build/lint | JDK 17 + SDK 34: `:app:assembleDebug :app:assembleRelease :app:lintDebug` passed (94 tasks). Debug APK signature verified; release APK is unsigned. Lint: zero errors, 27 warnings. See [build output](evidence/android-build.txt), [lint XML](evidence/android-lint.xml) and [APK hashes](evidence/android-apks.txt). No APK was installed or device/emulator test run. |
| Android dependency advisories | OSV query of 61 resolved debug-runtime/plugin Maven coordinates found one package/version advisory match: Kotlin Gradle plugin 1.9.24, GHSA-r937-wjx7-w2jp / CVE-2026-53914. Its patched source concerns KAPT; this app does not enable KAPT, so exploitability is not established. See A34 and [query evidence](evidence/android-advisories.json). This is not a complete audit of build-tool transitive dependencies or embedded native code. |
| Desktop visual inspection | Both tabs rendered at 1200×760 using PySide6 6.11.2/offscreen: [profiles](evidence/profiles.png), [system](evidence/system.png). These captures follow the reset reproduction, so the visible stale checkbox/header state is intentional evidence. Basic content renders; this does not establish platform integration, screen-reader behavior or mixed-DPI behavior. |
| Windows driver | Reviewed IOCTL sizes, range checks, exclusive open, ACL, report descriptor and cleanup paths. Portable Windows tests use mocked APIs. Actual MSBuild, signing, installation, Driver Verifier, PnP/power transitions and Windows Ink behavior remain unverified here. |

Tests ran on Linux/Python 3.14.8. Audit-only packages and JDK tools were installed
under `/tmp`; no desktop input was injected, drivers installed, firewall rules
changed, or administrator setup scripts executed.

## High priority findings

### A01 — Any reachable TCP client can inject desktop input

**High; reproduced.** `server/config.py:116`, `server/server.py:32` and
`server/server.py:131`. The default bind is `0.0.0.0`, with automatic startup.
Events are dispatched before any handshake; a handshake merely receives `OK`.
There is no authentication, pairing, transport encryption or server identity
check. `install.ps1` also opens TCP 40118 on Private/Domain profiles without a
remote-address restriction. The memory-only TCP reproduction sent DOWN without a
handshake and it reached the backend. Any host able to reach this listener can
move/click the desktop through the bridge; this does not imply arbitrary
keyboard injection or code execution.

Use loopback by default for USB and explicit Wi-Fi opt-in. Add authenticated
pairing, peer verification and authenticated transport. Enforce authentication
before dispatch and test rejected/expired credentials and replayed sessions.

### A02 — Linux disconnect does not release pen or buttons

**High; reproduced.** `server/server.py:182` calls an optional `reset()` on final
disconnect. `server/backends/linux_uinput.py` has no such method, unlike Windows.
A lost connection after DOWN or a barrel press leaves the persistent device's
state asserted until another event or device teardown. Implement an idempotent
Linux reset for pressure, touch, all buttons, proximity and smoothing. Test EOF,
read failure, cancellation and malformed traffic mid-stroke.

### A03 — Multiple clients share a device and suppress disconnect release

**High; reproduced.** `server/server.py:60` accepts concurrent clients and resets
only when `active_clients` is empty. Two clients interleave events on one tablet.
Even the Windows reset is skipped when the drawing client leaves but an idle
second connection remains. Reproduction confirms reset count stays zero. Give a
single authenticated session ownership; reject or explicitly arbitrate others,
and release the owner's state when it departs.

### A04 — Stopping the server leaves accepted connections alive

**High; reproduced.** `server/server.py:270` closes only the listening server.
There is no registry of accepted writers/tasks to close. On this Python 3.14 run,
`stop()` remained pending with an idle connected client; the client still had an
open socket. With runtime versions whose server wait completes earlier, the
accepted read task can still survive listener shutdown. In the GUI,
`server/gui/server_worker.py:102` waits for this stop before device close and task
cancellation, so the cleanup order cannot resolve that wait itself. Explicitly
close accepted writers, cancel/await handlers and reset the tablet, with a
bounded shutdown. Test idle and mid-stroke clients across supported Python versions.

### A05 — Linux remapping can leave a previous button held

**High; reproduced.** `server/backends/linux_uinput.py:209` derives release codes
from the *current* mapping; `server/backends/base.py:107` replaces mappings without
releasing previous ones. Press right-click, change mapping to middle-click,
release: RIGHT receives no release. Mapping both barrel buttons to RIGHT also
releases RIGHT when only one is released, despite the other still being held.
CANCEL processes the incoming barrel flags and can leave a barrel button held.
Track logical source state separately, combine sources per output button and
release old outputs before remapping. Reset all outputs on cancel/proximity loss.

### A06 — Backend lifecycle crosses threads without Linux synchronization

**High; source-confirmed race, scheduling outcome not stress-tested.**
`server/gui/server_worker.py:122` updates settings and `:126` creates/swaps/closes
devices from the GUI thread while `_run_loop` dispatches events on another
thread. Linux event handling can race device close/replacement and mix settings
within a report. Windows uses a backend RLock for ordinary settings/event I/O,
but the worker lifecycle itself is still shared. `start_server()` guards only
`_is_running`, which becomes true after initialization: calling twice before
then creates two threads (reproduced). Stop during initialization is ignored.
Marshal all device operations onto the owner loop, and add explicit starting,
running, stopping and stopped states with joined termination.

### A07 — Android replays offline input and can drop release transitions

**High; source-confirmed.** `PenEventSender.kt:44`, `:114`, `:137`. The queue
accepts events while disconnected, is never cleared on endpoint change or
reconnect, and drops arbitrary oldest batches when full. Old strokes can execute
seconds later or on a newly selected PC. A dropped UP/CANCEL/button transition
can alter device state. At 240 callbacks/sec, 2,000 batches represent about 8.3
seconds of input, before accounting for historical samples. Use session-bound
queues, discard offline drawing, send neutral state on reconnect, and coalesce
only replaceable samples while preserving state transitions.

## Functional and reliability findings

| ID / severity / evidence | Finding, impact and correction |
| --- | --- |
| A08 / Medium / reproduced | **Full-desktop mapping cannot clear prior bounds.** `server/backends/base.py:93` treats `None` as “do not update”, but the GUI passes `(None, None)` for full desktop. Switching from a half-width region still maps x=1 to 32767/65535. Use a separate omitted-value sentinel and allow explicit clearing. |
| A09 / Medium / source | **GUI exposes unsupported button actions.** `server/gui/profile_sections/buttons_section.py:38` offers eraser, undo, stylus/stylus2 and disabled. Linux pointer mode implements only right/middle/left; Linux tablet mode ignores mappings entirely and emits fixed stylus keys, including when “Disabled” is selected. Windows handles right/left/middle and ignores eraser/undo/stylus actions. Implement each advertised action or remove/disable unsupported options per backend/mode. README advertises left-click but the GUI does not offer it. |
| A10 / Medium / reproduced | **Aspect lock has no effect.** `base.py:65` stores `aspect_ratio_lock` and `tablet_aspect_ratio`; neither affects coordinate mapping. Runtime settings updates do not apply them either. Implement and test aspect-correct mapping using the actual target area, and propagate global changes, or remove the control. |
| A11 / Medium / reproduced | **CLI ignores saved click disable and monitor mapping.** `server/main.py:100` handles custom bounds but never resolves selected-monitor bounds. Its backend construction omits `click_on_touch`, so an osu! profile saved with click disabled still defaults to clicks in CLI. Reuse the GUI's configuration-to-backend resolver and test identical effective settings. CLI also never starts the advertised automatic profile watcher; document or implement parity. |
| A12 / Medium / reproduced | **Incoming events are insufficiently validated.** `protocol.py:124` accepts invalid actions/tools/button bits and NaN/Infinity, and silently truncates partial records. Linux dispatches invalid actions and finger records; Windows rejects invalid enum/nonfinite values and all fingers. Nonfinite values can also reach GUI conversions such as `int(ev.pressure * 100)`. Validate whole records and finite numeric ranges at the network boundary, with a documented finger policy shared by both backends. Kotlin `Protocol.packEvents()` also allows more than 2,730 records: a 65,544-byte payload advertises only eight bytes after `toShort()`, desynchronizing the stream. Split oversized batches or reject them; see `ProtocolProbe.java`. |
| A13 / Medium / reproduced + source | **Configuration values are not validated.** `server/config.py:48`, `:331` accept invalid ports, zero dimensions, arbitrary field types, mismatched profile dictionary keys/names and invalid enum values. Zero desktop dimensions divide by zero in mapping. Some invalid JSON shapes fall back to defaults, but valid JSON with wrong field types survives load and fails later in widgets/backend code. Validate schema, types, finite ranges and profile identity; recover visibly with a backup. Validate Android host/port in `SettingsActivity.kt:155` as well. |
| A14 / Medium / source | **Saving settings can destroy the previous file.** `server/config.py:406` writes directly with mode `w`. A process/disk failure after truncation leaves incomplete JSON and the next startup falls back to defaults. Write a temporary file in the same directory, flush and atomically replace; retain a last-good backup and surface errors. |
| A15 / Medium / reproduced | **System changes bypass unsaved-change tracking.** `server/gui/startup_panel.py:49` changes config directly; MainWindow never wires these changes to `_mark_dirty`. Port, startup, tray and name edits may be lost on quit without a save prompt. Manual active-profile changes also do not mark dirty. Add a common config-change signal; make tray Quit use the same save/discard/cancel flow as window close (`tray.py:29`). A failed save in the close flow must also abort quitting rather than proceeding after `save_all_settings()` returns. |
| A16 / Medium / reproduced | **Reset leaves controls disagreeing with config.** `main_window.py:347` replaces configuration but does not sync the global aspect widgets, auto-switch checkbox or header mode. Harness shows aspect lock checked while config is false, and auto-switch unchecked while config is true. Reset also ignores `save_config` failure and clears dirty state. Rebind/sync every config owner, apply listener changes deliberately, and clear dirty only after successful persistence. |
| A17 / Medium / source | **Android “Connected” does not prove a working bridge.** `PenEventSender.kt:147` sends a handshake but never reads an acknowledgment. It has no reader/heartbeat/liveness timeout; idle remote closure can leave green status until another write fails. Verify a versioned handshake, read responses and use bounded heartbeat deadlines. |
| A18 / Medium / source | **Android socket ownership has races and failure leaks.** `PenEventSender.kt:141` creates a local Socket and publishes it only after connect; failed connect is not explicitly closed by `disconnectSocket()`. Stop/endpoint change during connect cannot close it and may still emit a late Connected callback. Shared host/port/socket/stream fields lack synchronization; optional writes can silently do nothing after stream is nulled. Use one owner coroutine/thread, local `use`/finally cleanup, an endpoint generation token and joined cancellation. |
| A19 / Medium / source | **Android connection and radio lock outlive foreground use.** `MainActivity.kt:281` stops only in `onDestroy`; going Home or opening settings does not stop the sender or release its Wi-Fi lock. Screen-on applies while visible, but the sender keeps retrying while the Activity remains alive. Tie capture/connection to a deliberate foreground lifecycle, send cancel when leaving the surface, and test settings, background, rotation, screen lock and process recreation. This is a battery/lifecycle concern, not a claim of persistent background-service support. |
| A20 / Medium / reproduced | **xrandr omits monitors left/above the origin.** `server/monitors.py:33` requires positive `+x+y` offsets. A `1920x1080-1920+0` output is omitted, corrupting headless X11 monitor selection and desktop dimensions. Parse signed offsets and test negative X/Y, stacked, scaled and disconnected layouts. Qt/Windows paths already normalize negative origins. |
| A21 / Medium / source + official API contract | **Windows fallback can stage the driver without creating the root device.** `windows/install-driver.ps1:58` calls only `pnputil /add-driver ... /install` if DevCon is absent, even when no root device exists. Staging can succeed while the bridge remains unusable. The guide says this creates the root device. Require DevCon/devgen or create the devnode explicitly, then verify a present healthy root node/interface. Microsoft distinguishes [root-device creation](https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/devcon-install) from [installing onto matching existing devices](https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/pnputil-command-syntax). |
| A22 / Medium / source | **Permission setup can target the wrong user and overgrant access.** `startup_panel.py:139` invokes the setup script through pkexec, while `server/setup_uinput.sh:39` trusts `$USER`; an elevated environment can make this root rather than the initiating user. It also permanently adds the user to the broad `input` group rather than granting only the needed uinput access. The `99-...` uaccess rule needs validation against the host's seat ACL rule ordering. Pass/validate the initiating identity explicitly and prefer least-privilege uinput-specific access; verify actual write access before reporting success. |
| A23 / Medium / source | **Android Full Surface can remain cropped.** `PenSurfaceView.kt:147` applies persisted width/height percentages even to FULL mode, while `SettingsActivity.kt:123` hides these sliders in FULL mode. A previously reduced area remains active with its controls hidden. FULL must ignore custom percentages/offsets or keep those controls visible and explain the behavior. |
| A24 / Medium / source | **Multi-touch handling always reads pointer index zero.** `PenSurfaceView.kt:210` and `:313` ignore actionIndex, pointer IDs and POINTER_DOWN/UP. With finger rejection disabled, lifting pointer zero while another remains can continue a stroke at a different finger; with a finger at index zero, stylus input elsewhere is ignored. Windows discards fingers entirely even though Android offers disabling rejection. Track one active stylus pointer explicitly, cancel on loss, and specify cross-platform finger support. |

## Usability, diagnostics and distribution findings

| ID / severity / evidence | Finding and correction |
| --- | --- |
| A25 / Medium / source | **Diagnostics can misrepresent input.** `main_window.py:426` keeps only the latest event and replays it every 33ms to scratchpad; quick UP/DOWN boundaries can disappear, causing missing taps or joined strokes. Disconnect leaves the latest event and readings stale. `diagnostics_panel.py:54` never updates the eraser badge, while Windows cancel/exit returns without invoking its event callback. Use a bounded stroke-aware preview queue and explicit reset/eraser state; sample numeric readouts separately. |
| A26 / Medium / source | **Network admission and resource use are unrestricted.** `server/server.py:60` has no connection cap, handshake/read deadline or rate budget. An idle peer retains resources indefinitely; many peers multiply them. A single frame buffer is bounded by the uint16 payload size plus read chunk, so this is not an unlimited single-frame buffer finding. Add admission limits and explicit inactivity policy compatible with legitimate hovering. |
| A27 / Medium / source + rendering | **Keyboard and accessible names are incomplete.** `server/gui/widgets/collapsible_box.py:12` uses a mouse-only QWidget header with no keyboard activation; chip remove buttons are 16×16 with only “×”; monitor selection is mouse-only. Android collapse/expand use triangle glyphs, have no descriptive contentDescription and include a 38dp expand target. Use accessible buttons/actions, descriptive names, focus/keyboard support and suitable touch targets; test with TalkBack and a desktop screen reader. Android lint also flags missing `performClick()` on PenSurfaceView and 13 hardcoded-text/SetTextI18n warnings; use resources and accessible activation semantics. The desktop minimum 1100×720 also needs small-screen/high-DPI validation. |
| A28 / Low / source | **Install paths with spaces or quotes break launchers.** `install.sh:75` and `startup_panel.py:181` write unquoted Exec paths. The terminal elevation fallback embeds `script_path` inside single-quoted shell source, so an apostrophe breaks quoting and specially crafted paths can change the command. Use desktop-entry escaping and positional shell arguments instead of interpolating source. Static `spen-bridge.desktop` also relies on `start.sh` being on PATH. |
| A29 / Low / source | **Port changes do not update the running listener/firewall.** Startup panel updates config and the displayed connection port immediately, but an already running server retains its original port. Windows firewall setup remains fixed to 40118. Show pending-restart status or restart the listener transactionally, and handle configured-port firewall instructions. The installer uses `SilentlyContinue` for New-NetFirewallRule, then prints success even when creation fails. Verify postconditions before reporting success. |
| A30 / Low / source | **Logs grow without a bound and can interpret markup.** `server/gui/log_panel.py:31` appends to QTextEdit forever, including focused-window/profile text; QLabel and QTextEdit can interpret rich text. Long-running sessions with frequent profile switches grow memory, and crafted titles can mislead the display. Cap document blocks, render external strings as plain text/escaped HTML and avoid unnecessary window-title logging. No script execution is established by this finding. |
| A31 / Medium / repository evidence | **Build/test and supply-chain coverage is incomplete.** No Android workflow, Android tests, dependency lock/hashes or Gradle distribution checksum. Linux hardware tests skip in ordinary CI and several pure-math assertions are hidden behind that hardware gate. Portable Windows tests do not execute the kernel or PowerShell installer. CI actions use mutable version tags and Python dependencies use unbounded lower bounds. Add Android assemble/lint/tests; mockable Linux logic tests; supported-Python/Qt dependency constraints; checksummed toolchains and pinned actions; real Windows driver validation gates. A fresh successful dependency scan cannot guarantee future unconstrained resolutions. |
| A32 / Low / repository evidence | **License and support claims need reconciliation.** README claims MIT but the tracked tree has no LICENSE file. Its support table says Windows “Supported” while `docs/WINDOWS.md` explicitly calls it experimental and pending hardware validation. The Windows guide refers to “USB mode” but Android has only endpoint fields, with a hardcoded first-use `192.168.1.7`; users must manually enter 127.0.0.1 for adb reverse. Add the intended license text, make experimental status consistent and provide explicit USB endpoint instructions. This records documentation/distribution gaps, not a legal determination. |
| A33 / Medium / reproduced tool behavior + source | **Linux installer cannot update an existing uv environment.** `install.sh:57` runs `uv venv server/.venv` unconditionally after updating the checkout. With the installed uv, a second creation at an existing environment exits 2 (“A virtual environment already exists”), so `set -e` aborts the claimed in-place update before dependency installation. Reproduced with a disposable `/tmp` environment. Reuse a valid environment and create only when absent; avoid clearing it merely to update dependencies. |
| A34 / Low / conditional advisory match, not exploited | **Pinned Kotlin build plugin has an unsafe-deserialization advisory.** `android/build.gradle.kts:3` pins `org.jetbrains.kotlin.android` 1.9.24, resolving the Kotlin Gradle plugin coordinate flagged by [GHSA-r937-wjx7-w2jp / CVE-2026-53914](https://osv.dev/vulnerability/GHSA-r937-wjx7-w2jp). The [JetBrains patch](https://github.com/JetBrains/kotlin/commit/bf51df665b458fda7c3eaf436c4d88dc119d7ec6) specifically restricts deserialization of KAPT incremental-cache classes. No KAPT plugin or annotation-processing configuration is enabled in this project; reachability in its current build is not established. The advisory concerns build-cache metadata and code execution in the build environment; it is not evidence of an APK runtime vulnerability or of this checkout being compromised. OSV lists the first fixed package version as 2.4.20-Beta1. Plan a compatible patched Kotlin/AGP/Gradle upgrade, validate stable release availability and rebuild/test rather than blindly adopting a beta. Keep build caches isolated from untrusted writers while remediation is planned. See [full advisory](evidence/kotlin-plugin-advisory.json). |

## Performance and architecture observations

Useful existing measures include TCP_NODELAY, Linux QUICKACK where available,
historical MotionEvent batching, offset-based packet parsing, off-thread network
serialization, and throttled GUI painting. Windows has an explicit report contract,
range validation, exclusive access and process-handle cleanup. The source uses
VHF-owned buffering and synchronous passive-level deletion, consistent with the
[submission](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/vhf/nf-vhf-vhfreadreportsubmit)
and [cleanup](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/vhf/nf-vhf-vhfdelete) contracts. Tests cover pressure
math, portable dispatch, report bytes and 64-bit handle declarations.

The server deliberately coalesces cross-packet MOVE samples without comparing
pressure/tilt/coordinates (`server/server.py:246`). This trades sample fidelity for
backlog freshness: it can remove pressure extrema even though action/button/tool
transitions survive. The wire spec's “zero dropped curves” and README's “zero
latency” exceed what the implementation or these tests establish. Choose an
explicit fidelity/latency policy and benchmark it. Android lint also reports two potential root/theme overdraw warnings. These are optimization candidates, not measured performance regressions. No end-to-end latency,
240Hz/480Hz hardware sampling, sustained battery, CPU, thermal, Wi-Fi-loss or
mixed-DPI performance claims were measured here.

Privacy review: the inspected application code sends pen events to the configured desktop endpoint and stores settings locally; no analytics/account/payment subsystem was identified. Focused window identifiers/titles can enter GUI logs and the explicit Copy action, so consider whether titles should be retained. Android allows settings backup; any future pairing credentials need an explicit backup/storage policy.

Additional maintainability concerns: settings resolution is duplicated between
CLI, worker start, live apply and mode swap; pressure curves are duplicated between
backend and widget; config and backend state are mutable across threads; worker
and tablet exceptions are often logged or swallowed without an actionable GUI
error. Centralize validated effective settings and session ownership before adding
more transport/device modes.

## Recommended order and acceptance evidence

1. **Input security and release correctness (A01–A07, A12, A26).** Prove a rejected
   client cannot inject events; only one owner exists; EOF, cancel, stop, timeout,
   remap and endpoint changes release every output. Test on actual Linux and
   Windows devices as well as mock report sinks.
2. **Configuration and feature fidelity (A08–A16, A20, A23–A25).** Exercise every
   GUI action on each supported backend; compare GUI/CLI effective settings;
   verify full-desktop mapping after restricted mapping and restart persistence.
3. **Android lifecycle and installation (A17–A19, A21–A22, A28–A29).** Test
   background/resume, endpoint changes while connecting, dead peer detection,
   clean installs without DevCon, ordinary-user access and paths with spaces.
4. **Accessibility, release checks and evidence (A27, A30–A34).** Add keyboard/
   screen-reader validation, bounded plain-text logs, reproducible dependency and
   Android builds, consistent docs and the intended license artifact.

## Remaining platform verification

These require their actual platform/hardware and are explicitly **unverified**:

- Samsung S Pen historical timing, tilt, pressure, hover, barrel-only changes,
  palm contact, interrupted strokes, rotation and Android process lifecycle.
- Actual uinput device classification and button/pressure behavior in X11,
  GNOME/KDE/Sway/Hyprland, drawing apps and compositor-specific monitor mapping.
- Windows Debug/Release MSBuild and INF verification, signed-package first
  install/update/uninstall, standard-user ACL and exclusive-open behavior,
  Driver Verifier, removal while active, sleep/resume and Windows Ink/mixed DPI.
- End-to-end latency/loss, long-session stability, power use and accessibility on
  real devices. No measurements should be inferred from the mock tests.

Run current desired-behavior regression checks with `python audit/reproduce.py`
after installing app dependencies. The original `baseline_reproduce.py` is
historical defect evidence and is expected to fail as fixes land. It opened only
loopback ephemeral TCP ports and mocked Linux input device creation, optionally
saving GUI screenshots. Current remediation status and platform limits are
tracked in [REMEDIATION.md](REMEDIATION.md).
