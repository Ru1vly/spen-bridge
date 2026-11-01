# Experimental accessory USB host relay

This Linux prototype replaces the host ADB forwarding hop with native libusb bulk I/O. It forwards an opaque encrypted byte stream into the existing loopback TLS receiver. The Android client must still pin the server certificate and complete protocol-v2 mutual pairing proofs. The relay stores no credentials and cannot authenticate or inject pen events by itself.

**Not enabled in the application. Not yet tested against physical accessory USB.** An [Android helper prototype](../../docs/ANDROID_ACCESSORY_PROTOTYPE.md) now passes emulator lifecycle and authentication checks; physical USB, reconnect and host release behavior remain unverified. Software fixture tests establish byte preservation, TLS interoperability, bounded host cleanup and receiver ownership/reset on peer silence, not physical USB behavior or a 300 µs guarantee.

Build with a C11 compiler, pthreads and libusb development headers:

```sh
make -C native/usb-relay
native/usb-relay/spen-usb-relay --list
```

`--list` enumerates compatible devices already in accessory mode without opening or claiming their interfaces. There is no mode-switch request, automatic kernel-driver detach, configuration change or HID emulation. Only Google accessory VID 0x18d1 / PID 0x2d00, 0x2d01, 0x2d04 and 0x2d05 are accepted; vendor-specific ff/ff/00 interfaces with exactly one bulk IN and OUT endpoint are selected. The composite ADB interface is excluded.

A future physical trial explicitly selects an already configured accessory device and an **isolated diagnostic TLS receiver**, for example:

```sh
native/usb-relay/spen-usb-relay --bus 1 --address 9 --port 45000 --seconds 15
```

The prototype connects only to 127.0.0.1. It does not start a receiver or touch the normal desktop's existing connection. The command has a hard experiment duration of 1–60 seconds. Exiting disconnects the receiver, whose ordinary ownership cleanup releases input state.

Two workers transfer both directions independently using fixed 16 KiB buffers. Each USB operation has a 25 ms cancellation polling bound; successful data is forwarded immediately, without waiting for that interval. USB timeout results may contain partial bytes: reads retain them and writes resume at the exact unsent offset. Zero-length USB packets are not treated as EOF. Backpressure is bounded by a two-second progress deadline and the overall experiment deadline. A separate liveness check disconnects the local receiver after three seconds without positive inbound USB bytes (error `SPEN_RELAY_PEER_IDLE`, -9). The normal sender heartbeat runs every second, even while the pen is idle. Outbound host traffic and zero-length USB packets do not refresh this timer. The timer is a disconnect safeguard, not an input latency allowance. Workers join before the USB handle/interface is released. These bounds depend on libusb honoring its timeout contract; they are not real-time scheduling guarantees.

The fixture under `tests/native/` is compiled separately and is not part of the production executable. It simulates bulk transfers over a socket pair, including seven-byte partial progress accompanied by timeout status. Run:

```sh
server/.venv/bin/python -m pytest -q tests/test_native_usb_relay.py
```

References: [AOA interface identification](https://source.android.com/docs/core/interaction/accessories/aoa), [AOA 2.0 product IDs](https://source.android.com/docs/core/interaction/accessories/aoa2), [libusb partial transfers and timeout semantics](https://libusb.sourceforge.io/api-1.0/group__libusb__syncio.html).

The liveness tests keep the simulated USB socket attached while an authenticated client stops sending, verify that one-second PINGs maintain the session, then observe local receiver ownership being cleared and its reset callback invoked after silence. A separate test sends only host-to-phone bytes and confirms that those cannot keep a dead phone session alive. Nine native fixture tests pass with AddressSanitizer/UndefinedBehaviorSanitizer; physical unplug/helper-stop behavior remains a required S22 test before enabling real OS input.
