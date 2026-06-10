@echo off
title MAIA
color 0a

echo [1/3] Clonning


echo [2/3] Injector baslatiliyor...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\sel_temp" "https://www.chess.com/play/online"

echo [3/3] Bot baslatiliyor...
echo.
python main.py

pause