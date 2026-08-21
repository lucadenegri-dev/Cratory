import copy
import os
import sys
import tempfile
from pathlib import Path
import subprocess

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# DEVE precedere ogni import di app.*: app.core.config legge l'ambiente al
# momento dell'import, e app.db costruisce l'engine da settings.database_url.
# Senza questo, un test che dimentichi dependency_overrides[get_db] scriverebbe
# sul DB reale. Vale per entrambe le suite: da F2 l'engine è uno solo.
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="cratory-test-"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"

from app.db import Base  # noqa: E402
import app.models  # noqa: E402,F401 — registra tutte le tabelle su Base.metadata prima di create_all
from app.organize.services import scan_job  # noqa: E402
from app.services import (  # noqa: E402
    audio_analysis_job, mix_identify_job, streaming_import_job,
)

@event.listens_for(Engine, "connect")
def _accendi_le_foreign_key(dbapi_conn, _record):
    """Accende `PRAGMA foreign_keys=ON` su OGNI engine dei test.

    La produzione lo accende in `app.db._make_engine`, ma i test costruiscono
    engine SQLite a mano — la fixture `db` qui sotto e una sessantina di moduli
    che si fanno il proprio `create_engine("sqlite://")`. SQLite ha i vincoli
    spenti di default: l'intera suite girava quindi senza FK mentre la
    produzione le ha accese, e una FK dimenticata (una tabella nuova che punta
    a `tracks` e impedisce di cancellare una traccia) passava verde qui per poi
    dare 500 all'utente. L'ascoltatore e' registrato sulla classe `Engine`,
    non su una singola istanza, proprio per coprire anche gli engine costruiti
    nei singoli moduli di test senza doverli riscrivere uno per uno.
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


CAMELOT_KEYS = [
    "1A", "2A", "3A", "4A", "5A", "6A", "7A", "8A", "9A", "10A", "11A", "12A",
    "1B", "2B", "3B", "4B", "5B", "6B", "7B", "8B", "9B", "10B", "11B", "12B",
]


@pytest.fixture(autouse=True)
def _reset_runtime_settings():
    """La cache override di `runtime_settings` è un global di modulo: azzerarla
    tra i test evita contaminazione e fa sì che i `monkeypatch.setattr(settings, …)`
    esistenti continuino a valere (cache vuota → fallback a `settings`)."""
    from app.core import runtime_settings
    runtime_settings._overrides = {}
    yield
    runtime_settings._overrides = {}


@pytest.fixture(autouse=True)
def _ferma_il_riaggancio_della_coda():
    """Il riaggancio periodico della coda download è un thread daemon che
    richiama `fill()` all'infinito. Lo accende `download_dispatcher.boot()`, che
    parte dal lifespan reale di `main.py`: ogni test che usa `with TestClient(app)`
    ne lascia quindi uno in volo. Sopravvissuto al proprio test, quel thread
    rivendicherebbe righe della coda nel DB condiviso dagli altri (o, peggio, nel
    `SessionLocal` monkeypatchato dai test del dispatcher). Si spegne qui, dopo
    ogni test, così nessuno lo eredita.

    Azzera anche l'interruttore su slskd (`_slskd_blocked_until`): è un global
    di modulo come il thread, e un test che lo lascia aperto (es. uno scenario
    di daemon irraggiungibile) congelerebbe la coda del test successivo, che
    si aspetta l'interruttore chiuso di default. Stessa ragione per il
    contatore dei fallimenti consecutivi: lasciato a quattro da un test, il
    primo fallimento del successivo aprirebbe l'interruttore."""
    yield
    from app.services import download_dispatcher
    download_dispatcher.stop_retry_loop()
    download_dispatcher._slskd_blocked_until = 0.0
    download_dispatcher._slskd_blocked_reason = None
    download_dispatcher._consecutive_failures = 0
    download_dispatcher._last_failure_reason = None


