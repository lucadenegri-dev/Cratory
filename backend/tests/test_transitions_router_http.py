"""Copertura HTTP (TestClient) del router /api/transitions: after/{id}, before/{id},
score. Prima di questo file la logica era testata solo a livello di funzione
(test_transitions_single_compute.py chiama transitions._score_out direttamente):
qui si verifica lo shape JSON e i 404, come test_analysis_router.py."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track


@pytest.fixture()
def client():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    S = sessionmaker(bind=e, expire_on_commit=False)

    def _get_db():
        db = S()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app), S
    app.dependency_overrides.clear()


def _seed(S):
    with S() as s:
        s.add(Track(id=1, source_type="spotify", bpm=128.0, camelot_key="8A",
                    duration_seconds=300, artist="A", title="Anchor"))
        s.add(Track(id=2, source_type="spotify", bpm=129.0, camelot_key="9A",
                    duration_seconds=300, artist="B", title="Compatible"))
        s.add(Track(id=3, source_type="spotify", bpm=150.0, camelot_key="3B",
                    duration_seconds=300, artist="C", title="Risky"))
        # nessun bpm: esclusa da all_playable_tracks, non deve apparire nei candidati
        s.add(Track(id=4, source_type="spotify", bpm=None, artist="D", title="NoBpm"))
        s.commit()


def test_after_200_shape(client):
    c, S = client
    _seed(S)
    r = c.get("/api/transitions/after/1")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 2  # tutte le tracce con bpm tranne l'ancora stessa
    ids = {row["track"]["id"] for row in body}
    assert ids == {2, 3}
    row = body[0]
    assert "score" in row and "classification" in row["score"]
    assert 0 <= row["score"]["score"] <= 100


def test_after_404_track_non_esistente(client):
    c, S = client
    _seed(S)
    r = c.get("/api/transitions/after/999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "track_not_found"


def test_before_200_shape(client):
    c, S = client
    _seed(S)
    r = c.get("/api/transitions/before/1")
    assert r.status_code == 200
    ids = {row["track"]["id"] for row in r.json()}
    assert ids == {2, 3}


def test_before_404_track_non_esistente(client):
    c, S = client
    _seed(S)
    r = c.get("/api/transitions/before/999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "track_not_found"


def test_after_limit_param(client):
    c, S = client
    _seed(S)
    r = c.get("/api/transitions/after/1", params={"limit": 1})
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_after_lens_filtra_per_classificazione(client):
    c, S = client
    _seed(S)
    # senza lens: entrambe le candidate
    all_rows = c.get("/api/transitions/after/1").json()
    classes = {row["score"]["classification"] for row in all_rows}
    # con un lens valido preso da uno dei risultati, il set filtrato e' un sottoinsieme
    lens = next(iter(classes))
    filtered = c.get("/api/transitions/after/1", params={"lens": lens}).json()
    assert filtered  # almeno una riga (il lens scelto viene da un risultato reale)
    assert all(row["score"]["classification"] == lens for row in filtered)


def test_after_lens_sconosciuto_ignorato(client):
    """Un lens fuori dall'insieme valido (_LENSES) viene ignorato, non genera 422:
    il router lo scarta silenziosamente (`lens if lens in _LENSES else None`)."""
    c, S = client
    _seed(S)
    r = c.get("/api/transitions/after/1", params={"lens": "not_a_real_lens"})
    assert r.status_code == 200
    assert len(r.json()) == 2  # nessun filtro applicato


# I test di POST /score sono stati rimossi con l'endpoint (2026-07-12):
# documentato ma mai chiamato da UI o script, il ranking copre il caso d'uso.
