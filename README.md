# MockGPS 跑步模拟器

在 BlueStacks 5 安卓模拟器中模拟户外跑步：沿指定轨迹循环移动、注入跑步加速度波形、伪装传感器规格，让咕咚 / 高德等运动 App 记录到稳定的配速、步频与轨迹。

提供 **Tkinter GUI** 一键启动/停止，无需记忆命令行参数。

---

## 功能特性

- **GPS 路径回放**：沿 `.txt` / `.gpx` / `.kml` 轨迹循环移动，支持位置偏移补偿（修正咕咚显示偏移）
- **跑步晃动模拟**：左右晃动模拟真人跑步，幅度可调（默认 3.0 m）
- **速度随机波动**：±N km/h 均值回归，保证平均配速稳定
- **HAL 加速度注入**：通过 Frida 以 50Hz 向 BlueStacks 传感器 HAL 的 `/data/bstfifo` 命名管道写入跑步波形（着地峰值 ~18 m/s²）
- **传感器规格伪装**：把 BlueStacks 加速度计伪装成 BMI260（±4g / 200Hz / Bosch），让运动 App 认为其可用于计步
- **步频联动**：GUI 中的步频滑块拖动后 ≤1s 内同步到 HAL 注入器（通过 `cadence_state.txt` 联动）
- **可视化 GUI**：紫色渐变开始按钮、灰色停止按钮、按来源着色的实时日志

---

## 仓库结构

```
.
├── pc/                          # PC 端 Python + Frida 脚本
│   ├── run_gui.py               # ⭐ Tkinter GUI 主入口
│   ├── mock_route.py            # GPS 回放主脚本（Socket 17890 推送到手机）
│   ├── frida_hal_inject.js      # HAL 加速度注入 JS（50Hz 写 /data/bstfifo）
│   ├── frida_hal_run.py         # HAL 注入常驻器（每秒读 cadence_state.txt）
│   ├── frida_camouflage.js      # 传感器规格伪装 JS（BMI260）
│   ├── frida_attach.py          # 通用 Frida attach runner
│   ├── frida_inject_run.py      # 咕咚 Java 层注入常驻器（参考）
│   ├── frida_inject.js          # Java 层波形注入（参考）
│   ├── frida_recon.js           # 传感器枚举侦察（参考）
│   ├── frida_queue.js           # dispatchSensorEvent hook（参考）
│   ├── frida_native_recon.js    # libandroid.so NDK hook（参考）
│   ├── frida_native_poll.js     # getEvents 频率统计（参考）
│   ├── frida_libsensor.js       # libsensor.so 符号枚举（参考）
│   ├── frida_observe.py         # Java 加速度观察器（参考）
│   ├── frida_run.py             # 通用 Frida 启动器（参考）
│   ├── gen_track_route.py       # 轨迹文件生成工具
│   ├── track_final.txt          # 默认 400m 操场轨迹（421 点）
│   └── cadence_state.txt        # 步频状态文件（GUI 唯一写者，HAL 注入器读取）
│
├── android/                     # MockGPS Android 应用
│   └── app/src/main/java/com/mockgps/
│       ├── MainActivity.kt      # 简单 UI（启动/停止服务按钮）
│       ├── MockLocationService.kt  # 前台服务 + Socket 17890 服务端
│       └── LocationUpdateReceiver.kt
│
├── tools/                       # 逆向分析工具
│   ├── disasm_hal.py            # 用 capstone 反汇编 sensors.default.so
│   ├── read_const.py            # 读取 HAL 转换常量（C1=1e6, C2=-9.80665）
│   ├── analyze_hal.py           # HAL 函数定位
│   └── *.sh                     # 各种诊断脚本（dump_ui/sensor_dump/start_frida 等）
│
├── README.md                    # 本文件
└── SKILL.md                     # ⭐ Agent Skill 使用说明（让 AI agent 直接调用）
```

---

## 环境准备

### 必需组件

