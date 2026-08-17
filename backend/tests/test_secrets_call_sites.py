"""Ogni integrazione deve leggere la credenziale da runtime_settings (override
DB), non da settings: è la proprietà che rende utile il wizard, perché salvare
una chiave ha effetto senza riavviare il backend."""
from app.core import runtime_settings as rs
from app.core.config import settings


def test_spotify_usa_override(db, monkeypatch):
    from app.integrations import spotify
    monkeypatch.setattr(settings, "spotify_client_id", "")
    monkeypatch.setattr(settings, "spotify_client_secret", "")
    rs.apply(db, "spotify_client_id", "id-db")
    rs.apply(db, "spotify_client_secret", "secret-db")
    assert spotify._require_credentials() == ("id-db", "secret-db")


def test_llm_configured_usa_override(db, monkeypatch):
    from app.integrations import llm
    monkeypatch.setattr(settings, "ai_api_key", "")
    assert llm.llm_configured() is False
    rs.apply(db, "ai_api_key", "sk-db")
    assert llm.llm_configured() is True


def test_ai_tags_configured_usa_override(db, monkeypatch):
    from app.organize.services import ai_tags
    monkeypatch.setattr(settings, "ai_api_key", "")
    assert ai_tags.is_configured() is False
    rs.apply(db, "ai_api_key", "sk-db")
    assert ai_tags.is_configured() is True


def test_discogs_client_prende_il_token_override(db, monkeypatch):
    from app.integrations.discogs import DiscogsClient
    monkeypatch.setattr(settings, "discogs_token", "")
    rs.apply(db, "discogs_token", "tok-db")
    client = DiscogsClient()
    try:
        assert client.token == "tok-db"
    finally:
        client.close()


def test_discogs_meta_prende_il_token_override(db, monkeypatch):
    from app.organize.integrations.discogs_meta import DiscogsMetaClient
    monkeypatch.setattr(settings, "discogs_token", "")
    rs.apply(db, "discogs_token", "tok-db")
    assert DiscogsMetaClient().token == "tok-db"


def test_acoustid_configured_usa_override(db, monkeypatch):
    from app.organize.integrations import acoustid
    monkeypatch.setattr(settings, "acoustid_api_key", "")
    assert acoustid.acoustid_configured() is False
    rs.apply(db, "acoustid_api_key", "aid-db")
    assert acoustid.acoustid_configured() is True


def test_slskd_client_prende_la_api_key_override(db, monkeypatch):
    from app.integrations.slskd import SlskdClient
    monkeypatch.setattr(settings, "slskd_api_key", "")
    rs.apply(db, "slskd_api_key", "key-db")
    client = SlskdClient(url="http://localhost:5030")
    try:
        assert client.api_key == "key-db"
    finally:
        client.close()
