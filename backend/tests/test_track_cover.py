"""GET /api/tracks/{id}/cover: artwork embedded servito on-demand per le possedute.

Test diretti sulla funzione router (niente TestClient: stesso stile del progetto)."""
import subprocess

import pytest
from fastapi import HTTPException

from app.models import Track
from app.routers import tracks as tracks_router


def _flac_with_cover(path, *, data: bytes, mime: str = "image/png") -> None:
    from mutagen.flac import FLAC, Picture

    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=1", str(path), "-y"],
        check=True,
    )
    pic = Picture()
    pic.type = 3
    pic.mime = mime
    pic.data = data
    f = FLAC(str(path))
    f.add_picture(pic)
    f.save()


def test_cover_posseduta_ritorna_immagine(db, tmp_path):
    p = tmp_path / "x.flac"
    _flac_with_cover(p, data=b"\x89PNG\r\n\x1a\nIMG", mime="image/png")
    t = Track(source_type="local_files", has_local_file=True, local_path=str(p),
              title="X", artist="A")
    db.add(t); db.commit()

    resp = tracks_router.get_track_cover(t.id, db)
    assert resp.body == b"\x89PNG\r\n\x1a\nIMG"
    assert resp.media_type == "image/png"


def test_cover_traccia_non_posseduta_404(db):
    t = Track(source_type="spotify", has_local_file=False, title="Lead", artist="A")
    db.add(t); db.commit()
    with pytest.raises(HTTPException) as exc:
        tracks_router.get_track_cover(t.id, db)
    assert exc.value.status_code == 404


def test_cover_posseduta_senza_artwork_404(db, tmp_path):
    p = tmp_path / "x.flac"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=1", str(p), "-y"],
        check=True,
    )
    t = Track(source_type="local_files", has_local_file=True, local_path=str(p),
              title="X", artist="A")
    db.add(t); db.commit()
    with pytest.raises(HTTPException) as exc:
        tracks_router.get_track_cover(t.id, db)
    assert exc.value.status_code == 404
