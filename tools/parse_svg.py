#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析 SVG path，输出子路径数量、边界框、每个子路径的点数。"""
import re
import sys

SVG_PATH = r"D:\Codex\2026-10-16\new-chat-2\outputs\原图矢量版.svg"

with open(SVG_PATH, "r", encoding="utf-8") as f:
    svg = f.read()

m = re.search(r'd="([^"]+)"', svg)
d = m.group(1)

# 按 M 命令拆分子路径（大写 M = 绝对坐标新起点）
subpaths = re.split(r'(?=\bM\s)', d)
subpaths = [s.strip() for s in subpaths if s.strip()]
print(f"子路径数量: {len(subpaths)}")

# 全局边界框
all_x, all_y = [], []
for sp in subpaths:
    nums = [float(x) for x in re.findall(r'-?\d+\.?\d*', sp)]
    xs = nums[0::2]
    ys = nums[1::2]
    all_x.extend(xs)
    all_y.extend(ys)

print(f"X 范围: {min(all_x):.1f} ~ {max(all_x):.1f}  (宽 {max(all_x)-min(all_x):.1f})")
print(f"Y 范围: {min(all_y):.1f} ~ {max(all_y):.1f}  (高 {max(all_y)-min(all_y):.1f})")
print()
print(f"{'#':>3}  {'点数':>5}  {'X范围':>20}  {'Y范围':>20}")
print("-" * 60)
for i, sp in enumerate(subpaths):
    nums = [float(x) for x in re.findall(r'-?\d+\.?\d*', sp)]
    xs = nums[0::2]
    ys = nums[1::2]
    print(f"{i+1:>3}  {len(xs):>5}  {min(xs):>8.1f}~{max(xs):<8.1f}  {min(ys):>8.1f}~{max(ys):<8.1f}")
