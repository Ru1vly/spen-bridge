"""Packet matching must reject ambiguity and keep same-clock stage meanings."""

import importlib.util
import json
import struct
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "input_trace_analysis",
    Path(__file__).resolve().parents[1] / "audit/analyze_input_trace.py",
)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def trace(path, side, records, overflow=0):
    header = json.dumps(
        {
            "version": 1,
            "side": side,
            "record_bytes": 64,
            "records": len(records),
            "overflow": overflow,
        }
    ).encode()
    path.write_bytes(
        struct.pack(">I", len(header))
        + header
        + b"".join(struct.pack(">8q", *r) for r in records)
    )


def test_matching_keeps_cross_device_delay_unclaimed(tmp_path):
    phone = tmp_path / "phone"
    host = tmp_path / "host"
    trace(
        phone,
        "android",
        [
            (1, 1, 0, 1, 1000, 2000, 0, 0),
            (3, 1, 42, 1, 3000, 4000, 5000, 123),
            (4, 1, 40, 0, 1000, 1200, 6000, 0),
        ],
    )
    trace(
        host,
        "desktop",
        [
            (4, 5, 42, 1, 100000, 100100, 100200, 123),
            (6, 5, 40, 0, 98000, 98100, 98200, 0),
        ],
    )
    report = analysis.analyze(phone, host)
    assert report["counts"]["matched_packets"] == 1
    assert report["stages"]["android_source_to_callback"]["p50_us"] == 1
    assert report["stages"]["android_queue_to_write_start"]["p50_us"] == 1
    assert report["stages"]["host_total"]["p50_us"] == 0.2
    assert report["clock_bounds"][0]["offset_lower_ns"] == 92100
    assert report["clock_bounds"][0]["offset_upper_ns"] == 97000
    assert "Not certified" in report["one_way_latency_claim"]


def test_duplicate_packet_identity_is_not_arbitrarily_paired(tmp_path):
    phone = tmp_path / "phone"
    host = tmp_path / "host"
    record = (3, 1, 42, 1, 3000, 4000, 5000, 123)
    trace(phone, "android", [record, record], overflow=1)
    trace(host, "desktop", [(4, 5, 42, 1, 100000, 100100, 100200, 123)])
    report = analysis.analyze(phone, host)
    assert report["counts"]["matched_packets"] == 0
    assert report["counts"]["ambiguous_keys"] == 1
    assert report["trace_overflow"]
