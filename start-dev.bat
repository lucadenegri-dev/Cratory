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

rem --- DjOrganizer (app sorella) — avvia se presente, altrimenti salta ---
if not defined DJORG_DIR set "DJORG_DIR=%ROOT%..\DjOrganizer01"
set "DJORG_PYTHON=%DJORG_DIR%\backend\.venv\Scripts\python.exe"
if not exist "%DJORG_PYTHON%" (
    echo DjOrganizer non trovato in "%DJORG_DIR%" - avvio saltato.
    goto :djorg_done
)
if not exist "%DJORG_DIR%\frontend\node_modules" (
    echo DjOrganizer: dipendenze frontend mancanti - avvio saltato.
    goto :djorg_done
)
start "DjOrganizer Backend" cmd /k "cd /d ""%DJORG_DIR%\backend"" && ""%DJORG_PYTHON%"" -m uvicorn app.main:app --reload --port 8010"
start "DjOrganizer Frontend" cmd /k "cd /d ""%DJORG_DIR%\frontend"" && npm run dev -- --port 3010"
echo DjOrganizer backend:  http://localhost:8010/docs
echo DjOrganizer frontend: http://localhost:3010
:djorg_done

endlocal
