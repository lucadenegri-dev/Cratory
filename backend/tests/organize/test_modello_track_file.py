"""Modello Track 1─N AudioFile: colonne, relazione, semantica di cancellazione."""

import pytest
from sqlalchemy import inspect

from app.models import Track
from app.organize.models import AudioFile, ScanRoot


@pytest.fixture()
def radice(db):
    r = ScanRoot(path="/lib")
    db.add(r)
    db.flush()
    return r


def _file(radice, path: str, **kw) -> AudioFile:
    return AudioFile(root_id=radice.id, path=path, ext=".flac", size_bytes=1,
                     hash_method="stream", status="present", location="library", **kw)


def test_colonne_presenti():
    assert "primary_file_id" in inspect(Track).columns
    assert "track_id" in inspect(AudioFile).columns
    assert "location" in inspect(AudioFile).columns


def test_una_traccia_puo_avere_piu_file(db, radice):
    t = Track(source_type="manual", artist="A", title="B")
    db.add(t)
    db.flush()
    db.add_all([_file(radice, "/lib/a.flac", track_id=t.id),
                _file(radice, "/lib/a-copia.flac", track_id=t.id)])
    db.commit()
    db.refresh(t)
    assert {f.path for f in t.files} == {"/lib/a.flac", "/lib/a-copia.flac"}


def test_file_senza_traccia_e_legittimo(db, radice):
    """Un file nell'inbox non è ancora una traccia: track_id resta NULL."""
    f = _file(radice, "/inbox/x.mp3")
    f.location = "inbox"
    db.add(f)
    db.commit()
    assert f.track_id is None
    assert f.track is None


def test_cancellare_la_traccia_non_cancella_il_file(db, radice):
    """Il file è ancora sul disco: sopravvive con track_id azzerato."""
    t = Track(source_type="manual", artist="A", title="B")
    db.add(t)
    db.flush()
    f = _file(radice, "/lib/a.flac", track_id=t.id)
    db.add(f)
    db.commit()

    db.delete(t)
    db.commit()

    rimasto = db.get(AudioFile, f.id)
    assert rimasto is not None
    assert rimasto.track_id is None
