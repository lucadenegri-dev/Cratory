import math
import struct
import wave

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.integrations.slskd import SlskdFile
from app.models import Track
from app.services import soulseek_download_job as job


def _write_wav(path, *, freq=440, secs=0.2, rate=22050):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(
            struct.pack("<h", int(30000 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(int(rate * secs))
        ))


class _FakeClient:
    """slskd fake: ritorna un file lossless e un transfer subito completo."""

    def __init__(self, filename):
        self._filename = filename
        self.enqueued = []

    def search(self, artist, title, **kw):
        return [SlskdFile(username="bob", filename=self._filename, size=10,
                          bitrate=None, length=None, has_free_slot=True, queue_length=0)]

    def enqueue_download(self, file):
        self.enqueued.append(file)

    def transfer_state(self, username, filename):
        return {"filename": filename, "state": "Completed, Succeeded"}


@pytest.fixture()
def patch_job(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    # download dir con il file gia' presente (simula slskd che ha scaricato)
    download_dir = tmp_path / "dl"
    download_dir.mkdir()
    _write_wav(download_dir / "Da Funk.flac")  # basename combacia col candidato
    monkeypatch.setattr(job, "SessionLocal", TestSession)
    monkeypatch.setattr(job.settings, "slskd_download_dir", str(download_dir))
    monkeypatch.setattr(job, "POLL_INTERVAL", 0.0)
    monkeypatch.setattr(job, "DOWNLOAD_TIMEOUT", 1.0)
    fake = _FakeClient("bob\\Da Funk.flac")
    monkeypatch.setattr(job, "get_slskd_client", lambda: fake)
    # reset stato globale (contatori e items sono cumulativi tra una chiamata
    # e l'altra di _run, quindi vanno azzerati esplicitamente a ogni test)
    job._state.update(status="idle", processed=0, total=0, downloaded=0,
                      needs_review=0, not_found=0, failed=0, items=[])
    return TestSession, fake


def test_track_job_downloads_and_links(patch_job):
    TestSession, fake = patch_job
    db = TestSession()
    t = Track(platform="spotify", spotify_id="s1", source_type="spotify",
              title="Da Funk", artist="Daft Punk")
    db.add(t)
    db.commit()
    track_id = t.id
    db.close()

    chosen = fake.search("Daft Punk", "Da Funk")[0]
    job._run([(track_id, chosen)], None)  # esegue in-thread (sincrono) per il test

    st = job.job_state()
    assert st["status"] == "done"
    assert st["downloaded"] == 1
    db = TestSession()
    t2 = db.get(Track, track_id)
    assert t2.has_local_file is True
    assert t2.local_format == "flac"
    db.close()


def test_playlist_auto_pick_uses_search(patch_job):
    TestSession, fake = patch_job
    db = TestSession()
    t = Track(platform="spotify", spotify_id="s2", source_type="spotify",
              title="Da Funk", artist="Daft Punk")
    db.add(t)
    db.commit()
    track_id = t.id
    db.close()

    job._run([(track_id, None)], playlist_id=99)  # None -> auto-pick via search
    st = job.job_state()
    assert st["downloaded"] == 1
    assert len(fake.enqueued) == 1


class _FallbackClient:
    """Due candidati: il primo utente fallisce il transfer, il secondo riesce."""

    def __init__(self):
        self.enqueued = []

    def search(self, artist, title, **kw):
        return [
            SlskdFile(username="baduser", filename="baduser\\Da Funk.flac", size=10,
                      bitrate=None, length=None, has_free_slot=True, queue_length=0),
            SlskdFile(username="gooduser", filename="gooduser\\Da Funk.flac", size=10,
                      bitrate=None, length=None, has_free_slot=True, queue_length=0),
        ]

    def enqueue_download(self, file):
        self.enqueued.append(file.username)

    def transfer_state(self, username, filename):
        state = "Completed, Errored" if username == "baduser" else "Completed, Succeeded"
        return {"state": state}


def test_fallback_tries_next_user_when_first_fails(patch_job, monkeypatch):
    TestSession, _ = patch_job
    client = _FallbackClient()
    monkeypatch.setattr(job, "get_slskd_client", lambda: client)
    db = TestSession()
    t = Track(platform="spotify", spotify_id="s3", source_type="spotify",
              title="Da Funk", artist="Daft Punk")
    db.add(t)
    db.commit()
    track_id = t.id
    db.close()

    job._run([(track_id, None)], None)
    st = job.job_state()
    assert st["downloaded"] == 1
    # prima ha provato baduser (fallito), poi e' passato a gooduser (riuscito)
    assert client.enqueued == ["baduser", "gooduser"]
    db = TestSession()
    assert db.get(Track, track_id).has_local_file is True
    db.close()
