"""Diagnostic ADB discovery survives reboots and validates explicit overrides."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "runtime_tools", Path(__file__).resolve().parents[1] / "audit/runtime_tools.py"
)
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


def test_explicit_missing_adb_does_not_silently_pick_another_install(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("SPEN_ADB", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="SPEN_ADB"):
        tools.adb_path()


def test_path_install_and_serial_are_argv_values(monkeypatch):
    monkeypatch.delenv("SPEN_ADB", raising=False)
    monkeypatch.setattr(
        tools.shutil, "which", lambda _: "/persistent/platform-tools/adb"
    )
    monkeypatch.setenv("SPEN_ADB_SERIAL", "known-device")
    assert tools.adb_command() == [
        "/persistent/platform-tools/adb",
        "-s",
        "known-device",
    ]
    assert tools.adb_command("other-device")[-1] == "other-device"
