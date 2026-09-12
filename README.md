# S Pen Bridge

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform: Linux](https://img.shields.io/badge/platform-Linux-informational.svg)
![Windows: experimental](https://img.shields.io/badge/Windows-experimental-orange.svg)
[![Linux CI](https://github.com/Ru1vly/spen-bridge/actions/workflows/linux-ci.yml/badge.svg)](https://github.com/Ru1vly/spen-bridge/actions/workflows/linux-ci.yml)

Turn your Samsung Galaxy Tab and S Pen into a low latency, pressure sensitive graphics tablet for Linux (Krita, GIMP, Blender, Inkscape, Xournal++, and more) and Windows (Windows Ink).

## Table of Contents

- [Why This Exists](#why-this-exists)
- [Key Features](#key-features)
- [Platform Support](#platform-support)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
  - [1. Install on Linux](#1-install-on-linux)
  - [2. Install on Windows](#2-install-on-windows)
  - [3. Verify With a Synthetic Test](#3-verify-with-a-synthetic-test)
  - [4. Connect the Android App](#4-connect-the-android-app)
- [Documentation](#documentation)
- [License](#license)

## Why This Exists

Samsung's S Pen uses **Wacom EMR digitizer technology** inside the tablet screen for drawing: 4096 levels of pressure sensitivity, tilt angles, hover tracking, and palm rejection. The S Pen does **not** send drawing coordinates over Bluetooth.

**S Pen Bridge** works around that by running two pieces:

1. **An Android app** on your Samsung tablet that captures native S Pen hardware events (`MotionEvent`).
2. **A desktop server** (Python) that creates a virtual tablet device via the Linux kernel's `uinput` subsystem or Windows Virtual HID Framework (KMDF/VHF) and injects those events into your desktop.

Your drawing applications recognize the result as a real physical graphics tablet.

## Key Features

| Feature | Description |
| --- | --- |
| Full 4096 level pressure sensitivity | Natural, dynamic brush thickness and opacity |
| Stylus tilt support | X and Y tilt angles mapped to kernel evdev (Linux) and HID reports (Windows) |
| Hover and proximity tracking | Hover cursor preview before the pen touches the screen |
| High sampling rate | Processes Android `MotionEvent` historical batches for up to 240Hz+ stroke smoothness |
| Hardware palm rejection | Rejects capacitive finger touch while the stylus is in use |
| Dual connection modes | USB cable mode (`adb reverse`) for zero latency, or Wi-Fi mode for wireless drawing |
| Customizable pressure curves | Linear, Soft, Firm, and Sigmoid response curves with real-time visual preview |
| Per-app profiles | Automatically switches profiles and mappings based on active window title/class |
| Multi-monitor coordinate mapping | Map the tablet to a specific monitor, custom area, or the full virtual desktop (with negative offset support) |
| Barrel button remapping | Map stylus barrel buttons to Right Click, Middle Click, Left Click, or Eraser toggle |
| Built-in synthetic stroke generator | Test your setup in Krita or GIMP without an Android device connected |

## Platform Support

| Platform | Subsystem | Status |
| --- | --- | --- |
| **Linux** (X11 & Wayland) | `/dev/uinput` via `evdev`/`libinput` | Fully supported |
| **Windows 10/11 x64** | Windows Ink via Virtual HID Framework (`spenvhid.sys`) | Supported (driver requires test-signing or self-signing) |

## Architecture

```
[ Samsung Galaxy Tab + S Pen ]
               |
               |  MotionEvent (X, Y, Pressure, Tilt, Barrel Button)
               v
    [ Android App (Kotlin) ]
               |
               |  24-byte Binary Protocol (TCP / TCP_NODELAY via USB or Wi-Fi)
               v
      [ Desktop Server (Python) ]
               |
     +---------+---------+
     |                   |
     v (Linux)           v (Windows)
[ /dev/uinput ]     [ VHF / KMDF Driver (spenvhid.sys) ]
     |                   |
     v                   v
[ evdev / libinput ] [ Windows Ink / HID Digitizer ]
     |                   |
     +---------+---------+
               |
               v
[ Krita / GIMP / Blender / Inkscape / Photoshop ]
```

## Quick Start

### 1. Install on Linux

The fastest way to get set up is the one-command installer. It clones the repo into `~/spen-bridge`, sets up uinput permissions (with immediate ACL access), creates the Python virtual environment, and installs a desktop launcher entry. Running it again later updates an existing install in place.

```bash
curl -fsSL https://raw.githubusercontent.com/Ru1vly/spen-bridge/main/install.sh | bash
```

> [!TIP]
> Piping a script into `bash` runs it with your permissions. Read [install.sh](install.sh) first if you would rather see exactly what it does before running it.

Prefer to do it by hand, or already have the repo cloned? Run the same steps yourself:

```bash
# Set up uinput permissions (uses uaccess and setfacl for immediate access)
./server/setup_uinput.sh

# Create a virtual environment and install dependencies
uv venv server/.venv
uv pip install --python server/.venv/bin/python -r server/requirements.txt
```

Launch the server:

```bash
# Desktop GUI control panel
./start.sh

# Or launch the GUI directly:
server/.venv/bin/python server/main.py --gui

# Or run in headless console mode:
server/.venv/bin/python server/main.py --cli
```

### 2. Install on Windows

Requirements: Windows 10/11 x64, Python 3.10+ (with the `py` launcher).

In an administrator PowerShell prompt at the repository root:

```powershell
# 1. Install Python virtual environment, Start Menu shortcut, and configure firewall
.\install.ps1

# 2. Install the virtual HID tablet driver (see docs/WINDOWS.md to build & sign)
.\windows\install-driver.ps1 -InfPath .\dist\spenvhid\spenvhid.inf

# 3. Launch the desktop GUI
.\start.ps1

# Or run in headless CLI mode:
.\start.ps1 --cli
```

See [Windows Setup & Validation](docs/WINDOWS.md) for full driver build, test-signing, and troubleshooting details.

### 3. Verify With a Synthetic Test

To see the virtual tablet in action without connecting a tablet yet:

```bash
# Linux
server/.venv/bin/python server/test_synthetic.py

# Windows
server\.venv\Scripts\python.exe server\test_synthetic.py
```

### 4. Connect the Android App

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
| [Setup & Configuration Guide](docs/SETUP.md) | Full install, connection modes, GUI panel walkthrough, and per-app configuration |
| [Windows Setup & Driver Validation](docs/WINDOWS.md) | Windows Ink driver build, test-signing, installation scripts, and validation |
| [Binary Network Wire Protocol](docs/PROTOCOL.md) | The TCP wire format shared by the Android client and desktop server |
| [Windows Driver Protocol](docs/WINDOWS_DRIVER_PROTOCOL.md) | Kernel-level private IOCTL and HID report structures for `spenvhid.sys` |

## License

MIT License.
