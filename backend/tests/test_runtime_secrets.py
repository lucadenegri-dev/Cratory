"""Le chiavi API devono essere scrivibili a runtime con la stessa semantica dei
path: override DB sopra il default .env, vuoto = torna al default."""
import pytest

from app.core import runtime_settings as rs
from app.core.config import settings


def test_ogni_chiave_segreta_ha_un_accessor():
    """SECRET_KEYS non deve diventare una costante decorativa come
    ENV_BACKED_KEYS: ogni chiave dichiarata deve avere la sua funzione."""
    for key in rs.SECRET_KEYS:
        assert callable(getattr(rs, key)), f"manca l'accessor per {key}"


def test_gruppi_disgiunti():
    assert not set(rs.SECRET_KEYS) & set(rs.ENV_BACKED_KEYS)


def test_override_vince_sul_default_env(db, monkeypatch):
    monkeypatch.setattr(settings, "ai_api_key", "chiave-env")
    assert rs.ai_api_key() == "chiave-env"
    rs.apply(db, "ai_api_key", "chiave-db")
    assert rs.ai_api_key() == "chiave-db"
    assert rs.source("ai_api_key") == "db"


def test_override_vuoto_torna_al_default(db, monkeypatch):
    monkeypatch.setattr(settings, "discogs_token", "token-env")
    rs.apply(db, "discogs_token", "token-db")
    rs.apply(db, "discogs_token", "")
    assert rs.discogs_token() == "token-env"
    assert rs.source("discogs_token") == "env"


def test_secret_rifiuta_chiavi_fuori_gruppo():
    with pytest.raises(KeyError):
        rs.secret("database_url")


def test_i_segreti_non_vengono_espansi_come_path(db):
    """Una chiave che comincia per '~' non deve diventare un path della home."""
    rs.apply(db, "acoustid_api_key", "~strana~chiave")
    assert rs.acoustid_api_key() == "~strana~chiave"
