"""Servizio backup: DATA_DIR e DB su cartelle temporanee, sqlite vero."""
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import paths
from app.core.config import settings
from app.db import Base, ensure_schema
from app.services import backup


@pytest.fixture()
def dati(tmp_path, monkeypatch):
    """Un DATA_DIR temporaneo con un DB vero (schema completo, WAL acceso),
    una cover, un .env, uno slskd.yml, e roba che NON deve entrare."""
    data_dir = tmp_path / "dati"
    (data_dir / "data" / "covers").mkdir(parents=True)
    (data_dir / "data" / "thumb_cache").mkdir()
    (data_dir / "logs").mkdir()
    db_path = data_dir / "data" / "djassistant.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    ensure_schema(engine)
    with sqlite3.connect(db_path, isolation_level=None) as c:
        c.execute("PRAGMA journal_mode=WAL")
    (data_dir / "data" / "covers" / "playlist-1.jpg").write_bytes(b"\xff\xd8cover")
    (data_dir / ".env").write_text("SPOTIFY_CLIENT_ID=abc\n")
    (data_dir / "data" / "slskd.yml").write_text("soulseek:\n  password: segreta\n")
    (data_dir / "data" / "thumb_cache" / "1.jpg").write_bytes(b"no")
    (data_dir / "data" / "slskd.log").write_text("no")
    (data_dir / "logs" / "djassistant.log").write_text("no")
    monkeypatch.setattr(paths, "DATA_DIR", data_dir)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    engine.dispose()
    return data_dir


def _membri(zip_path: Path) -> set[str]:
    with zipfile.ZipFile(zip_path) as z:
        return set(z.namelist())


def test_contenuto_elenca_le_quattro_voci_e_le_dimensioni(dati):
    voci = {v.nome: v for v in backup.contenuto()}
    assert set(voci) == {"database", "covers", "env", "slskd"}
    assert all(v.presente for v in voci.values())
    assert voci["covers"].byte == len(b"\xff\xd8cover")
    assert voci["database"].byte > 0
    assert voci["covers"].file == 1
    assert voci["database"].file == 1 and voci["env"].file == 1 and voci["slskd"].file == 1


def test_contenuto_conta_le_cover(dati):
    """Il conteggio è quello che la scheda «Dati» mostra all'utente: «database,
    N cover, credenziali». Con due cover deve dire due."""
    (dati / "data" / "covers" / "playlist-2.jpg").write_bytes(b"\xff\xd8due")
    voci = {v.nome: v for v in backup.contenuto()}
    assert voci["covers"].file == 2


def test_contenuto_segna_assente_cio_che_manca(dati):
    (dati / ".env").unlink()
    shutil.rmtree(dati / "data" / "covers")
    voci = {v.nome: v for v in backup.contenuto()}
    assert voci["env"].presente is False and voci["env"].byte == 0 and voci["env"].file == 0
    assert voci["covers"].presente is False and voci["covers"].file == 0


def test_stima_non_dipende_dal_wal(dati):
    prima = backup.stima_byte()
    db = backup._db_path()
    with sqlite3.connect(db, isolation_level=None) as c:
        c.execute("PRAGMA wal_autocheckpoint=0")
        for i in range(200):
            c.execute(
                "INSERT INTO app_state(key, value, updated_at) VALUES (?, ?, ?)",
                (f"k{i}", "x" * 4000, "2024-01-01 00:00:00"),
            )
        c.execute("DELETE FROM app_state")
    # Il WAL è cresciuto di centinaia di KB; la stima segue le pagine usate, non il WAL.
    assert (db.parent / "djassistant.db-wal").stat().st_size > 100_000
    assert abs(backup.stima_byte() - prima) < 50_000


def test_nome_di_default_ha_data_e_ora():
    nome = backup.nome_di_default()
    assert nome.startswith("cratory-backup-") and nome.endswith(".zip")
    assert len(nome) == len("cratory-backup-20260913-1840.zip")


