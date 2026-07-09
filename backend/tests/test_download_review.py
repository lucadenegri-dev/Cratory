"""Revisione dei needs_review-per-durata: review detail, keep, discard."""
import math
import struct
import wave

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track


def _write_wav(path, *, secs=2, rate=22050):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(
            struct.pack("<h", int(30000 * math.sin(2 * math.pi * 440 * i / rate)))
            for i in range(int(rate * secs))
        ))


@pytest.fixture()
def client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def _needs_review_track(db, tmp_path, *, secs=2, duration=300):
    f = tmp_path / "Da Funk.wav"
    _write_wav(f, secs=secs)
    t = Track(platform="spotify", spotify_id="r1", source_type="spotify",
              title="Da Funk", artist="Daft Punk", duration_seconds=duration,
              last_download_outcome="needs_review",
              last_download_reason="durata non corrisponde (attesa 300s, file 2s)",
              last_download_path=str(f))
    db.add(t)
    db.commit()
    return t


def test_review_detail_confronta_atteso_e_scaricato(client_db, tmp_path):
    client, db = client_db
    t = _needs_review_track(db, tmp_path)
    r = client.get(f"/api/downloads/review/{t.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["expected"]["duration_seconds"] == 300
    assert body["downloaded"]["name"] == "Da Funk.wav"
    assert body["downloaded"]["duration_seconds"] == 2


def test_review_detail_senza_file(client_db, tmp_path):
    # needs_review-per-confidenza: nessun file da rivedere.
    client, db = client_db
    t = Track(platform="spotify", spotify_id="r2", source_type="spotify",
              title="X", artist="Y", last_download_outcome="needs_review",
              last_download_reason="confidenza sotto soglia per l'auto-pick")
    db.add(t)
    db.commit()
    r = client.get(f"/api/downloads/review/{t.id}")
    assert r.status_code == 200
    assert r.json()["downloaded"] is None


def test_keep_aggancia_il_file_e_svuota_l_archivio(client_db, tmp_path):
    client, db = client_db
    t = _needs_review_track(db, tmp_path)
    r = client.post("/api/downloads/keep-review", json={"track_id": t.id})
    assert r.status_code == 200
    db.expire_all()
    t2 = db.get(Track, t.id)
    assert t2.has_local_file is True
    assert t2.last_download_outcome is None
    assert t2.last_download_path is None


def test_discard_elimina_il_file_e_sgancia(client_db, tmp_path):
    import os
    client, db = client_db
    t = _needs_review_track(db, tmp_path)
    path = t.last_download_path
    r = client.post("/api/downloads/discard-review", json={"track_id": t.id})
    assert r.status_code == 200
    assert not os.path.exists(path)  # file rimosso dall'inbox
    db.expire_all()
    t2 = db.get(Track, t.id)
    assert t2.has_local_file is not True
    assert t2.last_download_outcome is None


def test_keep_404_su_traccia_inesistente(client_db):
    client, _ = client_db
    assert client.post("/api/downloads/keep-review", json={"track_id": 9999}).status_code == 404


def test_keep_409_se_nessun_file_dubbio(client_db):
    client, db = client_db
    t = Track(platform="spotify", spotify_id="r3", source_type="spotify",
              title="X", artist="Y", last_download_outcome="needs_review")
    db.add(t)
    db.commit()
    assert client.post("/api/downloads/keep-review", json={"track_id": t.id}).status_code == 409
