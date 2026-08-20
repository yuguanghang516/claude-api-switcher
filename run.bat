@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Claude API Switcher V1 - AI Gateway

:: ─── 查找真正的 Python ───
set "REAL_PYTHON="

:: 方法1: 检查常见安装路径
for %%p in (
    "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe"
    "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe"
    "C:\Program Files\Python311\python.exe"
    "C:\Program Files\Python310\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
) do (
    if exist "%%~p" (
        set "REAL_PYTHON=%%~p"
        goto :found_python
    )
)

:: 方法2: 尝试 where python（排除 Microsoft Store）
for /f "tokens=*" %%i in ('where python 2^>nul') do (
    echo %%i | findstr /i "WindowsApps" >nul
    if errorlevel 1 (
        set "REAL_PYTHON=%%i"
        goto :found_python
    )
)

:: 方法3: 尝试 py  launcher
where py >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('py -3.11 -c "import sys; print(sys.executable)" 2^>nul') do (
        set "REAL_PYTHON=%%i"
        goto :found_python
    )
)

:: 找不到 Python
echo.
echo ══════════════════════════════════════════════
echo   [错误] 未找到 Python！
echo ══════════════════════════════════════════════
echo.
echo   请安装 Python 3.10 或更高版本：
echo   https://www.python.org/downloads/
echo.
echo   安装时勾选 "Add Python to PATH"
echo.
pause
exit /b 1

:found_python
echo.
echo ══════════════════════════════════════════════
echo    Claude API Switcher V1 - AI Gateway
echo ══════════════════════════════════════════════
echo.
echo   Python: !REAL_PYTHON!
echo.

:: ─── 检查依赖 ───
!REAL_PYTHON! -c "import customtkinter, keyring, requests, flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo   缺少依赖，正在安装...
    echo.
    !REAL_PYTHON! -m pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo.
        echo   [错误] 依赖安装失败！
        pause
        exit /b 1
    )
)

:: ─── 启动程序 ───
echo   正在启动...
echo   关闭此窗口将退出程序
echo.

!REAL_PYTHON! main.py

:: 程序退出后暂停显示错误
echo.
echo ══════════════════════════════════════════════
echo   程序已退出，错误码: %errorlevel%
echo ══════════════════════════════════════════════
echo.
pause