def test_crea_include_i_membri_attesi_e_nessun_escluso(dati, tmp_path):
    esito = backup.crea(tmp_path / "b.zip")
    assert Path(esito.percorso) == tmp_path / "b.zip"
    assert esito.byte == (tmp_path / "b.zip").stat().st_size
    membri = _membri(tmp_path / "b.zip")
    assert membri == {"manifest.json", "data/djassistant.db", "data/covers/playlist-1.jpg",
                      ".env", "data/slskd.yml"}
    with zipfile.ZipFile(tmp_path / "b.zip") as z:
        manifest = json.loads(z.read("manifest.json"))
    assert manifest["formato"] == 1
    assert manifest["creato_il"] == esito.creato_il
    assert {m["nome"] for m in manifest["membri"]} == membri - {"manifest.json"}
    assert isinstance(manifest["app_version"], str)


def test_crea_aggiunge_zip_se_manca(dati, tmp_path):
    esito = backup.crea(tmp_path / "senza-estensione")
    assert esito.percorso.endswith("senza-estensione.zip")


def test_crea_salta_le_voci_assenti(dati, tmp_path):
    (dati / ".env").unlink()
    shutil.rmtree(dati / "data" / "covers")
    membri = _membri(Path(backup.crea(tmp_path / "b.zip").percorso))
    assert membri == {"manifest.json", "data/djassistant.db", "data/slskd.yml"}


def test_uno_snapshot_rimasto_da_un_crash_non_blocca_il_backup(dati, tmp_path):
    """`VACUUM INTO` vuole che il file di destinazione non esista: un
    `.db-snapshot` sopravvissuto a un crash farebbe fallire ogni backup
    successivo con «output file already exists»."""
    (tmp_path / "b.zip.db-snapshot").write_bytes(b"avanzo di un crash")
    esito = backup.crea(tmp_path / "b.zip")
    assert _membri(Path(esito.percorso)) >= {"manifest.json", "data/djassistant.db"}
    assert not (tmp_path / "b.zip.db-snapshot").exists()


def test_lo_snapshot_e_coerente_con_una_connessione_aperta(dati, tmp_path):
    db = backup._db_path()
    viva = sqlite3.connect(db, isolation_level=None)
    viva.execute(
        "INSERT INTO app_state(key, value, updated_at) VALUES ('prima', 'si', '2024-01-01 00:00:00')"
    )
    esito = backup.crea(tmp_path / "b.zip")
    viva.close()
    with zipfile.ZipFile(esito.percorso) as z:
        z.extract("data/djassistant.db", tmp_path / "estratto")
    with sqlite3.connect(tmp_path / "estratto" / "data" / "djassistant.db") as c:
        assert c.execute("SELECT value FROM app_state WHERE key='prima'").fetchone() == ("si",)
        assert c.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_un_errore_non_lascia_ne_zip_ne_parziale(dati, tmp_path, monkeypatch):
    class Rotto:
        def __init__(self, *a, **k):
            raise OSError("disco pieno")

    monkeypatch.setattr(backup.zipfile, "ZipFile", Rotto)
    with pytest.raises(OSError):
        backup.crea(tmp_path / "b.zip")
    # `dati` (la cartella DATA_DIR della fixture) è l'unica cosa che deve
    # restare in tmp_path: né zip né `.parziale` né `.db-snapshot`.
    assert list(tmp_path.iterdir()) == [dati]


def test_due_backup_insieme_il_secondo_e_rifiutato(dati, tmp_path):
    assert backup._lock.acquire(blocking=False)
    try:
        with pytest.raises(backup.BackupInCorso):
            backup.crea(tmp_path / "b.zip")
    finally:
        backup._lock.release()


# --- ispezione ------------------------------------------------------------------

