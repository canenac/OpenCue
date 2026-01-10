@echo off
title OpenCue Backend
cd /d D:\opencue\backend
call ..\venv311\Scripts\activate.bat
echo.
echo  ========================================
echo   OpenCue Backend Starting...
echo  ========================================
echo.
echo   WebSocket: ws://localhost:8765
echo   Dashboard: http://localhost:8080
echo.
echo   Press Ctrl+C to stop
echo  ========================================
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
pause
