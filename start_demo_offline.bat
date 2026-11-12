@echo off
setlocal
cd /d "%~dp0"
title StudyGraph Launcher - Zero-Glitch Offline Demo Mode

echo ========================================================
echo   StudyGraph: Zero-Glitch Offline Presentation Mode
echo   (No Wi-Fi or Gemini API dependencies required)
echo ========================================================
echo.
echo Project Directory: %CD%
echo.

echo Starting FastAPI Backend in Offline Demo Mode on http://127.0.0.1:8000 ...
start "StudyGraph Backend (Offline Demo)" cmd /k "set PYTHONPATH=. && set OFFLINE_DEMO_MODE=true && python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload"

echo Starting Vite React Frontend on http://localhost:5173 ...
start "StudyGraph Frontend" cmd /k "cd frontend && npm run dev"

echo Waiting for services to initialize...
ping 127.0.0.1 -n 6 >nul

echo Opening browser...
start http://localhost:5173

echo.
echo ========================================================
echo StudyGraph is running in OFFLINE DEMO MODE!
echo - Graphs served from frozen real snapshot (demo_data/)
echo - Live upload step runs instantly with pre-cached links
echo - Grounded study chat answers from verified citations
echo - Safe to turn off Wi-Fi completely on stage!
echo ========================================================
echo Keep this window or the spawned server windows open.
pause
