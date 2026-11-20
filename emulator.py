"""Drive a local Android Studio virtual device through its emulator console."""

import os
from pathlib import Path
import re
from shutil import which
import subprocess


EMULATOR_SERIAL = re.compile(r"emulator-[0-9]{4,5}")


def find_adb():
    installed = which("adb")
    if installed:
        return installed
    sdk_paths = [os.environ.get(name) for name in ("ANDROID_HOME", "ANDROID_SDK_ROOT")]
    if local_app_data := os.environ.get("LOCALAPPDATA"):
        sdk_paths.append(Path(local_app_data) / "Android" / "Sdk")
    for sdk in filter(None, sdk_paths):
        adb = Path(sdk) / "platform-tools" / "adb.exe"
        if adb.is_file():
            return str(adb)
    return "adb"


def run_adb(adb, *arguments):
    if not adb:
        raise RuntimeError("请先选择 adb.exe。")
    try:
        result = subprocess.run(
            [adb, *arguments], capture_output=True, text=True, errors="replace", timeout=7,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError:
        raise RuntimeError("找不到 ADB。请通过「选择」指定 Android SDK 的 adb.exe。") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError("ADB 响应超时。请确认本机模拟器已启动。") from None
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ADB 命令失败。")
    return result.stdout


def list_emulators(adb):
    devices = run_adb(adb, "devices")
    return tuple(
        fields[0] for line in devices.splitlines()
        if len(fields := line.split()) == 2 and fields[1] == "device"
        and EMULATOR_SERIAL.fullmatch(fields[0])
    )


def send_fix(adb, serial, point):
    if not EMULATOR_SERIAL.fullmatch(serial):
        raise ValueError("请填写本机 Android Emulator 序列号，例如 emulator-5554。")
    response = run_adb(adb, "-s", serial, "emu", "geo", "fix", str(point.longitude), str(point.latitude))
    lines = [line.strip() for line in response.splitlines()]
    if "OK" not in lines or any(line.startswith("KO:") for line in lines):
        raise RuntimeError(response.strip() or "模拟器没有确认定位更新。")
