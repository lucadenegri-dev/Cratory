"""Il ramo SoundCloud (yt-dlp) dell'esecuzione di un item di coda.

Erano i test del ramo SoundCloud del vecchio job monolitico: la logica e' passata
invariata al runner, dove la scelta del ramo la fa il `kind` dell'item invece
di una funzione di avvio dedicata. Le asserzioni restano quelle di prima —
esito sull'item, possesso e esito sulla traccia — lette dal DB invece che da un
dizionario globale.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.integrations.soundcloud_audio import SoundCloudAudioError
from app.models import DownloadQueueItem, Track
from app.services import download_queue as q
from app.services import download_runner as job


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


def _esegui(factory, track_id) -> DownloadQueueItem:
    """Accoda un item `soundcloud`, lo rivendica e lo esegue. Ritorna l'item
    concluso: e' li' che vive l'esito che prima stava in `_state`."""
    db = factory()
    try:
        q.enqueue(db, [track_id], kind="soundcloud")
        item = q.claim_next(db)
        job.run_item(item.id)
        db.expire_all()
        return db.get(DownloadQueueItem, item.id)
    finally:
        db.close()


def test_run_soundcloud_success(monkeypatch):
    factory, track_id = _factory_with_track()
    monkeypatch.setattr(job, "SessionLocal", factory)
    monkeypatch.setattr(job, "download_track_audio", lambda url, d: "/dl/A - B.mp3")
    monkeypatch.setattr(job, "read_audio_quality", lambda p: {"format": "mp3", "bitrate": 245})
    linked = {}

    def _fake_attach(db, track, *, path, fmt, bitrate):
        track.has_local_file = True
        # Come la vera `attach_local_file`, che chiude con db.commit(): il
        # runner interroga l'annullo fra una fase e l'altra e quella lettura
        # scade la sessione, quindi un possesso lasciato solo in memoria non
        # arriverebbe mai al DB.
        db.commit()
        linked.update(path=path, fmt=fmt, bitrate=bitrate)

    monkeypatch.setattr(job, "attach_local_file", _fake_attach)

    item = _esegui(factory, track_id)

    assert (item.state, item.outcome) == ("done", "downloaded")
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

    item = _esegui(factory, track_id)

    assert (item.state, item.outcome) == ("done", "failed")
    assert item.error == "boom"
    assert called["attach"] is False
    db = factory()
    tr = db.get(Track, track_id)
    assert tr.has_local_file is False
    assert tr.last_download_outcome == "failed"


def test_run_soundcloud_partial_attach_failure_leaves_track_unowned(monkeypatch):
    factory, track_id = _factory_with_track()
    monkeypatch.setattr(job, "SessionLocal", factory)
    monkeypatch.setattr(job, "download_track_audio", lambda url, d: "/dl/A - B.mp3")
    monkeypatch.setattr(job, "read_audio_quality", lambda p: {"format": "mp3", "bitrate": 245})

    def _attach_then_fail(db, track, *, path, fmt, bitrate):
        track.has_local_file = True  # muta il possesso in memoria...
        raise RuntimeError("dedup/merge failure")  # ...poi fallisce

    monkeypatch.setattr(job, "attach_local_file", _attach_then_fail)

    item = _esegui(factory, track_id)

    assert (item.state, item.outcome) == ("done", "failed")
    db = factory()
    tr = db.get(Track, track_id)
    assert tr.has_local_file is False  # rollback: NON marcata posseduta
    assert tr.last_download_outcome == "failed"
