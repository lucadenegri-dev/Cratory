"""Etichetta leggibile "Artista — Titolo" per una traccia, con fallback quando
artista/titolo mancano. Condivisa tra i servizi che la mostrano all'utente
(proposta di auto-link, job di download slskd)."""

from __future__ import annotations


def track_label(track) -> str:
    artist = (track.artist or "").strip() or "Artista sconosciuto"
    title = (track.title or "").strip() or "Senza titolo"
    return f"{artist} — {title}"
