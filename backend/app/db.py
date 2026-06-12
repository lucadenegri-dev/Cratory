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
    existing = {c["name"] for c in inspector.get_columns("tracks")}
    wanted = {
        "album_art_url": "TEXT",
        "spotify_artist_id": "VARCHAR",
        "enriched_at": "DATETIME",
    }
    with eng.begin() as conn:
        for col, ddl in wanted.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE tracks ADD COLUMN {col} {ddl}"))


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
