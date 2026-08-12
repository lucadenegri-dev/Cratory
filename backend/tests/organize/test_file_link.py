"""Derivazione della collocazione e manutenzione degli agganci."""

import pytest

from app.models import Track
from app.organize.models import AudioFile, ScanRoot
from app.organize.services.file_link import aggiorna_primary, deriva_location, stacca_file

LIB = "/Users/x/Music/Library"
INBOX = "/Users/x/Music/Downloads"


def test_deriva_location_library():
    assert deriva_location(f"{LIB}/Techno/a.flac", library_root=LIB, inbox_root=INBOX) == "library"


def test_deriva_location_inbox():
    assert deriva_location(f"{INBOX}/pack/b.mp3", library_root=LIB, inbox_root=INBOX) == "inbox"


def test_deriva_location_rifiuta_i_path_fuori_dalle_radici():
    with pytest.raises(ValueError, match="fuori"):
        deriva_location("/altrove/c.flac", library_root=LIB, inbox_root=INBOX)


def test_deriva_location_non_si_fa_ingannare_da_un_prefisso_parziale():
    """`/Music/LibraryVecchia` non sta dentro `/Music/Library`."""
    with pytest.raises(ValueError):
        deriva_location(f"{LIB}Vecchia/d.flac", library_root=LIB, inbox_root=INBOX)


@pytest.fixture()
def radice(db):
    r = ScanRoot(path=LIB)
    db.add(r)
    db.flush()
    return r


def test_aggiorna_primary_collega_traccia_e_file(db, radice):
    t = Track(source_type="manual", has_local_file=True, local_path=f"{LIB}/a.flac")
    f = AudioFile(root_id=radice.id, path=f"{LIB}/a.flac", ext=".flac", size_bytes=1,
                  hash_method="stream", status="present", location="library")
    db.add_all([t, f])
    db.flush()

    aggiorna_primary(db, t)
    db.flush()

    assert t.primary_file_id == f.id
    assert db.get(AudioFile, f.id).track_id == t.id


def test_aggiorna_primary_azzera_se_il_file_non_e_indicizzato(db, radice):
    t = Track(source_type="manual", has_local_file=True, local_path=f"{LIB}/mai-visto.flac",
              primary_file_id=None)
    db.add(t)
    db.flush()

    aggiorna_primary(db, t)
    assert t.primary_file_id is None


def test_stacca_file_azzera_le_tracce_che_lo_puntano(db, radice):
    f = AudioFile(root_id=radice.id, path=f"{LIB}/a.flac", ext=".flac", size_bytes=1,
                  hash_method="stream", status="present", location="library")
    db.add(f)
    db.flush()
    t = Track(source_type="manual", has_local_file=True, local_path=f"{LIB}/a.flac",
              primary_file_id=f.id)
    db.add(t)
    db.flush()

    toccate = stacca_file(db, f.id)
    db.flush()
    db.refresh(t)

    assert toccate == 1
    assert t.primary_file_id is None
    # has_local_file NON viene toccato: dire se la traccia è posseduta è
    # compito dell'indicizzazione libreria, non di questo helper.
    assert t.has_local_file is True
