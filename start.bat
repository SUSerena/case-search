@echo off
chcp 65001 >nul
title 深水网箱案例检索系统

echo ========================================
echo  深水网箱/浮动平台历史案例智能检索系统
echo ========================================
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 检查Python
where python >nul 2>nul
if %errorlevel%==0 (
    set PYTHON=python
    goto :check_deps
)

where py >nul 2>nul
if %errorlevel%==0 (
    set PYTHON=py
    goto :check_deps
)

REM 尝试常见安装路径
if exist "C:\Python312\python.exe" set PYTHON=C:\Python312\python.exe & goto :check_deps
if exist "C:\Python311\python.exe" set PYTHON=C:\Python311\python.exe & goto :check_deps
if exist "C:\Python310\python.exe" set PYTHON=C:\Python310\python.exe & goto :check_deps

echo [错误] 未找到Python，请先安装Python 3.8+
echo 下载地址: https://www.python.org/downloads/
pause
exit /b 1

:check_deps
echo 检查依赖...
%PYTHON% -c "import flask, pandas, openpyxl, xlrd" 2>nul
if %errorlevel%==0 (
    goto :start_app
)

echo 正在安装依赖包（首次运行可能需要几分钟）...
%PYTHON% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo [警告] 清华源安装失败，尝试使用官方源...
    %PYTHON% -m pip install -r requirements.txt
)

:start_app
echo.
echo 启动应用...
echo.
echo 访问地址: http://127.0.0.1:5000
echo 按 Ctrl+C 停止服务
echo.

%PYTHON% app.py

pause
