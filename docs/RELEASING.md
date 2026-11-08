# Preparing a GitHub release

The next candidate is **v1.1.0-rc1**, Android version code **2**. Version code
must increase for subsequent APKs. Physical acceptance is still open; keep this
candidate a draft until the intended acceptance checks are satisfied. A GitHub
sideload release is the distribution target here; Play Store publication is a
separate task.

## Signing identity

The dedicated release certificate is checked in as
`release/signing-certificate.pem`; its DER SHA-256 is pinned in
`release/signing-certificate.sha256`. The private key and passwords are outside
the repository at `~/.config/spen-bridge/release-signing/`, restricted to the
owner. The `signing.env` file there exports the four variables consumed by the
packager. Never commit that file or the private key. Keep a secure backup of
both before public distribution: future in-place updates depend on this key.
No private signing material is uploaded to GitHub by the packaging procedure.

The published v1.0.0 APK has signer SHA-256
`9f3e849598ca035189279dcfa2571c96234fc38670650901fed6ca8c20384184`.
The available local debug key differs. The candidate deliberately starts a
dedicated release identity; its migration/re-pairing requirements are described
in `release/v1.1.0-rc1.md`. Do not silently substitute a generated debug key.

## Verification and packaging

1. Commit the candidate source. Linux CI, Android CI and Windows Driver Build
   run on a push affecting their paths. Inspect every job rather than relying
   on earlier local reports. Android runs strict dependency verification, JVM
   tests, debug/release assembly and lint. Windows builds both configurations,
   validates the package and runs portable application/installer tests.
2. Download `android-build-and-reports` from the successful Android run for
   that exact commit. It includes the unsigned release APK and
   `source-commit.txt`. Do not use the debug or audit variant.
3. From a clean tracked checkout of the same commit, run:

   ```sh
   . "$HOME/.config/spen-bridge/release-signing/signing.env"
   python3 release/package_android.py \
     dist/ci/apk/release/app-release-unsigned.apk \
     --source-commit dist/ci/source-commit.txt \
     --build-tools "$HOME/.cache/spen-bridge/toolchains/android-sdk/build-tools/34.0.0" \
     --output dist/v1.1.0-rc1
   ```

   Adjust the downloaded artifact path and SDK location as needed. The script
   refuses a mismatched source commit/version, a debuggable APK, dirty tracked
   source, missing credentials, an existing destination or an unexpected signer.
   It aligns, signs and verifies the APK before writing the final directory.
4. Check `SHA256SUMS` and `signature-verification.txt` in the output directory.
   `provenance.json` records the input/output hashes, source commit, version and
   signer. Preserve it alongside the release APK.
5. Prepare a draft prerelease targeting the tested commit, using
   `release/v1.1.0-rc1.md` as the notes. Attach the signed APK, `SHA256SUMS`,
   `provenance.json` and signature report. Do not attach an unsigned APK or an
   unsigned Windows driver as an installable production artifact.
6. Complete the physical acceptance described in
   `docs/UI_UX_REMAINING_WORK.md`, review the documented limitations, ensure
   signing-key backup, then publish the candidate when approved.

The ordinary Android Gradle build intentionally produces an unsigned release
intermediate so CI needs no private key. Signing follows the Android
[command-line release procedure](https://developer.android.com/build/building-cmdline)
using `zipalign` followed by `apksigner`.

## Resource limits

Use hosted CI for full builds/tests while this desktop is in use. Do not start
emulators or unrestricted builds/benchmarks locally. Lightweight inspection,
lint and APK packaging do not require an emulator or access to a physical pen.
