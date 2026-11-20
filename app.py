"""MockGPS Desktop route preview and location tests."""

from math import isfinite
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from time import monotonic
import tkinter as tk
from tkinter import filedialog, ttk

from emulator import find_adb, list_emulators, send_fix
from routes import playback_samples, read_route, route_length


class Desktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MockGPS Desktop")
        self.geometry("820x640")
        self.minsize(680, 520)
        self.iconphoto(True, tk.PhotoImage(file=str(Path(__file__).with_name("assets") / "app-mark.png")))
        self.route = ()
        self.cancel = Event()
        self.events = Queue()
        self.adb = tk.StringVar(value=find_adb())
        self.serial = tk.StringVar(value="emulator-5554")
        self.speed = tk.StringVar(value="12")
        self.route_name = tk.StringVar(value="打开一条 TXT、GPX 或 KML 路线")
        self.status = tk.StringVar(value="可在桌面预览路线，也可发送到本机 Android Emulator。")

        panel = ttk.Frame(self, padding=18)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="MockGPS Desktop", font=("Microsoft YaHei UI", 21)).pack(anchor="w")
        toolbar = ttk.Frame(panel)
        toolbar.pack(fill="x", pady=(12, 8))
        self.open_button = ttk.Button(toolbar, text="打开路线", command=self.choose_route)
        self.open_button.pack(side="left")
        self.example_button = ttk.Button(toolbar, text="示例路线",
                                         command=lambda: self.open_route(Path(__file__).with_name("example-route.txt")))
        self.example_button.pack(side="left", padx=(8, 0))
        ttk.Label(toolbar, textvariable=self.route_name).pack(side="left", padx=12)
        self.canvas = tk.Canvas(panel, background="#ecf4f0", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.draw())

        config = ttk.Frame(panel)
        config.pack(fill="x", pady=10)
        config.columnconfigure(1, weight=1)
        ttk.Label(config, text="ADB").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(config, textvariable=self.adb).grid(row=0, column=1, columnspan=3, sticky="ew")
        ttk.Button(config, text="选择", command=self.choose_adb).grid(row=0, column=4, padx=(8, 0))
        ttk.Label(config, text="模拟器").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.device_menu = ttk.Combobox(config, textvariable=self.serial, width=16)
        self.device_menu.grid(row=1, column=1, sticky="ew", pady=(6, 0))
        self.detect_button = ttk.Button(config, text="检测", command=self.detect)
        self.detect_button.grid(row=1, column=2, padx=8, pady=(6, 0))
        ttk.Label(config, text="速度 (km/h)").grid(row=1, column=3, pady=(6, 0))
        ttk.Entry(config, textvariable=self.speed, width=8).grid(row=1, column=4, padx=(8, 0), pady=(6, 0))
        actions = ttk.Frame(panel)
        actions.pack(fill="x", pady=(0, 10))
        self.run_buttons = []
        for label, android, preview in (("桌面预览", False, False), ("发送起点", True, True),
                                        ("模拟器回放", True, False)):
            button = ttk.Button(actions, text=label, command=lambda a=android, p=preview: self.start(a, p))
            button.pack(side="left", padx=(0, 8))
            self.run_buttons.append(button)
        self.stop_button = ttk.Button(actions, text="停止", command=self.cancel.set, state="disabled")
        self.stop_button.pack(side="left")
        ttk.Label(panel, textvariable=self.status, wraplength=615).pack(anchor="w")
        self.position = None
        self.project_point = None
        self.running = False
        self.detecting = False
        self.set_running(False)
        self.after(40, self.consume)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def choose_route(self):
        name = filedialog.askopenfilename(filetypes=[("路线文件", "*.txt *.gpx *.kml"), ("所有文件", "*")])
        if name:
            self.open_route(name)

    def open_route(self, name):
        try:
            route = read_route(name)
        except (OSError, ValueError, SyntaxError) as error:
            self.status.set(f"无法打开路线：{error}")
            return
        self.route, self.position = route, None
        self.route_name.set(f"{Path(name).name}   ·   {len(route)} 段   ·   {route_length(route):,.0f} m")
        self.status.set("路线已加载。")
        self.draw()
        self.set_running(False)

    def set_running(self, running):
        self.running = running
        for button in (self.open_button, self.example_button):
            button.configure(state="disabled" if running else "normal")
        self.detect_button.configure(state="disabled" if running or self.detecting else "normal")
        for button in self.run_buttons:
            button.configure(state="disabled" if running or not self.route else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")

    def choose_adb(self):
        name = filedialog.askopenfilename(filetypes=[("ADB 可执行文件", "adb.exe")])
        if name:
            self.adb.set(name)

    def detect(self):
        adb = self.adb.get().strip()
        self.detecting = True
        self.detect_button.configure(state="disabled")
        self.status.set("正在检测本机模拟器…")

        def scan():
            try:
                self.events.put(("devices", list_emulators(adb)))
            except (OSError, RuntimeError) as error:
                self.events.put(("device_error", str(error)))

        Thread(target=scan, daemon=True).start()

    def draw(self):
        self.canvas.delete("all")
        self.project_point = None
        if not self.route:
            return
        points = [point for segment in self.route for point in segment]
        south, north = min(p.latitude for p in points), max(p.latitude for p in points)
        origin = points[0].longitude

        def longitude(point):
            return (point.longitude - origin + 180) % 360 - 180

        west, east = min(map(longitude, points)), max(map(longitude, points))
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        scale = min(max(1, width - 48) / max(1e-8, east - west),
                    max(1, height - 48) / max(1e-8, north - south))

        def pixel(point):
            return (width / 2 + (longitude(point) - (west + east) / 2) * scale,
                    height / 2 - (point.latitude - (south + north) / 2) * scale)

        for segment in self.route:
            stride = max(1, (len(segment) + 2999) // 3000)
            displayed = (*segment[:-1:stride], segment[-1])
            self.canvas.create_line(*(v for p in displayed for v in pixel(p)), fill="#278267", width=3)
        x, y = pixel(self.route[0][0])
        self.canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill="#236752", outline="white")
        self.project_point = pixel
        self.draw_position()

    def draw_position(self):
        self.canvas.delete("playhead")
        if self.position is not None and self.project_point is not None:
            x, y = self.project_point(self.position)
            self.canvas.create_oval(x - 5, y - 5, x + 5, y + 5,
                                    fill="#ef873b", outline="white", tags="playhead")

    def start(self, android, preview):
        try:
            speed = 12 if preview else float(self.speed.get())
            if not isfinite(speed) or not 0.1 <= speed <= 100:
                raise ValueError
        except ValueError:
            self.status.set("速度须介于 0.1 和 100 km/h 之间。")
            return
        adb, serial, route = self.adb.get().strip(), self.serial.get().strip(), self.route
        self.cancel.clear()
        self.set_running(True)
        self.status.set("正在发送起点…" if preview else "正在回放路线…")

        def replay():
            try:
                for segment in route:
                    started = monotonic()
                    for due, point in playback_samples(segment, speed):
                        if self.cancel.wait(max(0, started + due - monotonic())):
                            self.events.put(("done", "已停止回放。"))
                            return
                        if android:
                            send_fix(adb, serial, point)
                        self.events.put(("point", point))
                        if preview:
                            self.events.put(("done", "已向模拟器发送路线起点。"))
                            return
                self.events.put(("done", "路线回放完成。"))
            except Exception as error:
                self.events.put(("done", f"回放中止：{error}"))

        self.worker = Thread(target=replay, daemon=True)
        self.worker.start()

    def consume(self):
        try:
            while True:
                action, value = self.events.get_nowait()
                if action == "point":
                    self.position = value
                    self.draw_position()
                elif action == "done":
                    self.set_running(False)
                    self.status.set(value)
                elif action == "devices":
                    self.detecting = False
                    self.set_running(self.running)
                    self.device_menu.configure(values=value)
                    if len(value) == 1 and not self.running:
                        self.serial.set(value[0])
                    if not self.running:
                        self.status.set(f"已检测到 {len(value)} 台模拟器。" if value
                                        else "未找到在线的 Android Studio 模拟器。桌面预览仍可使用。")
                elif action == "device_error":
                    self.detecting = False
                    self.set_running(self.running)
                    if not self.running:
                        self.status.set(value)
        except Empty:
            self.after(40, self.consume)

    def close(self):
        self.cancel.set()
        if getattr(self, "worker", None) and self.worker.is_alive():
            self.after(50, self.close)
        else:
            self.destroy()


if __name__ == "__main__":
    Desktop().mainloop()
