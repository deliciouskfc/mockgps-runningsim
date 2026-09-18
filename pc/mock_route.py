#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MockGPS 电脑端脚本
==================
按指定速度沿路线移动手机的模拟定位。纯软件模拟，手机无需移动。

速度：5 分钟 / 公里 = 12 km/h ≈ 3.333 m/s

依赖：
    - 电脑已安装 adb 且加入 PATH
    - 手机已开启 USB 调试并连接（或无线调试）
    - 手机已安装 MockGPS 应用，并在开发者选项中设为「模拟位置应用」

用法：
    python mock_route.py route.txt
    python mock_route.py route.gpx --interval 1.0
    python mock_route.py route.kml --speed-kmh 12
"""

import argparse
import math
import os
import random
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

# 强制 stdout/stderr UTF-8 输出，避免 Windows 中文系统默认 GBK 编码导致
# GUI 端 Popen(encoding="utf-8") 读 PIPE 时报 decode 错误
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
# 子进程调用也用 UTF-8 decode，避免 adb 输出中文时被系统编码误伤
_SUBPROC_ENC = "utf-8"

# 默认速度：5 分钟一公里 = 12 km/h
DEFAULT_SPEED_KMH = 12.0
EARTH_RADIUS_M = 6371000.0


@dataclass
class Point:
    lat: float
    lng: float


class AltitudeSim:
    """纯随机游走海拔：无周期性正弦，仅靠强均值回归 + 限幅，
    在 base ± amp 范围内自然漂移。每步增量小且随机方向，
    整体呈真人跑步在起伏路面的不规则海拔变化。
    """

    def __init__(self, base: float = 47.0, amp: float = 5.0):
        self.base = base
        self.amp = amp
        self.drift = 0.0  # 当前相对 base 的偏移

    def at(self, t: float) -> float:
        if self.amp <= 0:
            return self.base
        # 随机步长增量（±0.6m/步），方向完全随机
        self.drift += random.uniform(-1.0, 1.0) * 0.6
        # 弱均值回归（每步衰减 1%），允许 drift 自由探索 ±amp 空间
        self.drift *= 0.99
        # 硬限幅在 ±amp 内
        if self.drift > self.amp:
            self.drift = self.amp
        elif self.drift < -self.amp:
            self.drift = -self.amp
        return self.base + self.drift


def haversine(p1: Point, p2: Point) -> float:
    """计算两点间球面距离（米）"""
    lat1, lng1 = math.radians(p1.lat), math.radians(p1.lng)
    lat2, lng2 = math.radians(p2.lat), math.radians(p2.lng)
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bearing(p1: Point, p2: Point) -> float:
    """计算 p1 -> p2 的方位角（度，0=北）"""
    lat1, lng1 = math.radians(p1.lat), math.radians(p1.lng)
    lat2, lng2 = math.radians(p2.lat), math.radians(p2.lng)
    dlng = lng2 - lng1
    y = math.sin(dlng) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlng)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


# ---------- 路线解析 ----------

def parse_route(path: str) -> list:
    """根据扩展名解析路线，返回 Point 列表"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".gpx":
        return parse_gpx(path)
    if ext in (".kml", ".kmz"):
        return parse_kml(path)
    return parse_txt(path)


def parse_txt(path: str) -> list:
    """解析纯文本路线，每行一个点：纬度,经度（逗号或空格分隔）"""
    points = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = re.split(r"[,\s]+", line)
            if len(parts) < 2:
                continue
            try:
                lat = float(parts[0])
                lng = float(parts[1])
                points.append(Point(lat, lng))
            except ValueError:
                continue
    return points


