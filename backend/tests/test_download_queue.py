from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import DownloadQueueItem, Track
from app.services import download_queue as q


def _db():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    return sessionmaker(bind=e, expire_on_commit=False)()


def _tracks(db, n):
    made = []
    for i in range(n):
        t = Track(source_type="manual", artist=f"A{i}", title=f"T{i}")
        db.add(t)
        made.append(t)
    db.commit()
    return made


def test_enqueue_crea_un_item_per_traccia_in_ordine():
    db = _db()
    tracks = _tracks(db, 3)
    added, skipped = q.enqueue(db, [t.id for t in tracks])
    assert (added, skipped) == (3, 0)
    items = q.list_items(db)
    assert [i.track_id for i in items] == [t.id for t in tracks]
    assert all(i.state == "queued" and i.outcome is None for i in items)
    assert all(i.kind == "soulseek_auto" for i in items)
    # position crescente e distinta: e' l'ordine della coda
    assert len({i.position for i in items}) == 3
    assert [i.position for i in items] == sorted(i.position for i in items)


def test_enqueue_non_duplica_una_traccia_gia_in_coda():
    db = _db()
    t = _tracks(db, 1)[0]
    q.enqueue(db, [t.id])
    added, skipped = q.enqueue(db, [t.id])
    assert (added, skipped) == (0, 1)
    assert len(q.list_items(db)) == 1


def test_enqueue_non_duplica_una_traccia_in_corso():
    db = _db()
    t = _tracks(db, 1)[0]
    q.enqueue(db, [t.id])
    db.query(DownloadQueueItem).update({"state": "running"})
    db.commit()
    added, skipped = q.enqueue(db, [t.id])
    assert (added, skipped) == (0, 1)


def test_enqueue_riaccoda_una_traccia_gia_finita():
    # done/cancelled non bloccano: e' proprio il caso "riprova".
    db = _db()
    t = _tracks(db, 1)[0]
    q.enqueue(db, [t.id])
    db.query(DownloadQueueItem).update({"state": "done", "outcome": "not_found"})
    db.commit()
    added, skipped = q.enqueue(db, [t.id])
    assert (added, skipped) == (1, 0)
    assert len(q.list_items(db)) == 2


def test_enqueue_conserva_kind_e_payload():
    db = _db()
    t = _tracks(db, 1)[0]
    cand = {"username": "u", "filename": "X.flac", "size": 1,
            "bitrate": None, "length": 300}
    q.enqueue(db, [t.id], kind="soulseek_chosen", payload=cand)
    item = q.list_items(db)[0]
    assert item.kind == "soulseek_chosen"
    assert item.payload_dict() == cand


def test_enqueue_ignora_track_id_inesistenti():
    db = _db()
    added, skipped = q.enqueue(db, [999])
    assert (added, skipped) == (0, 1)
    assert q.list_items(db) == []
