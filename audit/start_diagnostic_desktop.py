"""Start the current desktop app with passive trace controls, without duplicates."""

import argparse
import json
import os
import secrets
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def matching_processes():
    result = []
    for path in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            args = path.read_bytes().split(b"\0")
            if len(args) < 3 or b"--gui" not in args:
                continue
            if (path.parent / "cwd").resolve() != ROOT:
                continue
            entry = Path(os.fsdecode(args[1]))
            if not entry.is_absolute():
                entry = ROOT / entry
            if entry.resolve() == ROOT / "server/main.py":
                result.append(int(path.parent.name))
        except (OSError, ValueError):
            continue
    return result


def main(output):
    previous = matching_processes()
    if previous:
        raise RuntimeError(
            "A desktop app is already running; this command never kills it or opens a duplicate"
        )
    python = ROOT / "server/.venv/bin/python"
    if not python.is_file():
        raise RuntimeError("Project desktop environment is missing")
    directory = (
        Path.home() / ".cache/spen-bridge" / ("diagnostics-" + secrets.token_hex(6))
    )
    directory.mkdir(parents=True, mode=0o700)
    log = directory / "desktop.log"
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        process = subprocess.Popen(
            [str(python), "server/main.py", "--gui", "--debug"],
            cwd=ROOT,
            env={**os.environ, "SPEN_TRACE_DIR": str(directory)},
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    deadline = time.monotonic() + 10
    while not (directory / "status.json").exists():
        if process.poll() is not None:
            raise RuntimeError("Desktop exited; inspect " + str(log))
        if time.monotonic() > deadline:
            raise RuntimeError(
                "App started but trace controls are not ready; inspect " + str(log)
            )
        time.sleep(0.1)
    record = dict(
        desktop_pid=process.pid,
        desktop_trace_directory=str(directory),
        desktop_log=str(log),
        phone_restarted=False,
    )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "--output",
        default=str(
            ROOT / "audit/evidence/passive-tracing-2026-10-31/current-runtime.json"
        ),
    )
    main(p.parse_args().output)
