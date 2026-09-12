> Windows users: see [Windows setup](WINDOWS.md) for the application and driver installation. The instructions below cover Linux.

# S Pen Bridge: Complete Setup Guide

Follow this guide to get your Samsung S Pen and tablet working as a professional graphics tablet on Linux.

## Table of Contents

- [1. Linux PC Setup](#1-linux-pc-setup)
- [2. Desktop GUI Control Panel](#2-desktop-gui-control-panel)
- [3. Android App Setup](#3-android-app-setup)
- [4. Connection Modes](#4-connection-modes)
- [5. Configuring Your Drawing Apps](#5-configuring-your-drawing-apps)
- [6. Testing Without a Tablet (Synthetic Strokes)](#6-testing-without-a-tablet-synthetic-strokes)
- [7. Troubleshooting & FAQ](#7-troubleshooting--faq)

## 1. Linux PC Setup

### Step 1: Grant uinput Permissions

The Linux kernel's `uinput` module lets the server create a virtual graphics tablet. Run the included setup script:

```bash
chmod +x server/setup_uinput.sh
./server/setup_uinput.sh
```

> [!NOTE]
> The setup script installs `/etc/udev/rules.d/80-spen-bridge.rules` with `TAG+="uaccess"`, adds your user to the `input` group, and immediately applies an ACL via `setfacl` to `/dev/uinput`. **You do not need to log out or reboot**—the virtual tablet is ready to use immediately.

### Step 2: Install Server Dependencies

Using `uv` (recommended) or a standard `venv`:

```bash
# Using uv (fastest)
uv venv server/.venv
uv pip install --python server/.venv/bin/python -r server/requirements.txt

# Or using standard Python
python3 -m venv server/.venv
source server/.venv/bin/activate
pip install -r server/requirements.txt
```

### Step 3: Run the Server

```bash
server/.venv/bin/python server/main.py
```

With no display available, the server starts in headless mode automatically; with a display available and no other flags, it launches the desktop GUI. Pass `--gui` or `--cli` to force one or the other. Every flag below overrides the saved config for that run only.

| Flag | Default | Description |
| --- | --- | --- |
| `--gui` | off | Launch the desktop graphical control panel |
| `--cli` | off | Force headless CLI server mode |
| `--host <address>` | from config (`0.0.0.0`) | Host or IP address to bind the server to |
| `--port <port>` | from config (`40118`) | TCP port to listen on |
| `--name <name>` | from config | Virtual tablet device name |
| `--mode {pointer,tablet}` | from config (`pointer`) | `pointer` drives an absolute cursor with clicks; `tablet` exposes a pure tablet-v2 device |
| `--direct` | off | Enable `INPUT_PROP_DIRECT`, for a screen-mapped display tablet |
| `--screen-bounds "x,y,width,height"` | from config | Map the tablet to a specific screen region, for example `"0,0,1920,1080"` |
| `--desktop-size "width,height"` | from config | Full desktop resolution used to scale the mapping, for example `"1920,2160"` |
| `--debug` | off | Enable verbose debug logging |

## 2. Desktop GUI Control Panel

Running `./start.sh` or `server/.venv/bin/python server/main.py --gui` launches the desktop control panel:

### Connection & Status Panel
- **Status Indicator**: Shows whether the server is actively listening, connected to an Android client, or encountered an error.
- **Network Details**: Displays local LAN IP addresses and port number, along with a quick-connect QR code.
- **ADB Reverse Button**: One-click setup for USB tethered drawing (`adb reverse tcp:40118 tcp:40118`).

### Profile Management
- **Default Profile**: Used when no application-specific profile matches.
- **Application Profiles**: Create specialized configurations that activate automatically when you switch to specific windows (matches window title or application class, such as `krita`, `gimp`, `blender`, `inkscape`).
- **Profile Independence**: Every profile stores its own device mode, pressure curve, monitor mapping, and barrel button actions.

### Device Identity & Modes
- **Pointer Mode (Default)**: Emulates an absolute pointing device with click events. Compatible with all desktop applications and window managers out of the box.
- **Tablet Mode**: Exposes a pure Wacom-style `tablet-v2` digitizer interface. Best for applications that listen specifically to tablet pen events.
- **Direct Mode (`INPUT_PROP_DIRECT`)**: Configures the device as an on-screen display digitizer (useful if using your tablet as a secondary monitor with Moonlight, Sunshine, or Deskreen).

### Screen & Monitor Mapping
- **Full Desktop**: Spans tablet input across your entire virtual desktop.
- **Monitor Selection**: Automatically detects connected displays across X11 (`xrandr`), Wayland (`wlr-randr`, `hyprctl`), and Qt.
- **Negative Offset Handling**: Fully normalizes multi-monitor setups where secondary displays have negative X or Y origins relative to the primary display.
- **Custom Bounds & Aspect Lock**: Define an arbitrary rectangle `[X, Y, Width, Height]` or lock proportions to prevent circle distortion on widescreen canvases.

### Pressure Calibration
- **Curves**: Choose between `Linear`, `Soft` (gentle touch yields higher pressure), `Firm` (requires deliberate force), or `Sigmoid` (S-curve response).
- **Gamma & Thresholds**: Fine-tune gamma exponent and set minimum/maximum deadzones.
- **Real-Time Pressure Bar**: Visual widget reflecting real-time pressure when drawing with the S Pen.

### Stylus Buttons & Touch
- **Barrel Button Actions**: Remap the S Pen barrel button to `Right Click`, `Middle Click`, `Left Click`, or `Eraser Toggle`.
- **Click on Touch**: Toggle whether surface contact generates a primary mouse button click.
- **Stroke Smoothing**: Configurable moving-average filter to eliminate jitter during slow linework.

### System Tray
- When a system tray is available (KDE Plasma, XFCE, GNOME with AppIndicator), closing the window minimizes the bridge to the tray.
- If no tray is available, the window gracefully closes the application directly.

## 3. Android App Setup

### Building and Installing the App

1. Open the `android/` directory in **Android Studio**.
2. Connect your Samsung Galaxy Tab via USB (make sure Developer Options and USB Debugging are enabled).
3. Click **Run** (`Shift + F10`) to install the app onto your tablet.

> [!TIP]
> You can also build the APK directly and install it with adb: `./gradlew assembleDebug`, then `adb install app/build/outputs/apk/debug/app-debug.apk`. Pre-built APK releases are also available on [GitHub Releases](https://github.com/Ru1vly/spen-bridge/releases/latest).

## 4. Connection Modes

You can connect either over **USB cable** (recommended for zero latency) or over **Wi-Fi**.

### Mode A: USB Cable (Zero Latency via ADB, Recommended)

Using USB provides near zero latency and is immune to Wi-Fi jitter.

1. Connect the tablet to your PC via USB cable.
2. Make sure `adb` is installed on your PC (`sudo pacman -S android-tools` or `sudo apt install adb`).
3. Set up the reverse tunnel (the server listens on the PC; the app connects
   to `127.0.0.1` on the tablet, so the tunnel must run device-port -> host-port,
   which is what `adb reverse` does - `adb forward` runs the opposite direction
   and won't work here):
   ```bash
   adb reverse tcp:40118 tcp:40118
   ```
   *(Or simply click **Run ADB Reverse** in the desktop GUI control panel).*
4. Open the **S Pen Bridge** app on your tablet.
5. Tap **Settings**, set **Server IP** to `127.0.0.1`, then tap **Save & Reconnect**.

### Mode B: Local Wi-Fi

1. Make sure your Linux PC and Samsung tablet are on the same Wi-Fi network (preferably 5GHz).
2. Find your Linux PC's local IP address:
   ```bash
   ip -brief address
   # Look for 192.168.x.x or 10.x.x.x under your Wi-Fi or Ethernet interface
   ```
3. Open the **S Pen Bridge** app on your tablet.
4. Tap **Settings**, enter your PC's IP address and port (default `40118`), then tap **Save & Reconnect**.
5. The status dot turns green once connected.

## 5. Configuring Your Drawing Apps

### Krita

1. Open Krita.
2. Go to **Settings > Configure Krita > Tablet Settings**.
3. Under **Tablet**, test your pen pressure curve in the scratchpad.
4. On Wayland, Krita uses the system tablet protocol automatically. On X11, select the `Samsung S Pen Virtual Tablet` device.

### GIMP

1. Go to **Edit > Input Devices**.
2. Find `Samsung S Pen Virtual Tablet`.
3. Set **Mode** to `Screen` (or `Window`).
4. Save the device configuration.

### Blender (Grease Pencil / Sculpting)

1. Open Blender.
2. In Sculpt mode or Grease Pencil Draw mode, pen pressure and tilt automatically control brush radius and strength.

### Xournal++ (Note Taking and PDF Annotation)

1. Open Xournal++.
2. Go to **Edit > Preferences > Stylus**.
3. S Pen pressure sensitivity and barrel button mapping work out of the box.

## 6. Testing Without a Tablet (Synthetic Strokes)

To verify your Linux PC and drawing software setup before connecting a tablet:

1. Start the server:
   ```bash
   server/.venv/bin/python server/main.py
   ```
2. In a second terminal, run the test script:
   ```bash
   server/.venv/bin/python server/test_synthetic.py --count 1
   ```
3. Open Krita or any drawing app and position the canvas under your cursor. You should see a smooth spiral drawn with varying pressure and tilt.

## 7. Troubleshooting & FAQ

### Permission Denied on `/dev/uinput`
Run `./server/setup_uinput.sh`. The script configures udev rules and applies immediate ACL permissions (`setfacl`). If running in an environment without `acl` or `systemd-uaccess`, verify that your user belongs to the `input` group:
```bash
groups $USER
```
If you were just added to the group, a new session or `newgrp input` is required.

### ADB Reverse Fails
- Ensure USB debugging is enabled under Developer Options on your tablet.
- Run `adb devices` to check if the tablet is listed as `device` (not `unauthorized`). If prompted on the tablet screen, allow USB debugging.
- Verify no other service is bound to port 40118.

### Wayland Tablet Cursor Visibility
Under Wayland compositors (GNOME Wayland, Sway, Hyprland), tablet tools may appear only when the pen is in proximity (hovering). Ensure your tablet is actively transmitting hover events by hovering the S Pen within ~1 cm of the tablet glass.

### Multi-Monitor Coordinate Discrepancy
If strokes land on the wrong monitor:
1. Open the S Pen Bridge GUI.
2. Under **Screen Mapping**, select your specific drawing display instead of **Full Desktop**.
3. S Pen Bridge automatically offsets negative coordinates and handles mixed orientations.
