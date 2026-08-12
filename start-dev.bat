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

rem --- slskd (Soulseek download) — opzionale: avvia se presente, altrimenti salta ---
if not defined SLSKD_BIN set "SLSKD_BIN=%USERPROFILE%\slskd\slskd.exe"
if not defined SLSKD_CONFIG set "SLSKD_CONFIG=%USERPROFILE%\.config\slskd\slskd.yml"
if exist "%SLSKD_BIN%" (
    start "slskd" cmd /k ""%SLSKD_BIN%" --config "%SLSKD_CONFIG%""
    echo slskd:    http://localhost:5030
) else (
    echo slskd non trovato in "%SLSKD_BIN%" - download Soulseek disabilitato.
)

start "DJ Assistant Backend" cmd /k "cd /d ""%BACKEND_DIR%"" && ""%BACKEND_PYTHON%"" -m uvicorn app.main:app --reload --port 8000"
start "DJ Assistant Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && npm run dev"

echo Backend:  http://localhost:8000/docs
echo Frontend: http://localhost:3000
echo Organize: http://localhost:3000/organize

rem Sortory non si avvia piu' a parte: e' la sezione /organize di questa app
rem (fusione F1). Avviarlo in parallelo farebbe scrivere due processi sullo
rem stesso djorganizer.db e sugli stessi file su disco.

endlocal
