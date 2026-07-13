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

    def close(self):
        pass


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
    monkeypatch.setattr(job, "STALL_TIMEOUT", 1.0)
    monkeypatch.setattr(job, "HARD_TIMEOUT", 1.0)
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

    def close(self):
        pass


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


def test_manual_download_lascia_il_file_senza_catalogare(patch_job):
    # Ricerca manuale (track_id None): scarica il file sul disco ma NON lo cataloga
    # in Cratory. Entra in libreria via Sortory (sposta in LIBRARY_ROOT) +
    # indicizzazione: niente playlist "Soulseek", niente traccia local_files qui.
    from sqlalchemy import select

    from app.models import Playlist, Track
    TestSession, fake = patch_job
    file = fake.search("", "")[0]  # bob\Da Funk.flac (il file esiste in download_dir)
    job._run([(None, file)], None)
    st = job.job_state()
    assert st["downloaded"] == 1  # download riuscito
    db = TestSession()
    assert db.scalars(select(Track).where(Track.platform == "local_files")).all() == []
    assert db.scalars(select(Playlist).where(Playlist.name == "Soulseek")).all() == []
    db.close()


def test_durata_incoerente_va_in_needs_review(patch_job):
    # Il file scaricato ha durata ~2s ma la traccia ne attende 300: quasi
    # certamente la versione sbagliata → resta in inbox, la Track NON e' posseduta.
    from pathlib import Path

    TestSession, fake = patch_job
    fake._filename = "bob\\Da Funk.wav"  # wav vero: mutagen sceglie il parser dall'estensione
    _write_wav(Path(job.settings.slskd_download_dir) / "Da Funk.wav", secs=2)
    db = TestSession()
    t = Track(platform="spotify", spotify_id="s9", source_type="spotify",
              title="Da Funk", artist="Daft Punk", duration_seconds=300)
    db.add(t)
    db.commit()
    track_id = t.id
    db.close()

    job._run([(track_id, None)], None)
    st = job.job_state()
    assert st["needs_review"] == 1
    assert st["downloaded"] == 0
    assert "durata" in (st["items"][0]["reason"] or "")
    db = TestSession()
    t2 = db.get(Track, track_id)
    assert t2.has_local_file is False
    # Il path del file dubbio è persistito per la revisione "Tieni comunque".
    assert t2.last_download_path is not None
    assert t2.last_download_path.endswith("Da Funk.wav")
    db.close()


def test_chosen_in_sottocartella_persiste_il_path(patch_job):
    # Scenario reale (track 127): candidato scelto dall'utente (chosen != None),
    # file in una sottocartella dell'inbox, durata incoerente → needs_review.
    # Il path del file dubbio DEVE essere persistito per la revisione.
    from pathlib import Path

    TestSession, fake = patch_job
    sub = Path(job.settings.slskd_download_dir) / "1998 - Love (Loved)"
    sub.mkdir()
    _write_wav(sub / "02. Love (Loved).wav", secs=2)  # 2s reali
    fake._filename = "bob\\1998 - Love (Loved)\\02. Love (Loved).wav"
    db = TestSession()
    t = Track(platform="spotify", spotify_id="sub1", source_type="spotify",
              title="Loved", artist="Luke Slater", duration_seconds=237)  # 237 vs 2 → mismatch
    db.add(t)
    db.commit()
    track_id = t.id
    db.close()

    chosen = fake.search("Luke Slater", "Loved")[0]
    job._run([(track_id, chosen)], None)  # chosen != None: percorso di start_track_job
    st = job.job_state()
    assert st["needs_review"] == 1
    db = TestSession()
    t2 = db.get(Track, track_id)
    assert t2.last_download_path is not None, "path NON persistito (bug)"
    assert t2.last_download_path.endswith("02. Love (Loved).wav")
    db.close()


def test_durata_coerente_viene_collegata(patch_job):
    from pathlib import Path

    TestSession, fake = patch_job
    fake._filename = "bob\\Da Funk.wav"
    _write_wav(Path(job.settings.slskd_download_dir) / "Da Funk.wav", secs=2)
    db = TestSession()
    t = Track(platform="spotify", spotify_id="s10", source_type="spotify",
              title="Da Funk", artist="Daft Punk", duration_seconds=2)
    db.add(t)
    db.commit()
    track_id = t.id
    db.close()

    job._run([(track_id, None)], None)
    st = job.job_state()
    assert st["downloaded"] == 1
    db = TestSession()
    t2 = db.get(Track, track_id)
    assert t2.has_local_file is True
    assert t2.last_download_path is None  # nessun residuo dopo il collegamento
    db.close()


