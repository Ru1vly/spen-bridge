"""Run native accessibility checks on the isolated audit app; restore prior service settings."""
import argparse,json,shlex,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--serial',required=True);a=p.parse_args()
base=['adb','-s',a.serial]
root=Path(__file__).resolve().parents[1];out=root/'audit/evidence/ui-ux-fixes/device-2026-11-01';out.mkdir(parents=True,exist_ok=True)
def shell(*args,timeout=180):
 return subprocess.check_output(base+['shell',shlex.join(args)],text=True,timeout=timeout).strip()
package='com.spenbridge.app.uiaudit'
assert shell('pm','path',package).startswith('package:'), 'Install the isolated audit app first'
keys=['enabled_accessibility_services','accessibility_enabled']
original={k:shell('settings','get','secure',k) for k in keys}
service='com.samsung.android.accessibility.talkback/com.samsung.android.marvin.talkback.TalkBackService'
try:
 existing=original[keys[0]] if original[keys[0]] not in ('','null') else ''
 enabled=':'.join(dict.fromkeys([v for v in existing.split(':') if v]+[service]))
 shell('settings','put','secure',keys[0],enabled)
 shell('settings','put','secure',keys[1],'1')
 for _ in range(30):
  state=shell('dumpsys','accessibility').lower().replace(' ','')
  if 'touchexplorationenabled=true' in state:break
  time.sleep(1)
 else:raise RuntimeError('TalkBack did not activate touch exploration')
 result=shell('am','instrument','-w','-e','isolated_device','true','-e','talkback','true','-e','orientation','portrait',package+'/com.spenbridge.app.UiUxAuditInstrumentation')
 (out/'talkback-check.txt').write_text(result+'\n')
 assert 'talkback_focus=PASS:' in result and 'ui_ux_checks=PASS:' in result,result
 print('TalkBack touch exploration, accessibility focus, and native range editing passed',flush=True)
finally:
 for key,value in original.items():
  if value=='null':shell('settings','delete','secure',key)
  else:shell('settings','put','secure',key,value)
 time.sleep(1)
 restored={k:shell('settings','get','secure',k)==v for k,v in original.items()}
 (out/'accessibility-restoration.json').write_text(json.dumps(restored,indent=2)+'\n')
 assert all(restored.values()),'Accessibility settings did not restore'
 print('Original accessibility service settings restored',flush=True)
