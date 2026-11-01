"""Native offscreen scratchpad stress benchmark; no device or OS input."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json,math,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from server.widgets.scratchpad import ScratchpadWidget
from server.protocol import ACTION_MOVE
app=QApplication([])
w=ScratchpadWidget();w.resize(960,480);w.show();app.processEvents()
rows=[]
for batch in (16,32,128,2048):
    times=[]
    for repeat in range(20):
        points=[(i/max(1,batch-1),.5+.3*math.sin(i*.03),.7,ACTION_MOVE) for i in range(batch)]
        start=time.perf_counter();w.add_tablet_points(points);app.processEvents();w.grab()
        times.append((time.perf_counter()-start)*1000)
    rows.append(dict(batch=batch,p50_ms=sorted(times)[9],p95_ms=sorted(times)[18],max_ms=max(times)))
print(json.dumps(dict(scope='offscreen 960x480 Qt scratchpad drawing plus raster capture; no OS input or physical compositor',rows=rows),indent=2))
