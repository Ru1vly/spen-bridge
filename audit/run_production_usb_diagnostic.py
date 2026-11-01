"""Real USB, production Kotlin sender + Python receiver; no UI restarts or OS input."""

import argparse
import asyncio
import json
import math
import os
import re
import secrets
import shutil
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import itertools

from adb_transport_metadata import parse_transport_metadata
from analyze_input_trace import analyze
from runtime_tools import adb_command

from server.input_trace import TraceController
from server.security import load_identity
from server.server import SPenServer

ADB = adb_command()
PACKAGE = "com.spenbridge.app"
EVIDENCE_ROOT = Path("audit/evidence/passive-tracing-2026-10-31")
OUT = EVIDENCE_ROOT


async def adb(*args, data=None, check=True):
    process = await asyncio.create_subprocess_exec(
        *ADB,
        *args,
        stdin=asyncio.subprocess.PIPE
        if data is not None
        else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(data), 15)
    except BaseException:
        process.kill()
        await process.wait()
        raise
    if check and process.returncode:
        raise RuntimeError(
            "ADB diagnostic operation failed: " + err.decode(errors="replace")
        )
    return out


async def broadcast(action, *extras):
    out = (
        await adb(
            "shell",
            "am",
            "broadcast",
            "--receiver-foreground",
            "-n",
            PACKAGE + "/.InputTraceReceiver",
            "-a",
            PACKAGE + "." + action,
            *extras,
        )
    ).decode()
    match = re.search(r'data="([^"\n]*)"', out) or re.search(r"data=([^\s,]+)", out)
    if not match:
        raise RuntimeError("No diagnostic receiver result: " + out)
    return match[1]


class Sink:
    def __init__(self):
        self.ids = []
        self.times = []

    def handle_event(self, event):
        self.ids.append(round(event.x * 20000))
        self.times.append(time.perf_counter_ns())

    def reset(self):
        pass

    def close(self):
        pass


async def until(predicate, seconds=3):
    limit = time.monotonic() + seconds
    while time.monotonic() < limit:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise RuntimeError("Diagnostic state did not converge")


def host_command(directory, action, **extra):
    request = dict(id=uuid.uuid4().hex, action=action, **extra)
    temporary = directory / "control-new.json"
    fd = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    with os.fdopen(fd, "w") as out:
        json.dump(request, out)
    temporary.replace(directory / "control.json")


def intervals(times):
    values = sorted((b - a) / 1000 for a, b in itertools.pairwise(times))
    return (
        {
            label: values[min(len(values) - 1, math.ceil(len(values) * q) - 1)]
            for label, q in [
                ("p50_us", 0.5),
                ("p95_us", 0.95),
                ("p99_us", 0.99),
                ("max_us", 1),
            ]
        }
        if values
        else {}
    )


