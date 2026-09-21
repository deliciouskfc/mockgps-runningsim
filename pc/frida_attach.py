#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""attach 已运行的咕咚并加载外部 JS（不重启 app，不打断跑步）。
用法: python frida_attach.py <script.js> [seconds] [device]
      seconds 省略=常驻；device 省略=自动检测第一个在线设备
"""
import os, sys, time, subprocess, frida

# 强制 UTF-8 输出
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PKG = "com.codoon.gps"

def find_device():
    """自动检测第一个在线 adb 设备名。"""
    try:
        r = subprocess.run(["adb", "devices"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=3)
        for line in r.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("List") and "device" in line:
                # 格式: "emulator-5554  device" 或 "127.0.0.1:5555  device"
                return line.split()[0]
    except Exception:
        pass
    return None

def main():
    js_path = sys.argv[1]
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else None
    device = sys.argv[3] if len(sys.argv) > 3 else None

    # 自动检测设备
    if not device:
        device = find_device()
    if not device:
        print("[attach] 错误：未检测到 adb 设备，请先启动 BlueStacks", flush=True)
        sys.exit(1)

    dev = frida.get_usb_device(timeout=10)
    out = subprocess.run(["adb", "-s", device, "shell", "pidof", PKG],
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=10)
    pid_str = out.stdout.strip()
    if not pid_str:
        print(f"[attach] 错误：未找到 {PKG} 进程，请先在模拟器里打开咕咚", flush=True)
        sys.exit(2)
    pid = int(pid_str.split()[0])
    print(f"[attach] pid={pid} script={js_path}")
    session = dev.attach(pid)
    with open(js_path,"r",encoding="utf-8") as f:
        code = f.read()
    sc = session.create_script(code)
    def on_msg(m,d):
        if m["type"]=="log": print(m.get("payload",""), flush=True)
        elif m["type"]=="send": print("[send]", m.get("payload"), flush=True)
        elif m["type"]=="error": print("[error]", m.get("description"), "\n", m.get("stack",""), flush=True)
    sc.on("message", on_msg)
    sc.load()
    print("[attach] loaded. Ctrl+C to stop.\n", flush=True)
    try:
        if secs:
            time.sleep(secs)
        else:
            while True: time.sleep(1)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
