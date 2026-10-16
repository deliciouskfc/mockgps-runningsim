#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把奶龙 SVG 转成 GPS 轨迹文件（奶龙.txt），子路径间插 PAUSE 标记。

跑道参考 track_final.txt：400m 圆，圆心 22.6878086, 114.2029422。
龙形缩放到铺满跑道圆内（直径 ~127m，留边距后约 110m 高）。
眼睛子路径替换为正圆。
"""
import re
import math

SVG_PATH = r"D:\Codex\2026-10-16\new-chat-2\outputs\原图矢量版.svg"
OUT_PATH = r"c:\Users\admin\Documents\trae_projects\run\pc\奶龙.txt"

# 跑道参数
CENTER_LAT = 22.6878086
CENTER_LNG = 114.2029422
M_PER_DEG_LAT = 111320.0
M_PER_DEG_LNG = 111320.0 * math.cos(math.radians(CENTER_LAT))  # ~102730

# 龙形目标路径总长度（米）。不再按高度限制，直接按总长缩放铺满跑道。
TARGET_TOTAL_M = 2000.0


def parse_svg_path(d):
    """解析 SVG path d 属性，返回子路径列表，每个子路径是 [(x,y), ...] 采样点。"""
    # 按大写 M 拆分子路径
    parts = re.split(r'(?=\bM\s)', d)
    subpaths = [p.strip() for p in parts if p.strip()]

    all_points = []
    for sp in subpaths:
        pts = sample_subpath(sp)
        if len(pts) >= 2:
            all_points.append(pts)
    return all_points


def sample_subpath(sp):
    """采样单个子路径，返回点列表。处理 M/L/Q/Z 命令。"""
    tokens = re.findall(r'([MLQZ])|(-?\d+\.?\d*)', sp)
    cmds = []
    cur = []
    for tok in tokens:
        if tok[0]:  # 命令字母
            if cur:
                cmds.append(cur)
            cur = [tok[0]]
        elif tok[1]:  # 数字
            cur.append(float(tok[1]))
    if cur:
        cmds.append(cur)

    pts = []
    cx, cy = 0.0, 0.0
    start_x, start_y = 0.0, 0.0
    for cmd in cmds:
        op = cmd[0]
        args = cmd[1:]
        if op == 'M':
            cx, cy = args[0], args[1]
            start_x, start_y = cx, cy
            pts.append((cx, cy))
        elif op == 'L':
            for i in range(0, len(args), 2):
                cx, cy = args[i], args[i+1]
                pts.append((cx, cy))
        elif op == 'Q':
            # 二次贝塞尔 Q cx cy x y，每段采样 10 点
            for i in range(0, len(args), 4):
                qx, qy, ex, ey = args[i], args[i+1], args[i+2], args[i+3]
                for t in range(1, 11):
                    tt = t / 10.0
                    x = (1-tt)**2 * cx + 2*(1-tt)*tt * qx + tt**2 * ex
                    y = (1-tt)**2 * cy + 2*(1-tt)*tt * qy + tt**2 * ey
                    pts.append((x, y))
                cx, cy = ex, ey
        elif op == 'Z':
            pts.append((start_x, start_y))
            cx, cy = start_x, start_y
    return pts


def svg_to_gps(x, y, cx_svg, cy_svg, scale):
    """SVG 坐标转 GPS。SVG y 向下，GPS 纬度向上，故 y 取反。"""
    dx_m = (x - cx_svg) * scale
    dy_m = -(y - cy_svg) * scale  # 翻转 y
    lat = CENTER_LAT + dy_m / M_PER_DEG_LAT
    lng = CENTER_LNG + dx_m / M_PER_DEG_LNG
    return lat, lng


def make_circle(cx, cy, r_px, n=20):
    """生成正圆点列表。"""
    pts = []
    for i in range(n + 1):
        a = 2 * math.pi * i / n
        pts.append((cx + r_px * math.cos(a), cy + r_px * math.sin(a)))
    return pts


def main():
    with open(SVG_PATH, "r", encoding="utf-8") as f:
        svg = f.read()
    m = re.search(r'd="([^"]+)"', svg)
    d = m.group(1)

    subpaths = parse_svg_path(d)
    print(f"解析得到 {len(subpaths)} 个子路径")

    # 全局边界框
    all_x = [p[0] for sp in subpaths for p in sp]
    all_y = [p[1] for sp in subpaths for p in sp]
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    w, h = max_x - min_x, max_y - min_y
    cx_svg = (min_x + max_x) / 2
    cy_svg = (min_y + max_y) / 2
    print(f"SVG 边界: {min_x:.0f},{min_y:.0f} ~ {max_x:.0f},{max_y:.0f}  尺寸 {w:.0f}x{h:.0f}")

    # 按目标总路径长度反推缩放
    svg_total_px = 0.0
    for sp in subpaths:
        for i in range(1, len(sp)):
            svg_total_px += math.hypot(sp[i][0]-sp[i-1][0], sp[i][1]-sp[i-1][1])
    scale = TARGET_TOTAL_M / svg_total_px
    print(f"SVG 路径总长: {svg_total_px:.0f}px → 缩放 {scale:.5f}m/px → 目标 {TARGET_TOTAL_M:.0f}m")
    print(f"龙形尺寸: 高 {h*scale:.1f}m, 宽 {w*scale:.1f}m")

    # 识别眼睛子路径：Y 中心在头部（y_center < 350，嘴在 y~370）且尺寸合理
    eye_candidates = []
    for i, sp in enumerate(subpaths):
        ys = [p[1] for p in sp]
        xs = [p[0] for p in sp]
        yc = (min(ys) + max(ys)) / 2
        w = max(xs) - min(xs)
        hgt = max(ys) - min(ys)
        # 头部区域 + 非细长条（嘴是宽扁的）+ 尺寸合理
        if yc < 350 and w < 150 and hgt < 150 and w > 3 and hgt > 3:
            eye_candidates.append(i)
    print(f"眼睛候选子路径: {[i+1 for i in eye_candidates]}")

    # 合并眼睛候选为左右眼两个圆
    # 按 X 中心排序后，用最大间隔分成两组（左眼/右眼）
    eye_with_x = []
    for i in eye_candidates:
        xs = [p[0] for p in subpaths[i]]
        eye_with_x.append((i, (min(xs)+max(xs))/2))
    eye_with_x.sort(key=lambda t: t[1])

    # 找最大间隔切分
    split_idx = 1
    max_gap = 0
    for k in range(1, len(eye_with_x)):
        gap = eye_with_x[k][1] - eye_with_x[k-1][1]
        if gap > max_gap:
            max_gap = gap
            split_idx = k
    left_indices = [t[0] for t in eye_with_x[:split_idx]]
    right_indices = [t[0] for t in eye_with_x[split_idx:]]
    print(f"左眼子路径: {[i+1 for i in left_indices]}  右眼子路径: {[i+1 for i in right_indices]}")

    def eye_circle(indices):
        if not indices:
            return None
        xs = [p[0] for i in indices for p in subpaths[i]]
        ys = [p[1] for i in indices for p in subpaths[i]]
        cex = (min(xs) + max(xs)) / 2
        cey = (min(ys) + max(ys)) / 2
        r = max((max(xs)-min(xs)), (max(ys)-min(ys))) / 2
        return cex, cey, max(r, 10)  # 半径至少 10px

    left = eye_circle(left_indices)
    right = eye_circle(right_indices)
    print(f"左眼: {left}  右眼: {right}")

    # 构建最终子路径列表：移除眼睛候选，加入两个正圆
    final_subpaths = []
    eye_set = set(eye_candidates)
    for i, sp in enumerate(subpaths):
        if i not in eye_set:
            final_subpaths.append(sp)
    if left:
        final_subpaths.append(make_circle(*left))
    if right:
        final_subpaths.append(make_circle(*right))
    print(f"最终子路径数: {len(final_subpaths)}")

    # ---------- 段排序优化：旋转闭合路径起点 + 贪心最近邻，最小化段间跳跃 ----------
    def dist_px(a, b):
        return math.hypot(a[0]-b[0], a[1]-b[1])

    def rotate_to_nearest(seg, target_pt):
        """把闭合路径旋转，使离 target_pt 最近的点成为起点。"""
        if len(seg) < 2:
            return seg
        best_i = min(range(len(seg)), key=lambda i: dist_px(seg[i], target_pt))
        return seg[best_i:] + seg[:best_i]

    # 贪心：从离圆心最近的段开始，每次选离当前终点最近的段
    ordered = []
    remaining = list(range(len(final_subpaths)))
    # 起点选离全局中心最近的段（并旋转到离中心最近的点）
    center_pt = (cx_svg, cy_svg)
    first_idx = min(remaining,
                    key=lambda i: min(dist_px(p, center_pt) for p in final_subpaths[i]))
    first_seg = rotate_to_nearest(final_subpaths[first_idx], center_pt)
    ordered.append(first_seg)
    remaining.remove(first_idx)
    cur_pos = first_seg[-1]  # 段终点（闭合路径=起点，但旋转后末点是原起点）

    while remaining:
        # 对每个候选段，旋转到离 cur_pos 最近的点，选跳跃最小的
        best_i = None
        best_jump = float("inf")
        best_seg = None
        for i in remaining:
            seg = final_subpaths[i]
            # 找离 cur_pos 最近的点作为新起点
            rot = rotate_to_nearest(seg, cur_pos)
            jump = dist_px(rot[0], cur_pos)
            if jump < best_jump:
                best_jump = jump
                best_i = i
                best_seg = rot
        ordered.append(best_seg)
        remaining.remove(best_i)
        cur_pos = best_seg[-1]

    # 打印排序后的段间跳跃
    print(f"\n排序后段间跳跃（缩放后米）:")
    total_jump = 0
    for i in range(len(ordered)-1):
        jm = dist_px(ordered[i][-1], ordered[i+1][0]) * scale
        total_jump += jm
        print(f"  段{i+1}末 → 段{i+2}首: {jm:.1f}m")
    print(f"  总跳跃: {total_jump:.1f}m")

    final_subpaths = ordered

    # 写轨迹文件
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(f"# 奶龙轨迹 - 共 {len(final_subpaths)} 段，段间 PAUSE 需用户交互继续\n")
        f.write(f"# 圆心 {CENTER_LAT}, {CENTER_LNG}  缩放 {scale:.4f}m/px  尺寸 {w*scale:.0f}x{h*scale:.0f}m\n")
        f.write(f"# 段已按最近邻排序，段间跳跃最小化\n")
        for idx, sp in enumerate(final_subpaths):
            f.write(f"\n# === 段 {idx+1}/{len(final_subpaths)} ({len(sp)} 点) ===\n")
            for (x, y) in sp:
                lat, lng = svg_to_gps(x, y, cx_svg, cy_svg, scale)
                f.write(f"{lat:.8f},{lng:.8f}\n")
            if idx < len(final_subpaths) - 1:
                f.write("PAUSE\n")

    print(f"\n已写入 {OUT_PATH}")
    # 统计
    total = sum(len(sp) for sp in final_subpaths)
    print(f"总点数: {total}  暂停次数: {len(final_subpaths)-1}")


if __name__ == "__main__":
    main()
