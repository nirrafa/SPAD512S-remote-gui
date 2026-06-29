@echo off
REM Double-click to start the SPAD GUI with the mock camera (Windows).
REM Launches mock vendor server + bridge + web GUI in separate windows,
REM then opens your browser. Close those windows to stop.

cd /d "%~dp0\.."
echo Project: %CD%

if not exist ".venv" (
  echo.
  echo No Python environment ^(.venv^) found. First-time setup, run once:
  echo   py -3.11 -m venv .venv ^&^& .venv\Scripts\activate ^&^& pip install -e ".[dev]"
  echo.
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"

if not exist "frontend\node_modules" (
  echo Installing web GUI dependencies ^(first run only^)...
  pushd frontend && call npm install && popd
)

echo Starting mock camera, bridge, and GUI...
start "SPAD Mock Camera" cmd /k "python -m mock_server --port 9999"
start "SPAD Bridge" cmd /k "uvicorn bridge.main:app --port 8080"
start "SPAD GUI" cmd /k "cd frontend && npm run dev"

timeout /t 5 >nul
start "" "http://localhost:5173"

echo.
echo ============================================================
echo   SPAD GUI launched in separate windows.
echo   Browser:  http://localhost:5173
echo   API docs: http://localhost:8080/docs
echo   Close the three windows to stop everything.
echo ============================================================
echo.
echo (To use the REAL camera instead of the mock: close the mock
echo  window and set SPAD_VENDOR_HOST / SPAD_VENDOR_PORT for the bridge.)
pause
