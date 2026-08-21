@echo off
REM Starts every part of this project's "menus" together:
REM   - Reelframe (main app, port 5050)     -- Timeline + Bar Race Chart + Image to Video tabs
REM   - Bar Race Studio backend (port 8000) -- FastAPI, powers the "Bar Race Chart" tab
REM   - Bar Race Studio frontend (port 5173) -- Vite dev server, embedded via iframe
REM
REM Run this after every `git pull` -- it installs any missing dependencies
REM (fast/no-op if already installed) before starting fresh servers, so a
REM clean checkout works without extra manual setup steps.
setlocal
cd /d "%~dp0"

echo.
echo === Checking backend dependencies (bar-race-studio) ===
pushd bar-race-studio\backend
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [FAILED] pip install for bar-race-studio backend. Fix the error above and re-run.
    popd
    pause
    exit /b 1
)
python -m playwright install chromium
popd

echo.
echo === Checking frontend dependencies (bar-race-studio) ===
pushd bar-race-studio\frontend
call npm install
if errorlevel 1 (
    echo [FAILED] npm install for bar-race-studio frontend. Fix the error above and re-run.
    popd
    pause
    exit /b 1
)
popd

echo.
echo === Starting Bar Race Studio backend on http://localhost:8000 ===
start "Bar Race Studio - Backend (8000)" cmd /k "cd /d "%~dp0bar-race-studio\backend" && python -m uvicorn app.main:app --port 8000"

echo === Starting Bar Race Studio frontend on http://localhost:5173 ===
start "Bar Race Studio - Frontend (5173)" cmd /k "cd /d "%~dp0bar-race-studio\frontend" && npm run dev"

echo === Starting Reelframe (main app) on http://localhost:5050 ===
start "Reelframe - Main App (5050)" cmd /k "cd /d "%~dp0" && python app.py"

echo.
echo All three servers are starting in their own windows.
echo Give them a few seconds, then open http://localhost:5050
echo   - Timeline tab: works immediately
echo   - Bar Race Chart tab: waits on the backend/frontend windows above
echo   - Image to Video tab: works immediately, part of the main app
echo.
echo If a tab still looks wrong after this: hard-refresh the browser
echo (Ctrl+Shift+R) to rule out a cached old page, and check the three
echo windows this script opened for any error text.
pause
