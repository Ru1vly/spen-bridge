# S Pen Bridge: Complete Setup Guide

Follow this guide to get your Samsung S Pen and tablet working as a professional graphics tablet on Linux.

## Table of Contents

- [1. Linux PC Setup](#1-linux-pc-setup)
- [2. Android App Setup](#2-android-app-setup)
- [3. Connection Modes](#3-connection-modes)
- [4. Configuring Your Drawing Apps](#4-configuring-your-drawing-apps)
- [5. Testing Without a Tablet (Synthetic Strokes)](#5-testing-without-a-tablet-synthetic-strokes)

## 1. Linux PC Setup

### Step 1: Grant uinput Permissions

The Linux kernel's `uinput` module lets the server create a virtual graphics tablet. Make sure your user has access to `/dev/uinput`:

```bash
chmod +x server/setup_uinput.sh
./server/setup_uinput.sh
```

> [!NOTE]
> If you were newly added to the `input` group, log out and log back in for the change to take effect.

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

With no display available, the server starts in headless mode automatically; with one available and no other flags, it launches the desktop GUI. Pass `--gui` or `--cli` to force one or the other. Every flag below overrides the saved config for that run only.

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

## 2. Android App Setup

### Building and Installing the App

1. Open the `android/` directory in **Android Studio**.
2. Connect your Samsung Galaxy Tab via USB (make sure Developer Options and USB Debugging are enabled).
3. Click **Run** (`Shift + F10`) to install the app onto your tablet.

> [!TIP]
> You can also build the APK directly and install it with adb: `./gradlew assembleDebug`, then `adb install app/build/outputs/apk/debug/app-debug.apk`.

## 3. Connection Modes

You can connect either over **Wi-Fi** or over a **USB cable** (recommended for the lowest possible latency).

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

## 4. Configuring Your Drawing Apps

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

## 5. Testing Without a Tablet (Synthetic Strokes)

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
