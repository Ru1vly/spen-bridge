# UI/UX audit — 31 October 2026

Implementation and verification follow-up: [UI/UX fixes](../docs/UI_UX_FIXES.md), [current verification status](UI_UX_VERIFICATION_2026-11-01.md). The findings below retain the original audit evidence.

Scope: Android tablet surface and settings; desktop connection, settings, profiles, and first run. Audit only; application behavior has not been changed.

Evidence: current working-tree source, plus existing same-day native captures in `audit/evidence/full-2026-10-31/screens` and `screens-mobile`. The inspected captures agree with the source on the findings below. They are historical captures, not a newly executed build. No new device, screen-reader, contrast, or performance measurements were run. Scores below are provisional source-review scores; unmeasured performance is deliberately unscored.

## Verdict

The apps use native controls and have a coherent One UI adaptation. They do not read as web ports. The central UX problem is attention: the tablet competes with the desktop for attention, while the desktop foregrounds testing and implementation details. Preserve the native controls, theme roles, focus behavior, and adaptive navigation; reduce what users must see and decide.

| Dimension | Provisional score | Evidence / limit |
| --- | --- | --- |
| Accessibility | 2/4 | Spoken labels, sp text and generous targets exist; a new visual area editor needs equivalent nonvisual controls. TalkBack traversal is unverified. |
| Performance | Unscored | Input and rendering performance need measurement; no claim of jank from screenshots. |
| Appearance and theming | 3/4 | Shared light/dark roles; redundant headings and oversized diagnostic surface weaken hierarchy. |
| Platform conformance | 3/4 | Native Views and Qt, immersive system-bar handling; recoverability must survive a blank tablet surface. |
| Adaptivity | 3/4 | Orientation-aware dock and font-aware desktop layouts exist; area editor and large-text arrangements need verification. |

No defensible total /20 is available without performance verification. Findings: 0 P0, 6 P1, 4 P2. These priorities describe this UX scope, not overall release readiness.

## Findings and acceptance criteria

### 1. [P1] Pen use does not clear the mobile interface

Location: `android/app/src/main/java/com/spenbridge/app/MainActivity.kt:138` and `PenSurfaceView.kt:361`.

Manual collapse hides the dock but leaves a restore button; the connection chip is separate. Hover handling draws a cursor without driving chrome visibility. Visible controls can distract and intercept input at their locations.

Recommendation: one pen-presence state controlling all app-owned overlays. Hide controls before contact, on hover entry, and keep them hidden through contact and brief hover interruptions. Preserve layout geometry so hiding chrome never changes coordinate mapping. Restore controls only after the pen leaves proximity, with a short delay to avoid flicker. Keep Android Back/system gestures available and an accessible, finger-operated way to reach settings when idle. No persistent restore affordance while pen input is active.

Acceptance: hover, draw, lift, move across every edge, cancel, disconnect and reconnect; no dock, status chip, restore button, tooltip, snackbar or app dialog appears over active pen use. Connection errors remain available in Settings afterward. OS-owned overlays are outside the app's control.

Suggested command: `$impeccable harden`.

### 2. [P1] Tablet mode still paints text and pen feedback

Location: `PenSurfaceView.kt:404–470`; `res/values/strings.xml`, HUD strings.

The active-area label is painted directly onto the surface. A hover circle is unconditional during hover; local strokes are enabled by default. These violate the requested blank input surface.

Recommendation: tablet mode is an input surface with no visible text. During hover/contact it is visually blank, including frame, shading, cursor and local trail under the user's strict “no element” requirement. Move all area visualization into Settings. Retain a spoken surface description for accessibility; invisible accessibility text is not visual UI.

Acceptance: restricted and full areas, all aspect choices, both themes and orientations contain zero painted strings; active pen use contains zero app-owned decoration. Transport and desktop input continue normally.

Suggested command: `$impeccable distill`.

### 3. [P1] Area adjustment requires guessing

Location: `SettingsActivity.kt:173–220`; `TabletArea.kt:5`; `activity_settings.xml`, area section.

Four sliders update number labels only. Users must save, leave Settings and inspect the surface to understand the result. Aspect modes also allow independent width/height scaling, so the resulting rectangle can depart from the selected ratio.

