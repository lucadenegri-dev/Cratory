"""Stato unificato di TUTTE le integrazioni esterne (per la pagina Impostazioni).

Un solo elenco per l'intera app (fusione F1-F6): comprende anche i provider di
metadati della sezione Organize (MusicBrainz, AcoustID), che prima vivevano nel
duplicato /api/organize/providers. Semantica dei campi, uguale per ogni voce:

- configured: la configurazione NECESSARIA e' presente (True di suo per i
  servizi senza chiave obbligatoria, es. Discogs e MusicBrainz);
- connected: stato vivo di sessione dove esiste (OAuth Spotify), None dove il
  concetto non si applica. Per slskd lo stato vivo lo da' /api/slskd/status,
  interrogato dalla riga della UI: qui niente chiamate HTTP al demone;
- env: variabili necessarie; optional_env: variabili facoltative;
- optional_ok: True/False = facoltative presenti/assenti, None = nessuna.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import runtime_settings
from app.core.config import settings
from app.db import get_db
from app.integrations.soundcloud import soundcloud_available
from app.integrations.spotify import SpotifyWebClient
from app.organize.integrations import acoustid

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("/status")
def services_status(db: Session = Depends(get_db)):
    spotify_configured = bool(settings.spotify_client_id and settings.spotify_client_secret)
    user_connected = False
    if spotify_configured:
        client = SpotifyWebClient(db)
        try:
            user_connected = client.user_connected()
        finally:
            client.close()
    return {
        "services": [
            {
                "key": "spotify", "name": "Spotify", "category": "Streaming",
                "configured": spotify_configured, "connected": user_connected,
                "detail": "Import playlist, brani salvati e creazione playlist. Richiede login OAuth.",
                "env": ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"],
                "optional_env": [], "optional_ok": None,
                "docs": "https://developer.spotify.com/dashboard",
            },
            {
                "key": "anthropic", "name": "Anthropic — AI", "category": "AI",
                "configured": bool(settings.ai_api_key), "connected": None,
                "detail": "Una chiave sola per tutta l'AI: Set Agent (modello: "
                          f"{settings.ai_model or 'claude-opus-4-8'}), suggerimenti "
                          "artista/titolo e revisione generi in Organize.",
                "env": ["ANTHROPIC_API_KEY"],
                "optional_env": ["AI_MODEL"], "optional_ok": True,
                "docs": "https://console.anthropic.com",
            },
            {
                "key": "discogs", "name": "Discogs", "category": "Discovery · Metadati",
                # Usabile anche senza token (rate ridotto); il token alza il rate
                # limit e mostra le copertine.
                "configured": True, "connected": None,
                "detail": "Crate digging per il Discovery (genere/stile, etichetta) e "
                          "label/genere/anno per i tag di Organize. Funziona senza "
                          "token; DISCOGS_TOKEN alza il rate limit e mostra le copertine.",
                "env": [], "optional_env": ["DISCOGS_TOKEN"],
                "optional_ok": bool(settings.discogs_token),
                "docs": "https://www.discogs.com/settings/developers",
            },
            {
                "key": "musicbrainz", "name": "MusicBrainz", "category": "Metadati",
                "configured": True, "connected": None,
                "detail": "Identita' del brano + label, genere (via tag) e anno per i "
                          "tag di Organize. Nessuna chiave richiesta (~1 richiesta/secondo).",
                "env": [], "optional_env": ["MUSICBRAINZ_USER_AGENT"], "optional_ok": True,
                "docs": "https://musicbrainz.org/doc/MusicBrainz_API",
            },
            {
                "key": "acoustid", "name": "AcoustID / Chromaprint", "category": "Fingerprint",
                "configured": acoustid.acoustid_configured() and acoustid.fpcalc_available(),
                "connected": None,
                "detail": "Identita' acustica del file → MBID (match MusicBrainz esatto, "
                          "alta confidenza). Richiede la chiave AcoustID e il binario fpcalc.",
                "env": ["ACOUSTID_API_KEY", "FPCALC"],
                "optional_env": [], "optional_ok": None,
                "docs": "https://acoustid.org/",
            },
            {
                "key": "slskd", "name": "slskd (Soulseek)", "category": "Download",
                # Configurato = URL + cartella download presenti; l'API key e' opzionale
                # (slskd puo' girare senza auth). Stessa condizione di slskd_configured().
                "configured": bool(runtime_settings.slskd_url() and runtime_settings.slskd_download_dir()),
                "connected": None,
                "detail": "Acquisizione file via Soulseek: scarica le tracce di una playlist e "
                          "collega il file alla libreria. SLSKD_API_KEY opzionale.",
                "env": ["SLSKD_URL", "SLSKD_API_KEY", "SLSKD_DOWNLOAD_DIR"],
                "optional_env": [], "optional_ok": None,
                "docs": "https://github.com/slskd/slskd",
            },
            {
                "key": "soundcloud", "name": "SoundCloud", "category": "Download",
                "configured": soundcloud_available(), "connected": None,
                "detail": "Import dei like e download per-traccia via yt-dlp. "
                          "L'username si imposta qui nella riga.",
                "env": [], "optional_env": [], "optional_ok": None,
                "docs": "https://github.com/yt-dlp/yt-dlp",
            },
        ]
    }
