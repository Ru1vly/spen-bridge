# UI/UX fixes — 31 October 2026

Implements the changes in [the UI/UX audit](../audit/UI_UX_AUDIT_2026-10-31.md). This is a native One UI adaptation using existing Kotlin Views and Qt controls.

## Android

- Tablet mode paints no labels, local strokes, hover cursor, crop frame or shading. The icon dock and restore button disappear on pen proximity/contact. A delayed proximity-exit restore avoids flicker without changing the input viewport. Connection changes cannot independently restore the dock.
- Settings opens an index: Connection, Tablet area, Input, Help and support. Back moves to the index; exiting with unapplied changes offers Discard or Keep editing. Cancel uses the same loss guard. Android view-state restoration retains drafts across rotation.
- Tablet area uses a live, pinned preview. It moves beside scrolling controls in wide, short windows. Dragging moves the active rectangle; the bottom-right handle resizes it. Gesture calculations retain total movement from pointer-down, so slow movements are not lost to rounding and grabbing near the corner does not make it jump. Native, named sliders provide equivalent adjustments. Fixed-ratio modes synchronize height to width; Custom allows independent dimensions. Reset chooses a full surface. Preview and runtime both call `TabletArea.calculate`; the runtime passes its actual viewport dimensions to Settings.
- Apply tablet settings persists area/input preferences without validating pairing. Apply connection separately validates and persists manual pairing details. An empty Wi-Fi address is valid for USB-only use. A preview never changes saved mapping until Apply.
- The Connection page shows the most recent transport message passed from tablet mode. Pairing fields are behind Manual pairing details. Messages are absent from the tablet surface.
- Help and support is a separate native screen with setup/recovery instructions and a previewed diagnostic report. Copy is explicit. No hostnames, pairing credentials or logs are exported.

## Desktop

- Connection contains pairing and USB setup. The drawing canvas, swatches, synthetic-stroke UI and its preview buffering/wiring have been removed from the application window. The CLI synthetic test tool remains available.
- Live input diagnostics are behind a collapsed Connection details section. Help and support is a quiet, collapsed final section in Preferences, containing recovery instructions, a previewed allowlisted report and the existing bounded activity log. Copying a diagnostic report does not copy that log.
- Fresh configuration contains a neutral Default fallback only; automatic app switching is off. No named application profile is seeded during installation, loading an empty profile map, or migrating flat legacy settings. Existing user profiles and matching rules survive loading/saving. Deleted application profiles stay deleted.
- Save is disabled while clean. Explicit Unsaved changes / Settings saved feedback replaces the dot indicator and save-success modal. Pen preferences apply live; Save persists them. Network changes require a server restart. Existing failed-save and exit-loss protections remain.
- Connection and profile copy uses concrete actions and consistent sentence case. The Wikipedia writing guide informed removing generic explanatory copy; it was not used to label text as AI-generated.

## Verification and limits

Tests use isolated settings and preserve user profiles. Native physical-device instrumentation requires the separate `.uiaudit` package and explicit `isolated_device` opt-in; it refuses to run against a physical user's real app. The audit build shares debug helpers but has its own application ID. Clipboard readback preserves supported original content; rich or locked clipboards are skipped.

```sh
server/.venv/bin/python -m pytest -q tests
# Set JAVA_HOME and ANDROID_HOME to the installed toolchains first:
./android/gradlew -p android --offline --no-daemon --max-workers=2 assembleAudit assembleDebug testDebugUnitTest lintDebug
python audit/capture_ui_ux_android.py --isolated-device --serial DEVICE_SERIAL
python audit/run_ui_ux_talkback.py --serial DEVICE_SERIAL
```

The capture runner restores display, rotation, font and theme overrides. The TalkBack runner restores original accessibility settings. Actual Samsung TalkBack and four native viewport configurations passed on the S22 Ultra. Samsung's Show Air command icon was turned off through normal Settings to remove the system-owned floating shortcut. Actual physical pen motion remains unobserved; injected events cannot establish EMR or firmware behavior. No latency improvement is claimed.

See [current verification](../audit/UI_UX_VERIFICATION_2026-11-01.md), [remaining work](UI_UX_REMAINING_WORK.md), and `audit/evidence/ui-ux-fixes/` for results and screenshots.
