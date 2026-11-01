"""Frame-boundary and failure safety of combined uinput writes; no OS input."""

import struct
import sys
from unittest.mock import Mock, patch

import pytest

if not sys.platform.startswith("linux"):
    pytest.skip("Linux native input ABI", allow_module_level=True)
pytest.importorskip("evdev")
from evdev import ecodes as e

from server.backends.linux_uinput import _ReportWriter

EVENT = struct.Struct("@llHHi")


def decode(data):
    return [EVENT.unpack_from(data, i)[2:] for i in range(0, len(data), EVENT.size)]


def test_complete_report_is_one_write_with_release_before_sync():
    raw = Mock(fd=123)
    writer = _ReportWriter(raw)
    with patch(
        "server.backends.linux_uinput._write_native",
        side_effect=lambda _fd, data: len(data),
    ) as write:
        writer.write(e.EV_ABS, e.ABS_X, 123)
        writer.write(e.EV_KEY, e.BTN_TOUCH, 0)
        write.assert_not_called()
        writer.syn()
        assert write.call_count == 1
        assert decode(bytes(write.call_args.args[1])) == [
            (e.EV_ABS, e.ABS_X, 123),
            (e.EV_KEY, e.BTN_TOUCH, 0),
            (e.EV_SYN, e.SYN_REPORT, 0),
        ]


def test_aligned_short_write_completes_without_repeating_edges():
    writer = _ReportWriter(Mock(fd=123))
    consumed = []

    def write(_fd, data):
        n = EVENT.size if not consumed else len(data)
        consumed.append(bytes(data[:n]))
        return n

    with patch("server.backends.linux_uinput._write_native", side_effect=write):
        writer.write(e.EV_KEY, e.BTN_TOUCH, 1)
        writer.syn()
    assert decode(b"".join(consumed)) == [
        (e.EV_KEY, e.BTN_TOUCH, 1),
        (e.EV_SYN, e.SYN_REPORT, 0),
    ]


def test_failed_frame_is_not_replayed_on_release():
    writer = _ReportWriter(Mock(fd=123))
    with patch(
        "server.backends.linux_uinput._write_native",
        side_effect=OSError("disconnected"),
    ):
        writer.write(e.EV_KEY, e.BTN_TOUCH, 1)
        with pytest.raises(OSError):
            writer.syn()
    consumed = []
    with patch(
        "server.backends.linux_uinput._write_native",
        side_effect=lambda _fd, data: consumed.append(bytes(data)) or len(data),
    ):
        writer.write(e.EV_KEY, e.BTN_TOUCH, 0)
        writer.syn()
    assert decode(consumed[0]) == [
        (e.EV_KEY, e.BTN_TOUCH, 0),
        (e.EV_SYN, e.SYN_REPORT, 0),
    ]


@pytest.mark.parametrize("written", [0, 1])
def test_broken_kernel_write_cannot_spin_or_retain_a_contact_frame(written):
    writer = _ReportWriter(Mock(fd=123))
    with patch(
        "server.backends.linux_uinput._write_native", return_value=written
    ) as write:
        writer.write(e.EV_KEY, e.BTN_TOUCH, 1)
        with pytest.raises(OSError):
            writer.syn()
        assert write.call_count == 1
    writer.close()
