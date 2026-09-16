#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""反汇编 BlueStacks 64-bit sensors HAL，定位 bstfifo reader 的 read 长度与字段解析。
通过字符串 RIP 相对引用定位代码，解析 .rela.plt 得到调用目标函数名。
"""
import struct, sys
from capstone import *
from capstone.x86 import *

PATH = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\admin\Documents\trae_projects\run\tools\sensors64.so"
d = open(PATH, "rb").read()

# ---------- ELF64 解析 ----------
assert d[:4] == b"\x7fELF"
e_shoff = struct.unpack_from("<Q", d, 0x28)[0]
e_shentsize = struct.unpack_from("<H", d, 0x3A)[0]
e_shnum = struct.unpack_from("<H", d, 0x3C)[0]
e_shstrndx = struct.unpack_from("<H", d, 0x3E)[0]

secs = []
for i in range(e_shnum):
    off = e_shoff + i*e_shentsize
    name,typ,flags,addr,offset,size,link,info,align,entsize = struct.unpack_from("<IIQQQQIIQQ", d, off)
    secs.append(dict(name=name,typ=typ,flags=flags,addr=addr,offset=offset,size=size,
                     link=link,info=info,entsize=entsize))
shstr = secs[e_shstrndx]
def secname(s):
    o = shstr["offset"] + s["name"]
    end = d.index(b"\x00", o)
    return d[o:end].decode()
for s in secs:
    s["sname"] = secname(s)

def findsec(n):
    for s in secs:
        if s["sname"] == n: return s
    return None

text = findsec(".text")
# ---------- 解析 .dynsym/.dynstr ----------
dynsym = findsec(".dynsym"); dynstr = findsec(".dynstr")
def dynstr_name(idx):
    o = dynstr["offset"]+idx; return d[o:d.index(b'\x00',o)].decode('latin1')
syms = {}
if dynsym:
    cnt = dynsym["size"]//dynsym["entsize"]
    for i in range(cnt):
        o = dynsym["offset"]+i*dynsym["entsize"]
        st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack_from("<IBBHQQ", d, o)
        if st_name:
            syms[st_value] = dynstr_name(st_name)

# ---------- 解析 .rela.plt 建立 GOT->函数名 + PLT入口->函数名 ----------
relaplt = findsec(".rela.plt")
plt = findsec(".plt")
got_to_name = {}
plt_to_name = []
if relaplt:
    cnt = relaplt["size"]//24
    for i in range(cnt):
        o = relaplt["offset"]+i*24
        r_offset, r_info, r_addend = struct.unpack_from("<QQq", d, o)
        symidx = r_info >> 32
        name = dynstr_name(struct.unpack_from("<I", d, dynsym["offset"]+symidx*dynsym["entsize"])[0])
        got_to_name[r_offset] = name
        plt_to_name.append(name)

def call_target_name(target):
    # target 若落在 .plt，按 16 字节 entry 映射（plt[0] 保留）
    if plt and plt["addr"] <= target < plt["addr"]+plt["size"]:
        idx = (target - plt["addr"])//16
        # idx 0 是 PLT0；rela 顺序对应 idx-1
        j = idx-1
        if 0 <= j < len(plt_to_name):
            return plt_to_name[j]
    if target in syms:
        return syms[target]
    return None

# ---------- capstone 反汇编 .text ----------
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
code = d[text["offset"]:text["offset"]+text["size"]]
base = text["addr"]

STR_TARGETS = {
    0x41c2:"FIFO_PATH",
    0x427b:"READ_ERR",
    0x42a2:"INCOMPLETE",
    0x41f9:"TAG_READER",
    0x422f:"TRY_OPEN",
    0x424c:"OPERATOR",
    0x4257:"OPEN_FAIL",
}

insns = list(md.disasm(code, base))
addr_index = {ins.address: i for i,ins in enumerate(insns)}

# 找引用关键字符串的指令
hits = []
for i, ins in enumerate(insns):
    try:
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                tgt = ins.address + ins.size + op.mem.disp
                if tgt in STR_TARGETS:
                    hits.append((i, ins.address, STR_TARGETS[tgt], ins))
    except Exception:
        pass

print("===== string-reference hits =====")
for i,a,tag,ins in hits:
    print(f"{a:#08x} [{tag:11}] {ins.mnemonic} {ins.op_str}")

# dump 含 INCOMPLETE / READ_ERR / TRY_OPEN 的函数窗口
want = [h for h in hits if h[2] in ("INCOMPLETE","READ_ERR","TRY_OPEN","TAG_READER","OPEN_FAIL")]
ranges = sorted(set(i for i,_,_,_ in want))
if ranges:
    lo = max(0, min(ranges)-120)
    hi = min(len(insns), max(ranges)+40)
    print(f"\n===== disasm window [{insns[lo].address:#x} .. {insns[hi].address:#x}] =====")
    for ins in insns[lo:hi]:
        ann = ""
        if ins.mnemonic in ("call","jmp") and ins.operands and ins.operands[0].type==X86_OP_IMM:
            nm = call_target_name(ins.operands[0].imm)
            if nm: ann = "  ; -> "+nm
        marker = ""
        for ii,aa,tag,_ in hits:
            if aa==ins.address: marker = f"  ; <<< {tag}"
        print(f"{ins.address:#08x}  {ins.mnemonic:8} {ins.op_str}{ann}{marker}")
