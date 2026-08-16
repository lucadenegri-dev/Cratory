from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.main import app
from app.routers import downloads as downloads_router

client = TestClient(app)


def _engine():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    return e, sessionmaker(bind=e, expire_on_commit=False)


def test_status_reports_unavailable_when_not_configured(monkeypatch):
    _, factory = _engine()
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: False)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    r = client.get("/api/downloads/status")
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_track_auto_accoda_invece_di_avviare_un_job(monkeypatch):
    from app.models import Track
    from app.routers import downloads as downloads_router
    from app.services import download_queue as q

    engine, factory = _engine()
    db = factory()
    t = Track(source_type="manual", title="Night Signal", artist="Voiron")
    db.add(t)
    db.commit()

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    monkeypatch.setattr(downloads_router, "fill", lambda: None)

    r = client.post("/api/downloads/track/auto", json={"track_id": t.id})
    assert r.status_code == 200
    assert r.json() == {"enqueued": 1, "skipped": 0}
    assert [i.kind for i in q.list_items(factory())] == ["soulseek_auto"]


def test_niente_piu_409_con_un_download_gia_in_corso(monkeypatch):
    """Il vincolo un-alla-volta e' sparito: accodare e' sempre lecito."""
    from app.models import Track
    from app.routers import downloads as downloads_router

    engine, factory = _engine()
    db = factory()
    a = Track(source_type="manual", title="A", artist="X")
    b = Track(source_type="manual", title="B", artist="Y")
    db.add_all([a, b])
    db.commit()

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    monkeypatch.setattr(downloads_router, "fill", lambda: None)

    assert client.post("/api/downloads/track/auto", json={"track_id": a.id}).status_code == 200
    assert client.post("/api/downloads/track/auto", json={"track_id": b.id}).status_code == 200


def test_status_conserva_la_forma_e_la_deriva_dalla_coda(monkeypatch):
    from app.models import Track
    from app.routers import downloads as downloads_router
    from app.services import download_queue as q

    engine, factory = _engine()
    db = factory()
    t = Track(source_type="manual", title="A", artist="X")
    db.add(t)
    db.commit()
    q.enqueue(db, [t.id])
    item = q.claim_next(db)
    q.finish(db, item.id, "downloaded")

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)

    body = client.get("/api/downloads/status").json()
    for key in ("available", "status", "processed", "total", "downloaded",
                "needs_review", "not_found", "failed", "items", "current_label"):
        assert key in body, f"la barra globale del frontend legge {key}"
    assert body["downloaded"] == 1
    assert body["total"] == 1
    assert body["status"] == "done"      # nessun item vivo


def test_status_espone_le_stesse_chiavi_del_vecchio_job(monkeypatch):
    """Contratto col frontend: ne' una chiave in piu' ne' una in meno.

    Le chiavi sono quelle che il vecchio `_state` del job monolitico esponeva
    (meno `started_at`/`finished_at`: il job le teneva e le serializzava
    anche lui, ma nessun consumatore le leggeva, quindi sono state lasciate
    cadere di proposito nel passaggio alla coda), piu' `available`.
    Un'aggiunta silenziosa qui non romperebbe nulla; una rimozione
    romperebbe la barra globale senza che un test se ne accorga.
    """
    _, factory = _engine()
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)

    body = client.get("/api/downloads/status").json()
    assert set(body) == {
        "available", "status", "processed", "total", "downloaded",
        "needs_review", "not_found", "failed", "playlist_id", "items",
        "error", "current_label",
    }
    # Coda vuota: la barra non deve mostrare nulla in corso.
    assert body["status"] == "idle"
    assert body["total"] == 0


