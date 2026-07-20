@echo off
setlocal
cd /d "%~dp0"

set PORT=5050
set URL=http://127.0.0.1:%PORT%

netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo Reelframe is already running — opening browser...
    start "" "%URL%"
    exit /b 0
)

echo Starting Reelframe...
start "Reelframe server" /min cmd /c "python app.py"

:waitloop
timeout /t 1 /nobreak >nul
curl -s -o nul "%URL%/api/projects"
if not %errorlevel%==0 goto waitloop

start "" "%URL%"
exit /b 0