Recommendation: a live tablet-shaped preview above the controls, backed by the same `TabletArea.calculate` geometry as input mapping. Drag to position; resize with handles; offer sliders or numeric fields as accessible alternatives. Show target display ratio and usable area. Keep preview visible while editing. Provide Center, Reset and explicit Apply/Cancel behavior. Clarify whether aspect selection locks the ratio or defines a base rectangle; prefer locked ratio until explicitly unlocked.

Acceptance: every value edit updates preview immediately; drag updates values; boundaries clamp correctly; rotation uses the intended drawing orientation; preview and applied geometry match. Cancel leaves saved mapping untouched. Test minimum size, edge alignment, large text, touch and TalkBack.

Suggested command: `$impeccable shape`, then `$impeccable adapt`.

### 4. [P1] Unrelated pairing validation blocks local settings

Location: `SettingsActivity.kt:232–253`.

Save validates host, port, fingerprint and pairing code before persisting any area or control preference. A user cannot configure the tablet before pairing.

Recommendation: save local preferences independently. Validate connection credentials when pairing or applying connection changes. Preserve incomplete connection drafts across navigation. Warn about unsaved edits on exit only when edits would actually be lost.

Acceptance: a fresh unpaired install can change area and input preferences; invalid pairing data produces errors beside connection fields without discarding local edits.

Suggested command: `$impeccable harden`.

### 5. [P1] Desktop connection is dominated by a redundant drawing surface

Location: `server/gui/system_tab.py:51`, `scratchpad_panel.py`; `main_window.py:167,506–572`.

The “Try your pen” panel receives the larger column. Swatches, synthetic strokes and a local canvas compete with pairing and connection. Users already draw in their desktop application.

Recommendation: remove the drawing panel and its palette/actions from the desktop UI. Use the recovered space for a compact connection summary and useful next action. Put optional pressure/input diagnostics behind “Connection details” or Support. Remove scratchpad wiring and lifecycle assumptions as part of implementation; simply hiding the widget leaves unnecessary work and dependencies.

Acceptance: no S Pen drawing/test canvas in any workspace or window size. Pairing, pressure configuration, transport and useful diagnostic export remain functional.

Suggested command: `$impeccable distill`.

### 6. [P1] Fresh installs contain application-specific behavior

Location: `server/config.py:81–143,162,430–446`.

Fresh configuration seeds osu!, Krita and Blender, including app matching and button/pressure behavior. The legacy fallback also seeds these profiles. This creates choices and potentially changes behavior users never requested.

Recommendation: one neutral baseline configuration, no named app profiles or matching rules. Present “No app profiles yet” with a Create profile action. The required internal Default fallback can remain a baseline rather than masquerading as an app preset. Do not add an unsolicited preset catalog. Preserve existing user profiles and legacy personal settings; avoid silently deleting profiles that happen to share built-in names.

Acceptance: clean installation, absent profile field, empty profile map and legacy migration do not inject app presets. Save/reload does not resurrect removed profiles. Existing user profiles survive. Check default auto-switch behavior alongside the empty state.

Suggested command: `$impeccable onboard`, then `$impeccable harden`.

### 7. [P2] Mobile Settings spends too much space explaining itself

Location: `activity_settings.xml`; `strings.xml`, section headings and summaries.

The selected tab, large title and card heading repeat “Drawing area.” The phone capture places useful controls below substantial heading space. Pairing exposes a fingerprint, long code, network fields and a lengthy USB explanation together.

Recommendation: a compact Settings index: Connection, Tablet area, Input, and a quiet Support row at the end. Use one heading per page. Put the preview first on Tablet area. Show current desktop and connection state before technical fields. Keep port, fingerprint and manual transport details in Advanced. A scan/import pairing flow is a useful later improvement but requires a real protocol flow, not a decorative scan button.

Acceptance: the first viewport supports the page's main task; routine area editing does not require opening technical connection options. Retain all necessary advanced capabilities.

Suggested command: `$impeccable distill`, then `$impeccable layout`.

### 8. [P2] Support has no quiet, dedicated destination

Location: Android Settings sections (`SettingsActivity.kt:60`); desktop Preferences and activity log.

