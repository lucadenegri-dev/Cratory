"""PATCH /api/playlists/{id}: rename con lock del nome sul sync."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Playlist
from app.services.playlist_import import import_playlist


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


def test_rename_cambia_nome_e_locka(client_db):
    client, db = client_db
    pl = Playlist(platform="spotify", platform_playlist_id="sp1", name="Vecchio", kind="playlist")
    db.add(pl); db.commit()
    r = client.patch(f"/api/playlists/{pl.id}", json={"name": "  Nuovo  "})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Nuovo"
    assert body["name_locked"] is True


def test_rename_nome_vuoto_422(client_db):
    client, db = client_db
    pl = Playlist(platform="manual", name="P", kind="manual")
    db.add(pl); db.commit()
    assert client.patch(f"/api/playlists/{pl.id}", json={"name": "   "}).status_code == 422


def test_rename_playlist_inesistente_404(client_db):
    client, _ = client_db
    assert client.patch("/api/playlists/9999", json={"name": "X"}).status_code == 404


def test_sync_non_sovrascrive_nome_lockato(client_db):
    _, db = client_db
    pl = Playlist(platform="spotify", platform_playlist_id="sp1", name="Mio nome", kind="playlist", name_locked=True)
    db.add(pl); db.commit()
    import_playlist(db, platform="spotify", name="Nome piattaforma", items=[], platform_playlist_id="sp1")
    db.refresh(pl)
    assert pl.name == "Mio nome"


def test_sync_sovrascrive_nome_non_lockato(client_db):
    _, db = client_db
    pl = Playlist(platform="spotify", platform_playlist_id="sp1", name="Vecchio", kind="playlist")
    db.add(pl); db.commit()
    import_playlist(db, platform="spotify", name="Nome piattaforma", items=[], platform_playlist_id="sp1")
    db.refresh(pl)
    assert pl.name == "Nome piattaforma"