def test_current_label_esposto_durante_la_lavorazione(patch_job):
    # La barra job del frontend mostra la traccia in lavorazione: lo stato
    # espone current_label ("Artista — Titolo") mentre si processa, None a riposo.
    TestSession, fake = patch_job
    seen = []
    orig_search = fake.search

    def search_and_capture(artist, title, **kw):
        seen.append(job.job_state().get("current_label"))
        return orig_search(artist, title, **kw)

    fake.search = search_and_capture
    db = TestSession()
    t = Track(platform="spotify", spotify_id="s11", source_type="spotify",
              title="Da Funk", artist="Daft Punk")
    db.add(t)
    db.commit()
    track_id = t.id
    db.close()

    job._run([(track_id, None)], None)
    assert seen == ["Daft Punk — Da Funk"]
    assert job.job_state()["current_label"] is None


def test_slskd_giu_ferma_il_job_con_errore_chiaro(patch_job, monkeypatch):
    # Daemon disconnesso dalla rete Soulseek: inutile macinare N tracce che
    # fallirebbero tutte uguali → il job si ferma con un errore leggibile.
    from app.integrations.slskd import SlskdError

    class DownClient:
        def search(self, artist, title, **kw):
            raise SlskdError('slskd 409: "must be connected (currently: Disconnected)"')

        def close(self):
            pass

    TestSession, _ = patch_job
    monkeypatch.setattr(job, "get_slskd_client", lambda: DownClient())
    db = TestSession()
    ids = []
    for i in range(2):
        t = Track(platform="spotify", spotify_id=f"down{i}", source_type="spotify",
                  title=f"T{i}", artist="A")
        db.add(t)
        db.commit()
        ids.append(t.id)
    db.close()

    job._run([(ids[0], None), (ids[1], None)], None)
    st = job.job_state()
    assert st["status"] == "error"
    assert "Disconnected" in (st["error"] or "")
    assert st["processed"] < 2  # si e' fermato alla prima, niente accanimento


# --- Auto-pick: confidenza valutata su tutti i candidati, non solo il primo ----


def _cand(username, *, score, confidence):
    from app.services.soulseek_select import ScoredCandidate
    f = SlskdFile(username=username, filename=f"{username}\\Da Funk.flac", size=10,
                  bitrate=None, length=None, has_free_slot=True, queue_length=0)
    return ScoredCandidate(file=f, name_score=0.5, quality_tier=3,
                           score=score, confidence=confidence)


def _make_track(TestSession, spotify_id):
    db = TestSession()
    t = Track(platform="spotify", spotify_id=spotify_id, source_type="spotify",
              title="Da Funk", artist="Daft Punk")
    db.add(t); db.commit(); track_id = t.id; db.close()
    return track_id


def test_auto_pick_preferisce_candidato_confidente_a_score_inferiore(patch_job, monkeypatch):
    # Il primo per score e' incerto (confidence sotto soglia) ma piu' in basso
    # c'e' un candidato affidabile: l'auto-pick deve scegliere QUELLO, non
    # arrendersi a needs_review guardando solo ranked[0].
    TestSession, fake = patch_job
    ranked = [_cand("topuser", score=150, confidence=0.5),
              _cand("gooduser", score=120, confidence=0.9)]
    monkeypatch.setattr(job, "search_candidates", lambda *a, **kw: ranked)
    track_id = _make_track(TestSession, "conf1")

    job._run([(track_id, None)], None)

    st = job.job_state()
    assert st["downloaded"] == 1
    assert st["needs_review"] == 0
    assert [f.username for f in fake.enqueued] == ["gooduser"]


def test_auto_pick_nessun_confidente_va_in_needs_review(patch_job, monkeypatch):
    # Nessun candidato sopra soglia: needs_review come prima, stesso motivo.
    TestSession, fake = patch_job
    ranked = [_cand("topuser", score=150, confidence=0.5),
              _cand("other", score=120, confidence=0.6)]
    monkeypatch.setattr(job, "search_candidates", lambda *a, **kw: ranked)
    track_id = _make_track(TestSession, "conf2")

    job._run([(track_id, None)], None)

    st = job.job_state()
    assert st["needs_review"] == 1
    assert st["items"][0]["reason"] == "confidenza sotto soglia per l'auto-pick"
    assert fake.enqueued == []


