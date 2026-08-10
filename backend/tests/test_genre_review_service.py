"""Test del service di revisione generi (Task 1: colonna; Task 4: logica)."""

from app.models import AudioFile


def _file(db, fid, *, artist=None, title=None, genre=None, album=None,
          label=None, reviewed=None, path=None):
    f = AudioFile(id=fid, root_id=1, path=path or f"/m/{fid}.mp3", ext="mp3",
                  size_bytes=1, hash_method="file", status="present",
                  has_cover=False, artist=artist, title=title, genre=genre,
                  album=album, label=label, genre_reviewed_at=reviewed)
    db.add(f)
    db.commit()
    return f


def test_genre_reviewed_at_column_defaults_none(db):
    f = _file(db, 1, artist="ANNA", title="Hidden Beauties")
    assert f.genre_reviewed_at is None