def parse_gpx(path: str) -> list:
    """解析 GPX 文件中的航点/航迹点"""
    tree = ET.parse(path)
    root = tree.getroot()
    ns = ""
    m = re.match(r"\{(.+?)\}", root.tag)
    if m:
        ns = m.group(1)
    points = []

    def findall(tag):
        return root.iter(f"{{{ns}}}{tag}" if ns else tag)

    for pt in findall("trkpt"):
        lat = float(pt.get("lat"))
        lng = float(pt.get("lon"))
        points.append(Point(lat, lng))
    for pt in findall("rtept"):
        lat = float(pt.get("lat"))
        lng = float(pt.get("lon"))
        points.append(Point(lat, lng))
    for pt in findall("wpt"):
        lat = float(pt.get("lat"))
        lng = float(pt.get("lon"))
        points.append(Point(lat, lng))
    return points


def parse_kml(path: str) -> list:
    """解析 KML 文件中的 LineString 坐标"""
    tree = ET.parse(path)
    root = tree.getroot()
    ns = ""
    m = re.match(r"\{(.+?)\}", root.tag)
    if m:
        ns = m.group(1)
    points = []
    for coords in root.iter(f"{{{ns}}}coordinates" if ns else "coordinates"):
        text = coords.text.strip()
        for token in re.split(r"\s+", text):
            if not token:
                continue
            parts = token.split(",")
            if len(parts) >= 2:
                lng = float(parts[0])
                lat = float(parts[1])
                points.append(Point(lat, lng))
    return points


# ---------- 插值 ----------

def build_segments(points: list):
    """返回 (累计距离列表, 每段距离列表)"""
    cum = [0.0]
    segs = []
    for i in range(1, len(points)):
        d = haversine(points[i - 1], points[i])
        segs.append(d)
        cum.append(cum[-1] + d)
    return cum, segs


def point_at_distance(points: list, cum: list, segs: list, dist: float) -> Point:
    """在折线上找到距离起点 dist 米处的点"""
    if dist <= 0:
        return points[0]
    total = cum[-1]
    if dist >= total:
        return points[-1]
    for i in range(len(segs)):
        if dist <= cum[i + 1]:
            seg_len = segs[i]
            if seg_len == 0:
                return points[i]
            t = (dist - cum[i]) / seg_len
            lat = points[i].lat + t * (points[i + 1].lat - points[i].lat)
            lng = points[i].lng + t * (points[i + 1].lng - points[i].lng)
            return Point(lat, lng)
    return points[-1]


# ---------- 推送层（adb forward + Socket，绕开 MIUI 后台广播冻结）----------

import socket

SOCKET_PORT = 17890


def adb_base(device: str = None):
    cmd = ["adb"]
    if device:
        cmd += ["-s", device]
    return cmd