| 组件 | 版本 | 说明 |
|------|------|------|
| BlueStacks | 5.22+ | Pie64 实例（Android 9, x86_64） |
| Python | 3.10+ | PC 端脚本运行环境 |
| Frida | 16.7.19 | **不要用 17.x**（移除了 Java 全局对象） |
| ADB | 任意 | 用户自行安装 platform-tools |
| gh | 任意 | 可选，仅推送本仓库时用 |

### Python 依赖

```bash
pip install frida==16.7.19 capstone
```

### BlueStacks 配置

1. **启用 root**：用 [BlueStacksRootGUI](https://github.com/HD-Modtools/BlueStacksRootGUI) 的 **Manager Root** 模式装上 Kitsune Magisk v31.0，关闭 native root 避免冲突（不要用官方 Magisk，需要 patched boot 而 BlueStacks 无独立 boot 镜像）
2. **配置文件修改**：`D:\BlueStacks_nxt_cn\bluestacks.conf` 中
   - `bst.feature.rooting="1"`（启用 root 功能）
   - `bst.instance.Pie64.enable_root_access="1"`（实例级 root 开关）
   - 修改时用字节级替换，避免文件编码损坏
3. **重启 BlueStacks** 后 `adb shell su -c id` 应返回 `uid=0`

### frida-server 部署

```bash
# 下载 frida-server 16.7.19 for android-x86_64
adb push frida-server /data/local/tmp/
adb shell "chmod 755 /data/local/tmp/frida-server"
adb shell "su -c '/data/local/tmp/frida-server &'"
```

### MockGPS 应用安装

```bash
cd android
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

安装后到 **开发者选项 → 模拟位置应用** 选 `MockGPS`。

---

## 快速开始（GUI 一键启动）

```bash
cd pc
python run_gui.py
```

GUI 操作：
1. 点「浏览」选 `track_final.txt`
2. 调整速度 / 波动 / 步频（或保持默认：12 km/h ± 1.5，步频 168）
3. 点紫色「开始跑步」按钮
4. 观察日志区三路输出：`[hal]`（黄）/ `[camo]`（青）/ `[route]`（绿）
5. 运行中拖动步频滑块即时调整（≤1s 内同步到 HAL 注入）
6. 点灰色「停止」按钮结束

---

## 命令行用法（不使用 GUI）

### 1. 启动 HAL 加速度注入（终端 1）

```bash
cd pc
python frida_hal_run.py
```

以 root spawn `/system/bin/sleep` 作为原生宿主，注入 `frida_hal_inject.js`，每秒读 `cadence_state.txt` 同步 running/cadence。

### 2. 启动传感器伪装（终端 2，可选但推荐）

```bash
cd pc
python frida_attach.py frida_camouflage.js
```

attach 已运行的咕咚（`com.codoon.gps`），伪装加速度计规格为 BMI260。

### 3. 启动 GPS 路径回放（终端 3）

```bash
cd pc
python mock_route.py track_final.txt \
    --speed-kmh 12 \
    --speed-var 1.5 \
    --wobble 3.0 \
    --offset-lat -0.000728 \
    --offset-lng 0.001907 \
    --loops 0 \
    -s emulator-5554
```

参数说明：
| 参数 | 默认 | 说明 |
|------|------|------|
| `route` | 必填 | 轨迹文件路径（.txt/.gpx/.kml） |
| `--speed-kmh` | 12.0 | 移动速度 km/h（5 min/km） |
| `--interval` | 1.0 | 推送间隔秒数 |
| `--wobble` | 3.0 | 跑步晃动幅度（米），0=关闭 |
| `--speed-var` | 1.5 | 速度随机波动幅度 ±km/h（均值回归） |
| `--offset-lat` | 0.0 | 纬度偏移补偿（度）。+北移/-南移 |
| `--offset-lng` | 0.0 | 经度偏移补偿（度）。+东移/-西移 |
| `--loops` | 1 | 循环次数（0=无限） |
| `-s` | 自动 | adb 设备序列号 |
| `--disable-wifi` | off | 运行期间关闭手机 WiFi |

### 4. 调整步频

直接编辑 `pc/cadence_state.txt`：

```
running=1
cadence=180
```

保存后 ≤1s 内 HAL 注入器会通过 RPC 同步新步频。

---

## 轨迹文件格式

### `.txt`（推荐）

每行一个点，逗号或空格分隔纬度、经度：

```
# 400m跑道轨迹 421点
22.6877725,114.2034827
22.6877785,114.2034763
22.6877844,114.2034698
```

以 `#` 开头的行被忽略。

### `.gpx` / `.kml`

标准 GPX/KML 文件，自动解析 `trkpt` / `rtept` / `wpt` / `coordinates`。

---

## 关键技术原理

### BlueStacks 传感器 HAL 协议

逆向 `sensors.default.so`（24400 字节）得到：
- HAL 内部读线程 `bstsensor_accel_data_reader` 用 `__read_chk(fd, buf, 12, 12)` 从命名管道 `/data/bstfifo` 读 12 字节
- 帧格式：12 字节 = 3 × int32 LE，单位为 g 的百万分之一
- 转换公式：`HAL输出(m/s²) = (raw_int32 / 1e6) × (-9.80665)`
- 反推注入：`raw = round(-value_mps2 / 9.80665 × 1e6)`

### 跑步加速度波形

50Hz 注入，每帧 20ms：
- 步频相位：`ph = 2π × (cadence/60) × t`
- 着地冲击（z 轴）：`G + impact × (0.5 - 0.5×cos(ph))^6`，峰值 ~18 m/s²
- 弹跳（z 轴）：`bounce × sin(2ph - 0.6)`
- 左右摆臂（x 轴）：`swingX × sin(ph + π/2) + 0.8 × swingX × sin(2ph + 0.4)`
- 前后蹬伸（y 轴）：`swingY × sin(ph + 0.4) + 0.5 × swingY × sin(2ph + 1.1)`
- 高斯噪声：σ = 0.7 m/s²

### 传感器伪装必要性

BlueStacks 加速度计默认规格异常（maxRange=9.80665 即 ±1g、minDelay=200000ns 即 5Hz），导致咕咚判定其不可用于计步。伪装成 BMI260（±4g / 200Hz / Bosch）后可被运动 App 接受。

---

## 故障排查

| 现象 | 排查 |
|------|------|
| `adb` 找不到 | 安装 Android Platform Tools 并加入 PATH |
| `frida-ps -U` 列不出设备 | 确认 frida-server 已在设备上以 root 运行 |
| Frida 报 `'Java' is not defined` | frida-python 版本 ≥17，降级：`pip install frida==16.7.19` |
| mock_route 推送失败 | MockGPS App 未启动 / 屏幕熄灭被冻结；GUI 启动时会自动唤醒屏幕常亮 |
| 咕咚显示位置偏移 | 调整 `--offset-lat` / `--offset-lng`（每次调整 0.0001 度 ≈ 11m） |
| ReZygisk 启动即 Trap (exit 133) | Android 9 Pie64 环境不支持，放弃 Zygisk 路线，直接用 Frida |
| HAL 注入后 dumpsys 显示加速度计无数据 | 检查 `/data/bstfifo` 是否存在；frida_hal_inject.js 是否成功 spawn |
| 咕咚不订阅加速度计 | 检查 `frida_camouflage.js` 是否 attach 成功，看 `[REG]` 日志是否出现 sensor=1 |

---

## ⚠️ 免责声明

本项目仅用于**技术学习与研究**，探讨 Android 模拟器传感器注入、HAL 协议逆向、Frida 动态插桩等技术。请勿用于：
- 体育考试作弊
- 运动平台虚假记录
- 任何违反相关 App 用户协议或法律法规的用途

使用者自行承担一切后果。

---

## License

MIT
