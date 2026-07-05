from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url.startswith("sqlite:///"):
        db_path = Path(url.removeprefix("sqlite:///"))
        if not db_path.parent.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine(url, connect_args=connect_args)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return eng


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def ensure_schema(eng=None) -> None:
    """create_all + ALTER TABLE per colonne aggiunte dopo MVP 1 (niente Alembic: app locale)."""
    eng = eng or engine
    Base.metadata.create_all(eng)
    inspector = inspect(eng)
    # tabella -> {colonna: ddl} per colonne aggiunte dopo la creazione iniziale
    additions = {
        "tracks": {
            # MVP 2 (Spotify)
            "album_art_url": "TEXT",
            "enriched_at": "DATETIME",
            # Pivot playlist->set: identita' streaming, playlist di provenienza, stato
            "platform": "VARCHAR",
            "platform_track_id": "VARCHAR",
            "album_id": "VARCHAR",
            "isrc": "VARCHAR",
            "url": "TEXT",
            "local_path": "TEXT",
            "added_at": "DATETIME",
            "playlist_id": "INTEGER",
            "playlist_name": "VARCHAR",
            "status": "VARCHAR DEFAULT 'imported'",
            # Enrichment esterno (BPM/key/mood/energia/label/...)
            "genre_secondary": "VARCHAR",
            "release_date": "DATE",
            "label": "VARCHAR",
            "camelot_key": "VARCHAR",
            "mood": "VARCHAR",
            "energy": "INTEGER",
            "danceability": "INTEGER",
            "vocalness": "INTEGER",
            "enrichment_source": "VARCHAR",
            "enrichment_confidence": "INTEGER",
            # Ownership file locale (Soulseek download / import locale)
            "has_local_file": "BOOLEAN DEFAULT 0",
            "local_format": "VARCHAR",
            "local_bitrate": "INTEGER",
            "audio_hash": "VARCHAR",
            # Fingerprinting AcoustID (identita' acustica -> MusicBrainz)
            "mbid": "VARCHAR",
            # Scansione incrementale (Lotto A)
            "local_mtime": "FLOAT",
            "local_size": "INTEGER",
            # Scartate (Lotto B)
            "archived": "BOOLEAN DEFAULT 0",
            # Catena del genere (Lotto C)
            "genre_source": "VARCHAR",
            # Esiti download persistiti (sezione "da sistemare")
            "last_download_outcome": "VARCHAR",
            "last_download_reason": "VARCHAR",
        },
        "setlists": {
            "generated_by": "VARCHAR DEFAULT 'algorithmic'",
            "validation": "JSON",
            # Disk-first: i set pre-migrazione non hanno la garanzia "solo posseduti"
            "owned_only": "BOOLEAN DEFAULT 0",
        },
        "setlist_tracks": {
            "role": "VARCHAR",
            "transition_note": "TEXT",
        },
    }
    with eng.begin() as conn:
        for table, cols in additions.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for col, ddl in cols.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
        _migrate_drop_legacy(conn)
        _migrate_playlist_memberships(conn)


# Tabelle dell'era Rekordbox/MVP1 rimosse dopo il pivot a playlist->set.
_LEGACY_TABLES = ("beatgrid_points", "cue_points", "artists", "import_reports")
# source_type delle righe Rekordbox/locali, non piu' previste dal nuovo flusso.
_LEGACY_SOURCES = ("local", "rekordbox")


def _table_exists(conn, name: str) -> bool:
    return bool(conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"), {"n": name}
    ).first())


