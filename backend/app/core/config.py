"""Configurazione applicativa (pydantic-settings). App locale mono-utente."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DJORG_", env_file=".env", extra="ignore")

    # DB SQLite locale (cartella git-ignored).
    database_url: str = "sqlite:///./data/djorganizer.db"
    # Estensioni audio riconosciute dallo Scanner (minuscole, col punto).
    audio_exts: tuple[str, ...] = (".mp3", ".flac", ".wav", ".aiff", ".aif", ".m4a", ".aac")


settings = Settings()
