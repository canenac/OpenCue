' OpenCue Backend Launcher (runs minimized)
' Double-click to start, check system tray for icon

Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d D:\opencue\backend && ..\venv\Scripts\activate.bat && python -m uvicorn main:app --host 0.0.0.0 --port 8080", 0, False
