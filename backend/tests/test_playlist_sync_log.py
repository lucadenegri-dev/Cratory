"""Storico diff dei sync: playlist_sync_events + GET /sync-log."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
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


def _item(sid: str, title: str, artist: str = "A"):
    """Item Spotify minimale per normalize_spotify_item."""
    return {"track": {
        "id": sid, "name": title, "duration_ms": 200000,
        "artists": [{"name": artist}], "album": {"images": []},
        "external_ids": {}, "external_urls": {},
    }}


def test_import_e_prune_registrano_eventi(client_db):
    client, db = client_db
    report = import_playlist(db, platform="spotify", name="P",
                             items=[_item("s1", "Uno"), _item("s2", "Due")],
                             platform_playlist_id="pl1")
    pid = report["playlist_id"]
    log = client.get(f"/api/playlists/{pid}/sync-log").json()
    assert len(log) == 1
    assert sorted(t["title"] for t in log[0]["added"]) == ["Due", "Uno"]
    assert log[0]["removed"] == []

    # secondo sync: s2 sparisce (prune), s3 entra
    import_playlist(db, platform="spotify", name="P",
                    items=[_item("s1", "Uno"), _item("s3", "Tre")],
                    platform_playlist_id="pl1", prune=True)
    log = client.get(f"/api/playlists/{pid}/sync-log").json()
    assert len(log) == 2
    latest = log[0]  # più recente prima
    assert [t["title"] for t in latest["added"]] == ["Tre"]
    assert [t["title"] for t in latest["removed"]] == ["Due"]


def test_sync_senza_variazioni_non_crea_eventi(client_db):
    client, db = client_db
    items = [_item("s1", "Uno")]
    report = import_playlist(db, platform="spotify", name="P", items=items, platform_playlist_id="pl1")
    import_playlist(db, platform="spotify", name="P", items=items, platform_playlist_id="pl1", prune=True)
    log = client.get(f"/api/playlists/{report['playlist_id']}/sync-log").json()
    assert len(log) == 1  # solo il primo import


def test_delete_playlist_pulisce_lo_storico(client_db):
    client, db = client_db
    report = import_playlist(db, platform="spotify", name="P",
                             items=[_item("s1", "Uno")], platform_playlist_id="pl1")
    pid = report["playlist_id"]
    assert client.delete(f"/api/playlists/{pid}").status_code == 200
    from app.models import PlaylistSyncEvent
    from sqlalchemy import select
    assert db.scalars(select(PlaylistSyncEvent).where(PlaylistSyncEvent.playlist_id == pid)).first() is None


def test_sync_log_404(client_db):
    client, _ = client_db
    assert client.get("/api/playlists/9999/sync-log").status_code == 404