def _zip_con(tmp_path, nome="x.zip", *, manifest=..., db: bytes | Path | None = ..., extra=()):
    """Costruisce uno zip di prova a partire da un backup vero e lo altera."""
    vero = Path(backup.crea(tmp_path / "vero.zip").percorso)
    out = tmp_path / nome
    with zipfile.ZipFile(vero) as src, zipfile.ZipFile(out, "w") as dst:
        for m in src.namelist():
            if m == "manifest.json":
                if manifest is None:
                    continue
                dst.writestr(m, src.read(m) if manifest is ... else json.dumps(manifest))
            elif m == "data/djassistant.db":
                if db is None:
                    continue
                dst.writestr(m, src.read(m) if db is ... else (db if isinstance(db, bytes) else db.read_bytes()))
            else:
                dst.writestr(m, src.read(m))
        for nome_extra, contenuto in extra:
            dst.writestr(nome_extra, contenuto)
    return out


def test_ispeziona_un_backup_vero(dati, tmp_path):
    with sqlite3.connect(backup._db_path()) as c:
        c.execute(
            "INSERT INTO playlists(name, platform, track_count, kind, imported_at, created_at, updated_at) "
            "VALUES ('p', 'manual', 0, 'playlist', '2024-01-01 00:00:00', '2024-01-01 00:00:00', '2024-01-01 00:00:00')"
        )
    esito = backup.crea(tmp_path / "b.zip")
    r = backup.ispeziona(Path(esito.percorso))
    assert r.creato_il == esito.creato_il
    assert r.playlist == 1 and r.tracce == 0
    assert r.ha_credenziali is True
    assert "data/djassistant.db" in r.membri


def test_ispeziona_senza_credenziali(dati, tmp_path):
    (dati / ".env").unlink()
    (dati / "data" / "slskd.yml").unlink()
    r = backup.ispeziona(Path(backup.crea(tmp_path / "b.zip").percorso))
    assert r.ha_credenziali is False


@pytest.mark.parametrize("caso, codice", [
    ("non_zip", "archivio_non_valido"),
    ("senza_manifest", "manifest_assente"),
    ("formato_2", "manifest_assente"),
    ("senza_db", "db_assente"),
    ("db_troncato", "db_corrotto"),
])
def test_ispeziona_rifiuta_con_il_codice_giusto(dati, tmp_path, caso, codice):
    if caso == "non_zip":
        archivio = tmp_path / "x.zip"
        archivio.write_bytes(b"non sono uno zip")
    elif caso == "senza_manifest":
        archivio = _zip_con(tmp_path, manifest=None)
    elif caso == "formato_2":
        archivio = _zip_con(tmp_path, manifest={"formato": 2, "app_version": "1.0.0"})
    elif caso == "senza_db":
        archivio = _zip_con(tmp_path, db=None)
    else:
        archivio = _zip_con(tmp_path, db=b"SQLite format 3\x00" + b"\x00" * 100)
    with pytest.raises(backup.BackupNonValido) as e:
        backup.ispeziona(archivio)
    assert e.value.codice == codice


def test_ispeziona_rifiuta_una_versione_piu_recente(dati, tmp_path, monkeypatch):
    from app.core import version
    monkeypatch.setattr(version, "app_version", lambda: "1.0.8")
    archivio = _zip_con(tmp_path, manifest={"formato": 1, "app_version": "1.1.0", "creato_il": "x", "membri": []})
    with pytest.raises(backup.BackupNonValido) as e:
        backup.ispeziona(archivio)
    assert e.value.codice == "versione_piu_recente"


def test_ispeziona_accetta_una_versione_piu_vecchia_o_uguale(dati, tmp_path, monkeypatch):
    from app.core import version
    monkeypatch.setattr(version, "app_version", lambda: "1.0.8")
    for v in ("1.0.8", "0.9.0"):
        archivio = _zip_con(tmp_path, nome=f"{v}.zip", manifest={"formato": 1, "app_version": v, "creato_il": "x", "membri": []})
        assert backup.ispeziona(archivio).app_version == v


