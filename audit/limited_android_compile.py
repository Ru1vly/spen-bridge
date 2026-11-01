"""Run only inside the verified resource-limited transient service.

Refuses unrestricted execution. No emulator, install, benchmark or downloads.
"""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate_limits(limits, nice):
    quota, period = limits["cpu.max"].split()
    if quota == "max" or not 0 < int(quota) <= int(period) * 0.05:
        raise RuntimeError("Requires a CPU quota of at most 5% of one CPU")
    if limits["memory.max"] == "max" or int(limits["memory.max"]) > 768 * 1024**2:
        raise RuntimeError("Requires a memory cap of at most 768 MiB")
    if limits["memory.swap.max"] != "0" or nice < 19:
        raise RuntimeError("Requires swap disabled for this job and idle CPU priority")


def main():
    name = Path("/proc/self/cgroup").read_text().strip().split("::", 1)[1]
    group = Path("/sys/fs/cgroup") / name.lstrip("/")
    limits = {
        key: (group / key).read_text().strip()
        for key in ["cpu.max", "memory.max", "memory.high", "memory.swap.max"]
    }
    validate_limits(limits, os.getpriority(os.PRIO_PROCESS, 0))
    print(
        json.dumps(
            dict(resource_guard_passed=True, limits=limits, task="assembleDebug")
        ),
        flush=True,
    )
    tools = Path.home() / ".cache/spen-bridge/toolchains"
    env = {
        **os.environ,
        "JAVA_HOME": str(tools / "jdk17"),
        "ANDROID_HOME": str(tools / "android-sdk"),
        "JAVA_OPTS": "-Xmx64m -XX:ActiveProcessorCount=1",
        "GRADLE_OPTS": "",
    }
    args = [
        str(ROOT / "android/gradlew"),
        "-p",
        str(ROOT / "android"),
        "--offline",
        "--no-daemon",
        "--no-watch-fs",
        "--console=plain",
        "--max-workers=1",
        "-Pkotlin.compiler.execution.strategy=in-process",
        "-Dorg.gradle.parallel=false",
        "-Dorg.gradle.jvmargs=-Xmx320m -XX:MaxMetaspaceSize=256m -XX:ReservedCodeCacheSize=64m "
        "-XX:ActiveProcessorCount=1 -XX:+UseSerialGC -Dfile.encoding=UTF-8",
        "assembleDebug",
    ]
    os.chdir(ROOT)
    os.execvpe(args[0], args, env)


if __name__ == "__main__":
    main()
