@echo off
setlocal

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"
set "BACKEND_PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"

if not exist "%BACKEND_PYTHON%" (
    echo Backend virtualenv non trovata: "%BACKEND_PYTHON%"
    echo Crea la venv e installa le dipendenze come indicato nel README.
    exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
    echo Dipendenze frontend non trovate.
    echo Esegui prima "npm install" dentro la cartella frontend.
    exit /b 1
)

start "DJ Assistant Backend" cmd /k "cd /d ""%BACKEND_DIR%"" && ""%BACKEND_PYTHON%"" -m uvicorn app.main:app --reload --port 8000"
start "DJ Assistant Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && npm run dev"

echo Backend:  http://localhost:8000/docs
echo Frontend: http://localhost:3000

endlocal
