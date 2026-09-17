#!/system/bin/sh
# frida-server 开机自启（Magisk / Kitsune late_start service 阶段执行）
# 安装位置：/data/adb/service.d/frida-server.sh
# 等待系统启动完成后，以 root 后台拉起 frida-server16（回退 frida-server）

# 等待 boot_completed，最多约 120 秒
i=0
while [ "$(getprop sys.boot_completed)" != "1" ] && [ "$i" -lt 120 ]; do
    sleep 1
    i=$((i + 1))
done
sleep 5

# 选择二进制：优先 16 版本（匹配 frida-python 16.7.19）
BIN=/data/local/tmp/frida-server16
if [ ! -x "$BIN" ]; then
    BIN=/data/local/tmp/frida-server
fi

if [ -x "$BIN" ]; then
    chmod 755 "$BIN"
    # 已运行则不重复启动
    if ! pgrep -x "$(basename "$BIN")" >/dev/null 2>&1; then
        nohup "$BIN" >/dev/null 2>&1 &
    fi
fi
