@echo off
chcp 65001 >nul 2>nul
setlocal EnableExtensions
title ASI-HACK Space Analytics Engine - Ai.Mors
color 0B

rem =====================================================================
rem  ASI-HACK SPACE ANALYTICS ENGINE - ONE-CLICK LAUNCHER
rem  اضغط مرتين على هذا الملف لتشغيل النظام كاملاً وفتح لوحة التحكم
rem
rem  What it does:
rem    1) Locates a usable Python 3.10+
rem    2) Installs any missing libraries (requirements.txt)
rem    3) Starts the Flask backend (main.py)
rem    4) Waits until the API is healthy
rem    5) Opens the MORS command center in your default browser
rem    6) Keeps the server running until you close this window
rem =====================================================================

cd /d "%~dp0"
echo.
echo  ==================================================================
echo    ASI-HACK SPACE ANALYTICS ENGINE ^| Ai.Mors
echo    Multi-Agent Verified Pipeline (NASA + Gemini + Astropy)
echo  ==================================================================
echo.

rem ---------------- 1) find python ------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if defined PY goto :havepy
where python >nul 2>nul && set "PY=python"
if defined PY goto :havepy
where python3 >nul 2>nul && set "PY=python3"
if defined PY goto :havepy

echo  [X] Python was not found on this PC.
echo.
echo      Please install Python 3.10+ from https://www.python.org/downloads/
echo      IMPORTANT: tick "Add python.exe to PATH" during installation.
echo.
pause
exit /b 1

:havepy
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo  [OK] Python found: %%v

rem ---------------- 2) install dependencies ---------------------------
echo.
echo  [..] Checking required libraries (this runs only once)...
%PY% -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo  [!] Some packages could not be installed automatically.
    echo      Try manually:  %PY% -m pip install -r requirements.txt
    echo      Continuing anyway - the app degrades gracefully offline.
) else (
    echo  [OK] Libraries ready.
)

rem ---------------- 3) free the port if busy --------------------------
rem  netstat lines look like:
rem    TCP    127.0.0.1:5000         0.0.0.0:0              LISTENING       18372
rem  Split on whitespace the columns are:
rem    1=TCP 2=local-address 3=foreign-address 4=state 5=PID
rem  NOTE: keep the default (space) delimiters — adding ":" to delims
rem        makes cmd abort the FOR loop with `:" was unexpected`.
set "PORT=5000"
if not "%FLASK_PORT%"=="" set "PORT=%FLASK_PORT%"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :%PORT% ^| findstr LISTENING') do (
    echo  [..] Port %PORT% is busy - stopping old process PID %%p
    taskkill /F /PID %%p >nul 2>nul
)

rem ---------------- 4) start backend -----------------------------------
echo.
echo  [..] Starting backend on http://127.0.0.1:%PORT% ...
echo.

start "ASI-HACK Backend" /min cmd /c "%PY% main.py"

rem ---------------- 5) wait until healthy ------------------------------
set /a TRIES=0
:waitloop
set /a TRIES+=1
if %TRIES% gtr 60 goto :timeout
%PY% -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%PORT%/api/health',timeout=2).status==200 else 1)" >nul 2>nul
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto :waitloop
)

echo  [OK] Backend is UP and healthy.
echo.
echo  ==================================================================
echo    Command center : http://127.0.0.1:%PORT%/mors
echo    Legacy page    : http://127.0.0.1:%PORT%/
echo    Health         : http://127.0.0.1:%PORT%/api/health
echo    Open the command center, then press "Run Pipeline".
echo    Close THIS window to stop the server.
echo  ==================================================================
echo.

rem ---------------- 6) open browser ------------------------------------
start "" "http://127.0.0.1:%PORT%/mors"

echo  Server is running. You can close this window to stop it.
echo  (A minimized "ASI-HACK Backend" window holds the server process.)
pause >nul
exit /b 0

:timeout
echo.
echo  [X] The server did not become healthy within 60 seconds.
echo      Possible causes:
echo        - a firewall is blocking localhost
echo        - another program owns port %PORT%
echo        - check the minimized "ASI-HACK Backend" window for errors
echo.
pause
exit /b 1
