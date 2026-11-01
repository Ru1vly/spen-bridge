"""Restore transient build prerequisites into persistent, checksum-verified cache."""

import hashlib
import json
import shutil
import tarfile
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

BASE = Path.home() / ".cache/spen-bridge/toolchains"
BASE.mkdir(parents=True, exist_ok=True)


def download(url, path, algorithm, expected):
    if (
        not path.exists()
        or hashlib.new(algorithm, path.read_bytes()).hexdigest() != expected
    ):
        temporary = path.with_suffix(".download")
        with (
            urllib.request.urlopen(url, timeout=60) as source,
            temporary.open("wb") as out,
        ):
            shutil.copyfileobj(source, out)
        if hashlib.new(algorithm, temporary.read_bytes()).hexdigest() != expected:
            raise RuntimeError("Toolchain checksum mismatch")
        temporary.replace(path)


jdk = BASE / "jdk17"
if not (jdk / "bin/javac").exists():
    url = (
        "https://corretto.aws/downloads/latest/amazon-corretto-17-x64-linux-jdk.tar.gz"
    )
    checksum = (
        urllib.request.urlopen(
            "https://corretto.aws/downloads/latest_sha256/amazon-corretto-17-x64-linux-jdk.tar.gz",
            timeout=30,
        )
        .read()
        .decode()
        .split()[0]
    )
    archive = BASE / "jdk17.tar.gz"
    download(url, archive, "sha256", checksum)
    with tempfile.TemporaryDirectory(dir=BASE) as staging:
        with tarfile.open(archive) as source:
            source.extractall(staging, filter="data")
        root = next(p.parent.parent for p in Path(staging).rglob("bin/javac"))
        shutil.move(str(root), jdk)
    print(json.dumps({"jdk": str(jdk), "source": url, "sha256": checksum}), flush=True)
repo = ET.fromstring(
    urllib.request.urlopen(
        "https://dl.google.com/android/repository/repository2-3.xml", timeout=30
    ).read()
)
sdk = BASE / "android-sdk"
sdk.mkdir(exist_ok=True)
for package, destination, marker in [
    ("platforms;android-34", sdk / "platforms/android-34", "android.jar"),
    ("build-tools;34.0.0", sdk / "build-tools/34.0.0", "source.properties"),
]:
    if destination.exists():
        properties = destination / "source.properties"
        if (
            package == "platforms;android-34"
            and properties.exists()
            and "AndroidVersion.IsBaseSdk=false" in properties.read_text()
        ):
            recovered = BASE / (
                "sdk-extension-backup-" + str(__import__("time").time_ns())
            )
            destination.rename(recovered)
        else:
            continue
    remote = next(
        p
        for p in repo.iter()
        if p.tag.split("}")[-1] == "remotePackage" and p.get("path") == package
    )
    archives = next(c for c in remote if c.tag.split("}")[-1] == "archives")
    chosen = next(
        a
        for a in archives
        if next((c.text for c in a if c.tag.split("}")[-1] == "host-os"), "linux")
        == "linux"
    )
    complete = next(c for c in chosen if c.tag.split("}")[-1] == "complete")
    fields = {c.tag.split("}")[-1]: c for c in complete}
    url = "https://dl.google.com/android/repository/" + fields["url"].text
    checksum = fields["checksum"]
    algorithm = checksum.get("type", "sha1")
    archive = BASE / (package.replace(";", "-") + ".zip")
    download(url, archive, algorithm, checksum.text)
    with tempfile.TemporaryDirectory(dir=BASE) as staging:
        with zipfile.ZipFile(archive) as source:
            source.extractall(staging)
            for info in source.infolist():
                if not info.is_dir() and (info.external_attr >> 16) & 0o111:
                    (Path(staging) / info.filename).chmod(
                        (info.external_attr >> 16) & 0o777
                    )
        root = next(p.parent for p in Path(staging).rglob(marker))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(root), destination)
    print(
        json.dumps(
            {
                "package": package,
                "url": url,
                "checksum_type": algorithm,
                "checksum": checksum.text,
            }
        ),
        flush=True,
    )
platform_tools = Path.home() / ".local/share/spen-bridge/android/platform-tools"
if not (sdk / "platform-tools").exists():
    (sdk / "platform-tools").symlink_to(platform_tools, target_is_directory=True)
print(json.dumps({"sdk": str(sdk)}), flush=True)
