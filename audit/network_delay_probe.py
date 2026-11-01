"""Opaque TCP delay proxy around paired production TLS; no OS injection."""
import asyncio,json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.protocol import *
from server.security import load_identity,auth_proof
from server.server import SPenServer
class Sink:
 def __init__(self):self.at=None;self.delivered=asyncio.Event()
 def handle_event(self,e):self.at=time.perf_counter();self.delivered.set()
 def reset(self):pass
 def close(self):pass
async def main():
 with tempfile.TemporaryDirectory() as d:
  identity=load_identity(d);sink=Sink();delay=[0.0];tasks=set()
  server=SPenServer(sink,port=0,tls_context=identity.server_context(),pairing_code=identity.pairing_code)
  await server.start()
  async def proxy(r,w):
   task=asyncio.current_task();tasks.add(task)
   rr,ww=await asyncio.open_connection('127.0.0.1',server.bound_endpoint[1])
   async def copy(src,dst,up):
    while data:=await src.read(65536):
     if up and delay[0]:await asyncio.sleep(delay[0])
     dst.write(data);await dst.drain()
   streams=[asyncio.create_task(copy(r,ww,True)),asyncio.create_task(copy(rr,w,False))]
   try:await asyncio.wait(streams,return_when=asyncio.FIRST_COMPLETED)
   finally:
    for t in streams:t.cancel()
    await asyncio.gather(*streams,return_exceptions=True)
    ww.close();w.close();await asyncio.gather(ww.wait_closed(),w.wait_closed(),return_exceptions=True);tasks.discard(task)
  relay=await asyncio.start_server(proxy,'127.0.0.1',0)
  r,w=await asyncio.open_connection('127.0.0.1',relay.sockets[0].getsockname()[1],ssl=identity.client_context(),server_hostname='localhost')
  async def packet():
   kind,seq,size=unpack_header(await r.readexactly(HEADER_SIZE));return kind,seq,await r.readexactly(size)
  _,_,challenge=await packet();w.write(pack_packet(PKT_HANDSHAKE,0,auth_proof(identity.pairing_code,challenge[4:],'client')));await w.drain();await packet()
  delay[0]=.250;start=time.perf_counter();w.write(pack_events([PenEvent(ACTION_DOWN,0,4,.5,.5,.7)],1));await w.drain();await asyncio.wait_for(sink.delivered.wait(),2)
  result=dict(scope='paired production server via opaque TCP delay proxy, synthetic client, in-memory backend',configured_one_way_delay_ms=250,accepted_event_age_ms=(sink.at-start)*1000,stale_down_delivered=True,desktop_events_sent=False)
  w.close();await w.wait_closed();relay.close();await relay.wait_closed();await asyncio.gather(*list(tasks),return_exceptions=True);await server.stop()
  Path('audit/evidence/full-2026-10-31/network-delay.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
asyncio.run(main())
