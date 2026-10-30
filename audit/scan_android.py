"""Query OSV for locked runtime coordinates and the Kotlin/AGP/R8 toolchain."""
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parents[1]
packages = set()
for line in (root / 'android/app/gradle.lockfile').read_text().splitlines():
    if '=' not in line or line.startswith('#'):
        continue
    coordinate, configurations = line.split('=', 1)
    if 'debugRuntimeClasspath' in configurations.split(','):
        group, name, version = coordinate.split(':')
        packages.add((group + ':' + name, version))
gradle_properties = (root / 'android/gradle/wrapper/gradle-wrapper.properties').read_text()
gradle_version = re.search(r'gradle-([0-9.]+)-bin.zip', gradle_properties).group(1)
packages.update({('org.gradle:gradle-core', gradle_version),
                 ('org.jetbrains.kotlin:kotlin-gradle-plugin', '2.4.21'),
                 ('com.android.tools.build:gradle', '8.5.2'), ('com.android.tools:r8', '9.1.57'),
                 ('com.android.tools.lint:lint-gradle', '32.4.1')})
packages = [dict(name=name, version=version) for name, version in sorted(packages)]
query = dict(queries=[dict(package=dict(ecosystem='Maven', name=p['name']), version=p['version']) for p in packages])
request = urllib.request.Request('https://api.osv.dev/v1/querybatch', data=json.dumps(query).encode(),
                                 headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(request, timeout=45) as response:
    result = json.load(response)
report = dict(source='https://api.osv.dev/v1/querybatch', checked_at=datetime.now(timezone.utc).isoformat(),
              scope='Locked debugRuntimeClasspath plus Kotlin/AGP/R8/lint toolchain coordinates', packages=packages, response=result)
(root / 'audit/evidence/remediation-android-advisories.json').write_text(json.dumps(report, indent=2))
findings = [(p, r.get('vulns')) for p, r in zip(packages, result['results']) if r.get('vulns')]
print(json.dumps(dict(packages=len(packages), findings=findings), indent=2))
raise SystemExit(bool(findings))
