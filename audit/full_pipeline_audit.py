"""Read-only production TLS pipeline benchmark. No OS input backend."""
import asyncio, json, math, sys, tempfile, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.protocol import *
from server.security import load_identity, auth_proof
from server.server import SPenServer

def percentile(v,p):
    return sorted(v)[min(len(v)-1,math.ceil(len(v)*p)-1)] if v else None

class Sink:
    def __init__(self): self.sent={}; self.delays=[]
    def handle_event(self,e):
        self.delays.append((time.perf_counter_ns()-self.sent[round(e.x*10000)])/1e6)
    def reset(self): pass
    def close(self): pass

async def main():
    rows=[]
    with tempfile.TemporaryDirectory() as d:
        identity=load_identity(d)
        sink=Sink()
        server=SPenServer(sink,port=0,tls_context=identity.server_context(),pairing_code=identity.pairing_code,handshake_timeout=.5)
        await server.start()
        async def packet(r):
            kind,seq,size=unpack_header(await asyncio.wait_for(r.readexactly(HEADER_SIZE),2))
            return kind,seq,await r.readexactly(size)
        async def connect():
            r,w=await asyncio.open_connection('127.0.0.1',server.bound_endpoint[1],ssl=identity.client_context(),server_hostname='localhost')
            _,_,challenge=await packet(r)
            w.write(pack_packet(PKT_HANDSHAKE,0,auth_proof(identity.pairing_code,challenge[4:],'client')))
            await w.drain()
            assert await packet(r)==(PKT_HANDSHAKE,0,auth_proof(identity.pairing_code,challenge[4:],'server'))
            return r,w
        for rate,batch in ((240,1),(480,1),(960,1),(480,4)):
            r,w=await connect(); sink.sent={}; sink.delays=[]
            start=time.perf_counter(); cpu=time.process_time(); n=rate*2
            for i in range(0,n,batch):
                await asyncio.sleep(max(0,start+i/rate-time.perf_counter()))
                events=[]
                now=time.perf_counter_ns()
                for j in range(i,min(i+batch,n)):
                    sink.sent[j]=now; events.append(PenEvent(ACTION_MOVE,0,4,j/10000,.5,.7))
                w.write(pack_events(events,i)); await w.drain()
            w.write(pack_packet(PKT_PING,42,b'')); await w.drain()
            assert await packet(r)==(PKT_PONG,42,b'')
            assert len(sink.delays)==n
            rows.append(dict(rate_hz=rate,batch=batch,events=n,p50_ms=percentile(sink.delays,.5),p95_ms=percentile(sink.delays,.95),p99_ms=percentile(sink.delays,.99),max_ms=max(sink.delays),process_cpu_seconds=time.process_time()-cpu,elapsed_seconds=time.perf_counter()-start))
            w.close(); await w.wait_closed(); await asyncio.sleep(.05)
        raw=[]
        for _ in range(server.max_connections):
            _,w=await asyncio.open_connection('127.0.0.1',server.bound_endpoint[1]); w.write(b'\x16'); await w.drain();raw.append(w)
        await asyncio.sleep(.05)
        saturated=len(server._handlers)
        try:
            _,w=await connect(); w.close(); await w.wait_closed(); blocked=False
        except (OSError,asyncio.TimeoutError,asyncio.IncompleteReadError): blocked=True
        for w in raw: w.close()
        await asyncio.gather(*(w.wait_closed() for w in raw),return_exceptions=True)
        await asyncio.sleep(.1)
        _,w=await connect(); w.close();await w.wait_closed()
        await server.stop()
        result=dict(scope='Loopback TLS write to production server in-memory backend callback; excludes Android, real network, OS injection and display',rows=rows,admission=dict(unauthenticated_connections=saturated,paired_reconnect_blocked=blocked,recovered_after_attack_closed=True),desktop_events_sent=False)
        Path('audit/evidence/full-2026-10-31/pipeline.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
if __name__=='__main__': asyncio.run(main())
