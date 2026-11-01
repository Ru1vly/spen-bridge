"""Paired frame-parser benchmark: buffered input only, no TLS/USB/OS injection."""
import asyncio
import json
import inspect
import textwrap
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.protocol import ACTION_HOVER_MOVE, PenEvent, pack_events
from server.server import SPenServer, _Budget


# Build the rejected variant from the exact production parser, changing only
# deadline management. This keeps validation and packet structure identical.
source = textwrap.dedent(inspect.getsource(SPenServer._read_packet))
source = source.replace("return await asyncio.wait_for(read(), timeout)",
                        "async with asyncio.timeout(timeout):\n        return await read()")
namespace = dict(SPenServer._read_packet.__globals__)
exec(compile(source, "<deadline-benchmark-prototype>", "exec"), namespace)


class ContextDeadlinePrototype(SPenServer):
    _read_packet = namespace["_read_packet"]


async def trial(legacy, count):
    server = SPenServer(None) if legacy else ContextDeadlinePrototype(None)
    reader = asyncio.StreamReader()
    frame = pack_events([PenEvent(ACTION_HOVER_MOVE, 0, 0, .5, .5, 0)])
    reader.feed_data(frame * count)
    budget = _Budget(10**9)
    samples = []
    start = time.perf_counter_ns()
    for _ in range(count):
        before = time.perf_counter_ns()
        await server._read_packet(reader, 10, budget)
        samples.append(time.perf_counter_ns() - before)
    elapsed = time.perf_counter_ns() - start
    samples.sort()
    return dict(median_us=statistics.median(samples) / 1000,
                p99_us=samples[(len(samples) * 99) // 100] / 1000,
                max_us=samples[-1] / 1000,
                frames_per_second=count * 1e9 / elapsed)


async def main():
    await trial(True, 1000)
    await trial(False, 1000)
    rounds = []
    for index in range(6):
        result = {}
        for legacy in ((True, False) if index % 2 == 0 else (False, True)):
            result['before' if legacy else 'after'] = await trial(legacy, 10000)
        rounds.append(result)
    summary = {variant: {key: statistics.median(r[variant][key] for r in rounds)
                         for key in rounds[0][variant]}
               for variant in ('before', 'after')}
    print(json.dumps(dict(scope='Buffered frame parsing only; excludes TLS, USB, '
                               'event decode and OS submission',
                          rounds=rounds, median_of_rounds=summary), indent=2))


if __name__ == '__main__':
    asyncio.run(main())
