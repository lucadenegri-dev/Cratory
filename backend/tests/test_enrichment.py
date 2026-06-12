"""Test enrichment Spotify con sorgente finta: niente rete, regole F2 verificate."""

from app.models import Artist, Track
from app.services.enrichment import enrich_library
from app.services.import_service import import_rekordbox_xml


class FakeSource:
    """Risponde con metadata deterministici per ogni id richiesto."""

    def __init__(self):
        self.track_calls = 0

    def get_tracks_batch(self, ids):
        self.track_calls += 1
        return [
            {
                "id": sid,
                "name": f"Title {sid[:4]}",
                "artists": [{"id": f"art_{sid[:4]}", "name": f"Artist {sid[:4]}"}],
                "album": {
                    "name": f"Album {sid[:4]}",
                    "release_date": "2021-05-01",
                    "images": [{"url": f"https://img/{sid}.jpg"}],
                },
            }
            for sid in ids
        ]

    def get_artists_batch(self, ids):
        return [
            {"id": aid, "name": f"Artist {aid[4:]}", "genres": ["deconstructed club", "experimental"], "popularity": 55}
            for aid in ids
        ]


def test_enrich_fills_empty_metadata_only(db, sample_xml_bytes):
    import_rekordbox_xml(db, sample_xml_bytes)
    fake = FakeSource()

    report = enrich_library(db, fake)
    assert report["enriched"] == 198
    assert report["artists_updated"] > 0

    spotify_tracks = db.query(Track).filter(Track.spotify_id.is_not(None)).all()
    # tutti arricchiti: titolo, artista, cover, anno, genere da artista
    assert all(t.title for t in spotify_tracks)
    assert all(t.artist for t in spotify_tracks)
    assert all(t.album_art_url for t in spotify_tracks)
    # l'anno viene completato dove mancava (quello di Rekordbox non si tocca)
    assert all(t.year for t in spotify_tracks)
    assert all(t.genre for t in spotify_tracks)
    assert all(t.enriched_at for t in spotify_tracks)
    # gli artisti sono stati salvati con generi e popularity
    artist = db.query(Artist).first()
    assert artist.genres and artist.popularity == 55


def test_enrich_never_touches_dj_data(db, sample_xml_bytes):
    import_rekordbox_xml(db, sample_xml_bytes)
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


def test_enrich_is_cached(db, sample_xml_bytes):
    import_rekordbox_xml(db, sample_xml_bytes)
    fake = FakeSource()
    enrich_library(db, fake)
    calls_after_first = fake.track_calls

    report = enrich_library(db, fake)  # seconda passata: tutto in cache
    assert report["enriched"] == 0
    assert report["skipped_already_enriched"] is True
    assert fake.track_calls == calls_after_first

    report = enrich_library(db, fake, force=True)  # force ricarica
    assert report["enriched"] == 198


def test_reimport_preserves_enriched_metadata(db, sample_xml_bytes):
    import_rekordbox_xml(db, sample_xml_bytes)
    enrich_library(db, FakeSource())

    # re-import: l'XML ha title/artist vuoti per le tracce Spotify,
    # ma i valori arricchiti non devono sparire
    import_rekordbox_xml(db, sample_xml_bytes)
    spotify_tracks = db.query(Track).filter(Track.spotify_id.is_not(None)).all()
    assert all(t.title for t in spotify_tracks)
    assert all(t.artist for t in spotify_tracks)
