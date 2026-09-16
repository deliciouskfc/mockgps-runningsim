# -*- coding: utf-8 -*-
"""生成操场绕圈路线：标准 400m 田径场（两直道 + 两半圆弯道）"""
import math, sys

# 操场中心坐标（香港中文大学深圳 田径场估计位置，可用参数覆盖）
LAT0 = float(sys.argv[1]) if len(sys.argv) > 1 else 22.6910
LNG0 = float(sys.argv[2]) if len(sys.argv) > 2 else 114.2075
OUT  = sys.argv[3] if len(sys.argv) > 3 else "route_hz_track.txt"

R = 36.5          # 弯道半径（米）
STRAIGHT = 84.39  # 直道长度（米）
N = 48            # 每圈采样点数（平滑度）

# 周长 = 2*直道 + 2*π*R ≈ 398.1m
total = 2 * STRAIGHT + 2 * math.pi * R

def m2lat(dy): return dy / 111320.0
def m2lng(dx, lat): return dx / (111320.0 * math.cos(math.radians(lat)))

pts = []
for i in range(N):
    s = i / N * total          # 沿跑道的弧长位置
    if s < STRAIGHT:            # 下直道（东行）：y=-R
        x, y = -STRAIGHT/2 + s, -R
    elif s < STRAIGHT + math.pi*R:   # 东弯道：圆心(+S/2,0)，-90°→+90°
        a = (s - STRAIGHT) / R           # 弧角
        x, y = STRAIGHT/2 + R*math.sin(a), -R*math.cos(a)
    elif s < 2*STRAIGHT + math.pi*R: # 上直道（西行）：y=+R
        x, y = STRAIGHT/2 - (s - STRAIGHT - math.pi*R), R
    else:                        # 西弯道：圆心(-S/2,0)，90°→270°
        a = (s - 2*STRAIGHT - math.pi*R) / R
        x, y = -STRAIGHT/2 - R*math.sin(a), R*math.cos(a)
    pts.append((LAT0 + m2lat(y), LNG0 + m2lng(x, LAT0)))

with open(OUT, "w", encoding="utf-8") as f:
    f.write("# 港中深操场绕圈：中心(%.6f,%.6f) 每圈约%.0fm，12km/h一圈约2分钟\n" % (LAT0, LNG0, total))
    f.write("# 起跑方向：沿下直道向东\n")
    for la, ln in pts:
        f.write("%.7f,%.7f\n" % (la, ln))

print("生成 %s: %d 点/圈, 周长 %.1fm, 中心 (%.6f, %.6f)" % (OUT, N, total, LAT0, LNG0))
