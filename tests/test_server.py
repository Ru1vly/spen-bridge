import unittest

from server.server import SPenServer
from server.protocol import (
    PenEvent,
    ACTION_MOVE,
    ACTION_DOWN,
    BUTTON_TOUCH,
    BUTTON_STYLUS,
    TOOL_STYLUS,
    TOOL_ERASER,
)


class FakeTablet:
    def __init__(self):
        self.calls = []

    def handle_event(self, ev):
        self.calls.append(ev)


class TestEventGroupDispatch(unittest.TestCase):
    """SPenServer._dispatch_event_groups() coalesces a Wi-Fi backlog (several
    already-buffered packets delivered in one read()) down to the freshest
    position sample, to avoid the on-screen cursor visibly catching up in
    slow motion after a network stall. It must never do this within a single
    packet (Android's own historical-sample batching for stroke fidelity),
    and must never drop a press/release/proximity transition or a button
    state change."""

    def setUp(self):
        self.tablet = FakeTablet()
        self.server = SPenServer(tablet=self.tablet)

    def test_intra_packet_events_all_preserved(self):
        group = [
            PenEvent(ACTION_MOVE, 0, BUTTON_TOUCH, 0.1, 0.1, 0.5),
            PenEvent(ACTION_MOVE, 0, BUTTON_TOUCH, 0.2, 0.2, 0.5),
            PenEvent(ACTION_MOVE, 0, BUTTON_TOUCH, 0.3, 0.3, 0.5),
        ]
        self.server._dispatch_event_groups([group])
        self.assertEqual(len(self.tablet.calls), 3)

    def test_backlog_of_pure_moves_coalesces_to_freshest(self):
        groups = [
            [PenEvent(ACTION_MOVE, 0, BUTTON_TOUCH, 0.1, 0.1, 0.5)],
            [PenEvent(ACTION_MOVE, 0, BUTTON_TOUCH, 0.2, 0.2, 0.5)],
            [PenEvent(ACTION_MOVE, 0, BUTTON_TOUCH, 0.3, 0.3, 0.5)],
        ]
        self.server._dispatch_event_groups(groups)
        self.assertEqual(len(self.tablet.calls), 1)
        self.assertEqual(self.tablet.calls[0].x, 0.3)

    def test_button_transition_preserved_across_backlog(self):
        groups = [
            [PenEvent(ACTION_MOVE, 0, 0, 0.1, 0.1, 0.5)],
            [PenEvent(ACTION_MOVE, 0, BUTTON_TOUCH, 0.2, 0.2, 0.5)],
            [PenEvent(ACTION_MOVE, 0, BUTTON_TOUCH, 0.3, 0.3, 0.5)],
        ]
        self.server._dispatch_event_groups(groups)
        self.assertEqual(len(self.tablet.calls), 2)
        self.assertEqual((self.tablet.calls[0].buttons, self.tablet.calls[0].x), (0, 0.1))
        self.assertEqual((self.tablet.calls[1].buttons, self.tablet.calls[1].x), (BUTTON_TOUCH, 0.3))

    def test_transient_button_blip_survives(self):
        groups = [
            [PenEvent(ACTION_MOVE, 0, 0, 0.1, 0.1, 0.5)],
            [PenEvent(ACTION_MOVE, 0, BUTTON_STYLUS, 0.2, 0.2, 0.5)],
            [PenEvent(ACTION_MOVE, 0, 0, 0.3, 0.3, 0.5)],
        ]
        self.server._dispatch_event_groups(groups)
        self.assertEqual(len(self.tablet.calls), 3)

    def test_action_down_never_dropped(self):
        groups = [
            [PenEvent(ACTION_DOWN, 0, BUTTON_TOUCH, 0.1, 0.1, 0.5)],
            [PenEvent(ACTION_MOVE, 0, BUTTON_TOUCH, 0.2, 0.2, 0.5)],
        ]
        self.server._dispatch_event_groups(groups)
        self.assertEqual(len(self.tablet.calls), 2)
        self.assertEqual(self.tablet.calls[0].action, ACTION_DOWN)

    def test_lone_event_always_delivered(self):
        self.server._dispatch_event_groups([[PenEvent(ACTION_MOVE, 0, BUTTON_TOUCH, 0.5, 0.5, 0.5)]])
        self.assertEqual(len(self.tablet.calls), 1)

    def test_tool_type_change_across_backlog_not_coalesced(self):
        # Same action + same buttons, but a stylus/eraser tool switch: must not
        # be treated as a stale duplicate even without an intervening hover
        # exit/enter.
        groups = [
            [PenEvent(ACTION_MOVE, TOOL_STYLUS, BUTTON_TOUCH, 0.1, 0.1, 0.5)],
            [PenEvent(ACTION_MOVE, TOOL_ERASER, BUTTON_TOUCH, 0.2, 0.2, 0.5)],
        ]
        self.server._dispatch_event_groups(groups)
        self.assertEqual(len(self.tablet.calls), 2)
        self.assertEqual(self.tablet.calls[0].tool_type, TOOL_STYLUS)
        self.assertEqual(self.tablet.calls[1].tool_type, TOOL_ERASER)

    def test_stats_count_dispatched_not_raw_received(self):
        groups = [
            [PenEvent(ACTION_MOVE, 0, BUTTON_TOUCH, 0.1, 0.1, 0.5)],
            [PenEvent(ACTION_MOVE, 0, BUTTON_TOUCH, 0.2, 0.2, 0.5)],
            [PenEvent(ACTION_MOVE, 0, BUTTON_TOUCH, 0.3, 0.3, 0.5)],
        ]
        self.server._dispatch_event_groups(groups)
        # 3 raw events arrived, but only the freshest is actually applied —
        # stats must reflect what was applied, not what arrived.
        self.assertEqual(len(self.tablet.calls), 1)
        self.assertEqual(self.server.stats_events_count, 1)
        self.assertEqual(self.server.total_events_count, 1)


if __name__ == "__main__":
    unittest.main()
