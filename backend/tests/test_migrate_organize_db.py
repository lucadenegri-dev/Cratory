"""Migrazione del DB Organize dentro quello Cratory: invarianti, non costanti."""

import hashlib
import subprocess
import sys
import sqlite3

import pytest

from app.tools.migrate_organize_db import migra


@pytest.fixture()
def src_organize(tmp_path):
    """DB Organize sintetico: 3 file su 2 radici, 1 piano con 2 op, 2 undo."""
    path = tmp_path / "djorganizer.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE scan_root (id INTEGER PRIMARY KEY, path VARCHAR, label VARCHAR,
                                last_scanned_at DATETIME, target_root VARCHAR);
        CREATE TABLE audio_file (id INTEGER PRIMARY KEY, root_id INTEGER, path VARCHAR,
                                 ext VARCHAR, size_bytes INTEGER, hash_method VARCHAR,
                                 has_cover BOOLEAN, has_rating BOOLEAN, status VARCHAR,
                                 first_seen_at DATETIME, last_scanned_at DATETIME);
        CREATE TABLE plan (id INTEGER PRIMARY KEY, created_at DATETIME, status VARCHAR, rules_json JSON);
        CREATE TABLE plan_op (id INTEGER PRIMARY KEY, plan_id INTEGER, seq INTEGER, kind VARCHAR,
                              file_id INTEGER, before_json JSON, after_json JSON, status VARCHAR);
        CREATE TABLE undo_journal (id INTEGER PRIMARY KEY, run_id INTEGER, op_seq INTEGER,
                                   kind VARCHAR, file_id INTEGER, from_path VARCHAR, to_path VARCHAR,
                                   applied_at DATETIME, reversed BOOLEAN);
        CREATE TABLE issue (id INTEGER PRIMARY KEY, file_id INTEGER, type VARCHAR, severity VARCHAR,
                            detail TEXT, status VARCHAR, created_at DATETIME, updated_at DATETIME);
        INSERT INTO scan_root (id, path) VALUES (1, '/inbox'), (2, '/library');
        INSERT INTO audio_file (id, root_id, path, ext, size_bytes, hash_method, has_cover, has_rating,
                                status, first_seen_at, last_scanned_at)
            VALUES (10, 1, '/inbox/a.mp3', '.mp3', 1, 'stream', 0, 0, 'present',
                    '2024-01-01T00:00:00', '2024-01-01T00:00:00'),
                   (11, 2, '/library/b.flac', '.flac', 2, 'stream', 0, 0, 'present',
                    '2024-01-01T00:00:00', '2024-01-01T00:00:00'),
                   (12, 2, '/library/c.flac', '.flac', 3, 'stream', 0, 0, 'present',
                    '2024-01-01T00:00:00', '2024-01-01T00:00:00');
        INSERT INTO plan (id, created_at, status, rules_json) VALUES (5, '2024-01-01T00:00:00', 'applied', '{}');
        INSERT INTO plan_op (id, plan_id, seq, kind, file_id, before_json, after_json, status)
            VALUES (50, 5, 0, 'move', 10, '{}', '{}', 'done'),
                   (51, 5, 1, 'move', 11, '{}', '{}', 'done');
        INSERT INTO undo_journal (id, run_id, op_seq, kind, file_id, applied_at, reversed)
            VALUES (100, 5, 0, 'move', 10, '2024-01-01T00:00:00', 0),
                   (101, 5, 1, 'move', 11, '2024-01-01T00:00:00', 0);
        INSERT INTO issue (id, file_id, type, severity, detail, status)
            VALUES (200, 10, 'missing_tag', 'warn', 'x', 'closed');
    """)
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def dest_cratory(tmp_path):
    """DB Cratory di destinazione, con lo schema unificato già creato."""
    from sqlalchemy import create_engine

    from app.db import ensure_schema

    path = tmp_path / "djassistant.db"
    ensure_schema(create_engine(f"sqlite:///{path}"))
    return path


def test_dry_run_non_scrive(src_organize, dest_cratory):
    report = migra(src_organize, dest_cratory, dry_run=True)
    assert report.ok()
    assert report.audio_file == 3

    # Il contenuto, non l'mtime del file: SQLite può toccare il file anche su
    # rollback (journal/WAL), quindi un assert sull'mtime sarebbe fragile.
    conn = sqlite3.connect(dest_cratory)
    for tabella in ("scan_root", "audio_file", "plan", "plan_op", "undo_journal"):
        assert conn.execute(f"select count(*) from {tabella}").fetchone()[0] == 0
    conn.close()

    # La sorgente resta con gli stessi conteggi. Questo NON pinna l'ATTACH in
    # sola lettura: un ATTACH in scrittura su una sorgente WAL può causare un
    # checkpoint del WAL (il .db cresce, il -wal si azzera) che non altera
    # nessun conteggio — quindi questa asserzione passerebbe identica anche
    # togliendo mode=ro. La verifica che pinna davvero mode=ro è a livello di
    # byte, su una sorgente WAL con un -wal non vuoto: vedi
    # test_dry_run_non_scrive_non_altera_bytewise più sotto.
    conn_src = sqlite3.connect(src_organize)
    assert conn_src.execute("select count(*) from scan_root").fetchone()[0] == 2
    assert conn_src.execute("select count(*) from audio_file").fetchone()[0] == 3
    assert conn_src.execute("select count(*) from plan").fetchone()[0] == 1
    assert conn_src.execute("select count(*) from plan_op").fetchone()[0] == 2
    assert conn_src.execute("select count(*) from undo_journal").fetchone()[0] == 2
    conn_src.close()


@pytest.fixture()
def src_organize_wal(tmp_path):
    """Come src_organize, ma la sorgente è in journal_mode=WAL con un -wal
    non vuoto e mai checkpointato: è il caso reale, perché `app/db.py:24`
    forza `PRAGMA journal_mode=WAL` su ogni DB dell'app.

    Il -wal resta non vuoto solo se non esiste alcuna connessione SQLite
    ancora viva sul file: chiudere l'ultima connessione a un DB WAL esegue
    sempre un checkpoint automatico (verificato: anche solo chiudendo la
    connessione che ha scritto, prima di qualunque ATTACH, il .db passa già
    da 4096 a 8192 byte e il -wal sparisce). Per questo la riga scrive con un
    sottoprocesso che termina con `os._exit(0)`, bypassando sia il close()
    esplicito sia i finalizzatori dell'interprete Python in uscita normale:
    è l'equivalente del caso reale in cui l'app Organize viene fermata (o
    termina in modo brusco) lasciando un WAL da checkpointare, che è la
    precondizione realistica per lanciare questo script una volta sola sui
    dati veri."""
    path = tmp_path / "djorganizer.db"
    script = f"""
