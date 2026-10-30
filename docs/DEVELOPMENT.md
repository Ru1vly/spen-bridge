# Reproducible checks

Use Python 3.10–3.14 and JDK 17. The pinned Qt Linux wheels require glibc
2.34+ on x86_64, or 2.39+ on aarch64. Qt 6.11.2 supports Python below 3.15;
installers select/check that range instead of choosing an incompatible newer Python. Linux logic tests mock UInput; running pytest
never needs uinput privileges. Real kernel/compositor, S Pen and Windows driver
checks are separate gates listed in `audit/REMEDIATION.md` and `docs/WINDOWS.md`.

```sh
python -m venv server/.venv
server/.venv/bin/python -m pip install --require-hashes -r tests/requirements.txt
QT_QPA_PLATFORM=offscreen server/.venv/bin/python -m pytest -q
server/.venv/bin/ruff check --isolated --select E9,F server tests audit/reproduce.py
server/.venv/bin/pip-audit -r server/requirements.txt --disable-pip --no-deps
```

The requirements files include fully pinned transitive dependencies and hashes.
The audit's `--disable-pip --no-deps` reads those exact pins without downloading
large Qt wheels into a second resolver environment; installation enforces hashes.
To intentionally update them, edit `server/requirements.in` / `tests/requirements.in`,
then review the generated pins, hashes and advisory results:

```sh
uv pip compile server/requirements.in --universal --python-version 3.10 --generate-hashes -o server/requirements.txt
uv pip compile tests/requirements.in --universal --python-version 3.10 --generate-hashes -o tests/requirements.txt
```

Android uses AGP 8.5.2, Kotlin 2.4.21, Gradle 8.14.6, explicit R8 9.1.57 and lint
9.4.1. R8 meets Kotlin 2.4's bytecode requirement; the newer lint reads Kotlin
2.4 metadata. Gradle's distribution checksum, buildscript/application lockfiles
and SHA-256 dependency verification metadata are checked in.

```sh
cd android
./gradlew clean :app:testDebugUnitTest :app:assembleDebug :app:assembleRelease :app:lintDebug --dependency-verification strict
```

For an intentional Android dependency update, regenerate using the same task set
plus `--write-locks --write-verification-metadata sha256`, review the changed
coordinates and verify hashes against their publisher before committing. Re-run
without those write flags to check strict verification. `python audit/scan_android.py`
queries OSV for the locked debug runtime plus compiler/build tool coordinates.
Version-availability lint warnings are recorded separately from source errors;
upgrading compile/target SDK requires device compatibility testing.

The JVM TLS tests use an explicitly test-only key/certificate fixture. It is not
used by the app or server; production pairing generates a private per-user identity.
Qt render checks (`audit/render_remediation.py`) use no network/input backend.
The optional Gio launcher regression requires the system PyGObject/GioUnix typelib;
it skips where unavailable. CI actions are pinned to reviewed commit SHAs.

Portable PowerShell checks use `pwsh -NoProfile -File tests/test_driver_installer.ps1`.
All PnP/DevCon/pnputil operations are fakes; the actual installer keeps its admin
requirement. Native Windows signing, PnP and Ink validation remain separate.

Permission-helper account/group/ACL checks run against a regular fake `/dev/uinput`
in an isolated container. Only `modprobe` and `udevadm` are stubbed; no host devices
or permission directories are mounted. From the repository root:

```sh
podman build -t spen-permission-test -f tests/permission_container/Containerfile tests/permission_container
podman run --rm --network=none --security-opt=no-new-privileges \
  --volume "$PWD/server/setup_uinput.sh:/work/setup_uinput.sh:ro" \
  --volume "$PWD/tests/permission_container/test.sh:/work/test.sh:ro" \
  spen-permission-test bash /work/test.sh
```

This checks sudo/pkexec account selection, rejection of root/unknown accounts,
dedicated group ownership and real per-user ACL access. Real module loading,
udev/device creation and login-session permissions still require a disposable host.
