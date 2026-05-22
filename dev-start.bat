:: dev-start.bat — Start both servers for local development (Windows)
:: Run from the repo root.
:: Requires: Python venv at backend\venv, Node at frontend\node_modules

@echo off
echo Starting FastAPI backend on http://localhost:7860
echo Starting Angular frontend on http://localhost:4200
echo.

:: Set GEMINI_API_KEY and FIREBASE_CREDENTIALS_JSON before running the script otherwise the application will not work as intended.
:: Start backend in a new window
start "FastAPI Backend" cmd /k "cd backend && venv\Scripts\activate && uvicorn main:app --reload --port 7860"

:: Small delay then start Angular
timeout /t 2 /nobreak > nul
start "Angular Frontend" cmd /k "cd frontend && ng serve"

echo Both servers starting. Check the two new windows for logs.