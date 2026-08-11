"""Configurazione applicativa (pydantic-settings). App locale mono-utente."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DJORG_",
        env_file=BACKEND_DIR / ".env",
        extra="ignore",
    )

    # DB SQLite locale (cartella git-ignored).
    # Path assoluto: il default relativo dipendeva dal cwd (Sortory si lanciava
    # da backend/). Nel processo unico il cwd non è garantito. F2 unificherà
    # questo DB con quello di Cratory.
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'djorganizer.db').as_posix()}"
    # Estensioni audio riconosciute dallo Scanner (minuscole, col punto).
    audio_exts: tuple[str, ...] = (".mp3", ".flac", ".wav", ".aiff", ".aif", ".m4a", ".aac")

    # Soglie Inspector / Dedup (chunk 2)
    low_bitrate_kbps: int = 256
    duration_min_s: float = 30.0
    duration_max_s: float = 900.0
    fuzzy_dur_tol_s: float = 2.0

    # Provider testuali (enrichment) e fingerprint. Chiavi opzionali: senza
    # chiave il provider è semplicemente inattivo (degradazione pulita).
    discogs_token: str | None = None
    acoustid_api_key: str | None = None
    musicbrainz_user_agent: str = "Sortory/0.1 (+http://localhost)"

    # Cache thumbnail delle cover proposte (git-ignored, come ./data).
    cover_cache_dir: str = "./data/cover_cache"

    # Cache thumbnail delle cover **embeddate** nei file, generate on-demand.
    # Separata da cover_cache_dir: entrambe indicizzano per {file_id}.jpg e
    # condividerle confonderebbe l'artwork reale con la proposta di un provider.
    thumb_cache_dir: str = "./data/thumb_cache"

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """SQLite locale sempre relativo a backend/, mai alla cwd del processo.
        Stesso pattern di app/core/config.py: qui serve perché
        DJORG_DATABASE_URL nel .env vince sul default già assoluto sopra."""
        if not value.startswith("sqlite:///") or value == "sqlite:///:memory:":
            return value
        raw_path = value.removeprefix("sqlite:///")
        db_path = Path(raw_path)
        if not db_path.is_absolute():
            db_path = BACKEND_DIR / db_path
        return f"sqlite:///{db_path.resolve().as_posix()}"

    @field_validator("cover_cache_dir", "thumb_cache_dir")
    @classmethod
    def normalize_cache_dir(cls, value: str) -> str:
        """Stesso difetto di database_url, impatto minore: un path relativo qui
        dipende dal cwd del processo invece che essere ancorato a backend/."""
        if not value:
            return value
        path = Path(value)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return path.resolve().as_posix()


settings = Settings()
