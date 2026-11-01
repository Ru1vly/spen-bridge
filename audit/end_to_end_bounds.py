"""Causal clock calibration for matched Android -> Linux submission latency.

The affine-clock result is conditional on a linear relative clock over the
capture. Variable-rate sensitivity results state their drift caps explicitly.
No equal forward/reverse delay assumption and no addition of stage percentiles.
"""

import argparse
import hashlib
import json
import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from pathlib import Path

if __package__:
    from .analyze_input_trace import load
else:
    from analyze_input_trace import load


def unique(rows, key):
    buckets = defaultdict(list)
    for row in rows:
        buckets[key(row)].append(row)
    return {k: values[0] for k, values in buckets.items() if len(values) == 1}


def clip(polygon, a, b, c):
    result = []
    for p, q in zip(polygon, polygon[1:] + polygon[:1]):
        fp = a * p[0] + b * p[1] - c
        fq = a * q[0] + b * q[1] - c
        if fp <= 1e-7:
            result.append(p)
        if (fp < 0 < fq) or (fq < 0 < fp):
            t = fp / (fp - fq)
            result.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return result


def affine_polygon(lower, upper):
    # b + d*x: b in microseconds, x in seconds, d in ppm.
    dlo, dhi = -math.inf, math.inf
    for y, lo in lower:
        for x, hi in upper:
            dx = x - y
            if dx > 0:
                dhi = min(dhi, (hi - lo) / dx)
            elif dx < 0:
                dlo = max(dlo, (hi - lo) / dx)
            elif lo > hi:
                raise ValueError("Causal clock constraints inconsistent")
    if not math.isfinite(dlo + dhi) or dlo > dhi:
        raise ValueError("Affine clock rate not bounded or inconsistent")
    bottom = min(lower[0][1] - lower[0][0] * d for d in (dlo, dhi))
    top = max(upper[0][1] - upper[0][0] * d for d in (dlo, dhi))
    polygon = [(dlo, bottom), (dhi, bottom), (dhi, top), (dlo, top)]
    for x, hi in upper:
        polygon = clip(polygon, x, 1, hi)
    for y, lo in lower:
        polygon = clip(polygon, -y, -1, -lo)
    if not polygon:
        raise ValueError("No feasible affine clock")
    d = (dlo + dhi) / 2
    b = (max(lo - y * d for y, lo in lower) + min(hi - x * d for x, hi in upper)) / 2
    return polygon, (d, b)


def envelope(points, drift_ppm, upper):
    points = sorted(points)
    xs = [x for x, _ in points]
    choose = min if upper else max
    initial = math.inf if upper else -math.inf
    sign = -1 if upper else 1
    prefix, suffix = [], [0] * len(points)
    acc = initial
    for x, y in points:
        acc = choose(acc, y + sign * drift_ppm * x)
        prefix.append(acc)
    acc = initial
    for i in range(len(points) - 1, -1, -1):
        x, y = points[i]
        acc = choose(acc, y - sign * drift_ppm * x)
        suffix[i] = acc

    def at(x):
        i = bisect_right(xs, x)
        values = []
        if i:
            values.append(prefix[i - 1] - sign * drift_ppm * x)
        if i < len(xs):
            values.append(suffix[i] + sign * drift_ppm * x)
        return choose(values)

    return at


def statistics(lower, upper, point=None):
    if not lower:
        return dict(samples=0)
    lower, upper = sorted(lower), sorted(upper)
    point = sorted(point) if point is not None else None
    result = dict(samples=len(lower), minimum_lower_bound_ms=lower[0] / 1000)
    for name, q in [("median", 0.5), ("p95", 0.95), ("p99", 0.99), ("maximum", 1)]:
        i = min(len(lower) - 1, math.ceil(len(lower) * q) - 1)
        value = dict(lower_ms=lower[i] / 1000, upper_ms=upper[i] / 1000)
        if point is not None:
            value["midpoint_model_estimate_ms"] = point[i] / 1000
        result[name] = value
    return result


