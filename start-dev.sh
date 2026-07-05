#!/bin/zsh
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

# --- slskd (Soulseek download) — opzionale ---
# Override possibili: SLSKD_BIN, SLSKD_CONFIG. Default = installazione locale.
SLSKD_BIN="${SLSKD_BIN:-$HOME/Applications/slskd/slskd}"
SLSKD_CONFIG="${SLSKD_CONFIG:-$HOME/.config/slskd/slskd.yml}"
SLSKD_PID=""
if nc -z 127.0.0.1 5030 2>/dev/null; then
  echo "▶ slskd già in esecuzione su :5030 (lo lascio com'è)."
elif [[ -x "$SLSKD_BIN" && -f "$SLSKD_CONFIG" ]]; then
  echo "▶ slskd..."
  "$SLSKD_BIN" --config "$SLSKD_CONFIG" > "$HOME/.config/slskd/slskd.log" 2>&1 &
  SLSKD_PID=$!
else
  echo "• slskd non avviato (binario/config non trovati → download Soulseek disabilitato)."
fi

echo "▶ Backend..."
cd "$ROOT/backend"
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

echo "▶ Frontend..."
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

# --- DjOrganizer (app sorella) — avvia se presente, altrimenti salta ---
# Override possibile: DJORG_DIR. Default = cartella sorella di DJProject01.
DJORG_DIR="${DJORG_DIR:-$ROOT/../DjOrganizer01}"
DJORG_BACKEND_PID=""
DJORG_FRONTEND_PID=""
if [[ -x "$DJORG_DIR/backend/.venv/bin/python" && -d "$DJORG_DIR/frontend/node_modules" ]]; then
  echo "▶ DjOrganizer backend..."
  cd "$DJORG_DIR/backend"
  ./.venv/bin/python -m uvicorn app.main:app --reload --port 8010 &
  DJORG_BACKEND_PID=$!

  echo "▶ DjOrganizer frontend..."
  cd "$DJORG_DIR/frontend"
  npm run dev -- --port 3010 &
  DJORG_FRONTEND_PID=$!
else
  echo "• DjOrganizer non avviato (venv/node_modules non trovati in $DJORG_DIR)."
fi

echo ""
[[ -n "$SLSKD_PID" ]] && echo "slskd    → http://localhost:5030  (PID $SLSKD_PID)"
echo "Backend  → http://localhost:8000  (PID $BACKEND_PID)"
echo "Docs API → http://localhost:8000/docs"
echo "Frontend → http://localhost:3000  (PID $FRONTEND_PID)"
[[ -n "$DJORG_BACKEND_PID" ]]  && echo "DjOrganizer API → http://localhost:8010  (PID $DJORG_BACKEND_PID)"
[[ -n "$DJORG_FRONTEND_PID" ]] && echo "DjOrganizer UI  → http://localhost:3010  (PID $DJORG_FRONTEND_PID)"
echo ""
echo "Premi Ctrl+C per fermare tutto."

trap "kill $BACKEND_PID $FRONTEND_PID $SLSKD_PID $DJORG_BACKEND_PID $DJORG_FRONTEND_PID 2>/dev/null; echo '\nServizi fermati.'" INT TERM
wait
