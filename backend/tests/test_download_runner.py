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


# --- Fase e byte per-traccia -------------------------------------------------
#
# La fascia "in corso" della pagina /downloads e' la ragione d'essere della
# pagina: senza queste scritture un FLAC da un peer lento resta «Ricerca…» per
# venti minuti, senza barra.


def _spia_progressi(monkeypatch):
    scritte: list[tuple] = []
    monkeypatch.setattr(
        runner.queue, "set_progress",
        lambda db, item_id, phase, bytes_done=None, bytes_total=None:
            scritte.append((phase, bytes_done, bytes_total)))
    return scritte


def test_progress_writer_scrive_solo_quando_la_barra_si_muove(monkeypatch):
    """Il poll gira ogni due secondi per worker: scrivere ad ogni giro sarebbe
    una commit ogni due secondi per ridisegnare la stessa barra."""
    scritte = _spia_progressi(monkeypatch)
    write = runner._progress_writer(None, 1)
    write("downloading", 0, 1000)
    write("downloading", 5, 1000)     # sempre 0%: niente
    write("downloading", 9, 1000)     # sempre 0%: niente
    write("downloading", 20, 1000)    # 2%: si vede
    write("downloading", 1000, 1000)  # 100%: si vede
    assert scritte == [
        ("downloading", 0, 1000), ("downloading", 20, 1000),
        ("downloading", 1000, 1000),
    ]


def test_progress_writer_senza_totale_usa_un_salto_assoluto(monkeypatch):
    """slskd non espone sempre la dimensione: senza totale non c'e' percentuale
    su cui ragionare, si guarda quanto e' avanzato in assoluto."""
    scritte = _spia_progressi(monkeypatch)
    write = runner._progress_writer(None, 1)
    write("downloading", 0, None)
    write("downloading", 1000, None)                      # meno di un mega: niente
    write("downloading", 4 * 1024 * 1024, None)           # quattro mega: si vede
    assert scritte == [("downloading", 0, None), ("downloading", 4 * 1024 * 1024, None)]


def test_progress_writer_scrive_sempre_un_cambio_di_fase(monkeypatch):
    """Il cambio di fase non passa dalla soglia: e' l'informazione principale."""
    scritte = _spia_progressi(monkeypatch)
    write = runner._progress_writer(None, 1)
    write("searching")
    write("downloading", 0, None)
    assert scritte == [("searching", None, None), ("downloading", 0, None)]


def test_progress_writer_scrive_davvero_sull_item(factory):
    """Senza spie: la riga sul DB deve portare fase e byte, perche' e' quella
    che l'endpoint della coda serve alla pagina."""
    item_id, _ = _queued(factory)
    db = factory()
    write = runner._progress_writer(db, item_id)
    write("downloading", 512, 1024)
    item = factory().get(DownloadQueueItem, item_id)
    assert (item.phase, item.bytes_done, item.bytes_total) == ("downloading", 512, 1024)


def test_download_candidate_dichiara_la_fase_prima_di_attendere(monkeypatch):
    """L'attesa e' la parte che dura: la fase va scritta prima di entrarci, non
    dopo esserne usciti."""
    from app.integrations.slskd import SlskdFile

    monkeypatch.setattr(runner, "POLL_INTERVAL", 0.0)
    fasi_viste_dal_poll = []
    progressi: list[tuple] = []

    class _Client:
        def enqueue_download(self, file):
            pass

        def transfer_state(self, username, filename):
            fasi_viste_dal_poll.append(list(progressi))
            return {"id": "t1", "state": "Completed, Succeeded"}

    file = SlskdFile(username="u", filename="X.flac", size=4000, bitrate=None,
                     length=None, has_free_slot=True, queue_length=0)
    runner._download_candidate(_Client(), "/nessuna-cartella", file,
                               on_progress=lambda *a: progressi.append(a))
    assert progressi[0] == ("downloading", 0, 4000)
    # Al primo giro di poll la fase era gia' scritta.
    assert fasi_viste_dal_poll[0] == [("downloading", 0, 4000)]


def test_wait_for_download_riporta_i_byte_letti_dal_poll(monkeypatch):
    """I byte arrivano dallo stesso `bytesTransferred` gia' letto per rilevare
    lo stallo: nessuna chiamata in piu' al daemon."""
    from app.integrations.slskd import SlskdFile

    monkeypatch.setattr(runner, "POLL_INTERVAL", 0.0)
    stati = [
        {"id": "t1", "state": "InProgress", "bytesTransferred": 100},
        {"id": "t1", "state": "InProgress", "bytesTransferred": 900},
        {"id": "t1", "state": "Completed, Succeeded"},
    ]
    progressi: list[tuple] = []

    class _Client:
        def transfer_state(self, username, filename):
            return stati.pop(0)

    file = SlskdFile(username="u", filename="X.flac", size=1000, bitrate=None,
                     length=None, has_free_slot=True, queue_length=0)
    outcome, _ = runner._wait_for_download(_Client(), file,
                                            on_progress=lambda *a: progressi.append(a))
    assert outcome == "completed"
    assert progressi == [("downloading", 100, 1000), ("downloading", 900, 1000)]


