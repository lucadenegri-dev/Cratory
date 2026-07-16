"""Player tracce possedute: sicurezza del path e endpoint di streaming."""
from pathlib import Path

from app.services.file_search import path_within_roots


def test_path_within_roots_accetta_file_dentro_la_root(tmp_path):
    f = tmp_path / "song.mp3"
    f.write_bytes(b"x")
    assert path_within_roots(f, [str(tmp_path)]) is True


def test_path_within_roots_rifiuta_file_fuori_dalla_root(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    outside = tmp_path / "secret.mp3"
    outside.write_bytes(b"x")
    assert path_within_roots(outside, [str(root)]) is False


def test_path_within_roots_rifiuta_traversal(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    outside = tmp_path / "secret.mp3"
    outside.write_bytes(b"x")
    traversal = root / ".." / "secret.mp3"
    assert path_within_roots(traversal, [str(root)]) is False


def test_path_within_roots_rifiuta_symlink_verso_esterno(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    outside = tmp_path / "secret.mp3"
    outside.write_bytes(b"x")
    link = root / "link.mp3"
    link.symlink_to(outside)
    assert path_within_roots(link, [str(root)]) is False


def test_path_within_roots_con_roots_vuota_e_falso(tmp_path):
    f = tmp_path / "song.mp3"
    f.write_bytes(b"x")
    assert path_within_roots(f, []) is False


import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import Track
from app.routers import tracks


def _owned_track(db, path: str) -> Track:
    t = Track(source_type="local_files", platform="local_files", platform_track_id="d1",
              title="T", artist="A", has_local_file=True, local_path=path)
    db.add(t)
    db.commit()
    return t


def test_audio_404_se_traccia_inesistente(db):
    with pytest.raises(HTTPException) as ei:
        tracks.get_track_audio(9999, db)
    assert ei.value.status_code == 404
    assert ei.value.detail["code"] == "track_not_found"


def test_audio_404_se_non_posseduta(db):
    t = Track(source_type="spotify", title="T", artist="A", has_local_file=False)
    db.add(t); db.commit()
    with pytest.raises(HTTPException) as ei:
        tracks.get_track_audio(t.id, db)
    assert ei.value.status_code == 404
    assert ei.value.detail["code"] == "track_no_local_file"


def test_audio_404_se_path_fuori_root(db, tmp_path, monkeypatch):
    root = tmp_path / "library"; root.mkdir()
    outside = tmp_path / "secret.mp3"; outside.write_bytes(b"data")
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    t = _owned_track(db, str(outside))
    with pytest.raises(HTTPException) as ei:
        tracks.get_track_audio(t.id, db)
    assert ei.value.status_code == 404
    assert ei.value.detail["code"] == "track_file_not_allowed"


def test_audio_404_se_file_mancante(db, tmp_path, monkeypatch):
    root = tmp_path / "library"; root.mkdir()
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    t = _owned_track(db, str(root / "ghost.mp3"))  # dentro root ma non esiste
    with pytest.raises(HTTPException) as ei:
        tracks.get_track_audio(t.id, db)
    assert ei.value.status_code == 404
    assert ei.value.detail["code"] == "track_file_missing"


@pytest.fixture()
def client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_audio_200_serve_il_file(client_db, tmp_path, monkeypatch):
    client, db = client_db
    root = tmp_path / "library"; root.mkdir()
    f = root / "song.mp3"; f.write_bytes(b"ABCDEFGHIJ")
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    t = _owned_track(db, str(f))
    r = client.get(f"/api/tracks/{t.id}/audio")
    assert r.status_code == 200
    assert r.content == b"ABCDEFGHIJ"
    assert r.headers["content-type"] == "audio/mpeg"


def test_audio_206_su_range_request(client_db, tmp_path, monkeypatch):
    client, db = client_db
    root = tmp_path / "library"; root.mkdir()
    f = root / "song.mp3"; f.write_bytes(b"ABCDEFGHIJ")
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    t = _owned_track(db, str(f))
    r = client.get(f"/api/tracks/{t.id}/audio", headers={"Range": "bytes=0-3"})
    assert r.status_code == 206
    assert r.content == b"ABCD"
    assert "content-range" in {k.lower() for k in r.headers}