def test_in_sviluppo_la_versione_non_si_controlla(dati, tmp_path, monkeypatch):
    """`0.0.0-dev` batterebbe qualunque backup fatto da un'app vera: in un
    checkout senza VERSION il controllo si salta."""
    from app.core import version
    monkeypatch.setattr(version, "app_version", lambda: version.FALLBACK)
    archivio = _zip_con(tmp_path, manifest={"formato": 1, "app_version": "9.9.9", "creato_il": "x", "membri": []})
    assert backup.ispeziona(archivio).app_version == "9.9.9"


# --- ripristino: i due tempi ----------------------------------------------------

@pytest.fixture()
def sessione(dati):
    engine = create_engine(f"sqlite:///{backup._db_path()}", connect_args={"check_same_thread": False})
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def test_prepara_popola_lo_staging_senza_marker(dati, tmp_path, sessione):
    archivio = Path(backup.crea(tmp_path / "b.zip").percorso)
    r = backup.prepara(archivio, sessione)
    staging = dati / "data" / "restore-staging"
    assert (staging / "data" / "djassistant.db").is_file()
    assert (staging / "data" / "covers" / "playlist-1.jpg").is_file()
    assert (staging / ".env").is_file() and (staging / "data" / "slskd.yml").is_file()
    assert json.loads((staging / "riepilogo.json").read_text())["playlist"] == r.playlist
    assert not (dati / "data" / "restore-pending.json").exists()
    assert backup.riepilogo_in_attesa().creato_il == r.creato_il


def test_prepara_ignora_membri_non_ammessi(dati, tmp_path, sessione):
    """I due nomi ostili non finiscono nello staging, e nemmeno DOVE finirebbero
    se `_membro_ammesso` li lasciasse passare: `../fuori.txt` risolve a
    `dati/data/fuori.txt` e `data/covers/../../x` a `staging/x`. Si asserisce
    l'insieme esatto dei file sotto staging, così un membro in più — ovunque
    atterri — rompe il test."""
    archivio = _zip_con(tmp_path, extra=[("../fuori.txt", b"no"), ("data/covers/../../x", b"no")])
    backup.prepara(archivio, sessione)
    staging = dati / "data" / "restore-staging"
    trovati = {str(f.relative_to(staging)) for f in staging.rglob("*") if f.is_file()}
    assert trovati == {
        "riepilogo.json",
        "manifest.json",
        "data/djassistant.db",
        "data/covers/playlist-1.jpg",
        ".env",
        "data/slskd.yml",
    }
    # Dove sarebbero atterrati davvero, se fossero stati ammessi.
    assert not (dati / "data" / "fuori.txt").exists()
    assert not (staging / "x").exists()


def test_una_nuova_preparazione_revoca_la_conferma_precedente(dati, tmp_path, sessione):
    """Senza questo, il marker di A resterebbe a puntare a uno staging che nel
    frattempo contiene B: al prossimo avvio si applicherebbe B sotto un
    riepilogo che descrive A, e B non l'ha confermato nessuno."""
    primo = Path(backup.crea(tmp_path / "a.zip").percorso)
    backup.prepara(primo, sessione)
    backup.conferma(sessione)
    assert (dati / "data" / "restore-pending.json").exists()

    with sqlite3.connect(backup._db_path()) as c:
        c.execute(
            "INSERT INTO playlists(name, platform, track_count, kind, imported_at, created_at, updated_at) "
            "VALUES ('b', 'manual', 0, 'playlist', '2024-01-01 00:00:00', '2024-01-01 00:00:00', '2024-01-01 00:00:00')"
        )
    secondo = Path(backup.crea(tmp_path / "b.zip").percorso)
    r = backup.prepara(secondo, sessione)

    assert not (dati / "data" / "restore-pending.json").exists()
    assert r.playlist == 1
    assert backup.riepilogo_in_attesa().creato_il == r.creato_il
    assert backup.riepilogo_in_attesa().playlist == 1


