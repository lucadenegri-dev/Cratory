"""Test del nuovo flusso playlist->set (deterministico, nessuna rete/AI)."""

from app.models import Playlist, Track
from app.services.feature_enrichment import enrich_features
from app.services.gap_analysis import analyze_gaps
from app.services.playlist_import import import_playlist, normalize_spotify_item
from app.services.scoring import (
    energy_progression_score,
    genre_similarity_score,
    mood_coherence_score,
)
from app.services.set_generator import assign_roles
from app.services.track_status import compute_status


def _spotify_item(tid: str, *, name: str, artist: str, isrc: str | None = None,
                  ms: int = 200_000, added: str | None = "2024-01-01T00:00:00Z") -> dict:
    return {
        "added_at": added,
        "track": {
            "id": tid,
            "type": "track",
            "name": name,
            "duration_ms": ms,
            "artists": [{"name": artist}],
            "album": {"name": "Album", "images": [{"url": "http://img/cover.jpg"}]},
            "external_ids": {"isrc": isrc} if isrc else {},
            "external_urls": {"spotify": f"https://open.spotify.com/track/{tid}"},
        },
    }


# --- normalizzazione + import -------------------------------------------------


def test_normalize_skips_episodes_and_locals():
    assert normalize_spotify_item({"track": {"id": "x", "type": "episode"}}) is None
    assert normalize_spotify_item({"track": {"id": "x", "is_local": True}}) is None
    assert normalize_spotify_item({"track": None}) is None
    norm = normalize_spotify_item(_spotify_item("abc", name="T", artist="A", isrc="IT1234500001"))
    assert norm.platform == "spotify"
    assert norm.platform_track_id == "abc"
    assert norm.isrc == "IT1234500001"
    assert norm.duration_seconds == 200
    assert norm.added_at is not None


def _playlist_items_entry(tid: str, *, name: str, artist: str, isrc: str | None = None) -> dict:
    """Forma dell'endpoint /playlists/{id}/items: la traccia sta sotto 'item'."""
    base = _spotify_item(tid, name=name, artist=artist, isrc=isrc)
    return {"added_at": base["added_at"], "is_local": False, "item": base["track"]}


def test_normalize_handles_playlist_items_shape():
    # /playlists/{id}/items annida la traccia sotto 'item' (non 'track'): in
    # Development Mode l'endpoint /tracks da' 403, /items e' quello usato.
    norm = normalize_spotify_item(
        _playlist_items_entry("abc", name="T", artist="A", isrc="IT1234500001")
    )
    assert norm is not None
    assert norm.platform_track_id == "abc"
    assert norm.isrc == "IT1234500001"
    assert norm.duration_seconds == 200
    # episodi e brani locali scartati anche nella forma 'item'
    assert normalize_spotify_item({"item": {"id": "x", "type": "episode"}}) is None
    assert normalize_spotify_item({"is_local": True, "item": {"id": "x", "type": "track"}}) is None


def test_import_playlist_is_idempotent_and_dedups_by_isrc(db):
    items = [
        _spotify_item("t1", name="One", artist="A", isrc="ISRC0000001"),
        _spotify_item("t2", name="Two", artist="B"),
    ]
    rep1 = import_playlist(db, platform="spotify", name="My PL", items=items,
                           platform_playlist_id="PL1")
    assert rep1["created"] == 2
    assert rep1["total"] == 2

    # re-import della stessa playlist: nessun duplicato
    rep2 = import_playlist(db, platform="spotify", name="My PL", items=items,
                           platform_playlist_id="PL1")
    assert rep2["created"] == 0
    assert rep2["updated"] == 2
    assert db.query(Track).count() == 2
    assert db.query(Playlist).count() == 1

    # stessa traccia con id diverso ma stesso ISRC -> dedotta come esistente
    dup = [_spotify_item("t1_other_id", name="One", artist="A", isrc="ISRC0000001")]
    rep3 = import_playlist(db, platform="spotify", name="Other", items=dup,
                           platform_playlist_id="PL2")
    assert rep3["created"] == 0
    assert rep3["updated"] == 1
    assert db.query(Track).count() == 2


def test_imported_track_status_is_imported(db):
    import_playlist(db, platform="spotify", name="PL", items=[
        _spotify_item("t1", name="One", artist="A"),
    ], platform_playlist_id="PL1")
    track = db.query(Track).one()
    assert track.status == "imported"
    assert track.source_type == "spotify"


