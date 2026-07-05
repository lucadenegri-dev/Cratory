# backend/tests/test_migrate_drop_legacy_fk.py
"""Repro FK-safety per `_migrate_drop_legacy` (Task 7b).

Il pattern RENAME->rebuild->DROP corrompe i DB con foreign_keys=ON: il RENAME di
`tracks` riscrive le REFERENCES di `playlist_tracks`/`setlist_tracks`, e il DROP
della tabella rinominata fallisce se esistono righe figlie (o, se non fallisce,
le lascia orfane). Questi test usano `_make_engine` (stessa factory di produzione)
cosi' `PRAGMA foreign_keys=ON` e' attiva come a runtime: senza FK ON il bug non si
riproduce affatto.

VINCOLO: mai toccare il DB di sviluppo - solo engine su tmp_path.
"""
from datetime import datetime, timezone

from sqlalchemy import inspect, text

from app.db import Base, _make_engine, ensure_schema
import app.models  # noqa: F401 - registra i modelli su Base.metadata


def _make_legacy_db(db_path):
    """Crea uno schema completo via create_all, poi lo regredisce a 'pre-pivot':
    aggiunge le colonne legacy (rekordbox_track_id, tonality) e popola dati che
    esercitano sia il ramo coalesce sia il ramo DELETE con FK.
    """
    engine = _make_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        # Simula DB pre-pivot: colonne legacy Rekordbox su tracks.
        conn.execute(text("ALTER TABLE tracks ADD COLUMN rekordbox_track_id INTEGER"))
        conn.execute(text("ALTER TABLE tracks ADD COLUMN tonality VARCHAR"))

        now = datetime.now(timezone.utc).isoformat()

        # Track streaming "buona": camelot_key NULL, tonality valorizzata (da coalescare).
        conn.execute(text(
            "INSERT INTO tracks (id, source_type, title, artist, status, camelot_key, tonality, "
            "created_at, updated_at, has_local_file, archived) "
            "VALUES (1, 'spotify', 'Good Track', 'Artist A', 'imported', NULL, '8A', :now, :now, 0, 0)"
        ), {"now": now})

        # Track legacy Rekordbox: deve essere eliminata dal ramo DELETE.
        conn.execute(text(
            "INSERT INTO tracks (id, source_type, title, artist, status, rekordbox_track_id, "
            "created_at, updated_at, has_local_file, archived) "
            "VALUES (2, 'rekordbox', 'Legacy Track', 'Artist B', 'imported', 999, :now, :now, 0, 0)"
        ), {"now": now})

        # Playlist + membership che referenzia la track streaming (id=1).
        conn.execute(text(
            "INSERT INTO playlists (id, platform, name, track_count, kind, imported_at, "
            "created_at, updated_at) "
            "VALUES (1, 'spotify', 'My Playlist', 1, 'playlist', :now, :now, :now)"
        ), {"now": now})
        conn.execute(text(
            "INSERT INTO playlist_tracks (playlist_id, track_id, added_at) VALUES (1, 1, :now)"
        ), {"now": now})

        # Setlist + setlist_track che referenzia la track streaming (id=1).
        conn.execute(text(
            "INSERT INTO setlists (id, name, generated_by, validation, owned_only, "
            "created_at, updated_at) "
            "VALUES (1, 'My Set', 'algorithmic', '{}', 0, :now, :now)"
        ), {"now": now})
        conn.execute(text(
            "INSERT INTO setlist_tracks (id, setlist_id, track_id, position, created_at) "
            "VALUES (1, 1, 1, 0, :now)"
        ), {"now": now})

    return engine


