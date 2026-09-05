import unittest
from server.protocol import (
    PenEvent,
    pack_packet,
    pack_events,
    unpack_header,
    unpack_events,
    HEADER_SIZE,
    PKT_EVENT,
    PKT_PING,
    PKT_PONG,
    ACTION_DOWN,
    ACTION_MOVE,
    ACTION_UP,
    TOOL_STYLUS,
    BUTTON_TOUCH,
    BUTTON_STYLUS,
)


class TestSPenProtocol(unittest.TestCase):
    def test_pack_unpack_single_event(self):
        events = [
            PenEvent(
                action=ACTION_DOWN,
                tool_type=TOOL_STYLUS,
                buttons=BUTTON_TOUCH,
                x=0.25,
                y=0.75,
                pressure=0.85,
                tilt_x=12.5,
                tilt_y=-8.0,
            )
        ]
        packet = pack_events(events, seq=100)
        hdr = unpack_header(packet[:HEADER_SIZE])
        self.assertIsNotNone(hdr)
        pkt_type, seq, payload_len = hdr
        self.assertEqual(pkt_type, PKT_EVENT)
        self.assertEqual(seq, 100)

        unpacked = unpack_events(packet[HEADER_SIZE:])
        self.assertEqual(len(unpacked), 1)
        ev = unpacked[0]
        self.assertEqual(ev.action, ACTION_DOWN)
        self.assertEqual(ev.tool_type, TOOL_STYLUS)
        self.assertEqual(ev.buttons, BUTTON_TOUCH)
        self.assertAlmostEqual(ev.x, 0.25, places=4)
        self.assertAlmostEqual(ev.y, 0.75, places=4)
        self.assertAlmostEqual(ev.pressure, 0.85, places=4)
        self.assertAlmostEqual(ev.tilt_x, 12.5, places=4)
        self.assertAlmostEqual(ev.tilt_y, -8.0, places=4)

    def test_pack_unpack_batch_events(self):
        events = [
            PenEvent(ACTION_DOWN, TOOL_STYLUS, BUTTON_TOUCH, 0.1, 0.1, 0.5),
            PenEvent(ACTION_MOVE, TOOL_STYLUS, BUTTON_TOUCH, 0.2, 0.2, 0.7, 10.0, 5.0),
            PenEvent(ACTION_UP, TOOL_STYLUS, 0, 0.2, 0.2, 0.0),
        ]
        packet = pack_events(events, seq=202)
        unpacked = unpack_events(packet[HEADER_SIZE:])
        self.assertEqual(len(unpacked), 3)
        self.assertEqual(unpacked[1].action, ACTION_MOVE)
        self.assertAlmostEqual(unpacked[1].pressure, 0.7, places=4)

    def test_clamping(self):
        # Coordinates and pressure out of bounds should be clamped safely
        events = [
            PenEvent(ACTION_DOWN, TOOL_STYLUS, 0, -0.5, 1.5, 2.0, -120.0, 150.0)
        ]
        packet = pack_events(events, seq=1)
        unpacked = unpack_events(packet[HEADER_SIZE:])
        ev = unpacked[0]
        self.assertEqual(ev.x, 0.0)
        self.assertEqual(ev.y, 1.0)
        self.assertEqual(ev.pressure, 1.0)
        self.assertEqual(ev.tilt_x, -90.0)
        self.assertEqual(ev.tilt_y, 90.0)


if __name__ == "__main__":
    unittest.main()
