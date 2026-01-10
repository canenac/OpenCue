# OpenCue Backend Launcher
# Run with: .\Start-OpenCue.ps1

$Host.UI.RawUI.WindowTitle = "OpenCue Backend"

Write-Host ""
Write-Host "  ========================================" -ForegroundColor Cyan
Write-Host "   OpenCue Backend Starting..." -ForegroundColor White
Write-Host "  ========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "   WebSocket: " -NoNewline; Write-Host "ws://localhost:8765" -ForegroundColor Green
Write-Host "   Dashboard: " -NoNewline; Write-Host "http://localhost:8080" -ForegroundColor Green
Write-Host ""
Write-Host "   Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host "  ========================================" -ForegroundColor Cyan
Write-Host ""

Set-Location D:\opencue\backend
& ..\venv\Scripts\Activate.ps1
python -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