@pytest.fixture()
def db():
    # Le foreign key sono accese dall'ascoltatore su `Engine` in cima al file,
    # non qui: cosi' valgono anche per gli engine che i singoli moduli di test
    # si costruiscono da soli.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seed_tracks(db):
    """Factory fixture: seed_tracks(n, with_metadata) → inserisce tracce Spotify sintetiche."""
    from app.models import Track

    def _seed(n: int = 30, with_metadata: bool = True):
        for i in range(n):
            db.add(Track(
                platform="spotify",
                spotify_id=f"spot{i:06d}",
                platform_track_id=f"spot{i:06d}",
                source_type="spotify",
                isrc=f"USABC{i:07d}",
                title=f"Track {i}" if with_metadata else None,
                artist=f"Artist {i % 5}" if with_metadata else None,
                year=None,
                duration_seconds=300 + (i % 60),
                bpm=128.0 + (i % 8),
                camelot_key=CAMELOT_KEYS[i % len(CAMELOT_KEYS)],
                status="ready_for_set",
                has_local_file=True,
            ))
        db.commit()

    return _seed


@pytest.fixture(autouse=True)
def _impedisci_esecuzione_package_manager(monkeypatch):
    """I test non possono mai eseguire un gestore di pacchetti per davvero,
    nemmeno per sbaglio. Chi lo tenta fallisce subito con un messaggio chiaro
    di che cosa ha fatto e come aggiustarlo (aggiungere un mock), non silenziando
    l'errore o peggio installando davvero. La lista di comandi bloccati arriva
    dal registry: è la lista dei comandi che l'app sa eseguire in automatico.

    Due entry point da coprire: subprocess.Popen (usato da
    binary_installer.run_recipe per il flusso di sistema) e subprocess.run
    (usato da binary_installer._prova_esecuzione e da system_probe._run_version
    per il probe). Nessuna dipendenza nuova: tutto standard library.

    NOTA: il wrapper di Popen è una classe che eredita da subprocess.Popen
    in modo che le librerie terze (yt_dlp, etc) possono subclassare
    subprocess.Popen normalmente — non è una semplice funzione perché
    altrimenti il subclassing fallerebbe.
    """
    import subprocess as subprocess_orig

    # Estrai i comandi bloccati dal registry di system_probe. Leggi la lista
    # qui dentro il fixture perché il modulo non è stato importato in conftest
    # e vogliamo caricare il registry esattamente al momento di essere
    # eseguiti, non all'import. Inoltre, questo isola il costrutto dalla lista
    # stessa (cambiarla lì non rompe il fixture, perché qui la leggiamo sempre
    # al momento dell'esecuzione).
    def _get_blocked_commands():
        from app.services import system_probe
        # Nomi dei comandi dai quali ricavare i primi argomenti
        comandi_bloccati: set[str] = set()

        for component in system_probe.REGISTRY:
            ricette = component.recipes or {}
            for ricetta in ricette.values():
                if ricetta:  # lista non vuota
                    # Il primo elemento è il comando (es. "brew", "apt", "sudo", "winget")
                    comandi_bloccati.add(ricetta[0])

        # Aggiungi anche alcune varianti che potrebbe provare someone:
        # - apt e apt-get sono intercambiabili
        # - yum e dnf sono intercambiabili
        # - sudo di solito precede apt/yum ma conta lo stesso
        comandi_bloccati.update([
            "apt", "apt-get",
            "yum", "dnf",
            "pacman", "zypper", "apk",
            "sudo",
            "brew", "winget",
        ])

        return comandi_bloccati

    blocked = _get_blocked_commands()

    def _check_package_manager(argv):
        """Solleva un errore se argv esegue un package manager."""
        if not argv:
            return
        comando = argv[0]
        # Estrai basename dal percorso completo (es. "/opt/homebrew/bin/brew" -> "brew")
        basename = Path(comando).name if isinstance(comando, (str, Path)) else comando
        if basename in blocked:
            raise RuntimeError(
                f"SICUREZZA: il test ha cercato di eseguire '{basename}' per davvero.\n"
                f"Aggiungere un mock per subprocess.run() / subprocess.Popen() nel test.\n"
                f"Argomenti: {argv}"
            )

    original_run = subprocess_orig.run
    original_popen = subprocess_orig.Popen

    def wrapped_run(args, **kwargs):
        _check_package_manager(args if isinstance(args, (list, tuple)) else args.split())
        return original_run(args, **kwargs)

    # La classe wrapper per Popen che eredita da subprocess.Popen.
    # Così le librerie terze che fanno `class MyPopen(subprocess.Popen)` continueranno
    # a funzionare anche quando Popen è stato wrappato.
    class WrappedPopen(original_popen):
        def __init__(self, args=None, *popenargs, **kwargs):
            _check_package_manager(args if isinstance(args, (list, tuple)) else (args.split() if args else []))
            super().__init__(args, *popenargs, **kwargs)

    monkeypatch.setattr(subprocess_orig, "run", wrapped_run)
    monkeypatch.setattr(subprocess_orig, "Popen", WrappedPopen)


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    """I test non parlano MAI con l'API Anthropic vera: la chiave del .env
    reale renderebbe attivo l'anello AI del genere (lento e a pagamento).
    I test dell'AI monkeypatchano suggest_genre/il client esplicitamente."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "ai_api_key", "")


@pytest.fixture(autouse=True)
def _no_real_library_scan(monkeypatch):
    """Un test che istanzia TestClient(app) fa scattare il lifespan di app/main.py
    (ensure_schema +, se LIBRARY_ROOT e' configurato nel .env reale dello
    sviluppatore, scan_job.start_job_if_due): senza questo guard un test
    HTTP-level innescherebbe una scansione VERA della libreria musicale sul disco
    e scriverebbe sul DB reale (data/djassistant.db) invece che sul DB isolato del
    test — lento (minuti su una libreria grande) e non isolato tra i test.

    Da F4 blanka anche ARCHIVE_ROOT: `scanner.scan` (Organize) chiama ora la
    fase 2 dell'indicizzazione, che legge `runtime_settings.archive_root()` allo
    stesso modo del job — senza il guard, un test che invoca `scan()` senza
    monkeypatchare esplicitamente la cartella cammina l'ARCHIVE_ROOT VERO
    configurato nel .env dello sviluppatore.

    Copre le TRE radici configurabili, non due: anche SLSKD_DOWNLOAD_DIR (la
    cartella Inbox) va azzerata, altrimenti `radici(db)` la risolve comunque
    dal .env reale dello sviluppatore e uno scan/link nei test cammina e hasha
    quella cartella vera invece di una temporanea (vedi
    test_db_isolation.py::test_guard_scan_azzera_tutte_e_tre_le_radici)."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "library_root", "")
    monkeypatch.setattr(settings, "archive_root", "")
    monkeypatch.setattr(settings, "slskd_download_dir", "")


