"""Le credenziali si configurano via HTTP ma non tornano mai in chiaro."""
import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import runtime_settings as rs
from app.core.config import settings
from app.db import Base, get_db, ensure_schema
from app.main import app as fastapi_app
import app.models  # noqa: F401
import app.organize.models  # noqa: F401


def _override_db():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    ensure_schema(e)
    factory = sessionmaker(bind=e, expire_on_commit=False)

    def _db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = _db


def _client():
    return TestClient(fastapi_app)


def teardown_function():
    fastapi_app.dependency_overrides.clear()
    rs._overrides = {}


def test_il_valore_in_chiaro_non_compare_mai_nella_risposta(monkeypatch):
    """Asserzione sul JSON serializzato, non sul singolo campo: se un giorno
    qualcuno aggiunge la chiave in un altro punto della risposta, questo test
    la becca lo stesso."""
    _override_db()
    monkeypatch.setattr(settings, "ai_api_key", "sk-super-segreta-12345")
    body = _client().get("/api/settings/config").json()
    assert "sk-super-segreta-12345" not in json.dumps(body)


def test_hint_mostra_le_ultime_quattro(monkeypatch):
    _override_db()
    monkeypatch.setattr(settings, "ai_api_key", "sk-super-segreta-a3f9")
    body = _client().get("/api/settings/config").json()
    assert body["secrets"]["ai_api_key"] == {
        "configured": True, "source": "env", "hint": "••••a3f9",
    }


def test_chiave_assente(monkeypatch):
    _override_db()
    monkeypatch.setattr(settings, "discogs_token", "")
    body = _client().get("/api/settings/config").json()
    assert body["secrets"]["discogs_token"] == {
        "configured": False, "source": "env", "hint": None,
    }


def test_patch_salva_e_azzera(monkeypatch):
    _override_db()
    monkeypatch.setattr(settings, "discogs_token", "token-env")
    client = _client()

    body = client.patch("/api/settings/config", json={"discogs_token": "token-db"}).json()
    assert body["secrets"]["discogs_token"]["source"] == "db"
    assert rs.discogs_token() == "token-db"

    body = client.patch("/api/settings/config", json={"discogs_token": ""}).json()
    assert body["secrets"]["discogs_token"]["source"] == "env"
    assert rs.discogs_token() == "token-env"


def test_gli_spazi_intorno_alla_chiave_vengono_tolti():
    """Una chiave incollata porta spesso uno \\n finale: se lo si salva,
    l'header HTTP verso il provider diventa invalido e l'errore è incomprensibile."""
    _override_db()
    _client().patch("/api/settings/config", json={"ai_api_key": "  sk-abcd\n"})
    assert rs.ai_api_key() == "sk-abcd"


def test_ogni_campo_env_backed_e_esposto():
    """ENV_BACKED_KEYS deve essere la sorgente vera dei campi esposti, non una
    costante decorativa: aggiungerci una chiave deve comparire nella risposta
    senza toccare il router."""
    _override_db()
    body = _client().get("/api/settings/config").json()
    for key in rs.ENV_BACKED_KEYS:
        assert key in body, f"{key} non esposto"


def test_redirect_uri_e_esposto_in_sola_lettura():
    _override_db()
    body = _client().get("/api/settings/config").json()
    assert body["spotify_redirect_uri"] == settings.spotify_redirect_uri
