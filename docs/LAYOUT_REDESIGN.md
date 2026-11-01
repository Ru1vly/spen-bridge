# Desktop and mobile layout redesign

Current behavior is described in [UI/UX fixes](UI_UX_FIXES.md). This document records the earlier layout work; its canvas, settings tabs and preview descriptions are historical.

This pass responds to the request to redesign the layout on **both** platforms.
It retains the native One UI-inspired visual language and changes the task
structure. It does not install an official Samsung component SDK. See
[UI library provenance](UI_LIBRARY_PROVENANCE.md) for the exact dependencies and
primary design sources.

## Desktop

- **Connection:** pairing and USB controls alongside a large pen test area, with
  live input diagnostics. The canvas toolbar wraps onto two rows; columns stack
  when their measured minimum widths cannot fit the available workspace.
- **Pen settings:** an explicit **Edit profile** selector and focused **Pressure**,
  **Mapping**, **Buttons**, and **Device** categories, each with its own scrolling
  region. The active input profile remains labelled separately.
- **App profiles:** create, duplicate and delete profiles; manage automatic
  switching and window-matching rules; jump to tuning the selected profile.
- **Preferences:** startup, network/device preferences, permission and launcher
  utilities, reset and the activity log.

Expanded windows use a left navigation rail. Compact or large-text windows use
native tabs. The old saved Profiles/Connection selection migrates to the
corresponding new workspace. The same configuration objects, signals, ownership
rules and debounced live-apply path drive all controls.

## Android

- **Connect:** desktop address, port, certificate fingerprint and pairing code.
- **Drawing area:** aspect modes, custom dimensions, alignment and area shading.
- **Controls:** toolbar side, orientation, stroke preview and touch rejection.

The sections share the original field instances, so switching sections does not
discard edits. Save validates the full configuration and reveals Connect if a
pairing field needs attention. The selected section survives rotation. Settings
keeps the native Back action and keyboard/system insets.

On the drawing surface, a small bottom dock or side rail holds rotation, settings
and hide actions. The connection state has its own chip above the canvas, which
also opens connection settings. This keeps long status messages from widening
the drawing dock. Collapsed controls restore from the same edge.

## Verification

Current evidence is written to `audit/evidence/layout-v2/`, separate from the
previous rewrite's baseline. Reproduce with:

```sh
python audit/render_layout.py
python audit/capture_layout_android.py --adb /path/to/adb --serial emulator-5554
```

The desktop harness mocks device/server startup and persisted UI state. It asserts
actual child font sizes, reachable category controls, window bounds and no
horizontal editor or Connection overflow. The Android harness only operates on a
disposable emulator, deletes stale hierarchy dumps, waits for Settings visibility,
and uses synthetic pairing values. It restores emulator display/theme/font state.

Build, test, capture and independent-review results are recorded with the final
evidence. Physical S Pen timing, Samsung firmware-specific rendering and Windows
VHF are outside the emulator/offscreen validation scope.