def test_status_ignora_gli_annullati(monkeypatch):
    """La barra racconta il lavoro accodato, non lo storico ripulito."""
    from app.models import Track
    from app.services import download_queue as q

    _, factory = _engine()
    db = factory()
    a = Track(source_type="manual", title="A", artist="X")
    b = Track(source_type="manual", title="B", artist="Y")
    db.add_all([a, b])
    db.commit()
    q.enqueue(db, [a.id, b.id])
    items = q.list_items(db)
    q.cancel(db, items[0].id)

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)

    body = client.get("/api/downloads/status").json()
    assert body["total"] == 1          # l'annullato non conta nel denominatore
    assert body["processed"] == 0
    assert body["status"] == "running"  # resta un item in attesa


def test_status_racconta_solo_il_giro_corrente(monkeypatch):
    """Accodo 2, ne concludo 1: la barra dice 1 su 2 (non 1 su tutto lo storico)."""
    from app.models import Track
    from app.services import download_queue as q

    _, factory = _engine()
    db = factory()
    a = Track(source_type="manual", title="A", artist="X")
    b = Track(source_type="manual", title="B", artist="Y")
    db.add_all([a, b])
    db.commit()
    q.enqueue(db, [a.id, b.id])
    item = q.claim_next(db)
    q.finish(db, item.id, "downloaded")

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)

    body = client.get("/api/downloads/status").json()
    assert body["total"] == 2
    assert body["processed"] == 1


def test_status_un_nuovo_giro_non_eredita_lo_storico(monkeypatch):
    """La coda si svuota, poi accodo 1 nuovo: la barra dice 0 su 1, non 1 su 3
    (il rilievo: i contatori sommavano TUTTI gli item mai accodati e non
    annullati, non solo quelli del giro in corso)."""
    from app.models import Track
    from app.services import download_queue as q

    _, factory = _engine()
    db = factory()
    a = Track(source_type="manual", title="A", artist="X")
    b = Track(source_type="manual", title="B", artist="Y")
    c = Track(source_type="manual", title="C", artist="Z")
    db.add_all([a, b, c])
    db.commit()

    # Primo giro: 2 tracce, entrambe concluse -> la coda torna ferma.
    q.enqueue(db, [a.id, b.id])
    for _ in range(2):
        item = q.claim_next(db)
        q.finish(db, item.id, "downloaded")

    # Secondo giro: una sola traccia nuova, accodata a coda ferma.
    q.enqueue(db, [c.id])

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)

    body = client.get("/api/downloads/status").json()
    assert body["total"] == 1        # non 3: il primo giro non conta piu'
    assert body["processed"] == 0
    assert body["status"] == "running"  # il nuovo item e' in attesa


def test_status_a_coda_ferma_riporta_l_ultimo_giro_non_zero(monkeypatch):
    """A coda ferma dopo un giro concluso, la barra riporta i totali di
    QUEL giro — non zero (nulla di attivo) e non lo storico intero."""
    from app.models import Track
    from app.services import download_queue as q

    _, factory = _engine()
    db = factory()
    a = Track(source_type="manual", title="A", artist="X")
    b = Track(source_type="manual", title="B", artist="Y")
    db.add_all([a, b])
    db.commit()

    q.enqueue(db, [a.id, b.id])
    first = q.claim_next(db)
    q.finish(db, first.id, "downloaded")
    second = q.claim_next(db)
    q.finish(db, second.id, "not_found")
    # Coda ferma: nessun item queued/running.

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)

    body = client.get("/api/downloads/status").json()
    assert body["status"] == "done"
    assert body["total"] == 2
    assert body["processed"] == 2
    assert body["downloaded"] == 1
    assert body["not_found"] == 1


def test_status_mostra_l_etichetta_dell_item_in_corso(monkeypatch):
    from app.models import Track
    from app.services import download_queue as q

    _, factory = _engine()
    db = factory()
    t = Track(source_type="manual", title="Da Funk", artist="Daft Punk")
    db.add(t)
    db.commit()
    q.enqueue(db, [t.id])
    q.claim_next(db)

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)

    body = client.get("/api/downloads/status").json()
    assert body["status"] == "running"
    assert body["current_label"] == "Daft Punk — Da Funk"


