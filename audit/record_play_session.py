"""Passive S Pen/kernel report timing only. No grabs, writes or UI actions."""
import asyncio,collections,json,math,os,re,signal,sys,time,fcntl,struct
from datetime import datetime,timezone
from pathlib import Path
from evdev import InputDevice,list_devices,ecodes
OUT=Path('audit/evidence/s22-osu-session-2026-10-31');OUT.mkdir(parents=True,exist_ok=True)
ADB=['/tmp/spen-android-sdk/platform-tools/adb','-s','R3CTA0KD6NM']
class Counter:
    def __init__(self):
        self.count=0;self.last=None;self.first=None;self.hist=collections.Counter();self.max_gap_us=0;self.gaps=0;self.errors=[];self.segments=0
    def sample(self,stamp):
        self.count+=1
        if self.first is None:self.first=stamp
        if self.last is not None:
            delta=(stamp-self.last)*1e6
            if delta>=0:
                self.hist[min(1000000,round(delta))]+=1;self.max_gap_us=max(self.max_gap_us,delta);self.gaps+=1
        self.last=stamp
    def boundary(self):self.last=None;self.segments+=1
    def summary(self):
        pct={}
        for label,q in [('p50_us',.5),('p95_us',.95),('p99_us',.99)]:
            target=math.ceil(self.gaps*q);running=0;pct[label]=None
            for value,n in sorted(self.hist.items()):
                running+=n
                if running>=target and target:pct[label]=value;break
        return dict(reports=self.count,segments=self.segments,intervals=pct,max_gap_us=self.max_gap_us,errors=self.errors)
async def main():
    stop=asyncio.Event();loop=asyncio.get_running_loop()
    for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,stop.set)
    (OUT/'recorder.pid').write_text(str(os.getpid()))
    phone,host=Counter(),Counter();start=time.monotonic();began=datetime.now(timezone.utc).isoformat()
    process=await asyncio.create_subprocess_exec(*ADB,'shell','timeout 1800 getevent -lt /dev/input/event2',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    async def phone_reader():
        try:
            while line:=await process.stdout.readline():
                if b'SYN_REPORT' in line:
                    match=re.search(rb'\[\s*([0-9]+\.[0-9]+)\]',line)
                    if match:phone.sample(float(match[1]))
            err=(await process.stderr.read()).decode(errors='replace').strip()
            if err:phone.errors.append(err[:300])
        except Exception as e:phone.errors.append(type(e).__name__)
    async def host_reader():
        while not stop.is_set():
            device=None
            try:
                candidates=[]
                for path in list_devices():
                    d=InputDevice(path)
                    if d.name=='Samsung S Pen Virtual Tablet' and d.phys=='py-evdev-uinput':candidates.append(d)
                    else:d.close()
                if len(candidates)!=1:
                    for d in candidates:d.close()
                    await asyncio.sleep(.5);continue
                device=candidates[0];fcntl.ioctl(device.fd,0x400445a0,struct.pack('i',time.CLOCK_MONOTONIC));host.boundary()
                async for event in device.async_read_loop():
                    if event.type==ecodes.EV_SYN and event.code==ecodes.SYN_REPORT:host.sample(event.timestamp())
                    if stop.is_set():break
            except Exception as e:
                if len(host.errors)<20:host.errors.append(type(e).__name__+': '+str(e))
                await asyncio.sleep(.5)
            finally:
                if device:device.close()
    tasks=[asyncio.create_task(phone_reader()),asyncio.create_task(host_reader())]
    with (OUT/'per-second.jsonl').open('w') as f:
        last_phone=last_host=0
        try:
            for _ in range(1800):
                try:await asyncio.wait_for(stop.wait(),1);break
                except asyncio.TimeoutError:pass
                now=time.monotonic();f.write(json.dumps(dict(elapsed_seconds=round(now-start,3),phone_reports=phone.count-last_phone,desktop_reports=host.count-last_host,phone_total=phone.count,desktop_total=host.count))+'\n');f.flush()
                last_phone,last_host=phone.count,host.count
                (OUT/'live-summary.json').write_text(json.dumps(dict(elapsed_seconds=now-start,phone=phone.summary(),desktop=host.summary()),indent=2))
                if phone.count==0 and process.returncode is not None:break
        finally:
            if process.returncode is None:process.terminate()
            try:await asyncio.wait_for(process.wait(),3)
            except asyncio.TimeoutError:process.kill();await process.wait()
            for t in tasks:t.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            result=dict(started_at=began,elapsed_seconds=time.monotonic()-start,phone=phone.summary(),desktop=host.summary(),scope='S Pen kernel SYN_REPORT timestamps and virtual tablet SYN_REPORT timestamps; independent clocks, no one-way latency measurement',caveats=['ADB monitoring adds some traffic; not zero-overhead','Idle gaps are included; do not interpret all gaps as transport stalls','Kernel report counts are not application packet counts or proof of sensor scan frequency','Source and output reports are not paired; differences do not alone prove packet loss'],no_input_grabs=True,no_injected_input=True)
            (OUT/'summary.json').write_text(json.dumps(result,indent=2));(OUT/'recorder.pid').unlink(missing_ok=True)
            print(json.dumps(result,indent=2))
asyncio.run(main())
