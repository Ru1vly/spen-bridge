# Pairing and network setup

Use the matching Android app and desktop server from this checkout. Protocol v2
requires TLS and pairing; older unauthenticated senders cannot connect.

1. Connect both devices to the same local network. On desktop, open
   **Connection → Pair tablet**. This enables paired Wi-Fi access, starts or
   restarts the listener as needed, and opens discovery for two minutes.
2. On Android, open **Settings → Find desktop** and select your desktop.
   Compare the six-digit verification number on both screens, then choose
   **Allow device** on the desktop only if they match. No fingerprint or pairing
   code needs to be typed. Cancel if the numbers differ or the request is unexpected.
3. Android saves the approved desktop address and credentials automatically.
   Existing paired devices keep working. The desktop's **Wireless address** always
   comes from a physical LAN adapter, preferring Wi-Fi over Ethernet or USB
   tethering; it never shows USB loopback. Without a usable LAN adapter it says
   the address is unavailable. USB needs no IP entry.
4. Discovery uses UDP port **40119**, only while Pair tablet is open. Pairing and
   pen traffic use TLS on the selected TCP port (default **40118**). Allow these
   ports on your private local network. Discovery may be blocked by guest-network
   isolation or networks that suppress broadcasts. Advanced connection settings
   retain manual pairing for those environments; `python server/main.py
   --show-pairing` displays the existing identity for that fallback.
5. Connect a USB-debugging-authorized device and use **Set up USB connection**.
   While the desktop app stays open, it checks every two seconds and restores
   forwarding after a cable reconnect. Enable **Set up USB automatically on launch**
   to restore this monitor on future launches. CLI users can run
   `adb -d reverse tcp:40118 tcp:40118`, replacing both ports as needed.

Every connection cycle tries **USB first**, then **Wi-Fi immediately** if USB
fails. Only when both attempts fail does it wait **five seconds**, then start
again with USB. While connected over Wi-Fi, the app checks USB readiness every two seconds using
an authenticated read-only probe. Once USB is ready, it hands over after at least
750 ms without pen events, with no held tip/barrel button and an empty input queue.
Active strokes remain on Wi-Fi. A new USB session requires fresh capture
acknowledgement; old input is never replayed. After a connection drops, the sender
continues the USB-first retry sequence. Status text and the
Wi-Fi latency lock follow the route that actually authenticated. Pairing is
required for both routes.

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

For automatic discovery, also allow UDP 40119 on the same private subnet:

```powershell
New-NetFirewallRule -Name 'SPenBridge-Discovery' -DisplayName 'S Pen Bridge discovery' `
  -Direction Inbound -Action Allow -Profile Private -Protocol UDP `
  -LocalPort 40119 -RemoteAddress LocalSubnet -Program $python -ErrorAction Stop
```

Check that the displayed port and executable match the running server. Change or
remove this rule when changing ports or returning to USB. Linux firewall setup
varies by distribution; allow the chosen TCP port and UDP 40119 from your tablet's local network.

Pairing identity lives in `identity.json` next to the desktop config. It is created
owner-only and must stay private. Back it up securely if retaining an existing
pairing. If compromised, stop the server, remove that identity locally, then open
Pair tablet to generate a new identity and re-pair your own devices. Existing pins
and codes will stop working. Never share the identity file or paste the code in logs.
