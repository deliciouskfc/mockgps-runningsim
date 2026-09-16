#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提取 BlueStacks sensors HAL (.so) 的可打印字符串与 ELF 符号，辅助逆向 bstfifo 协议。"""
import sys, re, struct

path = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\admin\Documents\trae_projects\run\tools\sensors64.so"
data = open(path, "rb").read()
print(f"file size = {len(data)}")

# ---- 提取字符串 ----
print("\n===== STRINGS (>=4) =====")
for m in re.finditer(rb"[\x20-\x7e]{4,}", data):
    s = m.group().decode("ascii", "replace")
    print(f"{m.start():#06x}  {s}")
