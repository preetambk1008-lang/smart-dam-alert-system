@echo off
setlocal
title JalSuraksha - Smart Dam & Flood Alert System
cd /d "%~dp0"
echo Starting JalSuraksha API server...
where py >nul 2>nul
if %errorlevel%==0 (
    start "JalSuraksha API" "%~dp0backend\run_server.bat"
) else (
    where python >nul 2>nul
    if not %errorlevel%==0 (
        echo Python 3 was not found. Install Python 3 and try again.
        pause
        exit /b 1
    )
    start "JalSuraksha API" "%~dp0backend\run_server.bat"
)
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:5000"
echo Dashboard opened at http://127.0.0.1:5000
echo Farmer portal: http://127.0.0.1:5000/farmer
echo Keep the JalSuraksha API window open while using the dashboards.
endlocal
