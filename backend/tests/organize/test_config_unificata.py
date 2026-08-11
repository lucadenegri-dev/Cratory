"""F2: una sola classe Settings, senza prefisso DJORG_."""

import pytest


def test_modulo_config_organize_non_esiste_piu():
    with pytest.raises(ModuleNotFoundError):
        import app.organize.core.config  # noqa: F401


def test_campi_organize_su_settings_unica():
    from app.core.config import settings

    assert settings.audio_exts
    assert ".flac" in settings.audio_exts
    assert settings.low_bitrate_kbps > 0
    assert settings.duration_min_s > 0
    assert isinstance(settings.musicbrainz_user_agent, str)
    assert hasattr(settings, "acoustid_api_key")


def test_discogs_token_unico():
    from app.core.config import settings

    assert isinstance(settings.discogs_token, str)


def test_cache_dir_normalizzate_ad_assoluto(monkeypatch):
    """Un path relativo nel .env non deve dipendere dalla cwd del processo:
    stesso difetto che DJORG_DATABASE_URL aveva prima del validator."""
    from app.core.config import Settings

    s = Settings(cover_cache_dir="./data/cover_cache", thumb_cache_dir="./data/thumb_cache")
    assert s.cover_cache_dir.startswith("/")
    assert s.thumb_cache_dir.startswith("/")
