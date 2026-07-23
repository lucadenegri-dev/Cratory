from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Track
from app.services import soulseek_download_job as job
from app.integrations.soundcloud_audio import SoundCloudAudioError


def _factory_with_track():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    factory = sessionmaker(bind=e, expire_on_commit=False)
    db = factory()
    t = Track(source_type="soundcloud", platform="soundcloud",
              url="https://soundcloud.com/a/b", title="B", artist="A")
    db.add(t)
    db.commit()
    return factory, t.id


def test_run_soundcloud_success(monkeypatch):
    factory, track_id = _factory_with_track()
    monkeypatch.setattr(job, "SessionLocal", factory)
    monkeypatch.setattr(job, "download_track_audio", lambda url, d: "/dl/A - B.mp3")
    monkeypatch.setattr(job, "read_audio_quality", lambda p: {"format": "mp3", "bitrate": 245})
    linked = {}

    def _fake_attach(db, track, *, path, fmt, bitrate):
        track.has_local_file = True
        linked.update(path=path, fmt=fmt, bitrate=bitrate)

    monkeypatch.setattr(job, "attach_local_file", _fake_attach)

    job._state.update(status="running")
    job._run_soundcloud(track_id)

    assert job._state["status"] == "done"
    assert job._state["downloaded"] == 1
    assert linked == {"path": "/dl/A - B.mp3", "fmt": "mp3", "bitrate": 245}
    db = factory()
    tr = db.get(Track, track_id)
    assert tr.has_local_file is True
    assert tr.last_download_outcome == "downloaded"


def test_run_soundcloud_failure(monkeypatch):
    factory, track_id = _factory_with_track()
    monkeypatch.setattr(job, "SessionLocal", factory)

    def _boom(url, d):
        raise SoundCloudAudioError("boom")

    monkeypatch.setattr(job, "download_track_audio", _boom)
    called = {"attach": False}
    monkeypatch.setattr(job, "attach_local_file",
                        lambda *a, **k: called.update(attach=True))

    job._state.update(status="running")
    job._run_soundcloud(track_id)

    assert job._state["status"] == "done"
    assert job._state["failed"] == 1
    assert called["attach"] is False
    db = factory()
    tr = db.get(Track, track_id)
    assert tr.has_local_file is False
    assert tr.last_download_outcome == "failed"
