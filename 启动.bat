@echo off
title A股题材产业链分析工具 v3.5
cd /d "%~dp0"

echo.
echo ========================================
echo   A 股题材产业链分析工具 v3.5
echo ========================================
echo.

:: 检查虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境，请先运行: python -m venv .venv
    pause
    exit /b 1
)

echo [1/3] 激活虚拟环境...
call .venv\Scripts\activate.bat

echo [2/3] 检查依赖...
pip install -r requirements.txt -q

echo [3/3] 启动应用...
echo.
echo 浏览器将自动打开 http://localhost:8501
echo 按 Ctrl+C 停止应用
echo.

start http://localhost:8501
streamlit run app.py --server.headless true

pause
