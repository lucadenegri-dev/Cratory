"""Gli endpoint di installazione ora guidano il download dei binari."""
import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.services import binary_installer as bi
from app.services import slskd_daemon as sd


@pytest.fixture(autouse=True)
def _pulisci():
    bi.reset()
    yield
    bi.reset()


def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_chiave_sconosciuta(db):
    assert _client(db).post("/api/setup/install/rm-rf").status_code == 400
    app.dependency_overrides.clear()


def test_piattaforma_senza_build(db, monkeypatch):
    monkeypatch.setattr(bi.binary_manifest, "platform_tag", lambda: "darwin-arm64")
    monkeypatch.setattr(bi, "spawn", lambda fn: fn())
    res = _client(db).post("/api/setup/install/ffmpeg")
    assert res.status_code == 202
    assert bi.status()["status"] == "error"
    app.dependency_overrides.clear()


def test_stato_esposto(db):
    body = _client(db).get("/api/setup/install/status").json()
    assert body["status"] == "idle"
    app.dependency_overrides.clear()


def test_slskd_in_esecuzione_blocca_la_reinstallazione(db, monkeypatch):
    """Finding B2: sostituire il binario mentre il demone lo sta eseguendo lo
    rende irraggiungibile a `stop()` (su Linux l'eseguibile del processo vivo
    legge come cancellato, la prova di proprietà non incrocia più). Il
    controllo vive qui, nel router che già coordina installer e demone, non
    dentro `binary_installer` — che importarlo creerebbe un ciclo, dato che
    `slskd_daemon` importa già `binary_installer`."""
    monkeypatch.setattr(sd, "owned_pid", lambda: 4242)

    def esplodi(key):
        raise AssertionError("non doveva nemmeno provare a installare")

    monkeypatch.setattr(bi, "start", esplodi)
    res = _client(db).post("/api/setup/install/slskd")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "slskd_running_cannot_install"
    app.dependency_overrides.clear()


def test_slskd_non_in_esecuzione_si_installa_normalmente(db, monkeypatch):
    monkeypatch.setattr(sd, "owned_pid", lambda: None)
    monkeypatch.setattr(bi, "spawn", lambda fn: None)  # non far girare l'installazione per davvero
    res = _client(db).post("/api/setup/install/slskd")
    assert res.status_code == 202
    app.dependency_overrides.clear()


def test_piattaforma_senza_gestione_demone_non_blocca_l_installazione_slskd(db, monkeypatch):
    """Su piattaforme senza `ps`/SIGKILL (Windows) `owned_pid()` solleva
    `UnsupportedPlatform`: Cratory non potrebbe comunque aver mai avviato un
    demone lì (vedi `slskd_daemon.UnsupportedPlatform`), quindi non c'è un
    demone nostro da proteggere."""
    def non_supportato():
        raise sd.UnsupportedPlatform("no")

    monkeypatch.setattr(sd, "owned_pid", non_supportato)
    monkeypatch.setattr(bi, "spawn", lambda fn: None)
    res = _client(db).post("/api/setup/install/slskd")
    assert res.status_code == 202
    app.dependency_overrides.clear()


def test_altro_componente_non_chiede_nulla_al_demone(db, monkeypatch):
    """La guardia riguarda solo `slskd`: chiedere a `owned_pid()` per ffmpeg
    o fpcalc non avrebbe senso e non deve nemmeno essere tentato."""
    def esplodi():
        raise AssertionError("non doveva controllare il demone per questo componente")

    monkeypatch.setattr(sd, "owned_pid", esplodi)
    monkeypatch.setattr(bi, "spawn", lambda fn: None)
    res = _client(db).post("/api/setup/install/fpcalc")
    assert res.status_code == 202
    app.dependency_overrides.clear()


def test_checksum_sbagliato_riporta_un_codice_di_errore_distinto(db, monkeypatch):
    """Finding C: un hash che non torna non è un intoppo di rete come gli
    altri — il frontend deve poterlo distinguere da un fallimento generico
    per mostrare l'allarme del design doc §7, non il messaggio piatto di
    sempre. `error_code` è il canale: un valore preciso, non solo "c'è stato
    un errore"."""
    def rompi(key, **kw):
        raise bi.ChecksumMismatch("atteso aaaa, ottenuto bbbb")

    monkeypatch.setattr(bi, "install", rompi)
    monkeypatch.setattr(bi, "spawn", lambda fn: fn())
    res = _client(db).post("/api/setup/install/fpcalc")
    assert res.status_code == 202
    body = _client(db).get("/api/setup/install/status").json()
    assert body["status"] == "error"
    assert body["error_code"] == "checksum_mismatch"
    app.dependency_overrides.clear()


def test_archivio_pericoloso_riporta_un_codice_di_errore_distinto(db, monkeypatch):
    def rompi(key, **kw):
        raise bi.UnsafeArchive("percorso fuori dalla destinazione: ../../etc/passwd")

    monkeypatch.setattr(bi, "install", rompi)
    monkeypatch.setattr(bi, "spawn", lambda fn: fn())
    res = _client(db).post("/api/setup/install/fpcalc")
    assert res.status_code == 202
    body = _client(db).get("/api/setup/install/status").json()
    assert body["status"] == "error"
    assert body["error_code"] == "unsafe_archive"
    app.dependency_overrides.clear()


def test_un_fallimento_qualunque_non_ha_un_codice_di_errore(db, monkeypatch):
    """Le altre eccezioni (rete, binario che non parte, piattaforma senza
    build...) restano quello che erano: nessun allarme, `error_code` assente."""
    def rompi(key, **kw):
        raise bi.DoesNotRun("Bad CPU type in executable")

    monkeypatch.setattr(bi, "install", rompi)
    monkeypatch.setattr(bi, "spawn", lambda fn: fn())
    res = _client(db).post("/api/setup/install/fpcalc")
    assert res.status_code == 202
    body = _client(db).get("/api/setup/install/status").json()
    assert body["status"] == "error"
    assert body["error_code"] is None
    app.dependency_overrides.clear()
