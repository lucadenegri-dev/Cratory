"""Sezione Etichette: backfill label da Spotify (robusto: budget, cache, rate-limit) + panoramica."""

from app.integrations.spotify import SpotifyError
from app.models import EnrichmentCache, Track
from app.services.labels import backfill_labels, labels_overview


class _FakeSpotify:
    """Client finto: traccia -> album.id, album -> label. Conta le chiamate di rete."""

    def __init__(self, track_albums=None, album_labels=None, rate_limit_albums=None):
        self._track_albums = track_albums or {}
        self._album_labels = album_labels or {}
        self._rate_limit_albums = rate_limit_albums or set()
        self.track_calls = 0
        self.album_calls = 0

    def get_track_metadata(self, sid):
        self.track_calls += 1
        return {"id": sid, "album": {"id": self._track_albums.get(sid)}}

    def get_album(self, album_id):
        self.album_calls += 1
        if album_id in self._rate_limit_albums:
            raise SpotifyError("Spotify ha applicato un rate limit prolungato")
        return {"id": album_id, "label": self._album_labels.get(album_id)}


def _track(db, **kw) -> Track:
    kw.setdefault("source_type", "spotify")
    t = Track(**kw)
    db.add(t)
    db.commit()
    return t


def test_backfill_sets_label_from_album(db):
    t1 = _track(db, spotify_id="s1", title="A", album_id="alb1")
    t2 = _track(db, spotify_id="s2", title="B", album_id="alb1")
    _track(db, source_type="manual", title="C")  # niente identita' Spotify -> ignorata

    client = _FakeSpotify(album_labels={"alb1": "Warp Records"})
    report = backfill_labels(db, client)

    assert report["updated"] == 2
    assert report["remaining"] == 0
    assert report["rate_limited"] is False
    db.refresh(t1); db.refresh(t2)
    assert t1.label == t2.label == "Warp Records"
    # un solo album distinto -> una sola chiamata album (dedup nello stesso run)
    assert client.album_calls == 1
    # album_id gia' presente -> nessuna lookup di traccia
    assert client.track_calls == 0


def test_backfill_fetches_album_id_when_missing(db):
    t = _track(db, spotify_id="s1", title="A")  # album_id mancante
    client = _FakeSpotify(track_albums={"s1": "alb1"}, album_labels={"alb1": "Hyperdub"})
    backfill_labels(db, client)
    db.refresh(t)
    assert t.album_id == "alb1"  # memorizzato per i run futuri
    assert t.label == "Hyperdub"
    assert client.track_calls == 1


def test_backfill_respects_lookup_budget(db):
    for i in range(5):
        _track(db, spotify_id=f"s{i}", title=f"T{i}", album_id=f"alb{i}")
    client = _FakeSpotify(album_labels={f"alb{i}": f"Label {i}" for i in range(5)})

    report = backfill_labels(db, client, max_lookups=2)

    assert report["updated"] == 2
    assert report["remaining"] == 3
    assert client.album_calls == 2  # budget rispettato


def test_backfill_caches_album_label_across_runs(db):
    t1 = _track(db, spotify_id="s1", title="A", album_id="alb1")
    client = _FakeSpotify(album_labels={"alb1": "PAN"})
    backfill_labels(db, client)
    assert client.album_calls == 1
    assert db.query(EnrichmentCache).filter_by(provider="spotify_album_label").count() == 1

    # nuova traccia stesso album: il secondo run NON richiama l'album (cache hit)
    t2 = _track(db, spotify_id="s2", title="B", album_id="alb1")
    client2 = _FakeSpotify()  # qualsiasi chiamata fallirebbe (album sconosciuto -> label None)
    backfill_labels(db, client2)
    db.refresh(t2)
    assert t2.label == "PAN"
    assert client2.album_calls == 0


def test_backfill_stops_gracefully_on_rate_limit(db):
    _track(db, spotify_id="s1", title="A", album_id="alb1")
    _track(db, spotify_id="s2", title="B", album_id="alb2")
    client = _FakeSpotify(album_labels={"alb1": "Warp"}, rate_limit_albums={"alb2"})

    report = backfill_labels(db, client, max_lookups=100)

    assert report["rate_limited"] is True
    assert report["updated"] == 1  # la prima e' stata salvata prima dello stop


def test_backfill_does_not_overwrite_existing_label(db):
    t = _track(db, spotify_id="s1", title="A", album_id="alb1", label="Etichetta esistente")
    client = _FakeSpotify(album_labels={"alb1": "Nuova"})
    report = backfill_labels(db, client)
    assert report["updated"] == 0
    db.refresh(t)
    assert t.label == "Etichetta esistente"


def test_labels_overview_aggregates_counts_and_info(db):
    _track(db, spotify_id="s1", title="A", artist="Artist 1", genre="idm", year=2018, label="Warp")
    _track(db, spotify_id="s2", title="B", artist="Artist 2", genre="electronic", year=2020, label="Warp")
    _track(db, spotify_id="s3", title="C", artist="Artist 3", genre="dubstep", year=2012, label="Hyperdub")
    _track(db, spotify_id="s4", title="D", artist="Artist 4")  # senza label -> esclusa

    overview = labels_overview(db)

    assert [o["label"] for o in overview] == ["Warp", "Hyperdub"]  # ordinate per conteggio desc
    warp = overview[0]
    assert warp["track_count"] == 2
    assert warp["artist_count"] == 2
    assert set(warp["genres"]) == {"idm", "electronic"}
    assert warp["year_min"] == 2018
    assert warp["year_max"] == 2020
