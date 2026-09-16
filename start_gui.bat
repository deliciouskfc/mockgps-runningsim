@echo off
chcp 65001 >nul
title MockGPS 跑步模拟器
cd /d "%~dp0pc"
python run_gui.py
if errorlevel 1 (
    echo.
    echo ====================================
    echo 启动失败，错误码 %errorlevel%
    echo 请确认：
    echo   1. 已安装 Python 3.10+ 并加入 PATH
    echo   2. 已执行 pip install frida==16.7.19 capstone
    echo   3. pc/run_gui.py 文件存在
    echo ====================================
    pause
)
