@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Claude API Switcher V1 - 环境配置
color 0B

echo.
echo ══════════════════════════════════════════════
echo    Claude API Switcher V1 - AI Gateway
echo    一键环境配置脚本
echo ══════════════════════════════════════════════
echo.

:: ─── 查找真正的 Python ───
set "REAL_PYTHON="

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

for /f "tokens=*" %%i in ('where python 2^>nul') do (
    echo %%i | findstr /i "WindowsApps" >nul
    if errorlevel 1 (
        set "REAL_PYTHON=%%i"
        goto :found_python
    )
)

echo   [×] Python 未找到！
echo.
echo   正在通过 winget 安装 Python 3.11...
echo   请稍候（可能需要几分钟）...
echo.
winget install Python.Python.3.11 --accept-source-agreements --accept-package-agreements --disable-interactivity
if !errorlevel! neq 0 (
    echo.
    echo   [错误] 自动安装失败！
    echo   请手动从 https://www.python.org/downloads/ 安装
    pause
    exit /b 1
)

:: 重新查找
for %%p in (
    "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe"
    "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe"
) do (
    if exist "%%~p" (
        set "REAL_PYTHON=%%~p"
        goto :found_python
    )
)

echo   [错误] 安装后仍找不到 Python！
pause
exit /b 1

:found_python
echo   [✓] Python: !REAL_PYTHON!
for /f "tokens=*" %%v in ('!REAL_PYTHON! --version') do echo       版本: %%v

:: ─── 升级 pip ───
echo.
echo   [1/3] 升级 pip...
!REAL_PYTHON! -m pip install --upgrade pip >nul 2>&1
echo   [✓] pip 已升级

:: ─── 安装依赖 ───
echo.
echo   [2/3] 安装项目依赖...
!REAL_PYTHON! -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo   [错误] 依赖安装失败！请检查网络。
    pause
    exit /b 1
)
echo   [✓] 依赖安装完成

:: ─── 安装 pytest ───
echo.
echo   [3/3] 安装测试框架...
!REAL_PYTHON! -m pip install pytest >nul 2>&1

:: ─── 运行测试 ───
echo.
echo   运行测试验证...
!REAL_PYTHON! -m pytest tests -q --tb=line
if !errorlevel! equ 0 (
    echo.
    echo   [✓] 所有测试通过！
) else (
    echo.
    echo   [!] 部分测试未通过
)

:: ─── 完成 ───
echo.
echo ══════════════════════════════════════════════
echo   配置完成！
echo.
echo   启动程序:  run.bat
echo   重新配置:  setup.bat
echo ══════════════════════════════════════════════
echo.
pause
