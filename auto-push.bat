@echo off
set /p desc="Enter commit description (Press Enter for 'Auto update'): "
if "%desc%"=="" set desc=Auto update
git add .
git commit -m "%desc%"
git push origin main
pause
