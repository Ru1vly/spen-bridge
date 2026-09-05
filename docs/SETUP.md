# S Pen on Linux — Complete Setup Guide

Follow this guide to get your Samsung S Pen and tablet working as a professional graphics tablet on Linux.

---

## 1. Linux PC Setup

### Step 1: Grant uinput Permissions
The Linux kernel's `uinput` module allows the server to create a virtual graphics tablet. Ensure your user has access to `/dev/uinput`:

```bash
chmod +x server/setup_uinput.sh
./server/setup_uinput.sh
```

*(If you are newly added to the `input` group, log out and log back in for changes to take effect).*

### Step 2: Install Server Dependencies
Using `uv` (recommended) or standard `venv`:

```bash
# Using uv (fastest)
uv venv server/.venv
uv pip install --python server/.venv/bin/python -r server/requirements.txt

# Or using standard python
python3 -m venv server/.venv
source server/.venv/bin/activate
pip install -r server/requirements.txt
```

### Step 3: Run the Server
```bash
server/.venv/bin/python server/main.py
```

Options:
- `--port 40118` (Default port)
- `--screen-bounds "0,0,1920,1080"` (Map tablet strictly to a specific monitor)
- `--desktop-size "1920,2160"` (Full multi-monitor desktop size)
- `--direct` (Flag as on-screen display tablet instead of indirect pad)
- `--debug` (Verbose logging)

---

## 2. Android App Setup

### Building and Installing the App
1. Open the `android/` directory in **Android Studio**.
2. Connect your Samsung Galaxy Tab via USB (ensure Developer Options and USB Debugging are enabled).
3. Click **Run** (`Shift + F10`) to install the app onto your tablet.
   *(Or build the APK via `./gradlew assembleDebug` and install with `adb install app/build/outputs/apk/debug/app-debug.apk`).*

---

## 3. Connection Modes

You can connect either via **Wi-Fi** or via **USB cable (recommended for ultra-low latency)**:

### Mode A: USB Cable (Zero Latency via ADB) — Recommended! ⭐
Using USB provides near-zero latency and is immune to Wi-Fi jitter.

1. Connect tablet to PC via USB cable.
2. Ensure `adb` is installed on your PC (`sudo pacman -S android-tools` or `sudo apt install adb`).
3. Run port forwarding:
   ```bash
   adb forward tcp:40118 tcp:40118
   ```
4. Open the **S Pen on Linux** app on your tablet.
5. Tap **Settings**, set **Server IP** to `127.0.0.1`, and tap **Save & Reconnect**.

### Mode B: Local Wi-Fi
1. Make sure your Linux PC and Samsung tablet are connected to the same Wi-Fi network (preferably 5GHz).
2. Find your Linux PC's local IP address:
   ```bash
   ip -brief address
   # Look for 192.168.x.x or 10.x.x.x under your wifi or ethernet interface
   ```
3. Open the **S Pen on Linux** app on your tablet.
4. Tap **Settings**, enter your PC's IP address and port (default `40118`), and tap **Save & Reconnect**.
5. The status dot will turn **Green (Connected)**.

---

## 4. Configuring Your Drawing Apps

### Krita
1. Open Krita.
2. Go to **Settings** → **Configure Krita** → **Tablet Settings**.
3. Under *Tablet*, test your pen pressure curve in the scratchpad.
4. Note: On Wayland, Krita uses the system tablet protocol automatically. On X11, select the `Samsung S Pen Virtual Tablet` device.

### GIMP
1. Go to **Edit** → **Input Devices**.
2. Find `Samsung S Pen Virtual Tablet`.
3. Set **Mode** to `Screen` (or `Window`).
4. Save device configuration.

### Blender (Grease Pencil / Sculpting)
1. Open Blender.
2. In Sculpt mode or Grease Pencil Draw mode, pen pressure and tilt will automatically control brush radius and strength.

### Xournal++ (Note Taking & PDF Annotation)
1. Open Xournal++.
2. Go to **Edit** → **Preferences** → **Stylus**.
3. S Pen pressure sensitivity and barrel button mapping will work out of the box.

---

## 5. Testing Without Tablet (Synthetic Strokes)

To verify your Linux PC and drawing software setup before connecting a tablet:

1. Start the server:
   ```bash
   server/.venv/bin/python server/main.py
   ```
2. In a second terminal, run the test script:
   ```bash
   server/.venv/bin/python server/test_synthetic.py --count 1
   ```
3. Open Krita or any drawing app and position the canvas under your cursor: you will see a smooth spiral drawn with varying pressure and tilt!
