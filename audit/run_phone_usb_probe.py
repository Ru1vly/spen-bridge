"""Run an app-UID synthetic USB TLS probe; ephemeral credentials, no OS input."""
import asyncio,json,math,secrets,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.security import load_identity
from server.server import SPenServer
OUT=Path('audit/evidence/s22-usb-debug-2026-10-31')
ADB=['/tmp/spen-android-sdk/platform-tools/adb','-s','R3CTA0KD6NM']
PACKAGE='com.spenbridge.app'
def stats(v):
    v=sorted(v)
    return {name:v[min(len(v)-1,math.ceil(len(v)*p)-1)] for name,p in [('p50_us',.5),('p95_us',.95),('p99_us',.99),('max_us',1)]} if v else {}
class Sink:
    def __init__(self):self.times=[]
    def handle_event(self,e):self.times.append(time.perf_counter_ns())
    def reset(self):pass
    def close(self):pass
async def adb(*args,data=None,check=True):
    p=await asyncio.create_subprocess_exec(*ADB,*args,stdin=asyncio.subprocess.PIPE if data is not None else asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:out,err=await asyncio.wait_for(p.communicate(data),35)
    except BaseException:
        p.kill();await p.wait();raise
    if check and p.returncode:raise RuntimeError(f'ADB diagnostic command failed ({p.returncode}): {err.decode(errors="replace")} {out.decode(errors="replace")}')
    return out,err
async def main():
    device=(await adb('shell','getprop','ro.product.model'))[0].decode().strip()
    assert device=='SM-S908B',device
    folder='cache/spen-usb-audit-'+secrets.token_hex(6)
    sink=Sink();server=None;remote_port=None
    with tempfile.TemporaryDirectory(prefix='spen-usb-audit-') as tmp:
        identity=load_identity(tmp)
        server=SPenServer(sink,port=0,tls_context=identity.server_context(),pairing_code=identity.pairing_code)
        try:
            await server.start();host_port=server.bound_endpoint[1]
            reverse=(await adb('reverse','tcp:0',f'tcp:{host_port}'))[0].decode().strip()
            remote_port=int(reverse)
            await adb('shell',f"run-as {PACKAGE} mkdir -m 700 {folder}")
            properties=f'port={remote_port}\nfingerprint={identity.fingerprint}\ncode={identity.pairing_code}\ncount=5000\n'.encode()
            await adb('exec-in',f"run-as {PACKAGE} sh -c 'umask 077; cat > {folder}/config'",data=properties)
            rows=[]
            for repeat in range(3):
                sink.times=[]
                out,err=await adb('shell','am','instrument','-w','-e','config',f'/data/user/0/{PACKAGE}/{folder}/config',f'{PACKAGE}/.USBDiagnosticInstrumentation')
                (OUT/f'usb-probe-{repeat+1}.stderr.txt').write_bytes(err)
                (OUT/f'usb-probe-{repeat+1}.instrumentation.txt').write_bytes(out)
                result=next((line.partition('diagnostics=')[2] for line in out.decode().splitlines() if line.startswith('INSTRUMENTATION_RESULT: diagnostics=')),None)
                if result is None:raise RuntimeError('Instrumentation failed; see private-secret-free instrumentation result artifact')
                row=json.loads(result);arrivals=sink.times[500:]
                row['host_received_total']=len(sink.times)
                row['host_arrival_interval']=stats([(b-a)/1000 for a,b in zip(arrivals,arrivals[1:])])
                row['host_received_hz']=(len(arrivals)-1)*1e9/(arrivals[-1]-arrivals[0])
                assert len(sink.times)==5500
                rows.append(row)
                print(json.dumps(row),flush=True)
                await asyncio.sleep(.2)
            report=dict(device=device,desktop_events_sent=False,production_receiver=True,android_production_transport=False,phone_process='debug Instrumentation under com.spenbridge.app UID; synthetic source, per-report PING acknowledgement',one_way_latency_measured=False,rows=rows)
            (OUT/'usb-probe.json').write_text(json.dumps(report,indent=2))
        finally:
            await adb('shell',f'run-as {PACKAGE} rm -rf {folder}',check=False)
            if remote_port is not None:await adb('reverse','--remove',f'tcp:{remote_port}',check=False)
            if server:await server.stop()
asyncio.run(main())
