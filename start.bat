@echo off
chcp 65001 >nul 2>nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

title 书山有路 AI伴学
echo ============================================
echo   书山有路 - AI 主动伴学 · 一键启动
echo   %CD%
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] 未找到 Python，请先安装 https://python.org
    goto END_ERROR
)

where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] 未找到 Node.js，请先安装 https://nodejs.org
    goto END_ERROR
)

:: ============================================================
:: [1/2] Backend Python packages
:: ============================================================
echo [1/2] 后端 :8000 ...
cd backend

if exist "data\deps_ok" goto BACKEND_DONE

if not exist "data" mkdir "data"
set "PIP_LOG=%~dp0data\pip_install.log"
set RETRY=1

:PIP_INSTALL
echo.
echo   [尝试 !RETRY!/3] 安装 Python 依赖 ...
if !RETRY! EQU 1 (
    pip install -r requirements.txt --default-timeout=300 --no-cache-dir --log="!PIP_LOG!" 2>&1
) else if !RETRY! EQU 2 (
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --default-timeout=300 --no-cache-dir --log="!PIP_LOG!" 2>&1
) else (
    pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple --default-timeout=300 --no-cache-dir --log="!PIP_LOG!" 2>&1
)

if not errorlevel 1 goto PIP_OK
set /a RETRY+=1
if !RETRY! LEQ 3 (
    echo   [WARN] 安装失败，换源重试...
    ping -n 3 127.0.0.1 >nul
    goto PIP_INSTALL
)
echo   [ERROR] 依赖安装失败，日志: !PIP_LOG!
goto END_ERROR

:PIP_OK
echo ok > "data\deps_ok"
echo   Python 依赖安装完成。

:BACKEND_DONE
cd /d "%~dp0"

:: ============================================================
:: [2/2] Frontend Node packages
:: ============================================================
echo.
echo [2/2] 前端 :5173 ...
cd frontend

if exist "node_modules" goto FRONTEND_DONE

echo   首次运行，安装 Node 依赖...
set NPM_RETRY=1
:NPM_INSTALL
echo   [尝试 !NPM_RETRY!/3]
call npm install --fetch-timeout=120000
if not errorlevel 1 goto NPM_OK
set /a NPM_RETRY+=1
if !NPM_RETRY! LEQ 3 (
    echo   [WARN] npm 安装失败，重试...
    ping -n 3 127.0.0.1 >nul
    goto NPM_INSTALL
)
echo   [ERROR] npm 安装失败。
goto END_ERROR

:NPM_OK
echo   Node 依赖安装完成。

:FRONTEND_DONE
cd /d "%~dp0"

:: ============================================================
:: Start services
:: ============================================================
echo.
echo 正在启动...
echo   后端 -> http://localhost:8000/docs
echo   前端 -> http://localhost:5173
echo.
start "YuanQi-Backend" /D "%~dp0backend" cmd /k python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app
start "YuanQi-Frontend" /D "%~dp0frontend" cmd /k npm run dev

start "" /b powershell -NoProfile -WindowStyle Hidden -Command "$ok=$false; for ($i=0; $i -lt 60; $i++) { try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 5173); $c.Close(); $ok=$true; break } catch { Start-Sleep 1 } }; if ($ok) { Start-Process 'http://localhost:5173' }"

echo.
echo   已启动！浏览器将自动打开。
echo   关闭 CMD 窗口即可停止服务。
echo.
pause
endlocal
exit /b 0

:END_ERROR
echo.
echo   启动失败。
cd /d "%~dp0"
pause
endlocal
exit /b 1
