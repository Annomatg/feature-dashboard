@echo off
REM Start both Backend (via DevServer) and Frontend servers
echo ========================================
echo Feature Dashboard - Start All Servers
echo ========================================
echo.

REM Get the directory where this batch file is located
set SCRIPT_DIR=%~dp0

REM Check if DevServer is already running by checking port 8000
echo Checking if backend is already running...
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo.
    echo WARNING: Port 8000 is already in use!
    echo DevServer or backend may already be running.
    echo.
    choice /C YN /M "Do you want to continue anyway (may fail)"
    if errorlevel 2 goto :EOF
    echo.
)

echo Starting DevServer (Backend)...
REM Start DevServer (which manages the backend) in a new window
start "Feature Dashboard Backend (DevServer)" cmd /k "cd /d "%SCRIPT_DIR%" && dotnet run --project DevServer"

echo Waiting for backend to initialize...
timeout /t 5 /nobreak >nul

echo Starting Frontend...
REM Start frontend in a new window
start "Feature Dashboard Frontend" cmd /k "cd /d "%SCRIPT_DIR%frontend" && echo Starting Frontend on http://localhost:5173 && timeout /t 2 /nobreak >nul && start http://localhost:5173 && npm run dev"

echo.
echo ========================================
echo Both servers are starting!
echo ========================================
echo Backend (DevServer): http://localhost:8000
echo                      http://localhost:8000/docs
echo Frontend:            http://localhost:5173
echo.
echo Each server runs in a separate window.
echo Close the individual windows to stop them.
echo.
echo Press any key to close this window...
pause >nul
