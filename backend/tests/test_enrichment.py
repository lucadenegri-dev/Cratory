"""Test enrichment Spotify con sorgente finta: niente rete, regole F2 verificate."""

from app.models import Artist, Track
from app.services.enrichment import enrich_library

N = 20  # tracce sintetiche usate in tutti i test


class FakeSource:
    """Risponde con metadata deterministici per ogni id richiesto."""

    def __init__(self):
        self.track_calls = 0

    def get_tracks_batch(self, ids, on_progress=None):
        self.track_calls += 1
        if on_progress:
            on_progress(len(ids), len(ids), "tracce")
        return [
            {
                "id": sid,
                "name": f"Title {sid[-4:]}",
                "artists": [{"id": f"art_{sid[-4:]}", "name": f"Artist {sid[-4:]}"}],
                "album": {
                    "name": f"Album {sid[-4:]}",
                    "release_date": "2021-05-01",
                    "images": [{"url": f"https://img/{sid}.jpg"}],
                },
            }
            for sid in ids
        ]

    def get_artists_batch(self, ids, on_progress=None):
        if on_progress:
            on_progress(len(ids), len(ids), "artisti")
        return [
            {"id": aid, "name": f"Artist {aid[-4:]}", "genres": ["deconstructed club", "experimental"], "popularity": 55}
            for aid in ids
        ]


def test_enrich_fills_empty_metadata(db, seed_tracks):
    seed_tracks(n=N, with_metadata=False)  # tracce senza title/artist
    fake = FakeSource()

    report = enrich_library(db, fake)
    assert report["enriched"] == N
    assert report["artists_updated"] > 0

    spotify_tracks = db.query(Track).filter(Track.spotify_id.is_not(None)).all()
    assert all(t.title for t in spotify_tracks)
    assert all(t.artist for t in spotify_tracks)
    assert all(t.album_art_url for t in spotify_tracks)
    assert all(t.year for t in spotify_tracks)
    assert all(t.genre for t in spotify_tracks)
    assert all(t.enriched_at for t in spotify_tracks)
    artist = db.query(Artist).first()
    assert artist.genres and artist.popularity == 55


def test_enrich_never_touches_dj_data(db, seed_tracks):
    seed_tracks(n=N, with_metadata=True)
    before = {
        t.id: (t.bpm, t.tonality, t.duration_seconds, t.play_count)
        for t in db.query(Track).all()
    }
    enrich_library(db, FakeSource())
    after = {
        t.id: (t.bpm, t.tonality, t.duration_seconds, t.play_count)
        for t in db.query(Track).all()
    }
    assert before == after, "BPM/key/durata/playcount non devono cambiare con l'enrichment"


def test_enrich_is_cached(db, seed_tracks):
    seed_tracks(n=N, with_metadata=False)
    fake = FakeSource()
    enrich_library(db, fake)
    calls_after_first = fake.track_calls

    report = enrich_library(db, fake)  # seconda passata: tutto in cache
    assert report["enriched"] == 0
    assert report["skipped_already_enriched"] is True
    assert fake.track_calls == calls_after_first

    report = enrich_library(db, fake, force=True)  # force ricarica
    assert report["enriched"] == N


def test_enrich_reports_progress(db, seed_tracks):
    seed_tracks(n=N, with_metadata=False)
    events = []
    enrich_library(db, FakeSource(), on_progress=lambda p, t, phase: events.append((p, t, phase)))
    assert events, "il callback di progresso deve essere invocato"
    assert any(phase == "tracce" for _, _, phase in events)
    last_tracce = [e for e in events if e[2] == "tracce"][-1]
    assert last_tracce[0] == last_tracce[1]
