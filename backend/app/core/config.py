import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'djassistant.db'}"
    frontend_origin: str = "http://localhost:3000"

    # Integrazioni future (MVP 2+)
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = ""
    discogs_token: str = ""
    musicbrainz_user_agent: str = ""
    ai_api_key: str = ""
    ai_model: str = ""


settings = Settings()


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
