---
name: S Pen Bridge
description: App-owned native Samsung One UI adaptation for pen input.
colors:
  light-bg: "#f2f2f2"
  light-panel: "#ffffff"
  light-border: "#d7d9de"
  light-text: "#17171b"
  light-text-muted: "#565b65"
  light-accent-blue: "#165dce"
  light-accent-blue-hover: "#104da9"
  light-green: "#187447"
  light-red: "#b3261e"
  light-orange: "#8b5100"
  light-purple: "#6944b5"
  light-surface2: "#e8e9ed"
  light-surface3: "#d5d8df"
  light-surface4: "#747984"
  light-inset-bg: "#f7f7f9"
  light-selection: "#e5edfc"
  light-on-accent: "#ffffff"
  light-disabled: "#787c85"
  dark-bg: "#010101"
  dark-panel: "#171719"
  dark-border: "#3c3c41"
  dark-text: "#f5f5f7"
  dark-text-muted: "#b1b3bc"
  dark-accent-blue: "#8ab4ff"
  dark-accent-blue-hover: "#aecbff"
  dark-green: "#81d5a6"
  dark-red: "#ffb4ab"
  dark-orange: "#ffcb8a"
  dark-purple: "#d0b5ff"
  dark-surface2: "#29292d"
  dark-surface3: "#414149"
  dark-surface4: "#90909b"
  dark-inset-bg: "#222225"
  dark-selection: "#203452"
  dark-on-accent: "#092653"
  dark-disabled: "#92929c"
typography:
  desktop-display:
    fontFamily: "SamsungOne, SamsungOne UI, Segoe UI, Noto Sans, sans-serif"
    fontSize: "26px"
    fontWeight: 700
  desktop-workspace:
    fontSize: "23px"
    fontWeight: 600
  desktop-action:
    fontWeight: 600
  desktop-mono:
    fontFamily: "Cascadia Mono, DejaVu Sans Mono, monospace"
  android-display:
    fontFamily: "sans-serif"
    fontSize: "34sp"
    fontWeight: 700
  android-body:
    fontFamily: "sans-serif"
    fontSize: "16sp"
rounded:
  group: "24px"
  control: "16px"
  desktop-field: "12px"
  desktop-tab: "18px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
components:
  button-primary:
    backgroundColor: "{colors.light-accent-blue}"
    textColor: "{colors.light-on-accent}"
    rounded: "{rounded.control}"
    padding: "6px 14px"
    typography: "{typography.desktop-action}"
  button-secondary:
    backgroundColor: "{colors.light-surface2}"
    textColor: "{colors.light-text}"
    rounded: "{rounded.control}"
    padding: "6px 14px"
  field:
    backgroundColor: "{colors.light-inset-bg}"
    textColor: "{colors.light-text}"
    rounded: "{rounded.desktop-field}"
    padding: "8px 12px"
  group:
    backgroundColor: "{colors.light-panel}"
    textColor: "{colors.light-text}"
    rounded: "{rounded.group}"
    padding: "20px 16px 16px"
  navigation-selected:
    backgroundColor: "{colors.light-selection}"
    textColor: "{colors.light-accent-blue}"
    rounded: "{rounded.desktop-tab}"
    padding: "12px 22px"
  navigation-rail-selected:
    backgroundColor: "{colors.light-selection}"
    textColor: "{colors.light-accent-blue}"
    rounded: "{rounded.desktop-field}"
    padding: "10px 14px"
  button-primary-disabled:
    backgroundColor: "{colors.light-surface2}"
    textColor: "{colors.light-disabled}"
    rounded: "{rounded.control}"
    padding: "6px 14px"
  status-pill:
    backgroundColor: "{colors.light-surface2}"
    textColor: "{colors.light-text-muted}"
    padding: "5px 10px"
---

# Design System: S Pen Bridge

## Overview

**Creative North Star: "Samsung One UI"**

