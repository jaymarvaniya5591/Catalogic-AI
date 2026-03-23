@echo off
echo ========================================
echo   Ruva Catalog Generator
echo ========================================
echo.

:: Auto-setup: install dependencies if needed
pip show uvicorn >nul 2>&1
if %errorlevel% neq 0 (
    echo First time? Installing dependencies...
    pip install -r requirements.txt
    echo.
)

:: Auto-setup: install Playwright browser if needed
python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(); b.close(); p.stop()" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing browser for scraping...
    python -m playwright install chromium
    echo.
)

:: Kill anything already running on port 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo Server starting at: http://localhost:8000
echo Press Ctrl+C to stop
echo.
python -m uvicorn server:app
