"""Capture normal pen input passively, with no installs or process restarts."""

import argparse
import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path

from analyze_input_trace import analyze
from runtime_tools import adb_command

ADB = adb_command()
PACKAGE = "com.spenbridge.app"


async def adb(*args):
    process = await asyncio.create_subprocess_exec(
        *ADB, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), 15)
    except BaseException:
        process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise RuntimeError(
            "ADB capture operation failed: " + err.decode(errors="replace")
        )
    return out


async def command(action, *extras):
    text = (
        await adb(
            "shell",
            "am",
            "broadcast",
            "--receiver-foreground",
            "-n",
            PACKAGE + "/.InputTraceReceiver",
            "-a",
            PACKAGE + ".TRACE_" + action,
            *extras,
        )
    ).decode()
    match = re.search(r'data="([^"\n]*)"', text)
    if match is None:
        raise RuntimeError("No trace receiver result")
    return match[1]


def desktop_request(directory, action, **extra):
    token = uuid.uuid4().hex
    temporary = directory / "control-new.json"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(dict(id=token, action=action, **extra), out)
    temporary.replace(directory / "control.json")
    return token


async def wait_for(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        await asyncio.sleep(0.1)
    raise RuntimeError("Trace state did not converge")


async def main(args):
    deployment = json.loads(Path(args.deployment).read_text())
    directory = Path(deployment["desktop_trace_directory"])
    # Status files can survive a reboot. Require a live matching app process.
    process = Path("/proc") / str(deployment["desktop_pid"])
    try:
        command_line = (process / "cmdline").read_bytes().split(b"\0")
    except FileNotFoundError:
        raise RuntimeError(
            "The recorded desktop process has exited; start the current app before capture"
        ) from None
    if (
        len(command_line) < 3
        or b"--gui" not in command_line
        or Path(os.fsdecode(command_line[1])).name != "main.py"
    ):
        raise RuntimeError("Recorded PID does not identify the desktop app")

    before = (await adb("shell", "pidof", PACKAGE)).decode().strip()
    if not before:
        raise RuntimeError(
            "Open the normal phone app first; capture does not launch it"
        )
    current = await command("STATUS")
    if current.startswith(("recording:", "exporting:")):
        raise RuntimeError("A phone trace is already active")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    desktop_started = phone_started = False
    try:
        token = desktop_request(directory, "start", seconds=args.seconds)
        desktop_started = True
        await wait_for(
            lambda: (
                json.loads((directory / "status.json").read_text()).get("id") == token
            )
        )
        status = await command("START", "--ei", "seconds", str(args.seconds))
        if not status.startswith("recording:"):
            raise RuntimeError("Phone trace did not start: " + status)
        phone_started = True
        print(
            json.dumps(
                dict(capture_ready=True, seconds=args.seconds, process_restart=False)
            ),
            flush=True,
        )
        await asyncio.sleep(args.seconds + 1)
        await command("STOP")
        phone_started = False
        desktop_request(directory, "stop")
        for _ in range(30):
            status = await command("STATUS")
            if status.startswith("ready:"):
                break
            if status.startswith("error:"):
                raise RuntimeError(status)
            await asyncio.sleep(0.2)
        if not status.startswith("ready:"):
            raise RuntimeError("Phone export did not finish")
        name = status.partition(":")[2]
        if not re.fullmatch(r"input-trace-[0-9]+\.bin", name):
            raise RuntimeError("Unexpected trace name")
        phone_file = out / "android.bin"
        phone_file.write_bytes(
            await adb("exec-out", "run-as", PACKAGE, "cat", "files/" + name)
        )
        phone_file.chmod(0o600)
        host_status = await wait_for(
            lambda: (
                s
                if (s := json.loads((directory / "status.json").read_text())).get(
                    "state"
                )
                == "ready"
                else None
            )
        )
        desktop_started = False
        host_file = out / "desktop.bin"
        host_file.write_bytes((directory / host_status["file"]).read_bytes())
        host_file.chmod(0o600)
        report = analyze(phone_file, host_file)
        after = (await adb("shell", "pidof", PACKAGE)).decode().strip()
        report["phone_process_preserved"] = before == after
        report["synthetic_input_generated"] = False
        (out / "analysis.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    finally:
        if phone_started:
            await command("STOP")
        if desktop_started:
            desktop_request(directory, "stop")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, choices=range(1, 61), default=30)
    parser.add_argument(
        "--deployment",
        default="audit/evidence/passive-tracing-2026-10-31/current-runtime.json",
    )
    parser.add_argument("--output", required=True)
    asyncio.run(main(parser.parse_args()))
