"""Opt-in passive timing capture. No positions, credentials or input injection.

SPEN_TRACE_DIR enables a private local control directory at server startup.
A background poller processes bounded, owner-only JSON requests; the packet path
only writes primitive records to an already allocated bounded memory buffer.
"""

from __future__ import annotations

import json
import os
import stat
import struct
import threading
import time
import uuid
import zlib
from pathlib import Path

_RECORD = struct.Struct(">8q")


class TimingCapture:
    def __init__(self, capacity=200000, backend_name="unspecified"):
        if not 1 <= capacity <= 200000:
            raise ValueError("Invalid timing capacity")
        self._buffer = bytearray(capacity * _RECORD.size)
        self.capacity = capacity
        self.backend_name = backend_name
        self.stored = self.seen = 0
        self.closed = False
        self.lock = threading.Lock()
        self.began = time.perf_counter_ns()

    def packet(
        self,
        session,
        sequence,
        count,
        received,
        decoded,
        submitted,
        payload,
        success=True,
        kind=None,
    ):
        with self.lock:
            if self.closed:
                return
            self.seen += 1
            if self.stored == self.capacity:
                return
            _RECORD.pack_into(
                self._buffer,
                self.stored * _RECORD.size,
                kind if kind is not None else (4 if success else 5),
                session,
                sequence,
                count,
                received,
                decoded,
                submitted,
                zlib.crc32(payload),
            )
            self.stored += 1

    def export(self, destination):
        with self.lock:
            self.closed = True
        metadata = {
            "version": 1,
            "side": "desktop",
            "backend": self.backend_name,
            "clock": "perf_counter_ns",
            "clock_implementation": time.get_clock_info("perf_counter").implementation,
            "record_bytes": 64,
            "started_ns": self.began,
            "ended_ns": time.perf_counter_ns(),
            "records": self.stored,
            "seen": self.seen,
            "overflow": self.seen - self.stored,
        }
        header = json.dumps(metadata).encode()
        destination = Path(destination)
        temporary = destination.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(struct.pack(">I", len(header)))
                output.write(header)
                output.write(memoryview(self._buffer)[: self.stored * _RECORD.size])
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return metadata


class TraceController:
    def __init__(self, directory, backend_name="unspecified"):
        self.backend_name = backend_name
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = self.directory.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
        ):
            raise ValueError(
                "Timing directory must be owner-only and owned by this user"
            )
        self.current = None
        self._deadline = 0
        self._last_request = None
        self._started_wall_ns = time.time_ns()
        self._stop = threading.Event()
        self.status = {"state": "idle"}
        self._thread = threading.Thread(
            target=self._run, name="SPenTraceControl", daemon=True
        )
        self._thread.start()

    @property
    def enabled(self):
        return self.current is not None

    def packet(self, *args, **kwargs):
        capture = self.current
        if capture is not None:
            capture.packet(*args, **kwargs)

    def _publish(self):
        path = self.directory / "status.json"
        temporary = self.directory / "status.tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(self.status, output)
        os.replace(temporary, path)

    def _finish(self):
        capture, self.current = self.current, None
        if capture is None:
            return
        name = "input-trace-" + uuid.uuid4().hex + ".bin"
        self.status = {"state": "exporting", "file": name}
        self._publish()
        meta = capture.export(self.directory / name)
        self.status = {"state": "ready", "file": name, "metadata": meta}
        self._publish()

    def _request(self):
        path = self.directory / "control.json"
        info = path.lstat()
        if info.st_mtime_ns < self._started_wall_ns:
            return
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
            or info.st_size > 2048
        ):
            raise ValueError("Timing request must be an owner-only regular file")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as source:
            opened = os.fstat(source.fileno())
            if opened.st_ino != info.st_ino or opened.st_dev != info.st_dev:
                return
            request = json.loads(source.read(2049))
        if not isinstance(request, dict):
            raise TypeError("Invalid timing request")
        identifier = request.get("id")
        if not isinstance(identifier, str) or not identifier or len(identifier) > 128:
            raise ValueError("Invalid request identity")
        if identifier == self._last_request:
            return
        self._last_request = identifier
        action = request.get("action")
        if action == "start":
            seconds = request.get("seconds", 30)
            if type(seconds) is not int or not 1 <= seconds <= 60:
                raise ValueError("Invalid duration")
            if self.current is not None:
                raise ValueError("A timing capture is already active")
            self.current = TimingCapture(backend_name=self.backend_name)
            self._deadline = time.monotonic() + seconds
            self.status = {"state": "recording", "id": identifier, "seconds": seconds}
            self._publish()
        elif action == "stop":
            self._finish()
        else:
            raise ValueError("Invalid timing command")

    def _run(self):
        self._publish()
        while not self._stop.wait(0.1):
            try:
                if self.current is not None and time.monotonic() >= self._deadline:
                    self._finish()
                self._request()
            except FileNotFoundError:
                pass
            except (OSError, ValueError, TypeError):
                # Invalid control requests never affect authenticated input.
                pass
        self._finish()

    def close(self):
        self._stop.set()
        self._thread.join(2)


_controller = None
_controller_lock = threading.Lock()


def get_controller():
    directory = os.environ.get("SPEN_TRACE_DIR")
    if not directory:
        return None
    global _controller
    with _controller_lock:
        if _controller is None:
            _controller = TraceController(directory)
        return _controller
