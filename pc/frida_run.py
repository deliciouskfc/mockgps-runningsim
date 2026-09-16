#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用 Frida spawn runner：注入 JS 到指定包，打印 console/send 消息。
用法: python frida_run.py <package> <script.js> [seconds]
"""
import sys
import time
import frida


def main():
    pkg = sys.argv[1]
    js_path = sys.argv[2]
    seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0

    device = frida.get_usb_device(timeout=10)
    print(f"[runner] device={device.name}  spawning {pkg} ...")
    pid = device.spawn([pkg])
    session = device.attach(pid)

    def on_message(message, data):
        if message["type"] == "log":
            print(message.get("payload", ""), flush=True)
        elif message["type"] == "send":
            print(f"[send] {message.get('payload')}", flush=True)
        elif message["type"] == "error":
            print(f"[error] {message.get('description')}\n{message.get('stack','')}", flush=True)
        else:
            print(f"[msg] {message}", flush=True)

    with open(js_path, "r", encoding="utf-8") as f:
        code = f.read()
    script = session.create_script(code)
    script.on("message", on_message)
    script.load()
    device.resume(pid)
    print(f"[runner] resumed pid={pid}, collecting {seconds}s ...\n")
    try:
        time.sleep(seconds)
    except KeyboardInterrupt:
        pass
    print("\n[runner] done (detaching, app stays open)")
    try:
        session.detach()
    except Exception:
        pass


if __name__ == "__main__":
    main()
