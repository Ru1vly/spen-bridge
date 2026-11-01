# One UI native implementation contract

The user's pinned Samsung direction overrides unrelated concepts. The design
seed ran (18dacccc); travel boards, poster walls, botanical folios, star charts,
developer consoles and split-flap boards are declined because they obscure
product tasks and conflict with the requested Samsung interface. Keep their
useful disciplines only: persistent connection state, strong focus, consistent
scale, stable coordinates, separated destructive actions and readable status.

## First viewport

A quiet One UI workspace: S Pen Bridge as a large black/white title, readable
connection status, an explicit Input profile summary and one blue Start Server action. A rounded
selection marks Connection, Pen settings, App profiles or Preferences in an
expanded left rail or compact native tabs. The active-profile control lives in
the expanded rail footer; the Edit profile tuning target is labelled separately. White groups on a gray ground in light
mode, charcoal groups on black in dark mode. No bevels or ornamental shadows.
The user's real configuration drives every control.

On Android, the canvas fills the screen. A compact rounded toolbar becomes a
side rail in landscape and a reachable bottom bar in portrait; icon actions have
spoken labels. Settings separate a generous viewing title from grouped
Connect, Drawing area and Controls sections. The same field instances retain
unsaved edits across section changes, and selection survives rotation. Save
validates all sections and reveals Connect when pairing fields need attention.
Save stays reachable with keyboard/system insets. Tablets center the form at a
readable width. A separate connection chip above the canvas opens settings; long
status captions do not widen the bottom/side action dock.

## Interaction

The signature transition is functional: the same drawing controls change from
bottom bar to side rail without replacing the canvas or reconnecting the sender.
Collapsed controls restore from the same edge. Connection messages remain
available as spoken labels and tooltips when the visual caption is truncated.
Desktop navigation becomes a left rail at 70 M-widths; smaller or larger-text
workspaces use native tabs. Connection columns fit their measured minimum widths
with a 54 M-width floor, otherwise stacking Connection, canvas, then diagnostics.
Pen settings separates Pressure, Mapping, Buttons and Device into category pages
with independent scrolling. App profiles separates management and matching from
tuning; its sidebar becomes a compact selector above details below 60 M-widths.
Preferences owns startup and logs. All layouts preserve existing field instances,
configuration ownership and selection signals.
Native focus, switches, keyboard navigation and system Back remain authoritative.

## Source and implementation boundary

Samsung's current public One UI guidelines and One UI 9 product page are the
visual reference. There is no verified official Qt kit or downloadable One UI 9
Android SDK in those sources. The implementation is an app-owned native adaptation using Google Material
Components 1.12.0, AndroidX AppCompat 1.7.0 and PySide6 6.11.2/custom QSS.
It does not install an official Samsung component library. A Samsung firmware
release number is not the dependency or custom-theme version. See
[UI library provenance](UI_LIBRARY_PROVENANCE.md).
The requested visual world is pinned; no unrelated style choice is pending.

The optional 12ui draft service rejected the request pending account sign-in.
No generated concept was returned or approved, so native implementation proceeds
against Samsung's published design system. There is no pixel-comp approval claim.

## Quality gates

Keep all functions in ONE_UI_REWRITE.md. Test Android build, unit tests and lint;
run the desktop regressions; inspect actual native screenshots for both themes,
compact and expanded widths, large text, phone and tablet, both orientations,
profile sections and dialogs. No HTML/CSS detector runs on native UI code.
Physical S Pen timing, Samsung firmware-specific rendering and Windows native
input need hardware; headless renders do not prove those properties.

The layout-v2 evidence is kept in `audit/evidence/layout-v2/`; the older One UI
captures describe the prior layout and are not current layout validation. See
[layout redesign](LAYOUT_REDESIGN.md) for current task structure and verification
scope. Do not infer completed device/runtime or independent review from this
visual contract; use the final evidence records.
