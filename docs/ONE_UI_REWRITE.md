# One UI rewrite coverage

Current behavior is described in [UI/UX fixes](UI_UX_FIXES.md). This document records the earlier layout work; its canvas, settings tabs and preview descriptions are historical.

The subsequent [layout redesign](LAYOUT_REDESIGN.md) supersedes the screen
structure documented in this first-pass record. The theme remains a custom
native adaptation; [library provenance](UI_LIBRARY_PROVENANCE.md) explains it.

Status: both native interfaces rewritten and verified. The independent visual
review identified one responsive Profiles issue; its final verdict scored the
correction resolved. Design documentation is included in DESIGN.md.

## Current baseline

Fresh desktop captures were generated from the current worktree with
`SPEN_RENDER_TAG=-oneui-baseline python audit/render_remediation.py`.
Both tabs rendered at 960×640 and 760×540 with 10-point text, and at
960×720 with 16-point text, without increasing the requested window size.
The six captures are in `audit/evidence/remediation-qt-oneui-baseline-*.png`.
The renderer mocks device/server startup and is visual evidence only, not a
connection or native-input test. PySide6 is 6.11.2 in this environment.

`adb devices -l` currently reports no connected Android devices. The SDK exists
at `/tmp/spen-android-sdk`; Android visual validation still requires a device
or emulator. No 12ui or Android emulator job was running during this inventory.

The requested scope is the complete Android app and desktop receiver. Existing
transport, pairing, input, and configuration behavior must remain available.

## Design sources

- Samsung identifies [One UI 9](https://www.samsung.com/us/apps/one-ui/) as its
  current public release (checked 30 October 2026).

- Samsung's current public [One UI guidelines](https://developer.samsung.com/one-ui/index.html)
  cover phone, tablet, and PC experiences.
- [Basic layout](https://developer.samsung.com/one-ui/layout/basic.html)
  separates the viewing area from reachable interaction controls.
- [Large-screen layout](https://developer.samsung.com/one-ui/largescreen-and-foldable/large_screen_layout.html)
  is the authority for expanded layouts.
- The community [OneUIProject library](https://github.com/OneUIProject/oneui-design)
  is not an official Samsung SDK. Its README references One UI 4; it must not be
  represented as Samsung's latest official kit.

No official Qt kit has been identified. The desktop implementation needs native
Qt controls with a shared One UI visual specification. Verify Android library
currency and compatibility before choosing dependencies.

## Android surfaces

- Drawing canvas: connected, connecting, disconnected, input preview, active-area
  border and shading; expanded and collapsed controls; portrait and landscape;
  left/right toolbar placement and large text.
- Connection settings: host, port, fingerprint, pairing code, password visibility,
  USB guidance, validation, save and return.
- Active area: five aspect modes; custom width, height, offsets and alignment
  presets; border and shading switches.
- Display/input: toolbar placement, orientation, stroke preview and touch rejection.
- System surfaces: dialogs, keyboard, status/navigation bars and launch icon.

## Desktop surfaces

- Application shell: title, listener status, active profile, start/stop transitions,
  save state, recovery notice and navigation.
- Profiles: list, selection, create/duplicate/delete, default/global behavior,
  application matches, auto switching, identity, device, pressure curve, mapping
  and barrel buttons.
- System: connection, USB/Wi-Fi information, pairing dialog, startup preferences,
  diagnostics, scratchpad, synthetic input and logs.
- Shared controls: collapsible sections, chips, badges, validation and confirmation
  dialogs, tray menu and notifications.

## Completion evidence required

- Build Android and run its relevant tests and lint.
- Run the desktop regression suite and verify configuration/signal behavior.
- Render both desktop tabs, dialogs and representative profile states at compact,
  expanded and large-text sizes.
- Inspect Android drawing and settings at phone/tablet sizes, both orientations,
  large text and each supported theme.
- Exercise pairing, connection transitions, save, profile changes and input
  controls without replacing real functionality with illustrative UI.
- Compare implementation against the chosen design references, and document any
  unavailable platform validation explicitly.

## Implemented and verified

- Android: app-owned One UI color roles for light/dark; rounded grouped settings;
  centered tablet form; compact landscape header; reachable save; keyboard and
  system insets; 48dp icon actions with spoken labels; bottom bar/side rail;
  collapse/restore; left/right controls; themed canvas and adaptive launcher icon.
- Desktop: app-owned One UI theme for Qt, matching painted widgets, grouped
  settings and dialog surfaces, selection/focus states, status labels, native
  menus, named/selectable drawing swatches and responsive Connection columns and a compact profile selector above the full-width
  editor when a sidebar would constrain it.
- `audit/render_one_ui.py` renders both desktop themes, compact/expanded and
  **actual 16pt child fonts**, profile sections, pairing and profile dialogs.
  It asserts the child fonts before each capture; a prior invalid font-scale
  capture was replaced after independent review identified the harness issue.
- `audit/capture_one_ui_android.py` runs only on a disposable emulator. The current
  pass completed 32 checks, including phone/tablet viewport classes, both themes,
  portrait/landscape, large text, keyboard, validation, hide/show, valid save and
  moving the toolbar to the right. Pairing values are synthetic, not credentials.
- Android: 41 unit tests pass; debug APK and lint pass. Desktop: 126 tests and 17
  subtests pass. Detailed logs and native PNG/XML captures are in
  `audit/evidence/one-ui/`.

The current Android captures come from an API 34 Google emulator with phone and
large-screen size/density overrides, not Samsung firmware or physical devices.
Qt captures use the Linux offscreen plugin. Physical S Pen timing, actual Samsung
firmware rendering and Windows native-input hardware are not asserted by this
UI validation. Transport and input behavior are preserved and covered by the
existing regression suites; this rewrite does not change those subsystems.