import sqlite3, os
conn = sqlite3.connect({str(path)!r})
conn.execute("PRAGMA journal_mode=WAL")
conn.executescript('''
    CREATE TABLE scan_root (id INTEGER PRIMARY KEY, path VARCHAR, label VARCHAR,
                            last_scanned_at DATETIME, target_root VARCHAR);
    CREATE TABLE audio_file (id INTEGER PRIMARY KEY, root_id INTEGER, path VARCHAR,
                             ext VARCHAR, size_bytes INTEGER, hash_method VARCHAR,
                             has_cover BOOLEAN, has_rating BOOLEAN, status VARCHAR,
                             first_seen_at DATETIME, last_scanned_at DATETIME);
    CREATE TABLE plan (id INTEGER PRIMARY KEY, created_at DATETIME, status VARCHAR, rules_json JSON);
    CREATE TABLE plan_op (id INTEGER PRIMARY KEY, plan_id INTEGER, seq INTEGER, kind VARCHAR,
                          file_id INTEGER, before_json JSON, after_json JSON, status VARCHAR);
    CREATE TABLE undo_journal (id INTEGER PRIMARY KEY, run_id INTEGER, op_seq INTEGER,
                               kind VARCHAR, file_id INTEGER, from_path VARCHAR, to_path VARCHAR,
                               applied_at DATETIME, reversed BOOLEAN);
    INSERT INTO scan_root (id, path) VALUES (1, '/inbox'), (2, '/library');
    INSERT INTO audio_file (id, root_id, path, ext, size_bytes, hash_method, has_cover, has_rating,
                            status, first_seen_at, last_scanned_at)
        VALUES (10, 1, '/inbox/a.mp3', '.mp3', 1, 'stream', 0, 0, 'present',
                '2024-01-01T00:00:00', '2024-01-01T00:00:00');
    INSERT INTO plan (id, created_at, status, rules_json) VALUES (5, '2024-01-01T00:00:00', 'applied', '{{}}');
    INSERT INTO plan_op (id, plan_id, seq, kind, file_id, before_json, after_json, status)
        VALUES (50, 5, 0, 'move', 10, '{{}}', '{{}}', 'done');
    INSERT INTO undo_journal (id, run_id, op_seq, kind, file_id, applied_at, reversed)
        VALUES (100, 5, 0, 'move', 10, '2024-01-01T00:00:00', 0);
''')
conn.commit()
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", script], check=True)
    wal_path = path.with_name(path.name + "-wal")
    assert wal_path.exists() and wal_path.stat().st_size > 0, (
        "il -wal è vuoto: il fixture non riproduce il caso reale (WAL con "
        "dati non ancora checkpointati)."
    )
    return path