def test_auto_pick_primo_confidente_resta_scelto(patch_job, monkeypatch):
    # Il primo per score e' anche confidente: si sceglie lui (nessun cambio).
    TestSession, fake = patch_job
    ranked = [_cand("topuser", score=150, confidence=0.9),
              _cand("other", score=120, confidence=0.8)]
    monkeypatch.setattr(job, "search_candidates", lambda *a, **kw: ranked)
    track_id = _make_track(TestSession, "conf3")

    job._run([(track_id, None)], None)

    st = job.job_state()
    assert st["downloaded"] == 1
    assert [f.username for f in fake.enqueued] == ["topuser"]


def test_start_track_autopick_job_builds_correct_items(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        job, "_start",
        lambda items, pid: captured.update(items=items, playlist_id=pid) or {"status": "running"},
    )
    job.start_track_autopick_job(42)
    assert captured["items"] == [(42, None)]
    assert captured["playlist_id"] is None


def test_chosen_transfer_failed_sets_reason(patch_job, monkeypatch):
    TestSession, fake = patch_job

    class _Errored(_FakeClient):
        def transfer_state(self, username, filename):
            return {"state": "Completed, Errored"}

    client = _Errored("bob\\Da Funk.flac")
    monkeypatch.setattr(job, "get_slskd_client", lambda: client)
    db = TestSession()
    t = Track(platform="spotify", spotify_id="rf1", source_type="spotify",
              title="Da Funk", artist="Daft Punk")
    db.add(t); db.commit(); track_id = t.id; db.close()

    chosen = client.search("Daft Punk", "Da Funk")[0]
    job._run([(track_id, chosen)], None)

    db = TestSession(); t2 = db.get(Track, track_id)
    assert t2.last_download_outcome == "failed"
    assert t2.last_download_reason == "transfer_failed"
    db.close()


def test_enqueue_exception_sets_reason(patch_job, monkeypatch):
    TestSession, fake = patch_job

    class _NoEnqueue(_FakeClient):
        def enqueue_download(self, file):
            raise RuntimeError("boom")

    client = _NoEnqueue("bob\\Da Funk.flac")
    monkeypatch.setattr(job, "get_slskd_client", lambda: client)
    db = TestSession()
    t = Track(platform="spotify", spotify_id="rf2", source_type="spotify",
              title="Da Funk", artist="Daft Punk")
    db.add(t); db.commit(); track_id = t.id; db.close()

    chosen = client.search("Daft Punk", "Da Funk")[0]
    job._run([(track_id, chosen)], None)

    db = TestSession(); t2 = db.get(Track, track_id)
    assert t2.last_download_outcome == "failed"
    assert t2.last_download_reason == "enqueue_rejected"
    db.close()


def test_queue_timeout_sets_reason(patch_job, monkeypatch):
    TestSession, fake = patch_job
    monkeypatch.setattr(job, "QUEUE_PATIENCE", 0.0)  # pazienza esaurita subito

    class _Queued(_FakeClient):
        def transfer_state(self, username, filename):
            return {"state": "Queued, Remotely"}

    client = _Queued("bob\\Da Funk.flac")
    monkeypatch.setattr(job, "get_slskd_client", lambda: client)
    db = TestSession()
    t = Track(platform="spotify", spotify_id="rf3", source_type="spotify",
              title="Da Funk", artist="Daft Punk")
    db.add(t); db.commit(); track_id = t.id; db.close()

    chosen = client.search("Daft Punk", "Da Funk")[0]
    job._run([(track_id, chosen)], None)

    db = TestSession(); t2 = db.get(Track, track_id)
    assert t2.last_download_reason == "queue_timeout"
    db.close()


# --- A20: stall-detection su byte trasferiti invece del vecchio tetto fisso ---


class _ProgressClient:
    """Transfer InProgress con bytesTransferred crescente ad ogni poll, poi completa."""

    def __init__(self, completes_after: int):
        self.completes_after = completes_after
        self.calls = 0

    def transfer_state(self, username, filename):
        self.calls += 1
        if self.calls >= self.completes_after:
            return {"state": "Completed, Succeeded", "bytesTransferred": self.calls * 10}
        return {"state": "InProgress", "bytesTransferred": self.calls * 10}


