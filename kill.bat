@echo off
echo ========================================
echo   Killing all servers on port 8000
echo ========================================
echo.

set found=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING 2^>nul') do (
    echo Killing process %%a...
    taskkill /PID %%a /F >nul 2>&1
    set found=1
)

if %found%==0 (
    echo Nothing running on port 8000. All clear!
) else (
    echo.
    echo All servers stopped.
)