def test_dry_run_non_scrive_non_altera_bytewise(src_organize_wal, dest_cratory):
    """La garanzia reale di mode=ro non è sui conteggi (quelli sopravvivono
    identici a un checkpoint WAL, vedi il commento sopra) ma sui byte: né il
    .db né il -wal della sorgente devono cambiare, nemmeno per il checkpoint
    che un ATTACH in scrittura più il DETACH che segue farebbero scattare su
    una sorgente WAL non ancora checkpointata — il caso reale, perché
    app/db.py:24 forza PRAGMA journal_mode=WAL e uno stop non pulito di
    Organize lascia frame pendenti. Verificato a mano in entrambe le
    direzioni: senza `?mode=ro` questo test è rosso (il -wal viene troncato e
    cancellato, il .db passa da 4096 a 8192 byte); con `?mode=ro` è verde."""
    wal_path = src_organize_wal.with_name(src_organize_wal.name + "-wal")
    assert wal_path.stat().st_size > 0

    prima_db = hashlib.sha256(src_organize_wal.read_bytes()).hexdigest()
    prima_wal = hashlib.sha256(wal_path.read_bytes()).hexdigest()

    report = migra(src_organize_wal, dest_cratory, dry_run=True)
    assert report.ok()

    dopo_db = hashlib.sha256(src_organize_wal.read_bytes()).hexdigest()
    dopo_wal = hashlib.sha256(wal_path.read_bytes()).hexdigest()
    assert dopo_db == prima_db, "il file .db della sorgente è stato alterato dalla migrazione"
    assert dopo_wal == prima_wal, "il file -wal della sorgente è stato alterato dalla migrazione"


def test_dest_su_db_produzione_rifiutato(src_organize, dest_cratory, monkeypatch):
    """--dest non deve mai poter risolvere al DB configurato in produzione:
    è l'ultima rete prima di lanciare lo script sui dati veri (il task
    successivo lo fa davvero)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{dest_cratory.resolve()}")
    with pytest.raises(RuntimeError, match="produzione"):
        migra(src_organize, dest_cratory, dry_run=True)

    # Nessuna scrittura avvenuta: il guard scatta prima di apire la connessione.
    conn = sqlite3.connect(dest_cratory)
    assert conn.execute("select count(*) from scan_root").fetchone()[0] == 0
    conn.close()


def test_migrazione_reale_travasa_tutto(src_organize, dest_cratory):
    report = migra(src_organize, dest_cratory, dry_run=False)
    assert report.ok()

    conn = sqlite3.connect(dest_cratory)
    conta = lambda t: conn.execute(f"select count(*) from {t}").fetchone()[0]  # noqa: E731
    assert conta("audio_file") == 3
    assert conta("scan_root") == 2
    assert conta("plan") == 1
    assert conta("plan_op") == 2
    assert conta("undo_journal") == 2
    conn.close()


def test_issue_e_dupgroup_non_migrate(src_organize, dest_cratory):
    migra(src_organize, dest_cratory, dry_run=False)
    conn = sqlite3.connect(dest_cratory)
    assert conn.execute("select count(*) from issue").fetchone()[0] == 0
    conn.close()


def test_id_preservati_e_fk_coerenti(src_organize, dest_cratory):
    """La destinazione vergine è ciò che permette di conservare gli id
    originali senza tabella di corrispondenza: verificalo sugli id concreti,
    non solo sulla forma delle FK — altrimenti "id preservati" e "id
    rinumerati ma coerenti fra loro" sarebbero indistinguibili."""
    migra(src_organize, dest_cratory, dry_run=False)
    conn = sqlite3.connect(dest_cratory)
    assert conn.execute("select id from audio_file order by id").fetchall() == [
        (10,), (11,), (12,),
    ]
    assert conn.execute("select id from plan").fetchall() == [(5,)]
    assert conn.execute("select file_id from plan_op where id = 50").fetchone() == (10,)

    orfane = conn.execute("""
        select count(*) from plan_op o
        where not exists (select 1 from audio_file f where f.id = o.file_id)
    """).fetchone()[0]
    assert orfane == 0
    orfane_undo = conn.execute("""
        select count(*) from undo_journal u
        where not exists (select 1 from audio_file f where f.id = u.file_id)
    """).fetchone()[0]
    assert orfane_undo == 0
    conn.close()


