"""Endpoint miniatura: embedded → proposta provider → 404."""

import io
import os

from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import settings
from app.organize.integrations import tagio
from app.main import app
from app.organize.models import AudioFile, ScanRoot
from app.organize.services import cover_cache


def _jpeg(color=(10, 200, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), color).save(buf, format="JPEG")
    return buf.getvalue()


def _seed(db, path: str, *, has_cover: bool, file_id: int = 1) -> None:
    db.add(ScanRoot(id=1, path="/m", label="M"))
    db.add(AudioFile(id=file_id, root_id=1, path=path, ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=has_cover))
    db.commit()


def test_thumb_from_embedded_cover(db, copy_fixture, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thumb_cache_dir", str(tmp_path / "tc"))
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_cover(f, _jpeg())
    _seed(db, f, has_cover=True)

    with TestClient(app) as client:
        r = client.get("/api/organize/files/1/thumb")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(r.content)).format == "JPEG"


def test_thumb_falls_back_to_provider_proposal(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thumb_cache_dir", str(tmp_path / "tc"))
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    _seed(db, "/m/senza-cover.flac", has_cover=False)
    cover_cache.save_thumb(1, b"\xff\xd8proposta")

    with TestClient(app) as client:
        r = client.get("/api/organize/files/1/thumb")
    assert r.status_code == 200
    assert r.content == b"\xff\xd8proposta"


def test_thumb_404_when_nothing_available(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thumb_cache_dir", str(tmp_path / "tc"))
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    _seed(db, "/m/senza-cover.flac", has_cover=False)

    with TestClient(app) as client:
        r = client.get("/api/organize/files/1/thumb")
    assert r.status_code == 404
    # ISSUES/DUPLICATES/PLAN non passano cover_source: ogni riga senza cover
    # rifà questa richiesta a ogni mount, un max-age corto la smorza.
    assert "max-age" in r.headers["cache-control"]


def test_thumb_404_for_unknown_file(db):
    with TestClient(app) as client:
        assert client.get("/api/organize/files/999/thumb").status_code == 404


def test_thumb_does_not_open_file_when_has_cover_is_false(db, tmp_path, monkeypatch):
    """has_cover=False è la cache negativa: il file non va nemmeno aperto."""
    monkeypatch.setattr(settings, "thumb_cache_dir", str(tmp_path / "tc"))
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    _seed(db, "/m/senza-cover.flac", has_cover=False)

    def _boom(*a, **kw):
        raise AssertionError("get_thumb non deve essere chiamata")

    from app.organize.routers import library
    monkeypatch.setattr(library.thumbs, "get_thumb", _boom)

    with TestClient(app) as client:
        assert client.get("/api/organize/files/1/thumb").status_code == 404


def test_thumb_304_on_matching_etag(db, copy_fixture, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thumb_cache_dir", str(tmp_path / "tc"))
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_cover(f, _jpeg())
    _seed(db, f, has_cover=True)

    with TestClient(app) as client:
        first = client.get("/api/organize/files/1/thumb")
        again = client.get("/api/organize/files/1/thumb",
                           headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    assert again.content == b""


def test_thumb_200_with_new_etag_after_mtime_change(db, copy_fixture, tmp_path, monkeypatch):
    """L'altra metà del contratto ETag: quando l'mtime del file audio cambia
    (un apply che riscrive i tag, per esempio) il vecchio If-None-Match non
    deve più bastare — l'utente deve ricevere la copertina aggiornata, non un
    304 con l'immagine superata."""
    monkeypatch.setattr(settings, "thumb_cache_dir", str(tmp_path / "tc"))
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_cover(f, _jpeg())
    _seed(db, f, has_cover=True)

    with TestClient(app) as client:
        first = client.get("/api/organize/files/1/thumb")
        etag = first.headers["etag"]

        future = os.path.getmtime(f) + 10
        os.utime(f, (future, future))

        again = client.get("/api/organize/files/1/thumb", headers={"If-None-Match": etag})
    assert again.status_code == 200
    assert again.headers["etag"] != etag


def test_thumb_etag_folds_in_cover_cache_mtime(db, tmp_path, monkeypatch):
    """Sul fallback (has_cover=False) i byte vengono da cover_cache/{id}.jpg:
    'importa metadati dal provider' può sovrascrivere quel file senza toccare
    l'audio, quindi il suo mtime deve entrare nello stamp — altrimenti un
    client con l'ETag vecchio riceverebbe un 304 con l'immagine superata."""
    monkeypatch.setattr(settings, "thumb_cache_dir", str(tmp_path / "tc"))
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    _seed(db, "/m/senza-cover.flac", has_cover=False)
    cover_cache.save_thumb(1, b"\xff\xd8prima")

    with TestClient(app) as client:
        first = client.get("/api/organize/files/1/thumb")
        etag = first.headers["etag"]

        cover_cache.save_thumb(1, b"\xff\xd8seconda")
        future = os.path.getmtime(cover_cache.thumb_path(1)) + 10
        os.utime(cover_cache.thumb_path(1), (future, future))

        again = client.get("/api/organize/files/1/thumb", headers={"If-None-Match": etag})
    assert again.status_code == 200
    assert again.headers["etag"] != etag
    assert again.content == b"\xff\xd8seconda"
