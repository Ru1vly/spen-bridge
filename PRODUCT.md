# S Pen Bridge

<!-- impeccable:product-schema 1 -->

## Platform

adaptive

## Product Purpose

Use a Galaxy tablet and S Pen as a pressure-sensitive input tablet for a Linux
or Windows desktop. The Android client captures pen input; the Python desktop
receiver manages pairing, profiles, mapping, pressure and native input.

## Users and Operating Context

Repository-derived assumption: people drawing or writing in desktop creative
applications with an existing Galaxy tablet. They need quick connection and an
unobstructed pen surface, with detailed configuration available when needed.

## Capabilities and Constraints

Preserve the existing paired TLS USB/Wi-Fi transports, all settings and profile
behaviors, diagnostics, synthetic tests, startup preferences and tray behavior.
Android uses Kotlin and Views; desktop uses Python and PySide6. Windows native
input remains experimental as documented in README.md.

## Brand Commitments

The user requests a complete rewrite of both interfaces using Samsung's latest
UI kit. Use the currently published One UI design system and current official
One UI references. Do not label community libraries or a Qt adaptation as an
official Samsung SDK. Keep the name S Pen Bridge.

## Evidence

README.md, docs/PAIRING.md and docs/ONE_UI_REWRITE.md describe product behavior.
The current source and regression tests remain the authority for functionality.
No invented telemetry, customers or performance claims belong in the UI.

## Implementation Direction

Proceed under the user's repeated instruction to continue. Preserve all existing
workflows; use native controls and Samsung's published guidelines. This is a
session assumption, not a stored preference for future design workflows.