def analyze(android, desktop):
    pm, pr = load(android)
    hm, hr = load(desktop)
    if pm.get("side") != "android" or hm.get("side") != "desktop":
        raise ValueError("Wrong trace side")
    if any(r[0] == 9 for r in pr):
        raise ValueError("Segment queue resets before source/queue ordinal association")
    if pm.get("overflow") or hm.get("overflow"):
        raise ValueError("Overflow invalidates source/queue ordinal association")
    tx = unique([r for r in pr if r[0] == 3], lambda r: (r[2], r[7], r[3]))
    rx = unique([r for r in hr if r[0] == 4], lambda r: (r[2], r[7], r[3]))
    keys = tx.keys() & rx.keys()
    if len({tx[k][1] for k in keys}) != 1 or len({rx[k][1] for k in keys}) != 1:
        raise ValueError("Analyze one authenticated connection/generation at a time")
    generation = next(iter({tx[k][1] for k in keys}))
    host_session = next(iter({rx[k][1] for k in keys}))
    phone_ping = unique(
        [r for r in pr if r[0] == 4 and r[1] == generation], lambda r: r[2]
    )
    host_ping = unique(
        [r for r in hr if r[0] == 6 and r[1] == host_session], lambda r: r[2]
    )
    ping_keys = phone_ping.keys() & host_ping.keys()
    if len(ping_keys) < 3:
        raise ValueError("Insufficient bidirectional clock constraints")
    anchor = max(host_ping[k][5] - phone_ping[k][6] for k in ping_keys)
    ref = (pm["started_ns"] + pm["ended_ns"]) // 2
    lower = [
        (
            (phone_ping[k][6] - ref) / 1e9,
            (host_ping[k][5] - phone_ping[k][6] - anchor) / 1000,
        )
        for k in ping_keys
    ]
    upper = [
        (
            (phone_ping[k][4] - ref) / 1e9,
            (host_ping[k][4] - phone_ping[k][4] - anchor) / 1000,
        )
        for k in ping_keys
    ]
    upper += [
        ((tx[k][5] - ref) / 1e9, (rx[k][4] - tx[k][5] - anchor) / 1000) for k in keys
    ]
    polygon, center = affine_polygon(lower, upper)
    groups = defaultdict(list)
    for r in pr:
        if r[0] == 1:
            groups[r[5]].append(r)
    groups = sorted(groups.items())
    queued = sorted([r for r in pr if r[0] == 2], key=lambda r: r[4])
    if len(groups) != len(queued) or not all(
        len(g[1]) == q[3] and g[0] <= q[4] for g, q in zip(groups, queued)
    ):
        raise ValueError(
            "Source groups cannot be uniquely associated with queue admissions"
        )
    qtimes = [r[4] for r in queued]
    if any(a >= b for a, b in zip(qtimes, qtimes[1:])):
        raise ValueError("Queue admission intervals are ambiguous")
    used_queues = set()
    samples, singles = [], []
    for key in keys:
        p, h = tx[key], rx[key]
        i = bisect_left(qtimes, p[4])
        if (
            i >= len(queued)
            or queued[i][1] != p[1]
            or queued[i][3] != p[3]
            or not groups[i][0] <= p[4] <= queued[i][4]
        ):
            raise ValueError(
                "Batch creation does not uniquely match source/queue group"
            )
        if i in used_queues:
            raise ValueError("Multiple packets mapped to one unsplit source batch")
        used_queues.add(i)
        for s in groups[i][1]:
            if s[4] > s[5]:
                raise ValueError("Source timestamp occurs after callback")
            item = ((s[4] - ref) / 1e9, (h[6] - s[4] - anchor) / 1000)
            samples.append(item)
            if p[3] == 1:
                singles.append(item)

    def affine_stats(rows):
        lo, hi, mid = [], [], []
        for x, raw in rows:
            offsets = [b + d * x for d, b in polygon]
            lo.append(raw - max(offsets))
            hi.append(raw - min(offsets))
            mid.append(raw - (center[1] + center[0] * x))
        return statistics(lo, hi, mid)

    sensitivity = {}
    for drift in (100, 1000):
        get_lower = envelope(lower, drift, False)
        get_upper = envelope(upper, drift, True)
        if any(get_lower(x) > get_upper(x) + 1e-6 for x, _ in lower + upper):
            raise ValueError("Variable drift cap inconsistent with causal constraints")
        sensitivity[str(drift)] = {}
        for label, rows in [
            ("single_sample_submission", singles),
            ("all_samples_to_batch_completion", samples),
        ]:
            lo = [raw - get_upper(x) for x, raw in rows]
            hi = [raw - get_lower(x) for x, raw in rows]
            sensitivity[str(drift)][label] = statistics(lo, hi)
    return dict(
        scope="Android MotionEvent sample timestamp -> completion of Linux input backend submission",
        excludes=[
            "physical motion before digitizer timestamp",
            "kernel-to-game consumption",
            "game update/rendering",
            "display scanout and pixel response",
        ],
        files={
            str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest()
            for p in (android, desktop)
        },
        backend=hm.get("backend"),
        matched_packets=len(keys),
        matched_source_events=len(samples),
        source_precision_counts={
            "nanosecond_api": sum(r[0] == 1 and r[1] == 1 for r in pr),
            "millisecond_fallback": sum(r[0] == 1 and r[1] == 0 for r in pr),
        },
        single_event_packets=len(singles),
        matched_heartbeat_exchanges=len(ping_keys),
        source_to_queue_association="Exact group count/order and batch-creation interval checks; no resets/overflow",
        affine_clock_model=dict(
            assumption="Relative clock mapping is affine during capture; unequal path delay allowed",
            anchor_offset_ns=anchor,
            reference_phone_ns=ref,
            feasible_vertices_rate_ppm_offset_us=polygon,
            midpoint_model_rate_ppm=center[0],
            midpoint_model_offset_us=center[1],
            point_estimate_is_assumption_not_observed_clock=True,
        ),
        single_sample_submission=affine_stats(singles),
        all_samples_to_batch_completion=affine_stats(samples),
        variable_clock_drift_sensitivity_ppm=sensitivity,
        interpretation="Intervals are conditional feasible bounds, not statistical confidence intervals or hardware certification. "
        "The midpoint is one admissible clock mapping, not proof of symmetric network delay. "
        "Single-event packets avoid using end-of-batch as an individual event timestamp.",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--android", required=True)
    parser.add_argument("--desktop", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = analyze(Path(args.android), Path(args.desktop))
    Path(args.output).write_text(json.dumps(result, indent=2))
    print(
        json.dumps(
            {
                key: result[key]
                for key in [
                    "matched_packets",
                    "single_event_packets",
                    "single_sample_submission",
                    "variable_clock_drift_sensitivity_ppm",
                ]
            },
            indent=2,
        )
    )
