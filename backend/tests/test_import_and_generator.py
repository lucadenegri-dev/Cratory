"""Test end-to-end su DB in memoria: import del file reale + generazione set."""

from app.models import Track
from app.schemas import SetGenerationRequest
from app.services.import_service import import_rekordbox_xml
from app.services.set_generator import generate_set


def test_import_is_idempotent(db, sample_xml_bytes):
    report1 = import_rekordbox_xml(db, sample_xml_bytes, filename="export.xml")
    assert report1.stats["total_tracks"] == 293
    assert report1.stats["created"] == 293
    assert report1.stats["spotify_tracks"] == 198
    assert report1.stats["missing_title_or_artist"] > 0
    assert report1.stats["bpm_min"] is not None

    # re-import: nessun duplicato
    report2 = import_rekordbox_xml(db, sample_xml_bytes, filename="export.xml")
    assert report2.stats["created"] == 0
    assert report2.stats["updated"] == 293
    assert db.query(Track).count() == 293


def test_generate_set_respects_constraints(db, sample_xml_bytes):
    import_rekordbox_xml(db, sample_xml_bytes)
    req = SetGenerationRequest(
        target_duration_minutes=45,
        start_bpm=128,
        end_bpm=136,
        strategy="progressive",
        max_tracks_per_artist=2,
        avoid_short_tracks=True,
    )
    setlist = generate_set(db, req)

    assert len(setlist.tracks) >= 3
    track_ids = [st.track_id for st in setlist.tracks]
    assert len(track_ids) == len(set(track_ids)), "nessuna traccia duplicata"

    # max tracce per artista
    counts: dict[str, int] = {}
    for st in setlist.tracks:
        artist = (st.track.artist or "").lower()
        if artist:
            counts[artist] = counts.get(artist, 0) + 1
    assert all(c <= 2 for c in counts.values())

    # durata vicina al target (tolleranza: una traccia)
    total = sum(st.track.duration_seconds or 0 for st in setlist.tracks)
    assert total >= 45 * 60 * 0.8

    # niente tracce-sample cortissime
    assert all((st.track.duration_seconds or 0) >= 120 for st in setlist.tracks)

    # spiegazioni presenti
    assert setlist.global_explanation
    assert all(st.transition_reason for st in setlist.tracks)
    assert all(st.risk_level in ("low", "medium", "high") for st in setlist.tracks)

    # posizioni progressive
    assert [st.position for st in setlist.tracks] == list(range(1, len(setlist.tracks) + 1))


def test_generate_set_source_filter(db, sample_xml_bytes):
    import_rekordbox_xml(db, sample_xml_bytes)
    req = SetGenerationRequest(target_duration_minutes=30, sources=["spotify"])
    setlist = generate_set(db, req)
    assert all(st.track.source_type == "spotify" for st in setlist.tracks)