def test_migrazione_su_destinazione_non_vuota_fallisce(src_organize, dest_cratory):
    """Rilanciare la migrazione su un DB già migrato deve fermarsi, non duplicare."""
    migra(src_organize, dest_cratory, dry_run=False)
    with pytest.raises(RuntimeError, match="già popolata"):
        migra(src_organize, dest_cratory, dry_run=False)


@pytest.fixture()
def src_organize_fk_orfana(tmp_path):
    """Come src_organize, ma plan_op referenzia un file_id (999) inesistente."""
    path = tmp_path / "djorganizer.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE scan_root (id INTEGER PRIMARY KEY, path VARCHAR, label VARCHAR,
                                last_scanned_at DATETIME, target_root VARCHAR);
        CREATE TABLE audio_file (id INTEGER PRIMARY KEY, root_id INTEGER, path VARCHAR,
                                 ext VARCHAR, size_bytes INTEGER, hash_method VARCHAR,
                                 has_cover BOOLEAN, has_rating BOOLEAN, status VARCHAR,
                                 first_seen_at DATETIME, last_scanned_at DATETIME);
        CREATE TABLE plan (id INTEGER PRIMARY KEY, created_at DATETIME, status VARCHAR, rules_json JSON);
        CREATE TABLE plan_op (id INTEGER PRIMARY KEY, plan_id INTEGER, seq INTEGER, kind VARCHAR,
                              file_id INTEGER, before_json JSON, after_json JSON, status VARCHAR);
        CREATE TABLE undo_journal (id INTEGER PRIMARY KEY, run_id INTEGER, op_seq INTEGER,
                                   kind VARCHAR, file_id INTEGER, from_path VARCHAR, to_path VARCHAR,
                                   applied_at DATETIME, reversed BOOLEAN);
        INSERT INTO scan_root (id, path) VALUES (1, '/inbox');
        INSERT INTO audio_file (id, root_id, path, ext, size_bytes, hash_method, has_cover, has_rating,
                                status, first_seen_at, last_scanned_at)
            VALUES (10, 1, '/inbox/a.mp3', '.mp3', 1, 'stream', 0, 0, 'present',
                    '2024-01-01T00:00:00', '2024-01-01T00:00:00');
        INSERT INTO plan (id, created_at, status, rules_json) VALUES (5, '2024-01-01T00:00:00', 'applied', '{}');
        INSERT INTO plan_op (id, plan_id, seq, kind, file_id, before_json, after_json, status)
            VALUES (50, 5, 0, 'move', 999, '{}', '{}', 'done');
    """)
    conn.commit()
    conn.close()
    return path


def test_fk_orfana_blocca_commit_anche_senza_dry_run(src_organize_fk_orfana, dest_cratory):
    """`if dry_run or not report.ok(): ROLLBACK` ha due disgiunti: questo test
    esercita il secondo. È l'unica cosa che separa una migrazione corrotta da
    un COMMIT permanente sul DB dell'utente, quindi non deve solo essere
    segnalata — deve impedire la scrittura."""
    report = migra(src_organize_fk_orfana, dest_cratory, dry_run=False)
    assert not report.ok()
    assert report.fk_orfane > 0

    conn = sqlite3.connect(dest_cratory)
    for tabella in ("scan_root", "audio_file", "plan", "plan_op", "undo_journal"):
        assert conn.execute(f"select count(*) from {tabella}").fetchone()[0] == 0
    conn.close()


@pytest.fixture()
def src_organize_colonna_extra(tmp_path):
    """scan_root ha una colonna 'note' che la destinazione non conosce."""
    path = tmp_path / "djorganizer.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE scan_root (id INTEGER PRIMARY KEY, path VARCHAR, label VARCHAR,
                                last_scanned_at DATETIME, target_root VARCHAR, note VARCHAR);
        CREATE TABLE audio_file (id INTEGER PRIMARY KEY, root_id INTEGER, path VARCHAR,
                                 ext VARCHAR, size_bytes INTEGER, hash_method VARCHAR,
                                 has_cover BOOLEAN, has_rating BOOLEAN, status VARCHAR,
                                 first_seen_at DATETIME, last_scanned_at DATETIME);
        CREATE TABLE plan (id INTEGER PRIMARY KEY, created_at DATETIME, status VARCHAR, rules_json JSON);
        CREATE TABLE plan_op (id INTEGER PRIMARY KEY, plan_id INTEGER, seq INTEGER, kind VARCHAR,
                              file_id INTEGER, before_json JSON, after_json JSON, status VARCHAR);
        CREATE TABLE undo_journal (id INTEGER PRIMARY KEY, run_id INTEGER, op_seq INTEGER,
                                   kind VARCHAR, file_id INTEGER, from_path VARCHAR, to_path VARCHAR,
                                   applied_at DATETIME, reversed BOOLEAN);
        INSERT INTO scan_root (id, path, note) VALUES (1, '/inbox', 'da rivedere');
    """)
    conn.commit()
    conn.close()
    return path


