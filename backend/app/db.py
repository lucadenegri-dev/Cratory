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


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
