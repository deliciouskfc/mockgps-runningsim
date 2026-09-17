---
name: mockgps-runningsim
description: 在 BlueStacks 5 安卓模拟器中模拟户外跑步。沿指定轨迹循环移动、注入 50Hz 跑步加速度波形到传感器 HAL、伪装加速度计规格为 BMI260，让咕咚/高德等运动 App 记录到稳定的配速、步频与轨迹。提供 Tkinter GUI 一键启动/停止，无需记忆命令行参数。触发词：跑步模拟、mockgps、咕咚刷步数、BlueStacks 跑步、HAL 加速度注入、bstfifo、frida 传感器伪装。
---

# MockGPS 跑步模拟器 Skill

> 给 AI agent 用的使用说明。Agent 看到本文件后应能直接指导用户完成完整流程，或自动调用脚本启动模拟。

## 何时使用本 Skill

**触发场景**（满足任一即用）：
- 用户说"我想在蓝叠/BlueStacks 里跑步"、"模拟跑步给咕咚/高德看"
- 用户提到"刷步数"、"mockgps"、"模拟 GPS 跑步"
- 用户提到"加速度注入"、"bstfifo"、"传感器伪装"、"frida 传感器 hook"
- 用户在 `pc/run_gui.py` 或 `pc/mock_route.py` 上下文里要求开始/停止/调参

**不适用场景**：
- 真机 GPS 模拟（本 skill 专为 BlueStacks 5 设计）
- 体育考试作弊（违反本 skill 免责声明，应拒绝）

## 前置依赖检查清单

Agent 启动前**必须逐项确认**：

```
□ BlueStacks 5.22+ 已安装，Pie64 实例运行中（adb devices 能看到 emulator-5554）
□ BlueStacks 已 root（adb shell su -c id 返回 uid=0）
□ frida-server 16.7.19 x86_64 已部署到 /data/local/tmp/frida-server16，并配置开机自启（tools/frida_boot.sh → /data/adb/service.d/frida-server.sh）。重启模拟器后自动运行；GUI 启动时还会检测并兜底拉起（frida-ps -U 能列出进程即就绪）
□ PC 端 pip install frida==16.7.19 capstone
□ MockGPS APK 已安装并被设为「模拟位置应用」
□ 咕咚 com.codoon.gps 已安装并登录
□ 轨迹文件 pc/track_final.txt 存在
□ adb 在 PATH 中
```

任何一项缺失时，先指导用户补全再继续。

## 一键启动流程（推荐 GUI）

Agent 执行：

```bash
cd c:\Users\admin\Documents\trae_projects\run\pc
python run_gui.py
```

GUI 出现后告知用户：
1. 点「浏览」选 `track_final.txt`（默认操场 400m 轨迹）
2. 默认参数已填好（速度 12 km/h、波动 1.5、步频 168、晃动 3.0、offset -0.000728/0.001907 已校准）
3. 点紫色「开始跑步」按钮
4. 日志区应出现三路输出：
   - `[hal]`（黄）：`[hal] status: {"fd":N,"frames":N,"cfg":{...}}`
   - `[camo]`（青）：`[attach] loaded. Ctrl+C to stop.`
   - `[route]`（绿）：`已连接手机 MockGPS 服务（Socket 通道）` + 进度行
5. 运行中拖动步频滑块 → ≤1s 内 `[hal]` 显示 `sync cadence=新值`
6. 点灰色「停止」→ 所有子进程退出，Android 收到 QUIT

## 命令行三终端流程（如 GUI 不可用）

### 终端 1：HAL 加速度注入

```bash
cd c:\Users\admin\Documents\trae_projects\run\pc
python frida_hal_run.py
```

预期输出：
```
[hal] spawning native host /system/bin/sleep ...
[hal] host pid=XXXX
[hal] status: {"fd":3,"frames":0,"cfg":{"running":1,"cadence":168,...}}
[hal] sync run=1 cadence=168
```

### 终端 2：传感器伪装

```bash
cd c:\Users\admin\Documents\trae_projects\run\pc
python frida_attach.py frida_camouflage.js
```