# --- stato traccia -----------------------------------------------------------


def test_compute_status_transitions():
    t = Track(source_type="spotify")
    assert compute_status(t) == "imported"
    t.enrichment_source = "getsongbpm"
    assert compute_status(t) == "missing_features"
    t.bpm = 124.0
    t.camelot_key = "8A"
    t.enrichment_confidence = 90
    assert compute_status(t) == "ready_for_set"
    t.enrichment_confidence = 20
    assert compute_status(t) == "low_confidence"


# --- feature enrichment (fake provider, mai sovrascrive BPM esistente) -------


class _FakeProvider:
    name = "fake"

    def lookup(self, *, title, artist, isrc=None, duration_seconds=None):
        return {"bpm": 126, "camelot_key": "9A", "energy": 70, "mood": "dark",
                "label": "Label X", "confidence": 80}


def test_feature_enrichment_fills_only_missing(db):
    keep = Track(source_type="spotify", title="rek", bpm=128.0, camelot_key="5A")
    fill = Track(source_type="spotify", title="stream")
    db.add_all([keep, fill])
    db.commit()

    report = enrich_features(db, _FakeProvider(), force=False)
    assert report["enriched"] == 1  # solo quella senza BPM
    db.refresh(keep)
    db.refresh(fill)
    assert keep.bpm == 128.0  # dato preesistente intatto
    assert fill.bpm == 126.0
    assert fill.camelot_key == "9A"
    assert fill.status == "ready_for_set"
    assert fill.enrichment_source == "fake"


# --- analisi buchi -----------------------------------------------------------


def test_gap_analysis_detects_missing_peak_and_openers():
    tracks = [Track(source_type="spotify", bpm=122.0 + i * 0.2, energy=50) for i in range(6)]
    gaps = {g["gap_type"] for g in analyze_gaps(tracks)}
    assert "few_peak_tracks" in gaps
    assert "missing_openers" in gaps
    assert "uniform_energy" in gaps


def test_gap_analysis_detects_bpm_bridge():
    tracks = (
        [Track(source_type="spotify", bpm=b) for b in (118, 119, 120, 121)]
        + [Track(source_type="spotify", bpm=b) for b in (130, 131, 132)]
    )
    gaps = {g["gap_type"] for g in analyze_gaps(tracks)}
    assert "missing_bpm_bridge" in gaps


def test_gap_analysis_empty():
    assert analyze_gaps([]) == []


# --- ruoli set ---------------------------------------------------------------


def test_assign_roles_arc():
    roles = assign_roles(10)
    assert roles[0] == "intro"
    assert roles[-1] == "closing"
    assert "peak" in roles
    assert roles.index("peak") < len(roles) - 1
    assert assign_roles(1) == ["intro"]
    assert assign_roles(0) == []


# --- score feature -----------------------------------------------------------


def test_feature_scores_neutral_when_missing():
    assert energy_progression_score(None, 50) == 50
    assert mood_coherence_score("dark", None) == 50
    assert genre_similarity_score(None, None) == 50


def test_feature_scores_values():
    assert energy_progression_score(50, 55) == 100  # leggera salita
    assert energy_progression_score(80, 40) < 60     # crollo
    assert mood_coherence_score("Dark", "dark") == 100
    assert genre_similarity_score("deep house", "tech house") > 50


def test_delete_playlist_keeps_shared_tracks(db):
    """Cancellare una playlist (es. i Liked importati per sbaglio) NON deve
    eliminare dalla libreria i brani condivisi con altre playlist."""
    from app.repositories import delete_playlist, tracks_for_playlist

    import_playlist(
        db, platform="spotify", name="A", platform_playlist_id="pa",
        items=[_spotify_item("t1", name="Song", artist="Artist", isrc="IT1234500001")],
    )
    rep_liked = import_playlist(
        db, platform="spotify", name="Brani che ti piacciono", kind="liked",
        items=[_spotify_item("t1", name="Song", artist="Artist", isrc="IT1234500001")],
    )
    assert db.query(Track).count() == 1  # dedup per ISRC: una sola riga

    deleted_playlist_id = rep_liked["playlist_id"]
    assert delete_playlist(db, deleted_playlist_id) is True
    # il brano resta in libreria dopo la delete
    assert db.query(Track).count() == 1
    # la membership per la playlist cancellata non esiste piu'
    assert tracks_for_playlist(db, deleted_playlist_id) == []
