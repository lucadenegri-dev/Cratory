"""Stato unificato di tutte le integrazioni esterne (per la pagina Impostazioni).

Espone, per ogni servizio API, se e' configurato (chiave presente in .env) e, dove
ha senso, se e' collegato (Spotify: login OAuth utente). Cosi' la UI mostra un
elenco completo invece dello stato dei soli alcuni servizi.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.integrations.spotify import SpotifyWebClient

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("/status")
def services_status(db: Session = Depends(get_db)):
    spotify_configured = bool(settings.spotify_client_id and settings.spotify_client_secret)
    user_connected = SpotifyWebClient(db).user_connected() if spotify_configured else False
    return {
        "services": [
            {
                "key": "spotify", "name": "Spotify", "category": "Streaming",
                "configured": spotify_configured, "connected": user_connected,
                "detail": "Import playlist, brani salvati e creazione playlist. Richiede login OAuth.",
                "env": ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"],
                "docs": "https://developer.spotify.com/dashboard",
            },
            {
                "key": "anthropic", "name": "Anthropic — AI Set Agent", "category": "AI",
                "configured": bool(settings.ai_api_key), "connected": None,
                "detail": f"Modello: {settings.ai_model or 'claude-opus-4-8'}. Narrativa, prompt, discovery.",
                "env": ["AI_API_KEY", "AI_MODEL"],
                "docs": "https://console.anthropic.com",
            },
            {
                "key": "deezer", "name": "Deezer", "category": "Feature musicali",
                # Endpoint pubblico read-only: nessuna API key, attivabile/disattivabile via env.
                "configured": settings.deezer_enabled, "connected": None,
                "detail": "BPM via ISRC (match esatto). Gratis, senza API key.",
                "env": ["DEEZER_ENABLED"],
                "docs": "https://developers.deezer.com/api/track",
            },
            {
                "key": "getsongbpm", "name": "GetSongBPM", "category": "Feature musicali",
                "configured": bool(settings.getsongbpm_api_key), "connected": None,
                "detail": "BPM, tonalita' (Camelot) e danceability (match per artista/titolo).",
                "env": ["GETSONGBPM_API_KEY"],
                "docs": "https://getsongbpm.com/api",
            },
            {
                "key": "acousticbrainz", "name": "AcousticBrainz", "category": "Feature musicali",
                # Indicizzato per MBID: utile solo se MusicBrainz e' configurato.
                "configured": settings.acousticbrainz_enabled and bool(settings.musicbrainz_user_agent),
                "connected": None,
                "detail": "Analisi audio reale (BPM, key, mood, danceability, voce) via MBID di "
                          "MusicBrainz. Gratis, senza API key. Dataset storico (no uscite recenti).",
                "env": ["ACOUSTICBRAINZ_ENABLED", "MUSICBRAINZ_USER_AGENT"],
                "docs": "https://acousticbrainz.org/data",
            },
            {
                "key": "lastfm", "name": "Last.fm", "category": "Feature musicali",
                "configured": bool(settings.lastfm_api_key), "connected": None,
                "detail": "Genere e mood dai tag; motore di similarita' del Discovery.",
                "env": ["LASTFM_API_KEY"],
                "docs": "https://www.last.fm/api",
            },
            {
                "key": "discogs", "name": "Discogs", "category": "Discovery",
                # Usabile anche senza token (rate ridotto); il token alza il rate limit.
                "configured": True,
                "connected": bool(settings.discogs_token),
                "detail": "Profondita' per il Discovery (crate digging per genere/stile ed "
                          "etichetta). Funziona senza token; DISCOGS_TOKEN alza il rate limit "
                          "e mostra le copertine dei dischi.",
                "env": ["DISCOGS_TOKEN"],
                "docs": "https://www.discogs.com/settings/developers",
            },
            {
                "key": "musicbrainz", "name": "MusicBrainz", "category": "Feature musicali",
                # Nessuna API key, ma MusicBrainz richiede uno User-Agent identificativo:
                # entra nella catena solo se MUSICBRAINZ_USER_AGENT e' valorizzato.
                "configured": bool(settings.musicbrainz_user_agent), "connected": None,
                "detail": "Label, data di uscita e genere via ISRC. Richiede un User-Agent identificativo (no API key).",
                "env": ["MUSICBRAINZ_USER_AGENT"],
                "docs": "https://musicbrainz.org/doc/MusicBrainz_API",
            },
            {
                "key": "slskd", "name": "slskd (Soulseek)", "category": "Download",
                # Configurato = URL + cartella download presenti; l'API key e' opzionale
                # (slskd puo' girare senza auth). Stessa condizione di slskd_configured().
                "configured": bool(settings.slskd_url and settings.slskd_download_dir),
                "connected": None,
                "detail": "Acquisizione file via Soulseek: scarica le tracce di una playlist e "
                          "collega il file alla libreria. SLSKD_API_KEY opzionale.",
                "env": ["SLSKD_URL", "SLSKD_API_KEY", "SLSKD_DOWNLOAD_DIR"],
                "docs": "https://github.com/slskd/slskd",
            },
        ]
    }
