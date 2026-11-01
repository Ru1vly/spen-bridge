"""Tiny offline fixtures; no devices, subprocesses or performance workload."""

import json
import struct
import tempfile
import unittest
from pathlib import Path

from audit.summarize_android_trace import summarize


class AndroidTraceSummaryTests(unittest.TestCase):
    def trace(self, folder, rows, **extra):
        meta = dict(
            version=1, side="android", record_bytes=64, records=len(rows), overflow=0
        )
        meta.update(extra)
        header = json.dumps(meta).encode()
        file = Path(folder) / "trace.bin"
        file.write_bytes(
            struct.pack(">I", len(header))
            + header
            + b"".join(struct.pack(">8q", *r) for r in rows)
        )
        return file

    def test_resets_and_sender_stages_are_reported_separately(self):
        records = [
            (7, 0, 0, 1, 100, 100, 0, 0),
            (2, 5, -1, 4, 100, 0, 0, 0),
            (3, 5, 0, 1, 100, 200, 300, 55),
            (3, 5, 1, 3, 100, 600, 900, 56),
            (9, 5, 1, 1, 950, 0, 0, 0),
            (9, 6, 2, -1, 1000, 0, 0, 0),
            (10, 6, 3, 0, 1000, 0, 0, 0),
        ]
        with tempfile.TemporaryDirectory() as folder:
            result = summarize(self.trace(folder, records))
        self.assertEqual(result["counts"]["queued_events"], 4)
        self.assertEqual(result["counts"]["events_written"], 4)
        self.assertEqual(result["counts"]["event_packets_written"], 2)
        self.assertEqual(result["counts"]["synthetic_source_records"], 1)
        self.assertEqual(result["reset_reason_counts"], {"1": 1, "2": 1})
        self.assertEqual(result["stages"]["queue_to_write_start"]["p99_us"], 0.5)
        self.assertEqual(result["stages"]["write_call"]["p99_us"], 0.3)
        self.assertFalse(result["trace_overflow"])

    def test_overflow_is_not_hidden_and_reset_output_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            result = summarize(
                self.trace(folder, [(9, 1, 1, 1, 100, 0, 0, 0)] * 20, overflow=5)
            )
        self.assertTrue(result["trace_overflow"])
        self.assertEqual(len(result["first_reset_records"]), 16)
        self.assertEqual(result["omitted_reset_records"], 4)

    def test_incomplete_trailing_and_unbounded_traces_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            file = self.trace(folder, [])
            file.write_bytes(file.read_bytes() + b"x")
            with self.assertRaises(ValueError):
                summarize(file)
            file = self.trace(folder, [(3, 0, 0, 1, 100, 200, 300, 0)])
            file.write_bytes(file.read_bytes()[:-1])
            with self.assertRaises(ValueError):
                summarize(file)
            file.write_bytes(struct.pack(">I", 100) + b"{}")
            with self.assertRaises(ValueError):
                summarize(file)
            for extra in [dict(records=200001), dict(overflow=-1), dict(records=True)]:
                with self.assertRaises(ValueError):
                    summarize(self.trace(folder, [], **extra))
