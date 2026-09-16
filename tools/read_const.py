#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import struct
PATH = r"c:\Users\admin\Documents\trae_projects\run\tools\sensors64.so"
d = open(PATH,"rb").read()
# ELF sections for vaddr->offset
e_shoff=struct.unpack_from("<Q",d,0x28)[0]
e_shentsize=struct.unpack_from("<H",d,0x3A)[0]
e_shnum=struct.unpack_from("<H",d,0x3C)[0]
e_shstrndx=struct.unpack_from("<H",d,0x3E)[0]
secs=[]
for i in range(e_shnum):
    o=e_shoff+i*e_shentsize
    vals=struct.unpack_from("<IIQQQQIIQQ",d,o)
    secs.append(dict(zip(["name","type","flags","addr","offset","size","link","info","align","entsize"],vals)))
shstr=secs[e_shstrndx]
def sname(s):
    o=shstr["offset"]+s["name"]; return d[o:d.index(b"\0",o)].decode()
def v2o(v):
    for s in secs:
        if s["addr"]!=0 and s["addr"]<=v<s["addr"]+s["size"]:
            return s["offset"]+(v-s["addr"]), sname(s)
    return None,None

for v in (0x3fd0,0x3fd8):
    o,sec=v2o(v)
    c=struct.unpack_from("<d", d, o)[0]
    print(f"const @{v:#x} (file off {o:#x}, sec {sec}) = {c!r}")

# 编码公式： raw = value * C1 / C2
o1,_=v2o(0x3fd0); o2,_=v2o(0x3fd8)
C1=struct.unpack_from("<d",d,o1)[0]; C2=struct.unpack_from("<d",d,o2)[0]
print(f"\nC1={C1}  C2={C2}")
print("encode: int32 = round(value * C1 / C2)")
for target in (0.0, 9.81, 12.0, -5.0):
    raw=round(target*C1/C2)
    back=(raw/C1)*C2
    print(f"  value {target:6.2f} -> raw int32 {raw} -> back {back:.4f}")
