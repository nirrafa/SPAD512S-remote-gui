@echo off
title SPAD512 Remote Control (PRACTICE - fake camera)
cd /d "%~dp0.."
echo.
echo  ==================================================
echo   SPAD512 Remote Control  (PRACTICE mode)
echo  ==================================================
echo.
echo  This uses a FAKE camera so you can try the program
echo  safely. No real camera or vendor software needed.
echo  Do NOT use this mode while the real vendor software
echo  is running (they share the same connection).
echo.

rem ---- find Python ----------------------------------
set "PY=py -3"
py -3 --version >nul 2>nul
if errorlevel 1 set "PY=python"
%PY% --version >nul 2>nul
if errorlevel 1 goto nopython
%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto oldpython

rem ---- first-time setup -----------------------------
if exist ".venv\Scripts\python.exe" goto run
echo  First-time setup: preparing the Python environment.
echo  This needs internet and takes a few minutes. Please wait...
echo.
%PY% -m venv .venv
if errorlevel 1 goto setupfail
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto setupfail
echo.
echo  Setup finished!
echo.

:run
echo  Starting the fake camera + SPAD bridge...
echo  A browser window will open in a few seconds.
echo.
echo  KEEP THIS BLACK WINDOW OPEN while you practice.
echo  To stop everything: close this window, then close the
echo  small "SPAD fake camera" window in your taskbar too.
echo.
start "SPAD fake camera" /min ".venv\Scripts\python.exe" -m mock_server --port 9999
start "" /min cmd /c "timeout /t 6 /nobreak >nul & start http://localhost:8080"
".venv\Scripts\python.exe" -m uvicorn bridge.main:app --port 8080
echo.
echo  The bridge has stopped. Remember to also close the
echo  "SPAD fake camera" window if it is still open.
pause
exit /b 0

:nopython
echo  [PROBLEM] Python is not installed on this computer.
echo  Please do Step 1 of docs\windows_smoke_test.md first
echo  (install Python from python.org and tick "Add python.exe to PATH").
pause
exit /b 1

:oldpython
echo  [PROBLEM] The installed Python is too old (need 3.11 or newer).
echo  Please install the latest Python from python.org (see Step 1 of the guide).
pause
exit /b 1

:setupfail
echo  [PROBLEM] The first-time setup did not finish.
echo  Most common cause: no internet connection on this computer.
echo  Connect to the internet and double-click this file again.
pause
exit /b 1
