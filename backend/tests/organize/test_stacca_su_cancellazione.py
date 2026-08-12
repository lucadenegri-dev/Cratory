"""Cancellare un AudioFile non deve lasciare Track che lo puntano.

Track.primary_file_id non ha relationship() che ordini la cancellazione, e sul
DB migrato non ha nemmeno il vincolo FK (ADD COLUMN non può aggiungere
REFERENCES): senza `stacca_file` resta un puntatore a un id inesistente — la
stessa forma delle 158 righe orfane trovate migrando in F2.
"""

from sqlalchemy import select

from app.models import Track
from app.organize.models import AudioFile, ScanRoot
from app.organize.services.file_link import stacca_file

LIB = "/lib"


def _orfane(db) -> list[Track]:
    return list(db.scalars(
        select(Track).where(Track.primary_file_id.is_not(None))
        .where(~Track.primary_file_id.in_(select(AudioFile.id)))
    ))


def test_helper_azzera_prima_della_cancellazione(db):
    r = ScanRoot(path=LIB)
    db.add(r)
    db.flush()
    f = AudioFile(root_id=r.id, path=f"{LIB}/a.flac", ext=".flac", size_bytes=1,
                  hash_method="stream", status="present", location="library")
    db.add(f)
    db.flush()
    t = Track(source_type="manual", has_local_file=True, local_path=f"{LIB}/a.flac",
              primary_file_id=f.id)
    db.add(t)
    db.commit()

    stacca_file(db, f.id)
    db.delete(f)
    db.commit()

    assert _orfane(db) == []
    assert db.get(Track, t.id).primary_file_id is None