# I 4 job in background (analisi BPM/key, scansione+aggancio libreria,
# identificazione mix Shazam, import/sync streaming) tengono lo stato in un dict
# globale di modulo (app locale mono-utente, niente sessione HTTP per il
# polling). Un test che lascia lo stato a "running" (es. i test della guardia
# doppio-avvio in test_job_double_start.py) contaminerebbe qualsiasi test
# successivo che legge job_state() o chiama start_job() aspettandosi lo stato
# iniziale "idle". Da F4 Task 3 la scansione+indicizzazione e' un job solo
# (scan_job), non piu' due (library_index_job e' assorbito). Il download
# Soulseek non e' piu' in lista: non e' piu' un job con stato globale ma una
# coda persistita sul DB, che i test isolano gia' col loro engine.
_JOB_STATE_MODULES = [
    audio_analysis_job, scan_job, mix_identify_job, streaming_import_job,
]
_PRISTINE_JOB_STATES = [copy.deepcopy(m._state) for m in _JOB_STATE_MODULES]


@pytest.fixture(autouse=True)
def _reset_job_states():
    """Ripristina lo stato pristino di ogni job PRIMA e DOPO ogni test: prima, in
    caso un test precedente l'abbia lasciato sporco senza passare da qui (ordine
    di esecuzione non garantito); dopo, per non contaminare il test successivo."""
    def _reset():
        for module, pristine in zip(_JOB_STATE_MODULES, _PRISTINE_JOB_STATES):
            module._state.clear()
            module._state.update(copy.deepcopy(pristine))

    _reset()
    yield
    _reset()


