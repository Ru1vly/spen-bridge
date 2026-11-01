"""Analyze bounded normal-app traces without inventing a cross-device clock."""

import argparse
import itertools
import json
import math
import struct
from collections import defaultdict
from pathlib import Path


def load(path):
    data = Path(path).read_bytes()
    if len(data) < 4:
        raise ValueError("Incomplete trace")
    size = struct.unpack_from(">I", data)[0]
    if not 0 < size <= 8192:
        raise ValueError("Invalid trace header")
    meta = json.loads(data[4 : 4 + size])
    payload = data[4 + size :]
    if (
        meta.get("version") != 1
        or meta.get("record_bytes") != 64
        or len(payload) != meta.get("records", -1) * 64
    ):
        raise ValueError("Incomplete or unsupported trace")
    return meta, list(struct.iter_unpack(">8q", payload))


def distribution(values):
    values = sorted(values)
    if not values:
        return {"samples": 0}
    return dict(
        samples=len(values),
        negative=sum(v < 0 for v in values),
        **{
            name: values[min(len(values) - 1, math.ceil(len(values) * q) - 1)] / 1000
            for name, q in [
                ("p50_us", 0.5),
                ("p95_us", 0.95),
                ("p99_us", 0.99),
                ("max_us", 1),
            ]
        },
    )


def analyze(phone_path, desktop_path):
    pm, pr = load(phone_path)
    hm, hr = load(desktop_path)
    if pm.get("side") != "android" or hm.get("side") != "desktop":
        raise ValueError("Wrong trace side")
    source = [r for r in pr if r[0] == 1]
    synthetic = [r for r in pr if r[0] == 7]
    tx = [r for r in pr if r[0] == 3]
    rx = [r for r in hr if r[0] in (4, 5)]
    # Packet sequence plus payload fingerprint and count identifies the same
    # wire record. Ambiguous/repeated keys are excluded, never silently paired.
    tx_by = defaultdict(list)
    rx_by = defaultdict(list)
    for r in tx:
        tx_by[(r[2], r[7], r[3])].append(r)
    for r in rx:
        rx_by[(r[2], r[7], r[3])].append(r)
    keys = [
        k for k in tx_by.keys() & rx_by.keys() if len(tx_by[k]) == len(rx_by[k]) == 1
    ]
    matched = [(tx_by[k][0], rx_by[k][0]) for k in keys]
    phone_ping = defaultdict(list)
    host_ping = defaultdict(list)
    for r in pr:
        if r[0] == 4:
            phone_ping[r[2]].append(r)
    for r in hr:
        if r[0] == 6:
            host_ping[r[2]].append(r)
    bounds = []
    rtt = []
    for key in phone_ping.keys() & host_ping.keys():
        if len(phone_ping[key]) == len(host_ping[key]) == 1:
            p, h = phone_ping[key][0], host_ping[key][0]
            lower = h[5] - p[6]
            upper = h[4] - p[4]
            bounds.append(
                {
                    "sequence": key,
                    "offset_lower_ns": lower,
                    "offset_upper_ns": upper,
                    "uncertainty_width_us": (upper - lower) / 1000,
                }
            )
            rtt.append(p[6] - p[4])
    source_times = sorted({r[4] for r in source})
    tx_start = sorted(r[5] for r in tx)
    rx_start = sorted(r[4] for r in rx)

    def rate(times, count):
        return (
            count * 1e9 / (max(times) - min(times))
            if len(times) > 1 and max(times) > min(times)
            else None
        )

    report = {
        "scope": "passive stage timings; cross-device one-way latency not directly measured",
        "phone_metadata": pm,
        "desktop_metadata": hm,
        "counts": {
            "real_source_records": len(source),
            "distinct_real_source_times": len(source_times),
            "synthetic_source_records": len(synthetic),
            "phone_packets": len(tx),
            "phone_sent_events": sum(r[3] for r in tx),
            "host_packets": len(rx),
            "host_events": sum(r[3] for r in rx),
            "matched_packets": len(matched),
            "ambiguous_keys": sum(len(v) > 1 for v in tx_by.values())
            + sum(len(v) > 1 for v in rx_by.values()),
            "host_failed_submissions": sum(r[0] == 5 for r in rx),
            "rejected_source_records": sum(r[3] for r in pr if r[0] == 8),
            "queue_resets": sum(r[0] == 9 for r in pr),
            "transport_error_states": sum(r[0] == 10 and r[2] == 3 for r in pr),
        },
        "rates": {
            "phone_packets_per_second": rate(tx_start, len(tx) - 1),
            "host_packets_per_second": rate(rx_start, len(rx) - 1),
        },
        "stages": {
            "android_source_to_callback": distribution([r[5] - r[4] for r in source]),
            "android_source_spacing": distribution(
                [b - a for a, b in itertools.pairwise(source_times)]
            ),
            "android_queue_to_write_start": distribution([r[5] - r[4] for r in tx]),
            "android_write_call": distribution([r[6] - r[5] for r in tx]),
            "host_decode_and_budget": distribution([r[5] - r[4] for r in rx]),
            "host_submission": distribution([r[6] - r[5] for r in rx]),
            "host_total": distribution([r[6] - r[4] for r in rx]),
            "heartbeat_round_trip": distribution(rtt),
        },
        "clock_bounds": bounds,
        "one_way_latency_claim": "Not certified: phone and desktop clocks differ; heartbeat bounds have uncertainty and may drift. Do not use RTT/2 as a measured one-way delay.",
        "loss_claim": "Not certified from capture-edge counts; packet keys can identify matching records but traces can start/stop at different times. Inspect overflow and session boundaries.",
        "trace_overflow": bool(pm.get("overflow") or hm.get("overflow")),
    }
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--android", required=True)
    p.add_argument("--desktop", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    r = analyze(args.android, args.desktop)
    Path(args.output).write_text(json.dumps(r, indent=2))
    print(json.dumps(r, indent=2))
