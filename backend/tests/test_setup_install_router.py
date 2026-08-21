"""Gli endpoint di installazione ora guidano il download dei binari."""
import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.services import binary_installer as bi


@pytest.fixture(autouse=True)
def _pulisci():
    bi.reset()
    yield
    bi.reset()


def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_chiave_sconosciuta(db):
    assert _client(db).post("/api/setup/install/rm-rf").status_code == 400
    app.dependency_overrides.clear()


def test_piattaforma_senza_build(db, monkeypatch):
    monkeypatch.setattr(bi.binary_manifest, "platform_tag", lambda: "darwin-arm64")
    monkeypatch.setattr(bi, "spawn", lambda fn: fn())
    res = _client(db).post("/api/setup/install/ffmpeg")
    assert res.status_code == 202
    assert bi.status()["status"] == "error"
    app.dependency_overrides.clear()


def test_stato_esposto(db):
    body = _client(db).get("/api/setup/install/status").json()
    assert body["status"] == "idle"
    app.dependency_overrides.clear()
