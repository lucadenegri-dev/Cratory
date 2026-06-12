@echo off
rem Avvia il dev server Next.js garantendo Node nel PATH (usato da .claude/launch.json)
set "PATH=%PATH%;C:\Program Files\nodejs"
cd /d "%~dp0"
call npm run dev %*
