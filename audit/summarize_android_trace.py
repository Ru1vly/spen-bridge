"""Stream a bounded Android trace; diagnose sender stages without another run."""

import argparse
import json
import struct
from collections import Counter
from pathlib import Path

if __package__:
    from .analyze_input_trace import distribution
else:
    from analyze_input_trace import distribution

RECORD = struct.Struct(">8q")
MAX_RECORDS = 200000


def summarize(path):
    counts = Counter()
    reasons = Counter()
    states = Counter()
    resets = []
    queue_ns, write_ns = [], []
    queued_events = sent_events = 0
    with Path(path).open("rb") as source:
        prefix = source.read(4)
        if len(prefix) != 4:
            raise ValueError("Incomplete trace header")
        length = struct.unpack(">I", prefix)[0]
        if not 0 < length <= 8192:
            raise ValueError("Invalid trace header length")
        header = source.read(length)
        if len(header) != length:
            raise ValueError("Incomplete trace metadata")
        metadata = json.loads(header)
        if not isinstance(metadata, dict):
            raise ValueError("Invalid trace metadata")
        records = metadata.get("records")
        if (
            metadata.get("version") != 1
            or metadata.get("side") != "android"
            or metadata.get("record_bytes") != RECORD.size
            or type(records) is not int
            or not 0 <= records <= MAX_RECORDS
        ):
            raise ValueError("Unsupported or unbounded Android trace")
        overflow = metadata.get("overflow")
        if type(overflow) is not int or overflow < 0:
            raise ValueError("Invalid trace overflow count")
        for _ in range(records):
            raw = source.read(RECORD.size)
            if len(raw) != RECORD.size:
                raise ValueError("Incomplete trace record")
            kind, generation, detail, count, created, began, ended, _ = RECORD.unpack(
                raw
            )
            counts[kind] += 1
            if kind in (2, 3) and count <= 0:
                raise ValueError("Invalid sender event count")
            if kind == 2:
                queued_events += count
            elif kind == 3:
                sent_events += count
                queue_ns.append(began - created)
                write_ns.append(ended - began)
            elif kind == 9:
                reasons[detail] += 1
                if len(resets) < 16:
                    resets.append(
                        dict(generation=generation, reason=detail, time_ns=created)
                    )
            elif kind == 10:
                states[detail] += 1
        if source.read(1):
            raise ValueError("Unexpected trailing trace bytes")
    return dict(
        scope="Android-local sender trace only; no one-way USB or physical sensor latency claim",
        metadata=metadata,
        trace_overflow=overflow > 0,
        counts=dict(
            real_source_records=counts[1],
            synthetic_source_records=counts[7],
            queue_admissions=counts[2],
            queued_events=queued_events,
            event_packets_written=counts[3],
            events_written=sent_events,
            queue_resets=counts[9],
        ),
        reset_reason_counts={str(k): v for k, v in sorted(reasons.items())},
        reset_reason_meanings={
            "1": "admission rejected: invalid data or capacity",
            "2": "queued input exceeded freshness limit",
        },
        first_reset_records=resets,
        omitted_reset_records=max(0, counts[9] - len(resets)),
        transport_state_counts={str(k): v for k, v in sorted(states.items())},
        stages=dict(
            queue_to_write_start=distribution(queue_ns),
            write_call=distribution(write_ns),
        ),
        loss_claim="Counts alone do not certify loss: inspect capture boundaries, overflow, source validity and host delivery.",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("trace")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = summarize(args.trace)
    Path(args.output).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