Recovery instructions currently occupy routine connection screens. Users need help when something fails, without ongoing troubleshooting clutter.

Recommendation: a final “Help and support” row in Settings/Preferences. Open a separate page with connection troubleshooting, setup instructions, app version, and a user-triggered Copy diagnostic report action. Do not add banners, badges, automatic support popups or review prompts. Reports should exclude pairing secrets and certificate credentials; show what will be copied. Do not invent contact channels or nonfunctional links.

Acceptance: support is reachable from Settings, absent from tablet mode, and does not interrupt normal use. Any external link has a real configured destination. Diagnostic copying requires an explicit action.

Suggested command: `$impeccable shape`, then `$impeccable clarify`.

### 9. [P2] Copy describes implementation more than the next action

Location: `server/gui/connection_panel.py:90`; `header_bar.py:85`; Android `strings.xml`.

Examples: the persistent USB/Wi-Fi paragraph, “Enable USB Mode (ADB),” “Configured (server stopped),” and the generic settings subtitle. Warnings can list several causes without helping distinguish them. Title capitalization also varies.

Recommendation: use short, state-specific copy; give one actionable recovery step when the app has evidence for it. Put implementation explanations in details/help. Suggested wording:

| Current | Proposed |
| --- | --- |
| Connect your desktop. Make the pen feel like yours. | Remove; Settings already states the task. |
| Enable USB Mode (ADB) | Set up USB connection; explain USB debugging in the setup flow. |
| Configured (server stopped): … | Not running; keep address in connection details. |
| Input profile / Edit profile | Using: … / Editing: …, consistently placed. |
| Horizontal Alignment: 50% | Horizontal position, with a preview that explains what 50% means. |
| 16:9 · Recommended | 16:9; recommend a ratio only when supported by the actual target display. |

Comparison reference: [Wikipedia:Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing), read 31 October 2026. Its relevant observations concern generic/promotional wording, formulaic phrasing and vague explanations. Apply them as an editorial lens, not an authorship detector: the page explicitly cautions that these patterns do not establish AI authorship. The application mostly has plain functional copy; the main opportunity is specificity and removing unnecessary prose, not adding a chatty personality.

Acceptance: labels use sentence case, each message explains actual state, and recovery text never asserts a cause the app has not detected. Preserve technical accuracy in help.

Suggested command: `$impeccable clarify`.

### 10. [P2] Save state is too subtle on desktop

Location: `server/gui/header_bar.py:110`.

The global save button changes to “Save settings •”. A small dot does not clearly explain whether changes affect the live session or have been persisted.

Recommendation: establish one documented model for live application versus persistence. Show explicit “Unsaved changes” near Save, confirm success inline, and guard actual loss on exit. Avoid a permanent enabled save action when there is nothing to save. Keep live and edited profile context clear when automatic switching occurs.

Acceptance: changing a setting, saving, switching profiles, restarting and exiting each have predictable results; users can tell which profile is currently in use and which one they are editing.

Suggested command: `$impeccable clarify`, then `$impeccable harden`.

## Recommended delivery order

1. `$impeccable distill` / `$impeccable harden`: blank tablet mode, pen-driven overlay state, desktop canvas removal, and independent local settings saves.
2. `$impeccable onboard` / `$impeccable harden`: neutral fresh configuration and safe migration.
3. `$impeccable shape` / `$impeccable adapt`: live area editor and simpler settings with unobtrusive Support.
4. `$impeccable clarify`: state-specific copy, save feedback and profile context.
5. `$impeccable polish`: one bounded native verification pass across phone/tablet, portrait/landscape, compact/expanded desktop, both themes and large text; fix findings together and confirm once.

Verify pen proximity on real S Pen hardware, including edge hover, palm contact, cancellation, rotation and disconnect during drawing. Verify TalkBack and keyboard access separately from visual screenshots. Measure whether preview/chrome updates affect input latency before claiming a performance improvement. Re-run `$impeccable audit` after fixes.

Existing strengths to retain: theme-aware native controls, 48dp-or-larger main touch targets, spoken action descriptions, system-inset handling, font-aware desktop navigation, separate live/edit profile context, and shared tablet-area geometry.
