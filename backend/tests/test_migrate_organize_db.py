"""Migrazione del DB Organize dentro quello Cratory: invarianti, non costanti."""

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
    assert conn.execute("select count(*) from audio_file").fetchone()[0] == 0
    assert conn.execute("select count(*) from plan").fetchone()[0] == 0
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


def test_id_rimappati_e_fk_coerenti(src_organize, dest_cratory):
    """plan_op e undo_journal devono puntare agli audio_file nuovi, non ai vecchi id."""
    migra(src_organize, dest_cratory, dry_run=False)
    conn = sqlite3.connect(dest_cratory)
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
