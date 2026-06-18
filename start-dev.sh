#!/bin/zsh
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "▶ Backend..."
cd "$ROOT/backend"
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

echo "▶ Frontend..."
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Backend  → http://localhost:8000  (PID $BACKEND_PID)"
echo "Docs API → http://localhost:8000/docs"
echo "Frontend → http://localhost:3000  (PID $FRONTEND_PID)"
echo ""
echo "Premi Ctrl+C per fermare tutto."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo '\nServizi fermati.'" INT TERM
wait