def test_colonna_extra_in_sorgente_blocca_la_migrazione(src_organize_colonna_extra, dest_cratory):
    """Una colonna presente solo nella sorgente non deve sparire in silenzio:
    per una migrazione one-shot di dati insostituibili, conteggi che
    combaciano e un ok() vero mentre un dato è sparito è il peggior modo di
    fallire."""
    with pytest.raises(RuntimeError, match="note"):
        migra(src_organize_colonna_extra, dest_cratory, dry_run=False)

    conn = sqlite3.connect(dest_cratory)
    assert conn.execute("select count(*) from scan_root").fetchone()[0] == 0
    conn.close()


@pytest.fixture()
def src_organize_senza_has_rating(tmp_path):
    """audio_file sorgente senza has_rating: il DB Organize dell'utente può
    precedere l'ALTER TABLE che l'ha introdotta (è nullable lì, NOT NULL nella
    destinazione)."""
    path = tmp_path / "djorganizer.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE scan_root (id INTEGER PRIMARY KEY, path VARCHAR, label VARCHAR,
                                last_scanned_at DATETIME, target_root VARCHAR);
        CREATE TABLE audio_file (id INTEGER PRIMARY KEY, root_id INTEGER, path VARCHAR,
                                 ext VARCHAR, size_bytes INTEGER, hash_method VARCHAR,
                                 has_cover BOOLEAN, status VARCHAR,
                                 first_seen_at DATETIME, last_scanned_at DATETIME);
        CREATE TABLE plan (id INTEGER PRIMARY KEY, created_at DATETIME, status VARCHAR, rules_json JSON);
        CREATE TABLE plan_op (id INTEGER PRIMARY KEY, plan_id INTEGER, seq INTEGER, kind VARCHAR,
                              file_id INTEGER, before_json JSON, after_json JSON, status VARCHAR);
        CREATE TABLE undo_journal (id INTEGER PRIMARY KEY, run_id INTEGER, op_seq INTEGER,
                                   kind VARCHAR, file_id INTEGER, from_path VARCHAR, to_path VARCHAR,
                                   applied_at DATETIME, reversed BOOLEAN);
        INSERT INTO scan_root (id, path) VALUES (1, '/inbox');
        INSERT INTO audio_file (id, root_id, path, ext, size_bytes, hash_method, has_cover,
                                status, first_seen_at, last_scanned_at)
            VALUES (10, 1, '/inbox/a.mp3', '.mp3', 1, 'stream', 0, 'present',
                    '2024-01-01T00:00:00', '2024-01-01T00:00:00');
    """)
    conn.commit()
    conn.close()
    return path


def test_sorgente_senza_colonna_notnull_aborta(src_organize_senza_has_rating, dest_cratory):
    """has_rating è NOT NULL nella destinazione senza DEFAULT SQL (il
    `default=False` di SQLAlchemy è lato-Python): se la sorgente non ha quella
    colonna, l'INSERT deve fallire e non lasciare nulla a metà, non passare
    silenziosamente con righe azzerate."""
    with pytest.raises(sqlite3.IntegrityError):
        migra(src_organize_senza_has_rating, dest_cratory, dry_run=False)

    conn = sqlite3.connect(dest_cratory)
    assert conn.execute("select count(*) from scan_root").fetchone()[0] == 0
    assert conn.execute("select count(*) from audio_file").fetchone()[0] == 0
    conn.close()
