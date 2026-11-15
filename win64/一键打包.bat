@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo   电池医生 Windows 版 - 一键打包
echo ============================================
echo.

rem ---------- 找 Python ----------
set "PY="
for %%P in (py python python3) do (
    if not defined PY (
        where %%P >nul 2>nul && set "PY=%%P"
    )
)
if not defined PY goto :nopython

%PY% -c "import sys; print('Python', sys.version.split()[0])" || goto :nopython
echo.

rem ---------- 装 PyInstaller ----------
%PY% -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo [1/3] 首次运行，正在安装打包工具 PyInstaller ...
    %PY% -m pip install --upgrade pip >nul 2>nul
    %PY% -m pip install pyinstaller
    if errorlevel 1 goto :nopip
) else (
    echo [1/3] PyInstaller 已安装，跳过
)
echo.

rem ---------- 开始打包 ----------
echo [2/3] 正在打包，第一次大约需要 1-3 分钟 ...
echo.
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name BatteryDoctor ^
    --icon "icon.ico" ^
    --add-data "icon.ico;." ^
    main.py
if errorlevel 1 goto :buildfail
echo.

rem ---------- 收尾 ----------
echo [3/3] 打包完成
echo.
if exist "dist\BatteryDoctor.exe" (
    echo   成品： %~dp0dist\BatteryDoctor.exe
    echo   大小： 
    for %%F in ("dist\BatteryDoctor.exe") do echo         %%~zF 字节
    echo.
    echo   这个 exe 可以单独拷给别人，不需要装 Python。
    echo   Windows 10 / 11 直接双击即可运行。
    echo.
    choice /c YN /n /m "现在就打开 dist 文件夹吗? [Y/N] "
    if !errorlevel! equ 1 start "" "%~dp0dist"
) else (
    echo   没有找到成品，请把上面的报错发给我。
)
echo.
pause
exit /b 0

:nopython
echo.
echo [错误] 没有找到 Python。
echo.
echo   请先安装 Python 3.9 或更高版本： https://www.python.org/downloads/
echo   安装时务必勾选 "Add python.exe to PATH"。
echo.
pause
exit /b 1

:nopip
echo.
echo [错误] PyInstaller 安装失败，通常是网络问题。
echo   可以手动执行： python -m pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.
pause
exit /b 1

:buildfail
echo.
echo [错误] 打包过程报错了，把上面的信息发给我看看。
echo.
pause
exit /b 1