预期输出：
```
[attach] pid=XXXX script=frida_camouflage.js
[attach] loaded. Ctrl+C to stop.
```

### 终端 3：GPS 路径回放

```bash
cd c:\Users\admin\Documents\trae_projects\run\pc
python mock_route.py track_final.txt \
    --speed-kmh 12 \
    --speed-var 1.5 \
    --wobble 3.0 \
    --offset-lat -0.000728 \
    --offset-lng 0.001907 \
    --loops 0 \
    -s emulator-5554
```

预期输出：
```
路线点数: 421
总距离: 400.5 m (0.40 km)
速度: 12.0 km/h (3.33 m/s)
已连接手机 MockGPS 服务（Socket 通道）
===== 开始第 1 圈 =====
  [1] 进度   0.0%  (     0.0/400.5m)  lat=22.6877725 lng=114.2034827 ...
```

## 调整步频（运行中即时生效）

直接覆写 `pc/cadence_state.txt`：

```
running=1
cadence=180
```

保存后 ≤1s 内 HAL 注入器会通过 RPC 同步新步频，无需重启任何子进程。

**GUI 方式**：拖动步频滑块即可，debounce 300ms 自动写入。

## 调整位置偏移（修正咕咚显示偏移）

咕咚地图上看到的位置与操场跑道线偏移时，调整 `--offset-lat` / `--offset-lng`：
- 每调整 0.0001 度 ≈ 11 米
- `--offset-lat` 正值=北移，负值=南移
- `--offset-lng` 正值=东移，负值=西移

校准成功的默认值：`--offset-lat=-0.000728 --offset-lng=0.001907`

GUI 在「高级参数」折叠区里调整。

## 故障排查决策树

```
现象：咕咚步频始终为 0 或 20
├─ 检查 dumpsys sensorservice Active connections 是否有 com.codoon 包名订阅加速度计
│  ├─ 有 → 检查 frida_hal_inject.js 是否在写 /data/bstfifo（看 [hal] frames 计数是否增长）
│  │  └─ 增长 → HAL 数据已注入，问题在咕咚内部判定算法（可能需要更高步频或更长观察时间）
│  │  └─ 不增长 → 检查 frida-server 是否以 root 运行；检查 /data/bstfifo 是否存在
│  └─ 无 → 咕咚未订阅加速度计
│     ├─ 检查 frida_camouflage.js 是否 attach 成功（看 [camo] 日志）
│     ├─ 检查加速度计规格是否被伪装成 BMI260（dumpsys sensorservice 看 maxRange/minDelay）
│     └─ 仍无效 → 咕咚可能用 Orientation Sensor 计步，需要 hook libsensor.so 的 SensorEventQueue::injectSensorEvent
│
现象：mock_route 报 "无法连接手机 MockGPS 服务"
├─ adb devices 确认 emulator-5554 在线
├─ adb shell am start -n com.mockgps/.MainActivity 手动启动 App
├─ adb forward tcp:17890 tcp:17890 手动建立端口转发
└─ adb shell svc power stayon true 防止屏幕熄灭冻结进程
│
现象：Frida 报 "Java is not defined"
└─ frida-python 版本 ≥17。降级：pip install frida==16.7.19 frida-tools==12.x
│
现象：ReZygisk 启动即 Trap (exit 133 = SIGTRAP)
└─ Android 9 Pie64 环境不支持 ReZygisk（v1.0.0 移除 Kitsune 支持，rc.9 也 Trap）。放弃 Zygisk 路线，直接用 Frida
│
现象：BlueStacks 重启后位置偏移又出现
└─ NETWORK 定位源残留旧位置。确保 mock_route 注入 GPS+NETWORK+FUSED 三源同步；如有残留，先 adb shell svc wifi disable 切断 WiFi 定位源
```

## 关键文件路径速查