Samsung One UI is the pinned visual direction for both native applications. Large viewing titles, rounded flat groups, clear blue actions and reachable controls keep connection and configuration easy to scan while the Android drawing canvas stays open.

This is an app-owned adaptation built with Kotlin Views/Material Components and Qt. Samsung’s public product page and design guidelines are visual references. The installed Android libraries are Google Material Components 1.12.0 and AndroidX AppCompat 1.7.0; desktop uses PySide6 6.11.2 with app-owned QSS and widgets. None is an official Samsung One UI component SDK. A firmware release number is not a library or custom-theme version; see [UI library provenance](docs/UI_LIBRARY_PROVENANCE.md). The previous Catppuccin/neumorphic world is replaced. No generated pixel comp was approved; the optional draft service required an external account sign-in.

**Key Characteristics:**

- Flat groups separated by tone.
- One blue action language in both themes.
- Native input, focus and system behavior.
- Layouts respond to available space and text size.

## Colors

The frontmatter records the Qt source roles in both themes; Android shares the core background, surface, outline, text, primary, selection and status values. Names retain source semantics rather than introducing another token vocabulary.

### Primary

Blue identifies primary actions, selection and focus. Use the theme's matching on-accent text; dark mode has a pale blue action with dark ink. The hover role is desktop-specific.

### Neutral

Background, panel, inset, surface2–4, border, text, muted text and disabled roles establish the hierarchy. Light mode uses white groups on gray; dark mode uses charcoal groups on near-black. Android's light canvas matches the light inset role; its dark canvas matches the dark background.

Green means connected/ok, red means disconnected/error/destructive, orange means connecting/warning. Purple identifies customized desktop settings. These are semantic states rather than competing brand accents. Pair color with readable text or an accessible label.

## Typography

Qt requests SamsungOne/SamsungOne UI, then Segoe UI, Noto Sans and system sans-serif; fonts are not bundled or guaranteed. Android uses the platform sans-serif. Desktop body sizing follows the application/system font and respects larger text. Monospace is confined to logs and diagnostic text.

Desktop page titles use the desktop-display token; Android Settings uses android-display, with a smaller native header in landscape. Android body and main buttons use android-body. Desktop tabs, actions and group headings use semibold emphasis. Do not impose a web rem scale on native font settings.

## Layout

Desktop uses the source spacing rhythm, generous outer space and grouped settings. Four workspaces appear in the order Connection, Pen settings, App profiles and Preferences. At 70 times the current font metric width of “M” and above, a left rail presents the workspaces with the active-profile control in its footer; narrower or larger-text layouts use native tabs with scroll buttons. Rail width is 17 M-widths. The header separates the live **Input profile** summary from the **Edit profile** tuning target.

Connection places pairing and USB setup first. There is no desktop drawing or synthetic-stroke canvas. Live input diagnostics sit in a collapsed Connection details section. Preferences ends with a collapsed Help and support section containing troubleshooting, a previewed allowlisted diagnostic export, and the activity log.

Pen settings exposes an Edit profile selector above four category pages: Pressure, Mapping, Buttons and Device. Each category has its own scroll region. App profiles owns automatic switching, create/duplicate/delete and application matching, with an action to tune the selected profile. Its sidebar becomes a compact selector with management actions above matching details below 60 M-widths, preserving usable detail space. Both selectors share the authoritative profile-selection path. Saved old workspace indices migrate to the corresponding new tasks.

Android's tablet surface is blank: no labels, frame, shading, trail or hover cursor. The icon-only control dock is available while idle and hides, including its restore affordance, on stylus hover/contact. A delayed restore after proximity exit prevents flicker; hiding controls never changes mapping geometry. Connection messages are read in Settings rather than drawn on the tablet surface.

