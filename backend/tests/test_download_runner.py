import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import DownloadQueueItem, Track
from app.services import download_queue as q
from app.services import download_runner as runner


@pytest.fixture
def factory(monkeypatch):
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    f = sessionmaker(bind=e, expire_on_commit=False)
    monkeypatch.setattr(runner, "SessionLocal", f)
    return f


def _queued(factory, kind="soulseek_auto", payload=None):
    db = factory()
    t = Track(source_type="manual", artist="Aphex Twin", title="Xtal",
              duration_seconds=294)
    db.add(t)
    db.commit()
    q.enqueue(db, [t.id], kind=kind, payload=payload)
    item = q.claim_next(db)
    db.close()
    return item.id, t.id


def test_esito_scritto_su_item_e_su_traccia(factory, monkeypatch):
    """Regressione: i tab della wishlist leggono Track.last_download_outcome."""
    ids = _queued(factory)
    item_id, track_id = ids
    monkeypatch.setattr(runner, "_run_soulseek",
                        lambda db, item, track, chosen: ("downloaded", None, None))
    runner.run_item(item_id)
    db = factory()
    item = db.get(DownloadQueueItem, item_id)
    track = db.get(Track, track_id)
    assert (item.state, item.outcome) == ("done", "downloaded")
    assert track.last_download_outcome == "downloaded"


def test_needs_review_propaga_motivo_e_path(factory, monkeypatch):
    item_id, track_id = _queued(factory)
    monkeypatch.setattr(runner, "_run_soulseek",
                        lambda db, item, track, chosen: (
                            "needs_review", "durata non corrisponde", "/inbox/x.mp3"))
    runner.run_item(item_id)
    db = factory()
    item = db.get(DownloadQueueItem, item_id)
    track = db.get(Track, track_id)
    assert item.outcome == "needs_review"
    assert item.error == "durata non corrisponde"
    assert track.last_download_reason == "durata non corrisponde"
    assert track.last_download_path == "/inbox/x.mp3"


def test_un_eccezione_non_lascia_l_item_appeso(factory, monkeypatch):
    item_id, _ = _queued(factory)

    def boom(db, item, track, chosen):
        raise RuntimeError("daemon giu'")

    monkeypatch.setattr(runner, "_run_soulseek", boom)
    runner.run_item(item_id)          # non deve propagare
    db = factory()
    item = db.get(DownloadQueueItem, item_id)
    assert (item.state, item.outcome) == ("done", "failed")
    assert item.error


def test_item_annullato_prima_di_partire_non_scarica(factory, monkeypatch):
    item_id, _ = _queued(factory)
    db = factory()
    q.cancel(db, item_id)
    db.close()
    chiamato = []
    monkeypatch.setattr(runner, "_run_soulseek",
                        lambda *a: chiamato.append(1) or ("downloaded", None, None))
    runner.run_item(item_id)
    assert chiamato == []
    db = factory()
    assert db.get(DownloadQueueItem, item_id).state == "cancelled"


def test_soulseek_chosen_passa_il_candidato_dal_payload(factory, monkeypatch):
    cand = {"username": "u", "filename": "X.flac", "size": 1,
            "bitrate": None, "length": 294}
    item_id, _ = _queued(factory, kind="soulseek_chosen", payload=cand)
    visti = {}
    monkeypatch.setattr(runner, "_run_soulseek",
                        lambda db, item, track, chosen: visti.update(
                            username=chosen.username, filename=chosen.filename)
                        or ("downloaded", None, None))
    runner.run_item(item_id)
    assert visti == {"username": "u", "filename": "X.flac"}


def test_annullo_durante_il_lavoro_ferma_e_non_scrive_esito(factory, monkeypatch):
    """L'utente annulla mentre il worker sta gia' lavorando: l'item resta
    `cancelled` e la traccia NON riceve un esito (non e' andata male, e' stata
    fermata)."""
    item_id, track_id = _queued(factory)

    def annulla_a_meta(db, item, track, chosen):
        altra = factory()
        q.cancel(altra, item.id)
        altra.close()
        return "downloaded", None, None

    monkeypatch.setattr(runner, "_run_soulseek", annulla_a_meta)
    runner.run_item(item_id)
    db = factory()
    assert db.get(DownloadQueueItem, item_id).state == "cancelled"
    assert db.get(Track, track_id).last_download_outcome is None


def test_wait_for_download_si_arrende_se_l_item_viene_annullato(monkeypatch):
    """Il ciclo di attesa del transfer interroga `should_cancel` a ogni giro:
    senza questo, annullare una traccia in corso non avrebbe effetto fino alla
    fine del trasferimento."""
    from app.integrations.slskd import SlskdFile

    monkeypatch.setattr(runner, "POLL_INTERVAL", 0.01)
    cancellati = []

    class _Client:
        def transfer_state(self, username, filename):
            return {"id": "t1", "state": "InProgress", "bytesTransferred": 1}

        def cancel_download(self, username, transfer_id):
            cancellati.append(transfer_id)

    file = SlskdFile(username="u", filename="X.flac", size=1, bitrate=None,
                     length=None, has_free_slot=True, queue_length=0)
    outcome, reason = runner._wait_for_download(_Client(), file,
                                                should_cancel=lambda: True)
    assert outcome == "cancelled"
    assert cancellati == ["t1"]      # il transfer viene fermato anche su slskd
