@echo off
setlocal
set "desc="
set /p desc="Enter commit description (Press Enter for 'Auto update'): "
if not defined desc set "desc=Auto update"
git add .
git commit -m "%desc%"
git push origin main
endlocal
pause
