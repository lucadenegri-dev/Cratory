"""GET /api/playlists/{playlist_id}/gaps sul filo HTTP.

I test unitari coprono `analyze_gaps` (il servizio); qui si copre la route e la
forma della response, che nessun altro test attraversa via HTTP. Il file nasce
come guardia dell'ordine delle route quando esisteva anche /library/gaps: quella
e' stata rimossa, ma la copertura dell'endpoint superstite viveva solo qui.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Playlist, Track
from app.repositories import add_track_to_playlist


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: s
    try:
        yield s
    finally:
        app.dependency_overrides.pop(get_db, None)
        s.close()


@pytest.fixture()
def client(session):
    return TestClient(app)


def _playlist_con_tracce(db, n=6):
    """Playlist volutamente monotona: stesso genere, BPM vicini, energia piatta —
    cosi' l'analisi ha qualcosa da segnalare e `gaps` non e' vuota per caso."""
    pl = Playlist(platform="manual", name="P", kind="manual")
    db.add(pl); db.flush()
    for i in range(n):
        t = Track(source_type="local_files", title=f"T{i}", artist="A",
                  bpm=124.0, camelot_key="8A", genre="techno", energy=50)
        db.add(t); db.flush()
        add_track_to_playlist(db, t, pl)
    db.commit()
    return pl


def test_gaps_di_una_playlist(client, session):
    pl = _playlist_con_tracce(session)
    r = client.get(f"/api/playlists/{pl.id}/gaps")
    assert r.status_code == 200
    body = r.json()
    assert body["track_count"] == 6
    assert len(body["gaps"]) > 0
    for g in body["gaps"]:
        assert g["gap_type"] and g["severity"]


def test_la_response_non_espone_piu_scope(client, session):
    """`scope` distingueva playlist da libreria: rimossa la seconda, il campo e'
    sparito dallo schema. Qui si verifica che non torni indietro di soppiatto."""
    pl = _playlist_con_tracce(session)
    body = client.get(f"/api/playlists/{pl.id}/gaps").json()
    assert "scope" not in body


def test_playlist_inesistente_404(client, session):
    r = client.get("/api/playlists/9999/gaps")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "playlist_not_found"


def test_playlist_vuota_nessun_gap(client, session):
    pl = Playlist(platform="manual", name="vuota", kind="manual")
    session.add(pl); session.commit()
    body = client.get(f"/api/playlists/{pl.id}/gaps").json()
    assert body["track_count"] == 0
    assert body["gaps"] == []
