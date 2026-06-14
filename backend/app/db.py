from pathlib import Path

from sqlalchemy import create_engine, inspect, text
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
    return create_engine(url, connect_args=connect_args)


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
            "spotify_artist_id": "VARCHAR",
            "enriched_at": "DATETIME",
            # Pivot playlist->set: identita' streaming, playlist di provenienza, stato
            "platform": "VARCHAR",
            "platform_track_id": "VARCHAR",
            "isrc": "VARCHAR",
            "url": "TEXT",
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
        },
        "setlists": {
            "generated_by": "VARCHAR DEFAULT 'algorithmic'",
            "validation": "JSON",
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
        _relax_rekordbox_not_null(conn)


def _relax_rekordbox_not_null(conn) -> None:
    """Rende `tracks.rekordbox_track_id` nullable nei DB creati prima del pivot.

    In MVP 1 la colonna era `NOT NULL` (Rekordbox era la fonte primaria); col pivot
    e' diventata opzionale, ma SQLite non supporta ALTER COLUMN. Ricostruisce quindi
    la tabella preservando righe, indici e relazioni (setlist). Idempotente: dopo la
    prima esecuzione `notnull` e' 0 e la funzione esce subito.
    """
    info = conn.execute(text("PRAGMA table_info(tracks)")).fetchall()
    col = next((r for r in info if r[1] == "rekordbox_track_id"), None)
    if col is None or col[3] == 0:  # r[3] = flag notnull: gia' nullable o assente
        return
    create_sql = conn.execute(text(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='tracks'"
    )).scalar() or ""
    new_create = create_sql.replace(
        "rekordbox_track_id VARCHAR NOT NULL", "rekordbox_track_id VARCHAR"
    ).replace("CREATE TABLE tracks", "CREATE TABLE tracks_new", 1)
    if "tracks_new" not in new_create or "rekordbox_track_id VARCHAR NOT NULL" in new_create:
        return  # forma del DDL inattesa: non rischiare la migrazione automatica
    index_sqls = [r[0] for r in conn.execute(text(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='tracks' AND sql IS NOT NULL"
    )).fetchall()]
    collist = ", ".join(f'"{r[1]}"' for r in info)
    conn.execute(text(new_create))
    conn.execute(text(f"INSERT INTO tracks_new ({collist}) SELECT {collist} FROM tracks"))
    conn.execute(text("DROP TABLE tracks"))
    conn.execute(text("ALTER TABLE tracks_new RENAME TO tracks"))
    for isql in index_sqls:
        conn.execute(text(isql))


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
