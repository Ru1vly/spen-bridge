# S Pen Bridge

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform: Linux](https://img.shields.io/badge/platform-Linux-informational.svg)
![Windows: planned](https://img.shields.io/badge/Windows-planned-lightgrey.svg)

Turn your Samsung Galaxy Tab and S Pen into a low latency, pressure sensitive graphics tablet for Linux (Krita, GIMP, Blender, Inkscape, Xournal++, and more). Windows support is planned for an upcoming release.

## Table of Contents

- [Why This Exists](#why-this-exists)
- [Key Features](#key-features)
- [Platform Support](#platform-support)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
  - [1. Install on Linux](#1-install-on-linux)
  - [2. Verify With a Synthetic Test](#2-verify-with-a-synthetic-test)
  - [3. Connect the Android App](#3-connect-the-android-app)
- [Documentation](#documentation)
- [License](#license)

## Why This Exists

Samsung's S Pen uses **Wacom EMR digitizer technology** inside the tablet screen for drawing: 4096 levels of pressure sensitivity, tilt angles, hover tracking, and palm rejection. The S Pen does **not** send drawing coordinates over Bluetooth.

**S Pen Bridge** works around that by running two pieces:

1. **An Android app** on your Samsung tablet that captures native S Pen hardware events (`MotionEvent`).
2. **A Linux server** that creates a virtual Wacom tablet device via the Linux kernel's `uinput` subsystem and injects those events into your desktop.

Your Linux apps recognize the result as a real physical graphics tablet.

## Key Features

| Feature | Description |
| --- | --- |
| Full 4096 level pressure sensitivity | Natural, dynamic brush thickness and opacity |
| Stylus tilt support | X and Y tilt angles mapped to kernel evdev |
| Hover and proximity tracking | Hover cursor preview before the pen touches the screen |
| High sampling rate | Processes Android `MotionEvent` historical batches for up to 240Hz+ stroke smoothness |
| Hardware palm rejection | Rejects capacitive finger touch while the stylus is in use |
| Dual connection modes | USB cable mode (ADB forward) for near zero latency, or Wi-Fi mode for wireless drawing |
| Multi-monitor mapping | Map the tablet to a specific monitor or to the full virtual desktop |
| Built-in synthetic stroke generator | Test your setup in Krita or GIMP without an Android device connected |

## Platform Support

| Platform | Status |
| --- | --- |
| Linux | Supported |
| Windows | Planned for an upcoming release |

## Architecture

```
[ Samsung Galaxy Tab + S Pen ]
           |
           |  MotionEvent (X, Y, Pressure, Tilt, Barrel Button)
           v
[ Android App (Kotlin) ]
           |
           |  24-byte Binary Protocol (TCP / TCP_NODELAY)
           v
[ Linux Server (Python) ]
           |
           |  Kernel-level event injection via /dev/uinput
           v
[ Linux Input Subsystem (evdev / libinput) ]
           |
           v
[ Krita / GIMP / Blender / Inkscape ]
```

## Quick Start

### 1. Install on Linux

The fastest way to get set up is the one-command installer. It clones the repo into `~/spen-bridge`, sets up uinput permissions, creates the Python virtual environment, and installs a desktop launcher entry. Running it again later updates an existing install in place.

```bash
curl -fsSL https://raw.githubusercontent.com/Ru1vly/spen-bridge/main/install.sh | bash
```

> [!TIP]
> Piping a script into `bash` runs it with your permissions. Read [install.sh](install.sh) first if you would rather see exactly what it does before running it.

Prefer to do it by hand, or already have the repo cloned? Run the same steps yourself:

```bash
# Set up uinput permissions
./server/setup_uinput.sh

# Create a virtual environment and install dependencies
uv venv server/.venv
uv pip install --python server/.venv/bin/python -r server/requirements.txt
```

Either way, launch with:

```bash
# Desktop GUI control panel
./start.sh

# Or launch the GUI directly:
server/.venv/bin/python server/main.py --gui

# Or run in headless console mode:
server/.venv/bin/python server/main.py --cli
```

### 2. Verify With a Synthetic Test

To see the virtual tablet in action without connecting a tablet yet:

```bash
server/.venv/bin/python server/test_synthetic.py
```

### 3. Connect the Android App

Fastest path: connect your tablet over USB, download the latest APK from [Releases](https://github.com/Ru1vly/spen-bridge/releases/latest), and install it directly:

```bash
adb install spen-bridge-android-*.apk
```

Prefer building it yourself instead? Open the `android/` directory in Android Studio and install the app onto your tablet from there.

Either way, open **Settings** in the app and enter your PC's IP address, or connect via USB:

```bash
# For USB mode (the server listens on the PC; the app connects to
# 127.0.0.1 on the tablet, so the tunnel must run device-port -> host-port):
adb reverse tcp:40118 tcp:40118
```

See [docs/SETUP.md](docs/SETUP.md) for detailed instructions.

## Documentation

| Document | Covers |
| --- | --- |
| [Setup & Configuration Guide](docs/SETUP.md) | Full install, connection, and per-app configuration walkthrough |
| [Binary Network Wire Protocol](docs/PROTOCOL.md) | The TCP wire format shared by the Android client and Linux server |

## License

MIT License.
