import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DIR = BACKEND_DIR / "logs"
LOG_FILE = LOG_DIR / "djassistant.log"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'djassistant.db'}"
    frontend_origin: str = "http://localhost:3000"
    log_level: str = "INFO"

    # Integrazioni future (MVP 2+)
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    # Spotify accetta solo HTTPS o loopback 127.0.0.1 (non "localhost") come redirect
    spotify_redirect_uri: str = "http://127.0.0.1:8000/api/spotify/callback"
    discogs_token: str = ""
    musicbrainz_user_agent: str = ""
    # Enrichment musicale esterno (BPM/key/mood/energia). Vuoti = provider disattivo.
    getsongbpm_api_key: str = ""
    lastfm_api_key: str = ""
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
    logging.getLogger("app").info("Logging inizializzato (livello %s, file %s)",
                                  settings.log_level.upper(), LOG_FILE)
