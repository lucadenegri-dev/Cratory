from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db import Base
from app.main import app
from app.models import Track
from app.routers import downloads as downloads_router
from app.services import download_queue as q

client = TestClient(app)


def _factory():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    return sessionmaker(bind=e, expire_on_commit=False)


def _ok(monkeypatch):
    monkeypatch.setattr(downloads_router, "soundcloud_available", lambda: True)
    monkeypatch.setattr(downloads_router, "_ffmpeg_available", lambda: True)
    monkeypatch.setattr(settings, "slskd_download_dir", "/dl")
    monkeypatch.setattr(downloads_router, "fill", lambda: None)


def test_409_when_ytdlp_missing(monkeypatch):
    monkeypatch.setattr(downloads_router, "soundcloud_available", lambda: False)
    r = client.post("/api/downloads/track/soundcloud", json={"track_id": 1})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ytdlp_unavailable"


def test_409_when_ffmpeg_missing(monkeypatch):
    monkeypatch.setattr(downloads_router, "soundcloud_available", lambda: True)
    monkeypatch.setattr(downloads_router, "_ffmpeg_available", lambda: False)
    r = client.post("/api/downloads/track/soundcloud", json={"track_id": 1})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ffmpeg_unavailable"


def test_409_when_dir_not_configured(monkeypatch):
    monkeypatch.setattr(downloads_router, "soundcloud_available", lambda: True)
    monkeypatch.setattr(downloads_router, "_ffmpeg_available", lambda: True)
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    r = client.post("/api/downloads/track/soundcloud", json={"track_id": 1})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "download_dir_not_configured"


def test_404_when_track_missing(monkeypatch):
    _ok(monkeypatch)
    monkeypatch.setattr(downloads_router, "SessionLocal", _factory())
    r = client.post("/api/downloads/track/soundcloud", json={"track_id": 999})
    assert r.status_code == 404


def test_422_when_not_a_soundcloud_track(monkeypatch):
    _ok(monkeypatch)
    factory = _factory()
    db = factory()
    t = Track(source_type="spotify", platform="spotify", title="X", artist="Y")
    db.add(t)
    db.commit()
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    r = client.post("/api/downloads/track/soundcloud", json={"track_id": t.id})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "not_a_soundcloud_track"


def test_accoda_un_item_soundcloud(monkeypatch):
    """Il `kind` e' l'unica cosa che distingue questo download: dice al runner
    di passare da yt-dlp invece che da slskd."""
    _ok(monkeypatch)
    factory = _factory()
    db = factory()
    t = Track(source_type="soundcloud", platform="soundcloud",
              url="https://soundcloud.com/a/b", title="B", artist="A")
    db.add(t)
    db.commit()
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    r = client.post("/api/downloads/track/soundcloud", json={"track_id": t.id})
    assert r.status_code == 200
    assert r.json() == {"enqueued": 1, "skipped": 0, "replaced": 0}
    (item,) = q.list_items(factory())
    assert (item.track_id, item.kind) == (t.id, "soundcloud")
