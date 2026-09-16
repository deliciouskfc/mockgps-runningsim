#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""咕咚步频注入常驻器：attach/spawn 咕咚并加载 frida_inject.js。
每秒从 cadence_state.txt 读取 running/cadence 并通过 RPC 同步（供 mock_route 联动）。

用法:
    python frida_inject_run.py            # 优先附加已运行的咕咚，否则冷启动
状态文件 cadence_state.txt（与本脚本同目录）:
    running=1
    cadence=168
"""
import os
import sys
import time
import frida

PKG = "com.codoon.gps"
HERE = os.path.dirname(os.path.abspath(__file__))
JS = os.path.join(HERE, "frida_inject.js")
STATE = os.path.join(HERE, "cadence_state.txt")


def read_state():
    st = {"running": 1, "cadence": 168}
    try:
        with open(STATE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    st[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return st


def log_factory(tag):
    def on_message(message, data):
        if message["type"] == "log":
            print(f"[{tag}] {message.get('payload','')}", flush=True)
        elif message["type"] == "error":
            print(f"[{tag}][error] {message.get('description')}", flush=True)
    return on_message


def main():
    device = frida.get_usb_device(timeout=10)
    spawned = False
    session = None
    try:
        print(f"[inject] attaching to running {PKG} ...", flush=True)
        session = device.attach(PKG)
    except Exception as e:
        print(f"[inject] not running ({e}); spawning ...", flush=True)
        pid = device.spawn([PKG])
        session = device.attach(pid)
        spawned = True

    with open(JS, "r", encoding="utf-8") as f:
        code = f.read()
    script = session.create_script(code)
    script.on("message", log_factory("codoon"))
    script.load()
    if spawned:
        device.resume(pid)

    print("[inject] hook active. Syncing cadence state every 1s. Ctrl+C to stop (app stays open).",
          flush=True)
    last = None
    try:
        while True:
            st = read_state()
            key = (st.get("running"), st.get("cadence"))
            if key != last:
                try:
                    script.exports_sync.setrunning(int(st.get("running", 1)))
                    script.exports_sync.setcadence(float(st.get("cadence", 168)))
                    print(f"[inject] sync running={st.get('running')} cadence={st.get('cadence')}",
                          flush=True)
                except Exception as e:
                    print(f"[inject] rpc failed (app may have closed): {e}", flush=True)
                    break
                last = key
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[inject] stopped by user.")


if __name__ == "__main__":
    main()
