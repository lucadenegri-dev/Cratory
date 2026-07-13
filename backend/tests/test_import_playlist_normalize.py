"""import_playlist generalizzato: normalizzatore iniettabile + identità per item già pronti."""

from app.models import Playlist, Track
from app.services.playlist_import import (
    NormalizedTrack,
    identity_normalize,
    import_playlist,
)


def _norm(**kw) -> NormalizedTrack:
    base = dict(
        platform="local_files", platform_track_id=None, title=None, artist=None,
        album=None, duration_seconds=None, url=None, artwork_url=None, isrc=None,
        added_at=None,
    )
    base.update(kw)
    return NormalizedTrack(**base)


def test_importa_item_gia_normalizzati(db):
    items = [
        _norm(platform_track_id="h1", title="A", artist="X", local_path="/m/a.flac"),
        _norm(platform_track_id="h2", title="B", artist="Y", local_path="/m/b.flac"),
    ]
    report = import_playlist(
        db, platform="local_files", name="Crate", items=items, normalize=identity_normalize,
    )
    assert report["created"] == 2
    assert report["total"] == 2
    pl = db.get(Playlist, report["playlist_id"])
    assert pl.platform == "local_files"
    tracks = {t.title: t for t in db.query(Track).all()}
    assert tracks["A"].local_path == "/m/a.flac"
    assert tracks["A"].platform_track_id == "h1"


def test_dedup_per_platform_track_id(db):
    items = [_norm(platform_track_id="h1", title="A", artist="X", local_path="/m/a.flac")]
    import_playlist(db, platform="local_files", name="C1", items=items, normalize=identity_normalize)
    # stesso hash, path diverso (file spostato) -> aggiorna, non duplica
    items2 = [_norm(platform_track_id="h1", title="A", artist="X", local_path="/m/moved.flac")]
    report = import_playlist(db, platform="local_files", name="C2", items=items2, normalize=identity_normalize)
    assert report["created"] == 0
    assert report["updated"] == 1
    assert db.query(Track).count() == 1
    assert db.query(Track).first().local_path == "/m/moved.flac"


def test_spotify_resta_default(db):
    # item Spotify grezzo: il default normalize_spotify_item lo gestisce ancora.
    item = {
        "track": {
            "id": "sp1", "name": "Song", "duration_ms": 200000,
            "artists": [{"name": "Artist"}],
            "album": {"name": "Alb", "images": [], "release_date": "2020"},
            "external_ids": {"isrc": "US1234567890"},
            "external_urls": {"spotify": "http://x"},
        }
    }
    report = import_playlist(db, platform="spotify", name="P", items=[item])
    assert report["created"] == 1


def test_on_progress_default_none_nessuna_chiamata(db):
    # Comportamento invariato senza on_progress: nessun crash, nessuna chiamata implicita.
    items = [_norm(platform_track_id="h1", title="A", artist="X", local_path="/m/a.flac")]
    report = import_playlist(db, platform="local_files", name="C", items=items, normalize=identity_normalize)
    assert report["created"] == 1


def test_on_progress_chiamato_con_avanzamento_e_totale_finale(db):
    items = [
        _norm(platform_track_id=f"h{i}", title=f"T{i}", artist="X", local_path=f"/m/{i}.flac")
        for i in range(3)
    ]
    calls: list[tuple[int, int]] = []
    import_playlist(
        db, platform="local_files", name="C", items=items, normalize=identity_normalize,
        on_progress=lambda done, total: calls.append((done, total)),
    )
    assert calls[0] == (0, 3)  # chiamata iniziale: nessun item ancora processato
    assert calls[-1] == (3, 3)  # chiamata finale: tutti processati
    assert all(total == 3 for _, total in calls)
