@echo off
setlocal
cd /d "%~dp0"
title StudyGraph Launcher - Live Study and Presentation Mode

echo ========================================================
echo         StudyGraph: Semester Knowledge Engine
echo ========================================================
echo.
echo Project Directory: %CD%
echo.

echo Starting FastAPI Backend on http://127.0.0.1:8000 ...
start "StudyGraph Backend" cmd /k "set PYTHONPATH=. && set OFFLINE_DEMO_MODE=false && python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload"

echo Starting Vite React Frontend on http://localhost:5173 ...
start "StudyGraph Frontend" cmd /k "cd frontend && npm run dev"

echo Waiting for services to initialize...
ping 127.0.0.1 -n 6 >nul

echo Opening browser...
start http://localhost:5173

echo.
echo ========================================================
echo StudyGraph is running!
echo Backend:  http://127.0.0.1:8000/docs
echo Frontend: http://localhost:5173
echo ========================================================
echo Keep this window or the spawned server windows open.
pause