async def run(rate, count, traced, label):
    folder = "cache/spen-production-diagnostic-" + secrets.token_hex(6)
    pid_before = (await adb("shell", "pidof", PACKAGE)).decode().strip()
    phone_capture = False
    remote = None
    server = None
    controller = None
    sink = Sink()
    with tempfile.TemporaryDirectory(prefix="spen-production-usb-") as temporary:
        directory = Path(temporary)
        identity = load_identity(directory / "identity")
        try:
            controller = TraceController(
                directory / "trace", backend_name="in-memory diagnostic sink"
            )
            server = SPenServer(
                sink,
                port=0,
                tls_context=identity.server_context(),
                pairing_code=identity.pairing_code,
            )
            server.input_trace = controller
            await server.start()
            remote = int(
                (await adb("reverse", "tcp:0", f"tcp:{server.bound_endpoint[1]}"))
                .decode()
                .strip()
            )
            await adb("shell", f"run-as {PACKAGE} mkdir -m 700 {folder}")
            config = json.dumps(
                {
                    "port": remote,
                    "fingerprint": identity.fingerprint,
                    "code": identity.pairing_code,
                    "rate": rate,
                    "packets": count,
                }
            ).encode()
            await adb(
                "shell",
                "-T",
                f"run-as {PACKAGE} sh -c 'umask 077; cat > {folder}/config.json'",
                data=config,
            )
            copied = await adb(
                "exec-out", "run-as", PACKAGE, "cat", folder + "/config.json"
            )
            if json.loads(copied) != json.loads(config):
                raise RuntimeError("Private diagnostic config transfer did not match")
            print(
                json.dumps(
                    {
                        "config_transfer_verified": True,
                        "config_bytes": len(copied),
                        "label": label,
                    }
                ),
                flush=True,
            )
            if traced:
                host_command(directory / "trace", "start", seconds=30)
                await until(lambda: controller.enabled)
                status = await broadcast("TRACE_START", "--ei", "seconds", "30")
                if not status.startswith("recording:"):
                    raise RuntimeError("Phone trace not started: " + status)
                phone_capture = True
            status = await broadcast(
                "SYNTHETIC_START",
                "--es",
                "config",
                f"/data/user/0/{PACKAGE}/{folder}/config.json",
            )
            if status not in ("running",) and not status.startswith("complete:"):
                raise RuntimeError("Synthetic sender not started: " + status)
            await asyncio.sleep(count / rate + 2)
            status = await broadcast("SYNTHETIC_STATUS")
            if not status.startswith("complete:"):
                raise RuntimeError("Synthetic source failed: " + status)
            result = {
                "label": label,
                "target_packets_per_second": rate,
                "offered": count,
                "received": len(sink.ids),
                "unique_received": len(set(sink.ids)),
                "ordered": sink.ids == sorted(sink.ids),
                "complete": sink.ids == list(range(count)),
                "host_received_packets_per_second": (len(sink.ids) - 1)
                * 1e9
                / (sink.times[-1] - sink.times[0])
                if len(sink.times) > 1
                else None,
                "host_report_spacing": intervals(sink.times),
                "traced": traced,
                "no_desktop_input": True,
                "phone_pid_before": pid_before,
                "phone_pid_after": (await adb("shell", "pidof", PACKAGE))
                .decode()
                .strip(),
            }
            result["android_process_restarted"] = (
                result["phone_pid_before"] != result["phone_pid_after"]
            )
            if traced:
                await broadcast("TRACE_STOP")
                phone_capture = False
                host_command(directory / "trace", "stop")
                phone_status = ""
                for _ in range(30):
                    phone_status = await broadcast("TRACE_STATUS")
                    if phone_status.startswith("ready:"):
                        break
                    if phone_status.startswith("error:"):
                        raise RuntimeError(phone_status)
                    await asyncio.sleep(0.2)
                if not phone_status.startswith("ready:"):
                    raise RuntimeError("Phone export did not complete")
                name = phone_status.partition(":")[2]
                if not re.fullmatch(r"input-trace-[0-9]+\.bin", name):
                    raise RuntimeError("Invalid phone trace name")
                phone_file = OUT / (label + "-android.bin")
                phone_file.write_bytes(
                    await adb("exec-out", "run-as", PACKAGE, "cat", "files/" + name)
                )
                phone_file.chmod(0o600)
                await until(lambda: controller.status["state"] == "ready")
                desktop_file = OUT / (label + "-desktop.bin")
                shutil.copyfile(
                    directory / "trace" / controller.status["file"], desktop_file
                )
                desktop_file.chmod(0o600)
                analysis = analyze(phone_file, desktop_file)
                (OUT / (label + "-analysis.json")).write_text(
                    json.dumps(analysis, indent=2)
                )
                result["stages"] = analysis["stages"]
                result["trace_overflow"] = analysis["trace_overflow"]
                result["trace_counts"] = analysis["counts"]
                result["clock_bounds"] = analysis["clock_bounds"]
            return result
        finally:
            if phone_capture:
                await broadcast("TRACE_STOP")
            await adb("shell", f"run-as {PACKAGE} rm -rf {folder}", check=False)
            if remote is not None:
                await adb("reverse", "--remove", f"tcp:{remote}", check=False)
            if server:
                await server.stop()
            if controller:
                controller.close()


async def main(output=None):
    global OUT
    if not (await adb("shell", "pidof", PACKAGE)).strip():
        raise RuntimeError(
            "Open the normal app first; this tool does not launch or restart it"
        )
    OUT = (
        Path(output)
        if output is not None
        else EVIDENCE_ROOT
        / (
            "usb-run-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")
            + secrets.token_hex(4)
        )
    )
    if OUT.exists() and any(OUT.iterdir()):
        raise ValueError(
            "Use a new or empty output directory; previous trial evidence is preserved"
        )
    OUT.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"output_directory": str(OUT)}), flush=True)
    status, host_features, route_features = await asyncio.gather(
        adb("server-status", check=False),
        adb("host-features", check=False),
        adb("features", check=False),
    )
    transport_configuration = parse_transport_metadata(
        status.decode(errors="replace"),
        host_features.decode(errors="replace"),
        route_features.decode(errors="replace"),
    )
    rows = []
    for rate, count, traced, label in [
        (1000, 5000, False, "usb-1000-untraced"),
        (1000, 5000, True, "usb-1000-traced"),
        (3000, 9000, True, "usb-3000-traced"),
    ]:
        row = await run(rate, count, traced, label)
        rows.append(row)
        (OUT / "production-usb-results.json").write_text(
            json.dumps(
                {
                    "scope": "production Kotlin PenTransport/SocketProtocolLink through real USB/ADB to production Python receiver and isolated in-memory sink; synthetic source, excludes physical sensor and OS injection",
                    "transport_configuration": transport_configuration,
                    "rows": rows,
                },
                indent=2,
            )
        )
        print(json.dumps(row), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="New or empty trial directory; defaults to a unique run folder",
    )
    asyncio.run(main(parser.parse_args().output))