class _StalledClient:
    """Transfer InProgress con bytesTransferred fermo: non completa mai."""

    def __init__(self):
        self.calls = 0

    def transfer_state(self, username, filename):
        self.calls += 1
        return {"state": "InProgress", "bytesTransferred": 500}


def _slskd_file():
    return SlskdFile(username="bob", filename="bob\\x.flac", size=10, bitrate=None,
                     length=None, has_free_slot=True, queue_length=0)


def test_wait_for_download_progresso_oltre_il_vecchio_tetto_180s(monkeypatch):
    # Transfer che scarica attivamente per ~200s (oltre il vecchio DOWNLOAD_TIMEOUT
    # fisso di 180s = 90 poll da 2s): con bytesTransferred crescente ad ogni poll
    # NON deve essere ucciso, deve arrivare a completamento.
    monkeypatch.setattr(job.time, "sleep", lambda s: None)  # niente attesa reale
    client = _ProgressClient(completes_after=100)  # 100 * POLL_INTERVAL(2.0) = 200s
    outcome, reason = job._wait_for_download(client, _slskd_file())
    assert outcome == "completed"
    assert reason is None
    assert client.calls == 100


def test_wait_for_download_stallo_senza_avanzamento_byte_va_in_timeout(monkeypatch):
    # bytesTransferred fermo per STALL_TIMEOUT: stesso esito di prima (timeout),
    # ma si arrende molto prima del tetto assoluto invece di aspettare inutilmente.
    monkeypatch.setattr(job.time, "sleep", lambda s: None)
    monkeypatch.setattr(job, "STALL_TIMEOUT", 4.0)  # 2 poll da 2.0s
    client = _StalledClient()
    outcome, reason = job._wait_for_download(client, _slskd_file())
    assert outcome == "failed"
    assert reason == "download_timeout"
    # si e' arreso dopo lo stallo, non ha macinato poll fino al tetto assoluto
    assert client.calls <= 3


def test_wait_for_download_rispetta_il_tetto_assoluto(monkeypatch):
    # Anche con byte sempre crescenti (mai in stallo), un tetto assoluto HARD_TIMEOUT
    # deve comunque far desistere prima o poi (lossless da peer lentissimi).
    monkeypatch.setattr(job.time, "sleep", lambda s: None)
    monkeypatch.setattr(job, "HARD_TIMEOUT", 6.0)  # 3 poll da 2.0s
    monkeypatch.setattr(job, "STALL_TIMEOUT", 3600.0)  # non deve essere lo stallo a scattare
    client = _ProgressClient(completes_after=10_000)  # non completa mai entro il tetto
    outcome, reason = job._wait_for_download(client, _slskd_file())
    assert outcome == "failed"
    assert reason == "download_timeout"
    assert client.calls == 3


# --- E6: annullamento best-effort dei transfer abbandonati nel daemon ---


class _StalledCancelClient:
    """InProgress fermo: mai completa. Espone id + cancel_download per verificare
    che l'abbandono lato job pulisca anche il transfer sul daemon slskd."""

    def __init__(self):
        self.calls = 0
        self.cancelled = []

    def transfer_state(self, username, filename):
        self.calls += 1
        return {"state": "InProgress", "bytesTransferred": 500, "id": "tid-stall"}

    def cancel_download(self, username, transfer_id):
        self.cancelled.append((username, transfer_id))


def test_stall_timeout_cancella_il_transfer_nel_daemon(monkeypatch):
    monkeypatch.setattr(job.time, "sleep", lambda s: None)
    monkeypatch.setattr(job, "STALL_TIMEOUT", 4.0)
    client = _StalledCancelClient()
    outcome, reason = job._wait_for_download(client, _slskd_file())
    assert outcome == "failed"
    assert reason == "download_timeout"
    assert client.cancelled == [("bob", "tid-stall")]


class _QueuedCancelClient:
    """Resta in coda oltre QUEUE_PATIENCE: mai in download attivo."""

    def __init__(self):
        self.cancelled = []

    def transfer_state(self, username, filename):
        return {"state": "Queued, Remotely", "id": "tid-queue"}

    def cancel_download(self, username, transfer_id):
        self.cancelled.append((username, transfer_id))


