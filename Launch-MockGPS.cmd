@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "MOCKGPS_PYTHON=.venv\Scripts\python.exe"
    goto launch
)
for /f "delims=" %%P in ('where python.exe 2^>nul') do (
    "%%P" -c "import sys, tkinter; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
    if not errorlevel 1 (
        set "MOCKGPS_PYTHON=%%P"
        goto launch
    )
)
for /d %%P in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%P\python.exe" (
        "%%P\python.exe" -c "import sys, tkinter; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
        if not errorlevel 1 (
            set "MOCKGPS_PYTHON=%%P\python.exe"
            goto launch
        )
    )
)
py.exe -3 -c "import sys, tkinter; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 (
    echo MockGPS Desktop requires Python 3.10 or newer with Tcl/Tk.
    pause
    exit /b 1
)
py.exe -3 -X utf8 app.py
goto done

:launch
"%MOCKGPS_PYTHON%" -X utf8 app.py

:done
if errorlevel 1 pause
