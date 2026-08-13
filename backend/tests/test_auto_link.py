"""Proposta di auto-collegamento file-locale per le tracce da sistemare."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import Track
from app.services.auto_link import auto_link_preview


def _seed_pending(db):
    db.add(Track(platform="spotify", spotify_id="a1", source_type="spotify",
                 artist="Daft Punk", title="Da Funk",
                 last_download_outcome="not_found", has_local_file=False))
    db.add(Track(platform="spotify", spotify_id="a2", source_type="spotify",
                 artist="Nobody", title="Nowhere",
                 last_download_outcome="failed", has_local_file=False))
    db.commit()


def test_auto_link_preview_propone_solo_i_match(db, tmp_path, monkeypatch):
    (tmp_path / "Daft Punk - Da Funk.mp3").write_bytes(b"x")
    (tmp_path / "roba a caso.mp3").write_bytes(b"x")
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    _seed_pending(db)

    props = auto_link_preview(db)
    by = {p["title"]: p for p in props}
    assert by["Da Funk"]["hit"]["name"] == "Daft Punk - Da Funk.mp3"
    assert by["Da Funk"]["hit"]["source"] == "library"
    assert by["Nowhere"]["hit"] is None  # nessun file combacia


def test_auto_link_preview_label_format_with_fallback(db, tmp_path, monkeypatch):
    """Caratterizza il campo 'label' ('Artista — Titolo', em dash) esposto da
    auto_link_preview, fallback compreso quando artista/titolo mancano."""
    from app.models import Track
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    db.add(Track(platform="spotify", spotify_id="a3", source_type="spotify",
                 artist="Daft Punk", title="Da Funk",
                 last_download_outcome="not_found", has_local_file=False))
    db.add(Track(platform="spotify", spotify_id="a4", source_type="spotify",
                 artist=None, title=None,
                 last_download_outcome="not_found", has_local_file=False))
    db.commit()

    props = auto_link_preview(db)
    by_artist = {p["artist"]: p for p in props}
    assert by_artist["Daft Punk"]["label"] == "Daft Punk — Da Funk"
    assert by_artist[None]["label"] == "Artista sconosciuto — Senza titolo"


def test_auto_link_endpoint(tmp_path, monkeypatch):
    (tmp_path / "Daft Punk - Da Funk.flac").write_bytes(b"x")
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    monkeypatch.setattr(settings, "slskd_download_dir", "")

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    _seed_pending(session)
    app.dependency_overrides[get_db] = lambda: session
    try:
        client = TestClient(app)
        r = client.get("/api/downloads/auto-link")
        assert r.status_code == 200
        body = r.json()
        assert any(p["hit"] and p["hit"]["name"] == "Daft Punk - Da Funk.flac" for p in body)
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
