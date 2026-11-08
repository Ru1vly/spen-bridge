#!/usr/bin/env python3
"""Align, sign and verify a CI release APK using a private local key.

Passwords are read by apksigner from environment variables, never command args.
No build, installation, key generation, upload or publication occurs here.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.check_output([str(arg) for arg in args], text=True, stderr=subprocess.STDOUT)


def package(apk, source_commit, build_tools, output):
    commit = source_commit.read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or commit != run("git", "-C", ROOT, "rev-parse", "HEAD").strip():
        raise ValueError("CI source commit must match this checkout's HEAD")
    if run("git", "-C", ROOT, "status", "--porcelain", "--untracked-files=no").strip():
        raise ValueError("Commit tracked changes before packaging a release")
    gradle = (ROOT / "android/app/build.gradle.kts").read_text()
    version = re.search(r'versionName = "([^"]+)"', gradle).group(1)
    version_code = re.search(r"versionCode = (\d+)", gradle).group(1)
    metadata = run(build_tools / "aapt", "dump", "badging", apk)
    expected = f"package: name='com.spenbridge.app' versionCode='{version_code}' versionName='{version}'"
    if not metadata.startswith(expected) or "application-debuggable" in metadata:
        raise ValueError("APK must be the non-debuggable release variant at the checkout version")
    required = ["SPEN_KEYSTORE", "SPEN_KEY_ALIAS", "SPEN_STORE_PASSWORD", "SPEN_KEY_PASSWORD"]
    if any(not os.environ.get(name) for name in required):
        raise ValueError("Set all four SPEN signing environment variables (see docs/RELEASING.md)")
    expected_cert = (ROOT / "release/signing-certificate.sha256").read_text().strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_cert):
        raise ValueError("Invalid pinned release certificate SHA-256")
    if output.exists():
        raise ValueError("Output directory already exists; use a new directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Complete validation in a private staging directory before exposing outputs.
    with tempfile.TemporaryDirectory(prefix=".spen-sign-", dir=output.parent) as work:
        stage = Path(work)
        aligned = stage / "aligned.apk"
        signed = stage / f"spen-bridge-android-v{version}.apk"
        run(build_tools / "zipalign", "-p", "4", apk, aligned)
        run(build_tools / "apksigner", "sign", "--ks", os.environ["SPEN_KEYSTORE"],
            "--ks-key-alias", os.environ["SPEN_KEY_ALIAS"],
            "--ks-pass", "env:SPEN_STORE_PASSWORD", "--key-pass", "env:SPEN_KEY_PASSWORD",
            "--out", signed, aligned)
        verification = run(build_tools / "apksigner", "verify", "--verbose", "--print-certs", signed)
        certs = re.findall(r"Signer #\d+ certificate SHA-256 digest: ([0-9a-f]+)", verification)
        if certs != [expected_cert]:
            raise ValueError("Signed APK certificate does not match the pinned release identity")
        run(build_tools / "zipalign", "-c", "-p", "4", signed)
        digest = hashlib.sha256(signed.read_bytes()).hexdigest()
        archive = stage / f"spen-bridge-v{version}-source.tar.gz"
        with archive.open("wb") as stream:
            subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar.gz",
                            f"--prefix=spen-bridge-{version}/", commit], stdout=stream, check=True)
        archive_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        (stage / "SHA256SUMS").write_text(f"{digest}  {signed.name}\n{archive_digest}  {archive.name}\n")
        (stage / "provenance.json").write_text(json.dumps({
            "source_commit": commit, "version": version, "version_code": int(version_code),
            "apk": signed.name, "sha256": digest, "signer_sha256": expected_cert,
            "input_sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
            "source_archive": archive.name, "source_archive_sha256": archive_digest,
        }, indent=2) + "\n")
        (stage / "signature-verification.txt").write_text(verification)
        aligned.unlink()
        for sidecar in stage.glob("*.idsig"):
            sidecar.unlink()
        # copytree refuses to overwrite a destination created during signing.
        shutil.copytree(stage, output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--source-commit", type=Path, required=True, help="source-commit.txt from the same CI artifact")
    parser.add_argument("--build-tools", type=Path, required=True, help="Android SDK build-tools/34.0.0 directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(package(args.apk.resolve(), args.source_commit, args.build_tools.resolve(), args.output.resolve()))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Release packaging failed: {exc}\n")


if __name__ == "__main__":
    main()