def test_legacy_migration_is_fk_safe(tmp_path):
    db_path = tmp_path / "legacy.db"
    engine = _make_legacy_db(db_path)

    # Precondizione: il bug e' raggiungibile solo con FK davvero ON.
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1

    ensure_schema(engine)

    with engine.connect() as conn:
        # Le REFERENCES di playlist_tracks/setlist_tracks devono puntare a `tracks`,
        # mai al nome temporaneo del rebuild rotto.
        pt_sql = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE name='playlist_tracks'"
        )).scalar()
        assert "_tracks_legacy" not in pt_sql
        st_sql = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE name='setlist_tracks'"
        )).scalar()
        assert "_tracks_legacy" not in st_sql

        # Nessuna violazione FK residua.
        assert conn.execute(text("PRAGMA foreign_key_check")).fetchall() == []

        # Colonne legacy sparite.
        cols = {c["name"] for c in inspect(engine).get_columns("tracks")}
        assert "rekordbox_track_id" not in cols
        assert "tonality" not in cols

        # camelot_key coalesced dalla tonality legacy per la track streaming.
        row = conn.execute(text(
            "SELECT camelot_key, source_type FROM tracks WHERE id=1"
        )).one()
        assert row[0] == "8A"
        assert row[1] == "spotify"

        # Le righe figlie della track streaming sono intatte.
        assert conn.execute(text(
            "SELECT COUNT(*) FROM playlist_tracks WHERE track_id=1"
        )).scalar() == 1
        assert conn.execute(text(
            "SELECT COUNT(*) FROM setlist_tracks WHERE track_id=1"
        )).scalar() == 1

        # La track legacy (rekordbox) e' stata eliminata.
        assert conn.execute(text(
            "SELECT COUNT(*) FROM tracks WHERE source_type='rekordbox'"
        )).scalar() == 0

        # Nessuna tabella temporanea residua.
        assert not conn.execute(text(
            "SELECT 1 FROM sqlite_master WHERE name='_tracks_legacy'"
        )).first()

    # Idempotenza: un secondo run non deve cambiare lo schema.
    with engine.connect() as conn:
        schema_before = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
        )).fetchall()

    ensure_schema(engine)

    with engine.connect() as conn:
        schema_after = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
        )).fetchall()
        row = conn.execute(text(
            "SELECT camelot_key FROM tracks WHERE id=1"
        )).one()

    assert schema_before == schema_after
    assert row[0] == "8A"


def test_fresh_db_no_op(tmp_path):
    """Su un DB creato gia' dal modello corrente, _migrate_drop_legacy non deve
    fare nulla (nessuna colonna/tabella legacy da rimuovere)."""
    db_path = tmp_path / "fresh.db"
    engine = _make_engine(f"sqlite:///{db_path}")
    ensure_schema(engine)

    with engine.connect() as conn:
        schema_before = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
        )).fetchall()

    ensure_schema(engine)

    with engine.connect() as conn:
        schema_after = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
        )).fetchall()

    assert schema_before == schema_after


def test_leftover_tracks_legacy_recovery(tmp_path):
    """Simula un run vecchio-stile interrotto a meta': `_tracks_legacy` esiste gia'
    (RENAME avvenuto) e le tabelle figlie puntano gia' a `_tracks_legacy`. La
    migrazione deve fare recovery (RENAME back, self-healing delle REFERENCES) e
    completare senza corruzione.
    """
    db_path = tmp_path / "leftover.db"
    engine = _make_legacy_db(db_path)

    # Simula manualmente l'interruzione a meta' del vecchio pattern: rinomina
    # tracks -> _tracks_legacy (questo di per se' riscrive gia' le REFERENCES dei
    # figli, come verificato nello scratch repro).
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tracks RENAME TO _tracks_legacy"))

    with engine.connect() as conn:
        pt_sql = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE name='playlist_tracks'"
        )).scalar()
        assert "_tracks_legacy" in pt_sql  # precondizione: rewrite avvenuto

    ensure_schema(engine)

    with engine.connect() as conn:
        # Self-healing: le REFERENCES tornano a puntare a `tracks`.
        pt_sql = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE name='playlist_tracks'"
        )).scalar()
        assert "_tracks_legacy" not in pt_sql

        assert conn.execute(text("PRAGMA foreign_key_check")).fetchall() == []

        assert not conn.execute(text(
            "SELECT 1 FROM sqlite_master WHERE name='_tracks_legacy'"
        )).first()

        row = conn.execute(text(
            "SELECT camelot_key FROM tracks WHERE id=1"
        )).one()
        assert row[0] == "8A"

        assert conn.execute(text(
            "SELECT COUNT(*) FROM tracks WHERE source_type='rekordbox'"
        )).scalar() == 0