| 用途 | 文件 |
|------|------|
| GUI 主入口 | `pc/run_gui.py` |
| GPS 回放脚本 | `pc/mock_route.py` |
| HAL 加速度注入 JS | `pc/frida_hal_inject.js` |
| HAL 注入 runner | `pc/frida_hal_run.py` |
| 传感器伪装 JS | `pc/frida_camouflage.js` |
| 通用 attach runner | `pc/frida_attach.py` |
| 步频状态文件（联动信道） | `pc/cadence_state.txt` |
| 默认操场轨迹 | `pc/track_final.txt` |
| Android MockGPS 服务 | `android/app/src/main/java/com/mockgps/MockLocationService.kt` |
| frida-server 开机自启脚本 | `tools/frida_boot.sh`（安装到设备 `/data/adb/service.d/frida-server.sh`） |
| HAL 反汇编工具 | `tools/disasm_hal.py` |

**GPS Socket 协议**（PC → Android:17890，每行）：`纬度,经度,精度,方位,速度,海拔`，如 `22.6877725,114.2034827,5.00,90.00,3.333,32.75`；`QUIT` 停止服务。Android 端兼容缺第 6 字段（海拔默认 0）。

## 关键参数表

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 速度 | 12 km/h | 5 min/km 配速 |
| 速度波动 | ±1.5 km/h | 均值回归保证平均配速 |
| 步频 | 168 spm | 典型跑步步频 160-180 |
| 晃动幅度 | 3.0 m | 跑步左右晃动模拟真人 |
| 基准海拔 | 30 m | 避免运动 App 海拔恒为 0 |
| 海拔波动 | ±5 m | 90s 周期缓坡正弦(60%)+均值回归游走(40%)，平滑变化；0=关闭 |
| 推送间隔 | 1.0 s | GPS 坐标推送频率 |
| 纬度偏移 | -0.000728 | 修正咕咚显示偏移（港中深操场校准值） |
| 经度偏移 | 0.001907 | 同上 |
| 循环次数 | 0 | 0=无限循环 |
| HAL 注入频率 | 50 Hz | 每帧 20ms，模拟跑步加速度波形 |
| 着地峰值 | ~18 m/s² | impact=11.0, bounce=3.2 |
| 摆臂幅度 | 5.0 / 2.6 m/s² | swingX / swingY |

## HAL 加速度注入公式

```
raw_int32 = round(-value_mps2 / 9.80665 × 1e6)
HAL 输出 = (raw_int32 / 1e6) × (-9.80665)
```

帧格式：12 字节 = 3 × int32 LE（x, y, z），通过 `/data/bstfifo` 命名管道写入。

跑步波形（50Hz）：
- 步频相位：`ph = 2π × (cadence/60) × t`
- z 轴：`G + impact × (0.5 - 0.5×cos(ph))^6 + bounce × sin(2ph - 0.6)`
- x 轴：`swingX × sin(ph + π/2) + 0.8 × swingX × sin(2ph + 0.4)`
- y 轴：`swingY × sin(ph + 0.4) + 0.5 × swingY × sin(2ph + 1.1)`
- 噪声：σ = 0.7 m/s² 高斯

## 安全与免责

⚠️ **仅用于技术学习与研究**：Android 模拟器传感器注入、HAL 协议逆向、Frida 动态插桩等技术的学习。**禁止**用于体育考试作弊、运动平台虚假记录、违反 App 用户协议或法律法规的用途。使用者自行承担一切后果。

## Agent 调用示例

用户："帮我在蓝叠里跑步"

Agent 行为：
1. 读 SKILL.md 前置依赖检查清单，逐项确认
2. 缺失项指导用户补全
3. 全部就绪后执行 `python pc/run_gui.py`
4. 告知用户 GUI 操作步骤
5. 等待用户反馈，按故障排查决策树处理

用户："步频调到 180"

Agent 行为：
- 如 GUI 在运行：告诉用户拖动步频滑块
- 如命令行模式：覆写 `pc/cadence_state.txt` 为 `running=1\ncadence=180\n`
- 等待 `[hal] sync cadence=180` 日志确认

用户："咕咚位置偏了 10 米往北"

Agent 行为：
- 调整 `--offset-lat` 增加 `0.0001`（北移 11m）
- GUI 模式：在「高级参数」里改纬度偏移字段
- 命令行模式：重启 mock_route.py 带新参数
