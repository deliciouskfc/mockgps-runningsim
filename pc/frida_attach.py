#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""attach 已运行的咕咚并加载外部 JS（不重启 app，不打断跑步）。
用法: python frida_attach.py <script.js> [seconds]   seconds 省略=常驻
"""
import sys, time, subprocess, frida

# 强制 UTF-8 输出
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PKG = "com.codoon.gps"

def main():
    js_path = sys.argv[1]
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else None
    dev = frida.get_usb_device(timeout=10)
    out = subprocess.run(["adb","-s","emulator-5554","shell","pidof",PKG],
                         capture_output=True, text=True, timeout=10)
    pid = int(out.stdout.strip().split()[0])
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
