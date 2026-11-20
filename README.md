# MockGPS Desktop

用于开发和验证定位功能的 Windows 桌面工具。可以导入路线，在本机查看和回放，或把测试坐标发送到 Android Studio 启动的本机模拟器。

## 启动

安装含 Tcl/Tk 的 Python 3.10+，在项目目录双击 `Launch-MockGPS.cmd` 或运行 `python app.py`。打开后可点「示例路线」和「桌面预览」，直接查看移动轨迹。桌面预览无需连接 Android 设备。

如果要测试 Android 定位，从 Android Studio 启动虚拟设备并点击「检测」。工具会在 `PATH` 和常见 Android SDK 目录中查找 ADB，也可以点击「选择」指定 `adb.exe`。选好设备后，点击「发送起点」测试单个坐标，或点击「模拟器回放」按设定速度发送路线。停止后，模拟器会继续显示最后收到的坐标，可在模拟器定位面板另设位置。

## 路线格式

- TXT 每行写纬度、经度，中间用逗号或空格分隔。`PAUSE` 用于分段。默认 WGS84。GCJ-02 数据在首行写 `# coord_system=GCJ02`。
- GPX 支持轨迹和路线。KML 支持 `LineString`。

模拟器定位使用 [Android Emulator 控制台](https://developer.android.com/studio/run/emulator-console) 的 `geo fix`。坐标转换保留了附件中的 [第三方许可](coordinate_transform.LICENSE)。
