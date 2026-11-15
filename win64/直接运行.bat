@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 不打包，直接用 Python 运行（方便改代码时试）
where pythonw >nul 2>nul
if errorlevel 1 (
    echo 没找到 pythonw，尝试用 python 运行...
    python main.py
    pause
    exit /b
)
start "" pythonw "%~dp0main.py"
exit /b
