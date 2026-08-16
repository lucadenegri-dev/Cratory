import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track
from app.routers import download_queue as router_mod

client = TestClient(app)


@pytest.fixture
def factory(monkeypatch):
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    f = sessionmaker(bind=e, expire_on_commit=False)

    def _db():
        db = f()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    monkeypatch.setattr(router_mod, "fill", lambda: None)   # niente thread nei test
    yield f
    app.dependency_overrides.clear()


def _tracks(factory, n):
    db = factory()
    ids = []
    for i in range(n):
        t = Track(source_type="manual", artist=f"A{i}", title=f"T{i}")
        db.add(t)
        db.commit()
        ids.append(t.id)
    db.close()
    return ids


def test_post_accoda_un_lotto_e_riporta_i_saltati(factory):
    ids = _tracks(factory, 3)
    r = client.post("/api/downloads/queue", json={"track_ids": ids})
    assert r.status_code == 200
    assert r.json() == {"enqueued": 3, "skipped": 0}
    r2 = client.post("/api/downloads/queue", json={"track_ids": ids})
    assert r2.json() == {"enqueued": 0, "skipped": 3}


def test_post_con_candidato_accetta_una_sola_traccia(factory):
    ids = _tracks(factory, 2)
    cand = {"username": "u", "filename": "X.flac", "size": 1,
            "bitrate": None, "length": 294}
    r = client.post("/api/downloads/queue",
                    json={"track_ids": ids, "candidate": cand})
    assert r.status_code == 422
    r2 = client.post("/api/downloads/queue",
                     json={"track_ids": ids[:1], "candidate": cand})
    assert r2.status_code == 200
    got = client.get("/api/downloads/queue").json()["items"][0]
    assert got["kind"] == "soulseek_chosen"


def test_get_espone_slot_attivi_ed_etichetta(factory):
    ids = _tracks(factory, 1)
    client.post("/api/downloads/queue", json={"track_ids": ids})
    body = client.get("/api/downloads/queue").json()
    assert body["slots"] >= 1
    assert body["active"] == 0
    assert body["items"][0]["label"] == "A0 — T0"
    assert body["items"][0]["state"] == "queued"


def test_delete_annulla_un_item(factory):
    ids = _tracks(factory, 1)
    client.post("/api/downloads/queue", json={"track_ids": ids})
    item_id = client.get("/api/downloads/queue").json()["items"][0]["id"]
    assert client.delete(f"/api/downloads/queue/{item_id}").status_code == 200
    assert client.get("/api/downloads/queue").json()["items"][0]["state"] == "cancelled"
    # un item gia' concluso non si annulla due volte
    assert client.delete(f"/api/downloads/queue/{item_id}").status_code == 409


def test_top_porta_in_testa(factory):
    ids = _tracks(factory, 3)
    client.post("/api/downloads/queue", json={"track_ids": ids})
    items = client.get("/api/downloads/queue").json()["items"]
    ultimo = items[-1]["id"]
    assert client.post(f"/api/downloads/queue/{ultimo}/top").status_code == 200
    assert client.get("/api/downloads/queue").json()["items"][0]["id"] == ultimo


def test_cancel_queued_e_clear_done(factory):
    ids = _tracks(factory, 2)
    client.post("/api/downloads/queue", json={"track_ids": ids})
    assert client.post("/api/downloads/queue/cancel-queued").json() == {"cancelled": 2}
    assert client.delete("/api/downloads/queue/done").json() == {"removed": 0}


def test_404_su_item_inesistente(factory):
    assert client.delete("/api/downloads/queue/999").status_code == 404
    assert client.post("/api/downloads/queue/999/top").status_code == 404
