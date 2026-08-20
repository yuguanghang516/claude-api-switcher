@echo off
chcp 65001
title 诊断工具
echo.
echo === 诊断开始 ===
echo.
echo [1] 检查 Python...
where python
echo.
echo [2] Python 版本...
python --version
echo.
echo [3] 检查真实 Python...
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe" (
    echo 找到: C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe
    "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe" --version
) else (
    echo 未找到 Python311
)
echo.
echo [4] 测试导入...
C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe -c "import customtkinter; print('customtkinter OK')"
echo.
echo === 诊断完成 ===
echo.
pause