Android Settings opens a compact index: Connection, Tablet area, Input, and Help and support. Detail pages use a single app-bar title. The Tablet area preview stays above the scrolling values and uses the same geometry as input mapping. Dragging positions the area; the corner handle resizes it. Named native sliders are the accessible alternative; fixed-aspect modes lock height to width. Full screen is the fresh baseline. Reset, Apply, and discard-on-exit preserve explicit draft semantics. Pairing details are disclosed separately and validated only by Apply connection. Local area/input preferences apply independently. Support is a separate, user-opened native page with a previewed diagnostic report; no credentials or logs are exported.

Fresh desktop configuration contains only the neutral Default fallback, with automatic application switching off. Named application profiles are user-created; migrations preserve personal profiles and do not seed examples. Save status is explicit and inline, with Save disabled while clean. Pen edits apply live; saving persists them across launches. Network changes still require restarting the server.

Frontmatter px values describe Qt logical pixels. Android equivalents use dp for geometry and sp for text; platform-specific sizes are documented here rather than implying that px and dp are interchangeable.

## Elevation & Depth

Flat tonal layering provides separation. Qt card elevation is intentionally a no-op; Android main buttons explicitly disable elevation and state-list animation. Do not add ornamental shadows or bevels. Borders identify fields, menus and destructive actions, while stronger focus outlines communicate keyboard state. Native platform popups may retain platform rendering.

## Shapes

Rounded groups use the group radius, while desktop controls and fields use their own smaller radii. Android groups use 24dp corners, fields 16dp, and main/toolbar buttons 24dp. Desktop navigation uses rounded selection capsules. Preserve simple outlines and the shared pen/tablet silhouette in the vector and adaptive launcher artwork.

## Components

### Buttons

Blue primary actions carry the current theme's on-accent text. Neutral secondary actions use surface2, shifting to surface3 on desktop hover. Disabled named primary/success/destructive actions explicitly use disabled text, surface2 fill and border roles, rather than retaining an enabled blue/red appearance. Desktop buttons have a 28px minimum content height plus padding/border; Android main actions have a 48dp minimum height. Destructive actions use red text with an outlined panel background. Desktop keyboard focus is a visible blue border; native Android controls retain their focus/ripple behavior.

### Cards / Containers

Flat panel-colored groups organize related settings with rounded corners and interior spacing. Group labels sit above desktop cards and Android groups. Dialogs, pairing and painted widgets use the same theme roles as the main window.

### Inputs / Fields

Desktop inset fields have an outline and blue focused border; Android uses rounded filled Material text fields. Validation stays associated with the actual input, and disabled states remain visibly distinct. Native combo, spin, checkbox and radio behavior is preserved.

### Navigation

The desktop rail and compact native tabs share Connection, Pen settings, App profiles and Preferences in a stable order. Selected rows/tabs combine selection fill and blue text, with neutral hover and visible keyboard focus. Rail rows use their own padding; compact tabs preserve native scrolling. Pen category pages and Android settings sections expose task labels rather than one long undifferentiated form. Compact App profiles navigation uses a real combo with an accessible name and full-name tooltip.

### Status and matching chips

Neutral pills carry explicit status text with semantic color. Application-match chips may use a green outline for the active match. Canvas connection captions retain spoken labels/tooltips when shortened visually.

### Tablet surface and area editor

The runtime surface paints no decoration. The Settings-only area editor uses themed fills and a high-contrast outline, with a generous touch region around the resize handle. Controls retain spoken names, native slider semantics and sufficient targets. Do not reintroduce text or diagnostic overlays into tablet mode.

## Do's and Don'ts

### Do:

- Do use paired light/dark roles for every native and painted surface.
- Do preserve keyboard focus, spoken icon labels and full status tooltips.
- Do distinguish the live Input profile summary from the Edit profile target.
- Do keep compact App profiles selection above matching details and tuning categories independently scrollable.
- Do keep Android Save reachable with system bars and the keyboard.

### Don't:

- Don't add bevels, inset shadows or the discarded Catppuccin palette.
- Don't replace native workflows with illustrative controls.
- Don't call this adaptation an official Samsung SDK or promise Samsung firmware fidelity from emulator captures.
