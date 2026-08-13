"""Formattazione condivisa tra gli export testuali di set (`routers/sets.py`) e
playlist (`routers/playlists.py`)."""

from __future__ import annotations

from app.models import Track


def render_m3u8(tracks: list[Track], total: int) -> str:
    """M3U8 Rekordbox: punta ai file locali in libreria.

    `tracks` e' gia' filtrata dal chiamante (solo tracce con `local_path`);
    `total` e' il conteggio originale (prima del filtro), usato per il commento
    sul numero di tracce escluse perche' senza file su disco.
    """
    skipped = total - len(tracks)
    m3u = ["#EXTM3U"]
    if skipped:
        m3u.append(f"# {skipped} tracce senza file locale non incluse")
    for t in tracks:
        secs = int(t.duration_seconds) if t.duration_seconds else -1
        m3u.append(f"#EXTINF:{secs},{t.artist or '?'} — {t.title or t.spotify_id or '?'}")
        m3u.append(t.local_path)
    return "\n".join(m3u)


def fmt_duration(seconds: int | None) -> str:
    if not seconds:
        return "—"
    return f"{seconds // 60}:{seconds % 60:02d}"