def test_un_archivio_rifiutato_non_revoca_la_conferma(dati, tmp_path, sessione):
    """L'altra faccia: se `ispeziona` boccia l'archivio, lo staging non viene
    toccato e la conferma di prima resta valida per quello che c'è dentro."""
    backup.prepara(Path(backup.crea(tmp_path / "a.zip").percorso), sessione)
    backup.conferma(sessione)
    rotto = tmp_path / "rotto.zip"
    rotto.write_bytes(b"non sono uno zip")
    with pytest.raises(backup.BackupNonValido):
        backup.prepara(rotto, sessione)
    assert (dati / "data" / "restore-pending.json").exists()
    assert (dati / "data" / "restore-staging" / "data" / "djassistant.db").is_file()


def test_prepara_file_inesistente(dati, sessione, tmp_path):
    with pytest.raises(FileNotFoundError):
        backup.prepara(tmp_path / "manca.zip", sessione)


def test_conferma_scrive_il_marker_con_db_path_e_riepilogo(dati, tmp_path, sessione):
    archivio = Path(backup.crea(tmp_path / "b.zip").percorso)
    backup.prepara(archivio, sessione)
    backup.conferma(sessione)
    marker = json.loads((dati / "data" / "restore-pending.json").read_text())
    assert marker["db_path"] == str(backup._db_path())
    assert marker["staging"] == str(dati / "data" / "restore-staging")
    assert marker["riepilogo"]["tracce"] == 0


def test_conferma_senza_staging_solleva(dati, sessione):
    with pytest.raises(backup.NienteDaRipristinare):
        backup.conferma(sessione)


def test_annulla_pulisce_tutto_ed_e_idempotente(dati, tmp_path, sessione):
    backup.prepara(Path(backup.crea(tmp_path / "b.zip").percorso), sessione)
    backup.conferma(sessione)
    backup.annulla()
    backup.annulla()
    assert not (dati / "data" / "restore-staging").exists()
    assert not (dati / "data" / "restore-pending.json").exists()
    assert backup.riepilogo_in_attesa() is None


@pytest.mark.parametrize("modulo, attr, atteso", [
    ("app.services.audio_analysis_job", "is_running", "analysis"),
    ("app.services.streaming_import_job", "is_running", "import"),
    ("app.services.mix_identify_job", "is_running", "shazam"),
])
def test_prepara_rifiuta_con_un_job_in_corso(dati, tmp_path, sessione, monkeypatch, modulo, attr, atteso):
    import importlib
    monkeypatch.setattr(importlib.import_module(modulo), attr, lambda: True)
    archivio = Path(backup.crea(tmp_path / "b.zip").percorso)
    with pytest.raises(backup.JobInCorso) as e:
        backup.prepara(archivio, sessione)
    assert e.value.job == atteso
    assert not (dati / "data" / "restore-staging").exists()


def test_prepara_rifiuta_con_un_download_in_corso(dati, tmp_path, sessione):
    from app.models import DownloadQueueItem, Track
    t = Track(platform="spotify", platform_track_id="x", source_type="spotify", title="t", artist="a")
    sessione.add(t)
    sessione.flush()
    sessione.add(DownloadQueueItem(track_id=t.id, kind="soulseek_auto", state="running"))
    sessione.commit()
    with pytest.raises(backup.JobInCorso) as e:
        backup.prepara(Path(backup.crea(tmp_path / "b.zip").percorso), sessione)
    assert e.value.job == "downloads"


def test_un_download_in_coda_ma_non_in_corso_non_blocca(dati, tmp_path, sessione):
    from app.models import DownloadQueueItem, Track
    t = Track(platform="spotify", platform_track_id="x", source_type="spotify", title="t", artist="a")
    sessione.add(t)
    sessione.flush()
    sessione.add(DownloadQueueItem(track_id=t.id, kind="soulseek_auto", state="queued"))
    sessione.commit()
    backup.prepara(Path(backup.crea(tmp_path / "b.zip").percorso), sessione)


