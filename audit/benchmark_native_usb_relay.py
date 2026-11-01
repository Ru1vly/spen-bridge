"""Host-only paired TLS benchmark. The USB connection is a socket fixture."""

import asyncio
import json
import math
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server.protocol import (
    ACTION_HOVER_MOVE,
    HEADER_SIZE,
    PKT_HANDSHAKE,
    PKT_PING,
    PKT_PONG,
    PenEvent,
    pack_events,
    pack_packet,
    unpack_header,
)
from server.security import auth_proof, load_identity
from server.server import SPenServer


class Sink:
    def __init__(self):
        self.received = []

    def handle_event(self, event):
        self.received.append((round(event.x * 20000), time.perf_counter_ns()))

    def reset(self):
        pass


def distribution(values):
    values = sorted(values)
    return {
        key: values[min(len(values) - 1, math.ceil(len(values) * q) - 1)] / 1000
        for key, q in [
            ("p50_us", 0.5),
            ("p95_us", 0.95),
            ("p99_us", 0.99),
            ("max_us", 1),
        ]
    }


def exact(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.recv(size - len(data))
        if not chunk:
            raise EOFError("Receiver disconnected")
        data.extend(chunk)
    return bytes(data)


def packet(stream):
    kind, seq, size = unpack_header(exact(stream, HEADER_SIZE))
    return kind, seq, exact(stream, size)


def client(raw, identity, rate, count):
    raw.settimeout(3)
    sent, writes = [], []
    warmup = 200
    frames = [
        pack_events([PenEvent(ACTION_HOVER_MOVE, 0, 0, i / 20000, 0.5, 0)], i)
        for i in range(count + warmup)
    ]
    with identity.client_context().wrap_socket(
        raw, server_hostname="localhost"
    ) as stream:
        _, _, challenge = packet(stream)
        nonce = challenge[4:]
        stream.sendall(
            pack_packet(
                PKT_HANDSHAKE, 0, auth_proof(identity.pairing_code, nonce, "client")
            )
        )
        if packet(stream) != (
            PKT_HANDSHAKE,
            0,
            auth_proof(identity.pairing_code, nonce, "server"),
        ):
            raise ValueError("Pairing failed")
        start = time.perf_counter_ns()
        for i, frame in enumerate(frames):
            delay = (start + i * 1e9 / rate - time.perf_counter_ns()) / 1e9
            if delay > 0:
                time.sleep(delay)
            before = time.perf_counter_ns()
            stream.sendall(frame)
            sent.append(before)
            writes.append(time.perf_counter_ns() - before)
        stream.sendall(pack_packet(PKT_PING, 65535, b""))
        if packet(stream) != (PKT_PONG, 65535, b""):
            raise ValueError("Final acknowledgement failed")
    return sent, writes, warmup


async def trial(binary, identity, rate, relay_enabled):
    count = rate * 2
    sink = Sink()
    server = SPenServer(
        sink,
        port=0,
        tls_context=identity.server_context(),
        pairing_code=identity.pairing_code,
    )
    await server.start()
    relay = None
    raw = None
    try:
        host = socket.create_connection(server.bound_endpoint)
        if relay_enabled:
            usb, raw = socket.socketpair()
            relay = subprocess.Popen(
                [str(binary), str(host.fileno()), str(usb.fileno()), "0", "15"],
                pass_fds=(host.fileno(), usb.fileno()),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            usb.close()
            host.close()
        else:
            raw = host
        sent, writes, warmup = await asyncio.to_thread(
            client, raw, identity, rate, count
        )
        if [index for index, _ in sink.received] != list(range(count + warmup)):
            raise ValueError("Missing, duplicated or reordered input")
        received = [stamp for _, stamp in sink.received][warmup:]
        sent = sent[warmup:]
        result = dict(
            rate=rate,
            native_relay=relay_enabled,
            offered=count,
            received=len(received),
            sender_packets_per_second=(count - 1) * 1e9 / (sent[-1] - sent[0]),
            host_tls_write_to_sink=distribution(
                [b - a for a, b in zip(sent, received)]
            ),
            tls_write_call=distribution(writes[warmup:]),
        )
        if relay:
            out, err = await asyncio.to_thread(relay.communicate, timeout=2)
            if err:
                raise RuntimeError("Native relay diagnostic error")
            result["relay"] = json.loads(out)
        return result
    finally:
        if raw:
            raw.close()
        if relay and relay.poll() is None:
            relay.kill()
            await asyncio.to_thread(relay.communicate)
        await server.stop()


async def main(output):
    with tempfile.TemporaryDirectory(prefix="spen-native-relay-") as folder:
        binary = Path(folder) / "relay-fixture"
        subprocess.run(
            [
                "cc",
                "-std=c11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pthread",
                "-I",
                str(ROOT / "native/usb-relay"),
                str(ROOT / "native/usb-relay/relay.c"),
                str(ROOT / "tests/native/usb_relay_fixture.c"),
                "-o",
                str(binary),
            ],
            check=True,
        )
        identity = load_identity(Path(folder) / "identity")
        runs = []
        for rate in (1000, 3000):
            for order in ((False, True), (True, False)):
                for enabled in order:
                    runs.append(await trial(binary, identity, rate, enabled))
        summary = {}
        for rate in (1000, 3000):
            for enabled in (False, True):
                subset = [
                    r
                    for r in runs
                    if r["rate"] == rate and r["native_relay"] == enabled
                ]
                summary[f"{rate}-" + ("relay" if enabled else "direct")] = {
                    key: statistics.median(
                        r["host_tls_write_to_sink"][key] for r in subset
                    )
                    for key in subset[0]["host_tls_write_to_sink"]
                }
        report = dict(
            scope="Host-only synthetic TLS source -> native relay/socket-backed USB fixture -> "
            "loopback TLS receiver/in-memory sink. Same monotonic clock. No Android, "
            "physical USB, real pen or OS injection. Two AB/BA repetitions; no hard latency guarantee.",
            runs=runs,
            median_of_runs=summary,
        )
        Path(output).write_text(json.dumps(report, indent=2))
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    asyncio.run(main(parser.parse_args().output))
