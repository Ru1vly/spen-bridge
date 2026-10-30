"""Check real kernel state, exclusively grabbing the virtual node before writes.

No desktop events may be sent: a failed grab aborts before handle_event. Each
UInput device is destroyed before releasing its grab. Never use physical nodes.
"""
import asyncio
import json
import tempfile
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evdev import ecodes as e
from server.backends.linux_uinput import LinuxUinputTablet
from server.protocol import (
    ACTION_DOWN, ACTION_HOVER_EXIT, BUTTON_TOUCH, BUTTON_STYLUS, PenEvent,
    HEADER_SIZE, PKT_HANDSHAKE, pack_packet, pack_events, unpack_header,
)
from server.security import auth_proof, load_identity
from server.server import SPenServer


async def verify_disconnect(tablet, device):
    async def until(predicate):
        for _ in range(200):
            if predicate():
                return
            await asyncio.sleep(.005)
        raise AssertionError("Kernel state did not converge")

    with tempfile.TemporaryDirectory(prefix="spen-isolated-pairing-") as directory:
        identity = load_identity(directory)
        server = SPenServer(tablet, port=0, tls_context=identity.server_context(), pairing_code=identity.pairing_code)
        writer = None
        try:
            await server.start()
            reader, writer = await asyncio.open_connection("127.0.0.1", server.bound_endpoint[1],
                ssl=identity.client_context(), server_hostname="localhost")
            kind, sequence, size = unpack_header(await reader.readexactly(HEADER_SIZE))
            assert (kind, sequence, size) == (PKT_HANDSHAKE, 0, 36)
            challenge = await reader.readexactly(size)
            writer.write(pack_packet(PKT_HANDSHAKE, 0, auth_proof(identity.pairing_code, challenge[4:], "client")))
            await writer.drain()
            kind, sequence, size = unpack_header(await reader.readexactly(HEADER_SIZE))
            assert (kind, sequence, size) == (PKT_HANDSHAKE, 0, 36)
            assert await reader.readexactly(size) == auth_proof(identity.pairing_code, challenge[4:], "server")
            writer.write(pack_events([PenEvent(ACTION_DOWN, 0, BUTTON_TOUCH | BUTTON_STYLUS, .5, .5, .8)]))
            await writer.drain()
            await until(lambda: bool(device.active_keys()))
            writer.close()
            await writer.wait_closed()
            await until(lambda: not device.active_keys())
            assert device.absinfo(e.ABS_PRESSURE).value == 0
        finally:
            if writer:
                writer.close()
            await server.stop()


results = []
for mode in ('pointer', 'tablet'):
    tablet = device = None
    record = dict(mode=mode, desktop_events_sent=False)
    try:
        tablet = LinuxUinputTablet(name=f'SPen isolated audit {uuid.uuid4().hex[:8]}', mode=mode,
                                    desktop_size=(1920, 1080))
        device = tablet.uinput.device
        if device is None:
            raise RuntimeError('Virtual device node unavailable; no events sent')
        device.grab()  # Mandatory before any event. Raises if unavailable.
        record['exclusive_grab'] = True
        for tool in (0, 1):
            tablet.handle_event(PenEvent(ACTION_DOWN, tool, BUTTON_TOUCH | BUTTON_STYLUS, .25, .75, .7, 15, -20))
            held = set(device.active_keys())
            expected = {e.BTN_TOUCH, e.BTN_LEFT, e.BTN_RIGHT} if mode == 'pointer' else {
                e.BTN_TOUCH, e.BTN_STYLUS, e.BTN_TOOL_RUBBER if tool else e.BTN_TOOL_PEN}
            assert held == expected, (mode, tool, held, expected)
            assert device.absinfo(e.ABS_PRESSURE).value > 0
            assert device.absinfo(e.ABS_TILT_X).value == 15
            assert device.absinfo(e.ABS_TILT_Y).value == -20
            tablet.reset()
            assert not device.active_keys(), (mode, tool, device.active_keys())
            assert device.absinfo(e.ABS_PRESSURE).value == 0
            assert device.absinfo(e.ABS_TILT_X).value == 0
            assert device.absinfo(e.ABS_TILT_Y).value == 0
        tablet.handle_event(PenEvent(ACTION_DOWN, 0, BUTTON_TOUCH | BUTTON_STYLUS, .5, .5, .5))
        tablet.update_settings(button_primary='middle_click')
        assert not device.active_keys()
        tablet.handle_event(PenEvent(ACTION_DOWN, 0, BUTTON_TOUCH | BUTTON_STYLUS, .5, .5, .5))
        tablet.handle_event(PenEvent(ACTION_HOVER_EXIT, 0, BUTTON_STYLUS, .5, .5, 0))
        assert not device.active_keys()
        asyncio.run(verify_disconnect(tablet, device))
        record['paired_tls_disconnect_release'] = True
        record['result'] = 'held outputs, reset, remap and stale-flag exit verified against kernel state'
    except Exception as error:
        record['error'] = f'{type(error).__name__}: {error}'
    finally:
        # Destroy while still grabbed. Releasing the grab on a live held device
        # could expose its state to other consumers; never do that here.
        try:
            if tablet is not None:
                tablet.close()
        finally:
            if device is not None:
                device.close()
    results.append(record)
path = Path(__file__).parent / 'evidence/remediation-linux-kernel.json'
path.write_text(json.dumps(results, indent=2))
print(path.read_text())
raise SystemExit(any('error' in record for record in results))
