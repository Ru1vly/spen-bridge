# Pairing and network setup

Use the matching Android app and desktop server from this checkout. Protocol v2
requires TLS and pairing; older unauthenticated senders cannot connect.

1. On desktop, open System & Diagnostics → **Pair Tablet**, or run
   `python server/main.py --show-pairing`. This explicit action displays a public
   certificate fingerprint and a secret pairing code. Copy them only to your tablet.
2. In Android Settings, paste both fields. Save & Apply validates all fields.
   The fingerprint pins the desktop certificate; the code authenticates each fresh
   session. A changed identity requires pairing again. Settings are excluded from
   Android backup and device transfer.
3. For USB, start the desktop server (loopback is the default), connect a debugging
   authorized USB device, and use **Enable USB Mode (ADB)**. While the desktop app stays open, it checks every two seconds and restores forwarding after a cable reconnect. Forwarding targets USB devices explicitly, so a wireless ADB connection cannot be mistaken for a cable. Enable **Auto-forward USB ADB on launch** to resume this monitoring on future launches. The button uses the
   running port. On Android enter **127.0.0.1** and that port. For CLI, run
   `adb reverse tcp:40118 tcp:40118`, substituting your selected port in both places.
4. For Wi-Fi, enable **Allow paired Wi-Fi connections** and stop/start the server,
   or launch CLI with `--wifi`. Use the desktop LAN IP and running port on Android.
   Listener changes show as pending until restart. Allow only the selected port
   through your private-network firewall. USB requires no inbound LAN firewall rule.

One authenticated tablet owns the input device at a time. Backgrounding Android,
losing focus, changing endpoints or losing the connection cancels the stroke.
Reconnect starts a new session; lift the pen and start a fresh stroke.

## Windows firewall

The installer never opens a port automatically. After opting into Wi-Fi, use
Windows Defender Firewall → Advanced settings to allow the selected TCP port for
the application's `server\.venv\Scripts\python.exe`, on the Private profile and
local subnet only. In elevated PowerShell, this example creates or updates that
specific rule; set the port and checkout path first:

```powershell
$port = 40118
$python = (Resolve-Path '.\server\.venv\Scripts\python.exe').Path
$name = 'SPenBridge-PairedWiFi'
$rule = Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue
if ($rule) { Remove-NetFirewallRule -Name $name -ErrorAction Stop }
New-NetFirewallRule -Name $name -DisplayName 'S Pen Bridge paired Wi-Fi' `
  -Direction Inbound -Action Allow -Profile Private -Protocol TCP `
  -LocalPort $port -RemoteAddress LocalSubnet -Program $python -ErrorAction Stop
Get-NetFirewallRule -Name $name -ErrorAction Stop | Get-NetFirewallPortFilter
Get-NetFirewallRule -Name $name -ErrorAction Stop | Get-NetFirewallApplicationFilter
```

Check that the displayed port and executable match the running server. Change or
remove this rule when changing ports or returning to USB. Linux firewall setup
varies by distribution; allow the chosen TCP port from your tablet's local network.

Pairing identity lives in `identity.json` next to the desktop config. It is created
owner-only and must stay private. Back it up securely if retaining an existing
pairing. If compromised, stop the server, remove that identity locally, then open
Pair Tablet to generate a new identity and re-pair your own devices. Existing pins
and codes will stop working. Never share the identity file or paste the code in logs.