def _sha(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_applica_senza_marker_non_tocca_niente(dati):
    prima = _sha(backup._db_path())
    assert backup.applica_se_in_attesa() is None
    assert _sha(backup._db_path()) == prima


def test_applica_scambia_i_file_e_conserva_pre_restore(dati, tmp_path, sessione):
    # Il backup contiene 'nel_backup'; il DB attuale, dopo, conterrà 'dopo'.
    with sqlite3.connect(backup._db_path()) as c:
        c.execute(
            "INSERT INTO app_state(key, value, updated_at) VALUES ('nel_backup', '1', '2024-01-01 00:00:00')"
        )
    archivio = Path(backup.crea(tmp_path / "b.zip").percorso)
    with sqlite3.connect(backup._db_path()) as c:
        c.execute("DELETE FROM app_state WHERE key='nel_backup'")
        c.execute(
            "INSERT INTO app_state(key, value, updated_at) VALUES ('dopo', '1', '2024-01-01 00:00:00')"
        )
    (dati / ".env").write_text("CAMBIATO=1\n")
    backup.prepara(archivio, sessione)
    backup.conferma(sessione)
    sessione.close()
    sessione.get_bind().dispose()

    esito = backup.applica_se_in_attesa()

    assert esito.stato == "ok" and esito.tracce == 0
    with sqlite3.connect(backup._db_path()) as c:
        chiavi = {r[0] for r in c.execute("SELECT key FROM app_state")}
    assert "nel_backup" in chiavi and "dopo" not in chiavi
    assert (dati / ".env").read_text() == "SPOTIFY_CLIENT_ID=abc\n"
    pre = dati / "data" / "pre-restore"
    assert (pre / "djassistant.db").is_file()
    assert (pre / ".env").read_text() == "CAMBIATO=1\n"
    assert (pre / "covers" / "playlist-1.jpg").is_file()
    assert not (dati / "data" / "restore-pending.json").exists()
    assert not (dati / "data" / "restore-staging").exists()
    assert not (backup._db_path().parent / "djassistant.db-wal").exists()


def test_applica_logga_dove_finiscono_i_dati_prima_di_muoverli(dati, tmp_path, sessione, caplog):
    """Se lo scambio si interrompe a metà, questa riga è l'unica traccia di dove
    sono i dati di prima: va scritta PRIMA del primo `move`."""
    archivio = Path(backup.crea(tmp_path / "b.zip").percorso)
    backup.prepara(archivio, sessione)
    backup.conferma(sessione)
    sessione.close()
    sessione.get_bind().dispose()
    with caplog.at_level("WARNING", logger="app.services.backup"):
        backup.applica_se_in_attesa()
    righe = [r.getMessage() for r in caplog.records]
    assert any(str(dati / "data" / "pre-restore") in r for r in righe)
    # Prima dell'altro warning, quello di fine scambio.
    assert righe.index(next(r for r in righe if "pre-restore" in r)) < righe.index(
        next(r for r in righe if "ripristino applicato" in r)
    )


def test_applica_con_staging_mancante_toglie_il_marker_e_non_tocca_i_dati(dati):
    prima = _sha(backup._db_path())
    (dati / "data" / "restore-pending.json").write_text(json.dumps({
        "staging": str(dati / "data" / "restore-staging"),
        "db_path": str(backup._db_path()),
        "riepilogo": {},
    }))
    esito = backup.applica_se_in_attesa()
    assert esito.stato == "fallito" and esito.motivo == "staging_incompleto"
    assert _sha(backup._db_path()) == prima
    assert not (dati / "data" / "restore-pending.json").exists()


def test_applica_con_marker_illeggibile_lo_toglie(dati):
    (dati / "data" / "restore-pending.json").write_text("{non json")
    esito = backup.applica_se_in_attesa()
    assert esito.stato == "fallito"
    assert not (dati / "data" / "restore-pending.json").exists()
