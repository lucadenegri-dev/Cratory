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
                "key": "getsongbpm", "name": "GetSongBPM", "category": "Feature musicali",
                "configured": bool(settings.getsongbpm_api_key), "connected": None,
                "detail": "BPM, tonalita' (Camelot) e danceability.",
                "env": ["GETSONGBPM_API_KEY"],
                "docs": "https://getsongbpm.com/api",
            },
            {
                "key": "lastfm", "name": "Last.fm", "category": "Feature musicali",
                "configured": bool(settings.lastfm_api_key), "connected": None,
                "detail": "Genere e mood dai tag; motore di similarita' del Discovery.",
                "env": ["LASTFM_API_KEY"],
                "docs": "https://www.last.fm/api",
            },
            {
                "key": "musicbrainz", "name": "MusicBrainz", "category": "Feature musicali",
                # Funziona senza chiave: e' sempre "disponibile" (un user-agent e' consigliato).
                "configured": True, "connected": None,
                "detail": "Label, data di uscita e genere via ISRC. Nessuna chiave richiesta.",
                "env": ["MUSICBRAINZ_USER_AGENT"],
                "docs": "https://musicbrainz.org/doc/MusicBrainz_API",
            },
            {
                "key": "discogs", "name": "Discogs", "category": "Feature musicali",
                "configured": bool(settings.discogs_token), "connected": None,
                "detail": "Non ancora integrato (previsto per la Library Expansion).",
                "env": ["DISCOGS_TOKEN"],
                "docs": "https://www.discogs.com/settings/developers",
            },
        ]
    }
