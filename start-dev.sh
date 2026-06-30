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

echo ""
[[ -n "$SLSKD_PID" ]] && echo "slskd    → http://localhost:5030  (PID $SLSKD_PID)"
echo "Backend  → http://localhost:8000  (PID $BACKEND_PID)"
echo "Docs API → http://localhost:8000/docs"
echo "Frontend → http://localhost:3000  (PID $FRONTEND_PID)"
echo ""
echo "Premi Ctrl+C per fermare tutto."

trap "kill $BACKEND_PID $FRONTEND_PID $SLSKD_PID 2>/dev/null; echo '\nServizi fermati.'" INT TERM
wait
