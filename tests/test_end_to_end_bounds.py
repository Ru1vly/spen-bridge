"""Synthetic causal-clock and source-matching checks; no device/process work."""

import json
import struct
import tempfile
import unittest
from pathlib import Path

from audit.end_to_end_bounds import affine_polygon, analyze, envelope, statistics


class EndToEndBoundsTests(unittest.TestCase):
    def test_affine_feasible_polygon_contains_known_clock(self):
        lower = [(x, 1000 + 8 * x - gap) for x, gap in [(0, 100), (1, 300), (2, 50)]]
        upper = [(x, 1000 + 8 * x + gap) for x, gap in [(0, 20), (1, 60), (2, 10)]]
        polygon, _ = affine_polygon(lower, upper)
        for x in [0, 0.4, 1.7, 2]:
            offsets = [b + d * x for d, b in polygon]
            self.assertLessEqual(min(offsets), 1000 + 8 * x + 1e-6)
            self.assertGreaterEqual(max(offsets), 1000 + 8 * x - 1e-6)
        for d, b in polygon:
            self.assertTrue(all(b + d * x >= y - 1e-6 for x, y in lower))
            self.assertTrue(all(b + d * x <= y + 1e-6 for x, y in upper))

    def test_inconsistent_clock_constraints_are_rejected(self):
        with self.assertRaises(ValueError):
            affine_polygon([(0, 100), (1, 100)], [(0, 50), (1, 50)])

    def test_variable_drift_envelopes_contain_known_clock(self):
        lower = [(x, 1000 + 50 * x - 10) for x in [0, 1, 2]]
        upper = [(x, 1000 + 50 * x + 20) for x in [0, 0.5, 1.5, 2]]
        low, high = envelope(lower, 100, False), envelope(upper, 100, True)
        for x in [-0.1, 0.25, 1.2, 2.1]:
            self.assertLessEqual(low(x), 1000 + 50 * x)
            self.assertGreaterEqual(high(x), 1000 + 50 * x)

    def test_quantile_bounds_do_not_add_stage_percentiles(self):
        result = statistics([30, 10, 20], [50, 30, 40], [40, 20, 30])
        self.assertEqual(result["median"]["lower_ms"], 0.02)
        self.assertEqual(result["median"]["upper_ms"], 0.04)

    def fixture(self, folder, bad_count=False):
        p0, offset = 1_000_000_000, 1_000_000
        phone, host = [], []
        for i in range(3):
            s = p0 + (i + 1) * 100_000_000
            phone += [
                (1, 1, 0, 1, s, s + 10000, 0, 0),
                (2, 1, -1, 2 if bad_count and i == 0 else 1, s + 25000, 0, 0, 0),
                (3, 1, i, 1, s + 20000, s + 30000, s + 40000, 100 + i),
            ]
            host += [
                (
                    4,
                    77,
                    i,
                    1,
                    s + offset + 40000,
                    s + offset + 45000,
                    s + offset + 50000,
                    100 + i,
                )
            ]
        for i in range(3):
            p = p0 + i * 1_000_000_000
            phone += [(4, 1, 10 + i, 0, p, p + 1000, p + 12000, 0)]
            host += [
                (
                    6,
                    77,
                    10 + i,
                    0,
                    p + offset + 5000,
                    p + offset + 6000,
                    p + offset + 7000,
                    0,
                )
            ]
        paths = []
        for side, rows, base in [
            ("android", phone, p0),
            ("desktop", host, p0 + offset),
        ]:
            meta = dict(
                version=1,
                side=side,
                record_bytes=64,
                records=len(rows),
                overflow=0,
                started_ns=base - 1000,
                ended_ns=base + 3_000_000_000,
            )
            header = json.dumps(meta).encode()
            path = Path(folder) / (side + ".bin")
            path.write_bytes(
                struct.pack(">I", len(header))
                + header
                + b"".join(struct.pack(">8q", *r) for r in rows)
            )
            paths.append(path)
        return paths

    def test_complete_path_contains_known_fifty_microsecond_latency(self):
        with tempfile.TemporaryDirectory() as folder:
            result = analyze(*self.fixture(folder))
        self.assertEqual(result["matched_packets"], 3)
        self.assertEqual(result["single_event_packets"], 3)
        summary = result["single_sample_submission"]["median"]
        self.assertLessEqual(summary["lower_ms"], 0.05)
        self.assertGreaterEqual(summary["upper_ms"], 0.05)

    def test_mismatched_source_queue_group_is_not_guessed(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                analyze(*self.fixture(folder, bad_count=True))
