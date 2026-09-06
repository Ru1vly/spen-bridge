# S Pen on Linux 🎨

Turn your Samsung Galaxy Tab and S Pen into a low-latency, pressure-sensitive graphics tablet for Linux (Krita, GIMP, Blender, Inkscape, Xournal++, etc.).

---

## Why this exists

Samsung's S Pen uses **Wacom EMR digitizer technology** inside the tablet screen for drawing (4096 levels of pressure sensitivity, tilt angles, hover tracking, and palm rejection). The S Pen does **not** send drawing coordinates over Bluetooth.

**S Pen on Linux** bridges this by running:
1. **An Android app** on your Samsung tablet that captures native S Pen hardware events (`MotionEvent`).
2. **A Linux server** that creates a virtual Wacom tablet device via the Linux kernel's `uinput` subsystem and injects the events into your desktop.

Your Linux apps recognize it as a real physical graphics tablet.

---

## Key Features

- 🎯 **Full 4096-level Pressure Sensitivity**: Natural, dynamic brush thickness and opacity.
- 📐 **Stylus Tilt Support**: X and Y tilt angles mapped to kernel evdev.
- ✨ **Hover & Proximity Tracking**: Hover cursor preview before touching the screen.
- ⚡ **High Sampling Rate**: Processes Android `MotionEvent` historical batches for up to 240Hz+ stroke smoothness.
- 🛡️ **Hardware Palm Rejection**: Rejects capacitive finger touch when using stylus.
- 🔌 **Dual Connection Modes**:
  - **USB Cable Mode (ADB Forward)**: Near-zero latency, immune to network jitter.
  - **Wi-Fi Mode**: Convenient wireless drawing across local network.
- 🖥️ **Multi-Monitor Mapping**: Map the tablet to a specific monitor or full virtual desktop.
- 🧪 **Built-in Synthetic Stroke Generator**: Test your setup in Krita/GIMP without needing an Android device connected.

---

## Architecture

```
[ Samsung Galaxy Tab + S Pen ]
           │
           │  MotionEvent (X, Y, Pressure, Tilt, Barrel Button)
           ▼
[ Android App (Kotlin) ]
           │
           │  24-byte Binary Protocol (TCP / TCP_NODELAY)
           ▼
[ Linux Server (Python) ]
           │
           │  Kernel-level event injection via /dev/uinput
           ▼
[ Linux Input Subsystem (evdev / libinput) ]
           │
           ▼
[ Krita / GIMP / Blender / Inkscape ]
```

---

## Quick Start

### 1. Linux Server Setup

```bash
# Set up uinput permissions
./server/setup_uinput.sh

# Create virtual environment and install dependencies
uv venv server/.venv
uv pip install --python server/.venv/bin/python -r server/requirements.txt

# Launch the Desktop GUI Control Panel
./start.sh
# Or launch directly:
server/.venv/bin/python server/main.py --gui

# Or run in headless console mode:
server/.venv/bin/python server/main.py --cli
```

### 2. Verify with Synthetic Test

To see the virtual tablet in action without connecting a tablet yet:
```bash
server/.venv/bin/python server/test_synthetic.py
```

### 3. Connect Android App

Open the `android/` directory in Android Studio, install the app onto your Samsung tablet, open **Settings**, and enter your PC's IP or connect via USB:

```bash
# For USB mode:
adb forward tcp:40118 tcp:40118
```

See [docs/SETUP.md](docs/SETUP.md) for detailed instructions.

---

## Documentation

- [Setup & Configuration Guide](docs/SETUP.md)
- [Binary Network Wire Protocol](docs/PROTOCOL.md)

---

## License

MIT License