def test_track_auto_404_when_track_missing(monkeypatch):
    from app.routers import downloads as downloads_router

    _, factory = _engine()
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    monkeypatch.setattr(downloads_router, "fill", lambda: None)

    r = client.post("/api/downloads/track/auto", json={"track_id": 999})
    assert r.status_code == 404


def test_track_auto_409_when_not_configured(monkeypatch):
    from app.routers import downloads as downloads_router
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: False)
    r = client.post("/api/downloads/track/auto", json={"track_id": 1})
    assert r.status_code == 409


def test_track_chosen_accoda_col_candidato_nel_payload(monkeypatch):
    """Il candidato scelto dall'utente viaggia nel payload dell'item: e' l'unico
    modo in cui il runner sa che NON deve rifare l'auto-pick."""
    from app.models import Track
    from app.services import download_queue as q

    _, factory = _engine()
    db = factory()
    t = Track(source_type="manual", title="Da Funk", artist="Daft Punk")
    db.add(t)
    db.commit()

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    monkeypatch.setattr(downloads_router, "fill", lambda: None)

    r = client.post("/api/downloads/track", json={
        "track_id": t.id,
        "candidate": {"username": "bob", "filename": "bob\\Da Funk.flac",
                      "size": 10, "bitrate": 320, "length": 300},
    })
    assert r.status_code == 200
    assert r.json() == {"enqueued": 1, "skipped": 0}
    (item,) = q.list_items(factory())
    assert item.kind == "soulseek_chosen"
    assert item.payload_dict()["username"] == "bob"
    assert item.payload_dict()["filename"] == "bob\\Da Funk.flac"


def test_playlist_accoda_solo_le_tracce_senza_file_locale(monkeypatch):
    from app.models import Playlist, Track, playlist_tracks
    from app.services import download_queue as q

    _, factory = _engine()
    db = factory()
    p = Playlist(platform="spotify", name="P")
    db.add(p)
    db.commit()
    manca = Track(source_type="manual", title="Manca", artist="A", has_local_file=False)
    ce = Track(source_type="manual", title="Ce l'ho", artist="A", has_local_file=True)
    db.add_all([manca, ce])
    db.commit()
    db.execute(playlist_tracks.insert(), [
        {"playlist_id": p.id, "track_id": manca.id, "position": 0},
        {"playlist_id": p.id, "track_id": ce.id, "position": 1},
    ])
    db.commit()

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    monkeypatch.setattr(downloads_router, "fill", lambda: None)

    r = client.post(f"/api/downloads/playlist/{p.id}")
    assert r.status_code == 200
    assert r.json() == {"enqueued": 1, "skipped": 0}
    assert [i.track_id for i in q.list_items(factory())] == [manca.id]


def test_accodare_due_volte_la_stessa_traccia_la_salta(monkeypatch):
    """La deduplica della coda risponde ai doppi click: il secondo e' `skipped`."""
    from app.models import Track

    _, factory = _engine()
    db = factory()
    t = Track(source_type="manual", title="A", artist="X")
    db.add(t)
    db.commit()

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    monkeypatch.setattr(downloads_router, "fill", lambda: None)

    first = client.post("/api/downloads/track/auto", json={"track_id": t.id})
    second = client.post("/api/downloads/track/auto", json={"track_id": t.id})
    assert first.json() == {"enqueued": 1, "skipped": 0}
    assert second.json() == {"enqueued": 0, "skipped": 1}


def test_niente_fill_se_non_si_e_accodato_nulla(monkeypatch):
    """Svegliare il pool senza lavoro nuovo e' solo rumore."""
    from app.models import Track

    _, factory = _engine()
    db = factory()
    t = Track(source_type="manual", title="A", artist="X")
    db.add(t)
    db.commit()

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    calls = {"n": 0}
    monkeypatch.setattr(downloads_router, "fill",
                        lambda: calls.update(n=calls["n"] + 1))

    client.post("/api/downloads/track/auto", json={"track_id": t.id})
    assert calls["n"] == 1
    client.post("/api/downloads/track/auto", json={"track_id": t.id})  # duplicato
    assert calls["n"] == 1
