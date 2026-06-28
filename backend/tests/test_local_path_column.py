"""Colonna local_path: persistenza + overwrite-quando-presente in _apply_fields."""

from app.models import Playlist, Track
from app.services.playlist_import import NormalizedTrack, _apply_fields


def test_track_ha_local_path(db):
    t = Track(source_type="local_files", title="X", local_path="/music/x.flac")
    db.add(t)
    db.commit()
    db.refresh(t)
    assert t.local_path == "/music/x.flac"


def test_apply_fields_imposta_local_path(db):
    t = Track(source_type="local_files")
    norm = NormalizedTrack(
        platform="local_files", platform_track_id="h1", title="X", artist="Y",
        album=None, duration_seconds=None, url=None, artwork_url=None, isrc=None,
        added_at=None, local_path="/music/a.flac",
    )
    _apply_fields(t, norm)
    assert t.local_path == "/music/a.flac"


def test_apply_fields_aggiorna_local_path_su_spostamento(db):
    t = Track(source_type="local_files", local_path="/music/old.flac")
    norm = NormalizedTrack(
        platform="local_files", platform_track_id="h1", title="X", artist="Y",
        album=None, duration_seconds=None, url=None, artwork_url=None, isrc=None,
        added_at=None, local_path="/music/new.flac",
    )
    _apply_fields(t, norm)
    assert t.local_path == "/music/new.flac"  # sovrascritto deliberatamente


def test_apply_fields_non_tocca_local_path_se_norm_vuoto(db):
    t = Track(source_type="spotify", local_path="/music/keep.flac")
    norm = NormalizedTrack(
        platform="spotify", platform_track_id="s1", title="X", artist="Y",
        album=None, duration_seconds=None, url=None, artwork_url=None, isrc=None,
        added_at=None,  # local_path resta None
    )
    _apply_fields(t, norm)
    assert t.local_path == "/music/keep.flac"  # invariato: norm.local_path è None
