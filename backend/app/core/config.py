import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
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
    # Libreria canonica su disco (disk-first): radice indicizzata da /api/library/index.
    # Vuoto = indicizzazione disattiva. I file qui dentro SONO la libreria posseduta.
    library_root: str = ""
    # Archivio delle scartate (PASSED di DJPlayer). Vuoto = riconoscimento disattivo.
    archive_root: str = ""

    # Integrazioni future (MVP 2+)
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    # Spotify accetta solo HTTPS o loopback 127.0.0.1 (non "localhost") come redirect
    spotify_redirect_uri: str = "http://127.0.0.1:8000/api/spotify/callback"
    # Discogs: sorgente di profondita' per Discovery (generi/stili, etichette, artisti).
    # Funziona anche senza token (rate ridotto a ~25/min); col token sale a ~60/min.
    discogs_token: str = ""
    # slskd: URL del demone Soulseek locale (es. http://localhost:5030). Vuoto = acquisizione disattiva.
    slskd_url: str = ""
    # slskd: API key del demone (se richiesta dalla sua config).
    slskd_api_key: str = ""
    # slskd: cartella dove slskd scrive i download completati (usata per collegare il file alla Track).
    slskd_download_dir: str = ""
    # slskd: percorso del suo file di config, editato dal flag "Condividi libreria"
    # (slskd non espone le share via API a runtime). Default = posizione standard.
    slskd_config_path: str = "~/.config/slskd/slskd.yml"
    # Chiave AI unica per tutta l'app (Set Agent + tag/generi di Organize).
    # ANTHROPIC_API_KEY e' il nome standard dell'SDK; AI_API_KEY resta letta
    # come fallback per gli .env scritti prima della fusione.
    ai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "AI_API_KEY"),
    )
    ai_model: str = ""
    # Modello di default: claude-opus-4-8 (vedi integrations/llm.py).
    # Effort/thinking bassi tengono bassa la latenza: con effort alto + thinking
    # esteso la generazione diventa molto lenta. Ottimale misurato su set reali
    # (su Sonnet 4.6): adaptive + effort "low" ~66s con ordinamento BPM/Camelot
    # corretto; su Opus 4.8 i tempi possono variare. "disabled" e' veloce ma
    # sbaglia durata e progressione. (override via env)
    ai_effort: str = "low"  # low | medium | high | max
    ai_thinking: str = "adaptive"  # adaptive | disabled
    ai_timeout_seconds: float = 120.0

    # --- Organize (ex Sortory) ---------------------------------------------
    # Estensioni audio riconosciute dallo scanner (minuscole, col punto).
    audio_exts: tuple[str, ...] = (".mp3", ".flac", ".wav", ".aiff", ".aif", ".m4a", ".aac")
    # Soglie Inspector / Dedup.
    low_bitrate_kbps: int = 256
    duration_min_s: float = 30.0
    duration_max_s: float = 900.0
    fuzzy_dur_tol_s: float = 2.0
    # Provider di metadati testuali e fingerprint. Chiavi opzionali: senza
    # chiave il provider è inattivo (degradazione pulita). `discogs_token` non
    # si duplica: è lo stesso account che usa il Discovery, qui sopra.
    acoustid_api_key: str = ""
    musicbrainz_user_agent: str = "Cratory-Organize/0.1 (+http://localhost)"
    # Cache thumbnail: cover proposte dai provider e cover embeddate nei file.
    # Separate di proposito — entrambe indicizzano per {file_id}.jpg e
    # condividerle confonderebbe l'artwork reale con la proposta di un provider.
    cover_cache_dir: str = "./data/cover_cache"
    thumb_cache_dir: str = "./data/thumb_cache"
    # Binari esterni scaricati dall'app (ffmpeg, fpcalc, slskd). Stessa forma
    # delle cache qui sopra: relativo a backend/, sotto data/ (gitignorato).
    # Non è una cartella "in più" rispetto a CRATORY_BIN_DIR: ne è il default,
    # e in un bundle Tauri quella env la sovrascrive puntando al bundle.
    bin_dir: str = "./data/bin"

    @field_validator("library_root", "archive_root", "slskd_download_dir",
                     "slskd_config_path")
    @classmethod
    def expand_user_paths(cls, value: str) -> str:
        """`~` va espanso: un LIBRARY_ROOT='~/Music' altrimenti non risolve e
        indicizzazione/download falliscono in silenzio. Vuoto = feature disattiva."""
        return str(Path(value).expanduser()) if value else ""

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

    @field_validator("cover_cache_dir", "thumb_cache_dir", "bin_dir")
    @classmethod
    def _cache_dir_assoluta(cls, value: str) -> str:
        """Path relativo risolto rispetto a backend/, mai alla cwd del processo:
        stesso difetto che database_url aveva prima del suo validator."""
        if not value:
            return value
        path = Path(value)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return path.resolve().as_posix()


settings = Settings()

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging() -> None:
    """Logging su console + file rotante in backend/logs/. Idempotente."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    formatter = logging.Formatter(_LOG_FORMAT)

    root = logging.getLogger()
    root.setLevel(level)
    # rimuove handler precedenti (evita duplicati col --reload di uvicorn) e li
    # chiude: altrimenti il RotatingFileHandler resta con il file aperto e il gc
    # emette ResourceWarning quando lo raccoglie. StreamHandler.close() non chiude
    # lo stream sottostante (stderr resta valido), quindi e' sicuro farlo sempre.
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

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