def test_queue_timeout_cancella_il_transfer_nel_daemon(monkeypatch):
    monkeypatch.setattr(job.time, "sleep", lambda s: None)
    monkeypatch.setattr(job, "QUEUE_PATIENCE", 2.0)
    client = _QueuedCancelClient()
    outcome, reason = job._wait_for_download(client, _slskd_file())
    assert outcome == "failed"
    assert reason == "queue_timeout"
    assert client.cancelled == [("bob", "tid-queue")]


class _HardTimeoutCancelClient:
    """bytesTransferred sempre crescente (mai in stallo): scade solo per HARD_TIMEOUT."""

    def __init__(self):
        self.calls = 0
        self.cancelled = []

    def transfer_state(self, username, filename):
        self.calls += 1
        return {"state": "InProgress", "bytesTransferred": self.calls * 10, "id": "tid-hard"}

    def cancel_download(self, username, transfer_id):
        self.cancelled.append((username, transfer_id))


def test_hard_timeout_cancella_il_transfer_nel_daemon(monkeypatch):
    monkeypatch.setattr(job.time, "sleep", lambda s: None)
    monkeypatch.setattr(job, "HARD_TIMEOUT", 6.0)
    monkeypatch.setattr(job, "STALL_TIMEOUT", 3600.0)
    client = _HardTimeoutCancelClient()
    outcome, reason = job._wait_for_download(client, _slskd_file())
    assert outcome == "failed"
    assert reason == "download_timeout"
    assert client.cancelled == [("bob", "tid-hard")]


def test_cancel_fallito_e_best_effort_non_ferma_il_job(monkeypatch):
    # Se il DELETE verso il daemon fallisce, l'esito timeout va comunque
    # restituito: la cancellazione e' un tentativo, non un requisito.
    monkeypatch.setattr(job.time, "sleep", lambda s: None)
    monkeypatch.setattr(job, "STALL_TIMEOUT", 4.0)

    class _CancelRaises(_StalledCancelClient):
        def cancel_download(self, username, transfer_id):
            raise RuntimeError("daemon irraggiungibile")

    client = _CancelRaises()
    outcome, reason = job._wait_for_download(client, _slskd_file())
    assert outcome == "failed"
    assert reason == "download_timeout"


def test_completed_transfer_non_viene_cancellato(monkeypatch):
    # Esito positivo: nessuna cancellazione, il transfer resta cosi' com'e'.
    class _Completes(_ProgressClient):
        def __init__(self):
            super().__init__(completes_after=2)
            self.cancelled = []

        def cancel_download(self, username, transfer_id):
            self.cancelled.append((username, transfer_id))

    monkeypatch.setattr(job.time, "sleep", lambda s: None)
    client = _Completes()
    outcome, reason = job._wait_for_download(client, _slskd_file())
    assert outcome == "completed"
    assert client.cancelled == []


def test_cascade_all_failed_surfaces_specific_reason(patch_job, monkeypatch):
    TestSession, _ = patch_job

    class _AllErrored:
        def __init__(self): self.enqueued = []
        def search(self, artist, title, **kw):
            return [
                SlskdFile(username="u1", filename="u1\\Da Funk.flac", size=10,
                          bitrate=None, length=None, has_free_slot=True, queue_length=0),
                SlskdFile(username="u2", filename="u2\\Da Funk.flac", size=10,
                          bitrate=None, length=None, has_free_slot=True, queue_length=0),
            ]
        def enqueue_download(self, file): self.enqueued.append(file.username)
        def transfer_state(self, username, filename):
            return {"state": "Completed, Errored"}
        def close(self): pass

    client = _AllErrored()
    monkeypatch.setattr(job, "get_slskd_client", lambda: client)
    db = TestSession()
    t = Track(platform="spotify", spotify_id="rf4", source_type="spotify",
              title="Da Funk", artist="Daft Punk")
    db.add(t); db.commit(); track_id = t.id; db.close()

    job._run([(track_id, None)], None)  # None -> cascata via search

    db = TestSession(); t2 = db.get(Track, track_id)
    assert t2.last_download_outcome == "failed"
    # La cascata riporta il motivo specifico dell'ultimo tentativo (piu' utile del
    # generico "all_candidates_failed", che resta come fallback per reason None).
    assert t2.last_download_reason == "transfer_failed"
    db.close()
