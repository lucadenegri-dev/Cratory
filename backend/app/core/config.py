import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DIR = BACKEND_DIR / "logs"
LOG_FILE = LOG_DIR / "djassistant.log"
DEFAULT_DATABASE_PATH = BACKEND_DIR / "data" / "djassistant.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = DEFAULT_DATABASE_URL
    # Origini CORS ammesse (lista separata da virgola). 3000 = dev normale, 3001 = preview.
    frontend_origin: str = "http://localhost:3000,http://localhost:3001"
    log_level: str = "INFO"
    # Import da cartella locale: radice consentita per il file-browser (vuoto = home utente).
    local_import_root: str = ""
    # Libreria canonica su disco (disk-first): radice indicizzata da /api/library/index.
    # Vuoto = indicizzazione disattiva. I file qui dentro SONO la libreria posseduta.
    library_root: str = ""
    # URL del frontend DjOrganizer per il link "Apri DjOrganizer" in dashboard (opzionale).
    organizer_url: str = ""

    # Integrazioni future (MVP 2+)
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    # Spotify accetta solo HTTPS o loopback 127.0.0.1 (non "localhost") come redirect
    spotify_redirect_uri: str = "http://127.0.0.1:8000/api/spotify/callback"
    musicbrainz_user_agent: str = ""
    # Enrichment musicale esterno (BPM/key/mood/energia). Vuoti = provider disattivo.
    getsongbpm_api_key: str = ""
    lastfm_api_key: str = ""
    # Discogs: sorgente di profondita' per Discovery (generi/stili, etichette, artisti).
    # Funziona anche senza token (rate ridotto a ~25/min); col token sale a ~60/min.
    discogs_token: str = ""
    # slskd: URL del demone Soulseek locale (es. http://localhost:5030). Vuoto = acquisizione disattiva.
    slskd_url: str = ""
    # slskd: API key del demone (se richiesta dalla sua config).
    slskd_api_key: str = ""
    # slskd: cartella dove slskd scrive i download completati (usata per collegare il file alla Track).
    slskd_download_dir: str = ""
    # Deezer: BPM via ISRC, gratis e SENZA API key (endpoint pubblico). Attivo di default
    # perche' a costo zero e copre il BPM con l'identita' piu' affidabile (ISRC).
    deezer_enabled: bool = True
    # AcousticBrainz: analisi audio reale (BPM/key/mood/danceability/voce) via MBID, gratis e
    # senza API key. Indicizzato per MBID: entra in catena solo se MusicBrainz e' configurato.
    acousticbrainz_enabled: bool = True
    ai_api_key: str = ""
    ai_model: str = ""
    # Modello per la modalità "creative" del Set Builder (vuoto = stesso di ai_model).
    # Permette: ai_model economico (technical) + un modello più capace solo in creative.
    ai_model_creative: str = ""
    # Modello di default: claude-opus-4-8 (vedi integrations/llm.py).
    # Effort/thinking bassi tengono bassa la latenza: con effort alto + thinking
    # esteso la generazione diventa molto lenta. Ottimale misurato su set reali
    # (su Sonnet 4.6): adaptive + effort "low" ~66s con ordinamento BPM/Camelot
    # corretto; su Opus 4.8 i tempi possono variare. "disabled" e' veloce ma
    # sbaglia durata e progressione. (override via env)
    ai_effort: str = "low"  # low | medium | high | max
    ai_thinking: str = "adaptive"  # adaptive | disabled
    ai_timeout_seconds: float = 120.0

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """SQLite locale sempre relativo a backend/, mai alla cwd del processo."""
        if not value.startswith("sqlite:///") or value == "sqlite:///:memory:":
            return value
        raw_path = value.removeprefix("sqlite:///")
        db_path = Path(raw_path)
        if not db_path.is_absolute():
            db_path = BACKEND_DIR / db_path
        return f"sqlite:///{db_path.resolve().as_posix()}"


settings = Settings()

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging() -> None:
    """Logging su console + file rotante in backend/logs/. Idempotente."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    formatter = logging.Formatter(_LOG_FORMAT)

    root = logging.getLogger()
    root.setLevel(level)
    # rimuove handler precedenti (evita duplicati col --reload di uvicorn)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # gli access log di uvicorn passano dal nostro middleware: riduciamo il rumore
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # httpx a INFO stampa URL complete, incluse query string con API key dei provider.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("app").info("Logging inizializzato (livello %s, file %s)",
                                  settings.log_level.upper(), LOG_FILE)
