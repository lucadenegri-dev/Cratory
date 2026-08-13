"""Avvio di un job in background in un thread daemon: pattern condiviso dai job
mono-utente (analisi BPM/key, import/sync streaming). Separato in una funzione
dedicata così i test possono renderlo sincrono via monkeypatch, senza toccare
`threading.Thread` direttamente."""

import threading


def spawn(fn) -> None:
    """Separato per i test (che lo rendono sincrono)."""
    threading.Thread(target=fn, daemon=True).start()
