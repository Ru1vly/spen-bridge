"""Reproduce full-area overlay and USB-only validation on disposable emulator."""
from pathlib import Path
import sys,json
p=Path(__file__).with_name('capture_layout_android.py').resolve()
s=p.read_text().split('\ntry:\n')[0].replace('Path(__file__).parent / "evidence" / "layout-v2"','Path("audit/evidence/full-2026-10-31/mobile-extra")')
sys.argv=[str(p),'--adb','/tmp/spen-android-sdk/platform-tools/adb']
ns={'__file__':str(p),'__name__':'audit_helpers'}
exec(compile(s,str(p),'exec'),ns)
adb,shell,find,tap,capture=[ns[k] for k in ['adb','shell','find','tap','capture']]
package=ns['package']
try:
 shell('am','force-stop',package)
 prefs=('<?xml version="1.0" encoding="utf-8"?><map><boolean name="force_landscape" value="false"/><string name="area_mode">full</string><string name="server_ip"></string><int name="server_port" value="65432"/><string name="desktop_fingerprint">'+'0'*64+'</string><string name="pairing_code">'+'A'*43+'</string></map>').encode()
 adb('shell','run-as',package,'sh','-c',"'cat > shared_prefs/SPenBridgePrefs.xml'",data=prefs)
 ns['launch']();tap('btnCollapse');capture('android-full-area-collapsed')
 status=find('statusContainer');assert status is not None and status.get('clickable')=='true'
 tap('statusContainer')
 import time
 for _ in range(4):
  if find('settingsTabs') is not None:break
  time.sleep(.5)
 status_opened=find('settingsTabs') is not None
 if not status_opened:
  tap('btnExpand');ns['open_settings']()
 tap('btnSave');assert find('editServerIp') is not None and find('settingsTabs') is not None
 capture('android-usb-only-save-blocked')
 result=dict(full_area_collapsed_status_clickable=True,status_opens_settings=status_opened,valid_synthetic_pairing_blank_wifi_save_blocked=True,port=65432,hardware=False)
 (ns['output']/'edge-checks.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
finally:
 shell('am','force-stop',package)
