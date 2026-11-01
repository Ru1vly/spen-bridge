"""Install/run debug helper tests ONLY on a verified local Android emulator.

Instrumentation restarts its target. This runner refuses physical devices.
USB is simulated; receiver is an isolated in-memory sink, never OS injection.
"""

import argparse
import asyncio
import json
import re
import secrets
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime_tools import adb_path
from summarize_android_trace import summarize

from server.security import load_identity
from server.server import SPenServer

PACKAGE = "com.spenbridge.app"


class Sink:
    def __init__(self):
        self.events = []

    def handle_event(self, event):
        self.events.append(event)

    def reset(self):
        pass


async def main(args):
    if not args.serial.startswith("emulator-"):
        raise ValueError("Refusing instrumentation on a physical device")
    adb = [adb_path(), "-s", args.serial]

    async def command(*values, data=None, timeout=30, check=True):
        process = await asyncio.create_subprocess_exec(
            *adb,
            *values,
            stdin=asyncio.subprocess.PIPE
            if data is not None
            else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(process.communicate(data), timeout)
        except BaseException:
            process.kill()
            await process.wait()
            raise
        if check and process.returncode:
            raise RuntimeError(
                "Emulator ADB operation failed: " + err.decode(errors="replace")
            )
        return out

    hardware = (await command("shell", "getprop", "ro.hardware")).decode().strip()
    qemu = (await command("shell", "getprop", "ro.kernel.qemu")).decode().strip()
    if hardware not in ("ranchu", "goldfish") or qemu != "1":
        raise ValueError("Target is not a verified emulator")
    if (await command("shell", "getprop", "sys.boot_completed")).strip() != b"1":
        raise RuntimeError("Emulator has not finished booting")
    await command(
        "install",
        "-r",
        str(ROOT / "android/app/build/outputs/apk/debug/app-debug.apk"),
        timeout=120,
    )
    sink = Sink()
    route = None
    trace_files = []
    config = "cache/accessory-selftest-" + secrets.token_hex(8) + ".json"
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="spen-accessory-tls-") as directory:
        identity = load_identity(directory)
        server = SPenServer(
            sink,
            port=0,
            tls_context=identity.server_context(),
            pairing_code=identity.pairing_code,
        )
        await server.start()
        try:
            route = (
                (await command("reverse", "tcp:0", f"tcp:{server.bound_endpoint[1]}"))
                .decode()
                .strip()
            )
            if not route.isdigit() or not 1 <= int(route) <= 65535:
                raise RuntimeError("Invalid allocated reverse route")
            data = json.dumps(
                dict(
                    port=int(route),
                    fingerprint=identity.fingerprint,
                    code=identity.pairing_code,
                    trace=args.trace,
                )
            ).encode()
            # shell -T reliably preserves stdin here; exec-in previously produced
            # empty files on this host. Verify transfer without printing secrets.
            await command(
                "shell",
                "-T",
                f"run-as {PACKAGE} sh -c 'umask 077; cat > {config}'",
                data=data,
            )
            received = await command("exec-out", "run-as", PACKAGE, "cat", config)
            if json.loads(received) != json.loads(data):
                raise RuntimeError("Private test config transfer failed")
            raw = await command(
                "shell",
                "am",
                "instrument",
                "-w",
                "-e",
                "config",
                f"/data/user/0/{PACKAGE}/{config}",
                PACKAGE + "/.AccessoryDiagnosticInstrumentation",
                timeout=90,
            )
            log = raw.decode(errors="replace")
            output.with_suffix(".instrumentation.txt").write_text(log)
            line = next(
                (
                    line.partition("diagnostics=")[2]
                    for line in log.splitlines()
                    if line.startswith("INSTRUMENTATION_RESULT: diagnostics=")
                ),
                None,
            )
            if line is None:
                raise RuntimeError(
                    "Accessory emulator self-test failed; inspect instrumentation log"
                )
            result = json.loads(line)
            ids = [round(event.x * 20000) for event in sink.events]
            if (
                not ids
                or ids[0] != 10000
                or any(a >= b for a, b in zip(ids[1:], ids[2:]))
            ):
                raise RuntimeError("Synthetic TLS records were duplicated or reordered")
            for trial in result["synthetic_capacity"]:
                low, high = (0, 2000) if trial["rate_target"] == 1000 else (2000, 8000)
                received_count = sum(low <= index < high for index in ids[1:])
                trial["host_received"] = received_count
                trial["all_events_received"] = received_count == trial["offered"]
                trial["missing_at_host"] = trial["offered"] - received_count
                trace_name = trial.get("trace_file")
                if trace_name:
                    if not re.fullmatch(r"input-trace-[0-9]+\.bin", trace_name):
                        raise ValueError("Invalid exported trace filename")
                    trace_files.append("files/" + trace_name)
                    trace_data = await command(
                        "exec-out", "run-as", PACKAGE, "cat", "files/" + trace_name
                    )
                    trace_output = output.with_name(
                        output.stem + f"-{trial['rate_target']}-android.bin"
                    )
                    trace_output.write_bytes(trace_data)
                    trace_output.chmod(0o600)
                    trial["android_trace_summary"] = summarize(trace_output)

            result["complete_delivery"] = all(
                t["all_packets_written"] and t["all_events_received"]
                for t in result["synthetic_capacity"]
            )
            result.update(
                serial=args.serial,
                hardware=hardware,
                host_received_synthetic_records=len(sink.events),
                receiver="isolated in-memory sink",
                physical_usb_tested=False,
                phone_modified=False,
            )
            output.write_text(json.dumps(result, indent=2))
            print(json.dumps(result, indent=2))
        finally:
            cleanup = [
                command("shell", "run-as", PACKAGE, "rm", "-f", config, check=False),
                server.stop(),
            ]
            for trace_file in trace_files:
                cleanup.append(
                    command(
                        "shell", "run-as", PACKAGE, "rm", "-f", trace_file, check=False
                    )
                )
            if route and route.isdigit():
                cleanup.append(
                    command("reverse", "--remove", "tcp:" + route, check=False)
                )
            await asyncio.gather(*cleanup, return_exceptions=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default="emulator-5556")
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Capture bounded per-stage sender traces; adds measurement overhead",
    )
    parser.add_argument(
        "--output",
        default=str(
            ROOT
            / "audit/evidence/passive-tracing-2026-10-31/android-accessory-emulator.json"
        ),
    )
    asyncio.run(main(parser.parse_args()))
