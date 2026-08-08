"""Le nuove tracce nascono con added_at valorizzato (fallback 'adesso').

Regola: la data della piattaforma vince quando c'e' (import Spotify); per gli
altri flussi (manuale, flat/soundcloud, indicizzazione locale) la traccia viene
datata alla creazione. Le tracce esistenti con added_at NULL non vengono mai
retrodatate dai re-sync.
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import Base
from app.models import Track
from app.services.manual_import import import_manual_playlist
from app.services.playlist_import import NormalizedTrack, _apply_fields


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng, expire_on_commit=False)()
    try:
        yield s
    finally:
        s.close()


def _norm(added_at=None):
    return NormalizedTrack(
        platform="soundcloud", platform_track_id="123", title="T", artist="A",
        album=None, duration_seconds=None, url=None, artwork_url=None,
        isrc=None, added_at=added_at,
    )


def test_apply_fields_nuova_traccia_senza_data_piattaforma(db):
    track = Track(source_type="soundcloud")  # id ancora assente
    _apply_fields(track, _norm(added_at=None))
    assert track.added_at is not None


def test_apply_fields_data_piattaforma_vince(db):
    track = Track(source_type="spotify")
    _apply_fields(track, _norm(added_at=datetime(2026, 3, 1)))
    assert track.added_at == datetime(2026, 3, 1)


def test_apply_fields_non_retrodata_le_esistenti(db):
    track = Track(source_type="soundcloud")
    db.add(track)
    db.flush()  # id presente -> traccia "esistente"
    track.added_at = None
    _apply_fields(track, _norm(added_at=None))
    assert track.added_at is None


def test_import_manuale_data_le_nuove_tracce(db):
    import_manual_playlist(db, name="P", text="Artista - Titolo")
    track = db.scalar(select(Track).where(Track.title == "Titolo"))
    assert track is not None
    assert track.added_at is not None
