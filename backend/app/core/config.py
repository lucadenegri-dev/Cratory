"""Configurazione applicativa (pydantic-settings). App locale mono-utente."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DJORG_", env_file=".env", extra="ignore")

    # DB SQLite locale (cartella git-ignored).
    database_url: str = "sqlite:///./data/djorganizer.db"
    # Estensioni audio riconosciute dallo Scanner (minuscole, col punto).
    audio_exts: tuple[str, ...] = (".mp3", ".flac", ".wav", ".aiff", ".aif", ".m4a", ".aac")

    # Soglie Inspector / Dedup (chunk 2)
    low_bitrate_kbps: int = 256
    duration_min_s: float = 30.0
    duration_max_s: float = 900.0
    fuzzy_dur_tol_s: float = 2.0


settings = Settings()