def _migrate_drop_legacy(conn) -> None:
    """Ripulisce i DB pre-pivot: rimuove colonne/tabelle Rekordbox e le righe legacy.

    SQLite non supporta ALTER/DROP COLUMN affidabile con indici, quindi `tracks` viene
    ricostruita dal modello corrente copiando le sole colonne sopravvissute (con
    `camelot_key` = COALESCE(camelot_key, tonality) per non perdere la key). Le tabelle
    e le righe dell'era Rekordbox vengono eliminate; i set che restano senza tracce
    vengono potati.

    Robusta agli interrupt: SQLite auto-committa il DDL, quindi la funzione e' scritta
    per riprendere anche da un rebuild lasciato a meta' (tabella `_tracks_legacy`
    presente, indici orfani) ed e' idempotente quando non c'e' nulla di legacy.
    """
    from app.models import Track  # import differito: models importa db.Base

    cols = [r[1] for r in conn.execute(text("PRAGMA table_info(tracks)")).fetchall()]
    tracks_is_legacy = bool(cols) and ("rekordbox_track_id" in cols or "play_count" in cols)
    legacy_leftover = _table_exists(conn, "_tracks_legacy")
    if not tracks_is_legacy and not legacy_leftover:
        return

    if tracks_is_legacy:
        conn.execute(text("DROP TABLE IF EXISTS _tracks_legacy"))
        conn.execute(text("ALTER TABLE tracks RENAME TO _tracks_legacy"))

    # Gli indici seguono la tabella nel RENAME mantenendo il vecchio nome (ix_tracks_*):
    # vanno eliminati o la ricreazione di `tracks` fallisce con "index ... already exists".
    for (idx,) in conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='_tracks_legacy' AND sql IS NOT NULL"
    )).fetchall():
        conn.execute(text(f'DROP INDEX IF EXISTS "{idx}"'))

    conn.execute(text("DROP TABLE IF EXISTS tracks"))  # eventuale tracks vuota di un run interrotto
    Track.__table__.create(conn)  # schema + indici dal modello corrente

    legacy_cols = [r[1] for r in conn.execute(text("PRAGMA table_info(_tracks_legacy)")).fetchall()]
    shared = [c for c in Track.__table__.columns.keys() if c in legacy_cols]
    exprs = [
        "COALESCE(camelot_key, tonality)" if c == "camelot_key" and "tonality" in legacy_cols else f'"{c}"'
        for c in shared
    ]
    collist = ", ".join(f'"{c}"' for c in shared)
    conn.execute(text(f"INSERT INTO tracks ({collist}) SELECT {', '.join(exprs)} FROM _tracks_legacy"))
    conn.execute(text("DROP TABLE _tracks_legacy"))

    for tbl in _LEGACY_TABLES:
        conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))

    # Righe e set dell'era Rekordbox: elimina le tracce local/rekordbox, poi le voci di
    # set orfane e i set rimasti senza tracce (i set "veri" su tracce streaming restano).
    legacy_src = ", ".join(f"'{s}'" for s in _LEGACY_SOURCES)
    conn.execute(text(f"DELETE FROM tracks WHERE source_type IN ({legacy_src})"))
    conn.execute(text("DELETE FROM setlist_tracks WHERE track_id NOT IN (SELECT id FROM tracks)"))
    conn.execute(text("DELETE FROM setlists WHERE id NOT IN (SELECT setlist_id FROM setlist_tracks)"))


def _migrate_playlist_memberships(conn) -> None:
    """Backfill M2M: copia Track.playlist_id nelle membership, poi svuota le colonne legacy.

    Idempotente: INSERT OR IGNORE non duplica; dopo lo svuotamento non ci sono piu'
    righe con playlist_id valorizzato, quindi le esecuzioni successive sono no-op.
    """
    if not _table_exists(conn, "playlist_tracks"):
        return
    cols = [r[1] for r in conn.execute(text("PRAGMA table_info(tracks)")).fetchall()]
    if "playlist_id" not in cols:
        return
    conn.execute(text(
        "INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id, added_at) "
        "SELECT playlist_id, id, added_at FROM tracks WHERE playlist_id IS NOT NULL"
    ))
    conn.execute(text(
        "UPDATE tracks SET playlist_id = NULL, playlist_name = NULL WHERE playlist_id IS NOT NULL"
    ))


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
