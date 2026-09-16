#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""以 root spawn 一个原生宿主(/system/bin/sleep)，注入 HAL fifo 写入器并常驻。
每秒从 cadence_state.txt 同步 running/cadence。
"""
import os, time, sys, frida

HERE = os.path.dirname(os.path.abspath(__file__))
JS = os.path.join(HERE, "frida_hal_inject.js")
STATE = os.path.join(HERE, "cadence_state.txt")

def read_state():
    st = {"running":1,"cadence":168}
    try:
        for line in open(STATE,"r",encoding="utf-8"):
            line=line.strip()
            if "=" in line and not line.startswith("#"):
                k,v=line.split("=",1); st[k.strip()]=v.strip()
    except FileNotFoundError: pass
    return st

def main():
    dev = frida.get_usb_device(timeout=10)
    print("[hal] spawning native host /system/bin/sleep ...", flush=True)
    pid = dev.spawn(["/system/bin/sleep","999999"])
    print(f"[hal] host pid={pid}", flush=True)
    session = dev.attach(pid)
    code = open(JS,"r",encoding="utf-8").read()
    sc = session.create_script(code)
    def on_msg(m,d):
        if m["type"]=="log": print(m.get("payload",""), flush=True)
        elif m["type"]=="error": print("[error]", m.get("description"), m.get("stack",""), flush=True)
    sc.on("message", on_msg)
    sc.load()
    dev.resume(pid)
    time.sleep(1.0)
    print("[hal] status:", sc.exports_sync.status(), flush=True)

    last=None
    try:
        while True:
            st=read_state(); key=(st.get("running"),st.get("cadence"))
            if key!=last:
                sc.exports_sync.setrunning(int(st.get("running",1)))
                sc.exports_sync.setcadence(float(st.get("cadence",168)))
                print(f"[hal] sync run={st.get('running')} cadence={st.get('cadence')}", flush=True)
                last=key
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[hal] stop")

if __name__=="__main__":
    main()