def test_soundcloud_dichiara_la_fase_di_download(factory, monkeypatch):
    """yt-dlp non riporta avanzamento, ma la fase si puo' dire lo stesso:
    meglio «scarico» senza barra che «Ricerca…» per tutta la durata."""
    item_id, _ = _queued(factory, kind="soundcloud")
    scritte = _spia_progressi(monkeypatch)
    monkeypatch.setattr(runner, "download_track_audio", lambda url, d: "/dl/x.mp3")
    monkeypatch.setattr(runner, "read_audio_quality",
                        lambda p: {"format": "mp3", "bitrate": 320})
    monkeypatch.setattr(runner, "attach_local_file",
                        lambda db, track, **kw: track)
    runner.run_item(item_id)
    assert ("downloading", None, None) in scritte


# --- Risoluzione del file scaricato -----------------------------------------
#
# Con un download alla volta bastava il basename; con tre worker sulla stessa
# cartella condivisa il piu' recente e' spesso di un altro, e agganciare il file
# sbagliato non e' cosmetico: `attach_local_file` puo' fondere due tracce
# distinte cancellandone una.


def _scrivi(root, rel: str, *, mtime: float | None = None):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    if mtime is not None:
        import os
        os.utime(p, (mtime, mtime))
    return p


def test_resolve_preferisce_il_percorso_remoto_al_file_piu_recente(tmp_path):
    """Due worker, stesso basename: quello dell'altro e' piu' recente, ma il
    percorso remoto del candidato dice quale e' il proprio."""
    mio = _scrivi(tmp_path, "bob/Album X/A1.flac", mtime=1000)
    _scrivi(tmp_path, "alice/Album Y/A1.flac", mtime=9000)  # piu' recente, di un altro
    got = runner._resolve_local_path(str(tmp_path), "bob\\Album X\\A1.flac")
    assert got == str(mio.resolve())


def test_resolve_ignora_maiuscole_nel_percorso(tmp_path):
    """I peer Soulseek sono spesso Windows: il confronto non puo' essere
    sensibile alle maiuscole."""
    mio = _scrivi(tmp_path, "bob/album x/A1.flac", mtime=1000)
    _scrivi(tmp_path, "alice/Album Y/A1.flac", mtime=9000)
    got = runner._resolve_local_path(str(tmp_path), "bob\\Album X\\A1.flac")
    assert got == str(mio.resolve())


def test_resolve_preferisce_il_file_comparso_dopo_l_inizio(tmp_path):
    """Quando il percorso non distingue (slskd appiattisce la cartella), a
    parita' di tutto vince il file comparso durante questo lavoro."""
    _scrivi(tmp_path, "vecchio/A1.flac", mtime=1000)
    nuovo = _scrivi(tmp_path, "nuovo/A1.flac", mtime=5000)
    got = runner._resolve_local_path(str(tmp_path), "bob\\A1.flac", started_at=4000)
    assert got == str(nuovo.resolve())


def test_resolve_non_dichiara_mancante_un_file_troppo_vecchio(tmp_path):
    """L'ora d'inizio e' una preferenza, non un filtro: se slskd conservasse
    l'mtime del peer, filtrare darebbe "file_missing" su un file che c'e'."""
    unico = _scrivi(tmp_path, "bob/A1.flac", mtime=1000)
    got = runner._resolve_local_path(str(tmp_path), "bob\\A1.flac", started_at=9999)
    assert got == str(unico.resolve())


def test_resolve_senza_corrispondenze_resta_none(tmp_path):
    assert runner._resolve_local_path(str(tmp_path), "bob\\assente.flac") is None


def test_download_candidate_non_aggancia_il_file_di_un_altro_worker(tmp_path, monkeypatch):
    """Il giro intero: il candidato porta con se' il proprio percorso remoto,
    e il file agganciato e' il suo anche se un altro worker ne ha appena
    depositato uno omonimo."""
    from app.integrations.slskd import SlskdFile

    monkeypatch.setattr(runner, "POLL_INTERVAL", 0.0)
    mio = _scrivi(tmp_path, "bob/Album X/01 Intro.mp3", mtime=1000)
    _scrivi(tmp_path, "alice/Album Y/01 Intro.mp3", mtime=9000)

    class _Client:
        def enqueue_download(self, file):
            pass

        def transfer_state(self, username, filename):
            return {"id": "t1", "state": "Completed, Succeeded"}

    file = SlskdFile(username="bob", filename="bob\\Album X\\01 Intro.mp3", size=1,
                     bitrate=None, length=None, has_free_slot=True, queue_length=0)
    path, reason = runner._download_candidate(_Client(), str(tmp_path), file)
    assert reason is None
    assert path == str(mio.resolve())


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
