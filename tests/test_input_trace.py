"""Passive trace integrity, bounded storage, and local command isolation."""

import json
import os
import struct
import time
import uuid
import zlib
from pathlib import Path

import pytest

from server.input_trace import TimingCapture, TraceController

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="POSIX owner-only diagnostic controls"
)


def read_trace(path):
    data = Path(path).read_bytes()
    length = struct.unpack_from(">I", data)[0]
    header = json.loads(data[4 : 4 + length])
    payload = data[4 + length :]
    assert len(payload) == header["records"] * 64
    return header, list(struct.iter_unpack(">8q", payload))


def until(predicate):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Trace state did not converge")


def command(directory, action, **fields):
    request = dict(id=uuid.uuid4().hex, action=action, **fields)
    path = directory / "control.json"
    temporary = directory / "control-new.json"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(request, output)
    os.replace(temporary, path)


def test_bounded_trace_exports_identity_timing_and_overflow(tmp_path):
    trace = TimingCapture(2)
    for i in range(3):
        trace.packet(1, i, 1, 10, 20, 30, b"private sample bytes")
    path = tmp_path / "trace.bin"
    trace.export(path)
    header, records = read_trace(path)
    assert header["records"] == 2 and header["seen"] == 3 and header["overflow"] == 1
    assert records[0] == (4, 1, 0, 1, 10, 20, 30, zlib.crc32(b"private sample bytes"))
    assert b"private sample bytes" not in path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600
    trace.packet(1, 99, 1, 10, 20, 30, b"late")
    assert trace.seen == 3


def test_failure_is_distinct_from_successful_submission(tmp_path):
    trace = TimingCapture(2)
    trace.packet(1, 2, 1, 10, 20, 30, b"x", success=False)
    trace.export(tmp_path / "trace.bin")
    assert read_trace(tmp_path / "trace.bin")[1][0][0] == 5


def test_controller_can_start_and_export_without_restarting_input(tmp_path):
    directory = tmp_path / "private"
    controller = TraceController(directory)
    try:
        command(directory, "start", seconds=30)
        until(lambda: controller.enabled)
        controller.packet(1, 2, 1, 10, 20, 30, b"x")
        command(directory, "stop")
        until(lambda: controller.status["state"] == "ready")
        assert not controller.enabled
        assert read_trace(directory / controller.status["file"])[0]["records"] == 1
    finally:
        controller.close()


def test_old_control_file_does_not_restart_a_capture(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    command(directory, "start", seconds=30)
    controller = TraceController(directory)
    try:
        time.sleep(0.25)
        assert not controller.enabled
        assert controller.status["state"] == "idle"
    finally:
        controller.close()


def test_nonprivate_request_and_symlink_are_ignored(tmp_path):
    directory = tmp_path / "private"
    controller = TraceController(directory)
    try:
        command(directory, "start", seconds=30)
        (directory / "control.json").chmod(0o644)
        time.sleep(0.25)
        assert not controller.enabled
        (directory / "control.json").unlink()
        target = tmp_path / "outside"
        target.write_text(
            json.dumps({"id": "outside", "action": "start", "seconds": 30})
        )
        target.chmod(0o600)
        (directory / "control.json").symlink_to(target)
        time.sleep(0.25)
        assert not controller.enabled
    finally:
        controller.close()


def test_public_control_directory_is_rejected(tmp_path):
    directory = tmp_path / "public"
    directory.mkdir(mode=0o755)
    with pytest.raises(ValueError):
        TraceController(directory)
