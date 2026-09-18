#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MockGPS 跑步模拟 GUI
=====================
整合 mock_route.py（GPS 回放）+ frida_hal_run.py（HAL 加速度注入）+
frida_attach.py frida_camouflage.js（传感器伪装）三个子进程，提供：
- 路径文件选择
- 速度/配速双模式（含波动幅度）
- 步频输入与运行中即时调整（写入 cadence_state.txt 联动 HAL）
- 一键开始 / 停止
- 实时日志（按来源着色）

用法：
    python run_gui.py
"""
import os
import re
import sys
import time
import queue
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "cadence_state.txt")
HAL_RUNNER = os.path.join(HERE, "frida_hal_run.py")
ATTACH_RUNNER = os.path.join(HERE, "frida_attach.py")
CAMOUFLAGE_JS = os.path.join(HERE, "frida_camouflage.js")
ROUTE_RUNNER = os.path.join(HERE, "mock_route.py")

# 暗色主题
BG = "#1e1e2e"
BG_ENTRY = "#313244"
FG = "#cdd6f4"
FG_DIM = "#a6adc8"
BORDER = "#45475a"
ACCENT = "#89b4fa"
LOG_BG = "#0f0f0f"

# 日志 tag 颜色
TAG_COLORS = {
    "route": "#a6e3a1",   # 绿
    "hal": "#f9e2af",     # 黄
    "camo": "#89dceb",    # 青
    "gui": "#cdd6f4",     # 白
    "error": "#f38ba8",   # 红
}

# 默认参数（来自用户上次校准成功的值）
DEFAULTS = {
    "route": "",
    "speed_kmh": 12.0,
    "speed_var": 1.5,
    "pace": "5:00",
    "pace_var": 10,
    "cadence": 168,
    "wobble": 3.0,
    "offset_lat": -0.000728,
    "offset_lng": 0.001907,
    "altitude_base": 47.0,
    "altitude_var": 5.0,
    "interval": 1.0,
    "loops": 0,
    "device": "emulator-5554",
    "enable_hal": True,
    "enable_camo": True,
}


def hex_lerp(c1, c2, t):
    """线性插值两个十六进制颜色"""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


class GradientButton(tk.Canvas):
    """自绘渐变按钮控件（Canvas 实现，支持圆角、悬停、按压反馈）"""

    def __init__(self, parent, text, c_start, c_end, width=160, height=44,
                 command=None, font=("Microsoft YaHei UI", 11, "bold"),
                 bg=BG, fg="#ffffff", radius=10):
        super().__init__(parent, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0)
        self._bw, self._bh = width, height
        self._text = text
        self._c_start, self._c_end = c_start, c_end
        self._cmd = command
        self._font = font
        self._fg = fg
        self._radius = radius
        self._bg = bg
        self._state = "normal"  # normal / hover / pressed
        self._draw()
        self.bind("<Enter>", lambda e: self._set_state("hover"))
        self.bind("<Leave>", lambda e: self._set_state("normal"))
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _set_state(self, s):
        if self._state != s:
            self._state = s
            self._draw()

    def _on_press(self, _e):
        self._set_state("pressed")

    def _on_release(self, _e):
        self._set_state("hover")
        if self._cmd:
            self._cmd()

    def _draw(self):
        self.delete("all")
        w, h = self._bw, self._bh
        # 按状态调整颜色亮度
        if self._state == "pressed":
            cs = hex_lerp(self._c_start, "#000000", 0.25)
            ce = hex_lerp(self._c_end, "#000000", 0.25)
        elif self._state == "hover":
            cs = hex_lerp(self._c_start, "#ffffff", 0.12)
            ce = hex_lerp(self._c_end, "#ffffff", 0.12)
        else:
            cs, ce = self._c_start, self._c_end
        # 多段渐变线（垂直方向）
        steps = h
        for i in range(steps):
            t = i / (steps - 1) if steps > 1 else 0
            color = hex_lerp(cs, ce, t)
            x0 = self._radius
            x1 = w - self._radius
            # 圆角裁剪：在上下边缘区域内缩 x
            if i < self._radius:
                inset = self._radius - int((self._radius ** 2 - (self._radius - i) ** 2) ** 0.5)
                x0 = self._radius - inset + 2
                x1 = w - self._radius + inset - 2
            elif i > h - self._radius:
                di = i - (h - self._radius)
                inset = self._radius - int((self._radius ** 2 - (self._radius - di) ** 2) ** 0.5)
                x0 = self._radius - inset + 2
                x1 = w - self._radius + inset - 2
            self.create_line(x0, i + 1, x1, i + 1, fill=color)
        # 阴影边框
        self.create_rectangle(0, 0, w, h, outline=BORDER, width=1)
        # 文字
        self.create_text(w // 2, h // 2, text=self._text, font=self._font,
                         fill=self._fg)


class MockGPSGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MockGPS 跑步模拟器")
        self.geometry("900x780")
        self.configure(bg=BG)
        self.minsize(800, 700)

        # ttk 样式
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=FG,
                        fieldbackground=BG_ENTRY,
                        bordercolor=BORDER, lightcolor=BORDER,
                        darkcolor=BORDER, focuscolor=ACCENT)
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG,
                        font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 14, "bold"),
                        foreground=ACCENT)
        style.configure("TLabelframe", background=BG, foreground=FG,
                        bordercolor=BORDER)
        style.configure("TLabelframe.Label", background=BG,
                        foreground=ACCENT, font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TEntry", fieldbackground=BG_ENTRY, foreground=FG,
                        insertcolor=FG, bordercolor=BORDER, lightcolor=BORDER,
                        darkcolor=BORDER)
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.configure("TRadiobutton", background=BG, foreground=FG)
        style.configure("Horizontal.TScale", background=BG)
        style.configure("TButton", background=BG_ENTRY, foreground=FG,
                        bordercolor=BORDER, focusthickness=0)

        # 变量
        self.var_route = tk.StringVar(value=DEFAULTS["route"])
        self.var_speed_mode = tk.IntVar(value=0)  # 0=速度, 1=配速
        self.var_speed_kmh = tk.StringVar(value=str(DEFAULTS["speed_kmh"]))
        self.var_speed_var = tk.StringVar(value=str(DEFAULTS["speed_var"]))
        self.var_pace = tk.StringVar(value=DEFAULTS["pace"])
        self.var_pace_var = tk.StringVar(value=str(DEFAULTS["pace_var"]))
        self.var_cadence = tk.IntVar(value=DEFAULTS["cadence"])
        self.var_wobble = tk.StringVar(value=str(DEFAULTS["wobble"]))
        self.var_offset_lat = tk.StringVar(value=str(DEFAULTS["offset_lat"]))
        self.var_offset_lng = tk.StringVar(value=str(DEFAULTS["offset_lng"]))
        self.var_altitude_base = tk.StringVar(value=str(DEFAULTS["altitude_base"]))
        self.var_altitude_var = tk.StringVar(value=str(DEFAULTS["altitude_var"]))
        self.var_interval = tk.StringVar(value=str(DEFAULTS["interval"]))
        self.var_loops = tk.StringVar(value=str(DEFAULTS["loops"]))
        self.var_device = tk.StringVar(value=DEFAULTS["device"])
        self.var_enable_hal = tk.BooleanVar(value=DEFAULTS["enable_hal"])
        self.var_enable_camo = tk.BooleanVar(value=DEFAULTS["enable_camo"])
        self.var_status = tk.StringVar(value="状态：未启动")
        self.var_runtime = tk.StringVar(value="已运行：00:00:00")

        # 子进程与线程
        self.procs = {}  # tag -> Popen
        self.threads = []
        self.log_queue = queue.Queue()
        self.cadence_debounce_id = None
        self.start_time = None
        self.runtime_after_id = None

        # 构建界面
        self._build_config_panel()
        self._build_control_panel()
        self._build_log_panel()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 启动日志轮询
        self._drain_queue()

        # 自动检测设备
        self.after(500, self._check_device)

    # ---------- 界面构建 ----------

    def _build_config_panel(self):
        frm = ttk.LabelFrame(self, text="参数配置", padding=12)
        frm.pack(fill="x", padx=12, pady=(12, 6))

        # 第 1 行：路径文件
        row1 = ttk.Frame(frm)
        row1.pack(fill="x", pady=4)
        ttk.Label(row1, text="路径文件：").pack(side="left")
        entry = ttk.Entry(row1, textvariable=self.var_route)
        entry.pack(side="left", fill="x", expand=True, padx=6)
        GradientButton(row1, "浏览", "#06b6d4", "#10b981", width=80, height=30,
                       command=self._on_browse, font=("Microsoft YaHei UI", 9),
                       radius=6).pack(side="left")

        # 第 2 行：速度模式
        row2 = ttk.Frame(frm)
        row2.pack(fill="x", pady=4)
        ttk.Label(row2, text="速度模式：").pack(side="left")
        ttk.Radiobutton(row2, text="基础速度", variable=self.var_speed_mode,
                        value=0, command=self._on_mode_toggle).pack(side="left")
        ttk.Radiobutton(row2, text="目标配速", variable=self.var_speed_mode,
                        value=1, command=self._on_mode_toggle).pack(side="left")

        # 第 3 行：速度参数（两种模式动态切换内容）
        self.row_speed = ttk.Frame(frm)
        self.row_speed.pack(fill="x", pady=4, padx=20)
        self._build_speed_row()

        # 第 4 行：步频
        row4 = ttk.Frame(frm)
        row4.pack(fill="x", pady=4)
        ttk.Label(row4, text="步频（spm）：").pack(side="left")
        cad_entry = ttk.Entry(row4, textvariable=self.var_cadence, width=6)
        cad_entry.pack(side="left", padx=6)
        cad_entry.bind("<FocusOut>", lambda e: self._on_cadence_change())
        cad_entry.bind("<Return>", lambda e: self._on_cadence_change())
        ttk.Label(row4, text="  滑动调整：").pack(side="left")
        scale = ttk.Scale(row4, from_=140, to=200, orient="horizontal",
                          variable=self.var_cadence,
                          command=lambda v: self._on_cadence_change())
        scale.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Label(row4, text="(运行中即时生效，写入 cadence_state.txt)").pack(side="left")

        # 第 5 行：高级参数（折叠）
        self.adv_visible = False
        self.adv_toggle_btn = ttk.Button(frm, text="▼ 高级参数",
                                         command=self._toggle_advanced)
        self.adv_toggle_btn.pack(anchor="w", pady=(8, 2))
        self.adv_frame = ttk.LabelFrame(frm, text="高级", padding=8)

        adv = self.adv_frame
        r = ttk.Frame(adv); r.pack(fill="x", pady=2)
        ttk.Label(r, text="晃动幅度(m)：").pack(side="left")
        ttk.Entry(r, textvariable=self.var_wobble, width=6).pack(side="left", padx=4)
        ttk.Label(r, text="  推送间隔(s)：").pack(side="left")
        ttk.Entry(r, textvariable=self.var_interval, width=6).pack(side="left", padx=4)
        ttk.Label(r, text="  循环(0=无限)：").pack(side="left")
        ttk.Entry(r, textvariable=self.var_loops, width=6).pack(side="left", padx=4)

        ralt = ttk.Frame(adv); ralt.pack(fill="x", pady=2)
        ttk.Label(ralt, text="基准海拔(m)：").pack(side="left")
        ttk.Entry(ralt, textvariable=self.var_altitude_base, width=6).pack(side="left", padx=4)
        ttk.Label(ralt, text="  海拔波动(±m，0=关闭)：").pack(side="left")
        ttk.Entry(ralt, textvariable=self.var_altitude_var, width=6).pack(side="left", padx=4)

        r2 = ttk.Frame(adv); r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="纬度偏移：").pack(side="left")
        ttk.Entry(r2, textvariable=self.var_offset_lat, width=12).pack(side="left", padx=4)
        ttk.Label(r2, text="  经度偏移：").pack(side="left")
        ttk.Entry(r2, textvariable=self.var_offset_lng, width=12).pack(side="left", padx=4)
        ttk.Label(r2, text="  设备序列号：").pack(side="left")
        ttk.Entry(r2, textvariable=self.var_device, width=16).pack(side="left", padx=4)

        r3 = ttk.Frame(adv); r3.pack(fill="x", pady=2)
        ttk.Checkbutton(r3, text="启用 HAL 加速度注入",
                       variable=self.var_enable_hal).pack(side="left", padx=8)
        ttk.Checkbutton(r3, text="启用传感器伪装（frida_camouflage.js）",
                       variable=self.var_enable_camo).pack(side="left", padx=8)

    def _build_speed_row(self):
        for child in self.row_speed.winfo_children():
            child.destroy()
        if self.var_speed_mode.get() == 0:
            ttk.Label(self.row_speed, text="速度(km/h)：").pack(side="left")
            ttk.Entry(self.row_speed, textvariable=self.var_speed_kmh,
                      width=8).pack(side="left", padx=4)
            ttk.Label(self.row_speed, text="  波动幅度(±km/h)：").pack(side="left")
            ttk.Entry(self.row_speed, textvariable=self.var_speed_var,
                      width=6).pack(side="left", padx=4)
            ttk.Label(self.row_speed,
                      text=f"  ≈ 配速 {self._speed_to_pace_str(DEFAULTS['speed_kmh'])}").pack(side="left")
        else:
            ttk.Label(self.row_speed, text="配速(min:ss/km)：").pack(side="left")
            ttk.Entry(self.row_speed, textvariable=self.var_pace,
                      width=8).pack(side="left", padx=4)
            ttk.Label(self.row_speed, text="  波动幅度(±秒/km)：").pack(side="left")
            ttk.Entry(self.row_speed, textvariable=self.var_pace_var,
                      width=6).pack(side="left", padx=4)
            ttk.Label(self.row_speed,
                      text=f"  ≈ 速度 {self._pace_to_speed(DEFAULTS['pace']):.2f} km/h").pack(side="left")

    def _build_control_panel(self):
        frm = ttk.Frame(self)
        frm.pack(fill="x", padx=12, pady=6)
        self.btn_start = GradientButton(
            frm, "开始跑步", "#7c3aed", "#ec4899",
            width=160, height=48, command=self._on_start,
            font=("Microsoft YaHei UI", 13, "bold"), radius=12)
        self.btn_start.pack(side="left", padx=(0, 12))
        self.btn_stop = GradientButton(
            frm, "停止", "#4b5563", "#6b7280",
            width=120, height=48, command=self._on_stop,
            font=("Microsoft YaHei UI", 13, "bold"), radius=12)
        self.btn_stop.pack(side="left", padx=(0, 12))
        # 状态显示
        status_box = ttk.Frame(frm)
        status_box.pack(side="left", fill="x", expand=True)
        ttk.Label(status_box, textvariable=self.var_status,
                  font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        ttk.Label(status_box, textvariable=self.var_runtime,
                  font=("Microsoft YaHei UI", 10)).pack(anchor="w")

    def _build_log_panel(self):
        frm = ttk.LabelFrame(self, text="运行日志", padding=6)
        frm.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        self.log_text = tk.Text(frm, bg=LOG_BG, fg=FG, insertbackground=FG,
                                font=("Consolas", 9), wrap="word",
                                state="disabled", relief="flat",
                                borderwidth=0)
        scroll = ttk.Scrollbar(frm, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        # 配置 tag 颜色
        for tag, color in TAG_COLORS.items():
            self.log_text.tag_config(tag, foreground=color)

    # ---------- 高级参数折叠 ----------

    def _toggle_advanced(self):
        if self.adv_visible:
            self.adv_frame.pack_forget()
            self.adv_toggle_btn.config(text="▼ 高级参数")
        else:
            self.adv_frame.pack(fill="x", pady=4)
            self.adv_toggle_btn.config(text="▲ 高级参数")
        self.adv_visible = not self.adv_visible

    # ---------- 事件回调 ----------

    def _on_browse(self):
        init_dir = HERE
        path = filedialog.askopenfilename(
            title="选择轨迹文件",
            initialdir=init_dir,
            filetypes=[("轨迹文件", "*.txt *.gpx *.kml"), ("所有文件", "*.*")])
        if path:
            self.var_route.set(path)

    def _on_mode_toggle(self):
        # 切换模式时把当前值换算到对应字段
        if self.var_speed_mode.get() == 0:
            # 切到速度模式：把配速换算成速度
            try:
                sp = self._pace_to_speed(self.var_pace.get())
                self.var_speed_kmh.set(f"{sp:.2f}")
                # 配速波动 → 速度波动
                pv = float(self.var_pace_var.get())
                pace_min = self._parse_pace(self.var_pace.get())
                sv = (60.0 / (pace_min ** 2)) * (pv / 60.0)
                self.var_speed_var.set(f"{sv:.2f}")
            except Exception:
                pass
        else:
            # 切到配速模式：把速度换算成配速
            try:
                sp = float(self.var_speed_kmh.get())
                self.var_pace.set(self._speed_to_pace_str(sp))
                # 速度波动 → 配速波动（秒）
                sv = float(self.var_speed_var.get())
                pace_min = 60.0 / sp
                pv = sv * (pace_min ** 2) / 60.0 * 60.0  # 转回秒
                self.var_pace_var.set(f"{int(pv)}")
            except Exception:
                pass
        self._build_speed_row()

    def _on_cadence_change(self):
        if self.cadence_debounce_id:
            self.after_cancel(self.cadence_debounce_id)
        self.cadence_debounce_id = self.after(300, self._write_cadence_state)

    # ---------- 单位换算 ----------

    @staticmethod
    def _parse_pace(s):
        """5:00 → 5.0（分钟）；5:30 → 5.5"""
        m = re.match(r"^\s*(\d+):(\d+)\s*$", s)
        if m:
            return int(m.group(1)) + int(m.group(2)) / 60.0
        return float(s)

    @classmethod
    def _pace_to_speed(cls, s):
        """配速字符串 → 速度 km/h"""
        pace_min = cls._parse_pace(s)
        if pace_min <= 0:
            return 0
        return 60.0 / pace_min

    @staticmethod
    def _speed_to_pace_str(sp):
        """速度 km/h → 配速字符串 M:SS"""
        if sp <= 0:
            return "—"
        pace_min = 60.0 / sp
        m = int(pace_min)
        s = int(round((pace_min - m) * 60))
        return f"{m}:{s:02d}"

    # ---------- cadence_state.txt 写入 ----------

    def _write_cadence_state(self, running=None, cadence=None):
        if running is None:
            running = 1 if self.procs else 0
        if cadence is None:
            try:
                cadence = int(self.var_cadence.get())
            except Exception:
                cadence = DEFAULTS["cadence"]
        # 限制范围
        cadence = max(60, min(220, int(cadence)))
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                f.write(f"running={running}\ncadence={cadence}\n")
        except Exception as e:
            self._log("gui", f"写 cadence_state.txt 失败：{e}")
        self.cadence_debounce_id = None

    # ---------- 子进程启动 ----------

    def _on_start(self):
        if self.procs:
            messagebox.showwarning("提示", "已在运行中，请先停止")
            return
        route = self.var_route.get().strip()
        if not route or not os.path.isfile(route):
            messagebox.showerror("错误", "请选择有效的轨迹文件")
            return
        # 检查依赖文件
        if self.var_enable_hal.get() and not os.path.isfile(HAL_RUNNER):
            messagebox.showerror("错误", f"找不到 {HAL_RUNNER}")
            return
        if self.var_enable_camo.get() and not os.path.isfile(ATTACH_RUNNER):
            messagebox.showerror("错误", f"找不到 {ATTACH_RUNNER}")
            return
        if not os.path.isfile(ROUTE_RUNNER):
            messagebox.showerror("错误", f"找不到 {ROUTE_RUNNER}")
            return

        # 解析参数
        try:
            if self.var_speed_mode.get() == 0:
                speed_kmh = float(self.var_speed_kmh.get())
                speed_var = float(self.var_speed_var.get())
            else:
                speed_kmh = self._pace_to_speed(self.var_pace.get())
                pv = float(self.var_pace_var.get())
                pace_min = 60.0 / speed_kmh
                speed_var = (60.0 / (pace_min ** 2)) * (pv / 60.0)
            wobble = float(self.var_wobble.get())
            offset_lat = float(self.var_offset_lat.get())
            offset_lng = float(self.var_offset_lng.get())
            altitude_base = float(self.var_altitude_base.get())
            altitude_var = float(self.var_altitude_var.get())
            interval = float(self.var_interval.get())
            loops = int(self.var_loops.get())
            cadence = int(self.var_cadence.get())
            device = self.var_device.get().strip()
        except Exception as e:
            messagebox.showerror("参数错误", f"参数解析失败：{e}")
            return

        # 0. 确保设备上 frida-server 运行（HAL/伪装需要；BlueStacks 重启后会丢失）
        if self.var_enable_hal.get() or self.var_enable_camo.get():
            if not self._ensure_frida_server(device):
                if not messagebox.askyesno(
                        "frida-server 未就绪",
                        "无法在设备上启动 frida-server，加速度注入/传感器伪装将失败。\n\n"
                        "是否仍要继续启动（仅运行 GPS 回放）？"):
                    return

        # 1. 先写 cadence_state.txt 为 running=1 + 用户步频
        self._write_cadence_state(running=1, cadence=cadence)
        self._log("gui", f"已写入 cadence_state.txt: running=1, cadence={cadence}")

        py = sys.executable
        create_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0

        # 强制子进程 stdout/stderr 输出 UTF-8，避免 Windows 中文系统默认 GBK 导致
        # GUI 端 encoding="utf-8" 读 PIPE 时报 "codec can't decode byte 0xcf"
        sub_env = os.environ.copy()
        sub_env["PYTHONUTF8"] = "1"
        sub_env["PYTHONIOENCODING"] = "utf-8:replace"

        # 2. 启动 HAL 加速度注入
        if self.var_enable_hal.get():
            try:
                p = subprocess.Popen(
                    [py, HAL_RUNNER],
                    cwd=HERE,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, encoding="utf-8",
                    env=sub_env, creationflags=create_flags)
                self.procs["hal"] = p
                self._start_reader(p, "hal")
                self._log("gui", f"已启动 HAL 加速度注入 (pid={p.pid})")
            except Exception as e:
                self._log("error", f"启动 HAL 注入失败：{e}")

        # 3. 启动传感器伪装
        if self.var_enable_camo.get():
            try:
                p = subprocess.Popen(
                    [py, ATTACH_RUNNER, CAMOUFLAGE_JS],
                    cwd=HERE,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, encoding="utf-8",
                    env=sub_env, creationflags=create_flags)
                self.procs["camo"] = p
                self._start_reader(p, "camo")
                self._log("gui", f"已启动传感器伪装 (pid={p.pid})")
            except Exception as e:
                self._log("error", f"启动传感器伪装失败：{e}")

        # 4. 启动 GPS 路径回放（最后启动，因为它会做 adb forward + 设备唤醒）
        route_cmd = [py, ROUTE_RUNNER, route,
                     "--speed-kmh", f"{speed_kmh}",
                     "--speed-var", f"{speed_var}",
                     "--wobble", f"{wobble}",
                     "--offset-lat", f"{offset_lat}",
                     "--offset-lng", f"{offset_lng}",
                     "--altitude-base", f"{altitude_base}",
                     "--altitude-var", f"{altitude_var}",
                     "--interval", f"{interval}",
                     "--loops", f"{loops}",
                     "-s", device]
        try:
            p = subprocess.Popen(
                route_cmd, cwd=HERE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, encoding="utf-8",
                env=sub_env, creationflags=create_flags)
            self.procs["route"] = p
            self._start_reader(p, "route")
            self._log("gui", f"已启动 GPS 回放 (pid={p.pid}) 速度={speed_kmh}km/h 波动={speed_var}")
        except Exception as e:
            self._log("error", f"启动 GPS 回放失败：{e}")

        # 状态更新
        self.start_time = time.time()
        self.var_status.set(f"状态：运行中（步频={cadence}）")
        self._update_runtime()
        # 异步监控子进程退出
        self.after(1000, self._check_procs_alive)

    def _on_stop(self):
        if not self.procs:
            return
        self._log("gui", "正在停止所有子进程...")
        # 1. 先写 running=0，让 HAL 在被杀前停止注入
        try:
            cadence = int(self.var_cadence.get())
        except Exception:
            cadence = DEFAULTS["cadence"]
        self._write_cadence_state(running=0, cadence=cadence)
        # 2. 等 0.3s
        self.after(300, self._terminate_procs)

    def _terminate_procs(self):
        # 3. terminate 所有子进程（mock_route 的 finally 会发 QUIT 给 Android）
        for tag, p in list(self.procs.items()):
            try:
                if p.poll() is None:
                    p.terminate()
                    self._log("gui", f"[{tag}] 已发送 terminate")
            except Exception as e:
                self._log("error", f"[{tag}] terminate 失败：{e}")
        # 4. 0.5s 后 kill 兜底
        self.after(500, self._kill_procs)

    def _kill_procs(self):
        for tag, p in list(self.procs.items()):
            try:
                if p.poll() is None:
                    p.kill()
                    self._log("gui", f"[{tag}] 已强杀")
            except Exception:
                pass
        self.procs.clear()
        self.var_status.set("状态：已停止")
        self.var_runtime.set("已运行：00:00:00")
        if self.runtime_after_id:
            self.after_cancel(self.runtime_after_id)
            self.runtime_after_id = None

    # ---------- 子进程读线程 ----------

    def _start_reader(self, proc, tag):
        t = threading.Thread(target=self._read_proc_loop,
                              args=(proc, tag), daemon=True)
        t.start()
        self.threads.append(t)

    def _read_proc_loop(self, proc, tag):
        try:
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                self.log_queue.put((tag, line.rstrip("\n")))
        except Exception as e:
            self.log_queue.put(("error", f"[{tag}] reader error: {e}"))

    # ---------- 主线程日志轮询 ----------

    def _drain_queue(self):
        try:
            while True:
                tag, line = self.log_queue.get_nowait()
                self._log(tag, line)
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    def _log(self, tag, msg):
        self.log_text.configure(state="normal")
        # 提取日志中的 [tag] 前缀（如 [hal]），自动分类
        m = re.match(r"^\[(\w+)\]", msg)
        if m:
            inner = m.group(1).lower()
            if inner in TAG_COLORS:
                tag = inner
        self.log_text.insert("end", f"[{tag}] {msg}\n", tag)
        # 限制行数
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 5000:
            self.log_text.delete(1.0, f"{lines - 5000}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ---------- 状态监控 ----------

    def _update_runtime(self):
        if self.start_time and self.procs:
            elapsed = int(time.time() - self.start_time)
            h = elapsed // 3600
            m = (elapsed % 3600) // 60
            s = elapsed % 60
            try:
                cadence = int(self.var_cadence.get())
            except Exception:
                cadence = DEFAULTS["cadence"]
            self.var_runtime.set(f"已运行：{h:02d}:{m:02d}:{s:02d}  当前步频={cadence}")
        self.runtime_after_id = self.after(1000, self._update_runtime)

    def _check_procs_alive(self):
        if not self.procs:
            return
        all_dead = True
        for tag, p in list(self.procs.items()):
            rc = p.poll()
            if rc is not None:
                self._log("gui", f"[{tag}] 进程退出，rc={rc}")
                # 从字典移除（但保留其他活跃的）
        # 检查是否全部结束
        active = {t: p for t, p in self.procs.items() if p.poll() is None}
        if not active:
            self._log("gui", "所有子进程已结束")
            self.procs.clear()
            self.var_status.set("状态：已结束")
            if self.runtime_after_id:
                self.after_cancel(self.runtime_after_id)
                self.runtime_after_id = None
        else:
            self.procs = active
            self.after(1000, self._check_procs_alive)

    def _check_device(self):
        """启动时检查 adb 设备是否在线"""
        try:
            r = subprocess.run(["adb", "devices"], capture_output=True,
                                text=True, timeout=3)
            lines = [l for l in r.stdout.splitlines()
                     if l and not l.startswith("List") and "device" in l]
            if lines:
                self._log("gui", f"adb 设备在线：{lines[0].strip()}")
            else:
                self._log("gui", "提示：未检测到 adb 设备，请确认 BlueStacks 已启动")
        except FileNotFoundError:
            self._log("gui", "提示：未找到 adb，可能无法自动唤醒设备")
        except Exception as e:
            self._log("gui", f"adb 检测异常：{e}")

    def _ensure_frida_server(self, device):
        """检查设备上 frida-server 是否运行；未运行则以 root 后台拉起。
        优先 frida-server16（匹配 frida-python 16.x），回退 frida-server。
        返回 True 表示就绪。
        """
        adb = ["adb", "-s", device] if device else ["adb"]

        def run_shell(cmd, timeout=6):
            return subprocess.run(adb + ["shell", cmd],
                                  capture_output=True, text=True, timeout=timeout)

        # === 第一步：确保设备在线 + boot 完成 ===
        self._log("gui", "正在等待设备就绪...")
        try:
            r = subprocess.run(adb + ["wait-for-device"], timeout=60)
            if r.returncode != 0:
                self._log("error", "设备未就绪：adb wait-for-device 超时")
                return False
        except Exception as e:
            self._log("error", f"设备连接异常：{e}")
            return False

        # 等 boot_completed（最多 90s）
        boot_ok = False
        for _ in range(30):
            try:
                r = run_shell("getprop sys.boot_completed", timeout=5)
                if r.returncode == 0 and r.stdout.strip() == "1":
                    boot_ok = True
                    break
            except Exception:
                pass
            time.sleep(3)
        if not boot_ok:
            self._log("error", "设备 boot 未完成，无法启动 frida-server")
            return False
        self._log("gui", "设备已就绪（boot_completed=1）")

        # 检查 su 权限
        try:
            r = run_shell("su -c id", timeout=5)
            if r.returncode != 0 or "uid=0" not in r.stdout:
                self._log("error", "设备无 root 权限（su 返回非 uid=0），frida-server 无法启动")
                return False
        except Exception as e:
            self._log("error", f"su 检查异常：{e}")
            return False

        # === 第二步：frida-server 已在运行？ ===
        for name in ("frida-server16", "frida-server"):
            try:
                r = run_shell(f"pgrep -x {name}")
                if r.returncode == 0 and r.stdout.strip():
                    self._log("gui",
                              f"frida-server 已运行（{name}, pid={r.stdout.strip().splitlines()[0]}）")
                    return True
            except Exception:
                continue

        # 未运行，尝试以 root 拉起
        self._log("gui", "frida-server 未运行，尝试以 root 后台拉起...")
        for name in ("frida-server16", "frida-server"):
            try:
                if run_shell(f"ls /data/local/tmp/{name}").returncode != 0:
                    continue
                # su 后台启动并脱离 adb shell（nohup + &，重定向避免阻塞）
                run_shell(
                    f"su -c 'chmod 755 /data/local/tmp/{name}; "
                    f"nohup /data/local/tmp/{name} >/dev/null 2>&1 &'",
                    timeout=8)
                # 等待 daemon 就绪
                for _ in range(6):
                    time.sleep(1)
                    r = run_shell(f"pgrep -x {name}")
                    if r.returncode == 0 and r.stdout.strip():
                        self._log("gui",
                                  f"frida-server 已拉起（{name}, pid={r.stdout.strip().splitlines()[0]}）")
                        return True
            except Exception as e:
                self._log("error", f"拉起 {name} 异常：{e}")

        self._log("error",
                  "无法启动 frida-server：请确认设备已 root，且 /data/local/tmp/ 下有 frida-server16")
        return False

    # ---------- 关窗 ----------

    def _on_close(self):
        if self.procs:
            if not messagebox.askokcancel("确认", "子进程仍在运行，确定退出？"):
                return
            self._on_stop()
            self.after(1000, self._safe_destroy)
        else:
            self._safe_destroy()

    def _safe_destroy(self):
        for p in self.procs.values():
            try:
                if p.poll() is None:
                    p.kill()
            except Exception:
                pass
        self.procs.clear()
        self.destroy()


def main():
    app = MockGPSGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