def setup_forward(device: str = None) -> bool:
    """建立 adb 端口转发：电脑 127.0.0.1:17890 -> 手机 17890"""
    cmd = adb_base(device) + ["forward", f"tcp:{SOCKET_PORT}", f"tcp:{SOCKET_PORT}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding=_SUBPROC_ENC, errors="replace", timeout=5)
        if r.returncode == 0:
            return True
        print(f"[错误] adb forward 失败：{r.stderr.strip()}")
    except Exception as e:
        print(f"[错误] adb forward 异常：{e}")
    return False


class SocketPusher:
    """通过 adb forward 的本地 TCP 长连接向手机推送坐标"""

    def __init__(self, port: int = SOCKET_PORT):
        self.port = port
        self.sock: socket.socket = None

    def _connect(self):
        self.close()
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.settimeout(5)
        self.sock = s

    def push(self, lat: float, lng: float, accuracy: float, bearing_deg: float,
             speed: float, altitude: float = 0.0) -> bool:
        line = (f"{lat:.8f},{lng:.8f},{accuracy:.2f},"
                f"{bearing_deg:.2f},{speed:.3f},{altitude:.2f}\n")
        data = line.encode()
        for attempt in range(2):
            try:
                if self.sock is None:
                    self._connect()
                self.sock.sendall(data)
                return True
            except Exception:
                self.close()
                try:
                    self._connect()
                    self.sock.sendall(data)
                    return True
                except Exception as e:
                    if attempt == 1:
                        print(f"[Socket 错误] {e}")
                        return False

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


def check_adb(device: str = None):
    """检查 adb 与设备连接"""
    cmd = adb_base(device) + ["get-state"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding=_SUBPROC_ENC, errors="replace", timeout=5)
        if r.returncode == 0 and "device" in r.stdout:
            return True
        print(f"[错误] 设备未就绪：{r.stdout.strip()} {r.stderr.strip()}")
    except FileNotFoundError:
        print("[错误] 未找到 adb，请先安装 Android Platform Tools 并加入 PATH")
    except Exception as e:
        print(f"[错误] adb 调用失败：{e}")
    return False


def _adb_shell(device, args):
    subprocess.run(adb_base(device) + ["shell"] + args,
                   capture_output=True, text=True,
                   encoding=_SUBPROC_ENC, errors="replace", timeout=8)


def prepare_device(device: str = None):
    """设备准备：亮屏常亮（防止 MIUI 因 screen_off 冻结进程）、启动 App 服务。"""
    print("正在准备设备（亮屏/常亮/启动服务）...")
    # 唤醒并保持屏幕常亮：MIUI 在屏幕熄灭时会 freezeUid，导致后台进程无法处理推送
    _adb_shell(device, ["input", "keyevent", "KEYCODE_WAKEUP"])
    _adb_shell(device, ["svc", "power", "stayon", "true"])
    _adb_shell(device, ["settings", "put", "system", "screen_off_timeout", "1800000"])
    # 尝试关闭系统冻结器（部分机型生效）
    _adb_shell(device, ["device_config", "put", "activity_manager_native_boot", "use_freezer", "false"])
    # 加入 Doze 白名单
    _adb_shell(device, ["dumpsys", "deviceidle", "whitelist", "+com.mockgps"])
    # 启动 App（打开即自动启动前台服务与 Socket 服务器）
    _adb_shell(device, ["am", "start", "-n", "com.mockgps/.MainActivity"])
    # 等待服务与端口就绪
    for _ in range(15):
        time.sleep(1)
        if setup_forward(device):
            try:
                test = socket.create_connection(("127.0.0.1", SOCKET_PORT), timeout=2)
                test.close()
                print("设备就绪，MockGPS 服务已连接。")
                return True
            except Exception:
                pass
    print("[警告] 未能确认 MockGPS 服务，请手动打开手机上的 MockGPS App。")
    return False


# ---------- 主流程 ----------

def main():
    parser = argparse.ArgumentParser(description="按路线模拟手机定位移动")
    parser.add_argument("route", help="路线文件路径（支持 .gpx / .kml / .txt）")
    parser.add_argument("--speed-kmh", type=float, default=DEFAULT_SPEED_KMH,
                        help=f"移动速度 km/h（默认 {DEFAULT_SPEED_KMH}，即 5 分钟/公里）")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="推送间隔秒数（默认 1.0）")
    parser.add_argument("--accuracy", type=float, default=5.0, help="模拟定位精度米（默认 5）")
    parser.add_argument("--device", "-s", help="指定 adb 设备序列号")
    parser.add_argument("--once", action="store_true", help="只走一遍路线，不循环")
    parser.add_argument("--loops", type=int, default=1, help="循环次数（默认 1，0=无限）")
    parser.add_argument("--wobble", type=float, default=3.0,
                        help="跑步晃动幅度（米，默认3.0）。模拟真人左右晃动，0=关闭")
    parser.add_argument("--speed-var", type=float, default=1.5,
                        help="速度随机波动幅度 km/h（默认1.5），均值回归保证配速")
    parser.add_argument("--offset-lat", type=float, default=0.0,
                        help="纬度偏移补偿（度）。正值=北移，负值=南移。用于修正 App 显示偏移")
    parser.add_argument("--offset-lng", type=float, default=0.0,
                        help="经度偏移补偿（度）。正值=东移，负值=西移。用于修正 App 显示偏移")
    parser.add_argument("--disable-wifi", action="store_true",
                        help="运行期间关闭手机 WiFi（切断地图 SDK 的 WiFi 定位源，迫使其回退到 GPS）")
    parser.add_argument("--altitude-base", type=float, default=47.0,
                        help="基准海拔米（默认47）。模拟操场真实海拔，避免运动 App 显示海拔恒为0")
    parser.add_argument("--altitude-var", type=float, default=5.0,
                        help="海拔随机波动幅度 ±米（默认5）。纯随机游走+均值回归，0=关闭海拔模拟")
    args = parser.parse_args()

    points = parse_route(args.route)
    if len(points) < 2:
        print(f"[错误] 路线至少需要 2 个点，当前解析到 {len(points)} 个")
        sys.exit(1)

    cum, segs = build_segments(points)
    total_dist = cum[-1]
    speed_ms = args.speed_kmh * 1000 / 3600
    step_dist = speed_ms * args.interval
    total_time = total_dist / speed_ms

    print(f"路线点数: {len(points)}")
    print(f"总距离: {total_dist:.1f} m ({total_dist / 1000:.2f} km)")
    print(f"速度: {args.speed_kmh:.1f} km/h ({speed_ms:.2f} m/s)")
    print(f"预计单次耗时: {total_time:.0f} s ({total_time / 60:.1f} min)")
    print(f"推送间隔: {args.interval}s，每次前进约 {step_dist:.2f} m")
    if args.altitude_var > 0:
        print(f"海拔模拟: 基准 {args.altitude_base:.1f}m，波动 ±{args.altitude_var:.1f}m（缓坡+随机游走）")

    if not check_adb(args.device):
        sys.exit(2)

    prepare_device(args.device)

    # 可选：关闭 WiFi，切断地图 SDK 的 WiFi 定位源，迫使其回退到 GPS provider
    wifi_was_on = False
    if args.disable_wifi:
        try:
            r = subprocess.run(adb_base(args.device) + ["shell", "settings", "get", "wifi_on"],
                               capture_output=True, text=True,
                               encoding=_SUBPROC_ENC, errors="replace", timeout=5)
            wifi_was_on = (r.stdout.strip() == "1")
            _adb_shell(args.device, ["svc", "wifi", "disable"])
            print("[WiFi] 已关闭手机 WiFi（切断地图 WiFi 定位源，结束后自动恢复）")
        except Exception as e:
            print(f"[WiFi] 关闭失败：{e}")

    # 海拔模拟器（全程连续，跨圈不重置，避免海拔跳变）
    alt_sim = AltitudeSim(args.altitude_base, args.altitude_var)
    run_t0 = time.time()

    pusher = SocketPusher(SOCKET_PORT)
    alt0 = alt_sim.at(0.0)
    if not pusher.push(points[0].lat + args.offset_lat, points[0].lng + args.offset_lng,
                       args.accuracy, 0.0, speed_ms, alt0):
        print("[错误] 无法连接手机 MockGPS 服务，请确认 App 已打开且屏幕亮起")
        sys.exit(4)
    print(f"已连接手机 MockGPS 服务（Socket 通道，起始海拔 {alt0:.1f}m）\n")

    # 跑步晃动参数
    wobble_amp = args.wobble          # 振幅（米）
    wobble_phase = 0.0                 # 累积相位（步频 ~0.9Hz，一步约1.1s）
    wobble_rand = 0.0                  # 随机分量（慢速漂移）

    # 速度随机波动参数（均值回归，保证平均配速）
    speed_base = args.speed_kmh        # 基准速度
    speed_var = args.speed_var         # 波动幅度
    speed_cur = speed_base             # 当前速度
    speed_drift = 0.0                  # 速度漂移量

    # 步频/步长参数（用于计算显示，实际注入需要 root）
    # 典型跑步步频 160-180 spm，步长 ≈ 1.2-1.4m
    # 步频与速度正相关：cadence = 160 + (speed_kmh - 10) * 4

    loops = args.loops
    loop_idx = 0
    try:
        while True:
            if loops > 0 and loop_idx >= loops:
                break
            loop_idx += 1
            print(f"===== 开始第 {loop_idx} 圈 =====")
            dist = 0.0
            last_point = None
            t0 = time.time()
            while dist < total_dist:
                p = point_at_distance(points, cum, segs, dist)
                b = bearing(last_point, p) if last_point else 0.0

                # --- 速度随机波动（均值回归） ---
                # 随机游走，但向基准速度回归
                speed_drift += random.uniform(-1.0, 1.0) * speed_var * 0.15
                speed_drift *= 0.85  # 回归系数
                # 限制最大偏差
                speed_drift = max(-speed_var, min(speed_var, speed_drift))
                speed_cur = speed_base + speed_drift
                cur_ms = speed_cur * 1000 / 3600
                cur_step_dist = cur_ms * args.interval
                # 步频计算（随速度变化）
                cadence = int(160 + (speed_cur - 10) * 4)  # spm
                step_len = (speed_cur * 1000 / 60) / cadence  # 米/步

                # --- 模拟真人跑步左右晃动 ---
                d_lat = args.offset_lat
                d_lng = args.offset_lng
                if wobble_amp > 0:
                    # 步频相位跟随当前步频
                    step_freq_hz = cadence / 120.0  # spm → Hz（左右各一步）
                    wobble_phase += args.interval * step_freq_hz * 2 * math.pi
                    # 随机漂移：均值回归的随机游走
                    wobble_rand += random.uniform(-0.3, 0.3) * wobble_amp * 0.1
                    wobble_rand *= 0.92  # 回归
                    # 合成偏移量（米），垂直于行进方向
                    wobble_m = wobble_amp * math.sin(wobble_phase) + wobble_rand
                    # 垂直方向 = bearing + 90°
                    perp_rad = math.radians(b + 90.0)
                    north_m = wobble_m * math.cos(perp_rad)
                    east_m = wobble_m * math.sin(perp_rad)
                    d_lat += north_m / 111320.0
                    d_lng += east_m / (111320.0 * math.cos(math.radians(p.lat)))

                cur_alt = alt_sim.at(time.time() - run_t0)
                ok = pusher.push(p.lat + d_lat, p.lng + d_lng, args.accuracy, b, cur_ms, cur_alt)
                if not ok:
                    print("推送失败，停止。请检查设备连接与应用状态。")
                    return
                progress = dist / total_dist * 100
                print(f"  [{loop_idx}] 进度 {progress:5.1f}%  ({dist:8.1f}/{total_dist:.1f}m)  "
                      f"lat={p.lat:.7f} lng={p.lng:.7f} bearing={b:.1f}  "
                      f"速度={speed_cur:.1f}km/h 步频={cadence}spm 步长={step_len:.2f}m 海拔={cur_alt:.1f}m")
                last_point = p
                dist += cur_step_dist
                # 校准时间
                elapsed = time.time() - t0
                expected = (dist / cur_step_dist) * args.interval
                sleep_t = expected - elapsed
                if sleep_t > 0:
                    time.sleep(sleep_t)

            # 终点
            p = points[-1]
            end_alt = alt_sim.at(time.time() - run_t0)
            pusher.push(p.lat, p.lng, args.accuracy, 0.0, speed_ms, end_alt)
            print(f"  [{loop_idx}] 到达终点 lat={p.lat:.7f} lng={p.lng:.7f} 海拔={end_alt:.1f}m")

            if args.once:
                break
    except KeyboardInterrupt:
        print("\n用户中断。")
    finally:
        # 通过 socket 通知 App 停止服务（在 App 进程内执行，不受后台冻结影响）
        try:
            if pusher.sock is not None:
                pusher.sock.sendall(b"QUIT\n")
        except Exception:
            pass
        pusher.close()
        # 恢复 WiFi 状态
        if args.disable_wifi and wifi_was_on:
            _adb_shell(args.device, ["svc", "wifi", "enable"])
            print("[WiFi] 已恢复手机 WiFi")
        print("已结束，MockGPS 服务已停止。")


if __name__ == "__main__":
    main()