@pytest.fixture()
def fake_audio(monkeypatch, tmp_path):
    """Crea file finti e monkeypatcha hash/tag/qualita' per renderli deterministici.

    Condivisa: la usano i test dell'indicizzazione libreria e quelli sugli
    invarianti (e servira' allo scanner unico di F4).
    """
    from app.services import library_index as li

    hashes: dict[str, str] = {}
    tags: dict[str, dict] = {}

    def make(rel: str, *, digest: str, artist=None, title=None, isrc=None, genre=None, label=None):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        hashes[str(p.resolve())] = digest
        tags[str(p.resolve())] = {
            "title": title, "artist": artist, "album": None, "year": None,
            "duration_seconds": 200, "isrc": isrc, "genre": genre, "label": label,
        }
        return p

    monkeypatch.setattr(li, "audio_hash", lambda p: hashes[str(p.resolve() if hasattr(p, 'resolve') else p)])
    monkeypatch.setattr(li, "read_tags", lambda p: tags[str(p.resolve() if hasattr(p, 'resolve') else p)])
    monkeypatch.setattr(li, "read_audio_quality", lambda p: {"format": "mp3", "bitrate": 320})
    return make, tmp_path


@pytest.fixture()
def semina_indice_libreria(db):
    """Semina in `AudioFile` una riga (`location='library'`, `status='present'`)
    per ogni file audio sotto una radice, senza toccare le Track.

    Perché esiste: da F4 `collega_tracce` legge le righe `AudioFile` che lo
    scanner di Organize (`app/organize/services/scanner.py`) scrive quando
    cammina il disco — non cammina più il disco lei stessa. Quello scanner non
    gira nei test di questo modulo (`library_index`): questo helper riproduce
    SOLO il suo passo di popolamento indice, riusando lo stesso walk
    (`library_index.scan_folder`, così i test che lo monkeypatchano per
    simulare file che spariscono a metà corsa continuano a funzionare
    identici a prima di F4). I campi di qualità (`ext`/`size_bytes`/
    `hash_method`) sono segnaposto, come già in `tests/test_collega_tracce.py`:
    a `collega_tracce` non serve altro che path/location/status per agganciare
    — hash e tag li rilegge dal file vero al momento dell'aggancio.

    Upsert per (root_id, path), come lo scanner vero: un test che simula più
    corse (scan+link, scan+link) chiamando l'helper più volte sullo stesso
    file non deve urtare il vincolo di unicità.
    """
    from app.core import runtime_settings
    from app.organize.models import AudioFile
    from app.organize.services.roots import radici
    from app.services import library_index as li
    from sqlalchemy import select

    def _run(root) -> None:
        runtime_settings.apply(db, "library_root", str(root))
        root_id = radici(db)["library"].id
        for path in li.scan_folder(root):
            resolved = str(path.resolve())
            existing = db.scalar(select(AudioFile).where(
                AudioFile.root_id == root_id, AudioFile.path == resolved))
            if existing is not None:
                existing.status = "present"
                continue
            db.add(AudioFile(
                root_id=root_id, path=resolved, location="library",
                status="present", ext=path.suffix.lstrip("."), size_bytes=0,
                hash_method="test-stub",
            ))
        db.commit()

    return _run


@pytest.fixture()
def collega_da_disco(db, semina_indice_libreria):
    """Ponte fra i vecchi test 'index_library(db, root=...)' e la fase 2 attuale.

    Fino a F4 `index_library`/`collega_tracce` camminavano `root` per conto
    proprio. Ora `collega_tracce` legge solo le righe `AudioFile` già scritte
    (dallo scanner di Organize, in produzione). Questo helper riproduce quel
    solo passo di popolamento (`semina_indice_libreria`) e poi chiama le
    funzioni sotto test — non un sostituto loro: l'aggancio (hash, match,
    upsert) e la riconciliazione restano interamente lì.

    Senza archivio, il giro sono due delle tre parti nell'ordine obbligatorio
    (`collega_tracce` → `riconcilia_possessi`) con lo stesso `seen_paths`
    condiviso; il report è la somma dei due, come lo compone `index_library`.
    """
    from app.services import library_index as li

    def _run(root):
        semina_indice_libreria(root)
        seen_paths: set[str] = set()
        seen_digests: set[str] = set()
        report = li.collega_tracce(db, seen_paths=seen_paths, seen_digests=seen_digests)
        rec = li.riconcilia_possessi(db, seen_paths=seen_paths,
                                     scanned=report["scanned"])
        report["lost"] += rec["lost"]
        report["orphans_removed"] += rec["orphans_removed"]
        return report

    return _run
