"""Provenienza delle membership playlist (A12): `added_by` su playlist_tracks.

Una traccia aggiunta da Cratory (Discovery -> playlist) ha added_by='cratory' e il
prune del sync Spotify NON deve scollegarla, anche se il write-back verso Spotify
e' fallito e la traccia non compare nello snapshot della piattaforma. Le membership
da import piattaforma (added_by NULL) continuano a essere potate come oggi.
"""

from sqlalchemy import create_engine, inspect, select, text

from app import models  # noqa: F401 - registra i modelli su Base.metadata
from app.db import Base, ensure_schema
from app.models import Playlist, Track, playlist_tracks
from app.repositories import add_track_to_playlist, tracks_for_playlist
from app.routers.discovery import save_for_later
from app.schemas import DiscoverySaveForLaterRequest
from app.services.playlist_import import import_playlist


def _spotify_item(tid: str, *, name: str, artist: str, isrc: str | None = None) -> dict:
    return {
        "added_at": "2024-01-01T00:00:00Z",
        "track": {
            "id": tid,
            "type": "track",
            "name": name,
            "duration_ms": 200_000,
            "artists": [{"name": artist}],
            "album": {"name": "Album", "images": []},
            "external_ids": {"isrc": isrc} if isrc else {},
            "external_urls": {"spotify": f"https://open.spotify.com/track/{tid}"},
        },
    }


def _membership_added_by(db, playlist_id: int, track_id: int) -> str | None:
    return db.execute(
        select(playlist_tracks.c.added_by).where(
            playlist_tracks.c.playlist_id == playlist_id,
            playlist_tracks.c.track_id == track_id,
        )
    ).scalar_one()


# --- prune protection ---------------------------------------------------------


def test_prune_preserva_membership_cratory(db):
    items = [
        _spotify_item("t1", name="One", artist="A", isrc="ISRC0000001"),
        _spotify_item("t2", name="Two", artist="B", isrc="ISRC0000002"),
    ]
    import_playlist(db, platform="spotify", name="PL", items=items, platform_playlist_id="PL1")
    playlist = db.query(Playlist).filter(Playlist.platform_playlist_id == "PL1").one()

    # Traccia aggiunta da Discovery (write-back Spotify fallito: non e' nello snapshot)
    scoperta = Track(source_type="spotify", platform="spotify",
                     platform_track_id="sp9", spotify_id="sp9",
                     artist="Z", title="Nine", isrc="ISRC0000009")
    db.add(scoperta)
    db.flush()
    add_track_to_playlist(db, scoperta, playlist, added_by="cratory")
    db.commit()

    # ri-sync: lo snapshot Spotify contiene solo t1/t2, NON la scoperta
    report = import_playlist(
        db, platform="spotify", name="PL",
        items=items, platform_playlist_id="PL1", prune=True,
    )

    assert report["removed"] == 0
    linked = tracks_for_playlist(db, playlist.id)
    assert scoperta in linked  # la membership Cratory sopravvive al prune
    assert len(linked) == 3
    assert playlist.track_count == 3


def test_prune_rimuove_ancora_membership_da_import(db):
    # Nessuna regressione: le membership da import piattaforma (added_by NULL)
    # assenti dallo snapshot vengono scollegate come oggi.
    import_playlist(db, platform="spotify", name="PL", items=[
        _spotify_item("t1", name="One", artist="A", isrc="ISRC0000001"),
        _spotify_item("t2", name="Two", artist="B", isrc="ISRC0000002"),
    ], platform_playlist_id="PL1")

    report = import_playlist(db, platform="spotify", name="PL", items=[
        _spotify_item("t1", name="One", artist="A", isrc="ISRC0000001"),
    ], platform_playlist_id="PL1", prune=True)

    assert report["removed"] == 1
    playlist = db.query(Playlist).filter(Playlist.platform_playlist_id == "PL1").one()
    assert len(tracks_for_playlist(db, playlist.id)) == 1
    t2 = db.query(Track).filter(Track.isrc == "ISRC0000002").one()
    assert t2 not in tracks_for_playlist(db, playlist.id)


def test_membership_da_import_ha_added_by_null(db):
    import_playlist(db, platform="spotify", name="PL", items=[
        _spotify_item("t1", name="One", artist="A", isrc="ISRC0000001"),
    ], platform_playlist_id="PL1")
    playlist = db.query(Playlist).filter(Playlist.platform_playlist_id == "PL1").one()
    track = db.query(Track).filter(Track.isrc == "ISRC0000001").one()
    assert _membership_added_by(db, playlist.id, track.id) is None


# --- migrazione ----------------------------------------------------------------


def test_added_by_su_schema_nuovo():
    engine = create_engine("sqlite://")
    ensure_schema(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("playlist_tracks")}
    assert "added_by" in cols


def test_added_by_su_db_esistente_senza_colonna():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        # tabella pre-migrazione: senza added_by
        conn.execute(text("DROP TABLE playlist_tracks"))
        conn.execute(text(
            "CREATE TABLE playlist_tracks ("
            "playlist_id INTEGER NOT NULL REFERENCES playlists(id), "
            "track_id INTEGER NOT NULL REFERENCES tracks(id), "
            "added_at DATETIME, "
            "PRIMARY KEY (playlist_id, track_id))"
        ))
    ensure_schema(engine)
    ensure_schema(engine)  # idempotente: seconda passata no-op
    cols = {c["name"] for c in inspect(engine).get_columns("playlist_tracks")}
    assert "added_by" in cols


# --- endpoint -------------------------------------------------------------------


def test_save_for_later_marca_cratory(db):
    req = DiscoverySaveForLaterRequest(artist="A", title="Per Dopo")
    save_for_later(req, db)

    playlist = db.query(Playlist).filter(Playlist.kind == "discovery").one()
    track = db.query(Track).filter(Track.title == "Per Dopo").one()
    assert _membership_added_by(db, playlist.id, track.id) == "cratory"
